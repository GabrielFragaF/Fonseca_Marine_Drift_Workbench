from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import xarray as xr
from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from marine_drift_desktop.core.environment import EnvironmentalReaderInspection
from marine_drift_desktop.ui.environment_catalog import (
    EnvironmentInspectionWorker,
    EnvironmentalCatalogModel,
)


class EnvironmentalCatalogModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "catalog"
        self.root.mkdir(parents=True, exist_ok=True)
        self.first = self.root / "currents_2026.nc"
        self.second = self.root / "wind_2026.nc"
        self.first.touch()
        self.second.touch()
        self.model = EnvironmentalCatalogModel()

    def test_batch_add_deduplicates_paths_and_preserves_order(self) -> None:
        result = self.model.add_paths([self.first, self.second, self.first])

        self.assertEqual(result.added_paths, (self.first, self.second))
        self.assertEqual(result.duplicate_paths, (self.first,))
        self.assertEqual(self.model.rowCount(), 2)
        self.assertEqual(self.model.entry_at(0).path, self.first)

    def test_remove_rows_handles_noncontiguous_selection(self) -> None:
        third = self.root / "waves.nc"
        third.touch()
        self.model.add_paths([self.first, self.second, third])

        removed = self.model.remove_rows([0, 2])

        self.assertEqual(set(removed), {self.first, third})
        self.assertEqual(self.model.rowCount(), 1)
        self.assertEqual(self.model.entry_at(0).path, self.second)

    def test_role_updates_preserve_multiple_roles_in_request_config(self) -> None:
        self.model.add_paths([self.first])

        self.model.update_roles(
            self.first,
            ["Ocean circulation", "Temperature & hydrography"],
            source="user",
        )
        config = self.model.to_configs()[0]

        self.assertEqual(
            config.roles,
            ["Ocean circulation", "Temperature & hydrography"],
        )
        self.assertEqual(self.model.entry_at(0).role_source, "user")

    def test_unreadable_file_remains_visible_as_blocking_error(self) -> None:
        unreadable = self.root / "broken.nc"
        self.model.add_paths([unreadable])

        self.model.apply_error(unreadable, "NetCDF header is invalid")
        entry = self.model.entry_at(0)

        self.assertEqual(entry.status, "error")
        self.assertIn("header", entry.error_message)
        self.assertEqual(self.model.rowCount(), 1)
        self.assertEqual(self.model.to_configs()[0].path, unreadable)

    def test_inspection_updates_temporal_spatial_and_status_columns(self) -> None:
        self.model.add_paths([self.first])
        inspection = EnvironmentalReaderInspection(
            path=self.first,
            time_start="2026-01-01T00:00:00",
            time_end="2026-12-31T18:00:00",
            grid_type="rectilinear",
            recognized_opendrift_variables=["x_sea_water_velocity"],
        )

        self.model.apply_inspection(self.first, inspection)

        self.assertEqual(self.model.entry_at(0).status, "ready")
        self.assertIn("2026-01-01", self.model.data(self.model.index(0, 2), Qt.DisplayRole))
        self.assertEqual(self.model.data(self.model.index(0, 4), Qt.DisplayRole), "Ready")

    def test_sort_uses_filename_and_status_values(self) -> None:
        self.model.add_paths([self.second, self.first])
        self.model.apply_error(self.second, "broken")

        self.model.sort(0, Qt.AscendingOrder)
        self.assertEqual(self.model.entry_at(0).path, self.first)

        self.model.sort(4, Qt.AscendingOrder)
        self.assertEqual(self.model.entry_at(0).status, "error")

    def test_inspection_worker_emits_metadata_without_blocking_model_updates(self) -> None:
        dataset = self.root / "worker_forcing.nc"
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
        ).to_netcdf(dataset)
        worker = EnvironmentInspectionWorker([dataset])
        inspected = QSignalSpy(worker.inspected)
        failed = QSignalSpy(worker.failed)

        worker.start()
        self.assertTrue(worker.wait(10_000))
        self.application.processEvents()

        self.assertEqual(failed.count(), 0)
        self.assertEqual(inspected.count(), 1)
        path, inspection = inspected.at(0)
        self.assertEqual(path, dataset)
        self.assertEqual(inspection.time_count, 2)


if __name__ == "__main__":
    unittest.main()
