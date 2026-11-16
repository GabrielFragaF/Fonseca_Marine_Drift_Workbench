import unittest
from PySide6.QtWidgets import QApplication
from marine_drift_desktop.ui.pages.simulation_setup_page import SimulationSetupPage
from marine_drift_desktop.ui.area_map import _outlines, StudyAreaMap


class AreaMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_coordinate_edits_update_preview(self):
        page = SimulationSetupPage()
        for field, value in ((page.min_lon, -55), (page.max_lon, -35),
                             (page.min_lat, -34), (page.max_lat, -15)):
            field.setValue(value)
        self.assertEqual(page.area_map.bounds, (-55, -35, -34, -15))
        self.assertIn("Longitude -55 to -35", page.area_map.accessibleDescription())
        page.close()

    def test_offline_outline_has_global_coordinates(self):
        rings = _outlines()
        self.assertGreater(len(rings), 100)
        for ring in rings:
            for lon, lat in ring:
                self.assertTrue(-180.01 <= lon <= 180.01)
                self.assertTrue(-90 <= lat <= 90)

    def test_zoom_is_view_only_and_fit_follows_edits(self):
        widget = StudyAreaMap()
        widget.set_bounds(-44.7, -42, -24, -22)
        fitted = widget.view_bounds
        widget.zoom(0.5)
        self.assertLess(widget.view_bounds[1] - widget.view_bounds[0], fitted[1] - fitted[0])
        self.assertEqual(widget.bounds, (-44.7, -42, -24, -22))
        widget.show_world()
        self.assertEqual(widget.view_bounds, (-180, 180, -90, 90))
        widget.fit_to_bounds()
        self.assertEqual(widget.view_bounds, fitted)
        widget.set_bounds(170, 180, 80, 90)
        w, e, s, n = widget.view_bounds
        self.assertTrue(-180 <= w < e <= 180)
        self.assertTrue(-90 <= s < n <= 90)
        widget.set_bounds(10, -10, 0, 0)
        self.assertEqual(widget.view_bounds, (w, e, s, n))
