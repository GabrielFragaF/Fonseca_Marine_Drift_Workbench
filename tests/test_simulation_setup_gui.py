from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout, QComboBox, QMessageBox, QScrollArea, QStackedWidget

from marine_drift_desktop.ui.components import AnimatedStackedWidget
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from marine_drift_desktop.ui.pages.simulation_setup_page import SimulationSetupPage
from marine_drift_desktop.ui.theme import build_stylesheet
from tools.render_gui_review import (
    SIMULATION_REVIEW_CASES,
    SIMULATION_REVIEW_SIZES,
    configure_simulation_review_case,
)


class SimulationSetupPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = SimulationSetupPage()
        self.page.resize(1200, 720)
        self.page.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.page.close()

    def test_builder_exposes_six_ordered_decisions(self) -> None:
        self.assertEqual(
            self.page.STEP_TITLES,
            (
                "Study area",
                "Observations",
                "Drift duration",
                "Windage",
                "Particle release",
                "Model physics",
            ),
        )
        self.assertIsInstance(self.page.configuration_stack, QStackedWidget)
        self.assertEqual(self.page.configuration_stack.count(), 6)
        self.assertEqual(self.page.current_step_index, 0)
        self.assertEqual(set(self.page.step_states.values()), {"not_started"})
        self.assertIsInstance(self.page.configuration_stack, AnimatedStackedWidget)

    def test_three_column_builder_keeps_summary_in_the_viewport(self) -> None:
        progress_width = self.page.progress_panel.width()
        center_width = self.page.configuration_panel.width()
        summary_width = self.page.summary_panel.width()
        self.assertGreater(center_width, progress_width)
        self.assertGreater(center_width, summary_width)
        self.assertTrue(self.page.summary_panel.isVisibleTo(self.page))
        summary_right = self.page.summary_panel.mapTo(
            self.page, self.page.summary_panel.rect().bottomRight()
        ).x()
        self.assertLess(summary_right, self.page.viewport().width())
        self.assertIsInstance(self.page.summary_scroll, QScrollArea)
        self.assertIsInstance(self.page.configuration_stack.currentWidget(), QScrollArea)

    def test_builder_has_semantic_state_styling(self) -> None:
        stylesheet = build_stylesheet("Segoe UI")
        self.assertIn("QFrame#SetupProgress", stylesheet)
        self.assertIn("QFrame#SetupConfiguration", stylesheet)
        self.assertIn('QLabel#SetupSummaryItem[state="valid"]', stylesheet)
        self.assertIn('QLabel#SetupStepFeedback[level="error"]', stylesheet)

    def test_model_timestep_is_visible_in_model_physics_step(self) -> None:
        self.page.set_current_step(5)
        self.assertTrue(self.page.advanced_group.isAncestorOf(self.page.model_time_step))

    def test_continue_validates_current_step_before_advancing(self) -> None:
        self.page.min_lon.setValue(10.0)
        self.page.max_lon.setValue(5.0)
        self.page.continue_step_button.click()
        self.assertEqual(self.page.current_step_index, 0)
        self.assertEqual(self.page.step_states[0], "error")
        self.assertIn("Minimum", self.page.step_feedback.text())

        self.page.min_lon.setValue(-10.0)
        self.page.max_lon.setValue(5.0)
        self.page.continue_step_button.click()
        self.assertEqual(self.page.step_states[0], "valid")
        self.assertEqual(self.page.current_step_index, 1)
        self.assertEqual(self.page.step_states[1], "incomplete")

    def test_method_specific_fields_use_progressive_disclosure(self) -> None:
        self.page.set_current_step(2)
        self.page.duration_mode.setCurrentIndex(
            self.page.duration_mode.findData("fixed")
        )
        self.assertTrue(self.page.fixed_duration_panel.isVisibleTo(self.page))
        self.assertFalse(self.page.duration_profile_panel.isVisibleTo(self.page))

        self.page.set_current_step(3)
        self.page.wind_mode.setCurrentIndex(self.page.wind_mode.findData("none"))
        self.assertFalse(self.page.windage_dataset_panel.isVisibleTo(self.page))
        self.assertFalse(self.page.windage_fixed_panel.isVisibleTo(self.page))
        self.assertFalse(self.page.windage_measurement_panel.isVisibleTo(self.page))

        self.page.set_current_step(4)
        self.page.release_strategy.setCurrentIndex(
            self.page.release_strategy.findData("multiple")
        )
        self.assertTrue(self.page.release_scenarios_panel.isVisibleTo(self.page))
        self.assertFalse(self.page.fixed_start_panel.isVisibleTo(self.page))
        self.page.release_strategy.setCurrentIndex(
            self.page.release_strategy.findData("fixed_hour")
        )
        self.assertFalse(self.page.release_scenarios_panel.isVisibleTo(self.page))
        self.assertTrue(self.page.fixed_start_panel.isVisibleTo(self.page))

    def test_uncertainty_toggles_control_numeric_fields(self) -> None:
        self.page.set_current_step(5)
        self.page.current_uncertainty_toggle.setChecked(False)
        self.assertFalse(self.page.current_uncertainty.isVisibleTo(self.page))
        self.page.current_uncertainty_toggle.setChecked(True)
        self.assertTrue(self.page.current_uncertainty.isVisibleTo(self.page))

        self.page.wind_uncertainty_toggle.setChecked(False)
        self.assertFalse(self.page.wind_uncertainty.isVisibleTo(self.page))

    def test_summary_updates_from_active_methods(self) -> None:
        self.page.duration_mode.setCurrentIndex(
            self.page.duration_mode.findData("fixed")
        )
        self.page.fixed_duration_days.setValue(12)
        self.assertIn("12 days", self.page.summary_labels[2].text())

        self.page.wind_mode.setCurrentIndex(self.page.wind_mode.findData("fixed"))
        self.page.fixed_wind_percent.setValue(1.5)
        self.assertIn("1.5%", self.page.summary_labels[3].text())
        self.assertIn("0.015", self.page.summary_labels[3].text())

    def test_validation_issues_override_display_without_changing_step_state(self) -> None:
        self.page.step_states[2] = "valid"
        self.page.step_states[3] = "valid"
        self.page.validation_step_issues = {
            2: [SimpleNamespace(level="warning"), SimpleNamespace(level="error")],
            3: [SimpleNamespace(level="warning")],
        }
        self.page._refresh_step_ui()
        self.assertEqual(self.page.step_states[2], "valid")
        self.assertEqual(self.page.step_states[3], "valid")
        self.assertIn("Fix required", self.page.step_items[2].text())
        self.assertIn("Review", self.page.step_items[3].text())
        self.assertNotIn("Ready", self.page.compact_step_selector.itemText(2))
        self.assertEqual(self.page.step_items[2].foreground().color().name(), "#b34444")
        self.assertEqual(self.page.summary_labels[2].property("state"), "error")
        self.assertEqual(self.page.summary_labels[3].property("state"), "warning")
        self.page.step_states[3] = "error"
        self.page._refresh_step_ui()
        self.assertEqual(self.page.summary_labels[3].property("state"), "error")
        self.page.validation_step_issues = {}
        self.page._refresh_step_ui()
        self.assertIn("Ready", self.page.step_items[2].text())

    def test_windage_measurement_form_fits_without_horizontal_scrolling(self) -> None:
        self.assertIsInstance(self.page.windage_measurement_scroll, QScrollArea)
        self.assertEqual(
            self.page.windage_measurement_scroll.horizontalScrollBarPolicy(),
            Qt.ScrollBarAlwaysOff,
        )

    def test_each_setup_subsection_uses_responsive_width(self) -> None:
        for index in range(self.page.configuration_stack.count()):
            section = self.page.configuration_stack.widget(index)
            self.assertIsInstance(section, QScrollArea)
            self.assertEqual(section.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
            self.assertLess(section.widget().minimumWidth(), 820)

    def test_scientific_units_preserve_standard_degree_symbols(self) -> None:
        self.assertEqual(self.page.temperature_boundary_fields[0].suffix(), " °C")
        self.assertIn("°C", self.page.duration_table.horizontalHeaderItem(2).text())
        self.assertLess(self.page.windage_measurement_panel.minimumWidth(), 820)

    def test_duration_editor_adds_and_removes_rows_and_temperature_bands(self) -> None:
        self.assertIsInstance(self.page.duration_profile_scroll, QScrollArea)
        self.assertEqual(self.page.duration_profile_scroll.horizontalScrollBarPolicy(), Qt.ScrollBarAlwaysOff)
        self.assertEqual(self.page.duration_table.horizontalScrollBarPolicy(), Qt.ScrollBarAsNeeded)
        initial_rows = self.page.duration_table.rowCount()
        initial_columns = self.page.duration_table.columnCount()
        self.page.add_duration_state()
        self.assertEqual(self.page.duration_table.rowCount(), initial_rows + 1)
        self.page.duration_table.selectRow(initial_rows)
        self.page.remove_selected_duration_state()
        self.assertEqual(self.page.duration_table.rowCount(), initial_rows)

        self.page.add_temperature_boundary(28.5)
        self.assertEqual(self.page.duration_table.columnCount(), initial_columns + 1)
        self.assertIn(28.5, self.page.duration_boundaries)
        self.page.duration_table.selectColumn(2)
        self.page.remove_selected_temperature_band()
        self.assertEqual(self.page.duration_table.columnCount(), initial_columns)

    def test_add_temperature_button_creates_a_visible_editable_boundary(self) -> None:
        self.page.set_current_step(2)
        initial_fields = len(self.page.temperature_boundary_fields)
        initial_columns = self.page.duration_table.columnCount()
        self.page.add_temperature_band_button.click()
        self.app.processEvents()
        self.assertEqual(len(self.page.temperature_boundary_fields), initial_fields + 1)
        self.assertEqual(self.page.duration_table.columnCount(), initial_columns + 1)
        self.assertFalse(self.page.temperature_boundary_fields[-1].isHidden())

    def test_summary_toggle_reclaims_space_and_preserves_step_references(self) -> None:
        step_list = self.page.internal_step_list
        labels = tuple(self.page.summary_labels)
        width = self.page.configuration_panel.width()
        self.page.summary_toggle_button.click()
        self.app.processEvents()
        self.assertFalse(self.page.summary_panel.isVisible())
        self.assertGreater(self.page.configuration_panel.width(), width)
        self.page.resize(800, 720)
        self.app.processEvents()
        self.assertFalse(self.page.summary_panel.isVisible())
        self.page.summary_toggle_button.click()
        self.app.processEvents()
        self.assertTrue(self.page.summary_panel.isVisible())
        self.assertIs(self.page.internal_step_list, step_list)
        self.assertEqual(tuple(self.page.summary_labels), labels)

    def test_expanded_forms_fit_compact_and_desktop_centers(self) -> None:
        self.page.setStyleSheet(build_stylesheet("Segoe UI"))
        self.page.position_search_toggle.setChecked(True)
        self.page.selection_mode.setCurrentIndex(self.page.selection_mode.findData("random"))
        self.page.wind_mode.setCurrentIndex(self.page.wind_mode.findData("measurement"))
        self.page.release_strategy.setCurrentIndex(self.page.release_strategy.findData("multiple_fixed"))
        for width in (800, 1090, 1110, 1200, 1440):
            self.page.resize(width, 900)
            for index in range(6):
                with self.subTest(width=width, step=index):
                    self.page.set_current_step(index)
                    for _ in range(4):
                        self.app.processEvents()
                    section = self.page.configuration_stack.currentWidget()
                    self.assertEqual(section.horizontalScrollBar().maximum(), 0)
                    self.assertLessEqual(section.widget().width(), section.viewport().width())
                    for field in section.widget().findChildren(QComboBox):
                        if field.isVisibleTo(section):
                            right = field.mapTo(section.widget(), field.rect().bottomRight()).x()
                            self.assertLess(right, section.widget().width())
                    self.assertLessEqual(self.page.particle_count.width(), 190)
                    if index == 0:
                        self.assertEqual(self.page.area_map.height(), max(
                            260, min(400, (self.page.area_map.width() - 24) // 2 + 100)))

    def test_growing_duration_table_keeps_toolbar_and_form_in_view(self) -> None:
        self.page.resize(800, 900)
        self.page.set_current_step(2)
        for boundary in range(25, 40):
            self.page.add_temperature_boundary(float(boundary))
        for _ in range(4):
            self.app.processEvents()
        self.assertGreater(self.page.duration_table.horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.page.duration_profile_scroll.horizontalScrollBar().maximum(), 0)
        self.assertEqual(self.page.configuration_stack.currentWidget().horizontalScrollBar().maximum(), 0)
        for button in (self.page.add_duration_state_button, self.page.remove_duration_state_button,
                       self.page.add_temperature_band_button, self.page.remove_temperature_band_button):
            right = button.mapTo(self.page.duration_profile_panel, button.rect().bottomRight()).x()
            self.assertLess(right, self.page.duration_profile_panel.width())
            self.assertFalse(self.page.duration_table.isAncestorOf(button))

    def test_dynamically_added_observation_filters_fit_the_form(self) -> None:
        window = MarineDriftMainWindow()
        try:
            window.resize(1200, 900)
            window.show()
            window.show_workbench()
            window.stage_navigation.setCurrentRow(2)
            page = window.simulation_setup_page
            page.set_current_step(1)
            page.selection_mode.setCurrentIndex(page.selection_mode.findData("filter"))
            window._add_filter_condition()
            row = page.filter_condition_rows[-1]
            for _ in range(4):
                self.app.processEvents()
            self.assertIs(row, window.filter_condition_rows[-1])
            self.assertEqual(row.container.layout().direction(), QBoxLayout.TopToBottom)
            section = page.configuration_stack.currentWidget()
            self.assertLessEqual(section.widget().width(), section.viewport().width())
            for field in (row.connector, row.column, row.operator, row.value, row.remove_button):
                right = field.mapTo(section.widget(), field.rect().bottomRight()).x()
                self.assertLess(right, section.widget().width())
        finally:
            with patch.object(QMessageBox, "question", return_value=QMessageBox.Discard):
                window.close()

    def test_duration_rows_can_use_dataset_factor_labels(self) -> None:
        self.page.set_decomposition_values(["fresh", "moderate", "advanced"])
        self.assertEqual(
            [self.page.duration_table.item(row, 0).text() for row in range(3)],
            ["fresh", "moderate", "advanced"],
        )
        self.assertEqual(
            self.page.decomposition_mapping(),
            {"fresh": 1, "moderate": 2, "advanced": 3},
        )

    def test_temperature_boundaries_cannot_be_inverted(self) -> None:
        self.page.add_temperature_boundary(28.0)
        first, second = self.page.temperature_boundary_fields
        self.assertLess(first.maximum(), second.value())
        self.assertGreater(second.minimum(), first.value())
        first.setValue(40.0)
        self.assertLess(first.value(), second.value())

    def test_invalid_model_code_explains_the_table_row(self) -> None:
        self.page.duration_table.item(0, 1).setText("fresh")
        with self.assertRaisesRegex(ValueError, "Row 1"):
            self.page.decomposition_mapping()

    def test_remove_temperature_band_defaults_to_the_last_band(self) -> None:
        self.page.add_temperature_boundary(28.0)
        self.page.duration_table.clearSelection()
        self.page.remove_selected_temperature_band()
        self.assertEqual(self.page.duration_boundaries, [24.0])

    def test_large_particle_release_is_a_nonblocking_warning(self) -> None:
        self.page.release_strategy.setCurrentIndex(
            self.page.release_strategy.findData("multiple")
        )
        self.page.iteration_count.setValue(15)
        self.page.particle_count.setValue(100_000)
        state, message = self.page.validate_step(4)
        self.assertEqual(state, "warning")
        self.assertIn("workload", message.lower())

    def test_visual_review_contract_covers_every_internal_step_and_state(self) -> None:
        self.assertEqual(SIMULATION_REVIEW_SIZES["wide"], (1440, 900))
        self.assertEqual(SIMULATION_REVIEW_SIZES["compact"], (1080, 760))
        self.assertEqual(
            tuple(case.step_index for case in SIMULATION_REVIEW_CASES),
            tuple(range(6)),
        )
        self.assertEqual(
            {case.state for case in SIMULATION_REVIEW_CASES},
            {"default", "advanced-expanded", "incomplete", "valid", "warning"},
        )

    def test_compact_review_cases_keep_configuration_dominant(self) -> None:
        window = MarineDriftMainWindow()
        try:
            window.resize(*SIMULATION_REVIEW_SIZES["compact"])
            window.show()
            for case in SIMULATION_REVIEW_CASES:
                with self.subTest(case=case.name):
                    configure_simulation_review_case(window, case.name)
                    self.app.processEvents()
                    page = window.simulation_setup_page
                    self.assertEqual(page.current_step_index, case.step_index)
                    self.assertGreater(
                        page.configuration_panel.width(), page.progress_panel.width()
                    )
                    self.assertTrue(page.compact_step_selector.isVisible())
                    self.assertEqual(page.compact_step_selector.currentIndex(), case.step_index)
                    self.assertGreaterEqual(page.configuration_panel.width(), 700)
                    self.assertEqual(
                        page.builder_layout.getItemPosition(
                            page.builder_layout.indexOf(page.summary_panel)
                        )[:2], (1, 0)
                    )
                    self.assertEqual(len(page.summary_labels), 6)
        finally:
            window.project_dirty = False
            window.close()


class SimulationSetupSynchronizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MarineDriftMainWindow()

    def tearDown(self) -> None:
        self.window.project_dirty = False
        self.window.close()

    def test_builder_controls_synchronize_into_simulation_request(self) -> None:
        page = self.window.simulation_setup_page
        page.duration_mode.setCurrentIndex(page.duration_mode.findData("fixed"))
        page.fixed_duration_days.setValue(9)
        page.wind_mode.setCurrentIndex(page.wind_mode.findData("none"))
        page.release_strategy.setCurrentIndex(
            page.release_strategy.findData("fixed_hour")
        )
        page.fixed_start_hour.setValue(8)
        page.current_uncertainty_toggle.setChecked(False)
        page.wind_uncertainty_toggle.setChecked(True)
        page.wind_uncertainty.setValue(0.22)

        self.window._start_preflight = lambda: None
        self.window._preview_configuration()
        settings = self.window.request.settings
        self.assertEqual(settings.duration.mode, "fixed")
        self.assertEqual(settings.duration.fixed_days, 9)
        self.assertEqual(settings.wind_drift.mode, "none")
        self.assertEqual(settings.iteration_count, 1)
        self.assertEqual(settings.start_time_mode, "fixed_hour")
        self.assertEqual(settings.fixed_start_hour, 8)
        self.assertFalse(settings.current_uncertainty_enabled)
        self.assertTrue(settings.wind_uncertainty_enabled)
        self.assertEqual(settings.wind_uncertainty, 0.22)

    def test_global_review_transition_requires_valid_internal_steps(self) -> None:
        self.window.stage_navigation.setCurrentRow(2)
        self.window.next_button.click()
        self.assertEqual(self.window.stage_navigation.currentRow(), 2)
        self.assertIn(
            self.window.simulation_setup_page.current_step_index,
            {2, 3},
        )

        page = self.window.simulation_setup_page
        page.duration_mode.setCurrentIndex(page.duration_mode.findData("fixed"))
        page.wind_mode.setCurrentIndex(page.wind_mode.findData("none"))
        self.window.next_button.click()
        self.assertEqual(self.window.stage_navigation.currentRow(), 3)


if __name__ == "__main__":
    unittest.main()
