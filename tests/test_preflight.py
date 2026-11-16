from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xarray as xr
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from marine_drift_desktop.core.environment import inspect_environment_reader
from marine_drift_desktop.core.preflight import run_preflight
from marine_drift_desktop.domain.models import (
    ColumnMapping,
    EnvironmentalReaderConfig,
    SimulationRequest,
)
from marine_drift_desktop.ui.preflight_worker import PreflightWorker


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "preflight"
        self.root.mkdir(parents=True, exist_ok=True)
        self.forcing = self.root / "default_forcing.nc"
        xr.Dataset(
            data_vars={
                "uo": (
                    ("time", "lat", "lon"),
                    np.zeros((2, 2, 2)),
                    {"standard_name": "eastward_sea_water_velocity"},
                ),
                "vo": (
                    ("time", "lat", "lon"),
                    np.zeros((2, 2, 2)),
                    {"standard_name": "northward_sea_water_velocity"},
                ),
            },
            coords={
                "time": (
                    "time",
                    [0.0, 6.0],
                    {
                        "standard_name": "time",
                        "units": "hours since 2026-01-01 00:00:00",
                    },
                ),
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(self.forcing)

    def _request(self, *, malformed_rows: int = 0) -> SimulationRequest:
        dataset = self.root / "observations.csv"
        rows = [
            "obs-1,Marine fauna,3,22,0.015,-38,-12,2026-01-03,10:00",
            "obs-2,Marine fauna,3,22,0.015,-38,-12,2026-01-04,11:00",
        ]
        rows.extend(
            f"bad-{index},Marine fauna,3,22,0.015,-38,-12,not-a-date,11:00"
            for index in range(malformed_rows)
        )
        dataset.write_text(
            "id,taxon,decomp,sst,windage,lon,lat,date,time\n"
            + "\n".join(rows)
            + "\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.settings.wind_drift.mode = "fixed"
        request.settings.wind_drift.fixed_percent = 0
        request.data_sources.observation_dataset = dataset
        request.data_sources.output_directory = self.root / "outputs"
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(self.forcing, ["Currents"])
        ]
        request.column_mapping = ColumnMapping(
            stranding_identifier="id",
            taxon_label="taxon",
            decomposition_code="decomp",
            sea_surface_temperature="sst",
            wind_drift_factor="windage",
            longitude="lon",
            latitude="lat",
            observed_date="date",
            observed_time="time",
        )
        request.settings.iteration_count = 3
        request.settings.particle_count = 4
        return request

    def test_preflight_returns_reusable_counts_and_workload(self) -> None:
        result = run_preflight(self._request(malformed_rows=1))

        self.assertTrue(result.is_ready)
        self.assertTrue(result.preparation_performed)
        self.assertEqual(result.source_rows, 3)
        self.assertEqual(result.selected_rows, 3)
        self.assertEqual(result.runnable_observations, 2)
        self.assertEqual(result.skipped_observations, 1)
        self.assertEqual(result.planned_model_iterations, 6)
        self.assertEqual(result.planned_particle_trajectories, 24)
        self.assertTrue(result.skip_reasons)
        self.assertIsNotNone(result.forcing_readiness)
        self.assertEqual(
            result.forcing_readiness.check("required_currents").level,
            "success",
        )
        observation_check = next(
            check for check in result.checks if check.key == "observation_data"
        )
        self.assertEqual(observation_check.level, "warning")
        self.assertFalse(observation_check.blocks_run)

    def test_forcing_window_uses_fixed_hour_and_iteration_offsets(self) -> None:
        forcing = self.root / "planned_window_forcing.nc"
        xr.Dataset(
            data_vars={
                "uo": (
                    ("time", "lat", "lon"),
                    np.zeros((2, 2, 2)),
                    {"standard_name": "eastward_sea_water_velocity"},
                ),
                "vo": (
                    ("time", "lat", "lon"),
                    np.zeros((2, 2, 2)),
                    {"standard_name": "northward_sea_water_velocity"},
                ),
            },
            coords={
                "time": (
                    "time",
                    [-50.0, 74.0],
                    {
                        "standard_name": "time",
                        "units": "hours since 2026-01-01 00:00:00",
                    },
                ),
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(forcing)
        request = self._request()
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(forcing, ["Ocean circulation"])
        ]
        request.settings.start_time_mode = "fixed_hour"
        request.settings.fixed_start_hour = 2
        request.settings.iteration_interval_hours = 2

        result = run_preflight(request)

        coverage = result.forcing_readiness.check("temporal_coverage")
        self.assertEqual(coverage.level, "success")
        self.assertIn(datetime(2025, 12, 29, 22, 0).isoformat(), coverage.detail)
        self.assertIn(datetime(2026, 1, 4, 2, 0).isoformat(), coverage.detail)

    def test_structurally_invalid_request_skips_expensive_preparation(self) -> None:
        result = run_preflight(SimulationRequest())

        self.assertFalse(result.is_ready)
        self.assertFalse(result.preparation_performed)
        self.assertEqual(result.source_rows, 0)
        self.assertTrue(any(check.blocks_run for check in result.checks))

    def test_missing_model_columns_are_individual_issues_with_navigation_targets(self) -> None:
        request = self._request()
        request.settings.wind_drift.mode = "dataset"
        request.column_mapping.wind_drift_factor = ""
        request.column_mapping.sea_surface_temperature = ""
        result = run_preflight(request)
        issues = [check for check in result.checks if check.blocks_run]
        self.assertEqual({issue.field_ids for issue in issues}, {("sst_column",), ("wind_column",)})
        self.assertEqual({issue.subsection for issue in issues}, {2, 3})
        self.assertTrue(all(issue.target_step == "simulation_setup" for issue in issues))
        self.assertFalse(result.preparation_performed)

    def test_reader_role_error_names_the_file_and_catalog_row(self) -> None:
        request = self._request()
        request.data_sources.environment_readers[0].roles = []
        result = run_preflight(request)
        issue = next(check for check in result.checks if check.blocks_run)
        self.assertIn(self.forcing.name, issue.detail)
        self.assertEqual(issue.field_ids, ("environment_reader:0",))
        self.assertEqual(issue.target_step, "environmental_forcing")

    def test_zero_runnable_observations_is_blocking(self) -> None:
        request = self._request(malformed_rows=1)
        source = request.data_sources.observation_dataset
        assert source is not None
        source.write_text(
            "id,taxon,decomp,sst,windage,lon,lat,date,time\n"
            "bad,Marine fauna,3,22,0.015,-38,-12,not-a-date,11:00\n",
            encoding="utf-8",
        )

        result = run_preflight(request)

        self.assertFalse(result.is_ready)
        observation_check = next(
            check for check in result.checks if check.key == "observation_data"
        )
        self.assertTrue(observation_check.blocks_run)

    def test_preflight_retains_one_inspection_per_unique_environment_reader(self) -> None:
        forcing = self.root / "forcing.nc"
        xr.Dataset(
            data_vars={"uo": (("time", "lat", "lon"), np.zeros((2, 2, 2)))},
            coords={
                "time": (
                    "time",
                    [0.0, 6.0],
                    {
                        "standard_name": "time",
                        "units": "hours since 2026-01-01 00:00:00",
                    },
                ),
                "lat": ("lat", [-13.0, -12.0], {"standard_name": "latitude"}),
                "lon": ("lon", [-39.0, -38.0], {"standard_name": "longitude"}),
            },
        ).to_netcdf(forcing)
        request = self._request()
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(forcing, ["Currents"]),
            EnvironmentalReaderConfig(forcing, ["Temperature"]),
        ]
        request.settings.coverage.mode = "environment_intersection"
        request.settings.coverage.contributing_paths = [str(forcing)]

        with patch(
            "marine_drift_desktop.core.environment.inspect_environment_reader",
            wraps=inspect_environment_reader,
        ) as inspect:
            result = run_preflight(request)

        self.assertEqual(len(result.environment_inspections), 1)
        self.assertEqual(result.environment_inspections[0].path, forcing)
        self.assertEqual(inspect.call_count, 1)
        self.assertTrue(
            any(check.key == "environmental_forcing" for check in result.checks)
        )

    def test_qt_worker_emits_generation_and_preflight_result(self) -> None:
        worker = PreflightWorker(self._request(), generation=7)
        completed = QSignalSpy(worker.completed)
        failed = QSignalSpy(worker.failed)
        finished = QSignalSpy(worker.finished)

        worker.start()
        self.assertTrue(worker.wait(10_000))
        self.application.processEvents()
        self.assertEqual(finished.count(), 1)
        self.assertEqual(
            failed.count(),
            0,
            failed.at(0)[1] if failed.count() else "Unexpected preflight worker failure",
        )
        self.assertEqual(completed.count(), 1)

        generation, result = completed.at(0)
        self.assertEqual(generation, 7)
        self.assertTrue(result.is_ready)


if __name__ == "__main__":
    unittest.main()
