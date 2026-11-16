import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QLocale, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox

from marine_drift_desktop.app import create_application
from marine_drift_desktop.ui.components import CompactDoubleSpinBox, SearchableColumnComboBox
from marine_drift_desktop.ui.pages.review_run_page import ReviewRunState
from marine_drift_desktop.ui.theme import build_stylesheet


class WindowsGuiPolishTests(unittest.TestCase):
    def test_message_boxes_define_readable_light_surface_and_text(self):
        stylesheet = build_stylesheet("Arial")
        self.assertIn("QMessageBox {", stylesheet)
        self.assertIn("QMessageBox QLabel", stylesheet)
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        _, self.window = create_application()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.project_dirty = False
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_home_opens_first_and_new_project_resets_work(self):
        window = self.window
        self.assertIs(window.workspace_stack.currentWidget(), window.welcome_page)
        window.welcome_page.new_project_button.click()
        window.project_name.setText("My project")
        window.stage_navigation.setCurrentRow(2)
        window.home_button.click()
        with patch(
            "marine_drift_desktop.ui.main_window.QMessageBox.question",
            return_value=QMessageBox.Discard,
        ):
            window.welcome_page.new_project_button.click()
        self.assertEqual(window.stage_navigation.currentRow(), 0)
        self.assertEqual(window.project_name.text(), "New reverse-drift project")

    def test_partner_logos_open_the_supplied_sites(self):
        with patch("marine_drift_desktop.ui.welcome.QDesktopServices.openUrl") as open_url:
            for button, url in zip(self.window.welcome_page.partner_buttons, (
                "https://www.lecufpr.net/", "https://thelabirinto.com/",
                "https://www.observatoire-pelagis.cnrs.fr/?lang=en",
            )):
                self.assertFalse(button.icon().isNull())
                button.click()
                self.assertEqual(open_url.call_args.args[0].toString(), url)
        self.assertEqual(len(self.window.welcome_page.partner_buttons), 3)

    def test_welcome_copy_and_tutorial_wording_are_publication_ready(self):
        page = self.window.welcome_page
        labels = " ".join(label.text() for label in page.findChildren(QLabel))
        self.assertEqual(page.tutorial_button.text(), "Explore the tutorial")
        self.assertEqual(page.new_project_button.text(), "Create new project")
        self.assertEqual(page.open_project_button.text(), "Open existing project")
        self.assertFalse(page.framework_logo.pixmap().isNull())
        self.assertEqual(self.window.tutorial_button.text(), "Tutorial")
        self.assertIn("marine megafauna stranding records", labels)
        self.assertIn("reproducible reverse-drift workflow", labels)
        self.assertIn(
            "Scalable reverse-drift framework transforms sea turtle strandings into "
            "indicators of at-sea mortality in the southwestern Atlantic",
            labels,
        )

        self.window.start_tutorial()
        self.assertTrue(self.window.guided_tour.counter.text().startswith("TUTORIAL"))
        self.assertEqual(self.window.guided_tour.exit_button.text(), "Exit tutorial")

    def test_finish_setup_reaches_review_and_blocks_invalid_setup(self):
        window = self.window
        window.show_workbench()
        window.stage_navigation.setCurrentRow(2)
        page = window.simulation_setup_page
        page.duration_mode.setCurrentIndex(page.duration_mode.findData("fixed"))
        page.wind_mode.setCurrentIndex(page.wind_mode.findData("none"))
        page.min_lon.setValue(20)
        page.max_lon.setValue(10)
        page.set_current_step(5)
        page.continue_step_button.click()
        self.assertEqual(window.stage_navigation.currentRow(), 2)
        self.assertEqual(page.current_step_index, 0)
        page.min_lon.setValue(-20)
        page.set_current_step(5)
        page.continue_step_button.click()
        self.assertEqual(window.stage_navigation.currentRow(), 3)

    def test_area_method_only_shows_relevant_controls(self):
        window = self.window
        window.show_workbench()
        window.stage_navigation.setCurrentRow(2)
        page = window.simulation_setup_page
        self.assertFalse(page.coverage_group.isHidden())
        self.assertTrue(page.manual_extent_panel.isHidden())
        page.study_area_preset.setCurrentIndex(page.study_area_preset.findData("manual"))
        self.assertTrue(page.coverage_group.isHidden())
        self.assertFalse(page.manual_extent_panel.isHidden())
        page.min_lon.setValue(-42.1234)
        page.study_area_preset.setCurrentIndex(0)
        self.assertFalse(page.coverage_group.isHidden())
        self.assertTrue(page.manual_extent_panel.isHidden())
        self.assertAlmostEqual(page.min_lon.value(), -42.1234)

    def test_number_format_keeps_precision_and_locale(self):
        box = CompactDoubleSpinBox()
        box.setDecimals(4)
        box.setRange(-180, 180)
        for locale, expected in (("en_US", "1.5"), ("pt_BR", "1,5")):
            box.setLocale(QLocale(locale))
            box.setValue(1.5)
            self.assertEqual(box.cleanText(), expected)
            box.setValue(0.0001)
            self.assertAlmostEqual(box.value(), 0.0001)
            self.assertTrue(box.cleanText().endswith("0001"))

    def test_completion_popup_is_opaque_and_selectable(self):
        window = self.window
        window.show_workbench()
        selector = window.identifier_column
        self.assertIsInstance(selector, SearchableColumnComboBox)
        selector.addItems(["individual_id", "latitude", "longitude"])
        selector.setEditText("vid")
        completer = selector.completer()
        completer.setCompletionPrefix("vid")
        completer.complete()
        self.app.processEvents()
        popup = completer.popup()
        self.assertTrue(popup.isVisible())
        self.assertIn("background: #ffffff", popup.styleSheet())
        background = popup.viewport().grab().toImage().pixelColor(popup.viewport().width() - 3, 3)
        self.assertEqual(background.alpha(), 255)
        self.assertGreater(background.lightness(), 180)
        index = completer.completionModel().index(0, 0)
        QTest.mouseClick(popup.viewport(), Qt.LeftButton, pos=popup.visualRect(index).center())
        self.assertEqual(selector.currentText(), "individual_id")

    def test_validation_feedback_tracks_state(self):
        page = self.window.review_run_page
        page.set_state(ReviewRunState.VALIDATING)
        page.show_validation_overlay()
        self.assertFalse(page.inline_validation.isHidden())
        self.assertEqual(page.inline_validation_progress.maximum(), 0)
        page.update_validation_progress(1, 1, 4)
        self.assertEqual(page.inline_validation_progress.maximum(), 100)
        self.assertIn("environmental", page.inline_validation_label.text().lower())
        for state in (ReviewRunState.BLOCKED, ReviewRunState.READY, ReviewRunState.FAILED, ReviewRunState.UNVALIDATED):
            page.set_state(state)
            self.assertFalse(page.inline_validation.isVisible())

    def test_timezone_and_forcing_fallback_controls_are_available(self):
        page = self.window.observation_page
        self.assertEqual(page.input_timezone.currentData(), "as_recorded")
        self.assertGreaterEqual(page.input_timezone.findData("America/Sao_Paulo"), 0)
        self.assertNotIn(page.input_timezone, page.mapping_indicators)
        self.assertEqual(page.mapping_progress.maximum(), 7)
        setup = self.window.simulation_setup_page
        self.assertFalse(setup.current_fallback_toggle.isChecked())
        self.assertFalse(setup.wind_fallback_toggle.isChecked())
        self.assertTrue(setup.fallback_group.title().startswith("Missing forcing"))
        self.assertEqual(setup.current_fallback_toggle.text(), "Fallback currents")
        self.assertGreaterEqual(setup.current_fallback_toggle.minimumWidth(), 170)

    def test_validation_progress_is_inline_with_primary_action(self):
        self.window.show_workbench()
        self.window.stage_navigation.setCurrentRow(3)
        page = self.window.review_run_page
        page.set_state(ReviewRunState.VALIDATING)
        self.app.processEvents()
        self.assertTrue(page.inline_validation.isVisible())
        self.assertLess(page.inline_validation.geometry().right(), page.validate_button.geometry().left())

    def test_real_preflight_keeps_inline_progress_visible_before_worker_starts(self):
        self.window.show_workbench()
        self.window.stage_navigation.setCurrentRow(3)
        with patch("marine_drift_desktop.ui.main_window.PreflightWorker.start"):
            self.window._start_preflight()
        page = self.window.review_run_page
        self.assertEqual(page.state, ReviewRunState.VALIDATING)
        self.assertTrue(page.inline_validation.isVisible())
        self.window._preflight_worker.deleteLater()
        self.window._preflight_worker = None

    def test_tour_visits_all_sections_and_restores_setup(self):
        window = self.window
        page = window.simulation_setup_page
        before = page.step_states.copy()
        window.start_tutorial()
        tour = window.guided_tour
        for index in range(len(tour.steps)):
            tour.show_step(index)
            self.app.processEvents()
            self.assertEqual(window.stage_navigation.currentRow(), tour.steps[index].stage)
            self.assertTrue(tour.target.isVisible())
        tour.advance()
        self.assertFalse(tour.isVisible())
        self.assertEqual(page.step_states, before)
        self.assertEqual(window.stage_navigation.currentRow(), 0)
        self.assertIsNone(window._preflight_worker)
        self.assertIsNone(window._simulation_process)

    def test_tutorial_registry_resolves_precise_visible_targets(self):
        window = self.window
        window.start_tutorial()
        tour = window.guided_tour
        expected_keys = (
            "observation-source", "observation-records", "observation-time",
            "observation-position", "forcing-catalog", "forcing-inspector",
            "forcing-readiness", "setup-area", "setup-selection", "setup-duration",
            "setup-windage", "setup-release", "setup-physics", "review-destination",
            "review-action", "results-export", "results-map",
        )
        self.assertEqual(tuple(step.key for step in tour.steps), expected_keys)
        for index, step in enumerate(tour.steps):
            tour.show_step(index)
            QTest.qWait(30)
            self.assertEqual(tour.progress.value(), index + 1)
            self.assertEqual(tour.progress.maximum(), len(tour.steps))
            self.assertEqual(window.stage_navigation.currentRow(), step.stage)
            self.assertIs(tour.target, tour.resolve_target(step.target_path))
            self.assertTrue(tour.target.isVisibleTo(window))
            self.assertFalse(tour.spotlight_rect().isEmpty())

    def test_tutorial_spotlight_uses_overlay_coordinates(self):
        self.window.start_tutorial()
        tour = self.window.guided_tour
        self.app.processEvents()
        expected = tour.mapFromGlobal(tour.target.mapToGlobal(QPoint(0, 0))) - QPoint(5, 5)
        actual = tour.spotlight_rect().toAlignedRect().topLeft()
        self.assertEqual(actual, expected)

    def test_tutorial_spotlight_is_clipped_to_scroll_viewport(self):
        from PySide6.QtCore import QRectF
        self.window.resize(1000, 650)
        self.window.start_tutorial()
        tour = self.window.guided_tour
        tour.show_step(9)
        QTest.qWait(50)
        page = self.window.simulation_setup_page
        viewport = page.viewport()
        clip = QRectF(viewport.rect())
        clip.moveTopLeft(tour.mapFromGlobal(viewport.mapToGlobal(QPoint(0, 0))))
        self.assertFalse(tour.spotlight_rect().isEmpty())
        self.assertTrue(clip.contains(tour.spotlight_rect()))

    def test_resume_dialog_sends_explicit_decision_to_worker(self):
        from unittest.mock import MagicMock
        self.window._simulation_process = MagicMock()
        try:
            for text, decision in (("Keep completed; run missing", "preserve"),
                                   ("Recalculate and overwrite", "overwrite")):
                with patch.object(QMessageBox, "exec", return_value=0), patch.object(
                    QMessageBox, "clickedButton",
                    new=lambda dialog: next(b for b in dialog.buttons() if b.text() == text)):
                    self.window._handle_simulation_event({
                        "event": "resume_review", "completed": 55000, "pending": 90000,
                        "invalid": 0, "conflicts": 0, "configuration_changed": True})
                self.assertIn(decision.encode(), self.window._simulation_process.write.call_args.args[0])
        finally:
            self.window._simulation_process = None

    def test_tutorial_navigation_is_read_only_and_card_avoids_spotlight(self):
        window = self.window
        page = window.simulation_setup_page
        page.step_states = {index: "not_started" for index in range(6)}
        window.start_tutorial()
        tour = window.guided_tour
        for index in range(len(tour.steps)):
            before = page.step_states.copy()
            tour.show_step(index)
            QTest.qWait(40)
            self.assertEqual(page.step_states, before)
            self.assertFalse(tour.card.geometry().intersects(tour.spotlight_rect().toRect()))

    def test_tutorial_missing_target_uses_fallback_without_invalid_spotlight(self):
        window = self.window
        window.start_tutorial()
        tour = window.guided_tour
        tour.steps[0] = tour.steps[0]._replace(target_path="observation_page.missing")
        tour.show_step(0)
        QTest.qWait(30)
        self.assertIsNone(tour.target)
        self.assertIn("unavailable", tour.description.text().lower())
        self.assertTrue(tour.spotlight_rect().isEmpty())

    def test_tutorial_exit_restores_previous_page_and_scroll_position(self):
        window = self.window
        window.resize(1024, 700)
        window.show_workbench()
        window.stage_navigation.setCurrentRow(0)
        self.app.processEvents()
        scroll = window.observation_page.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        previous = scroll.value()
        self.assertGreater(previous, 0)
        window.start_tutorial()
        window.guided_tour.show_step(0)
        QTest.qWait(40)
        window.guided_tour.finish()
        self.app.processEvents()
        self.assertEqual(window.stage_navigation.currentRow(), 0)
        self.assertEqual(scroll.value(), previous)


if __name__ == "__main__":
    unittest.main()
