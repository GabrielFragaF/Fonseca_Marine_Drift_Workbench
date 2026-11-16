from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from datetime import datetime
from numbers import Integral, Real
from pathlib import Path

from ..domain.models import (
    CanonicalObservation,
    SimulationIterationPlan,
    SimulationRequest,
)
from .planning import stranding_event_token


PROVENANCE_SCHEMA_VERSION = 1
_ATTRIBUTE_PREFIX = "marine_drift_"
_OUTPUT_TYPE = "trajectory"


@dataclass(frozen=True, slots=True)
class TrajectoryProvenance:
    schema_version: int
    output_type: str
    stranding_identifier: str
    taxon_label: str
    decomposition_code: int
    observed_at: datetime
    reverse_drift_duration_days: int
    wind_drift_factor: float
    iteration_index: int
    simulation_start_time: datetime
    particles_per_release: int
    observation_dataset: Path
    identifier_column: str
    environment_export_variables: tuple[str, ...] = ()
    fallback_values: dict[str, object] = field(default_factory=dict)
    decomposition_state: str = ""
    event_token: str = ""


def write_trajectory_provenance(
    path: Path | str,
    observation: CanonicalObservation,
    iteration: SimulationIterationPlan,
    request: SimulationRequest,
) -> None:
    """Stamp a completed trajectory NetCDF without modifying its variables."""
    from netCDF4 import Dataset

    observation_dataset = request.data_sources.observation_dataset
    if observation_dataset is None:
        raise ValueError("Trajectory provenance requires an observation dataset path.")

    attributes = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "output_type": _OUTPUT_TYPE,
        "stranding_identifier": observation.stranding_identifier,
        "event_token": stranding_event_token(observation),
        "taxon_label": observation.taxon_label,
        "decomposition_code": observation.decomposition_code,
        "decomposition_state": next(
            (label for label, code in request.settings.duration.decomposition_value_map.items()
             if code == observation.decomposition_code),
            str(observation.decomposition_code),
        ),
        "observed_at": observation.observed_at.isoformat(),
        "reverse_drift_duration_days": observation.reverse_drift_duration_days,
        "wind_drift_factor": observation.wind_drift_factor,
        "iteration_index": iteration.iteration_index,
        "simulation_start_time": iteration.start_time.isoformat(),
        "particles_per_release": request.settings.particle_count,
        "observation_dataset": str(observation_dataset),
        "identifier_column": request.column_mapping.stranding_identifier,
        "environment_export_variables": json.dumps(
            request.settings.environment_export_variables, sort_keys=True
        ),
        "fallback_values": json.dumps(
            asdict(request.settings.fallback_values), sort_keys=True
        ),
    }
    with Dataset(path, "a") as dataset:
        for name, value in attributes.items():
            dataset.setncattr(f"{_ATTRIBUTE_PREFIX}{name}", value)


def read_trajectory_provenance(path: Path | str) -> TrajectoryProvenance:
    """Read and validate marine-drift trajectory provenance attributes."""
    from netCDF4 import Dataset

    with Dataset(path) as dataset:
        schema_version = _read_integer(
            {"schema_version": _read_attribute(dataset, "schema_version")},
            "schema_version",
        )
        if schema_version != PROVENANCE_SCHEMA_VERSION:
            raise ValueError(
                "Incompatible trajectory provenance schema version: "
                f"{schema_version!r}."
            )
        output_type = _read_string(
            {"output_type": _read_attribute(dataset, "output_type")},
            "output_type",
        )
        if output_type != _OUTPUT_TYPE:
            raise ValueError(
                "Incompatible trajectory provenance output type: "
                f"{output_type!r}."
            )
        attributes = _read_required_attributes(dataset)

    return TrajectoryProvenance(
        schema_version=schema_version,
        output_type=output_type,
        stranding_identifier=_read_string(attributes, "stranding_identifier"),
        taxon_label=_read_string(attributes, "taxon_label"),
        decomposition_code=_read_integer(attributes, "decomposition_code"),
        observed_at=_read_datetime(attributes, "observed_at"),
        reverse_drift_duration_days=_read_integer(
            attributes, "reverse_drift_duration_days"
        ),
        wind_drift_factor=_read_float(attributes, "wind_drift_factor"),
        iteration_index=_read_integer(attributes, "iteration_index"),
        simulation_start_time=_read_datetime(attributes, "simulation_start_time"),
        particles_per_release=_read_integer(attributes, "particles_per_release"),
        observation_dataset=Path(_read_string(attributes, "observation_dataset")),
        identifier_column=_read_string(attributes, "identifier_column"),
        environment_export_variables=tuple(json.loads(str(
            _read_optional_attribute(dataset_path=path, name="environment_export_variables", default="[]")
        ))),
        fallback_values=dict(json.loads(str(
            _read_optional_attribute(dataset_path=path, name="fallback_values", default="{}")
        ))),
        decomposition_state=str(_read_optional_attribute(
            dataset_path=path, name="decomposition_state",
            default=str(_read_integer(attributes, "decomposition_code")),
        )),
        event_token=str(_read_optional_attribute(dataset_path=path, name="event_token", default="")),
    )


def _read_optional_attribute(
    *, dataset_path: Path | str, name: str, default: object
) -> object:
    from netCDF4 import Dataset

    with Dataset(dataset_path) as dataset:
        attribute_name = f"{_ATTRIBUTE_PREFIX}{name}"
        return dataset.getncattr(attribute_name) if attribute_name in dataset.ncattrs() else default


def _read_required_attributes(dataset: object) -> dict[str, object]:
    names = (
        "schema_version",
        "output_type",
        "stranding_identifier",
        "taxon_label",
        "decomposition_code",
        "observed_at",
        "reverse_drift_duration_days",
        "wind_drift_factor",
        "iteration_index",
        "simulation_start_time",
        "particles_per_release",
        "observation_dataset",
        "identifier_column",
    )
    return {name: _read_attribute(dataset, name) for name in names}


def _read_attribute(dataset: object, name: str) -> object:
    attribute_name = f"{_ATTRIBUTE_PREFIX}{name}"
    if attribute_name not in dataset.ncattrs():
        if name == "schema_version":
            raise ValueError("NetCDF file is unmarked with marine-drift provenance.")
        raise ValueError(
            "Incompatible trajectory provenance: missing required attribute "
            f"`{attribute_name}`."
        )
    return dataset.getncattr(attribute_name)


def _read_string(attributes: dict[str, object], name: str) -> str:
    value = attributes[name]
    if not isinstance(value, str):
        raise ValueError(f"Incompatible trajectory provenance: `{name}` must be text.")
    return value


def _read_integer(attributes: dict[str, object], name: str) -> int:
    value = attributes[name]
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"Incompatible trajectory provenance: `{name}` must be an integer.")
    return int(value)


def _read_float(attributes: dict[str, object], name: str) -> float:
    value = attributes[name]
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"Incompatible trajectory provenance: `{name}` must be numeric.")
    return float(value)


def _read_datetime(attributes: dict[str, object], name: str) -> datetime:
    from .timestamps import utc_naive
    value = _read_string(attributes, name)
    try:
        return utc_naive(datetime.fromisoformat(value))
    except ValueError as exc:
        raise ValueError(
            f"Incompatible trajectory provenance: `{name}` must be ISO 8601 text."
        ) from exc
