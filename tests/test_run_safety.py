import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from netCDF4 import Dataset
from tests.results_test_support import write_synthetic_trajectory
from marine_drift_desktop.core.resume import inspect_existing_outputs

from marine_drift_desktop.core.batch_execution import _request_fingerprint
from marine_drift_desktop.core.environment import EnvironmentalReaderInspection
from marine_drift_desktop.core.forcing_validation import evaluate_forcing_readiness
from marine_drift_desktop.core.planning import plan_simulation_runs
from marine_drift_desktop.core.records import _parse_combined_datetime, _combine_date_and_time
from marine_drift_desktop.core.results_source import _observation_time_match_score
from marine_drift_desktop.domain.models import (
    CanonicalObservation, EnvironmentalReaderConfig, SimulationRequest, SpatialExtent,
)


class RunSafetyTests(unittest.TestCase):
    def test_resume_does_not_reuse_different_stranding_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, iteration, request = write_synthetic_trajectory(root / "old.nc")
            changed = replace(old, longitude=old.longitude + 1)
            plan = plan_simulation_runs(changed, request.settings, root)[0]
            plan.iteration_index = iteration.iteration_index
            done, review = inspect_existing_outputs([SimpleNamespace(observation=changed, iteration=plan)], root, "x", lambda _: None)
            self.assertNotIn(plan.output_path, done)
            self.assertEqual(review["conflicts"], 1)
            self.assertEqual(review["superseded_files"], [str(root / "old.nc")])

    def test_resume_unverifiable_legacy_renamed_file_is_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, iteration, request = write_synthetic_trajectory(root / "old.nc")
            with Dataset(root / "old.nc", "a") as dataset:
                if "marine_drift_event_token" in dataset.ncattrs():
                    dataset.delncattr("marine_drift_event_token")
            plan = plan_simulation_runs(old, request.settings, root)[0]
            plan.iteration_index = iteration.iteration_index
            done, review = inspect_existing_outputs([SimpleNamespace(observation=old, iteration=plan)], root, "x", lambda _: None)
            self.assertNotIn(plan.output_path, done)
            self.assertEqual(review["conflicts"], 1)

    def test_resume_accepts_legacy_filename_with_matching_event_token(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, iteration, request = write_synthetic_trajectory(root / "old.nc")
            plan = plan_simulation_runs(old, request.settings, root)[0]
            plan.iteration_index = iteration.iteration_index
            with Dataset(root / "old.nc", "a") as dataset:
                dataset.delncattr("marine_drift_event_token")
            (root / "old.nc").rename(plan.output_path)
            done, review = inspect_existing_outputs([SimpleNamespace(observation=old, iteration=plan)], root, "x", lambda _: None)
            self.assertIn(plan.output_path, done)
            self.assertEqual(review["conflicts"], 0)
    def test_offsets_are_converted_not_discarded(self):
        expected = datetime(2026, 1, 2, 2, 15)
        self.assertEqual(_parse_combined_datetime("2026-01-01T23:15:00-03:00"), expected)
        self.assertEqual(_combine_date_and_time("2026-01-01", "23:15-03:00"), expected)
        self.assertEqual(_parse_combined_datetime(datetime(2026, 1, 1, 23, 15,
                         tzinfo=timezone(timedelta(hours=-3)))), expected)
        self.assertEqual(_observation_time_match_score(
            {"date": "2026-01-01", "time": "23:15-03:00"}, expected), 2)

    def test_resume_signature_tracks_referenced_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.csv"
            path.write_text("id\n1\n")
            request = SimulationRequest()
            request.data_sources.observation_dataset = path
            original = _request_fingerprint(request)
            self.assertEqual(original, _request_fingerprint(request))
            path.write_text("id\n1\n2\n")
            self.assertNotEqual(original, _request_fingerprint(request))
            forcing = Path(directory) / "forcing.nc"
            forcing.write_bytes(b"test")
            request.data_sources.environment_readers = [EnvironmentalReaderConfig(forcing)]
            original = _request_fingerprint(request)
            forcing.write_bytes(b"changed")
            self.assertNotEqual(original, _request_fingerprint(request))

    def test_repeated_ids_distinguish_events_but_not_duplicate_rows(self):
        observation = CanonicalObservation("same-id", "Marine fauna", 3, 22, 0,
                                           -40, -20, datetime(2026, 1, 2), 7)
        settings = SimulationRequest().settings
        def output(item):
            return plan_simulation_runs(item, settings, Path("output"))[0].output_path
        self.assertEqual(output(observation), output(replace(observation)))
        self.assertNotEqual(output(observation), output(replace(observation, latitude=-21)))
        self.assertNotEqual(output(observation), output(replace(observation, observed_at=datetime(2026, 1, 3))))

    def test_active_windage_requires_covered_wind_components(self):
        extent = SpatialExtent(-45, -35, -25, -15)
        reader = EnvironmentalReaderConfig(Path("merged.nc"), ["Ocean circulation"])
        inspection = EnvironmentalReaderInspection(
            path=reader.path, extent=extent,
            time_start="2026-01-01T00:00:00Z", time_end="2026-01-03T00:00:00Z",
            recognized_opendrift_variables=["x_sea_water_velocity", "y_sea_water_velocity"],
            compatibility_message="OpenDrift reader initialized successfully.",
        )
        def check(required):
            return evaluate_forcing_readiness([reader], [inspection], study_extent=extent,
                required_start=datetime(2026, 1, 1), required_end=datetime(2026, 1, 2),
                require_wind=required)
        self.assertTrue(check(False).is_ready)
        self.assertFalse(check(True).is_ready)
        inspection.recognized_opendrift_variables.extend(["x_wind", "y_wind"])
        self.assertTrue(check(True).is_ready)
        inspection.time_end = "2026-01-01T01:00:00Z"
        readiness = check(True)
        self.assertTrue(readiness.is_ready)
        self.assertEqual(readiness.check("wind_temporal_coverage").level, "warning")
