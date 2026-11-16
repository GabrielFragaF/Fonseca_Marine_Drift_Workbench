from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from ..domain.models import (
    CanonicalObservation,
    SimulationIterationPlan,
    SimulationRequest,
    SimulationSettings,
)
from .duration import build_duration_profile
from .environment import resolve_environment_extent
from .io import read_observation_records
from .landmask import LandPredicate, adjust_to_nearby_water, is_position_within_extent
from .planning import plan_simulation_runs
from .records import canonicalize_observation
from .request_serialization import simulation_request_to_dict
from .selection import select_observation_records
from .trajectory_provenance import write_trajectory_provenance

DEFAULT_BATCH_SIZE = 5_000
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class SimulationJob:
    global_index: int
    observation: CanonicalObservation
    iteration: SimulationIterationPlan

    @property
    def key(self) -> str:
        return f"{self.observation.stranding_identifier}:{self.iteration.iteration_index}"


class SimulationJobExecutionError(RuntimeError):
    """Raised after a failed job is logged and checkpointed under the stop policy."""

    def __init__(self, job: SimulationJob, cause: Exception) -> None:
        super().__init__(f"Simulation job `{job.key}` failed: {cause}")
        self.job = job
        self.cause = cause


@dataclass(frozen=True, slots=True)
class SimulationBatchResult:
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    existing_jobs: int
    skipped_records: int
    checkpoint_path: Path
    failure_log_path: Path
    source_rows: int = 0
    selected_rows: int = 0
    positions_adjusted: int = 0
    position_search_failed: int = 0
    manifest_path: Path | None = None
    elapsed_seconds: float = 0.0
    completion_status: str = "completed"


@dataclass(frozen=True, slots=True)
class ObservationPreparationResult:
    observations: list[CanonicalObservation]
    source_rows: int
    selected_rows: int
    skipped_rows: int
    skip_reasons: dict[str, int]
    positions_adjusted: int
    position_search_failed: int


def batch_ranges(total_jobs: int, batch_size: int = DEFAULT_BATCH_SIZE) -> Iterator[tuple[int, int, int]]:
    if batch_size < 1:
        raise ValueError("Batch size must be at least 1.")
    for start in range(0, total_jobs, batch_size):
        yield start // batch_size + 1, start, min(start + batch_size, total_jobs)


def run_simulation_batches(
    request: SimulationRequest,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    execute_job: Callable[[SimulationJob, SimulationRequest, list[Any]], Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    is_land: LandPredicate | None = None,
    existing_output_decision: Callable[[dict[str, Any]], str] | None = None,
) -> SimulationBatchResult:
    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    if request.data_sources.output_directory is None:
        raise ValueError("Choose an output directory before running simulations.")
    if request.settings.job_error_policy not in {"continue", "stop"}:
        raise ValueError("Choose a supported simulation error policy.")
    output_directory = request.data_sources.output_directory
    preparation = prepare_observations(request, is_land=is_land)
    observations = preparation.observations
    if not observations:
        reasons = "; ".join(f"{reason} ({count})" for reason, count in preparation.skip_reasons.items())
        raise ValueError("No runnable observations. Check selection and field mappings. " + reasons)
    skipped_records = preparation.skipped_rows
    _validate_unique_output_paths(observations, request, output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_directory / ".marine_drift_checkpoint.json"
    failure_log_path = output_directory / "simulation_failures.jsonl"
    manifest_path = output_directory / "run_manifest.json"
    total_jobs = len(observations) * request.settings.iteration_count
    fingerprint = _request_fingerprint(request)
    checkpoint = _read_matching_checkpoint(checkpoint_path, fingerprint)
    has_matching_checkpoint = bool(checkpoint)
    next_job_index = min(int(checkpoint.get("next_job_index", 0)), total_jobs)
    preserved_paths: set[Path] = set()
    explicit_policy = existing_output_decision is not None
    if explicit_policy:
        from .resume import inspect_existing_outputs
        complete_paths, review = inspect_existing_outputs(
            _iter_jobs(observations, request, output_directory), output_directory,
            fingerprint, lambda event: _emit(progress_callback, event))
        review["configuration_changed"] |= not has_matching_checkpoint
        superseded = review.pop("superseded_files")
        review["changed_sections"] = []
        if manifest_path.exists():
            try:
                previous = json.loads(manifest_path.read_text(encoding="utf-8"))
                current = simulation_request_to_dict(request)
                review["changed_sections"] = [
                    key for key, value in current["settings"].items()
                    if previous.get("model_settings", {}).get(key) != value]
                if previous.get("field_mapping") != current["column_mapping"]:
                    review["changed_sections"].append("field_mapping")
            except (OSError, ValueError, AttributeError):
                pass
        if complete_paths or review["invalid"] or review["conflicts"] or review["unrelated"]:
            decision = existing_output_decision(review)
            if decision not in {"preserve", "overwrite"}:
                raise ValueError("Simulation start cancelled; existing results are unchanged.")
            if decision == "preserve":
                if review["conflicts"]:
                    raise ValueError("Some existing files cannot be identified safely. Choose a new output folder or explicitly overwrite them.")
                preserved_paths = complete_paths
            elif superseded:
                # Keep older names out of exports when a changed plan is recalculated.
                archive = output_directory / ".marine_drift_history" / run_id
                archive.mkdir(parents=True, exist_ok=True)
                for name in superseded:
                    path = Path(name)
                    path.rename(archive / path.name)
        next_job_index = len(preserved_paths)
    if manifest_path.exists():
        history = output_directory / ".marine_drift_history"
        history.mkdir(exist_ok=True)
        shutil.copy2(manifest_path, history / f"manifest-before-{run_id}.json")
    _write_run_manifest(
        manifest_path, request, run_id=run_id, started_at=started_at,
        completion_status="running", checkpoint_path=checkpoint_path,
        failure_log_path=failure_log_path,
    )
    completed_jobs = len(preserved_paths)
    failed_jobs = 0
    existing_jobs = len(preserved_paths)
    executed_jobs = 0
    executor = execute_job or _execute_opendrift_job
    readers = [] if execute_job is not None else _load_environment_readers(request)

    _emit(progress_callback, {
        "event": "workload", "total_jobs": total_jobs,
        "valid_records": len(observations), "skipped_records": skipped_records,
        "source_rows": preparation.source_rows,
        "selected_rows": preparation.selected_rows,
        "positions_adjusted": preparation.positions_adjusted,
        "position_search_failed": preparation.position_search_failed,
        "batch_size": batch_size, "resume_index": next_job_index,
        "existing": existing_jobs,
        "skip_reasons": preparation.skip_reasons,
    })

    active_batch = 0
    for job in _iter_jobs(observations, request, output_directory):
        if job.iteration.output_path in preserved_paths:
            continue
        checkpointed_job = (
            not explicit_policy and has_matching_checkpoint and job.global_index < next_job_index
        )
        if checkpointed_job and _output_is_complete(job.iteration.output_path):
            completed_jobs += 1
            existing_jobs += 1
            continue
        batch_number = job.global_index // batch_size + 1
        if batch_number != active_batch:
            active_batch = batch_number
            batch_start = (batch_number - 1) * batch_size
            _emit(progress_callback, {
                "event": "batch_started", "batch": batch_number,
                "start": batch_start,
                "end": min(batch_start + batch_size, total_jobs),
                "total_jobs": total_jobs,
                "processed": existing_jobs + executed_jobs if explicit_policy else job.global_index,
                "existing": existing_jobs, "failed": failed_jobs,
            })
        job_error: Exception | None = None
        try:
            executor(job, request, readers)
            completed_jobs += 1
        except Exception as exc:
            job_error = exc
            failed_jobs += 1
            with failure_log_path.open("a", encoding="utf-8") as failure_log:
                failure_log.write(json.dumps({
                    "job_index": job.global_index, "job": job.key,
                    "output": str(job.iteration.output_path), "error": str(exc),
                }) + "\n")

        executed_jobs += 1
        processed = existing_jobs + executed_jobs if explicit_policy else job.global_index + 1
        _emit(progress_callback, {
            "event": "progress", "processed": processed,
            "total_jobs": total_jobs, "completed": completed_jobs,
            "failed": failed_jobs, "existing": existing_jobs,
            "batch": batch_number, "job": job.key,
        })
        batch_finished = processed % batch_size == 0 or processed == total_jobs
        stopping_after_error = (
            job_error is not None and request.settings.job_error_policy == "stop"
        )
        if batch_finished or stopping_after_error:
            _write_checkpoint(
                checkpoint_path, fingerprint, processed, completed_jobs,
                failed_jobs, existing_jobs, total_jobs,
            )
        if batch_finished:
            _emit(progress_callback, {
                "event": "batch_completed", "batch": batch_number,
                "processed": processed, "total_jobs": total_jobs,
                "existing": existing_jobs, "failed": failed_jobs,
            })
        if stopping_after_error:
            _write_run_manifest(
                manifest_path, request, run_id=run_id, started_at=started_at,
                completion_status="failed", checkpoint_path=checkpoint_path,
                failure_log_path=failure_log_path, preparation=preparation,
                total_jobs=total_jobs, completed_jobs=completed_jobs,
                failed_jobs=failed_jobs, existing_jobs=existing_jobs,
                elapsed_seconds=time.monotonic() - started_monotonic,
            )
            raise SimulationJobExecutionError(job, job_error) from job_error

    elapsed_seconds = time.monotonic() - started_monotonic
    completion_status = "completed_with_errors" if failed_jobs else "completed"
    _write_checkpoint(
        checkpoint_path, fingerprint, total_jobs, completed_jobs,
        failed_jobs, existing_jobs, total_jobs,
    )
    _write_run_manifest(
        manifest_path, request, run_id=run_id, started_at=started_at,
        completion_status=completion_status, checkpoint_path=checkpoint_path,
        failure_log_path=failure_log_path, preparation=preparation,
        total_jobs=total_jobs, completed_jobs=completed_jobs,
        failed_jobs=failed_jobs, existing_jobs=existing_jobs,
        elapsed_seconds=elapsed_seconds,
    )
    return SimulationBatchResult(
        total_jobs=total_jobs,
        completed_jobs=completed_jobs,
        failed_jobs=failed_jobs,
        existing_jobs=existing_jobs,
        skipped_records=skipped_records,
        checkpoint_path=checkpoint_path,
        failure_log_path=failure_log_path,
        source_rows=preparation.source_rows,
        selected_rows=preparation.selected_rows,
        positions_adjusted=preparation.positions_adjusted,
        position_search_failed=preparation.position_search_failed,
        manifest_path=manifest_path,
        elapsed_seconds=elapsed_seconds,
        completion_status=completion_status,
    )


def _iter_jobs(
    observations: list[CanonicalObservation],
    request: SimulationRequest,
    output_directory: Path,
) -> Iterator[SimulationJob]:
    global_index = 0
    for observation in observations:
        for iteration in plan_simulation_runs(
            observation, request.settings, output_directory
        ):
            yield SimulationJob(global_index, observation, iteration)
            global_index += 1


def _validate_unique_output_paths(
    observations: list[CanonicalObservation],
    request: SimulationRequest,
    output_directory: Path,
) -> None:
    """Validate per-observation output namespaces without retaining all jobs."""
    identifiers_by_namespace: dict[Path, str] = {}
    for observation in observations:
        plans = plan_simulation_runs(observation, request.settings, output_directory)
        if not plans:
            continue
        paths: set[Path] = set()
        namespace: Path | None = None
        for iteration in plans:
            path = iteration.output_path
            if path in paths:
                raise ValueError(
                    "Output planner invariant: each iteration for an observation "
                    "must have a unique output path."
                )
            paths.add(path)
            iteration_namespace = _output_namespace(iteration)
            if namespace is None:
                namespace = iteration_namespace
            elif iteration_namespace != namespace:
                raise ValueError(
                    "Output planner invariant: all iterations for an observation "
                    "must share one output namespace."
                )
        assert namespace is not None
        prior_identifier = identifiers_by_namespace.get(namespace)
        if prior_identifier is not None:
            raise ValueError(
                "Output-name collision: "
                f"`{namespace.name}` is generated for both `{prior_identifier}` and "
                f"`{observation.stranding_identifier}`."
            )
        identifiers_by_namespace[namespace] = observation.stranding_identifier


def _output_namespace(iteration: SimulationIterationPlan) -> Path:
    suffix = f"_{iteration.iteration_index:02d}"
    stem = iteration.output_path.stem
    if not stem.endswith(suffix):
        raise ValueError(
            "Output planner invariant: output names must end with their "
            "zero-padded iteration index."
        )
    return iteration.output_path.with_name(
        f"{stem[:-len(suffix)]}{iteration.output_path.suffix}"
    )


def prepare_observations(
    request: SimulationRequest,
    *,
    is_land: LandPredicate | None = None,
) -> ObservationPreparationResult:
    if request.data_sources.observation_dataset is None:
        raise ValueError("Choose an observation dataset before running simulations.")
    records = read_observation_records(request.data_sources.observation_dataset)
    selection = select_observation_records(
        records, request.settings.observation_selection
    )
    extent = request.settings.extent
    coverage = request.settings.coverage
    if coverage.mode == "environment_intersection":
        paths = [
            reader.path for reader in request.data_sources.environment_readers
            if reader.path is not None
        ]
        if coverage.contributing_paths:
            selected_paths = {str(Path(path)) for path in coverage.contributing_paths}
            paths = [path for path in paths if str(path) in selected_paths]
        extent = resolve_environment_extent(paths, coverage.buffer_degrees)
        request.settings.extent = extent

    position_settings = request.settings.position_search
    land_predicate = is_land
    if position_settings.mode in {"search_nearby_water", "skip_if_invalid"} and land_predicate is None:
        land_predicate = _global_land_predicate()

    profile = build_duration_profile(request.settings.duration)
    observations: list[CanonicalObservation] = []
    observation_keys: set[tuple[object, ...]] = set()
    reasons: Counter[str] = Counter()
    positions_adjusted = 0
    position_search_failed = 0
    for record in selection.records:
        try:
            observation = canonicalize_observation(
                record, request.column_mapping, profile,
                wind_drift_settings=request.settings.wind_drift,
                coordinate_format=request.settings.coordinate_format,
                duration_column=(request.settings.duration.duration_column
                                 if request.settings.duration.mode == "dataset" else ""),
                fixed_duration_days=(request.settings.duration.fixed_days
                                     if request.settings.duration.mode == "fixed" else None),
                decomposition_value_map=request.settings.duration.decomposition_value_map,
            )
            if position_settings.mode == "skip_if_invalid":
                assert land_predicate is not None
                if land_predicate(observation.longitude, observation.latitude):
                    raise ValueError("Observation position is on land.")
            if position_settings.mode == "search_nearby_water":
                assert land_predicate is not None
                adjustment = adjust_to_nearby_water(
                    observation.longitude,
                    observation.latitude,
                    land_predicate,
                    extent,
                    shift_degrees=position_settings.radial_step_degrees,
                    max_radius_degrees=position_settings.max_radius_degrees,
                    angle_step_degrees=position_settings.angle_step_degrees,
                    max_attempts=position_settings.max_attempts,
                )
                if adjustment.search_failed:
                    position_search_failed += 1
                    message = "No nearby water position was found within the search limits."
                    if position_settings.failure_behavior == "stop":
                        raise RuntimeError(message)
                    raise ValueError(message)
                if adjustment.was_adjusted:
                    positions_adjusted += 1
                    observation = replace(
                        observation,
                        longitude=adjustment.longitude,
                        latitude=adjustment.latitude,
                    )
            if not is_position_within_extent(
                observation.longitude, observation.latitude, extent
            ):
                raise ValueError("Observation position is outside the spatial extent.")
            observation_key = (
                observation.stranding_identifier,
                observation.observed_at,
                observation.longitude,
                observation.latitude,
                observation.decomposition_code,
            )
            if observation_key in observation_keys:
                reasons["Exact duplicate observation row."] += 1
                continue
            observation_keys.add(observation_key)
        except RuntimeError:
            raise
        except (KeyError, ValueError) as exc:
            reasons[str(exc)] += 1
            continue
        observations.append(observation)
    return ObservationPreparationResult(
        observations=observations,
        source_rows=selection.source_count,
        selected_rows=selection.selected_count,
        skipped_rows=selection.selected_count - len(observations),
        skip_reasons=dict(reasons),
        positions_adjusted=positions_adjusted,
        position_search_failed=position_search_failed,
    )


def _global_land_predicate() -> LandPredicate:
    import numpy as np
    from opendrift.readers.reader_global_landmask import Reader

    reader = Reader()

    def is_land(longitude: float, latitude: float) -> bool:
        result = reader.get_variables(
            "land_binary_mask",
            x=np.asarray([longitude], dtype=float),
            y=np.asarray([latitude], dtype=float),
        )["land_binary_mask"]
        return bool(np.asarray(result).reshape(-1)[0])

    return is_land


def _load_environment_readers(request: SimulationRequest) -> list[Any]:
    from opendrift.readers.reader_netCDF_CF_generic import Reader

    paths = [reader.path for reader in request.data_sources.environment_readers]
    if not paths:
        paths = [
            path for name, path in request.data_sources.input_sources().items()
            if name != "observation_dataset" and path is not None
        ]
    unique_paths = list(dict.fromkeys(paths))
    return [Reader(str(path)) for path in unique_paths]


def _execute_opendrift_job(
    job: SimulationJob,
    request: SimulationRequest,
    readers: list[Any],
) -> None:
    _disable_opendrift_git_version_lookup()
    from opendrift.models.oceandrift import OceanDrift
    from .environment_export import validate_environment_variables

    settings = request.settings
    fallback = settings.fallback_values
    model = OceanDrift(loglevel=50)
    for reader in readers:
        model.add_reader(reader)
    has_landmask = any("land_binary_mask" in getattr(reader, "variables", ()) for reader in readers)
    model.set_config("general:use_auto_landmask", not has_landmask)
    model.set_config("environment:fallback:x_sea_water_velocity", fallback.x_sea_water_velocity if fallback.currents_enabled else None)
    model.set_config("environment:fallback:y_sea_water_velocity", fallback.y_sea_water_velocity if fallback.currents_enabled else None)
    model.set_config("environment:fallback:x_wind", 0.0)
    model.set_config("environment:fallback:y_wind", 0.0)
    model.set_config(
        "environment:fallback:sea_surface_wave_stokes_drift_x_velocity",
        fallback.stokes_drift_x_velocity if fallback.stokes_drift_enabled else None,
    )
    model.set_config(
        "environment:fallback:sea_surface_wave_stokes_drift_y_velocity",
        fallback.stokes_drift_y_velocity if fallback.stokes_drift_enabled else None,
    )
    model.set_config(
        "environment:fallback:sea_floor_depth_below_sea_level",
        fallback.sea_floor_depth_below_sea_level if fallback.seafloor_depth_enabled else None,
    )
    model.set_config("general:coastline_action", settings.coastline_action)
    current_uncertainty, wind_uncertainty = resolve_uncertainty_values(settings)
    model.set_config("drift:current_uncertainty", current_uncertainty)
    model.set_config("drift:wind_uncertainty", wind_uncertainty)
    observation = job.observation
    if observation.wind_drift_factor != 0:
        if not any({"x_wind", "y_wind"}.issubset(getattr(reader, "variables", ())) for reader in readers):
            raise ValueError("Active windage requires both horizontal wind components in an environmental reader.")
        model.set_config("environment:fallback:x_wind", fallback.x_wind if fallback.wind_enabled else None)
        model.set_config("environment:fallback:y_wind", fallback.y_wind if fallback.wind_enabled else None)
    model.seed_elements(
        lon=observation.longitude,
        lat=observation.latitude,
        number=settings.particle_count,
        radius=settings.release_radius_meters,
        time=job.iteration.start_time,
        wind_drift_factor=observation.wind_drift_factor,
    )
    job.iteration.output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_output_path = job.iteration.output_path.with_name(
        f"{job.iteration.output_path.stem}.partial{job.iteration.output_path.suffix}"
    )
    time_step_seconds = settings.model_time_step_hours * 3600
    steps = round(observation.reverse_drift_duration_days * 24 / settings.model_time_step_hours)
    export_variables = list(dict.fromkeys([
        "status", "lon", "lat", "depth", "time",
        *validate_environment_variables(settings.environment_export_variables),
    ]))
    model.run(
        steps=steps,
        time_step=-time_step_seconds,
        time_step_output=time_step_seconds,
        outfile=str(partial_output_path),
        export_variables=export_variables,
    )
    # OpenDrift retains a lazy read handle after finalising its NetCDF output.
    # Close it before reopening the file to attach provenance; HDF5 on macOS
    # rejects concurrent access to the same file.
    result_dataset = getattr(model, "result", None)
    close_result = getattr(result_dataset, "close", None)
    if callable(close_result):
        close_result()
    write_trajectory_provenance(partial_output_path, observation, job.iteration, request)
    from netCDF4 import Dataset
    with Dataset(partial_output_path, "a") as dataset:
        dataset.setncattr("marine_drift_request_fingerprint", _request_fingerprint(request))
    os.replace(partial_output_path, job.iteration.output_path)


def _disable_opendrift_git_version_lookup() -> None:
    """Avoid a visible `git` subprocess for every model in Windows GUI runs."""
    import opendrift.version

    opendrift.version.version_or_git = lambda: opendrift.version.__version__


def resolve_uncertainty_values(settings: SimulationSettings) -> tuple[float, float]:
    """Resolve user-facing uncertainty switches into OpenDrift configuration values."""
    return (
        settings.current_uncertainty if settings.current_uncertainty_enabled else 0.0,
        settings.wind_uncertainty if settings.wind_uncertainty_enabled else 0.0,
    )


def _output_is_complete(path: Path) -> bool:
    """Return whether a trajectory file is safe to skip during resume."""
    if not path.exists():
        return False
    try:
        from netCDF4 import Dataset

        with Dataset(path) as dataset:
            time_dimension = dataset.dimensions.get("time")
            return bool(
                time_dimension is not None
                and len(time_dimension) > 0
                and "lon" in dataset.variables
                and "lat" in dataset.variables
            )
    except (OSError, RuntimeError, ValueError):
        return False


def _request_fingerprint(request: SimulationRequest) -> str:
    paths = [path for path in request.data_sources.input_sources().values() if path]
    paths.extend(reader.path for reader in request.data_sources.environment_readers)
    inputs = []
    for path in sorted(set(paths), key=str):
        try:
            stat = path.stat()
            inputs.append((str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except OSError:
            inputs.append((str(path.resolve()), None))
    payload = json.dumps(
        {"engine_revision": 2, "configuration": simulation_request_to_dict(request), "input_files": inputs},
        sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_matching_checkpoint(path: Path, fingerprint: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if payload.get("request_fingerprint") == fingerprint else {}


def _write_checkpoint(
    path: Path, fingerprint: str, next_job_index: int, completed_jobs: int,
    failed_jobs: int, existing_jobs: int, total_jobs: int,
) -> None:
    payload = json.dumps({
        "request_fingerprint": fingerprint,
        "next_job_index": next_job_index,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "existing_jobs": existing_jobs,
        "total_jobs": total_jobs,
    }, indent=2)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(payload, encoding="utf-8")
    os.replace(temporary_path, path)


def _package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _write_run_manifest(
    path: Path,
    request: SimulationRequest,
    *,
    run_id: str,
    started_at: str,
    completion_status: str,
    checkpoint_path: Path,
    failure_log_path: Path,
    preparation: ObservationPreparationResult | None = None,
    total_jobs: int = 0,
    completed_jobs: int = 0,
    failed_jobs: int = 0,
    existing_jobs: int = 0,
    elapsed_seconds: float = 0.0,
) -> None:
    request_payload = simulation_request_to_dict(request)
    output_directory = request.data_sources.output_directory
    payload = {
        "run_id": run_id,
        "created_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow": "reverse_drift",
        "completion_status": completion_status,
        "elapsed_seconds": elapsed_seconds,
        "observation_dataset": str(
            request.data_sources.observation_dataset or ""
        ),
        "forcing_files": [
            {
                "path": str(reader.path),
                "roles": list(reader.roles),
                "variables": list(reader.recognized_variables),
            }
            for reader in request.data_sources.environment_readers
        ],
        "model_settings": request_payload["settings"],
        "request_fingerprint": _request_fingerprint(request),
        "field_mapping": request_payload["column_mapping"],
        "workload": {
            "source_rows": preparation.source_rows if preparation else 0,
            "selected_rows": preparation.selected_rows if preparation else 0,
            "valid_rows": len(preparation.observations) if preparation else 0,
            "skipped_rows": preparation.skipped_rows if preparation else 0,
            "scenario_count": request.settings.iteration_count,
            "particles_per_release": request.settings.particle_count,
            "trajectory_count": total_jobs,
            "completed": completed_jobs,
            "existing": existing_jobs,
            "failed": failed_jobs,
        },
        "output_paths": {
            "directory": str(output_directory or ""),
            "checkpoint": str(checkpoint_path),
            "failure_log": str(failure_log_path),
        },
        "software_versions": {
            "python": sys.version.split()[0],
            "marine_drift_workbench": _package_version("marine-drift-desktop"),
            "opendrift": _package_version("opendrift"),
        },
    }
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary_path, path)


def _emit(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is not None:
        callback(event)
