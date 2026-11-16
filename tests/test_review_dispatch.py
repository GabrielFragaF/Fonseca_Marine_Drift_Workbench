import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from marine_drift_desktop.core.timestamps import source_time_to_utc
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from marine_drift_desktop.ui.pages.review_run_page import ReviewRunState


class DispatchTests(unittest.TestCase):
    def test_worker_uses_packaged_opendrift_version_without_git_subprocess(self):
        from marine_drift_desktop.core.batch_execution import _disable_opendrift_git_version_lookup
        import opendrift.version

        original = opendrift.version.version_or_git
        try:
            _disable_opendrift_git_version_lookup()
            self.assertEqual(opendrift.version.version_or_git(), opendrift.version.__version__)
        finally:
            opendrift.version.version_or_git = original

    def test_fallback_values_reach_model_without_running_simulation(self):
        from marine_drift_desktop.core.batch_execution import _execute_opendrift_job
        from marine_drift_desktop.domain.models import SimulationRequest
        request = SimulationRequest()
        values = request.settings.fallback_values
        values.currents_enabled = values.wind_enabled = True
        values.stokes_drift_enabled = values.seafloor_depth_enabled = True
        values.x_sea_water_velocity = -0.12
        values.y_sea_water_velocity = 0.23
        values.x_wind = 1.2
        values.y_wind = -2.3
        values.stokes_drift_x_velocity = 0.04
        values.stokes_drift_y_velocity = -0.05
        values.sea_floor_depth_below_sea_level = 42
        job = SimpleNamespace(observation=SimpleNamespace(wind_drift_factor=0.015, longitude=0, latitude=0), iteration=SimpleNamespace(start_time=datetime(2025, 1, 1)))
        for enabled in (True, False):
            values.currents_enabled = values.wind_enabled = enabled
            values.stokes_drift_enabled = values.seafloor_depth_enabled = enabled
            model = Mock()
            model.seed_elements.side_effect = RuntimeError("stop before simulation")
            with patch("opendrift.models.oceandrift.OceanDrift", return_value=model):
                with self.assertRaisesRegex(RuntimeError, "stop before simulation"):
                    _execute_opendrift_job(job, request, [SimpleNamespace(variables=["x_wind", "y_wind"])])
            config = {call.args[0]: call.args[1] for call in model.set_config.call_args_list}
            for name, value in {"x_sea_water_velocity": -0.12, "y_sea_water_velocity": 0.23, "x_wind": 1.2, "y_wind": -2.3, "sea_surface_wave_stokes_drift_x_velocity": 0.04, "sea_surface_wave_stokes_drift_y_velocity": -0.05, "sea_floor_depth_below_sea_level": 42}.items():
                self.assertEqual(config["environment:fallback:" + name], value if enabled else None)
            model.run.assert_not_called()

    def test_ready_footer_dispatches_without_navigation(self):
        window = SimpleNamespace(
            stage_navigation=Mock(),
            review_run_page=SimpleNamespace(state=ReviewRunState.READY_WITH_WARNINGS),
            _run_simulations=Mock(),
        )
        window.stage_navigation.currentRow.return_value = 3
        MarineDriftMainWindow._advance_workflow(window)
        window._run_simulations.assert_called_once_with()
        window.stage_navigation.setCurrentRow.assert_not_called()

    def test_unvalidated_footer_validates(self):
        window = SimpleNamespace(
            stage_navigation=Mock(),
            review_run_page=SimpleNamespace(state=ReviewRunState.UNVALIDATED),
            _preview_configuration=Mock(),
        )
        window.stage_navigation.currentRow.return_value = 3
        MarineDriftMainWindow._advance_workflow(window)
        window._preview_configuration.assert_called_once_with()

    def test_clock_time_is_only_converted_when_requested(self):
        value = datetime(2025, 1, 1, 9)
        self.assertEqual(source_time_to_utc(value, "as_recorded"), value)
        self.assertEqual(source_time_to_utc(value, "America/Sao_Paulo"), datetime(2025, 1, 1, 12))
        self.assertEqual(source_time_to_utc(value, "Asia/Tokyo"), datetime(2025, 1, 1, 0))

    def test_windows_source_worker_prefers_windowless_python(self):
        with patch("marine_drift_desktop.ui.main_window.sys.platform", "win32"), patch(
            "marine_drift_desktop.ui.main_window.sys.frozen", False, create=True
        ), patch(
            "marine_drift_desktop.ui.main_window.sys.executable", "/runtime/python.exe"
        ), patch(
            "marine_drift_desktop.ui.main_window.Path.is_file", return_value=True
        ):
            program = MarineDriftMainWindow._simulation_worker_program()
        self.assertEqual(program, str(Path("/runtime/pythonw.exe")))
