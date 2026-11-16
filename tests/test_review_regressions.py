import unittest
from unittest.mock import patch

from marine_drift_desktop.core.batch_execution import (
    ObservationPreparationResult, run_simulation_batches,
)
from marine_drift_desktop.core.windage import wind_drift_factor_for_record
from marine_drift_desktop.domain.models import SimulationRequest, WindDriftSettings
from pathlib import Path


class ReviewRegressions(unittest.TestCase):
    def test_nan_measurement_cannot_be_clamped_into_valid_windage(self):
        settings = WindDriftSettings(mode="measurement", measurement_column="size")
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                wind_drift_factor_for_record({"size": value}, "", settings)

    def test_no_observations_cannot_report_completed_run(self):
        request = SimulationRequest()
        request.data_sources.output_directory = Path("unused-review-output")
        empty = ObservationPreparationResult([], 2, 2, 2, {"Invalid date": 2}, 0, 0)
        with patch("marine_drift_desktop.core.batch_execution.prepare_observations", return_value=empty):
            with self.assertRaisesRegex(ValueError, "No runnable observations"):
                run_simulation_batches(request, execute_job=lambda *args: None)
