from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class ColumnMapping:
    stranding_identifier: str = ""
    taxon_label: str = ""
    decomposition_code: str = ""
    sea_surface_temperature: str = ""
    wind_drift_factor: str = ""
    longitude: str = ""
    latitude: str = ""
    datetime_mode: Literal["separate", "combined"] = "separate"
    observed_date: str = ""
    observed_time: str = ""
    observed_datetime: str = ""
    input_timezone: str = "as_recorded"

    def as_dict(self) -> dict[str, str]:
        return {
            "stranding_identifier": self.stranding_identifier,
            "taxon_label": self.taxon_label,
            "decomposition_code": self.decomposition_code,
            "sea_surface_temperature": self.sea_surface_temperature,
            "wind_drift_factor": self.wind_drift_factor,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "observed_date": self.observed_date,
            "observed_time": self.observed_time,
            "observed_datetime": self.observed_datetime,
        }


@dataclass(slots=True)
class DataSourcePaths:
    observation_dataset: Path | None = None
    output_directory: Path | None = None
    bathymetry: Path | None = None
    biogeochemistry_primary: Path | None = None
    biogeochemistry_secondary: Path | None = None
    currents_primary: Path | None = None
    currents_secondary: Path | None = None
    waves_primary: Path | None = None
    waves_secondary: Path | None = None
    wind_primary: Path | None = None
    wind_secondary: Path | None = None
    environment_readers: list["EnvironmentalReaderConfig"] = field(default_factory=list)

    def input_sources(self) -> dict[str, Path | None]:
        return {
            "observation_dataset": self.observation_dataset,
            "bathymetry": self.bathymetry,
            "biogeochemistry_primary": self.biogeochemistry_primary,
            "biogeochemistry_secondary": self.biogeochemistry_secondary,
            "currents_primary": self.currents_primary,
            "currents_secondary": self.currents_secondary,
            "waves_primary": self.waves_primary,
            "waves_secondary": self.waves_secondary,
            "wind_primary": self.wind_primary,
            "wind_secondary": self.wind_secondary,
        }


@dataclass(slots=True)
class EnvironmentalReaderConfig:
    path: Path
    roles: list[str] = field(default_factory=list)
    recognized_variables: list[str] = field(default_factory=list)
    role_source: Literal["auto", "user", "needs_review"] = "needs_review"
    group_id: str = ""
    priority: int = 0


@dataclass(slots=True)
class SpatialExtent:
    min_longitude: float = -180.0
    max_longitude: float = 180.0
    min_latitude: float = -90.0
    max_latitude: float = 90.0

    def is_valid(self) -> bool:
        return (
            self.min_longitude < self.max_longitude
            and self.min_latitude < self.max_latitude
        )


@dataclass(slots=True)
class FallbackValues:
    currents_enabled: bool = False
    wind_enabled: bool = False
    stokes_drift_enabled: bool = False
    seafloor_depth_enabled: bool = False
    x_sea_water_velocity: float = 0.0
    y_sea_water_velocity: float = 0.0
    x_wind: float = 0.0
    y_wind: float = 0.0
    stokes_drift_x_velocity: float = 0.0
    stokes_drift_y_velocity: float = 0.0
    sea_floor_depth_below_sea_level: float = 25.0


@dataclass(slots=True)
class WindDriftSettings:
    """User-facing windage configuration, stored internally as a fraction."""

    mode: Literal["none", "dataset", "fixed", "measurement"] = "dataset"
    source_scale: Literal["fraction", "percent"] = "fraction"
    fixed_percent: float = 1.5
    measurement_column: str = ""
    measurement_unit: Literal["meters", "centimeters"] = "meters"
    measurement_minimum: float = 0.0
    measurement_maximum: float = 1.0
    wind_drift_minimum_percent: float = 0.0
    wind_drift_maximum_percent: float = 1.5
    outside_range_behavior: Literal["clamp", "extrapolate"] = "clamp"


@dataclass(slots=True)
class DurationSettings:
    mode: Literal["fixed", "estimated", "dataset"] = "estimated"
    fixed_days: int = 7
    duration_column: str = ""
    temperature_threshold_celsius: float = 24.0
    cool_water_days: dict[int, int] = field(
        default_factory=lambda: {1: 2, 2: 3, 3: 4, 4: 7, 5: 12}
    )
    warm_water_days: dict[int, int] = field(
        default_factory=lambda: {1: 2, 2: 2, 3: 3, 4: 6, 5: 8}
    )
    # New profiles can use any number of ordered temperature boundaries.  The
    # legacy two-table fields above remain so existing saved projects still load.
    temperature_boundaries_celsius: list[float] = field(default_factory=lambda: [24.0])
    scenario_days: dict[int, list[int]] = field(default_factory=dict)
    decomposition_value_map: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class CoverageSettings:
    mode: Literal["manual", "environment_intersection"] = "manual"
    buffer_degrees: float = 0.0
    contributing_paths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PositionSearchSettings:
    mode: Literal["direct", "search_nearby_water", "skip_if_invalid"] = "direct"
    radial_step_degrees: float = 0.01
    max_radius_degrees: float = 0.5
    angle_step_degrees: int = 10
    max_attempts: int = 5000
    failure_behavior: Literal["skip", "stop"] = "skip"


@dataclass(slots=True)
class FilterCondition:
    column: str = ""
    operator: str = "equals"
    value: str | float | int | None = None
    values: list[str] = field(default_factory=list)
    connector: Literal["and", "or"] = "and"


@dataclass(slots=True)
class ObservationSelectionSettings:
    mode: Literal["all", "random", "filter"] = "all"
    sample_size: int = 0
    random_seed: int = 0
    conditions: list[FilterCondition] = field(default_factory=list)


@dataclass(slots=True)
class SimulationSettings:
    iteration_count: int = 15
    iteration_interval_hours: float = 1.0
    model_time_step_hours: float = 1.0
    start_time_mode: Literal["observation_time", "fixed_hour"] = "observation_time"
    fixed_start_hour: int = 0
    particle_count: int = 1
    release_radius_meters: float = 0.0
    current_uncertainty_enabled: bool = True
    current_uncertainty: float = 0.05
    wind_uncertainty_enabled: bool = True
    wind_uncertainty: float = 0.10
    job_error_policy: Literal["continue", "stop"] = "continue"
    coastline_action: str = "previous"
    environment_export_variables: list[str] = field(default_factory=list)
    coordinate_format: Literal["decimal_degrees", "degrees_minutes_seconds"] = (
        "decimal_degrees"
    )
    extent: SpatialExtent = field(default_factory=SpatialExtent)
    fallback_values: FallbackValues = field(default_factory=FallbackValues)
    wind_drift: WindDriftSettings = field(default_factory=WindDriftSettings)
    duration: DurationSettings = field(default_factory=DurationSettings)
    coverage: CoverageSettings = field(default_factory=CoverageSettings)
    position_search: PositionSearchSettings = field(default_factory=PositionSearchSettings)
    observation_selection: ObservationSelectionSettings = field(
        default_factory=ObservationSelectionSettings
    )


@dataclass(slots=True)
class SimulationRequest:
    data_sources: DataSourcePaths = field(default_factory=DataSourcePaths)
    column_mapping: ColumnMapping = field(default_factory=ColumnMapping)
    settings: SimulationSettings = field(default_factory=SimulationSettings)


@dataclass(slots=True)
class CanonicalObservation:
    stranding_identifier: str
    taxon_label: str
    decomposition_code: int
    sea_surface_temperature: float | None
    wind_drift_factor: float
    longitude: float
    latitude: float
    observed_at: datetime
    reverse_drift_duration_days: int


@dataclass(slots=True)
class SimulationIterationPlan:
    iteration_index: int
    start_time: datetime
    output_path: Path


@dataclass(slots=True)
class SimulationSummary:
    total_records: int = 0
    simulated_records: int = 0
    skipped_records: int = 0
    output_directory: Path | None = None
    messages: list["ValidationMessage"] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not any(message.level == "error" for message in self.messages)


@dataclass(slots=True)
class ValidationMessage:
    level: Literal["error", "warning", "info"]
    text: str
    target_step: str = ""
    subsection: int | None = None
    field_ids: tuple[str, ...] = ()
