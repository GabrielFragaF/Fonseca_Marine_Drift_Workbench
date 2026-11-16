from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QProgressBar, QSpinBox, QVBoxLayout,
)

from ..components import ActionButton, AnimatedToggle
from ..icons import line_icon
from ..trajectory_map import TrajectoryMapCard
from .base import WorkflowStagePage


class ResultsExportState(str, Enum):
    UNINSPECTED = "uninspected"
    INSPECTING = "inspecting"
    READY = "ready"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class ResultsExportPage(WorkflowStagePage):
    inspect_requested = Signal()
    export_requested = Signal()
    cancel_requested = Signal()
    browse_results_requested = Signal()
    browse_output_requested = Signal()
    open_output_requested = Signal()
    configuration_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Results & export",
            "Sample likely origin positions from completed trajectories and create analysis-ready tables.",
            step_number="05", category="POST-PROCESSING", icon_name="output", parent=parent,
        )
        self.state = ResultsExportState.UNINSPECTED
        self.latest_run_directory: Path | None = None
        self.results_directory = QLineEdit()
        self.results_directory.setPlaceholderText("Choose a folder containing completed NetCDF trajectories")
        self.output_directory = QLineEdit()
        self.output_directory.setPlaceholderText("Choose where exported tables will be saved")
        self.positions_per_day = QSpinBox()
        self.positions_per_day.setRange(1, 10_000)
        self.positions_per_day.setValue(1)
        self.positions_per_day.setSuffix(" position/day")
        self.parquet_toggle = AnimatedToggle("Parquet (canonical table)")
        self.parquet_toggle.setChecked(True)
        self.parquet_toggle.setEnabled(False)
        self.csv_toggle = AnimatedToggle("CSV copy")
        self.xlsx_toggle = AnimatedToggle("Excel copy")
        self.environment_variable_checks: dict[str, QCheckBox] = {}
        self._build_content()
        self.results_directory.textChanged.connect(self._changed)
        self.output_directory.textChanged.connect(lambda _text: self.configuration_changed.emit())
        self.positions_per_day.valueChanged.connect(self._changed)
        self.csv_toggle.toggled.connect(lambda _checked: self.configuration_changed.emit())
        self.xlsx_toggle.toggled.connect(lambda _checked: self.configuration_changed.emit())
        self.set_state(self.state)

    def _build_content(self) -> None:
        grid = QGridLayout()
        grid.setSpacing(12)
        source = QGroupBox("Source results")
        self.source_card = source
        source.setObjectName("ResultsSourceCard")
        source_layout = QVBoxLayout(source)
        source_layout.addWidget(self._muted("Use the latest completed run or inspect any compatible results folder."))
        source_row = QHBoxLayout()
        source_row.addWidget(self.results_directory, 1)
        browse = ActionButton("Browse", variant="secondary")
        browse.setIcon(line_icon("folder", "#176579", 18))
        browse.clicked.connect(self.browse_results_requested.emit)
        source_row.addWidget(browse)
        source_layout.addLayout(source_row)
        self.latest_run_label = self._muted("No completed run has been detected in this session.")
        source_layout.addWidget(self.latest_run_label)

        sampling = QGroupBox("Position sampling")
        self.sampling_card = sampling
        sampling.setObjectName("ResultsSamplingCard")
        sampling_layout = QVBoxLayout(sampling)
        sampling_layout.addWidget(QLabel("Positions per drift day, per simulation"))
        sampling_layout.addWidget(self.positions_per_day)
        sampling_layout.addWidget(self._muted("The available maximum is calculated from the trajectory output interval."))
        self.capacity_label = QLabel("Inspect results to calculate sampling capacity.")
        self.capacity_label.setProperty("role", "info-banner")
        self.capacity_label.setWordWrap(True)
        sampling_layout.addWidget(self.capacity_label)

        formats = QGroupBox("Export formats")
        self.formats_card = formats
        formats.setObjectName("ResultsFormatsCard")
        formats_layout = QVBoxLayout(formats)
        formats_layout.addWidget(self._muted("The weighted Parquet table is created first. Optional copies are derived from it."))
        formats_layout.addWidget(self.parquet_toggle)
        formats_layout.addWidget(self.csv_toggle)
        formats_layout.addWidget(self.xlsx_toggle)
        self.environment_fields_group = QGroupBox("Environmental columns")
        self.environment_fields_layout = QVBoxLayout(self.environment_fields_group)
        self.environment_fields_note = self._muted(
            "Inspect results to see environmental values stored in the trajectories."
        )
        self.environment_fields_layout.addWidget(self.environment_fields_note)
        formats_layout.addWidget(self.environment_fields_group)

        activity = QGroupBox("Export activity")
        self.activity_card = activity
        activity.setObjectName("ResultsActivityCard")
        activity_layout = QVBoxLayout(activity)
        self.status_title = QLabel("Results not inspected")
        self.status_title.setObjectName("ResultsStatusTitle")
        self.status_detail = self._muted("Select a results folder, then inspect it before exporting.")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.output_directory, 1)
        output_browse = ActionButton("Export to...", variant="secondary")
        output_browse.clicked.connect(self.browse_output_requested.emit)
        destination_row.addWidget(output_browse)
        actions = QHBoxLayout()
        follow_up_actions = QHBoxLayout()
        self.inspect_button = ActionButton("Inspect results", variant="secondary")
        self.inspect_button.setIcon(line_icon("search", "#176579", 18))
        self.export_button = ActionButton("Export positions", variant="primary")
        self.export_button.setIcon(line_icon("output", "#ffffff", 18))
        self.cancel_button = ActionButton("Cancel", variant="danger")
        self.open_button = ActionButton("Open export folder", variant="secondary")
        self.inspect_button.clicked.connect(self.inspect_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.open_button.clicked.connect(self.open_output_requested.emit)
        actions.addWidget(self.inspect_button)
        actions.addStretch(1)
        actions.addWidget(self.export_button)
        follow_up_actions.addStretch(1)
        follow_up_actions.addWidget(self.cancel_button)
        follow_up_actions.addWidget(self.open_button)
        activity_layout.addWidget(self.status_title)
        activity_layout.addWidget(self.status_detail)
        activity_layout.addWidget(self.progress)
        activity_layout.addWidget(QLabel("Save tables to"))
        activity_layout.addLayout(destination_row)
        activity_layout.addLayout(actions)
        activity_layout.addLayout(follow_up_actions)

        self._cards_grid = grid
        self._cards = (source, sampling, formats, activity)
        self._compact_layout = None
        self.content_layout.addLayout(grid)
        self.trajectory_map = TrajectoryMapCard(self.results_directory, self.output_directory)
        self.content_layout.addWidget(self.trajectory_map)
        self.content_layout.addStretch(1)
        self._arrange_cards()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_cards_grid"):
            self._arrange_cards()

    def _arrange_cards(self) -> None:
        compact = self.viewport().width() < 1000
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        for card in self._cards:
            self._cards_grid.removeWidget(card)
        for index, card in enumerate(self._cards):
            row, column = (index, 0) if compact else divmod(index, 2)
            self._cards_grid.addWidget(card, row, column, Qt.AlignTop)
        self._cards_grid.setColumnStretch(0, 1)
        self._cards_grid.setColumnStretch(1, 0 if compact else 1)

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("role", "muted")
        return label

    def _changed(self, *_: object) -> None:
        self.mark_inspection_dirty()
        self.configuration_changed.emit()

    def set_latest_run(self, directory: Path | None) -> None:
        self.latest_run_directory = directory
        if directory is None:
            self.latest_run_label.setText("No completed run has been detected in this session.")
            return
        self.latest_run_label.setText(f"Latest completed run: {directory}")
        self.results_directory.setText(str(directory))
        if not self.output_directory.text().strip():
            self.output_directory.setText(str(directory / "exports"))

    def mark_inspection_dirty(self) -> None:
        if self.state not in {ResultsExportState.INSPECTING, ResultsExportState.EXPORTING}:
            self.set_state(ResultsExportState.UNINSPECTED)

    def apply_inspection(self, event: dict[str, object]) -> None:
        maximum = int(event.get("max_positions_per_drift_day", 0) or 0)
        if maximum > 0:
            self.positions_per_day.setMaximum(maximum)
        rows = int(event.get("estimated_rows", 0) or 0)
        files = int(event.get("accepted_file_count", 0) or 0)
        particles = int(event.get("particle_trajectory_count", 0) or 0)
        self.capacity_label.setText(
            f"{files:,} compatible files · {particles:,} particle trajectories · "
            f"up to {maximum:,} positions/day · about {rows:,} export rows"
        )
        self._set_environmental_variables(
            list(event.get("environmental_variables", []) or [])
        )
        issues = event.get("issues", [])
        self.status_detail.setText(
            "Compatible trajectory metadata loaded. Review the estimate and export formats."
            if not issues else f"Metadata loaded with {len(issues)} notice(s). Export remains available."
        )
        self.set_state(ResultsExportState.READY if files else ResultsExportState.FAILED)

    def _set_environmental_variables(self, variables: list[object]) -> None:
        for checkbox in self.environment_variable_checks.values():
            self.environment_fields_layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self.environment_variable_checks.clear()
        self.environment_fields_note.setVisible(not variables)
        if not variables:
            self.environment_fields_note.setText(
                "No environmental values were stored in this run. Rerun with trajectory environmental values enabled."
            )
            return
        for item in variables:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            availability = str(item.get("availability", "partial"))
            units = str(item.get("units", ""))
            text = str(item.get("label", name))
            if units:
                text += f" ({units})"
            if availability == "partial":
                text += " - partial"
            checkbox = QCheckBox(text)
            checkbox.setChecked(availability == "common")
            checkbox.toggled.connect(lambda _checked: self.configuration_changed.emit())
            self.environment_variable_checks[name] = checkbox
            self.environment_fields_layout.addWidget(checkbox)

    def selected_environmental_variables(self) -> list[str]:
        return [
            name for name, checkbox in self.environment_variable_checks.items()
            if checkbox.isChecked()
        ]

    def apply_progress(self, event: dict[str, object]) -> None:
        completed = int(event.get("completed", event.get("processed_files", event.get("files", 0))) or 0)
        total = int(event.get("total", event.get("total_files", 0)) or 0)
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(completed)
            self.progress.setFormat(f"{completed:,} of {total:,} files")
        else:
            self.progress.setRange(0, 0)
        message = event.get("message")
        if message:
            self.status_detail.setText(str(message))
        elif event.get("stage"):
            stage = str(event["stage"]).replace("_", " ").capitalize()
            rows = int(event.get("rows", 0) or 0)
            self.status_detail.setText(f"{stage} · {completed:,} files · {rows:,} rows")

    def apply_failure(self, message: str) -> None:
        self.status_detail.setText(message)
        self.set_state(ResultsExportState.FAILED)

    def apply_completion(self, event: dict[str, object]) -> None:
        warnings = list(event.get("warnings", []) or [])
        rows = int(event.get("row_count", 0) or 0)
        self.status_detail.setText(
            f"Created {rows:,} weighted mortality-position rows. "
            + (f"{len(warnings)} warning(s) were recorded." if warnings else "All requested files were created.")
        )
        self.set_state(ResultsExportState.COMPLETED_WITH_WARNINGS if warnings else ResultsExportState.COMPLETED)

    def set_state(self, state: ResultsExportState) -> None:
        self.state = state
        busy = state in {ResultsExportState.INSPECTING, ResultsExportState.EXPORTING}
        ready = state == ResultsExportState.READY
        completed = state in {ResultsExportState.COMPLETED, ResultsExportState.COMPLETED_WITH_WARNINGS}
        titles = {
            ResultsExportState.UNINSPECTED: "Results not inspected",
            ResultsExportState.INSPECTING: "Inspecting trajectory metadata",
            ResultsExportState.READY: "Ready to export",
            ResultsExportState.EXPORTING: "Creating weighted position table",
            ResultsExportState.COMPLETED: "Export complete",
            ResultsExportState.COMPLETED_WITH_WARNINGS: "Export complete with notices",
            ResultsExportState.FAILED: "Action needs attention",
        }
        self.status_title.setText(titles[state])
        self.inspect_button.setEnabled(not busy and bool(self.results_directory.text().strip()))
        self.export_button.setEnabled(ready)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.open_button.setVisible(completed)
        self.progress.setVisible(busy)
        self.results_directory.setEnabled(not busy)
        self.output_directory.setEnabled(not busy)
        self.positions_per_day.setEnabled(not busy)
        self.csv_toggle.setEnabled(not busy)
        self.xlsx_toggle.setEnabled(not busy)
        self.trajectory_map.set_external_busy(busy)
