from __future__ import annotations

import math
import os
from pathlib import Path

from ..domain.models import SimulationRequest, ValidationMessage
from .environment import resolve_environment_extent
from .io import read_observation_columns
from .selection import SUPPORTED_FILTER_OPERATORS

OBSERVATION_SUFFIXES = {".xlsx", ".xls", ".csv", ".parquet"}
NETCDF_SUFFIXES = {".nc", ".nc4"}

SOURCE_LABELS = {
    "observation_dataset": "Observation dataset",
    "bathymetry": "Bathymetry dataset",
    "biogeochemistry_primary": "Biogeochemistry dataset (primary)",
    "biogeochemistry_secondary": "Biogeochemistry dataset (secondary)",
    "currents_primary": "Currents and SST dataset (primary)",
    "currents_secondary": "Currents and SST dataset (secondary)",
    "waves_primary": "Wave dataset (primary)",
    "waves_secondary": "Wave dataset (secondary)",
    "wind_primary": "Wind dataset (primary)",
    "wind_secondary": "Wind dataset (secondary)",
}

COLUMN_LABELS = {
    "stranding_identifier": "Stranding identifier field",
    "taxon_label": "Taxon label field",
    "decomposition_code": "Decomposition code field",
    "sea_surface_temperature": "Sea surface temperature field",
    "wind_drift_factor": "Wind drift factor field",
    "longitude": "Longitude field",
    "latitude": "Latitude field",
    "observed_date": "Observed date field",
    "observed_time": "Observed time field",
    "observed_datetime": "Observed datetime field",
}


def validate_output_destination(path: Path | None) -> ValidationMessage:
    """Return output readiness without creating or modifying the destination."""
    if path is None or not str(path).strip():
        return ValidationMessage("error", "An output directory must be selected.")
    if path.exists() and path.is_file():
        return ValidationMessage(
            "error", "The output location points to a file. Choose a directory instead."
        )

    writable_parent = path
    while not writable_parent.exists() and writable_parent.parent != writable_parent:
        writable_parent = writable_parent.parent
    if not writable_parent.is_dir() or not os.access(writable_parent, os.W_OK):
        return ValidationMessage(
            "error", "The output folder cannot be created or written at this location."
        )
    if path.exists():
        return ValidationMessage("info", "Output directory is writable.")
    return ValidationMessage(
        "info", f"The output directory will be created when the run starts: `{path}`."
    )


class SimulationRequestValidator:
    def validate(self, request: SimulationRequest) -> list[ValidationMessage]:
        messages: list[ValidationMessage] = []
        for validate, step, subsection, fields in (
            (self._validate_column_mapping, "stranding_data", None, ("field_mapping_card",)),
            (self._validate_input_sources, "environmental_forcing", None, ("catalog_table",)),
            (self._validate_output_directory, "review_run", None, ("output_directory",)),
            (self._validate_settings, "simulation_setup", 5, ("advanced_group",)),
            (self._validate_wind_drift, "simulation_setup", 3, ("windage_group",)),
            (self._validate_observation_selection, "simulation_setup", 1, ("selection_group",)),
            (self._validate_coverage, "simulation_setup", 0, ("study_area_group",)),
        ):
            batch: list[ValidationMessage] = []
            validate(request, batch)
            for message in batch:
                if not message.target_step:
                    message.target_step = step
                    message.subsection = subsection
                    if not message.field_ids:
                        message.field_ids = fields
            messages.extend(batch)
        return messages

    def _validate_column_mapping(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        mappings = request.column_mapping.as_dict()
        datetime_mode = request.column_mapping.datetime_mode
        if datetime_mode == "separate":
            mappings.pop("observed_datetime")
        elif datetime_mode == "combined":
            mappings.pop("observed_date")
            mappings.pop("observed_time")
        else:
            messages.append(
                ValidationMessage(
                    "error",
                    f"Unsupported observation datetime mapping mode `{datetime_mode}`.",
                )
            )
            return
        if request.settings.wind_drift.mode != "dataset":
            mappings.pop("wind_drift_factor")
        if request.settings.duration.mode != "estimated":
            mappings.pop("sea_surface_temperature")

        targets = {
            "stranding_identifier": ("stranding_data", None, "identifier_column"),
            "taxon_label": ("stranding_data", None, "taxon_column"),
            "decomposition_code": ("stranding_data", None, "decomposition_column"),
            "sea_surface_temperature": ("simulation_setup", 2, "sst_column"),
            "wind_drift_factor": ("simulation_setup", 3, "wind_column"),
            "longitude": ("stranding_data", None, "lon_column"),
            "latitude": ("stranding_data", None, "lat_column"),
            "observed_date": ("stranding_data", None, "date_column"),
            "observed_time": ("stranding_data", None, "time_column"),
            "observed_datetime": ("stranding_data", None, "observed_datetime_column"),
            "measurement": ("simulation_setup", 3, "measurement_column"),
            "duration": ("simulation_setup", 2, "duration_column"),
        }
        if request.settings.wind_drift.mode == "measurement":
            mappings["measurement"] = request.settings.wind_drift.measurement_column
        if request.settings.duration.mode == "dataset":
            mappings["duration"] = request.settings.duration.duration_column
        labels = dict(COLUMN_LABELS, measurement="Specimen measurement field", duration="Reverse-drift duration field")
        def mapping_issue(key: str, text: str) -> ValidationMessage:
            step, subsection, field_id = targets[key]
            return ValidationMessage("error", text, step, subsection, (field_id,))

        missing = [key for key, value in mappings.items() if not value.strip()]
        if missing:
            messages.extend(mapping_issue(key, f"Choose source columns for: {labels[key]}.") for key in missing)
            return

        dataset_path = request.data_sources.observation_dataset
        if dataset_path is not None and dataset_path.exists() and dataset_path.is_file():
            try:
                source_columns = read_observation_columns(dataset_path)
            except (OSError, ValueError, ImportError) as exc:
                messages.append(
                    ValidationMessage(
                        "error",
                        f"Could not read the observation dataset structure: {exc}",
                    )
                )
                return

            missing_columns = [
                key
                for key, value in mappings.items()
                if value not in source_columns
            ]
            if missing_columns:
                messages.extend(mapping_issue(key,
                    f"The observation dataset is missing mapped columns for: {labels[key]} (`{mappings[key]}`). Choose an available column.")
                    for key in missing_columns)
                return

        messages.append(
            ValidationMessage(
                "info",
                "Column mapping is populated and matches the selected observation dataset.",
            )
        )

    def _validate_input_sources(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        if request.data_sources.environment_readers:
            self._validate_reader_catalog(request, messages)
            sources = {
                "observation_dataset": request.data_sources.observation_dataset,
            }
        else:
            sources = request.data_sources.input_sources()

        for key, path in sources.items():
            label = SOURCE_LABELS[key]
            step = "stranding_data" if key == "observation_dataset" else "environmental_forcing"
            fields = ("dataset_path",) if key == "observation_dataset" else ("catalog_table",)
            if path is None:
                messages.append(ValidationMessage("error", f"{label} is required.", step, field_ids=fields))
                continue

            raw_path = str(path).strip()
            if not raw_path:
                messages.append(ValidationMessage("error", f"{label} is required.", step, field_ids=fields))
                continue

            if path.exists() and path.is_dir():
                messages.append(
                    ValidationMessage("error", f"{label} must be a file, not a folder.", step, field_ids=fields)
                )
                continue

            if not path.is_absolute():
                messages.append(
                    ValidationMessage(
                        "warning",
                        f"{label} uses a relative path. Prefer an absolute path so installed users are not tied to a launch directory.",
                    )
                )

            suffixes = (
                OBSERVATION_SUFFIXES if key == "observation_dataset" else NETCDF_SUFFIXES
            )
            if path.suffix.lower() not in suffixes:
                allowed = ", ".join(sorted(suffixes))
                messages.append(
                    ValidationMessage(
                        "warning",
                        f"{label} does not use one of the expected file extensions ({allowed}).",
                    )
                )

            if not path.exists():
                messages.append(
                    ValidationMessage(
                        "warning",
                        f"{label} does not exist yet at `{path}`.",
                    )
                )

    def _validate_reader_catalog(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        for index, reader in enumerate(request.data_sources.environment_readers, start=1):
            if not reader.roles:
                messages.append(
                    ValidationMessage(
                        "error", f"Environmental reader {index} (`{reader.path.name}`) needs at least one role. Select the file in Environmental forcing and assign its model role.",
                        "environmental_forcing", field_ids=(f"environment_reader:{index - 1}",),
                    )
                )
            if not reader.path.exists() or not reader.path.is_file():
                messages.append(
                    ValidationMessage(
                        "error", f"Environmental reader {index} does not exist: {reader.path}",
                        "environmental_forcing", field_ids=(f"environment_reader:{index - 1}",),
                    )
                )

    def _validate_output_directory(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        path = request.data_sources.output_directory
        destination_message = validate_output_destination(path)
        messages.append(destination_message)
        if destination_message.level == "error" or path is None:
            return

        if not path.is_absolute():
            messages.append(
                ValidationMessage(
                    "warning",
                    "The output directory is relative. Prefer an absolute location for an installed desktop app.",
                )
            )


    def _validate_settings(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        if request.settings.iteration_count < 1:
            messages.append(
                ValidationMessage("error", "Iteration count must be at least 1.", "simulation_setup", 4, ("iteration_count",))
            )

        if request.settings.iteration_interval_hours < 0:
            messages.append(
                ValidationMessage("error", "Iteration interval cannot be negative.", "simulation_setup", 4, ("iteration_interval",))
            )

        timestep = request.settings.model_time_step_hours
        if timestep <= 0 or not math.isfinite(timestep):
            messages.append(
                ValidationMessage("error", "Model timestep must be greater than zero.", "simulation_setup", 5, ("model_time_step",))
            )
        elif not math.isclose(24.0 / timestep, round(24.0 / timestep), abs_tol=1e-9):
            messages.append(
                ValidationMessage(
                    "error",
                    "Model timestep must divide evenly into 24 hours (for example 0.5, 1, 2, 3, 6, 12, or 24).",
                    "simulation_setup", 5, ("model_time_step",),
                )
            )

        if not 0 <= request.settings.fixed_start_hour <= 23:
            messages.append(
                ValidationMessage("error", "Fixed start hour must be between 0 and 23.", "simulation_setup", 4, ("fixed_start_hour",))
            )

        if request.settings.particle_count < 1:
            messages.append(
                ValidationMessage("error", "Particle count must be at least 1.", "simulation_setup", 4, ("particle_count",))
            )

        if request.settings.release_radius_meters < 0:
            messages.append(
                ValidationMessage("error", "Release radius cannot be negative.", "simulation_setup", 4, ("release_radius",))
            )

        if (
            request.settings.current_uncertainty_enabled
            and request.settings.current_uncertainty < 0
        ) or (
            request.settings.wind_uncertainty_enabled
            and request.settings.wind_uncertainty < 0
        ):
            messages.append(
                ValidationMessage(
                    "error",
                    "Uncertainty values must be zero or positive.",
                    "simulation_setup", 5, ("current_uncertainty", "wind_uncertainty"),
                )
            )

        if request.settings.job_error_policy not in {"continue", "stop"}:
            messages.append(
                ValidationMessage(
                    "error", "Choose a supported simulation error policy.", "review_run", field_ids=("continue_errors_toggle",),
                )
            )

        if request.settings.coordinate_format not in {
            "decimal_degrees",
            "degrees_minutes_seconds",
        }:
            messages.append(
                ValidationMessage("error", "Choose a supported coordinate format.", "stranding_data", field_ids=("coordinate_format",))
            )

        duration = request.settings.duration
        if duration.mode not in {"fixed", "estimated", "dataset"}:
            messages.append(
                ValidationMessage("error", "Choose a supported drift-duration mode.", "simulation_setup", 2, ("duration_mode",))
            )
        if duration.mode == "fixed" and duration.fixed_days < 1:
            messages.append(
                ValidationMessage(
                    "error", "Fixed drift duration must be at least 1 day.", "simulation_setup", 2, ("fixed_duration_days",),
                )
            )
        if duration.mode == "estimated" and (
            duration.temperature_threshold_celsius < -5
            or duration.temperature_threshold_celsius > 50
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "Duration temperature threshold is outside the usual sea-surface range.",
                    "simulation_setup", 2, ("duration_threshold",),
                )
            )
        if duration.mode == "estimated" and duration.scenario_days:
            boundaries = duration.temperature_boundaries_celsius
            if boundaries != sorted(set(boundaries)):
                messages.append(ValidationMessage(
                    "error", "Duration temperature boundaries must be unique and ordered.", "simulation_setup", 2, ("duration_profile_panel",),
                ))
            expected_bands = len(boundaries) + 1
            if any(len(days) != expected_bands or any(day < 1 for day in days)
                   for days in duration.scenario_days.values()):
                messages.append(ValidationMessage(
                    "error", "Every decomposition state needs one positive duration per temperature band.", "simulation_setup", 2, ("duration_table",),
                ))

        if not request.settings.extent.is_valid():
            messages.append(
                ValidationMessage(
                    "error",
                    "Spatial extent is invalid. Minimum bounds must be lower than maximum bounds.",
                    "simulation_setup", 0, ("min_lon", "max_lon", "min_lat", "max_lat"),
                )
            )

        search = request.settings.position_search
        if search.mode not in {"direct", "search_nearby_water", "skip_if_invalid"}:
            messages.append(ValidationMessage("error", "Choose a supported initial-position mode.", "simulation_setup", 1, ("initial_position_group",)))
        if search.radial_step_degrees <= 0:
            messages.append(ValidationMessage("error", "Nearby-water radial step must be greater than zero.", "simulation_setup", 1, ("position_radial_step",)))
        if search.max_radius_degrees <= 0:
            messages.append(ValidationMessage("error", "Nearby-water maximum radius must be greater than zero.", "simulation_setup", 1, ("position_max_radius",)))
        elif search.max_radius_degrees < search.radial_step_degrees:
            messages.append(ValidationMessage(
                "error", "Nearby-water maximum radius must be at least the radial step.", "simulation_setup", 1, ("position_max_radius", "position_radial_step"),
            ))
        if not 1 <= search.angle_step_degrees <= 360:
            messages.append(ValidationMessage("error", "Nearby-water angle step must be between 1 and 360 degrees.", "simulation_setup", 1, ("position_angle_step",)))
        if search.max_attempts < 1:
            messages.append(ValidationMessage("error", "Nearby-water maximum attempts must be at least 1.", "simulation_setup", 1, ("position_max_attempts",)))
        if search.failure_behavior not in {"skip", "stop"}:
            messages.append(ValidationMessage("error", "Choose whether a failed position search should skip or stop.", "simulation_setup", 1, ("initial_position_group",)))

    def _validate_observation_selection(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        selection = request.settings.observation_selection
        if selection.mode not in {"all", "random", "filter"}:
            messages.append(ValidationMessage("error", "Choose a supported observation selection mode."))
            return
        if selection.mode == "random" and selection.sample_size < 1:
            messages.append(ValidationMessage("error", "Random sample size must be at least 1.", "simulation_setup", 1, ("selection_sample_size",)))
        if selection.mode != "filter":
            return
        if not selection.conditions:
            messages.append(ValidationMessage("error", "Add at least one observation filter condition."))
            return

        source_columns: list[str] = []
        dataset = request.data_sources.observation_dataset
        if dataset is not None and dataset.exists() and dataset.is_file():
            try:
                source_columns = read_observation_columns(dataset)
            except (OSError, ValueError, ImportError):
                pass
        for index, condition in enumerate(selection.conditions, start=1):
            if condition.column not in source_columns:
                messages.append(ValidationMessage(
                    "error",
                    f"Observation filter {index} uses missing column `{condition.column}`.",
                ))
            if condition.operator not in SUPPORTED_FILTER_OPERATORS:
                messages.append(ValidationMessage(
                    "error",
                    f"Observation filter {index} uses unsupported operator `{condition.operator}`.",
                ))
            if condition.connector not in {"and", "or"}:
                messages.append(ValidationMessage(
                    "error", f"Observation filter {index} must use AND or OR."
                ))

    def _validate_coverage(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        coverage = request.settings.coverage
        if coverage.mode not in {"manual", "environment_intersection"}:
            messages.append(ValidationMessage("error", "Choose a supported spatial-coverage mode."))
            return
        if coverage.buffer_degrees < 0:
            messages.append(ValidationMessage("error", "Environmental coverage buffer cannot be negative.", "simulation_setup", 0, ("coverage_buffer",)))
            return
        if coverage.mode != "environment_intersection":
            return
        paths = [reader.path for reader in request.data_sources.environment_readers]
        if coverage.contributing_paths:
            included = {str(path) for path in coverage.contributing_paths}
            paths = [path for path in paths if str(path) in included]
        try:
            resolved = resolve_environment_extent(paths, coverage.buffer_degrees)
        except (OSError, ValueError, ImportError) as exc:
            messages.append(ValidationMessage("error", f"Could not resolve environmental coverage: {exc}"))
            return
        request.settings.extent = resolved
        messages.append(ValidationMessage(
            "info", "Spatial extent was resolved from overlapping environmental coverage."
        ))

    def _validate_wind_drift(
        self,
        request: SimulationRequest,
        messages: list[ValidationMessage],
    ) -> None:
        settings = request.settings.wind_drift
        if settings.mode not in {"none", "dataset", "fixed", "measurement"}:
            messages.append(
                ValidationMessage("error", "Choose a supported wind-drift mode.")
            )
            return
        if settings.mode == "fixed" and (
            not math.isfinite(settings.fixed_percent)
            or not 0 <= settings.fixed_percent <= 100
        ):
            messages.append(ValidationMessage(
                "error", "Fixed wind drift percentage must be between 0 and 100.", "simulation_setup", 3, ("fixed_wind_percent",),
            ))
        if settings.mode == "measurement" and (
            settings.measurement_maximum <= settings.measurement_minimum
        ):
            messages.append(
                ValidationMessage(
                    "error",
                    "Specimen measurement maximum must be greater than minimum.",
                    "simulation_setup", 3, ("measurement_minimum", "measurement_maximum"),
                )
            )
        if settings.mode == "measurement" and any(
            not math.isfinite(percent) or not 0 <= percent <= 100
            for percent in (
                settings.wind_drift_minimum_percent,
                settings.wind_drift_maximum_percent,
            )
        ):
            messages.append(ValidationMessage(
                "error", "Measurement wind drift percentages must be between 0 and 100.", "simulation_setup", 3, ("wind_min_percent", "wind_max_percent"),
            ))
        if settings.mode == "dataset":
            if settings.source_scale not in {"fraction", "percent"}:
                messages.append(ValidationMessage(
                    "error", "Choose a supported wind-drift source scale.", "simulation_setup", 3, ("windage_group",),
                ))
                return
            label = "percentage" if settings.source_scale == "percent" else "decimal fraction"
            messages.append(
                ValidationMessage(
                    "info",
                    f"Wind-drift column will be interpreted as {label} values.",
                )
            )
