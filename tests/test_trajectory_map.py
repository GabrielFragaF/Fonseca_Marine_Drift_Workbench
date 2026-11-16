import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from netCDF4 import Dataset
from tests.results_test_support import make_trajectory_netcdf
from marine_drift_desktop.core.trajectory_map import prepare_trajectory_map


class TrajectoryMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def add(self, name, identifier, iteration=1, **kwargs):
        return make_trajectory_netcdf(self.root / name, identifier=identifier,
                                      iteration=iteration, **kwargs)

    def test_distinct_identifiers_one_run_each_reproducible(self):
        for identifier in ("A", "B", "C"):
            for run in range(1, 4):
                self.add(f"{identifier}-{run}.nc", identifier, run)
        result = prepare_trajectory_map(self.root, 2, 42)
        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(len({run["identifier"] for run in result["runs"]}), 2)
        self.assertEqual(result, prepare_trajectory_map(self.root, 2, 42))
        self.assertEqual(result["available_individuals"], 3)
        self.assertTrue(all(run["tracks"] for run in result["runs"]))
        json.dumps(result, allow_nan=False)

    def test_numeric_identifier_aliases_are_not_sampled_twice(self):
        self.add("a.nc", "42")
        self.add("b.nc", "42.0", 2)
        result = prepare_trajectory_map(self.root, 5, 42)
        self.assertEqual(len(result["runs"]), 1)
        self.assertEqual(result["available_individuals"], 1)
        self.assertTrue(result["warnings"])

    def test_invalid_coordinates_and_dateline_do_not_create_connecting_lines(self):
        path = self.add("a.nc", "A", trajectories=1)
        with Dataset(path, "a") as ds:
            ds.variables["lon"][0, :5] = [179, -179, -178, -177, -176]
            ds.variables["lat"][0, 3] = 999
        track = prepare_trajectory_map(self.root, 1, 42)["runs"][0]["tracks"][0]
        self.assertIn(None, track)
        for before, after in zip(track, track[1:]):
            if before is not None and after is not None:
                self.assertLessEqual(abs(before[0] - after[0]), 180)
        self.assertTrue(all(p is None or -90 <= p[1] <= 90 for p in track))

    def test_large_ensemble_is_bounded_and_disclosed(self):
        self.add("a.nc", "A", trajectories=35, duration_days=3)
        result = prepare_trajectory_map(self.root, 1, 7)
        self.assertLessEqual(len(result["runs"][0]["tracks"]), 12)
        self.assertTrue(result["warnings"])

    def test_all_invalid_positions_fail_instead_of_empty_success(self):
        path = self.add("a.nc", "A")
        with Dataset(path, "a") as ds:
            ds.variables["lat"][:] = 999
        with self.assertRaisesRegex(ValueError, "valid positions"):
            prepare_trajectory_map(self.root, 1, 42)

    def test_count_must_be_a_positive_bounded_integer(self):
        for count in (0, -1, 51, True, 1.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                prepare_trajectory_map(self.root, count, 42)

    def test_numeric_workbench_files_are_sampled_without_full_inspection(self):
        for identifier in ("101", "102", "103"):
            for run in (1, 2):
                self.add(f"{identifier}_Chelonia-mydas_DEC2_DUR3d_EV0123456789abcdef_{run:02}.nc", identifier, run)
        with patch("marine_drift_desktop.core.trajectory_map.inspect_results_directory", side_effect=AssertionError("full scan")):
            result = prepare_trajectory_map(self.root, 2, 42)
        self.assertEqual(len(result["runs"]), 2)
        self.assertEqual(len({r["identifier"] for r in result["runs"]}), 2)
        self.assertIn("candidate", " ".join(result["warnings"]).lower())

    def test_numeric_filename_cannot_misidentify_embedded_trajectory(self):
        self.add("101_Chelonia-mydas_DEC2_DUR3d_EV0123456789abcdef_01.nc", "999")
        with self.assertRaisesRegex(ValueError, "valid positions"):
            prepare_trajectory_map(self.root, 1, 42)

    def test_numeric_prefix_and_underscore_is_a_valid_identifier(self):
        self.add("101_alpha_Chelonia-mydas_DEC2_DUR3d_EV0123456789abcdef_01.nc", "101_alpha")
        result = prepare_trajectory_map(self.root, 1, 42)
        self.assertEqual(result["runs"][0]["identifier"], "101_alpha")

    def test_fast_map_rejects_mixed_source_datasets(self):
        for identifier in ("101", "102"):
            make_trajectory_netcdf(self.root / f"{identifier}_Chelonia-mydas_DEC2_DUR3d_EV0123456789abcdef_01.nc",
                                   identifier=identifier, observation_dataset=self.root / f"{identifier}.csv")
        with self.assertRaisesRegex(ValueError, "observation dataset"):
            prepare_trajectory_map(self.root, 2, 42)
