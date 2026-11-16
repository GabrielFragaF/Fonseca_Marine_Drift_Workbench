from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from numbers import Integral
from pathlib import Path
from typing import Iterator

import numpy as np
from netCDF4 import Dataset, num2date

from .results_inspection import TrajectoryFileMetadata
from .results_source import (
    SourceObservationLookup,
    normalize_stranding_identifier,
    select_source_observation_row,
)


_MATCH_TOLERANCE_HOURS = 1e-6
_GENERATED_FIELDS = frozenset(
    {
        "stranding_identifier",
        "taxon_label",
        "decomposition_code",
        "decomposition_state",
        "observed_at",
        "drift_duration_days",
        "simulation_iteration",
        "particle_index",
        "sample_index",
        "positions_per_drift_day",
        "drift_day",
        "hours_before_stranding",
        "actual_time",
        "mortality_longitude",
        "mortality_latitude",
        "status",
        "source_file",
        "weight",
    }
)


@dataclass(frozen=True, slots=True)
class SampleTarget:
    time_index: int
    sample_index: int
    drift_day: int
    hours_before_stranding: float


def select_sample_targets(
    times: Sequence[object],
    *,
    duration_days: int,
    positions_per_day: int,
) -> tuple[SampleTarget, ...]:
    """Match evenly spaced reverse-drift targets to unique exported times."""
    if isinstance(duration_days, bool) or not isinstance(duration_days, Integral):
        raise ValueError("duration_days must be an integer.")
    if duration_days < 1:
        raise ValueError("duration_days must be at least 1.")
    if isinstance(positions_per_day, bool) or not isinstance(
        positions_per_day, Integral
    ):
        raise ValueError("positions_per_day must be an integer.")
    if positions_per_day < 1:
        raise ValueError("positions_per_day must be at least 1.")

    elapsed_hours = _elapsed_hours(times)
    output_interval_hours = _regular_output_interval_hours(elapsed_hours)
    targets: list[SampleTarget] = []
    used_indices: set[int] = set()

    for drift_day in range(1, duration_days + 1):
        for position in range(1, positions_per_day + 1):
            ideal_hours = (drift_day - 1) * 24.0 + position * 24.0 / positions_per_day
            time_index = min(
                range(len(elapsed_hours)),
                key=lambda index: (abs(elapsed_hours[index] - ideal_hours), index),
            )
            actual_hours = elapsed_hours[time_index]
            if time_index == 0:
                raise ValueError("Sample targets must exclude reverse-drift offset zero.")
            if abs(actual_hours - ideal_hours) > output_interval_hours / 2 + _MATCH_TOLERANCE_HOURS:
                raise ValueError("Sample target is outside the exported-time tolerance.")
            if time_index in used_indices:
                raise ValueError(
                    "Requested positions per drift day cannot provide unique exported times."
                )
            used_indices.add(time_index)
            targets.append(
                SampleTarget(
                    time_index=time_index,
                    sample_index=len(targets),
                    drift_day=drift_day,
                    hours_before_stranding=float(actual_hours),
                )
            )

    return tuple(targets)


def iter_sampled_positions(
    metadata: TrajectoryFileMetadata,
    *,
    positions_per_day: int,
    source_lookup: Mapping[str, dict[str, object]] | None = None,
    omitted_position_counter: Callable[[], None] | None = None,
    missing_source_callback: Callable[[str], None] | None = None,
    environmental_variables: Sequence[str] = (),
) -> Iterator[dict[str, object]]:
    """Yield valid sampled particle positions while opening one NetCDF file."""
    with Dataset(metadata.path) as dataset:
        time = dataset.variables["time"]
        decoded_times = num2date(
            time[:],
            units=time.units,
            calendar=getattr(time, "calendar", "standard"),
        )
        targets = select_sample_targets(
            decoded_times,
            duration_days=metadata.provenance.reverse_drift_duration_days,
            positions_per_day=positions_per_day,
        )
        longitude = dataset.variables["lon"]
        latitude = dataset.variables["lat"]
        status = dataset.variables.get("status")
        environment = {
            name: dataset.variables.get(name)
            for name in environmental_variables
        }
        for name, variable in environment.items():
            if variable is not None and variable.shape != longitude.shape:
                raise ValueError(
                    f"Environmental variable `{name}` must share the trajectory x time shape."
                )
        if status is not None and status.shape != longitude.shape:
            raise ValueError("Optional `status` must share the trajectory x time shape.")

        normalized_identifier = normalize_stranding_identifier(
            metadata.provenance.stranding_identifier
        )
        source_row = _source_row_for(
            metadata,
            source_lookup,
            missing_source_callback=missing_source_callback,
        )
        for particle_index in range(metadata.trajectory_count):
            for target in targets:
                longitude_value = longitude[particle_index, target.time_index]
                latitude_value = latitude[particle_index, target.time_index]
                if not _is_finite_coordinate(longitude_value) or not _is_finite_coordinate(
                    latitude_value
                ):
                    if omitted_position_counter is not None:
                        omitted_position_counter()
                    continue
                generated = {
                    "stranding_identifier": normalized_identifier,
                    "taxon_label": metadata.provenance.taxon_label,
                    "decomposition_code": metadata.provenance.decomposition_code,
                    "decomposition_state": (
                        metadata.provenance.decomposition_state
                        or str(metadata.provenance.decomposition_code)
                    ),
                    "observed_at": metadata.provenance.observed_at.isoformat(),
                    "drift_duration_days": metadata.provenance.reverse_drift_duration_days,
                    "simulation_iteration": metadata.provenance.iteration_index,
                    "particle_index": particle_index,
                    "sample_index": target.sample_index,
                    "positions_per_drift_day": positions_per_day,
                    "drift_day": target.drift_day,
                    "hours_before_stranding": hours_before_observation(
                        decoded_times[target.time_index],
                        metadata.provenance.observed_at,
                    ),
                    "actual_time": _format_time(decoded_times[target.time_index]),
                    "mortality_longitude": float(longitude_value),
                    "mortality_latitude": float(latitude_value),
                    "source_file": str(metadata.path),
                }
                if status is not None:
                    generated["status"] = _to_python_scalar(
                        status[particle_index, target.time_index]
                    )
                for name, variable in environment.items():
                    generated[name] = (
                        None
                        if variable is None
                        else _nullable_scalar(variable[particle_index, target.time_index])
                    )
                yield _merge_source_row(source_row, generated)


def _nullable_scalar(value: object) -> object | None:
    if np.ma.is_masked(value):
        return None
    converted = _to_python_scalar(value)
    if isinstance(converted, (float, np.floating)) and not np.isfinite(converted):
        return None
    return converted


def _elapsed_hours(times: Sequence[object]) -> list[float]:
    if len(times) < 2:
        raise ValueError("At least two exported times are required for sampling.")
    first = times[0]
    offsets = [_seconds_between(value, first) for value in times]
    if offsets[0] != 0.0 or any(value == 0.0 for value in offsets[1:]):
        raise ValueError("Exported times must start at one unique stranding time.")
    if any(value > 0.0 for value in offsets[1:]):
        raise ValueError(
            "Reverse-drift timestamps must represent times before stranding."
        )
    return [-value / 3600.0 for value in offsets]


def _regular_output_interval_hours(elapsed_hours: Sequence[float]) -> float:
    interval = elapsed_hours[1] - elapsed_hours[0]
    if interval <= 0 or any(
        abs((elapsed_hours[index + 1] - elapsed_hours[index]) - interval)
        > _MATCH_TOLERANCE_HOURS
        for index in range(len(elapsed_hours) - 1)
    ):
        raise ValueError("Exported times must be regularly spaced away from stranding.")
    return interval


def _seconds_between(value: object, first: object) -> float:
    if isinstance(value, np.datetime64) or isinstance(first, np.datetime64):
        return float((value - first) / np.timedelta64(1, "s"))
    delta = value - first  # type: ignore[operator]
    return float(delta.total_seconds())


def hours_before_observation(actual_time: object, observed_at: datetime) -> float:
    """Return signed elapsed hours from a trajectory position to observation."""
    return _seconds_between(observed_at, actual_time) / 3600.0


def _source_row_for(
    metadata: TrajectoryFileMetadata,
    source_lookup: Mapping[str, dict[str, object]] | None,
    *,
    missing_source_callback: Callable[[str], None] | None,
) -> dict[str, object]:
    if source_lookup is None:
        return {}
    identifier = normalize_stranding_identifier(metadata.provenance.stranding_identifier)
    if isinstance(source_lookup, SourceObservationLookup):
        row = select_source_observation_row(
            source_lookup, identifier, metadata.provenance.observed_at
        )
    else:
        row = source_lookup.get(identifier)
    if row is not None:
        return row
    if missing_source_callback is not None:
        missing_source_callback(identifier)
    columns = getattr(source_lookup, "columns", ())
    return {str(column): "" for column in columns}


def _merge_source_row(
    source_row: Mapping[str, object],
    generated: dict[str, object],
) -> dict[str, object]:
    row = dict(generated)
    used_names = set(_GENERATED_FIELDS)
    for column, value in source_row.items():
        name = str(column)
        while name in used_names:
            name = f"source_{name}"
        row[name] = value
        used_names.add(name)
    return row


def _is_finite_coordinate(value: object) -> bool:
    if np.ma.is_masked(value):
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _format_time(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _to_python_scalar(value: object) -> object:
    item = getattr(value, "item", None)
    return item() if callable(item) else value
