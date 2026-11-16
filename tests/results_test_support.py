from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from marine_drift_desktop.core.trajectory_provenance import (
    write_trajectory_provenance,
)
from marine_drift_desktop.domain.models import (
    CanonicalObservation,
    ColumnMapping,
    DataSourcePaths,
    SimulationIterationPlan,
    SimulationRequest,
    SimulationSettings,
)
from marine_drift_desktop.domain.results import ResultsExportRequest


def provenance_inputs(
    root: Path,
    *,
    identifier: str = "tag 42/alpha",
    taxon_label: str = "Marine fauna / test",
    particle_count: int = 3,
    duration_days: int = 2,
) -> tuple[CanonicalObservation, SimulationIterationPlan, SimulationRequest]:
    observed_at = datetime(2024, 4, 13, 7, 50)
    observation = CanonicalObservation(
        stranding_identifier=identifier,
        taxon_label=taxon_label,
        decomposition_code=3,
        sea_surface_temperature=22.0,
        wind_drift_factor=0.015,
        longitude=-38.0,
        latitude=-12.0,
        observed_at=observed_at,
        reverse_drift_duration_days=duration_days,
    )
    iteration = SimulationIterationPlan(
        iteration_index=2,
        start_time=observed_at + timedelta(hours=2),
        output_path=root / "trajectory.nc",
    )
    request = SimulationRequest(
        data_sources=DataSourcePaths(observation_dataset=root / "source data.csv"),
        column_mapping=ColumnMapping(stranding_identifier="record/id"),
        settings=SimulationSettings(particle_count=particle_count),
    )
    return observation, iteration, request


def write_synthetic_trajectory(
    path: Path,
    *,
    particle_count: int = 3,
    duration_days: int = 2,
    output_interval_hours: int = 1,
    include_status: bool = True,
    marked: bool = True,
) -> tuple[CanonicalObservation, SimulationIterationPlan, SimulationRequest]:
    """Create a small, production-shaped trajectory file for result tests."""
    if particle_count < 1:
        raise ValueError("particle_count must be at least 1")
    if duration_days < 0:
        raise ValueError("duration_days must not be negative")
    if output_interval_hours < 1:
        raise ValueError("output_interval_hours must be at least 1")

    path.parent.mkdir(parents=True, exist_ok=True)
    observation, iteration, request = provenance_inputs(
        path.parent,
        particle_count=particle_count,
        duration_days=duration_days,
    )
    iteration.output_path = path
    _write_trajectory_arrays(
        path,
        trajectories=particle_count,
        duration_days=duration_days,
        step_hours=output_interval_hours,
        include_status=include_status,
        start_time=iteration.start_time,
    )

    if marked:
        write_trajectory_provenance(path, observation, iteration, request)
    return observation, iteration, request


def make_trajectory_netcdf(
    path: Path,
    *,
    identifier: str = "observation-1",
    taxon: str = "Marine fauna",
    trajectories: int = 2,
    duration_days: int = 1,
    step_hours: int = 1,
    iteration: int = 1,
    marked: bool = True,
    observation_dataset: Path | None = None,
    identifier_column: str = "id",
    observed_at: datetime | None = None,
    environmental_variables: dict[str, tuple[np.ndarray, dict[str, str]]] | None = None,
) -> Path:
    """Create a deterministic trajectory file for downstream results tests."""
    if trajectories < 1:
        raise ValueError("trajectories must be at least 1")
    if duration_days < 0:
        raise ValueError("duration_days must not be negative")
    if step_hours < 1:
        raise ValueError("step_hours must be at least 1")

    path.parent.mkdir(parents=True, exist_ok=True)
    trajectory_start = datetime(2026, 1, 2)
    if marked:
        observation, iteration_plan, request = provenance_inputs(
            path.parent,
            identifier=identifier,
            taxon_label=taxon,
            particle_count=trajectories,
            duration_days=duration_days,
        )
        if observed_at is not None:
            observation = replace(observation, observed_at=observed_at)
            iteration_plan.start_time = observed_at
        trajectory_start = iteration_plan.start_time
        iteration_plan.iteration_index = iteration
        iteration_plan.output_path = path
        request.data_sources.observation_dataset = (
            observation_dataset or path.parent / "observations.csv"
        )
        request.column_mapping.stranding_identifier = identifier_column
    _write_trajectory_arrays(
        path,
        trajectories=trajectories,
        duration_days=duration_days,
        step_hours=step_hours,
        include_status=True,
        start_time=trajectory_start,
        environmental_variables=environmental_variables,
    )
    if marked:
        write_trajectory_provenance(path, observation, iteration_plan, request)
    return path


def make_results_fixture(
    root: Path,
    *,
    positions_per_day: int = 4,
    write_csv: bool = False,
    write_xlsx: bool = False,
) -> ResultsExportRequest:
    results = root / "run"
    exports = root / "exports"
    results.mkdir(parents=True, exist_ok=True)
    source = root / "observations.csv"
    pd.DataFrame(
        [{"id": "observation-1", "observer": "Researcher A", "length_cm": 92.5}]
    ).to_csv(source, index=False)
    make_trajectory_netcdf(
        results / "observation-1_Marine-fauna_DEC3_DUR1d_01.nc",
        observation_dataset=source,
    )
    return ResultsExportRequest(
        results_directory=results,
        output_directory=exports,
        positions_per_drift_day=positions_per_day,
        write_csv=write_csv,
        write_xlsx=write_xlsx,
    )


def _write_trajectory_arrays(
    path: Path,
    *,
    trajectories: int,
    duration_days: int,
    step_hours: int,
    include_status: bool,
    start_time: datetime,
    environmental_variables: dict[str, tuple[np.ndarray, dict[str, str]]] | None = None,
) -> None:
    duration_hours = duration_days * 24
    if duration_hours % step_hours != 0:
        raise ValueError(
            "step_hours/output_interval_hours must evenly divide duration_days*24"
        )
    elapsed = np.arange(0, duration_hours + 1, step_hours)
    times = np.datetime64(start_time, "ns") - elapsed.astype("timedelta64[h]")
    lon = np.arange(trajectories, dtype=float)[:, None] + elapsed[None, :] / 100.0
    lat = np.arange(trajectories, dtype=float)[:, None] - elapsed[None, :] / 100.0
    data_vars = {
        "lon": (("trajectory", "time"), lon),
        "lat": (("trajectory", "time"), lat),
    }
    if include_status:
        data_vars["status"] = (
            ("trajectory", "time"),
            np.zeros_like(lon, dtype="int16"),
        )
    for name, (values, attributes) in (environmental_variables or {}).items():
        data_vars[name] = (("trajectory", "time"), values, attributes)
    xr.Dataset(
        data_vars=data_vars,
        coords={"trajectory": np.arange(trajectories), "time": times},
    ).to_netcdf(path)
