from __future__ import annotations

import contextlib
import io
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from marine_drift_desktop.core.request_serialization import write_simulation_request
from marine_drift_desktop.core.results_inspection import inspect_results_directory
from marine_drift_desktop.core.trajectory_provenance import read_trajectory_provenance
from marine_drift_desktop.domain.models import (
    ColumnMapping,
    EnvironmentalReaderConfig,
    FilterCondition,
    SimulationRequest,
)
from marine_drift_desktop.simulation_worker import run_worker


class SimulationWorkerTests(unittest.TestCase):
    def test_serialized_request_runs_a_real_opendrift_simulation(self) -> None:
        import numpy as np
        import xarray as xr

        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "simulation_worker"
        output = root / "outputs"
        root.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        for path in output.glob("*"):
            if path.is_file():
                path.unlink()

        observed_at = datetime(2024, 4, 13, 12)
        times = np.array(
            [observed_at - timedelta(hours=hour) for hour in range(30)][::-1],
            dtype="datetime64[ns]",
        )
        latitudes = np.linspace(-13.0, -12.0, 4)
        longitudes = np.linspace(-38.0, -37.0, 4)
        shape = (len(times), len(latitudes), len(longitudes))
        forcing = root / "forcing.nc"
        xr.Dataset(
            data_vars={
                "eastward_current": (
                    ("time", "latitude", "longitude"),
                    np.full(shape, 0.05, dtype="float32"),
                    {"standard_name": "eastward_sea_water_velocity", "units": "m s-1"},
                ),
                "northward_current": (
                    ("time", "latitude", "longitude"),
                    np.full(shape, 0.02, dtype="float32"),
                    {"standard_name": "northward_sea_water_velocity", "units": "m s-1"},
                ),
            },
            coords={
                "time": ("time", times, {"standard_name": "time"}),
                "latitude": (
                    "latitude", latitudes,
                    {"standard_name": "latitude", "units": "degrees_north"},
                ),
                "longitude": (
                    "longitude", longitudes,
                    {"standard_name": "longitude", "units": "degrees_east"},
                ),
            },
        ).to_netcdf(forcing)

        observations = root / "observations.csv"
        observations.write_text(
            "id,taxon,decomp,sst,windage,lon,lat,date,time,duration\n"
            "worker-1,Marine fauna,1,22,0,-37.4,-12.5,2024-04-13,12:00,1\n"
            "worker-2,Marine fauna,1,22,0,-37.5,-12.5,2024-04-13,12:00,1\n"
            "worker-3,Marine fauna,1,22,0,-37.6,-12.5,2024-04-13,12:00,1\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = observations
        request.data_sources.output_directory = output
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(forcing, ["Currents"], [])
        ]
        request.column_mapping = ColumnMapping(
            stranding_identifier="id", taxon_label="taxon",
            decomposition_code="decomp", sea_surface_temperature="sst",
            wind_drift_factor="", longitude="lon", latitude="lat",
            observed_date="date", observed_time="time",
        )
        request.settings.duration.mode = "fixed"
        request.settings.duration.fixed_days = 1
        request.settings.wind_drift.mode = "none"
        request.settings.iteration_count = 1
        request.settings.particle_count = 2
        request.settings.coastline_action = "none"
        request.settings.fallback_values.stokes_drift_enabled = True
        request.settings.fallback_values.seafloor_depth_enabled = True
        request.settings.observation_selection.mode = "filter"
        request.settings.observation_selection.conditions = [
            FilterCondition(column="id", operator="equals", value="worker-1")
        ]
        request_path = write_simulation_request(request, root / "request.json")

        worker_output = io.StringIO()
        with contextlib.redirect_stdout(worker_output):
            exit_code = run_worker(str(request_path))

        events = [
            json.loads(line.split("=", 1)[1])
            for line in worker_output.getvalue().splitlines()
            if line.startswith("MARINE_DRIFT_EVENT=")
        ]
        self.assertEqual(exit_code, 0)
        self.assertEqual(events[-1]["event"], "finished")
        self.assertEqual(events[-1]["completed"], 1)
        self.assertEqual(events[-1]["completion_status"], "completed")
        self.assertGreaterEqual(events[-1]["elapsed_seconds"], 0.0)
        manifest_path = Path(events[-1]["manifest_path"])
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["completion_status"], "completed")
        self.assertEqual(manifest["workload"]["source_rows"], 3)
        self.assertEqual(manifest["workload"]["selected_rows"], 1)
        self.assertEqual(manifest["workload"]["trajectory_count"], 1)
        self.assertIn("software_versions", manifest)
        workload = next(event for event in events if event["event"] == "workload")
        self.assertEqual(workload["source_rows"], 3)
        self.assertEqual(workload["selected_rows"], 1)
        self.assertIn("elapsed_seconds", workload)
        trajectories = list(output.glob("*.nc"))
        self.assertEqual(len(trajectories), 1)
        provenance = read_trajectory_provenance(trajectories[0])
        self.assertEqual(provenance.particles_per_release, 2)
        self.assertEqual(provenance.stranding_identifier, "worker-1")
        self.assertEqual(provenance.identifier_column, "id")
        self.assertEqual(provenance.observation_dataset, observations)

        inspection = inspect_results_directory(output)
        self.assertEqual(inspection.accepted_file_count, 1)
        self.assertEqual(inspection.particle_trajectory_count, 2)
        self.assertEqual(inspection.files[0].time_count, 25)
        self.assertEqual(inspection.files[0].output_interval_seconds, 3600.0)
        self.assertEqual(inspection.files[0].max_positions_per_drift_day, 24)
        self.assertEqual(inspection.max_positions_per_drift_day, 24)


if __name__ == "__main__":
    unittest.main()
