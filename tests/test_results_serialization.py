from __future__ import annotations

import json
import shutil
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from marine_drift_desktop.core.results_serialization import (
    read_results_export_request,
    results_export_request_to_dict,
    write_results_export_request,
)
from marine_drift_desktop.domain.results import (
    ResultsExportPaths,
    ResultsExportRequest,
)


class ResultsSerializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = (
            Path(__file__).resolve().parents[1]
            / ".tmp_tests"
            / "results_serialization"
        )
        shutil.rmtree(self.root, ignore_errors=True)
        self.results_directory = self.root / "results"
        self.results_directory.mkdir(parents=True)

    def test_request_round_trips_paths_and_format_flags_exactly(self) -> None:
        request = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=self.root / "exports",
            positions_per_drift_day=4,
            write_csv=True,
            write_xlsx=True,
            output_basename="seasonal_mortality",
            observation_dataset_override=self.root / "observations.csv",
            environmental_variables=["sea_water_temperature", "x_wind"],
        )

        payload = results_export_request_to_dict(request)
        path = write_results_export_request(request, self.root / "request.json")

        self.assertEqual(
            payload,
            {
                "results_directory": str(self.results_directory),
                "output_directory": str(self.root / "exports"),
                "positions_per_drift_day": 4,
                "write_csv": True,
                "write_xlsx": True,
                "output_basename": "seasonal_mortality",
                "observation_dataset_override": str(self.root / "observations.csv"),
                "environmental_variables": ["sea_water_temperature", "x_wind"],
            },
        )
        self.assertEqual(read_results_export_request(path), request)

    def test_old_request_defaults_to_no_environmental_variables(self) -> None:
        path = self.root / "legacy.json"
        path.write_text(json.dumps({
            "results_directory": str(self.results_directory),
            "output_directory": str(self.root / "exports"),
        }), encoding="utf-8")

        request = read_results_export_request(path)

        self.assertEqual(request.environmental_variables, [])

    def test_request_round_trip_preserves_missing_optional_override(self) -> None:
        request = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=self.root / "exports",
        )

        path = write_results_export_request(request, self.root / "request.json")

        self.assertIsNone(read_results_export_request(path).observation_dataset_override)

    def test_validation_rejects_zero_sampling_density_and_blank_basename(self) -> None:
        request = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=self.root / "exports",
            positions_per_drift_day=0,
        )
        with self.assertRaisesRegex(ValueError, "positions_per_drift_day"):
            request.validate()

        request.positions_per_drift_day = 1
        request.output_basename = "  "
        with self.assertRaisesRegex(ValueError, "output_basename"):
            request.validate()

    def test_validation_rejects_invalid_results_and_file_output_paths(self) -> None:
        missing_results = ResultsExportRequest(
            results_directory=self.root / "missing",
            output_directory=self.root / "exports",
        )
        with self.assertRaisesRegex(ValueError, "results_directory"):
            missing_results.validate()

        output_file = self.root / "output-file"
        output_file.write_text("not a directory", encoding="utf-8")
        file_output = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=output_file,
        )
        with self.assertRaisesRegex(ValueError, "output_directory"):
            file_output.validate()

    def test_validation_accepts_not_yet_created_output_directory(self) -> None:
        output_directory = self.root / "existing-parent" / "future-output"
        output_directory.parent.mkdir()
        request = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=output_directory,
        )

        request.validate()

        self.assertFalse(output_directory.exists())

    def test_malformed_and_missing_key_json_raise_value_error(self) -> None:
        cases = {
            "root-list": ([], "JSON object"),
            "missing-results": (
                {"output_directory": str(self.root / "exports")},
                "missing required key.*results_directory",
            ),
            "numeric-results": (
                {
                    "results_directory": 42,
                    "output_directory": str(self.root / "exports"),
                },
                "results_directory.*string",
            ),
            "string-csv-flag": (
                {
                    "results_directory": str(self.results_directory),
                    "output_directory": str(self.root / "exports"),
                    "write_csv": "yes",
                },
                "write_csv.*boolean",
            ),
        }
        for name, (payload, message) in cases.items():
            with self.subTest(name=name):
                path = self.root / f"{name}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    read_results_export_request(path)

    def test_atomic_write_leaves_no_sibling_tmp_file_after_success(self) -> None:
        request = ResultsExportRequest(
            results_directory=self.results_directory,
            output_directory=self.root / "exports",
        )
        path = self.root / "nested" / "request.json"
        temporary_path = path.with_name(f"{path.name}.tmp")

        written_path = write_results_export_request(request, path)

        self.assertEqual(written_path, path)
        self.assertTrue(path.is_file())
        self.assertFalse(temporary_path.exists())

    def test_export_paths_are_frozen_and_optional_paths_default_to_none(self) -> None:
        paths = ResultsExportPaths(parquet=self.root / "results.parquet")

        self.assertIsNone(paths.csv)
        self.assertIsNone(paths.xlsx)
        self.assertIsNone(paths.failures)
        self.assertIsNone(paths.manifest)
        with self.assertRaises(FrozenInstanceError):
            paths.parquet = self.root / "other.parquet"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
