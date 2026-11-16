from __future__ import annotations

from dataclasses import dataclass
from math import floor, isclose
from numbers import Integral
from pathlib import Path

from netCDF4 import Dataset, num2date

from .trajectory_provenance import (
    TrajectoryProvenance,
    read_trajectory_provenance,
)
from .environment_export import ENVIRONMENT_EXPORT_CATALOGUE


@dataclass(frozen=True, slots=True)
class EnvironmentalVariableMetadata:
    name: str
    units: str
    long_name: str
    standard_name: str
    available_file_count: int


@dataclass(frozen=True, slots=True)
class TrajectoryFileMetadata:
    path: Path
    provenance: TrajectoryProvenance
    trajectory_count: int
    time_count: int
    output_interval_seconds: float
    max_positions_per_drift_day: int
    environmental_variables: tuple[EnvironmentalVariableMetadata, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultsInspectionIssue:
    path: Path
    level: str
    message: str


@dataclass(frozen=True, slots=True)
class ResultsInspection:
    files: tuple[TrajectoryFileMetadata, ...]
    issues: tuple[ResultsInspectionIssue, ...]
    observation_dataset: Path
    identifier_column: str
    total_file_count: int

    @property
    def environmental_variables(self) -> dict[str, EnvironmentalVariableMetadata]:
        grouped: dict[str, list[EnvironmentalVariableMetadata]] = {}
        for file in self.files:
            for variable in file.environmental_variables:
                grouped.setdefault(variable.name, []).append(variable)
        return {
            name: EnvironmentalVariableMetadata(
                name=name,
                units=values[0].units,
                long_name=values[0].long_name,
                standard_name=values[0].standard_name,
                available_file_count=len(values),
            )
            for name, values in grouped.items()
        }

    @property
    def common_environmental_variables(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, item in self.environmental_variables.items() if item.available_file_count == len(self.files)))

    @property
    def partial_environmental_variables(self) -> tuple[str, ...]:
        return tuple(sorted(name for name, item in self.environmental_variables.items() if item.available_file_count < len(self.files)))

    @property
    def accepted_file_count(self) -> int:
        return len(self.files)

    @property
    def simulation_count(self) -> int:
        return len(self.files)

    @property
    def particle_trajectory_count(self) -> int:
        return sum(file.trajectory_count for file in self.files)

    @property
    def unique_identifiers(self) -> tuple[str, ...]:
        return tuple(sorted({file.provenance.stranding_identifier for file in self.files}))

    @property
    def minimum_output_interval_seconds(self) -> float:
        return min(file.output_interval_seconds for file in self.files)

    @property
    def max_positions_per_drift_day(self) -> int:
        return min(file.max_positions_per_drift_day for file in self.files)

    @property
    def observation_dataset_available(self) -> bool:
        return self.observation_dataset.is_file()

    def estimated_rows(self, positions_per_drift_day: int) -> int:
        return sum(
            file.trajectory_count
            * file.provenance.reverse_drift_duration_days
            * positions_per_drift_day
            for file in self.files
        )


class ResultsInspectionError(ValueError):
    """Raised when a results directory cannot provide one compatible export set."""


def inspect_results_directory(
    path: Path | str,
    *,
    observation_dataset_override: Path | None = None,
    progress_callback=None,
) -> ResultsInspection:
    """Inspect top-level Workbench trajectories without loading trajectory arrays."""
    directory = Path(path)
    files = tuple(sorted(directory.glob("*.nc"))) if directory.is_dir() else ()
    accepted: list[TrajectoryFileMetadata] = []
    issues: list[ResultsInspectionIssue] = []

    for index, file_path in enumerate(files, 1):
        try:
            provenance = read_trajectory_provenance(file_path)
            accepted.append(_read_file_metadata(file_path, provenance))
        except (OSError, RuntimeError, ValueError) as exc:
            issues.append(
                ResultsInspectionIssue(
                    path=file_path,
                    level="warning",
                    message=str(exc),
                )
            )
        if progress_callback and (index == 1 or index % 100 == 0 or index == len(files)):
            progress_callback({"event": "map_inspecting", "completed": index, "total": len(files)})

    if not accepted:
        raise ResultsInspectionError(
            f"No valid Marine Drift Workbench trajectory files found in `{directory}`."
        )

    observation_datasets = {file.provenance.observation_dataset for file in accepted}
    if len(observation_datasets) != 1 and observation_dataset_override is None:
        raise ResultsInspectionError(
            "Valid trajectory files disagree on their embedded observation dataset."
        )
    if len(observation_datasets) != 1:
        issues.append(
            ResultsInspectionIssue(
                path=directory,
                level="warning",
                message="Trajectory files reference different observation datasets; the selected override will be used.",
            )
        )
    identifier_columns = {file.provenance.identifier_column for file in accepted}
    if len(identifier_columns) != 1:
        raise ResultsInspectionError(
            "Valid trajectory files disagree on their embedded identifier column."
        )

    return ResultsInspection(
        files=tuple(accepted),
        issues=tuple(issues),
        observation_dataset=observation_dataset_override or next(iter(observation_datasets)),
        identifier_column=next(iter(identifier_columns)),
        total_file_count=len(files),
    )


def validate_sampling_capacity(
    inspection: ResultsInspection,
    positions_per_drift_day: int,
) -> None:
    """Reject densities that cannot be represented by every accepted trajectory."""
    if isinstance(positions_per_drift_day, bool) or not isinstance(
        positions_per_drift_day, Integral
    ):
        raise ValueError("Positions per drift day must be an integer.")
    if positions_per_drift_day < 1:
        raise ValueError("Positions per drift day must be at least 1.")
    if positions_per_drift_day > inspection.max_positions_per_drift_day:
        raise ValueError(
            "Positions per drift day exceeds the available output frequency."
        )


def _read_file_metadata(
    path: Path,
    provenance: TrajectoryProvenance,
) -> TrajectoryFileMetadata:
    with Dataset(path) as dataset:
        required_variables = ("time", "lon", "lat")
        for name in required_variables:
            if name not in dataset.variables:
                raise ValueError(f"Missing required variable `{name}`.")

        time = dataset.variables["time"]
        lon = dataset.variables["lon"]
        lat = dataset.variables["lat"]
        _validate_trajectory_dimensions(lon, lat, time)
        output_interval_seconds = _read_regular_interval_seconds(time)
        trajectory_count = int(lon.shape[0])
        time_count = int(time.shape[0])
        environmental_variables = tuple(
            EnvironmentalVariableMetadata(
                name=name,
                units=str(getattr(variable, "units", "")),
                long_name=str(getattr(variable, "long_name", "")),
                standard_name=str(getattr(variable, "standard_name", "")),
                available_file_count=1,
            )
            for name, variable in dataset.variables.items()
            if name in ENVIRONMENT_EXPORT_CATALOGUE
            and variable.dimensions == ("trajectory", "time")
            and variable.shape == lon.shape
        )

    return TrajectoryFileMetadata(
        path=path,
        provenance=provenance,
        trajectory_count=trajectory_count,
        time_count=time_count,
        output_interval_seconds=output_interval_seconds,
        max_positions_per_drift_day=floor(86_400 / output_interval_seconds),
        environmental_variables=environmental_variables,
    )


def _validate_trajectory_dimensions(
    lon: object,
    lat: object,
    time: object,
) -> None:
    if time.dimensions != ("time",) or len(time.shape) != 1:
        raise ValueError("Variable `time` must be one-dimensional on `time`.")
    if lon.dimensions != ("trajectory", "time") or lat.dimensions != (
        "trajectory",
        "time",
    ):
        raise ValueError("Variables `lon` and `lat` must share a trajectory x time shape.")
    if lon.shape != lat.shape or lon.shape[1] != time.shape[0] or lon.shape[0] < 1:
        raise ValueError("Variables `lon` and `lat` must share a trajectory x time shape.")


def _read_regular_interval_seconds(time: object) -> float:
    if time.shape[0] < 2:
        raise ValueError("Variable `time` must contain at least two regular values.")
    if not hasattr(time, "units"):
        raise ValueError("Variable `time` must define CF time units.")

    try:
        timestamps = num2date(
            time[:],
            units=time.units,
            calendar=getattr(time, "calendar", "standard"),
        )
        intervals = [
            (timestamps[index + 1] - timestamps[index]).total_seconds()
            for index in range(len(timestamps) - 1)
        ]
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Variable `time` must contain decodable CF timestamps.") from exc

    interval = intervals[0]
    if interval == 0 or any(
        value == 0
        or value * interval < 0
        or not isclose(value, interval, rel_tol=1e-9, abs_tol=1e-6)
        for value in intervals
    ):
        raise ValueError("Variable `time` must be strictly monotonic with regular spacing.")

    interval_seconds = abs(float(interval))
    if interval_seconds > 86_400:
        raise ValueError("Variable `time` output interval exceeds one day.")
    return interval_seconds
