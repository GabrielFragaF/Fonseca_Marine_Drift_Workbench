from __future__ import annotations

import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

from netCDF4 import Dataset
from netCDF4 import num2date

from marine_drift_desktop.core.trajectory_provenance import (
    PROVENANCE_SCHEMA_VERSION,
    read_trajectory_provenance,
    write_trajectory_provenance,
)
from marine_drift_desktop.core.planning import stranding_event_token
from tests import results_test_support
from tests.results_test_support import provenance_inputs, write_synthetic_trajectory


class TrajectoryProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_round_trip_preserves_exact_identifiers_and_numbers(self) -> None:
        path = self.root / "trajectory.nc"
        observation, iteration, request = write_synthetic_trajectory(
            path, particle_count=17, duration_days=9, marked=False
        )

        write_trajectory_provenance(path, observation, iteration, request)

        provenance = read_trajectory_provenance(path)

        self.assertEqual(
            [field.name for field in fields(provenance)],
            [
                "schema_version",
                "output_type",
                "stranding_identifier",
                "taxon_label",
                "decomposition_code",
                "observed_at",
                "reverse_drift_duration_days",
                "wind_drift_factor",
                "iteration_index",
                "simulation_start_time",
                "particles_per_release",
                "observation_dataset",
                "identifier_column",
                "environment_export_variables",
                "fallback_values",
                "decomposition_state",
                "event_token",
            ],
        )
        self.assertEqual(provenance.schema_version, PROVENANCE_SCHEMA_VERSION)
        self.assertEqual(provenance.output_type, "trajectory")
        self.assertEqual(provenance.stranding_identifier, "tag 42/alpha")
        self.assertEqual(provenance.taxon_label, "Marine fauna / test")
        self.assertEqual(provenance.decomposition_code, 3)
        self.assertEqual(provenance.observed_at, observation.observed_at)
        self.assertEqual(provenance.reverse_drift_duration_days, 9)
        self.assertEqual(provenance.wind_drift_factor, 0.015)
        self.assertEqual(provenance.iteration_index, 2)
        self.assertEqual(provenance.simulation_start_time, iteration.start_time)
        self.assertEqual(provenance.particles_per_release, 17)
        self.assertEqual(provenance.observation_dataset, request.data_sources.observation_dataset)
        self.assertIsInstance(provenance.observation_dataset, Path)
        self.assertEqual(provenance.identifier_column, "record/id")
        self.assertEqual(provenance.environment_export_variables, ())
        self.assertEqual(provenance.event_token, stranding_event_token(observation))
        self.assertFalse(provenance.fallback_values["currents_enabled"])
        with Dataset(path) as dataset:
            self.assertIn("marine_drift_observed_at", dataset.ncattrs())
            self.assertIn("marine_drift_reverse_drift_duration_days", dataset.ncattrs())
            self.assertIn("marine_drift_wind_drift_factor", dataset.ncattrs())
            self.assertIn("marine_drift_observation_dataset", dataset.ncattrs())
            self.assertIn("marine_drift_identifier_column", dataset.ncattrs())
            self.assertIn("marine_drift_environment_export_variables", dataset.ncattrs())
            self.assertIn("marine_drift_fallback_values", dataset.ncattrs())

    def test_environment_configuration_round_trips_and_optional_attributes_are_backward_compatible(self) -> None:
        path = self.root / "environment.nc"
        observation, iteration, request = write_synthetic_trajectory(path, marked=False)
        request.settings.environment_export_variables = ["sea_water_temperature", "x_wind"]
        request.settings.fallback_values.wind_enabled = True
        request.settings.fallback_values.x_wind = 1.5
        write_trajectory_provenance(path, observation, iteration, request)

        provenance = read_trajectory_provenance(path)

        self.assertEqual(provenance.environment_export_variables, ("sea_water_temperature", "x_wind"))
        self.assertTrue(provenance.fallback_values["wind_enabled"])
        self.assertEqual(provenance.fallback_values["x_wind"], 1.5)

        with Dataset(path, "a") as dataset:
            dataset.delncattr("marine_drift_environment_export_variables")
            dataset.delncattr("marine_drift_fallback_values")
        legacy = read_trajectory_provenance(path)
        self.assertEqual(legacy.environment_export_variables, ())
        self.assertEqual(legacy.fallback_values, {})

    def test_stable_fixture_writes_monotonic_time_coordinate_and_requested_shape(self) -> None:
        make_trajectory_netcdf = getattr(
            results_test_support, "make_trajectory_netcdf", None
        )
        self.assertIsNotNone(make_trajectory_netcdf)
        path = make_trajectory_netcdf(
            self.root / "capacity.nc",
            trajectories=5,
            duration_days=2,
            step_hours=6,
            marked=False,
        )

        with Dataset(path) as dataset:
            time = dataset.variables["time"]
            decoded = num2date(time[:], units=time.units, calendar=time.calendar)
            intervals = [
                (decoded[index + 1] - decoded[index]).total_seconds()
                for index in range(len(decoded) - 1)
            ]
            self.assertEqual(time.dimensions, ("time",))
            self.assertEqual(len(decoded), 9)
            self.assertTrue(all(interval == -6 * 3600 for interval in intervals))
            self.assertEqual(decoded[0].isoformat(), "2026-01-02T00:00:00")
            self.assertEqual(decoded[-1].isoformat(), "2025-12-31T00:00:00")
            self.assertEqual(dataset.variables["lon"].shape, (5, 9))
            self.assertEqual(dataset.variables["lat"].shape, (5, 9))

    def test_synthetic_fixtures_reject_intervals_that_do_not_evenly_divide_duration(
        self,
    ) -> None:
        cases = {
            "stable helper": lambda path: results_test_support.make_trajectory_netcdf(
                path, duration_days=1, step_hours=5
            ),
            "compatibility wrapper": lambda path: write_synthetic_trajectory(
                path, duration_days=1, output_interval_hours=5
            ),
        }

        for name, create_fixture in cases.items():
            with self.subTest(name=name):
                path = self.root / f"{name.replace(' ', '-')}.nc"
                with self.assertRaisesRegex(ValueError, "evenly divide"):
                    create_fixture(path)
                self.assertFalse(path.exists())

    def test_unmarked_and_unsupported_schema_files_are_rejected(self) -> None:
        unmarked_path = self.root / "unmarked.nc"
        write_synthetic_trajectory(unmarked_path, marked=False)
        unsupported_path = self.root / "unsupported.nc"
        write_synthetic_trajectory(unsupported_path, marked=False)
        with Dataset(unsupported_path, "a") as dataset:
            dataset.setncattr("marine_drift_schema_version", 999)
            dataset.setncattr("marine_drift_output_type", "trajectory")

        with self.assertRaisesRegex(ValueError, "unmarked"):
            read_trajectory_provenance(unmarked_path)
        with self.assertRaisesRegex(ValueError, "schema"):
            read_trajectory_provenance(unsupported_path)

    def test_writing_provenance_leaves_trajectory_arrays_unchanged(self) -> None:
        path = self.root / "trajectory.nc"
        observation, iteration, request = write_synthetic_trajectory(
            path, particle_count=4, duration_days=1, marked=False
        )
        with Dataset(path) as dataset:
            before = {
                name: dataset.variables[name][:].copy()
                for name in ("lon", "lat", "status")
            }

        write_trajectory_provenance(path, observation, iteration, request)

        with Dataset(path) as dataset:
            for name, expected in before.items():
                self.assertTrue((dataset.variables[name][:] == expected).all())


if __name__ == "__main__":
    unittest.main()
