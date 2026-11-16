from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from marine_drift_desktop.ui.pages.results_export_page import (
    ResultsExportPage, ResultsExportState,
)


class ResultsExportPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = ResultsExportPage()

    def tearDown(self) -> None:
        self.page.deleteLater()

    def test_page_uses_four_focused_cards_and_numeric_sampling(self) -> None:
        for name in ("ResultsSourceCard", "ResultsSamplingCard", "ResultsFormatsCard", "ResultsActivityCard"):
            self.assertIsNotNone(self.page.findChild(object, name))
        self.assertEqual(self.page.positions_per_day.value(), 1)
        self.assertTrue(self.page.parquet_toggle.isChecked())
        self.assertFalse(self.page.parquet_toggle.isEnabled())

    def test_inspection_sets_capacity_and_enables_export(self) -> None:
        self.page.apply_inspection({
            "accepted_file_count": 3,
            "particle_trajectory_count": 120,
            "max_positions_per_drift_day": 8,
            "estimated_rows": 840,
            "issues": [],
        })
        self.assertEqual(self.page.state, ResultsExportState.READY)
        self.assertEqual(self.page.positions_per_day.maximum(), 8)
        self.assertTrue(self.page.export_button.isEnabled())
        self.assertIn("840", self.page.capacity_label.text())

    def test_inspection_builds_environmental_variable_choices(self) -> None:
        self.page.apply_inspection({
            "accepted_file_count": 2,
            "particle_trajectory_count": 4,
            "max_positions_per_drift_day": 8,
            "estimated_rows": 8,
            "environmental_variables": [
                {"name": "sea_water_temperature", "label": "Sea-water temperature", "units": "K", "availability": "common"},
                {"name": "x_wind", "label": "Eastward wind", "units": "m s-1", "availability": "partial"},
            ],
            "issues": [],
        })

        self.assertEqual(self.page.selected_environmental_variables(), ["sea_water_temperature"])
        self.page.environment_variable_checks["x_wind"].setChecked(True)
        self.assertEqual(self.page.selected_environmental_variables(), ["sea_water_temperature", "x_wind"])

    def test_source_or_sampling_edit_requires_reinspection(self) -> None:
        self.page.apply_inspection({"accepted_file_count": 1, "max_positions_per_drift_day": 4})
        self.page.positions_per_day.setValue(2)
        self.assertEqual(self.page.state, ResultsExportState.UNINSPECTED)
        self.assertFalse(self.page.export_button.isEnabled())

    def test_completed_export_exposes_output_folder_action(self) -> None:
        self.page.apply_completion({"row_count": 25, "warnings": []})
        self.assertEqual(self.page.state, ResultsExportState.COMPLETED)
        self.assertTrue(self.page.open_button.isVisibleTo(self.page))

    def test_latest_run_populates_source_and_separate_export_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            self.page.set_latest_run(run)
            self.assertEqual(self.page.results_directory.text(), str(run))
            self.assertEqual(self.page.output_directory.text(), str(run / "exports"))


if __name__ == "__main__":
    unittest.main()
