import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from marine_drift_desktop.core.trajectory_map import prepare_trajectory_map
from marine_drift_desktop.results_worker import run_worker
from marine_drift_desktop.ui.pages.results_export_page import ResultsExportPage, ResultsExportState
from marine_drift_desktop.ui.trajectory_map import _basemap_land
from tests.results_test_support import make_trajectory_netcdf


class TrajectoryMapGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.page = ResultsExportPage()
        self.card = self.page.trajectory_map
        for identifier in ("A", "B", "C"):
            for iteration in (1, 2):
                make_trajectory_netcdf(self.root / f"{identifier}-{iteration}.nc",
                                      identifier=identifier, iteration=iteration)
        self.page.results_directory.setText(str(self.root))

    def tearDown(self):
        self.card.shutdown()
        self.page.close()
        self.temp.cleanup()

    def wait_for_finish(self):
        deadline = time.monotonic() + 25
        while self.card._busy and time.monotonic() < deadline:
            QTest.qWait(30)
        self.assertFalse(self.card._busy, self.card.status.text())

    def test_full_worker_roundtrip_without_table_export(self):
        self.card.count.setValue(2)
        self.assertEqual(self.page.state, ResultsExportState.UNINSPECTED)
        self.card.generate()
        self.assertTrue(self.card._busy)
        self.wait_for_finish()
        self.assertIsNotNone(self.card.canvas.payload, self.card.status.text())
        self.assertEqual(len(self.card.canvas.payload["runs"]), 2)
        self.assertTrue(self.card.save_button.isEnabled())
        self.assertEqual(self.page.state, ResultsExportState.UNINSPECTED)
        self.assertFalse(list(self.root.glob("*.parquet")))

    def test_png_contains_selection_metadata_and_configuration_edits_invalidate(self):
        payload = prepare_trajectory_map(self.root, 2, 42)
        self.card.canvas.set_payload(payload)
        image_path = self.root / "map.png"
        self.card.canvas.save_png(image_path)
        image = QImage(str(image_path))
        self.assertFalse(image.isNull())
        metadata = json.loads(image.text("Marine Drift Workbench selection"))
        self.assertEqual(metadata["seed"], 42)
        self.assertEqual(len(metadata["runs"]), 2)
        self.assertNotIn("tracks", metadata["runs"][0])
        self.card.seed.setValue(43)
        self.assertIsNone(self.card.canvas.payload)
        self.assertFalse(self.card.save_button.isEnabled())

    def test_source_edits_cancel_stale_worker_and_cannot_publish_old_map(self):
        self.card.generate()
        self.page.results_directory.setText(str(self.root / "different"))
        self.wait_for_finish()
        self.assertIsNone(self.card.canvas.payload)
        QTest.qWait(3100)  # Cancellation timer must not access a deleted QProcess.

    def test_export_busy_disables_map_generation(self):
        self.page.set_state(ResultsExportState.EXPORTING)
        self.assertFalse(self.card.generate_button.isEnabled())
        self.card.generate()
        self.assertIsNone(self.card.controller.process)

    def test_failed_worker_start_releases_busy_state(self):
        with patch("marine_drift_desktop.ui.results_export_controller.sys.executable", "Z:/missing/python.exe"):
            self.card.generate()
            self.wait_for_finish()
        self.assertIsNone(self.card.controller.process)
        self.assertTrue(self.card.generate_button.isEnabled())
        self.assertIn("could not be started", self.card.status.text())

    def test_map_worker_emits_result_file(self):
        request = self.root / "request.json"
        request.write_text(json.dumps({"results_directory": str(self.root),
                                       "individual_count": 2, "seed": 42}), encoding="utf-8")
        with patch("marine_drift_desktop.results_worker._emit") as emit:
            self.assertEqual(run_worker("map", str(request)), 0)
        event = emit.call_args.args[0]
        self.assertEqual(event["event"], "map_ready")
        self.assertTrue(Path(event["path"]).is_file())

    def test_repainting_reuses_map_image_until_selection_changes(self):
        canvas = self.card.canvas
        canvas.set_payload(prepare_trajectory_map(self.root, 2, 42))
        canvas.resize(800, 500)
        canvas.grab()
        cached = canvas._cached_image
        self.assertIsNotNone(cached)
        canvas.grab()
        self.assertIs(canvas._cached_image, cached)
        canvas.set_payload(None)
        self.assertIsNone(canvas._cached_image)

    def test_offline_basemap_contains_detailed_land_polygons(self):
        land = _basemap_land()
        self.assertGreater(len(land), 100)
        self.assertTrue(all(len(polygon) >= 2 for polygon in land))
