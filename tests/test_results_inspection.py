from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xarray as xr
from netCDF4 import Dataset

from marine_drift_desktop.core import results_inspection
from marine_drift_desktop.core.results_inspection import (
    ResultsInspectionError,
    inspect_results_directory,
    validate_sampling_capacity,
)
from marine_drift_desktop.core.trajectory_provenance import write_trajectory_provenance
from tests import results_test_support


class ResultsInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source_path = self.root / "observations.csv"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_inspection_counts_mixed_files_and_uses_least_dense_capacity(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "a.nc",
            identifier="alpha",
            trajectories=3,
            duration_days=2,
            step_hours=1,
            iteration=1,
            observation_dataset=self.source_path,
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "b.nc",
            identifier="bravo",
            trajectories=2,
            duration_days=1,
            step_hours=3,
            iteration=2,
            observation_dataset=self.source_path,
        )

        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.total_file_count, 2)
        self.assertEqual(inspection.accepted_file_count, 2)
        self.assertEqual(inspection.simulation_count, 2)
        self.assertEqual(inspection.particle_trajectory_count, 5)
        self.assertEqual(inspection.unique_identifiers, ("alpha", "bravo"))
        self.assertEqual(
            getattr(inspection, "minimum_output_interval_seconds", None),
            3600.0,
        )
        self.assertEqual(inspection.max_positions_per_drift_day, 8)
        self.assertEqual(inspection.estimated_rows(4), 32)
        self.assertEqual(inspection.observation_dataset, self.source_path)
        self.assertEqual(inspection.identifier_column, "id")
        self.assertFalse(inspection.observation_dataset_available)

    def test_inspection_rejects_unmarked_file_without_discarding_valid_file(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "forcing.nc", marked=False
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "trajectory.nc", observation_dataset=self.source_path
        )

        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.accepted_file_count, 1)
        self.assertEqual(inspection.total_file_count, 2)
        self.assertEqual(len(inspection.issues), 1)
        self.assertIn("unmarked", inspection.issues[0].message)

    def test_inspection_fails_when_no_valid_files_remain(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "unmarked.nc", marked=False
        )

        with self.assertRaisesRegex(ResultsInspectionError, "No valid"):
            inspect_results_directory(self.root)

    def test_inspection_reports_missing_required_variable(self) -> None:
        path = results_test_support.make_trajectory_netcdf(
            self.root / "missing-lat.nc", observation_dataset=self.source_path
        )
        with Dataset(path, "a") as dataset:
            dataset.renameVariable("lat", "latitude")

        results_test_support.make_trajectory_netcdf(
            self.root / "valid.nc", observation_dataset=self.source_path
        )
        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.accepted_file_count, 1)
        self.assertEqual(len(inspection.issues), 1)
        self.assertIn(
            "missing required variable `lat`", inspection.issues[0].message.lower()
        )

    def test_inspection_reports_invalid_trajectory_dimensions(self) -> None:
        self._write_custom_trajectory(
            self.root / "invalid-shape.nc",
            lon_dimensions=("trajectory", "time"),
            lat_dimensions=("trajectory", "other_time"),
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "valid.nc", observation_dataset=self.source_path
        )

        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.accepted_file_count, 1)
        self.assertEqual(len(inspection.issues), 1)
        self.assertIn("trajectory x time", inspection.issues[0].message)

    def test_inspection_reports_irregular_time_spacing(self) -> None:
        path = results_test_support.make_trajectory_netcdf(
            self.root / "irregular.nc", duration_days=1, observation_dataset=self.source_path
        )
        with Dataset(path, "a") as dataset:
            time = dataset.variables["time"]
            values = time[:]
            values[2] = values[1] - 2
            time[:] = values
        results_test_support.make_trajectory_netcdf(
            self.root / "valid.nc", observation_dataset=self.source_path
        )

        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.accepted_file_count, 1)
        self.assertEqual(len(inspection.issues), 1)
        self.assertIn("regular", inspection.issues[0].message)

    def test_inspection_rejects_conflicting_source_provenance(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "a.nc",
            observation_dataset=self.root / "source-a.csv",
            identifier_column="record_id",
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "b.nc",
            observation_dataset=self.root / "source-b.csv",
            identifier_column="record_id",
        )

        with self.assertRaisesRegex(ResultsInspectionError, "observation dataset"):
            inspect_results_directory(self.root)

    def test_inspection_allows_conflicting_source_paths_with_override(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "a.nc", observation_dataset=self.root / "source-a.csv"
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "b.nc", observation_dataset=self.root / "source-b.csv"
        )
        override = self.root / "current-source.csv"

        inspection = inspect_results_directory(
            self.root, observation_dataset_override=override
        )

        self.assertEqual(inspection.observation_dataset, override)
        self.assertTrue(any(issue.level == "warning" for issue in inspection.issues))

    def test_inspection_rejects_conflicting_identifier_columns(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "a.nc",
            observation_dataset=self.source_path,
            identifier_column="record_id",
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "b.nc",
            observation_dataset=self.source_path,
            identifier_column="tag_id",
        )

        with self.assertRaisesRegex(ResultsInspectionError, "identifier column"):
            inspect_results_directory(self.root)

    def test_sampling_validation_rejects_zero_and_over_capacity(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "trajectory.nc", step_hours=6, observation_dataset=self.source_path
        )
        inspection = inspect_results_directory(self.root)

        with self.assertRaisesRegex(ValueError, "at least 1"):
            validate_sampling_capacity(inspection, 0)
        with self.assertRaisesRegex(ValueError, "available output frequency"):
            validate_sampling_capacity(inspection, 5)
        validate_sampling_capacity(inspection, 4)

    def test_inspection_never_materializes_trajectory_arrays(self) -> None:
        results_test_support.make_trajectory_netcdf(
            self.root / "trajectory.nc", observation_dataset=self.source_path
        )

        with patch.object(results_inspection, "Dataset", _GuardedDataset):
            inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.accepted_file_count, 1)

    def test_inspection_reports_common_and_partial_environmental_variables(self) -> None:
        shape = (2, 25)
        temperature = np.arange(np.prod(shape), dtype=float).reshape(shape)
        wind = np.ones(shape, dtype=float)
        results_test_support.make_trajectory_netcdf(
            self.root / "a.nc",
            observation_dataset=self.source_path,
            environmental_variables={
                "sea_water_temperature": (temperature, {"units": "K", "standard_name": "sea_water_temperature"}),
                "x_wind": (wind, {"units": "m s-1", "long_name": "Eastward wind"}),
            },
        )
        results_test_support.make_trajectory_netcdf(
            self.root / "b.nc",
            observation_dataset=self.source_path,
            environmental_variables={
                "sea_water_temperature": (temperature, {"units": "K", "standard_name": "sea_water_temperature"}),
            },
        )

        inspection = inspect_results_directory(self.root)

        self.assertEqual(inspection.common_environmental_variables, ("sea_water_temperature",))
        self.assertEqual(inspection.partial_environmental_variables, ("x_wind",))
        descriptor = inspection.environmental_variables["sea_water_temperature"]
        self.assertEqual(descriptor.units, "K")
        self.assertEqual(descriptor.available_file_count, 2)

    def _write_custom_trajectory(
        self,
        path: Path,
        *,
        lon_dimensions: tuple[str, str],
        lat_dimensions: tuple[str, str],
    ) -> None:
        times = np.array(
            ["2026-01-02T00:00", "2026-01-01T23:00"], dtype="datetime64[ns]"
        )
        dataset = xr.Dataset(
            data_vars={
                "lon": (lon_dimensions, np.zeros((2, 2))),
                "lat": (lat_dimensions, np.zeros((2, 2))),
            },
            coords={
                "trajectory": np.arange(2),
                "time": times,
                "other_time": np.arange(2),
            },
        )
        dataset.to_netcdf(path)
        observation, iteration, request = results_test_support.provenance_inputs(path.parent)
        iteration.output_path = path
        request.data_sources.observation_dataset = self.source_path
        write_trajectory_provenance(path, observation, iteration, request)


class _GuardedDataset:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._dataset = Dataset(*args, **kwargs)

    def __enter__(self) -> _GuardedDataset:
        self._dataset.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._dataset.__exit__(*args)

    @property
    def variables(self) -> dict[str, _GuardedVariable]:
        return {
            name: _GuardedVariable(name, variable)
            for name, variable in self._dataset.variables.items()
        }


class _GuardedVariable:
    def __init__(self, name: str, variable: object) -> None:
        self._name = name
        self._variable = variable

    @property
    def dimensions(self) -> tuple[str, ...]:
        return self._variable.dimensions

    @property
    def shape(self) -> tuple[int, ...]:
        return self._variable.shape

    def __getitem__(self, index: object) -> object:
        if self._name in {"lon", "lat", "status"}:
            raise AssertionError(f"inspection materialized {self._name}")
        return self._variable[index]

    def __getattr__(self, name: str) -> object:
        return getattr(self._variable, name)


if __name__ == "__main__":
    unittest.main()
