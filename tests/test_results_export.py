from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from marine_drift_desktop.core import results_export as results_export_module
from marine_drift_desktop.core.results_export import (
    ResultsExportCancelled,
    convert_parquet_to_csv,
    generate_mortality_positions,
)
from tests.results_test_support import make_results_fixture, make_trajectory_netcdf


class ResultsExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "results_export"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def test_export_joins_source_and_weights_sum_to_one_per_stranding(self) -> None:
        result = generate_mortality_positions(make_results_fixture(self.root))
        table = pd.read_parquet(result.paths.parquet)

        self.assertEqual(len(table), 2 * 4)
        self.assertEqual(set(table["observer"]), {"Researcher A"})
        self.assertTrue(np.allclose(
            table.groupby("stranding_identifier")["weight"].sum().to_numpy(),
            1.0,
        ))
        self.assertEqual(result.row_count, len(table))

    def test_source_decomposition_state_is_renamed_without_schema_collision(self) -> None:
        request = make_results_fixture(self.root)
        source = self.root / "observations.csv"
        table = pd.read_csv(source)
        table["decomposition_state"] = "Fresh"
        table.to_csv(source, index=False)

        result = generate_mortality_positions(request)
        exported = pd.read_parquet(result.paths.parquet)

        self.assertIn("decomposition_state", exported.columns)
        self.assertIn("source_decomposition_state", exported.columns)

    def test_exact_duplicate_source_rows_do_not_make_export_ambiguous(self) -> None:
        request = make_results_fixture(self.root)
        source = self.root / "observations.csv"
        records = pd.read_csv(source)
        pd.concat([records, records], ignore_index=True).to_csv(source, index=False)

        result = generate_mortality_positions(request)

        self.assertTrue(result.paths.parquet.is_file())

    def test_weights_span_every_file_and_iteration_for_identifier(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=2)
        source = self.root / "observations.csv"
        make_trajectory_netcdf(
            request.results_directory / "second.nc",
            identifier="observation-1",
            trajectories=3,
            iteration=2,
            observation_dataset=source,
        )

        table = pd.read_parquet(generate_mortality_positions(request).paths.parquet)

        self.assertEqual(len(table), (2 + 3) * 2)
        self.assertTrue(np.isclose(table["weight"].sum(), 1.0))

    def test_reused_identifier_with_different_observed_times_has_separate_weights(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        source = self.root / "observations.csv"
        pd.DataFrame([
            {"id": "observation-1", "recorded_at": "2024-04-13 07:50", "site": "first"},
            {"id": "observation-1", "recorded_at": "2024-04-14 08:00", "site": "second"},
        ]).to_csv(source, index=False)
        make_trajectory_netcdf(
            request.results_directory / "second_event.nc",
            identifier="observation-1",
            trajectories=2,
            iteration=1,
            observation_dataset=source,
            observed_at=datetime(2024, 4, 14, 8, 0),
        )

        table = pd.read_parquet(generate_mortality_positions(request).paths.parquet)

        self.assertEqual(set(table["site"]), {"first", "second"})
        self.assertTrue(np.allclose(
            table.groupby("observed_at")["weight"].sum().to_numpy(), 1.0
        ))

    def test_equivalent_numeric_identifiers_share_one_normalized_weight_pool(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        source = self.root / "observations.csv"
        pd.DataFrame([{"id": 121666, "observer": "A"}]).to_csv(source, index=False)
        for path in request.results_directory.glob("*.nc"):
            path.unlink()
        make_trajectory_netcdf(
            request.results_directory / "a.nc",
            identifier="121666.0",
            observation_dataset=source,
        )
        make_trajectory_netcdf(
            request.results_directory / "b.nc",
            identifier="121666",
            iteration=2,
            observation_dataset=source,
        )

        table = pd.read_parquet(generate_mortality_positions(request).paths.parquet)

        self.assertEqual(set(table["stranding_identifier"]), {"121666"})
        self.assertTrue(np.isclose(table["weight"].sum(), 1.0))

    def test_mixed_source_column_is_normalized_to_stable_arrow_text(self) -> None:
        results = self.root / "run"
        results.mkdir()
        source = self.root / "observations.xlsx"
        pd.DataFrame([
            {"id": "observation-1", "mixed": 4},
            {"id": "observation-2", "mixed": "unknown"},
        ]).to_excel(source, index=False)
        make_trajectory_netcdf(
            results / "first.nc",
            identifier="observation-1",
            observation_dataset=source,
        )
        make_trajectory_netcdf(
            results / "second.nc",
            identifier="observation-2",
            observation_dataset=source,
        )
        request = make_results_fixture(self.root / "request", positions_per_day=1)
        request.results_directory = results
        request.output_directory = self.root / "exports"

        table = pd.read_parquet(generate_mortality_positions(request).paths.parquet)

        self.assertEqual(set(table["mixed"]), {"4", "unknown"})

    def test_csv_and_xlsx_are_converted_from_completed_parquet(self) -> None:
        request = make_results_fixture(self.root, write_csv=True, write_xlsx=True)
        result = generate_mortality_positions(request)
        parquet = pd.read_parquet(result.paths.parquet)

        self.assertEqual(len(pd.read_csv(result.paths.csv)), len(parquet))
        self.assertEqual(len(pd.read_excel(result.paths.xlsx)), len(parquet))
        self.assertEqual(list(pd.read_csv(result.paths.csv).columns), list(parquet.columns))

    def test_xlsx_over_row_limit_is_skipped_without_invalidating_parquet(self) -> None:
        with mock.patch("marine_drift_desktop.core.results_export.EXCEL_MAX_DATA_ROWS", 2):
            result = generate_mortality_positions(
                make_results_fixture(self.root, write_xlsx=True)
            )

        self.assertTrue(result.paths.parquet.is_file())
        self.assertIsNone(result.paths.xlsx)
        self.assertTrue(any("exceeds Excel row limit" in item for item in result.warnings))

    def test_missing_source_match_writes_diagnostics_and_keeps_rows(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        source = self.root / "observations.csv"
        pd.DataFrame([{"id": "different", "observer": "B"}]).to_csv(source, index=False)

        result = generate_mortality_positions(request)
        table = pd.read_parquet(result.paths.parquet)
        failures = pd.read_csv(result.paths.failures)

        self.assertEqual(len(table), 2)
        self.assertIn("missing_source", set(failures["kind"]))
        self.assertTrue(any("source observation" in item.lower() for item in result.warnings))

    def test_exact_duplicate_source_rows_are_exported_once_per_trajectory(self) -> None:
        request = make_results_fixture(self.root)
        pd.DataFrame([{"id": "observation-1"}, {"id": "observation-1"}]).to_csv(
            self.root / "observations.csv", index=False
        )

        result = generate_mortality_positions(request)

        self.assertTrue(result.paths.parquet.exists())

    def test_invalid_coordinates_are_omitted_and_reported(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        import netCDF4

        path = next(request.results_directory.glob("*.nc"))
        with netCDF4.Dataset(path, "a") as dataset:
            dataset.variables["lon"][1, 24] = np.nan

        result = generate_mortality_positions(request)

        self.assertEqual(result.row_count, 1)
        self.assertEqual(result.omitted_positions, 1)

    def test_rejected_netcdf_is_counted_as_failed_without_discarding_valid_rows(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        make_trajectory_netcdf(request.results_directory / "unmarked.nc", marked=False)

        result = generate_mortality_positions(request)

        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.failed_files, 1)
        self.assertTrue(result.paths.failures.is_file())

    def test_cancellation_never_publishes_final_products(self) -> None:
        request = make_results_fixture(self.root)

        with self.assertRaises(ResultsExportCancelled):
            generate_mortality_positions(request, cancel_check=lambda: True)

        self.assertFalse((request.output_directory / "mortality_positions.parquet").exists())
        self.assertEqual(list(request.output_directory.glob("*.partial*")), [])

    def test_csv_conversion_cancellation_removes_partial_and_propagates(self) -> None:
        request = make_results_fixture(self.root)
        result = generate_mortality_positions(request)
        target = request.output_directory / "cancelled.csv"

        with self.assertRaises(ResultsExportCancelled):
            convert_parquet_to_csv(
                result.paths.parquet, target, cancel_check=lambda: True
            )

        self.assertFalse(target.exists())
        self.assertEqual(list(request.output_directory.glob("*.partial")), [])

    def test_cancellation_after_weighting_does_not_publish_parquet(self) -> None:
        request = make_results_fixture(self.root, write_csv=True)
        with mock.patch(
            "marine_drift_desktop.core.results_export.convert_parquet_to_csv",
            side_effect=ResultsExportCancelled("cancelled during conversion"),
        ):
            with self.assertRaises(ResultsExportCancelled):
                generate_mortality_positions(request)

        self.assertFalse((request.output_directory / "mortality_positions.parquet").exists())

    def test_runtime_file_failure_discards_rows_already_buffered_for_that_file(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        source = self.root / "observations.csv"
        failing = next(request.results_directory.glob("*.nc"))
        make_trajectory_netcdf(
            request.results_directory / "valid.nc",
            identifier="observation-1",
            iteration=2,
            observation_dataset=source,
        )
        original = results_export_module.iter_sampled_positions

        def rows(metadata, **kwargs):
            if metadata.path == failing:
                yield from list(original(metadata, **kwargs))[:1]
                raise ValueError("failure after first row")
            yield from original(metadata, **kwargs)

        events: list[dict[str, object]] = []
        with mock.patch.object(results_export_module, "iter_sampled_positions", rows):
            result = generate_mortality_positions(request, progress_callback=events.append)
        table = pd.read_parquet(result.paths.parquet)

        self.assertEqual(len(table), 2)
        self.assertEqual(result.accepted_files, 1)
        self.assertEqual(result.failed_files, 1)
        self.assertEqual(events[-1]["files"], 1)

    def test_last_weight_corrects_floating_residual_to_exact_group_sum(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=5)

        table = pd.read_parquet(generate_mortality_positions(request).paths.parquet)

        self.assertEqual(float(table["weight"].sum()), 1.0)

    def test_manifest_and_progress_describe_completed_canonical_export(self) -> None:
        events: list[dict[str, object]] = []
        result = generate_mortality_positions(
            make_results_fixture(self.root), progress_callback=events.append
        )
        manifest = json.loads(result.paths.manifest.read_text(encoding="utf-8"))

        self.assertEqual(manifest["row_count"], result.row_count)
        self.assertEqual(Path(manifest["paths"]["parquet"]), result.paths.parquet)
        self.assertEqual(events[-1]["stage"], "complete")

    def test_export_includes_selected_environmental_values_and_metadata(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        trajectory = next(request.results_directory.glob("*.nc"))
        trajectory.unlink()
        values = np.arange(2 * 25, dtype=float).reshape(2, 25)
        make_trajectory_netcdf(
            trajectory,
            observation_dataset=self.root / "observations.csv",
            environmental_variables={
                "sea_water_temperature": (
                    values,
                    {"units": "K", "standard_name": "sea_water_temperature"},
                )
            },
        )
        request.environmental_variables = ["sea_water_temperature"]

        result = generate_mortality_positions(request)
        table = pd.read_parquet(result.paths.parquet)
        manifest = json.loads(result.paths.manifest.read_text(encoding="utf-8"))

        self.assertEqual(table["sea_water_temperature"].tolist(), [24.0, 49.0])
        self.assertEqual(manifest["environmental_variables"]["sea_water_temperature"]["units"], "K")

    def test_partial_environmental_variable_exports_nulls_with_warning(self) -> None:
        request = make_results_fixture(self.root, positions_per_day=1)
        source = self.root / "observations.csv"
        first = next(request.results_directory.glob("*.nc"))
        first.unlink()
        wind = np.ones((2, 25), dtype=float)
        make_trajectory_netcdf(
            first,
            observation_dataset=source,
            environmental_variables={"x_wind": (wind, {"units": "m s-1"})},
        )
        make_trajectory_netcdf(
            request.results_directory / "second.nc",
            observation_dataset=source,
            iteration=2,
        )
        request.environmental_variables = ["x_wind"]

        result = generate_mortality_positions(request)
        table = pd.read_parquet(result.paths.parquet)

        self.assertEqual(table["x_wind"].notna().sum(), 2)
        self.assertEqual(table["x_wind"].isna().sum(), 2)
        self.assertTrue(any("x_wind" in warning and "1 of 2" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()
