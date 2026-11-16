import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSpinBox
from PySide6.QtGui import QFontDatabase
from marine_drift_desktop.app import _select_ui_font
from marine_drift_desktop.ui.pages.results_export_page import ResultsExportPage
from marine_drift_desktop.ui.pages.environment_page import EnvironmentPage
from marine_drift_desktop.ui.theme import build_stylesheet


class VisualRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_bundled_font_loads_and_repeated_selection_is_stable(self):
        self.assertEqual(_select_ui_font(self.app), "Source Sans 3")
        self.assertEqual(_select_ui_font(self.app), "Source Sans 3")
        styles = QFontDatabase.styles("Source Sans 3")
        self.assertIn("Regular", styles)
        self.assertIn("Semibold", styles)
        self.assertIn("Bold", styles)

    def test_export_cards_reflow_without_losing_values(self):
        page = ResultsExportPage()
        page.setStyleSheet(build_stylesheet())
        page.positions_per_day.setValue(3)
        page.csv_toggle.setChecked(True)
        page.show()
        try:
            for width, compact in ((1200, False), (760, True), (1200, False)):
                page.resize(width, 850)
                self.app.processEvents()
                self.assertEqual(page._compact_layout, compact)
                for index, card in enumerate(page._cards):
                    position = page._cards_grid.getItemPosition(page._cards_grid.indexOf(card))
                    self.assertEqual(position[:2], (index, 0) if compact else divmod(index, 2))
                self.assertEqual(page.positions_per_day.value(), 3)
                self.assertTrue(page.csv_toggle.isChecked())
        finally:
            page.close()

    def test_numeric_arrow_remains_clickable_with_bundled_style(self):
        page = ResultsExportPage()
        page.setStyleSheet(build_stylesheet())
        page.resize(1200, 850)
        page.show()
        self.app.processEvents()
        try:
            spin = page.positions_per_day
            option = QStyleOptionSpinBox()
            spin.initStyleOption(option)
            rect = spin.style().subControlRect(
                QStyle.CC_SpinBox, option, QStyle.SC_SpinBoxUp, spin
            )
            self.assertGreaterEqual(rect.width(), 24)
            QTest.mouseClick(spin, Qt.LeftButton, pos=rect.center())
            self.assertEqual(spin.value(), 2)
        finally:
            page.close()

    def test_compact_inspector_preserves_role_controls_and_can_scroll_to_actions(self):
        page = EnvironmentPage()
        page.setStyleSheet(build_stylesheet())
        page.resize(810, 650)
        page.show()
        self.app.processEvents()
        try:
            self.assertGreaterEqual(page.role_list.height(), 84)
            self.assertGreater(page.inspector_scroll.verticalScrollBar().maximum(), 0)
            page.inspector_scroll.ensureWidgetVisible(page.preview_coverage_button)
            self.app.processEvents()
            center = page.preview_coverage_button.mapTo(
                page.inspector_scroll.viewport(), page.preview_coverage_button.rect().center()
            )
            self.assertTrue(page.inspector_scroll.viewport().rect().contains(center))
        finally:
            page.close()
