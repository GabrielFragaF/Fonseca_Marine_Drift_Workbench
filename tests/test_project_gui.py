import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from marine_drift_desktop.core.project_files import ProjectDocument, read_project, write_project
from marine_drift_desktop.domain.models import (
    EnvironmentalReaderConfig,
    FilterCondition,
    SimulationRequest,
)
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow


class ProjectGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MarineDriftMainWindow()

    def tearDown(self):
        self.window.project_dirty = False
        self.window.close()

    def test_apply_project_restores_configuration_and_requires_validation(self):
        request = SimulationRequest()
        request.data_sources.observation_dataset = Path("C:/survey/records.csv")
        request.data_sources.output_directory = Path("C:/survey/results")
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(
                Path("C:/survey/currents.nc"),
                roles=["Ocean circulation"],
                recognized_variables=["x_sea_water_velocity"],
            )
        ]
        request.column_mapping.stranding_identifier = "record_id"
        request.column_mapping.longitude = "longitude"
        request.settings.model_time_step_hours = 0.5
        request.settings.coverage.mode = "environment_intersection"
        request.settings.coverage.buffer_degrees = 0.25
        request.settings.observation_selection.mode = "filter"
        request.settings.observation_selection.conditions = [
            FilterCondition(column="species", operator="equals", value="Kogia")
        ]

        self.window.apply_project(ProjectDocument("Kogia survey", request))

        self.assertEqual(self.window.project_name.text(), "Kogia survey")
        self.assertEqual(self.window.dataset_path.text(), str(Path("C:/survey/records.csv")))
        self.assertEqual(self.window.output_directory.text(), str(Path("C:/survey/results")))
        self.assertEqual(self.window.identifier_column.currentText(), "record_id")
        self.assertEqual(self.window.model_time_step.value(), 0.5)
        self.assertTrue(self.window.coverage_toggle.isChecked())
        self.assertEqual(self.window.coverage_buffer.value(), 0.25)
        self.assertEqual(self.window.selection_mode.currentData(), "filter")
        self.assertEqual(len(self.window.filter_condition_rows), 1)
        self.assertEqual(self.window.environment_catalog_model.rowCount(), 1)
        self.window.active_project_path = Path(tempfile.gettempdir()) / "reader-roundtrip.mdwproj"
        self.assertTrue(self.window.save_project())
        restored = read_project(self.window.active_project_path)
        self.assertEqual(
            restored.request.data_sources.environment_readers[0].recognized_variables,
            ["x_sea_water_velocity"],
        )
        self.window.active_project_path.unlink(missing_ok=True)
        self.assertFalse(self.window._is_validated)

    def test_apply_project_preserves_every_duration_boundary(self):
        request = SimulationRequest()
        duration = request.settings.duration
        duration.temperature_boundaries_celsius = [18.0, 24.0]
        duration.scenario_days = {1: [5, 3, 1]}
        duration.decomposition_value_map = {"fresh": 1}

        self.window.apply_project(ProjectDocument("Thermal profile", request))

        fields = self.window.simulation_setup_page.temperature_boundary_fields
        self.assertEqual([field.value() for field in fields], [18.0, 24.0])

    def test_reset_project_clears_loaded_values(self):
        request = SimulationRequest()
        request.data_sources.observation_dataset = Path("C:/survey/records.csv")
        self.window.apply_project(ProjectDocument("Survey", request))

        self.window.reset_project()

        self.assertEqual(self.window.project_name.text(), "New reverse-drift project")
        self.assertEqual(self.window.dataset_path.text(), "")
        self.assertIsNone(self.window.active_project_path)
        self.assertFalse(self.window.project_dirty)

    def test_restores_release_and_inactive_filter_without_signal_mutation(self):
        request = SimulationRequest()
        request.settings.iteration_count = 8
        request.settings.start_time_mode = "fixed_hour"
        request.settings.fixed_start_hour = 9
        request.settings.job_error_policy = "stop"
        request.settings.position_search.mode = "skip_if_invalid"
        request.settings.observation_selection.mode = "all"
        request.settings.observation_selection.conditions = [
            FilterCondition(column="code", operator="equals", value=0)
        ]
        self.window.apply_project(ProjectDocument("Saved", request))
        self.assertEqual(self.window.release_strategy.currentData(), "multiple_fixed")
        self.assertEqual(self.window.filter_condition_rows[0].value.text(), "0")
        self.assertTrue(self.window._collect_request_from_ui())
        self.assertEqual(self.window.request.settings.iteration_count, 8)
        self.assertEqual(self.window.request.settings.start_time_mode, "fixed_hour")
        self.assertEqual(self.window.request.settings.job_error_policy, "stop")
        self.assertEqual(self.window.request.settings.position_search.mode, "skip_if_invalid")
        self.assertEqual(len(self.window.request.settings.observation_selection.conditions), 1)

    def test_unsaved_new_project_can_cancel_close(self):
        from PySide6.QtGui import QCloseEvent
        from PySide6.QtWidgets import QMessageBox
        self.window.project_dirty = True
        event = QCloseEvent()
        with patch("marine_drift_desktop.ui.main_window.QMessageBox.question",
                   return_value=QMessageBox.Cancel):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())

    def test_save_project_collects_current_controls_without_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "field-study.mdwproj"
            self.window.project_name.setText("Field study")
            self.window.dataset_path.setText("C:/survey/observations.csv")
            self.window.model_time_step.setValue(0.25)
            self.window.active_project_path = path

            self.assertTrue(self.window.save_project())

            restored = read_project(path)
            self.assertEqual(restored.name, "Field study")
            self.assertEqual(
                restored.request.data_sources.observation_dataset,
                Path("C:/survey/observations.csv"),
            )
            self.assertEqual(restored.request.settings.model_time_step_hours, 0.25)
            self.assertFalse(self.window._is_validated)
            self.assertFalse(self.window.project_dirty)

    def test_open_project_loads_configuration_selected_from_welcome(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.mdwproj"
            request = SimulationRequest()
            request.settings.particle_count = 42
            write_project(ProjectDocument("Saved survey", request), path)
            with patch(
                "marine_drift_desktop.ui.main_window.QFileDialog.getOpenFileName",
                return_value=(str(path), "Marine Drift projects (*.mdwproj)"),
            ):
                self.window.welcome_page.open_project_button.click()

            self.assertEqual(self.window.project_name.text(), "Saved survey")
            self.assertEqual(self.window.particle_count.value(), 42)
            self.assertEqual(self.window.active_project_path, path)
            self.assertIs(
                self.window.workspace_stack.currentWidget(),
                self.window.workspace_stack.widget(1),
            )


if __name__ == "__main__":
    unittest.main()
