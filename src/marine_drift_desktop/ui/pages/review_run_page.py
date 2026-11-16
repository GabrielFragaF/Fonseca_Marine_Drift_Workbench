from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.preflight import PreflightCheck, PreflightResult
from ...domain.models import SimulationRequest
from ..components import ActionButton, AnimatedToggle
from ..icons import line_icon
from .base import WorkflowStagePage


class ReviewRunState(str, Enum):
    UNVALIDATED = "unvalidated"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    READY_WITH_WARNINGS = "ready_with_warnings"
    READY = "ready"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunSummaryValues:
    source_rows: int
    selected_rows: int
    valid_rows: int
    scenarios_per_observation: int
    particles_per_release: int
    expected_trajectories: int
    duration: str
    windage: str
    forcing: str
    spatial_extent: str
    observations_evaluated: bool = True

    @classmethod
    def from_request(
        cls, request: SimulationRequest, result: PreflightResult
    ) -> "RunSummaryValues":
        settings = request.settings
        if settings.duration.mode == "fixed":
            duration = f"Fixed, {settings.duration.fixed_days} days"
        elif settings.duration.mode == "dataset":
            duration = "Per observation from dataset"
        else:
            duration = "Estimated from temperature and decomposition"

        windage_labels = {
            "none": "No windage",
            "fixed": f"Fixed, {settings.wind_drift.fixed_percent:g}%",
            "dataset": "Per observation from dataset",
            "measurement": "Estimated from specimen measurement",
        }
        readers = request.data_sources.environment_readers
        roles = sorted({role for reader in readers for role in reader.roles})
        forcing = f"{len(readers)} dataset{'s' if len(readers) != 1 else ''}"
        if roles:
            forcing += " · " + ", ".join(roles)
        extent = settings.extent
        spatial_extent = (
            f"{extent.min_longitude:g}° to {extent.max_longitude:g}° lon; "
            f"{extent.min_latitude:g}° to {extent.max_latitude:g}° lat"
        )
        return cls(
            source_rows=result.source_rows,
            selected_rows=result.selected_rows,
            valid_rows=result.runnable_observations,
            scenarios_per_observation=settings.iteration_count,
            particles_per_release=settings.particle_count,
            expected_trajectories=result.planned_particle_trajectories,
            duration=duration,
            windage=windage_labels.get(settings.wind_drift.mode, "Not configured"),
            forcing=forcing,
            spatial_extent=spatial_extent,
            observations_evaluated=result.preparation_performed,
        )


class ReviewRunPage(WorkflowStagePage):
    """Final project checkpoint with one explicit operational state."""

    workflow_step_requested = Signal(str)
    issue_requested = Signal(object)
    validate_requested = Signal()
    run_requested = Signal()
    cancel_requested = Signal()
    open_results_requested = Signal()
    continue_errors_changed = Signal(bool)
    state_changed = Signal()

    def __init__(self, output_group: QWidget, parent=None) -> None:
        super().__init__(
            "Review & run",
            "Validate the project, confirm the workload, and run simulations locally.",
            step_number="04",
            category="EXECUTION",
            icon_name="review",
            parent=parent,
        )
        self.state = ReviewRunState.UNVALIDATED
        self._compact_layout = False
        self.output_group = output_group
        self.destination_card = self._build_destination_card()
        self.summary_row = self._build_summary_row()
        self.primary_action_card = self._build_primary_action_card()
        self.activity_card = self._build_activity_card()
        self.content_layout.addWidget(self.destination_card)
        self.content_layout.addWidget(self.primary_action_card)
        self.validation_panel = QFrame(self.viewport())
        self.validation_panel.setObjectName("ValidationPanel")
        self.validation_panel.setFixedHeight(310)
        validation_layout = QVBoxLayout(self.validation_panel)
        validation_layout.setContentsMargins(28, 22, 28, 22)
        title = QLabel("Checking your project")
        title.setAlignment(Qt.AlignCenter)
        title.setObjectName("ValidationTitle")
        detail = QLabel("Reading observations, checking environmental coverage and estimating the workload...")
        detail.setAlignment(Qt.AlignCenter)
        detail.setWordWrap(True)
        self.validation_detail = detail
        self.validation_progress = QProgressBar()
        self.validation_progress.setAccessibleName("Project validation in progress")
        self.validation_progress.setRange(0, 0)
        self.validation_progress.setTextVisible(False)
        self.validation_progress.setFixedHeight(10)
        validation_layout.addWidget(title)
        validation_layout.addWidget(detail)
        validation_layout.addSpacing(8)
        validation_layout.addWidget(self.validation_progress)
        self.validation_phases = []
        for phase in ("Configuration", "Environmental datasets", "Observation data", "Coverage and workload"):
            validation_layout.addWidget(QLabel(phase))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            validation_layout.addWidget(bar)
            self.validation_phases.append(bar)
        self.validation_dialog = self._build_validation_dialog()
        self.content_layout.addWidget(self.summary_row)
        self.content_layout.addWidget(self.activity_card)
        self.content_layout.addStretch(1)
        self.set_state(self.state)

    def _build_validation_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setObjectName("ValidationDialog")
        dialog.setWindowTitle("Checking project")
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setWindowFlag(Qt.FramelessWindowHint)
        dialog.setModal(True)
        dialog.setFixedWidth(540)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(30, 26, 30, 26)
        layout.setSpacing(10)
        title = QLabel("Checking your project")
        title.setObjectName("ValidationTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        self.validation_dialog_detail = QLabel("Preparing validation...")
        self.validation_dialog_detail.setAlignment(Qt.AlignCenter)
        self.validation_dialog_detail.setWordWrap(True)
        layout.addWidget(self.validation_dialog_detail)
        self.validation_dialog_progress = QProgressBar()
        self.validation_dialog_progress.setRange(0, 0)
        self.validation_dialog_progress.setTextVisible(False)
        self.validation_dialog_progress.setFixedHeight(10)
        layout.addWidget(self.validation_dialog_progress)
        self.validation_dialog_phases = []
        for phase in ("Configuration", "Environmental datasets", "Observation data", "Coverage and workload"):
            layout.addWidget(QLabel(phase))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(7)
            layout.addWidget(bar)
            self.validation_dialog_phases.append(bar)
        return dialog

    def _build_destination_card(self) -> QGroupBox:
        card = QGroupBox("Run destination")
        card.setObjectName("RunDestinationCard")
        layout = QVBoxLayout(card)
        description = QLabel(
            "Trajectory files, checkpoints, logs, and the reproducibility manifest "
            "will be saved in this local folder."
        )
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        layout.addWidget(description)
        if isinstance(self.output_group, QGroupBox):
            self.output_group.setTitle("")
            self.output_group.setObjectName("DestinationFields")
        layout.addWidget(self.output_group)
        return card

    def _build_summary_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName("ReviewSummaryRow")
        layout = QGridLayout(row)
        self.summary_layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.readiness_card = self._build_readiness_card()
        self.run_summary_card = self._build_run_summary_card()
        self.execution_options_card = self._build_options_card()
        self.summary_cards = (
            self.readiness_card,
            self.run_summary_card,
            self.execution_options_card,
        )
        for column, card in enumerate(self.summary_cards):
            layout.addWidget(card, 0, column)
        layout.setColumnStretch(0, 4)
        layout.setColumnStretch(1, 4)
        layout.setColumnStretch(2, 3)
        return row

    def _build_readiness_card(self) -> QGroupBox:
        card = QGroupBox("Project readiness")
        card.setObjectName("ReadinessCard")
        layout = QVBoxLayout(card)
        self.preview_state = QLabel("Project not validated")
        self.preview_state.setObjectName("PreviewState")
        self.preview_state.setProperty("state", "idle")
        counts = QHBoxLayout()
        self.readiness_blocking_count = QLabel("Not checked")
        self.readiness_warning_count = QLabel("Checks pending")
        counts.addWidget(self.readiness_blocking_count)
        counts.addWidget(self.readiness_warning_count)
        counts.addStretch(1)
        self.readiness_rows = QVBoxLayout()
        self.readiness_rows.setSpacing(6)
        layout.addWidget(self.preview_state)
        layout.addLayout(counts)
        layout.addLayout(self.readiness_rows)
        layout.addStretch(1)
        return card

    def _summary_value(self, title: str) -> tuple[QWidget, QLabel]:
        row = QFrame()
        row.setObjectName("RunSummaryValue")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setSpacing(1)
        heading = QLabel(title)
        heading.setProperty("role", "eyebrow")
        value = QLabel("Validate to calculate")
        value.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(value)
        return row, value

    def _build_run_summary_card(self) -> QGroupBox:
        card = QGroupBox("Run summary")
        card.setObjectName("RunSummaryCard")
        layout = QVBoxLayout(card)
        rows = [
            ("Observations", "observation_summary"),
            ("Scenarios and particles", "trajectory_summary"),
            ("Drift duration", "duration_summary"),
            ("Windage", "windage_summary"),
            ("Environmental forcing", "forcing_summary"),
            ("Study area", "extent_summary"),
        ]
        for title, attribute in rows:
            row, value = self._summary_value(title)
            setattr(self, attribute, value)
            layout.addWidget(row)
        layout.addStretch(1)
        return card

    def _build_options_card(self) -> QGroupBox:
        card = QGroupBox("Execution options")
        card.setObjectName("ExecutionOptionsCard")
        layout = QVBoxLayout(card)
        self.continue_errors_toggle = AnimatedToggle()
        self.continue_errors_toggle.setChecked(True)
        self.continue_errors_toggle.toggled.connect(self.continue_errors_changed.emit)
        option = QHBoxLayout()
        copy = QLabel("Continue past individual simulation errors")
        copy.setWordWrap(True)
        option.addWidget(copy, 1)
        option.addWidget(self.continue_errors_toggle)
        detail = QLabel("Failures are recorded while unaffected simulations continue.")
        detail.setWordWrap(True)
        detail.setProperty("role", "muted")
        layout.addLayout(option)
        layout.addWidget(detail)
        layout.addStretch(1)
        return card

    def _action_button(self, text: str, icon: str, variant: str) -> ActionButton:
        button = ActionButton(text, variant=variant)
        button.setIcon(line_icon(icon, "#ffffff", 18))
        return button

    def _build_primary_action_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PrimaryActionCard")
        layout = QHBoxLayout(card)
        self.primary_state_title = QLabel("Validate before running")
        self.primary_state_title.setObjectName("PrimaryStateTitle")
        self.primary_state_detail = QLabel(
            "Checks confirm that observations, forcing, model settings, and output are ready."
        )
        self.primary_state_detail.setWordWrap(True)
        copy = QVBoxLayout()
        copy.addWidget(self.primary_state_title)
        copy.addWidget(self.primary_state_detail)

        self.validate_button = self._action_button("Validate project", "review", "primary")
        self.run_simulations_button = self._action_button("Run simulations", "run", "primary")
        self.cancel_run_button = self._action_button("Cancel run", "close", "danger")
        self.open_results_button = self._action_button("Open results", "folder", "primary")
        self.validate_button.clicked.connect(self.validate_requested.emit)
        self.run_simulations_button.clicked.connect(self.run_requested.emit)
        self.cancel_run_button.clicked.connect(self.cancel_requested.emit)
        self.open_results_button.clicked.connect(self.open_results_requested.emit)
        self._primary_buttons = (
            self.validate_button,
            self.run_simulations_button,
            self.cancel_run_button,
            self.open_results_button,
        )
        self.inline_validation = QWidget()
        self.inline_validation.setObjectName("InlineValidation")
        inline_layout = QVBoxLayout(self.inline_validation)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(5)
        self.inline_validation_label = QLabel("Preparing validation...")
        self.inline_validation_label.setObjectName("InlineValidationLabel")
        self.inline_validation_progress = QProgressBar()
        self.inline_validation_progress.setObjectName("InlineValidationProgress")
        self.inline_validation_progress.setAccessibleName("Project validation progress")
        self.inline_validation_progress.setRange(0, 0)
        self.inline_validation_progress.setTextVisible(False)
        self.inline_validation_progress.setFixedSize(260, 9)
        inline_layout.addWidget(self.inline_validation_label)
        inline_layout.addWidget(self.inline_validation_progress)
        layout.addLayout(copy, 1)
        layout.addWidget(self.inline_validation)
        for button in self._primary_buttons:
            layout.addWidget(button)
        return card

    def _build_activity_card(self) -> QGroupBox:
        card = QGroupBox("Run activity")
        card.setObjectName("RunActivityCard")
        layout = QVBoxLayout(card)
        self.activity_tabs = QTabWidget()
        progress = QWidget()
        progress_layout = QVBoxLayout(progress)
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 100)
        self.run_progress.setValue(0)
        self.run_progress.setFormat("Waiting")
        self.activity_stage = QLabel("Waiting to start")
        metrics = QGridLayout()
        self.activity_trajectories = QLabel("0 trajectories")
        self.activity_failures = QLabel("0 failed")
        self.activity_elapsed = QLabel("0s elapsed")
        self.activity_batch = QLabel("No active batch")
        metrics.addWidget(self.activity_trajectories, 0, 0)
        metrics.addWidget(self.activity_failures, 0, 1)
        metrics.addWidget(self.activity_elapsed, 1, 0)
        metrics.addWidget(self.activity_batch, 1, 1)
        progress_layout.addWidget(self.activity_stage)
        progress_layout.addWidget(self.run_progress)
        progress_layout.addLayout(metrics)

        self.preview_output = QTextEdit()
        self.preview_output.setObjectName("LogOutput")
        self.preview_output.setReadOnly(True)
        self.preview_output.setMaximumHeight(220)
        self.preview_output.setPlaceholderText(
            "Validation details and technical run messages appear here."
        )
        self.activity_tabs.addTab(progress, "Progress")
        self.activity_tabs.addTab(self.preview_output, "Technical log")
        layout.addWidget(self.activity_tabs)
        return card

    def set_state(self, state: ReviewRunState) -> None:
        self.validation_panel.hide()
        if state != ReviewRunState.VALIDATING and hasattr(self, "validation_dialog"):
            self.validation_dialog.hide()
        self.state = state
        self.inline_validation.setVisible(state == ReviewRunState.VALIDATING)
        for button in self._primary_buttons:
            button.setLoading(False)
        action_by_state = {
            ReviewRunState.UNVALIDATED: self.validate_button,
            ReviewRunState.VALIDATING: self.validate_button,
            ReviewRunState.BLOCKED: self.validate_button,
            ReviewRunState.READY_WITH_WARNINGS: self.run_simulations_button,
            ReviewRunState.READY: self.run_simulations_button,
            ReviewRunState.RUNNING: self.cancel_run_button,
            ReviewRunState.CANCELLING: self.cancel_run_button,
            ReviewRunState.COMPLETED: self.open_results_button,
            ReviewRunState.COMPLETED_WITH_ERRORS: self.open_results_button,
            ReviewRunState.FAILED: self.validate_button,
        }
        active = action_by_state[state]
        for button in self._primary_buttons:
            button.setVisible(button is active)
            button.setEnabled(button is active)
        if state == ReviewRunState.VALIDATING:
            active.setLoading(True, "Validating...")
        elif state == ReviewRunState.CANCELLING:
            active.setLoading(True, "Stopping...")

        titles = {
            ReviewRunState.UNVALIDATED: ("Validate before running", "Run readiness has not been checked."),
            ReviewRunState.VALIDATING: ("Checking project readiness", "Observation and environmental metadata are being inspected."),
            ReviewRunState.BLOCKED: ("Resolve blocking checks", "Correct the affected workflow steps, then validate again."),
            ReviewRunState.READY_WITH_WARNINGS: ("Ready with warnings", "Review the warnings or run with the current assumptions."),
            ReviewRunState.READY: ("Ready to run", "The validated request will run locally in seamless batches."),
            ReviewRunState.RUNNING: ("Simulations are running", "Completed outputs are checkpointed as work progresses."),
            ReviewRunState.CANCELLING: ("Stopping safely", "Finished outputs are retained while the worker shuts down."),
            ReviewRunState.COMPLETED: ("Run complete", "Open the result folder and reproducibility manifest."),
            ReviewRunState.COMPLETED_WITH_ERRORS: ("Completed with warnings", "Successful outputs are available; review the recorded failures."),
            ReviewRunState.FAILED: ("Run interrupted", "Review the technical log, correct the issue, and validate again."),
        }
        title, detail = titles[state]
        self.primary_state_title.setText(title)
        self.primary_state_detail.setText(detail)
        self.preview_state.setText(title)
        semantic = (
            "ready" if state in {ReviewRunState.READY, ReviewRunState.COMPLETED}
            else "attention" if state in {ReviewRunState.BLOCKED, ReviewRunState.COMPLETED_WITH_ERRORS, ReviewRunState.FAILED}
            else "running" if state in {ReviewRunState.VALIDATING, ReviewRunState.RUNNING, ReviewRunState.CANCELLING}
            else "idle"
        )
        self.preview_state.setProperty("state", semantic)
        action_semantic = (
            "error" if state in {ReviewRunState.BLOCKED, ReviewRunState.FAILED}
            else "warning" if state in {
                ReviewRunState.READY_WITH_WARNINGS,
                ReviewRunState.COMPLETED_WITH_ERRORS,
            }
            else "ready" if state in {
                ReviewRunState.READY,
                ReviewRunState.COMPLETED,
            }
            else "running" if state in {
                ReviewRunState.VALIDATING,
                ReviewRunState.RUNNING,
                ReviewRunState.CANCELLING,
            }
            else "idle"
        )
        self.primary_action_card.setProperty("state", action_semantic)
        self.primary_action_card.style().unpolish(self.primary_action_card)
        self.primary_action_card.style().polish(self.primary_action_card)
        running = state in {ReviewRunState.RUNNING, ReviewRunState.CANCELLING}
        self.output_group.setEnabled(not running)
        self.continue_errors_toggle.setEnabled(not running)
        activity_visible = state not in {
            ReviewRunState.UNVALIDATED,
            ReviewRunState.VALIDATING,
            ReviewRunState.BLOCKED,
            ReviewRunState.READY,
            ReviewRunState.READY_WITH_WARNINGS,
        }
        self.activity_card.setVisible(activity_visible)
        self.content_layout.removeWidget(self.activity_card)
        self.content_layout.removeWidget(self.summary_row)
        if activity_visible:
            self.content_layout.insertWidget(4, self.activity_card)
            self.content_layout.insertWidget(5, self.summary_row)
        else:
            self.content_layout.insertWidget(4, self.summary_row)
            self.content_layout.insertWidget(5, self.activity_card)
        if state == ReviewRunState.VALIDATING:
            self.inline_validation_label.setText("Checking configuration...")
            self.inline_validation_progress.setRange(0, 0)
            for bar in self.validation_phases:
                bar.setRange(0, 100)
                bar.setValue(0)
            for bar in self.validation_dialog_phases:
                bar.setRange(0, 100)
                bar.setValue(0)
        self.state_changed.emit()

    def update_validation_progress(self, stage: int, completed: int, total: int) -> None:
        names = ("Checking configuration", "Inspecting environmental datasets", "Preparing observation data", "Checking coverage and workload")
        self.validation_detail.setText(names[stage])
        self.validation_dialog_detail.setText(names[stage])
        self.inline_validation_label.setText(names[stage] + "...")
        self.validation_progress.setRange(0, 100)
        self.validation_dialog_progress.setRange(0, 100)
        phase_progress = int(100 * completed / total) if total else 25
        overall = min(99, stage * 25 + phase_progress // 4)
        self.validation_progress.setValue(overall)
        self.validation_dialog_progress.setValue(overall)
        self.inline_validation_progress.setRange(0, 100)
        self.inline_validation_progress.setValue(overall)
        for index, (bar, dialog_bar) in enumerate(zip(self.validation_phases, self.validation_dialog_phases)):
            bar.setRange(0, 0 if index == stage and not total else 100)
            bar.setValue(100 if index < stage else int(100 * completed / total) if index == stage and total else 0)
            dialog_bar.setRange(0, 0 if index == stage and not total else 100)
            dialog_bar.setValue(100 if index < stage else int(100 * completed / total) if index == stage and total else 0)

    def show_validation_overlay(self) -> None:
        self.inline_validation.show()

    def _reveal_validation(self):
        if self.state == ReviewRunState.VALIDATING:
            self.show_validation_overlay()

    def _position_validation_panel(self) -> None:
        viewport_rect = self.viewport().rect()
        width = max(280, min(560, viewport_rect.width() - 32))
        self.validation_panel.setFixedWidth(width)
        self.validation_panel.move(
            viewport_rect.center().x() - width // 2,
            viewport_rect.center().y() - self.validation_panel.height() // 2,
        )

    def set_compact_layout(self, compact: bool) -> None:
        if compact == self._compact_layout and self.summary_layout.count() == 3:
            return
        self._compact_layout = compact
        for card in self.summary_cards:
            self.summary_layout.removeWidget(card)
        for index, card in enumerate(self.summary_cards):
            row, column = (index, 0) if compact else (0, index)
            self.summary_layout.addWidget(card, row, column)
        for column, stretch in enumerate((4, 4, 3)):
            self.summary_layout.setColumnStretch(
                column, 0 if compact and column else stretch
            )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_compact_layout(event.size().width() < 1_000)
        self._position_validation_panel()

    def set_readiness(self, checks: Iterable[PreflightCheck]) -> None:
        while self.readiness_rows.count():
            item = self.readiness_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        check_list = tuple(checks)
        blocking = sum(check.blocks_run for check in check_list)
        warnings = sum(check.level == "warning" for check in check_list)
        self.readiness_blocking_count.setText(f"{blocking} blocking")
        self.readiness_warning_count.setText(
            f"{warnings} warning{'s' if warnings != 1 else ''}"
        )
        priority = {"error": 0, "warning": 1, "info": 2, "success": 3}
        for check in sorted(check_list, key=lambda check: priority[check.level]):
            row = QFrame()
            row.setObjectName("ReadinessRow")
            row.setProperty("severity", check.level)
            row.setProperty("targetStep", check.target_step)
            layout = QVBoxLayout(row)
            layout.setContentsMargins(8, 6, 8, 6)
            title = QLabel(check.title)
            title.setProperty("role", "readiness-title")
            detail = QLabel(check.detail)
            detail.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(detail)
            if check.level in {"error", "warning"}:
                step_names = {"stranding_data": "Stranding data", "environmental_forcing": "Environmental forcing",
                              "simulation_setup": "Simulation setup", "review_run": "Review & run"}
                location = step_names.get(check.target_step, "Review & run")
                if check.subsection is not None:
                    sections = ("Study area", "Observations", "Drift duration", "Windage", "Particle release", "Model physics")
                    location += " / " + sections[check.subsection]
                where = QLabel(location)
                where.setWordWrap(True)
                where.setProperty("role", "muted")
                layout.addWidget(where)
                action = ActionButton("Go to correction" if check.blocks_run else "Review warning", variant="secondary")
                action.clicked.connect(lambda checked=False, issue=check: self.issue_requested.emit(issue))
                layout.addWidget(action)
            self.readiness_rows.addWidget(row)

    def set_run_summary(self, summary: RunSummaryValues) -> None:
        self.observation_summary.setText(
            f"{summary.valid_rows:,} runnable of {summary.selected_rows:,} selected "
            f"({summary.source_rows:,} source rows)"
            if summary.observations_evaluated else
            "Not evaluated yet. Resolve configuration errors, then validate again."
        )
        self.trajectory_summary.setText(
            f"{summary.scenarios_per_observation:,} scenarios · "
            f"{summary.particles_per_release:,} particles · "
            f"{summary.expected_trajectories:,} expected trajectories"
            if summary.observations_evaluated else
            f"{summary.scenarios_per_observation:,} scenarios / {summary.particles_per_release:,} particles per start. Workload not evaluated yet."
        )
        self.duration_summary.setText(summary.duration)
        self.windage_summary.setText(summary.windage)
        self.forcing_summary.setText(summary.forcing)
        self.extent_summary.setText(summary.spatial_extent)

    def reset_run_summary(self, text: str = "Validate to calculate") -> None:
        for label in (
            self.observation_summary,
            self.trajectory_summary,
            self.duration_summary,
            self.windage_summary,
            self.forcing_summary,
            self.extent_summary,
        ):
            label.setText(text)

    def update_activity(self, event: Mapping[str, Any]) -> None:
        event_name = str(event.get("event", ""))
        total = int(event.get("total_jobs", 0))
        processed = int(event.get("processed", event.get("resume_index", 0)))
        if event_name == "finished" and "processed" not in event:
            processed = total
        if total:
            self.run_progress.setRange(0, total)
            self.run_progress.setValue(min(processed, total))
            self.run_progress.setFormat("%v of %m trajectories")
            self.activity_trajectories.setText(
                f"{processed:,} of {total:,} trajectories"
                + (f" ({int(event['existing']):,} kept from previous runs)" if event.get("existing") else "")
            )
        failed = int(event.get("failed", 0))
        self.activity_failures.setText(f"{failed:,} failed")
        elapsed = float(event.get("elapsed_seconds", 0.0))
        self.activity_elapsed.setText(f"{elapsed:.0f}s elapsed")
        batch = int(event.get("batch", 0))
        self.activity_batch.setText(f"Batch {batch}" if batch else "Preparing workload")
        stages = {
            "workload": "Workload prepared",
            "batch_started": "Running simulations",
            "progress": "Writing trajectories",
            "batch_completed": "Batch checkpoint saved",
            "finished": "Run complete",
            "fatal": "Run failed",
        }
        if event_name in stages:
            self.activity_stage.setText(stages[event_name])
