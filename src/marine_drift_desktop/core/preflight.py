from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable, Literal

from ..domain.models import SimulationRequest, SimulationSummary, ValidationMessage
from .batch_execution import prepare_observations
from . import environment
from .environment import EnvironmentalReaderInspection
from .forcing_validation import ForcingReadiness, evaluate_forcing_readiness
from .landmask import LandPredicate
from .planning import plan_simulation_runs
from .validation import SimulationRequestValidator, validate_output_destination

CheckLevel = Literal["success", "error", "warning", "info"]
WorkflowStep = Literal[
    "stranding_data", "environmental_forcing", "simulation_setup", "review_run"
]


@dataclass(frozen=True, slots=True)
class PreflightCheck:
    key: str
    level: CheckLevel
    title: str
    detail: str
    target_step: WorkflowStep
    blocks_run: bool = False
    subsection: int | None = None
    field_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreflightResult:
    checks: tuple[PreflightCheck, ...] = ()
    validation_messages: tuple[ValidationMessage, ...] = ()
    environment_inspections: tuple[EnvironmentalReaderInspection, ...] = ()
    forcing_readiness: ForcingReadiness | None = None
    preparation_performed: bool = False
    source_rows: int = 0
    selected_rows: int = 0
    runnable_observations: int = 0
    skipped_observations: int = 0
    planned_model_iterations: int = 0
    planned_particle_trajectories: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return (
            self.preparation_performed
            and self.runnable_observations > 0
            and not any(message.level == "error" for message in self.validation_messages)
            and not any(check.blocks_run for check in self.checks)
        )

    def to_summary(self, request: SimulationRequest) -> SimulationSummary:
        messages = list(self.validation_messages)
        messages.extend(
            ValidationMessage("error", check.detail)
            for check in self.checks
            if check.blocks_run
            and not any(message.text == check.detail for message in messages)
        )
        if self.preparation_performed:
            messages.append(
                ValidationMessage(
                    "info",
                    f"{self.runnable_observations:,} observations are ready for "
                    f"{self.planned_model_iterations:,} model iterations.",
                )
            )
        return SimulationSummary(
            total_records=self.source_rows,
            simulated_records=self.runnable_observations,
            skipped_records=self.skipped_observations,
            output_directory=request.data_sources.output_directory,
            messages=messages,
        )


def run_preflight(
    request: SimulationRequest,
    *,
    validator: SimulationRequestValidator | None = None,
    is_land: LandPredicate | None = None,
    progress: Callable[[int, int, int], None] | None = None,
) -> PreflightResult:
    """Fully inspect one immutable request snapshot without creating run outputs."""
    working_request = deepcopy(request)
    report = progress or (lambda stage, completed, total: None)
    report(0, 0, 0)
    coverage = working_request.settings.coverage
    original_coverage_mode = coverage.mode
    defer_coverage_resolution = (
        original_coverage_mode == "environment_intersection"
        and coverage.buffer_degrees >= 0
    )
    if defer_coverage_resolution:
        coverage.mode = "manual"
    messages = tuple(
        (validator or SimulationRequestValidator()).validate(working_request)
    )
    coverage.mode = original_coverage_mode
    issues = tuple(message for message in messages if message.level != "info")
    checks: list[PreflightCheck] = [
        PreflightCheck(
            key=f"configuration_{index}", level=message.level,
            title="Configuration needs correction" if message.level == "error" else "Configuration warning",
            detail=message.text, target_step=message.target_step or "review_run",
            blocks_run=message.level == "error", subsection=message.subsection,
            field_ids=message.field_ids,
        )
        for index, message in enumerate(issues)
        if message.field_ids != ("output_directory",)
    ]
    if not issues:
        checks.append(_configuration_check(messages))
    checks.append(_output_destination_check(working_request))
    if any(message.level == "error" for message in messages):
        return PreflightResult(checks=tuple(checks), validation_messages=messages)

    inspections: list[EnvironmentalReaderInspection] = []
    inspection_error = False
    unique_paths = list(
        dict.fromkeys(
            reader.path for reader in working_request.data_sources.environment_readers
        )
    )
    report(1, 0, len(unique_paths))
    for index, path in enumerate(unique_paths):
        try:
            inspections.append(environment.inspect_environment_reader(path))
        except (ImportError, OSError, ValueError) as exc:
            inspection_error = True
            checks.append(
                PreflightCheck(
                    key=f"environmental_reader:{path}",
                    level="error",
                    title="Environmental reader",
                    detail=f"Could not inspect `{path.name}`: {exc}",
                    target_step="environmental_forcing",
                    blocks_run=True,
                )
            )
        report(1, index + 1, len(unique_paths))
    coverage_error = False
    if defer_coverage_resolution and not inspection_error:
        try:
            selected_paths = unique_paths
            if coverage.contributing_paths:
                included = {str(path) for path in coverage.contributing_paths}
                selected_paths = [path for path in unique_paths if str(path) in included]
            by_path = {inspection.path: inspection for inspection in inspections}
            extents = []
            for path in selected_paths:
                inspection = by_path[path]
                if inspection.extent is None:
                    detail = inspection.coverage_warning or "coverage is unavailable"
                    raise ValueError(f"Could not use `{path.name}`: {detail}.")
                extents.append(inspection.extent)
            working_request.settings.extent = environment.intersect_extents(
                extents, coverage.buffer_degrees
            )
            coverage.mode = "manual"
        except (KeyError, ValueError) as exc:
            coverage_error = True
            checks.append(
                PreflightCheck(
                    key="environmental_coverage",
                    level="error",
                    title="Environmental coverage",
                    detail=f"Could not resolve shared environmental coverage: {exc}",
                    target_step="environmental_forcing",
                    blocks_run=True,
                )
            )
    checks.append(
        _environment_check(
            inspections, len(unique_paths), inspection_error or coverage_error
        )
    )
    if inspection_error or coverage_error:
        return PreflightResult(
            checks=tuple(checks),
            validation_messages=messages,
            environment_inspections=tuple(inspections),
        )

    report(2, 0, 0)
    try:
        preparation = prepare_observations(working_request, is_land=is_land)
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        checks.append(
            PreflightCheck(
                key="observation_data",
                level="error",
                title="Observation data",
                detail=f"Observations could not be prepared: {exc}",
                target_step="stranding_data",
                blocks_run=True,
            )
        )
        return PreflightResult(
            checks=tuple(checks),
            validation_messages=messages,
            environment_inspections=tuple(inspections),
        )

    report(3, 0, 0)
    runnable = len(preparation.observations)
    planned_iterations = runnable * working_request.settings.iteration_count
    planned_particles = planned_iterations * working_request.settings.particle_count
    checks.append(_observation_check(runnable, preparation.skipped_rows))
    forcing_readiness = None
    if runnable:
        required_start, required_end = _required_forcing_window(
            preparation.observations,
            working_request,
        )
        forcing_readiness = evaluate_forcing_readiness(
            working_request.data_sources.environment_readers,
            inspections,
            study_extent=working_request.settings.extent,
            required_start=required_start,
            required_end=required_end,
            require_wind=any(observation.wind_drift_factor != 0 for observation in preparation.observations),
            fallback_values=working_request.settings.fallback_values,
        )
        checks.extend(
            PreflightCheck(
                key=f"forcing:{check.key}",
                level=check.level,
                title=check.title,
                detail=check.detail,
                target_step="environmental_forcing",
                blocks_run=check.blocks_run,
            )
            for check in forcing_readiness.checks
        )
    checks.append(
        PreflightCheck(
            key="simulation_workload",
            level="success" if runnable else "error",
            title="Simulation workload",
            detail=(
                f"{planned_iterations:,} model iterations and "
                f"{planned_particles:,} particle trajectories are planned."
            ),
            target_step="simulation_setup",
            blocks_run=not runnable,
        )
    )
    report(3, 1, 1)
    return PreflightResult(
        checks=tuple(checks),
        validation_messages=messages,
        environment_inspections=tuple(inspections),
        forcing_readiness=forcing_readiness,
        preparation_performed=True,
        source_rows=preparation.source_rows,
        selected_rows=preparation.selected_rows,
        runnable_observations=runnable,
        skipped_observations=preparation.skipped_rows,
        planned_model_iterations=planned_iterations,
        planned_particle_trajectories=planned_particles,
        skip_reasons=dict(preparation.skip_reasons),
    )


def _required_forcing_window(
    observations: list,
    request: SimulationRequest,
) -> tuple:
    """Use every scheduled scenario start rather than raw observation timestamps."""
    required_start = None
    required_end = None
    output_directory = request.data_sources.output_directory
    assert output_directory is not None
    for observation in observations:
        for iteration in plan_simulation_runs(
            observation,
            request.settings,
            output_directory,
        ):
            candidate_start = iteration.start_time - timedelta(
                days=observation.reverse_drift_duration_days
            )
            if required_start is None or candidate_start < required_start:
                required_start = candidate_start
            if required_end is None or iteration.start_time > required_end:
                required_end = iteration.start_time
    assert required_start is not None and required_end is not None
    return required_start, required_end


def _configuration_check(messages: tuple[ValidationMessage, ...]) -> PreflightCheck:
    errors = sum(message.level == "error" for message in messages)
    warnings = sum(message.level == "warning" for message in messages)
    if errors:
        level: CheckLevel = "error"
        detail = f"Resolve {errors} blocking configuration issue(s) before preflight."
    elif warnings:
        level = "warning"
        detail = f"Configuration has {warnings} warning(s) to review."
    else:
        level = "success"
        detail = "Required paths, mappings, and model settings are valid."
    return PreflightCheck(
        key="configuration",
        level=level,
        title="Configuration",
        detail=detail,
        target_step="review_run",
        blocks_run=bool(errors),
    )


def _output_destination_check(request: SimulationRequest) -> PreflightCheck:
    message = validate_output_destination(request.data_sources.output_directory)
    level: CheckLevel = "success" if message.level == "info" else message.level
    return PreflightCheck(
        key="output_destination",
        level=level,
        title="Output directory",
        detail=message.text,
        target_step="review_run",
        blocks_run=message.level == "error",
        field_ids=("output_directory",),
    )


def _environment_check(
    inspections: list[EnvironmentalReaderInspection],
    expected: int,
    inspection_error: bool,
) -> PreflightCheck:
    warnings = sum(
        diagnostic.level == "warning"
        for inspection in inspections
        for diagnostic in inspection.diagnostics
    )
    if inspection_error:
        level: CheckLevel = "error"
    elif warnings:
        level = "warning"
    else:
        level = "success"
    detail = f"Inspected {len(inspections)} of {expected} unique environmental reader(s)."
    if warnings:
        detail += f" {warnings} metadata warning(s) require review."
    return PreflightCheck(
        key="environmental_forcing",
        level=level,
        title="Environmental forcing",
        detail=detail,
        target_step="environmental_forcing",
        blocks_run=inspection_error,
    )


def _observation_check(runnable: int, skipped: int) -> PreflightCheck:
    if not runnable:
        return PreflightCheck(
            key="observation_data",
            level="error",
            title="Observation data",
            detail="No selected observation can be converted into a runnable model input.",
            target_step="stranding_data",
            blocks_run=True,
        )
    level: CheckLevel = "warning" if skipped else "success"
    detail = f"{runnable:,} observation(s) are runnable."
    if skipped:
        detail += f" {skipped:,} selected observation(s) will be skipped."
    return PreflightCheck(
        key="observation_data",
        level=level,
        title="Observation data",
        detail=detail,
        target_step="stranding_data",
    )
