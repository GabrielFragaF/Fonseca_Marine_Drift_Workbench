from __future__ import annotations

import importlib
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from netCDF4 import Dataset

from marine_drift_desktop.core.results_inspection import inspect_results_directory
from tests import results_test_support


class TrajectorySamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[1]
            / ".tmp_tests"
            / "trajectory_sampling"
        )
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def test_five_positions_per_day_are_unique_exclude_zero_and_include_endpoint(self) -> None:
        sampling = self._sampling_module()
        times = np.arange(
            np.datetime64("2026-01-02T00:00"),
            np.datetime64("2025-12-31T23:00"),
            np.timedelta64(-1, "h"),
        )

        targets = sampling.select_sample_targets(
            times, duration_days=1, positions_per_day=5
        )

        self.assertEqual(
            [target.hours_before_stranding for target in targets],
            [5.0, 10.0, 14.0, 19.0, 24.0],
        )
        self.assertEqual(len({target.time_index for target in targets}), 5)
        self.assertNotIn(0, [target.time_index for target in targets])
        self.assertEqual(targets[-1].hours_before_stranding, 24.0)

    def test_hours_before_stranding_is_relative_to_observation_not_model_start(self) -> None:
        sampling = self._sampling_module()
        observed_at = datetime(2026, 1, 2, 10, 37)

        self.assertEqual(
            sampling.hours_before_observation(
                observed_at - timedelta(hours=7.5), observed_at
            ),
            7.5,
        )

    def test_multi_day_targets_are_evenly_spaced_in_each_complete_day(self) -> None:
        sampling = self._sampling_module()
        times = np.arange(
            np.datetime64("2026-01-03T00:00"),
            np.datetime64("2025-12-31T23:00"),
            np.timedelta64(-1, "h"),
        )

        targets = sampling.select_sample_targets(
            times, duration_days=2, positions_per_day=2
        )

        self.assertEqual(
            [target.hours_before_stranding for target in targets],
            [12.0, 24.0, 36.0, 48.0],
        )
        self.assertEqual([target.drift_day for target in targets], [1, 1, 2, 2])

    def test_multi_hour_outputs_reject_density_without_unique_matches(self) -> None:
        sampling = self._sampling_module()
        times = np.arange(
            np.datetime64("2026-01-02T00:00"),
            np.datetime64("2025-12-31T18:00"),
            np.timedelta64(-6, "h"),
        )

        targets = sampling.select_sample_targets(
            times, duration_days=1, positions_per_day=4
        )

        self.assertEqual([target.hours_before_stranding for target in targets], [6, 12, 18, 24])
        with self.assertRaisesRegex(ValueError, "unique"):
            sampling.select_sample_targets(times, duration_days=1, positions_per_day=5)

    def test_forward_time_coordinates_are_rejected(self) -> None:
        sampling = self._sampling_module()
        times = np.arange(
            np.datetime64("2026-01-01T00:00"),
            np.datetime64("2026-01-02T01:00"),
            np.timedelta64(1, "h"),
        )

        with self.assertRaisesRegex(ValueError, "reverse-drift|before stranding"):
            sampling.select_sample_targets(
                times, duration_days=1, positions_per_day=4
            )

    def test_every_particle_uses_the_same_target_indices(self) -> None:
        sampling = self._sampling_module()
        path = results_test_support.make_trajectory_netcdf(
            self.root / "multi.nc", trajectories=3, duration_days=1
        )
        metadata = inspect_results_directory(self.root).files[0]

        rows = list(sampling.iter_sampled_positions(metadata, positions_per_day=4))

        self.assertEqual(len(rows), 12)
        self.assertEqual({row["particle_index"] for row in rows}, {0, 1, 2})
        sample_hours = {
            particle: [row["hours_before_stranding"] for row in rows if row["particle_index"] == particle]
            for particle in range(3)
        }
        self.assertEqual(sample_hours[0], sample_hours[1])
        self.assertEqual(sample_hours[1], sample_hours[2])
        self.assertEqual(sample_hours[0], [4.0, 10.0, 16.0, 22.0])
        self.assertEqual({row["source_file"] for row in rows}, {str(path)})

    def test_rows_propagate_status_and_omit_invalid_coordinates_with_a_count(self) -> None:
        sampling = self._sampling_module()
        path = results_test_support.make_trajectory_netcdf(
            self.root / "invalid.nc", trajectories=2, duration_days=1
        )
        with Dataset(path, "a") as dataset:
            dataset.variables["status"][0, 6] = 7
            dataset.variables["lon"][1, 12] = np.nan
        metadata = inspect_results_directory(self.root).files[0]
        omitted: list[int] = []

        rows = list(
            sampling.iter_sampled_positions(
                metadata,
                positions_per_day=4,
                omitted_position_counter=lambda: omitted.append(1),
            )
        )

        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(omitted), 1)
        self.assertEqual(
            next(
                row["status"]
                for row in rows
                if row["particle_index"] == 0
                and row["hours_before_stranding"] == 4.0
            ),
            7,
        )
        self.assertTrue(all(np.isfinite(row["mortality_longitude"]) for row in rows))
        self.assertTrue(all(np.isfinite(row["mortality_latitude"]) for row in rows))

    def test_source_join_preserves_complete_rows_and_generated_fields_win_conflicts(self) -> None:
        sampling = self._sampling_module()
        source = self._source_module()
        results_test_support.make_trajectory_netcdf(self.root / "joined.nc")
        metadata = inspect_results_directory(self.root).files[0]
        source_path = self.root / "source.csv"
        pd.DataFrame(
            [
                {
                    "id": "observation-1",
                    "observer": "A. Researcher",
                    "taxon_label": "incorrect source taxon",
                    "source_taxon_label": "existing source column",
                    "particle_index": 99,
                    "source_file": "source workbook",
                    "weight": 0.25,
                }
            ]
        ).to_csv(source_path, index=False)

        lookup = source.load_source_observation_lookup(source_path, "id")
        row = next(
            sampling.iter_sampled_positions(
                metadata, positions_per_day=1, source_lookup=lookup
            )
        )

        self.assertEqual(row["observer"], "A. Researcher")
        self.assertEqual(row["taxon_label"], "Marine fauna")
        self.assertEqual(row["source_taxon_label"], "incorrect source taxon")
        self.assertEqual(
            row["source_source_taxon_label"], "existing source column"
        )
        self.assertEqual(row["particle_index"], 0)
        self.assertEqual(row["source_particle_index"], 99)
        self.assertEqual(row["source_file"], str(metadata.path))
        self.assertEqual(row["source_source_file"], "source workbook")
        self.assertNotIn("weight", row)
        self.assertEqual(row["source_weight"], 0.25)

    def test_missing_source_match_retains_row_with_blank_source_attributes(self) -> None:
        sampling = self._sampling_module()
        source = self._source_module()
        results_test_support.make_trajectory_netcdf(self.root / "missing-source.nc")
        metadata = inspect_results_directory(self.root).files[0]
        source_path = self.root / "source.csv"
        pd.DataFrame([{"id": "other", "observer": "A. Researcher"}]).to_csv(
            source_path, index=False
        )

        lookup = source.load_source_observation_lookup(source_path, "id")
        missing: list[str] = []
        row = next(
            sampling.iter_sampled_positions(
                metadata,
                positions_per_day=1,
                source_lookup=lookup,
                missing_source_callback=missing.append,
            )
        )

        self.assertEqual(row["id"], "")
        self.assertEqual(row["observer"], "")
        self.assertEqual(missing, ["observation-1"])

    def test_selected_environmental_values_use_exact_particle_and_time_index(self) -> None:
        sampling = self._sampling_module()
        values = np.arange(2 * 25, dtype=float).reshape(2, 25)
        values[1, 24] = np.nan
        results_test_support.make_trajectory_netcdf(
            self.root / "environment.nc",
            trajectories=2,
            environmental_variables={
                "sea_water_temperature": (
                    values,
                    {"units": "K", "standard_name": "sea_water_temperature"},
                )
            },
        )
        metadata = inspect_results_directory(self.root).files[0]

        rows = list(sampling.iter_sampled_positions(
            metadata,
            positions_per_day=1,
            environmental_variables=("sea_water_temperature",),
        ))

        self.assertEqual(rows[0]["sea_water_temperature"], values[0, 24])
        self.assertIsNone(rows[1]["sea_water_temperature"])

    def _sampling_module(self):
        return self._load_module("marine_drift_desktop.core.trajectory_sampling")

    def _source_module(self):
        return self._load_module("marine_drift_desktop.core.results_source")

    def _load_module(self, name: str):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            self.fail(f"Task 4 module is required: {exc}")


class ResultsSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[1]
            / ".tmp_tests"
            / "results_source"
        )
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def test_normalize_identifiers_trims_text_and_spreadsheet_integral_numbers(self) -> None:
        source = self._source_module()

        self.assertEqual(source.normalize_stranding_identifier("  alpha  "), "alpha")
        self.assertEqual(source.normalize_stranding_identifier(121666), "121666")
        self.assertEqual(source.normalize_stranding_identifier(121666.0), "121666")
        self.assertEqual(source.normalize_stranding_identifier("121666.0"), "121666")

    def test_blank_identifiers_are_rejected(self) -> None:
        source = self._source_module()

        for value in (None, "", "   ", np.nan, pd.NA, pd.NaT):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "blank"):
                    source.normalize_stranding_identifier(value)

    def test_identical_duplicate_normalized_source_identifiers_are_safe(self) -> None:
        source = self._source_module()
        path = self.root / "duplicates.csv"
        pd.DataFrame([{"id": 121666}, {"id": 121666.0}]).to_csv(path, index=False)

        lookup = source.load_source_observation_lookup(path, "id")
        selected = source.select_source_observation_row(lookup, "121666", datetime(2020, 1, 1))
        self.assertEqual(selected["id"], 121666.0)

    def test_duplicate_identifier_is_resolved_by_embedded_observation_time(self) -> None:
        source = self._source_module()
        path = self.root / "reused_identifier.csv"
        pd.DataFrame(
            [
                {"id": "121666", "recorded_at": "2019-11-24 09:50", "site": "first"},
                {"id": "121666", "recorded_at": "2020-06-06 11:52", "site": "second"},
            ]
        ).to_csv(path, index=False)

        lookup = source.load_source_observation_lookup(path, "id")
        selected = source.select_source_observation_row(
            lookup, "121666", datetime(2020, 6, 6, 11, 52)
        )

        self.assertEqual(selected["site"], "second")

    def test_lookup_preserves_the_complete_source_row(self) -> None:
        source = self._source_module()
        path = self.root / "observations.csv"
        pd.DataFrame(
            [
                {
                    "id": "  alpha  ",
                    "integer": 3,
                    "note": "preserve me",
                    "flag": True,
                }
            ]
        ).to_csv(path, index=False)

        lookup = source.load_source_observation_lookup(path, "id")

        self.assertEqual(lookup["alpha"], {
            "id": "  alpha  ",
            "integer": 3,
            "note": "preserve me",
            "flag": True,
        })

    def _source_module(self):
        try:
            return importlib.import_module("marine_drift_desktop.core.results_source")
        except ModuleNotFoundError as exc:
            self.fail(f"Task 4 module is required: {exc}")


if __name__ == "__main__":
    unittest.main()
