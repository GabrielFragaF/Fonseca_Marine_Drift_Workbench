from __future__ import annotations

import unittest
from datetime import date, datetime
import math
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from marine_drift_desktop.core.duration import ThermalDurationProfile, build_default_duration_profile
from marine_drift_desktop.core.environment import inspect_environment_reader
from marine_drift_desktop.core.landmask import (
    adjust_to_nearby_water,
    is_position_within_extent,
)
from marine_drift_desktop.core.planning import plan_simulation_runs
from marine_drift_desktop.core.records import canonicalize_observation
from marine_drift_desktop.core.windage import wind_drift_factor_for_record
from marine_drift_desktop.domain.models import (
    ColumnMapping,
    EnvironmentalReaderConfig,
    FilterCondition,
    ObservationSelectionSettings,
    SimulationRequest,
    SpatialExtent,
    WindDriftSettings,
)
from marine_drift_desktop.services.workflow import SimulationWorkflowService


class ModelTimestepTests(unittest.TestCase):
    def test_validation_rejects_a_timestep_that_cannot_span_a_day(self) -> None:
        from marine_drift_desktop.core.validation import SimulationRequestValidator

        request = SimulationRequest()
        request.settings.model_time_step_hours = 5.0
        result = SimulationRequestValidator().validate(request)

        self.assertTrue(any("timestep" in message.text.lower() for message in result))


class ObservationSelectionTests(unittest.TestCase):
    def _select(self, records, settings):
        try:
            from marine_drift_desktop.core.selection import select_observation_records
        except ModuleNotFoundError:
            self.fail("Observation selection service is not implemented.")
        return select_observation_records(records, settings)

    def test_random_selection_is_repeatable_for_a_seed(self) -> None:
        records = [{"id": f"obs-{index}", "score": index} for index in range(10)]
        settings = ObservationSelectionSettings(
            mode="random", sample_size=3, random_seed=42
        )

        first = self._select(records, settings)
        second = self._select(records, settings)

        self.assertEqual(first.records, second.records)
        self.assertEqual(first.source_count, 10)
        self.assertEqual(first.selected_count, 3)

    def test_filter_selection_combines_conditions_in_display_order(self) -> None:
        records = [
            {"id": "a", "score": 1, "taxon": "ray"},
            {"id": "b", "score": 4, "taxon": "ray"},
            {"id": "c", "score": 6, "taxon": "shark"},
        ]
        settings = ObservationSelectionSettings(
            mode="filter",
            conditions=[
                FilterCondition(column="score", operator=">=", value=4),
                FilterCondition(
                    column="taxon", operator="equals", value="ray", connector="and"
                ),
            ],
        )

        result = self._select(records, settings)

        self.assertEqual([record["id"] for record in result.records], ["b"])

    def test_filter_supports_contains_blank_and_selected_values(self) -> None:
        records = [
            {"name": "Green turtle", "region": "north", "note": ""},
            {"name": "Loggerhead", "region": "south", "note": None},
            {"name": "Green specimen", "region": "east", "note": "checked"},
        ]
        settings = ObservationSelectionSettings(
            mode="filter",
            conditions=[
                FilterCondition(column="name", operator="contains", value="green"),
                FilterCondition(
                    column="region",
                    operator="in_values",
                    values=["north", "east"],
                    connector="and",
                ),
                FilterCondition(
                    column="note", operator="is_not_blank", connector="or"
                ),
            ],
        )

        result = self._select(records, settings)

        self.assertEqual([record["region"] for record in result.records], ["north", "east"])

    def test_random_selection_rejects_count_above_source_rows(self) -> None:
        settings = ObservationSelectionSettings(
            mode="random", sample_size=2, random_seed=1
        )
        with self.assertRaisesRegex(ValueError, "between 1 and 1"):
            self._select([{"id": "only"}], settings)


class WorkflowValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = SimulationWorkflowService()
        self.workspace_temp_root = Path(__file__).resolve().parents[1] / ".tmp_tests"
        self.workspace_temp_root.mkdir(exist_ok=True)

    def test_blank_request_is_not_valid(self) -> None:
        summary = self.service.preview(SimulationRequest())

        self.assertFalse(summary.is_valid)
        self.assertTrue(any(message.level == "error" for message in summary.messages))

    def test_workflow_service_does_not_expose_obsolete_prepare_plan_api(self) -> None:
        self.assertFalse(hasattr(self.service, "prepare_run"))

    def test_valid_absolute_paths_and_mapping_pass_preview(self) -> None:
        root = self.workspace_temp_root / "validation_case"
        root.mkdir(parents=True, exist_ok=True)
        dataset = root / "observations.csv"
        dataset.write_text(
            "id,taxon,decomp,sst,wind_factor,lon,lat,date,time\n"
            "obs-01,Marine fauna,3,22.0,0.015,-38.12,-12.55,2026-04-24,10:37\n",
            encoding="utf-8",
        )

        request = SimulationRequest()
        request.column_mapping.stranding_identifier = "id"
        request.column_mapping.taxon_label = "taxon"
        request.column_mapping.decomposition_code = "decomp"
        request.column_mapping.sea_surface_temperature = "sst"
        request.column_mapping.wind_drift_factor = "wind_factor"
        request.column_mapping.longitude = "lon"
        request.column_mapping.latitude = "lat"
        request.column_mapping.observed_date = "date"
        request.column_mapping.observed_time = "time"

        request.data_sources.observation_dataset = dataset
        request.data_sources.output_directory = root / "outputs"

        for name in [
            "bathymetry.nc",
            "biogeochemistry_primary.nc",
            "biogeochemistry_secondary.nc",
            "currents_primary.nc",
            "currents_secondary.nc",
            "waves_primary.nc",
            "waves_secondary.nc",
            "wind_primary.nc",
            "wind_secondary.nc",
        ]:
            path = root / name
            path.write_text("", encoding="utf-8")

        request.data_sources.bathymetry = root / "bathymetry.nc"
        request.data_sources.biogeochemistry_primary = root / "biogeochemistry_primary.nc"
        request.data_sources.biogeochemistry_secondary = root / "biogeochemistry_secondary.nc"
        request.data_sources.currents_primary = root / "currents_primary.nc"
        request.data_sources.currents_secondary = root / "currents_secondary.nc"
        request.data_sources.waves_primary = root / "waves_primary.nc"
        request.data_sources.waves_secondary = root / "waves_secondary.nc"
        request.data_sources.wind_primary = root / "wind_primary.nc"
        request.data_sources.wind_secondary = root / "wind_secondary.nc"

        summary = self.service.preview(request)

        self.assertTrue(summary.is_valid)
        self.assertFalse(any(message.level == "error" for message in summary.messages))

    def test_preview_rejects_mapped_columns_missing_from_dataset(self) -> None:
        root = self.workspace_temp_root / "schema_validation_case"
        root.mkdir(parents=True, exist_ok=True)
        dataset = root / "observations.csv"
        dataset.write_text("id\n1\n", encoding="utf-8")

        request = SimulationRequest()
        request.data_sources.observation_dataset = dataset
        request.column_mapping.stranding_identifier = "id"
        request.column_mapping.taxon_label = "taxon"
        request.column_mapping.decomposition_code = "decomp"
        request.column_mapping.sea_surface_temperature = "sst"
        request.column_mapping.wind_drift_factor = "wind"
        request.column_mapping.longitude = "lon"
        request.column_mapping.latitude = "lat"
        request.column_mapping.observed_date = "date"
        request.column_mapping.observed_time = "time"

        summary = self.service.preview(request)

        self.assertFalse(summary.is_valid)
        self.assertTrue(any("missing mapped columns" in message.text for message in summary.messages))

    def test_combined_datetime_mapping_does_not_require_separate_columns(self) -> None:
        root = self.workspace_temp_root / "combined_datetime_validation"
        root.mkdir(parents=True, exist_ok=True)
        dataset = root / "observations.csv"
        dataset.write_text(
            "id,taxon,decomp,sst,wind,lon,lat,observed_at\n"
            "obs-1,Marine fauna,3,22,0.015,-38,-12,13/04/2024 07:50\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = dataset
        request.column_mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            sea_surface_temperature="sst",
            wind_drift_factor="wind",
            longitude="lon",
            latitude="lat",
            datetime_mode="combined",
            observed_datetime="observed_at",
        )

        summary = self.service.preview(request)
        mapping_messages = [
            message.text.lower()
            for message in summary.messages
            if "column mapping" in message.text.lower()
            or "source columns" in message.text.lower()
            or "mapped columns" in message.text.lower()
        ]

        self.assertTrue(any("matches" in text for text in mapping_messages))
        self.assertFalse(any("observed date" in text for text in mapping_messages))
        self.assertFalse(any("observed time" in text for text in mapping_messages))

    def test_combined_datetime_mapping_requires_its_source_column(self) -> None:
        request = SimulationRequest()
        request.column_mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            sea_surface_temperature="sst",
            wind_drift_factor="wind",
            longitude="lon",
            latitude="lat",
            datetime_mode="combined",
        )

        summary = self.service.preview(request)

        self.assertTrue(
            any("observed datetime" in message.text.lower() for message in summary.messages)
        )

    def test_validation_rejects_unsupported_datetime_mapping_mode(self) -> None:
        request = SimulationRequest()
        request.column_mapping.datetime_mode = "automatic"

        summary = self.service.preview(request)

        self.assertTrue(
            any(
                "unsupported observation datetime mapping mode" in message.text.lower()
                for message in summary.messages
            )
        )

    def test_fixed_duration_and_no_windage_do_not_require_inactive_columns(self) -> None:
        root = self.workspace_temp_root / "fixed_duration_validation"
        root.mkdir(parents=True, exist_ok=True)
        dataset = root / "observations.csv"
        dataset.write_text(
            "id,taxon,decomp,lon,lat,date,time\n"
            "obs-1,Marine fauna,3,-38,-12,2024-04-13,07:50\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = dataset
        request.column_mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            longitude="lon",
            latitude="lat",
            observed_date="date",
            observed_time="time",
        )
        request.settings.duration.mode = "fixed"
        request.settings.duration.fixed_days = 5
        request.settings.wind_drift.mode = "none"

        summary = self.service.preview(request)
        mapping_messages = [
            message.text.lower()
            for message in summary.messages
            if "column mapping" in message.text.lower()
            or "source columns" in message.text.lower()
            or "mapped columns" in message.text.lower()
        ]

        self.assertTrue(any("matches" in text for text in mapping_messages))
        self.assertFalse(any("temperature" in text for text in mapping_messages))
        self.assertFalse(any("wind drift" in text for text in mapping_messages))

    def test_estimated_duration_requires_sea_surface_temperature(self) -> None:
        mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            sea_surface_temperature="sst",
            longitude="lon",
            latitude="lat",
            observed_date="date",
            observed_time="time",
        )

        with self.assertRaisesRegex(ValueError, "Sea surface temperature is required"):
            canonicalize_observation(
                {
                    "id": "obs-1", "taxon": "Marine fauna", "decomp": 3,
                    "sst": "", "lon": -38.0, "lat": -12.0,
                    "date": "2026-01-03", "time": "10:00",
                },
                mapping,
                build_default_duration_profile(),
                wind_drift_settings=WindDriftSettings(mode="none"),
            )

    def test_wind_drift_configuration_blocks_out_of_bounds_percentages(self) -> None:
        fixed = SimulationRequest()
        fixed.settings.wind_drift = WindDriftSettings(mode="fixed", fixed_percent=101)
        measurement = SimulationRequest()
        measurement.settings.wind_drift = WindDriftSettings(
            mode="measurement",
            measurement_column="length_cm",
            wind_drift_minimum_percent=-1,
            wind_drift_maximum_percent=101,
        )

        fixed_summary = self.service.preview(fixed)
        measurement_summary = self.service.preview(measurement)

        self.assertTrue(any("between 0 and 100" in message.text for message in fixed_summary.messages))
        self.assertTrue(any("between 0 and 100" in message.text for message in measurement_summary.messages))

    def test_wind_drift_configuration_blocks_nonfinite_percentages(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                fixed = SimulationRequest()
                fixed.settings.wind_drift = WindDriftSettings(
                    mode="fixed", fixed_percent=value
                )
                measurement = SimulationRequest()
                measurement.settings.wind_drift = WindDriftSettings(
                    mode="measurement",
                    measurement_column="length_cm",
                    wind_drift_minimum_percent=value,
                )

                self.assertTrue(any(
                    "between 0 and 100" in message.text
                    for message in self.service.preview(fixed).messages
                ))
                self.assertTrue(any(
                    "between 0 and 100" in message.text
                    for message in self.service.preview(measurement).messages
                ))

    def test_validation_rejects_nonpositive_fixed_duration(self) -> None:
        request = SimulationRequest()
        request.settings.duration.mode = "fixed"
        request.settings.duration.fixed_days = 0

        summary = self.service.preview(request)

        self.assertTrue(
            any("fixed drift duration" in message.text.lower() for message in summary.messages)
        )

    def test_disabled_uncertainty_ignores_stored_negative_value(self) -> None:
        request = SimulationRequest()
        request.settings.current_uncertainty_enabled = False
        request.settings.current_uncertainty = -1.0

        summary = self.service.preview(request)

        self.assertFalse(
            any("uncertainty values" in message.text.lower() for message in summary.messages)
        )

    def test_validation_rejects_unsupported_job_error_policy(self) -> None:
        request = SimulationRequest()
        request.settings.job_error_policy = "retry_forever"

        summary = self.service.preview(request)

        self.assertTrue(
            any("simulation error policy" in message.text.lower() for message in summary.messages)
        )

    def test_validation_rejects_filter_column_missing_from_dataset(self) -> None:
        root = self.workspace_temp_root / "filter_validation_case"
        root.mkdir(parents=True, exist_ok=True)
        dataset = root / "observations.csv"
        dataset.write_text(
            "id,taxon,decomp,sst,wind_factor,lon,lat,date,time\n"
            "obs-01,Marine fauna,3,22,0.015,-38,-12,2026-04-24,10:37\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = dataset
        request.data_sources.output_directory = root / "outputs"
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(root / "forcing.nc", ["Currents"], [])
        ]
        (root / "forcing.nc").write_bytes(b"placeholder")
        request.column_mapping = ColumnMapping(
            stranding_identifier="id", taxon_label="taxon",
            decomposition_code="decomp", sea_surface_temperature="sst",
            wind_drift_factor="wind_factor", longitude="lon", latitude="lat",
            observed_date="date", observed_time="time",
        )
        request.settings.observation_selection.mode = "filter"
        request.settings.observation_selection.conditions = [
            FilterCondition(column="missing", operator="equals", value="x")
        ]

        summary = self.service.preview(request)

        self.assertFalse(summary.is_valid)
        self.assertTrue(
            any("missing" in message.text.lower() for message in summary.messages)
        )

    def test_validation_rejects_invalid_position_search_limits(self) -> None:
        request = SimulationRequest()
        request.settings.position_search.mode = "search_nearby_water"
        request.settings.position_search.radial_step_degrees = 0
        request.settings.position_search.angle_step_degrees = 361

        summary = self.service.preview(request)

        text = " ".join(message.text for message in summary.messages).lower()
        self.assertIn("radial step", text)
        self.assertIn("angle step", text)


class ObservationGeneralizationTests(unittest.TestCase):
    def test_missing_excel_date_is_rejected_instead_of_becoming_year_one(self) -> None:
        with self.assertRaisesRegex(ValueError, "Observed date"):
            canonicalize_observation(
                {
                    "id": "obs-missing-date", "taxon": "Marine fauna", "decomp": 3,
                    "sst": 22.0, "wind": 0.0, "lon": -38.12, "lat": -12.55,
                    "obs_date": pd.NaT, "obs_time": "08:00",
                },
                ColumnMapping(
                    stranding_identifier="id", taxon_label="taxon",
                    decomposition_code="decomp", sea_surface_temperature="sst",
                    wind_drift_factor="wind", longitude="lon", latitude="lat",
                    observed_date="obs_date", observed_time="obs_time",
                ),
                build_default_duration_profile(),
            )

    def test_naive_brazilian_time_is_converted_to_utc(self) -> None:
        observation = canonicalize_observation(
            {
                "id": "obs-br", "taxon": "Marine fauna", "decomp": 3,
                "sst": 22.0, "wind": 0.015, "lon": -38.12, "lat": -12.55,
                "observed_at": "13/04/2024 09:00",
            },
            ColumnMapping(
                stranding_identifier="id", taxon_label="taxon",
                decomposition_code="decomp", sea_surface_temperature="sst",
                wind_drift_factor="wind", longitude="lon", latitude="lat",
                datetime_mode="combined", observed_datetime="observed_at",
                input_timezone="America/Sao_Paulo",
            ),
            build_default_duration_profile(),
        )
        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 12,))

    def test_explicit_timestamp_offset_overrides_selected_timezone(self) -> None:
        observation = canonicalize_observation(
            {
                "id": "obs-offset", "taxon": "Marine fauna", "decomp": 3,
                "sst": 22.0, "wind": 0.015, "lon": -38.12, "lat": -12.55,
                "observed_at": "2024-04-13T09:00:00-02:00",
            },
            ColumnMapping(
                stranding_identifier="id", taxon_label="taxon",
                decomposition_code="decomp", sea_surface_temperature="sst",
                wind_drift_factor="wind", longitude="lon", latitude="lat",
                datetime_mode="combined", observed_datetime="observed_at",
                input_timezone="America/Sao_Paulo",
            ),
            build_default_duration_profile(),
        )
        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 11, 0))

    def test_combined_datetime_mode_uses_one_timestamp_column(self) -> None:
        observation = canonicalize_observation(
            {
                "record_id": "obs-20",
                "taxon": "Marine fauna",
                "condition_code": 3,
                "sst_c": 22.0,
                "wind_factor": 0.015,
                "x": -38.12,
                "y": -12.55,
                "observed_at": "13/04/2024 07:50",
            },
            ColumnMapping(
                stranding_identifier="record_id",
                taxon_label="taxon",
                decomposition_code="condition_code",
                sea_surface_temperature="sst_c",
                wind_drift_factor="wind_factor",
                longitude="x",
                latitude="y",
                datetime_mode="combined",
                observed_datetime="observed_at",
            ),
            build_default_duration_profile(),
        )

        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 7, 50))

    def test_combined_datetime_mode_accepts_fractional_excel_datetime(self) -> None:
        excel_datetime = (
            (date(2024, 4, 13) - date(1899, 12, 30)).days
            + (7 * 60 + 30) / (24 * 60)
        )
        observation = canonicalize_observation(
            {
                "id": "obs-excel",
                "taxon": "Marine fauna",
                "decomp": 3,
                "sst": 22.0,
                "wind": 0.015,
                "lon": -38.12,
                "lat": -12.55,
                "observed_at": excel_datetime,
            },
            ColumnMapping(
                stranding_identifier="id",
                taxon_label="taxon",
                decomposition_code="decomp",
                sea_surface_temperature="sst",
                wind_drift_factor="wind",
                longitude="lon",
                latitude="lat",
                datetime_mode="combined",
                observed_datetime="observed_at",
            ),
            build_default_duration_profile(),
        )

        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 7, 30))

    def test_combined_day_first_timestamp_is_accepted_as_observed_date(self) -> None:
        observation = canonicalize_observation(
            {
                "record_id": "obs-21", "taxon": "Marine fauna", "condition_code": 3,
                "sst_c": 22.0, "wind_factor": 0.015, "x": -38.12, "y": -12.55,
                "obs_date": "13/04/2024 07:50", "obs_time": "07:50",
            },
            ColumnMapping(
                stranding_identifier="record_id", taxon_label="taxon",
                decomposition_code="condition_code", sea_surface_temperature="sst_c",
                wind_drift_factor="wind_factor", longitude="x", latitude="y",
                observed_date="obs_date", observed_time="obs_time",
            ),
            build_default_duration_profile(),
        )

        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 7, 50))

    def test_excel_serial_date_is_accepted(self) -> None:
        excel_serial = (date(2024, 4, 13) - date(1899, 12, 30)).days
        observation = canonicalize_observation(
            {
                "record_id": "obs-22", "taxon": "Marine fauna", "condition_code": 3,
                "sst_c": 22.0, "wind_factor": 0.015, "x": -38.12, "y": -12.55,
                "obs_date": excel_serial, "obs_time": "07:50",
            },
            ColumnMapping(
                stranding_identifier="record_id", taxon_label="taxon",
                decomposition_code="condition_code", sea_surface_temperature="sst_c",
                wind_drift_factor="wind_factor", longitude="x", latitude="y",
                observed_date="obs_date", observed_time="obs_time",
            ),
            build_default_duration_profile(),
        )

        self.assertEqual(observation.observed_at, datetime(2024, 4, 13, 7, 50))

    def test_canonicalize_observation_uses_generic_fields(self) -> None:
        mapping = ColumnMapping(
            stranding_identifier="record_id",
            taxon_label="taxon",
            decomposition_code="condition_code",
            sea_surface_temperature="sst_c",
            wind_drift_factor="wind_factor",
            longitude="x",
            latitude="y",
            observed_date="obs_date",
            observed_time="obs_time",
        )
        row = {
            "record_id": "obs-17",
            "taxon": "Delphinidae sp.",
            "condition_code": 4,
            "sst_c": 22.0,
            "wind_factor": 0.015,
            "x": -38.12,
            "y": -12.55,
            "obs_date": "2026-04-24",
            "obs_time": "10:37",
        }

        observation = canonicalize_observation(
            raw_row=row,
            column_mapping=mapping,
            duration_profile=build_default_duration_profile(),
        )

        self.assertEqual(observation.stranding_identifier, "obs-17")
        self.assertEqual(observation.taxon_label, "Delphinidae sp.")
        self.assertEqual(observation.reverse_drift_duration_days, 7)
        self.assertEqual(observation.observed_at, datetime(2026, 4, 24, 10, 37))

    def test_plan_simulation_runs_creates_complete_iteration_schedule(self) -> None:
        mapping = ColumnMapping(
            stranding_identifier="record_id",
            taxon_label="taxon",
            decomposition_code="condition_code",
            sea_surface_temperature="sst_c",
            wind_drift_factor="wind_factor",
            longitude="x",
            latitude="y",
            observed_date="obs_date",
            observed_time="obs_time",
        )
        row = {
            "record_id": "obs-17",
            "taxon": "Delphinidae sp.",
            "condition_code": 5,
            "sst_c": 25.2,
            "wind_factor": 0.015,
            "x": -38.12,
            "y": -12.55,
            "obs_date": "2026-04-24",
            "obs_time": "10:37",
        }
        request = SimulationRequest()
        request.settings.iteration_count = 15
        observation = canonicalize_observation(
            raw_row=row,
            column_mapping=mapping,
            duration_profile=build_default_duration_profile(),
        )

        plans = plan_simulation_runs(
            observation=observation,
            settings=request.settings,
            output_directory=Path("C:/simulations/output"),
        )

        self.assertEqual(len(plans), 15)
        self.assertEqual(plans[0].iteration_index, 1)
        self.assertEqual(plans[0].start_time, datetime(2026, 4, 24, 10, 37))
        self.assertEqual(plans[-1].iteration_index, 15)
        self.assertEqual(plans[-1].start_time, datetime(2026, 4, 23, 20, 37))
        self.assertTrue(str(plans[0].output_path).endswith(".nc"))

    def test_plan_supports_fixed_start_hour_and_custom_iteration_interval(self) -> None:
        request = SimulationRequest()
        request.settings.iteration_count = 3
        request.settings.start_time_mode = "fixed_hour"
        request.settings.fixed_start_hour = 9
        request.settings.iteration_interval_hours = 2.5
        observation = canonicalize_observation(
            {
                "record_id": "obs-19", "taxon": "Marine fauna", "condition_code": 3,
                "sst_c": 22.0, "wind_factor": 0.015, "x": -38.12, "y": -12.55,
                "obs_date": "2026-04-24", "obs_time": "10:37",
            },
            ColumnMapping(
                stranding_identifier="record_id", taxon_label="taxon", decomposition_code="condition_code",
                sea_surface_temperature="sst_c", wind_drift_factor="wind_factor", longitude="x",
                latitude="y", observed_date="obs_date", observed_time="obs_time",
            ),
            build_default_duration_profile(),
        )

        plans = plan_simulation_runs(observation, request.settings, Path("C:/simulations/output"))

        self.assertEqual(plans[0].start_time, datetime(2026, 4, 24, 9, 0))
        self.assertEqual(plans[1].start_time, datetime(2026, 4, 24, 6, 30))

    def test_duration_column_overrides_temperature_profile(self) -> None:
        observation = canonicalize_observation(
            {
                "record_id": "obs-20", "taxon": "Marine fauna", "condition_code": 3,
                "sst_c": 22.0, "wind_factor": 0.015, "x": -38.12, "y": -12.55,
                "obs_date": "2026-04-24", "obs_time": "10:37", "duration_days": 9,
            },
            ColumnMapping(
                stranding_identifier="record_id", taxon_label="taxon", decomposition_code="condition_code",
                sea_surface_temperature="sst_c", wind_drift_factor="wind_factor", longitude="x",
                latitude="y", observed_date="obs_date", observed_time="obs_time",
            ),
            build_default_duration_profile(),
            duration_column="duration_days",
        )

        self.assertEqual(observation.reverse_drift_duration_days, 9)

    def test_fixed_duration_overrides_temperature_profile(self) -> None:
        observation = canonicalize_observation(
            {
                "record_id": "obs-fixed",
                "taxon": "Marine fauna",
                "condition_code": 5,
                "sst_c": 10.0,
                "x": -38.12,
                "y": -12.55,
                "obs_date": "2026-04-24",
                "obs_time": "10:37",
            },
            ColumnMapping(
                stranding_identifier="record_id",
                taxon_label="taxon",
                decomposition_code="condition_code",
                longitude="x",
                latitude="y",
                observed_date="obs_date",
                observed_time="obs_time",
            ),
            build_default_duration_profile(),
            wind_drift_settings=WindDriftSettings(mode="none"),
            fixed_duration_days=5,
        )

        self.assertEqual(observation.reverse_drift_duration_days, 5)
        self.assertEqual(observation.wind_drift_factor, 0.0)

class WindDriftTests(unittest.TestCase):
    def test_no_windage_returns_zero_without_a_source_column(self) -> None:
        factor = wind_drift_factor_for_record(
            {},
            "",
            WindDriftSettings(mode="none"),
        )

        self.assertEqual(factor, 0.0)

    def test_percent_source_is_converted_to_opendrift_fraction(self) -> None:
        factor = wind_drift_factor_for_record(
            {"windage": 1.5},
            "windage",
            WindDriftSettings(mode="dataset", source_scale="percent"),
        )

        self.assertEqual(factor, 0.015)

    def test_fraction_source_is_not_converted(self) -> None:
        factor = wind_drift_factor_for_record(
            {"windage": 0.015},
            "windage",
            WindDriftSettings(mode="dataset", source_scale="fraction"),
        )

        self.assertEqual(factor, 0.015)

    def test_dataset_wind_drift_rejects_invalid_scales_and_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            wind_drift_factor_for_record(
                {"windage": 1.01},
                "windage",
                WindDriftSettings(mode="dataset", source_scale="fraction"),
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            wind_drift_factor_for_record(
                {"windage": 101},
                "windage",
                WindDriftSettings(mode="dataset", source_scale="percent"),
            )
        with self.assertRaisesRegex(ValueError, "supported wind-drift source scale"):
            wind_drift_factor_for_record(
                {"windage": 0.015},
                "windage",
                WindDriftSettings(mode="dataset", source_scale="ratio"),
            )

    def test_dataset_wind_drift_rejects_nonfinite_values(self) -> None:
        for source_scale in ("fraction", "percent"):
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(source_scale=source_scale, value=value):
                    with self.assertRaisesRegex(ValueError, "finite"):
                        wind_drift_factor_for_record(
                            {"windage": value},
                            "windage",
                            WindDriftSettings(
                                mode="dataset",
                                source_scale=source_scale,
                            ),
                        )

    def test_measurement_rule_interpolates_between_user_thresholds(self) -> None:
        factor = wind_drift_factor_for_record(
            {"length_cm": 50},
            "",
            WindDriftSettings(
                mode="measurement",
                measurement_column="length_cm",
                measurement_minimum=0,
                measurement_maximum=100,
                wind_drift_minimum_percent=1,
                wind_drift_maximum_percent=3,
            ),
        )

        self.assertEqual(factor, 0.02)

    def test_text_decomposition_value_uses_saved_integer_mapping(self) -> None:
        observation = canonicalize_observation(
            {"id": "one", "taxon": "test", "condition": "fresh", "sst": 25,
             "lon": -40, "lat": -25, "date": "2025-01-01", "time": "12:00"},
            ColumnMapping(stranding_identifier="id", taxon_label="taxon",
                          decomposition_code="condition", sea_surface_temperature="sst",
                          longitude="lon", latitude="lat", observed_date="date", observed_time="time"),
            ThermalDurationProfile(temperature_boundaries_celsius=[24], scenario_days={1: [3, 2]}),
            wind_drift_settings=WindDriftSettings(mode="none"),
            decomposition_value_map={"fresh": 1},
        )
        self.assertEqual(observation.decomposition_code, 1)
        self.assertEqual(observation.reverse_drift_duration_days, 2)

    def test_dms_coordinates_are_converted_before_planning(self) -> None:
        mapping = ColumnMapping(
            stranding_identifier="record_id",
            taxon_label="taxon",
            decomposition_code="condition",
            sea_surface_temperature="sst",
            wind_drift_factor="windage",
            longitude="longitude",
            latitude="latitude",
            observed_date="date",
            observed_time="time",
        )
        observation = canonicalize_observation(
            {
                "record_id": "obs-18",
                "taxon": "Marine fauna",
                "condition": 3,
                "sst": 24.0,
                "windage": 0.015,
                "longitude": "38 07 12 W",
                "latitude": "12 33 00 S",
                "date": "2026-04-24",
                "time": "10:00",
            },
            mapping,
            build_default_duration_profile(),
            coordinate_format="degrees_minutes_seconds",
        )

        self.assertAlmostEqual(observation.longitude, -38.12)
        self.assertAlmostEqual(observation.latitude, -12.55)


class EnvironmentalReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "environment"
        self.root.mkdir(parents=True, exist_ok=True)
        self.dataset = self.root / "forcing.nc"
        xr.Dataset(
            data_vars={
                "uo": (("time", "lat", "lon"), np.zeros((1, 2, 2))),
                "thetao": (("time", "lat", "lon"), np.zeros((1, 2, 2))),
            },
            coords={
                "time": ("time", [0], {"standard_name": "time", "units": "hours since 2026-01-01"}),
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(self.dataset)

    def test_inspection_reads_netcdf_metadata(self) -> None:
        inspection = inspect_environment_reader(self.dataset)

        self.assertIn("uo", inspection.variables)
        self.assertIn("longitude", inspection.standard_names.values())
        self.assertIn("lon", inspection.coordinate_variables)
        self.assertIsNotNone(getattr(inspection, "extent", None))
        self.assertEqual(
            inspection.extent,
            SpatialExtent(-39.0, -38.0, -13.0, -12.0),
        )

    def test_inspection_reports_temporal_grid_and_variable_metadata(self) -> None:
        metadata_dataset = self.root / "forcing_metadata.nc"
        xr.Dataset(
            data_vars={
                "uo": (
                    ("time", "lat", "lon"),
                    np.zeros((3, 3, 3)),
                    {
                        "standard_name": "eastward_sea_water_velocity",
                        "units": "m s-1",
                        "grid_mapping": "crs",
                    },
                ),
                "crs": ((), 0, {"spatial_ref": "EPSG:4326"}),
            },
            coords={
                "time": (
                    "time",
                    [0.0, 6.0, 12.0],
                    {
                        "standard_name": "time",
                        "units": "hours since 2026-01-01 00:00:00",
                    },
                ),
                "lat": (
                    "lat",
                    [-13.0, -12.5, -12.0],
                    {"standard_name": "latitude", "units": "degrees_north"},
                ),
                "lon": (
                    "lon",
                    [-39.0, -38.5, -38.0],
                    {"standard_name": "longitude", "units": "degrees_east"},
                ),
            },
        ).to_netcdf(metadata_dataset)

        inspection = inspect_environment_reader(metadata_dataset)

        self.assertEqual(inspection.variable_units["uo"], "m s-1")
        self.assertEqual(inspection.variable_dimensions["uo"], ("time", "lat", "lon"))
        self.assertEqual(inspection.time_name, "time")
        self.assertEqual(inspection.time_start, "2026-01-01T00:00:00")
        self.assertEqual(inspection.time_end, "2026-01-01T12:00:00")
        self.assertEqual(inspection.time_count, 3)
        self.assertEqual(inspection.temporal_resolution_seconds, 21600.0)
        self.assertTrue(inspection.time_is_monotonic)
        self.assertTrue(inspection.time_is_regular)
        self.assertEqual(inspection.grid_type, "rectilinear")
        self.assertEqual(inspection.longitude_resolution, 0.5)
        self.assertEqual(inspection.latitude_resolution, 0.5)
        self.assertEqual(inspection.crs, "EPSG:4326")

    def test_inspection_emits_structured_diagnostic_when_time_is_missing(self) -> None:
        no_time_dataset = self.root / "forcing_without_time.nc"
        xr.Dataset(
            data_vars={"uo": (("lat", "lon"), np.zeros((2, 2)))},
            coords={
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(no_time_dataset)

        inspection = inspect_environment_reader(no_time_dataset)

        diagnostic = next(
            item for item in inspection.diagnostics
            if item.code == "temporal_coordinate_missing"
        )
        self.assertEqual(diagnostic.level, "warning")
        self.assertIn("time coordinate", diagnostic.message.lower())

    def test_inspection_diagnoses_irregular_and_non_monotonic_time(self) -> None:
        irregular_dataset = self.root / "forcing_irregular_time.nc"
        xr.Dataset(
            data_vars={"uo": (("time", "lat", "lon"), np.zeros((4, 2, 2)))},
            coords={
                "time": (
                    "time",
                    [0.0, 6.0, 3.0, 12.0],
                    {
                        "standard_name": "time",
                        "units": "hours since 2026-01-01 00:00:00",
                    },
                ),
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(irregular_dataset)

        inspection = inspect_environment_reader(irregular_dataset)
        diagnostic_codes = {item.code for item in inspection.diagnostics}

        self.assertFalse(inspection.time_is_monotonic)
        self.assertFalse(inspection.time_is_regular)
        self.assertIn("non_monotonic_time", diagnostic_codes)
        self.assertIn("irregular_time_step", diagnostic_codes)

    def test_intersection_uses_shared_coverage_and_applies_buffer(self) -> None:
        from marine_drift_desktop.core import environment

        self.assertTrue(hasattr(environment, "intersect_extents"))
        result = environment.intersect_extents(
            [
                SpatialExtent(-50.0, -30.0, -40.0, -20.0),
                SpatialExtent(-45.0, -25.0, -35.0, -15.0),
            ],
            buffer_degrees=0.5,
        )
        self.assertEqual(result, SpatialExtent(-45.5, -29.5, -35.5, -19.5))

    def test_intersection_rejects_environmental_files_without_overlap(self) -> None:
        from marine_drift_desktop.core import environment

        self.assertTrue(hasattr(environment, "intersect_extents"))
        with self.assertRaisesRegex(ValueError, "do not overlap"):
            environment.intersect_extents(
                [
                    SpatialExtent(-50.0, -40.0, -30.0, -20.0),
                    SpatialExtent(-30.0, -20.0, -30.0, -20.0),
                ],
                buffer_degrees=0.0,
            )

    def test_inspection_normalizes_zero_to_360_longitudes(self) -> None:
        normalized_dataset = self.root / "forcing_360.nc"
        xr.Dataset(
            data_vars={"uo": (("lat", "lon"), np.zeros((2, 2)))},
            coords={
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [321.0, 322.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(normalized_dataset)

        inspection = inspect_environment_reader(normalized_dataset)

        self.assertEqual(getattr(inspection, "longitude_convention", None), "0_to_360")
        self.assertEqual(
            inspection.extent,
            SpatialExtent(-39.0, -38.0, -13.0, -12.0),
        )

    def test_reader_catalog_replaces_legacy_environment_requirements(self) -> None:
        observation = self.root / "observations.csv"
        observation.write_text(
            "id,taxon,decomp,sst,wind,lon,lat,date,time\n"
            "obs-01,Marine fauna,3,22.0,0.015,-38.12,-12.55,2026-04-24,10:37\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = observation
        request.data_sources.output_directory = self.root / "outputs"
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(path=self.dataset, roles=["Currents"])
        ]
        request.column_mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            sea_surface_temperature="sst",
            wind_drift_factor="wind",
            longitude="lon",
            latitude="lat",
            observed_date="date",
            observed_time="time",
        )

        summary = SimulationWorkflowService().preview(request)

        self.assertTrue(summary.is_valid)


class LandmaskAdjustmentTests(unittest.TestCase):
    def test_position_extent_check_uses_generic_spatial_extent(self) -> None:
        extent = SpatialExtent(
            min_longitude=-50.0,
            max_longitude=-30.0,
            min_latitude=-40.0,
            max_latitude=-20.0,
        )

        self.assertTrue(is_position_within_extent(-38.0, -25.0, extent))
        self.assertFalse(is_position_within_extent(-60.0, -25.0, extent))

    def test_land_position_is_shifted_to_nearby_water(self) -> None:
        extent = SpatialExtent(
            min_longitude=-50.0,
            max_longitude=-30.0,
            min_latitude=-40.0,
            max_latitude=-20.0,
        )

        def is_land(longitude: float, latitude: float) -> bool:
            return abs(longitude + 38.0) < 0.015 and abs(latitude + 25.0) < 0.015

        adjustment = adjust_to_nearby_water(
            longitude=-38.0,
            latitude=-25.0,
            is_land=is_land,
            extent=extent,
            shift_degrees=0.01,
            max_radius_degrees=0.05,
        )

        self.assertTrue(adjustment.was_adjusted)
        self.assertTrue(adjustment.is_within_extent)
        self.assertFalse(is_land(adjustment.longitude, adjustment.latitude))


if __name__ == "__main__":
    unittest.main()
