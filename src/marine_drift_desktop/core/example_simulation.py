from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExampleSimulationResult:
    trajectory_path: Path
    forcing_path: Path
    particle_count: int
    steps: int


def run_example_simulation(
    output_directory: Path,
    *,
    steps: int = 2,
    particle_count: int = 20,
) -> ExampleSimulationResult:
    """Run a compact deterministic reverse-drift case through OpenDrift."""

    import numpy as np
    import xarray as xr
    from opendrift.models.oceandrift import OceanDrift
    from opendrift.readers import reader_netCDF_CF_generic

    output_directory.mkdir(parents=True, exist_ok=True)
    forcing_path = output_directory / "example_forcing.nc"
    trajectory_path = output_directory / "example_trajectory.nc"

    end_time = datetime(2024, 4, 13, 12)
    times = np.array(
        [end_time - timedelta(hours=hour) for hour in range(steps + 4)][::-1],
        dtype="datetime64[ns]",
    )
    latitudes = np.linspace(-13.2, -11.8, 8)
    longitudes = np.linspace(-39.2, -36.8, 10)
    shape = (len(times), len(latitudes), len(longitudes))
    dataset = xr.Dataset(
        data_vars={
            "eastward_current": (
                ("time", "latitude", "longitude"),
                np.full(shape, 0.08, dtype="float32"),
                {"standard_name": "eastward_sea_water_velocity", "units": "m s-1"},
            ),
            "northward_current": (
                ("time", "latitude", "longitude"),
                np.full(shape, 0.03, dtype="float32"),
                {"standard_name": "northward_sea_water_velocity", "units": "m s-1"},
            ),
        },
        coords={
            "time": ("time", times, {"standard_name": "time"}),
            "latitude": (
                "latitude", latitudes, {"standard_name": "latitude", "units": "degrees_north"}
            ),
            "longitude": (
                "longitude", longitudes, {"standard_name": "longitude", "units": "degrees_east"}
            ),
        },
        attrs={"title": "Marine Drift Workbench deterministic example forcing"},
    )
    dataset.to_netcdf(forcing_path)

    if trajectory_path.exists():
        trajectory_path.unlink()

    model = OceanDrift(loglevel=50)
    model.add_reader(reader_netCDF_CF_generic.Reader(forcing_path))
    model.set_config("general:use_auto_landmask", False)
    model.set_config("environment:fallback:land_binary_mask", 0)
    model.set_config("environment:fallback:x_wind", 0.0)
    model.set_config("environment:fallback:y_wind", 0.0)
    model.set_config("environment:fallback:sea_surface_wave_stokes_drift_x_velocity", 0.0)
    model.set_config("environment:fallback:sea_surface_wave_stokes_drift_y_velocity", 0.0)
    model.set_config("environment:fallback:sea_floor_depth_below_sea_level", 100.0)
    model.set_config("general:coastline_action", "none")
    model.seed_elements(
        lon=-37.2,
        lat=-12.5,
        number=particle_count,
        radius=500,
        time=end_time,
        wind_drift_factor=0.0,
    )
    model.run(
        steps=steps,
        time_step=-3600,
        time_step_output=3600,
        outfile=str(trajectory_path),
        export_variables=["status", "lon", "lat", "depth", "time"],
    )
    return ExampleSimulationResult(
        trajectory_path=trajectory_path,
        forcing_path=forcing_path,
        particle_count=particle_count,
        steps=steps,
    )
