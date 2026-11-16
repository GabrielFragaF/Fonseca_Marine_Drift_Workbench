from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..components import (
    ActionButton,
    AnimatedComboBox,
    AnimatedStackedWidget,
    AnimatedToggle,
    SearchableColumnComboBox,
    CompactDoubleSpinBox,
)
from ..icons import line_icon
from ..area_map import StudyAreaMap
from ...core.environment_export import ENVIRONMENT_EXPORT_CATALOGUE
from .base import WorkflowStagePage


class _SetupFilterRowsLayout(QVBoxLayout):
    """Keep dynamically supplied filter rows in the setup page's single-column flow."""

    def addWidget(self, widget: QWidget, *args) -> None:
        layout = widget.layout()
        if isinstance(layout, QBoxLayout):
            layout.setDirection(QBoxLayout.TopToBottom)
            for index in range(layout.count()):
                layout.setStretch(index, 0)
                field = layout.itemAt(index).widget()
                if isinstance(field, QComboBox):
                    field.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                    field.setMinimumContentsLength(18)
                elif isinstance(field, ActionButton):
                    layout.setAlignment(field, Qt.AlignLeft)
        super().addWidget(widget, *args)


class SimulationSetupPage(WorkflowStagePage):
    """Spatial, biological, release, and model-physics configuration controls."""

    setup_finished = Signal()

    STEP_TITLES = (
        "Study area",
        "Observations",
        "Drift duration",
        "Windage",
        "Particle release",
        "Model physics",
    )
    STEP_STATES = {"not_started", "incomplete", "valid", "warning", "error"}

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Simulation setup",
            "Define the spatial extent, biological assumptions, release design, and model physics.",
            step_number="03",
            category="MODEL DESIGN",
            icon_name="setup",
            parent=parent,
        )

        self._build_study_area()
        self._build_environmental_coverage()
        self.study_area_group.layout().addWidget(self.coverage_group, 1, 0, 1, 4)
        self.coverage_toggle.toggled.connect(self._update_area_panels)
        self._update_area_panels()
        self._build_initial_position()
        self._build_observation_selection()
        self._build_duration()
        self._build_windage()
        self._build_release_and_physics()

        self.current_step_index = 0
        self.step_states = {index: "not_started" for index in range(6)}
        self.content_layout.addWidget(self._build_model_builder(), 1)
        self._connect_builder_updates()
        self._update_duration_panels()
        self._update_windage_panels()
        self._update_release_panels()
        self._update_uncertainty_panels()
        self._update_summaries()

    def _build_study_area(self) -> None:
        self.study_area_group = QGroupBox("Spatial extent")
        layout = QGridLayout(self.study_area_group)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        self.study_area_preset = AnimatedComboBox()
        self.study_area_preset.addItem(
            "Environmental reader coverage (recommended)", "environment_intersection"
        )
        self.study_area_preset.addItem("Define extent manually", "manual")
        self.min_lon = self._float_box(-180.0, 180.0, -180.0)
        self.max_lon = self._float_box(-180.0, 180.0, 180.0)
        self.min_lat = self._float_box(-90.0, 90.0, -90.0)
        self.max_lat = self._float_box(-90.0, 90.0, 90.0)
        self._add_form_field(layout, 0, "Study area source", self.study_area_preset)
        self.manual_extent_panel = QFrame()
        manual_layout = QGridLayout(self.manual_extent_panel)
        manual_layout.setContentsMargins(0, 0, 0, 0)
        self._add_field_pair(
            manual_layout, 0, "Min longitude", self.min_lon, "Max longitude", self.max_lon
        )
        self._add_field_pair(
            manual_layout, 1, "Min latitude", self.min_lat, "Max latitude", self.max_lat
        )
        layout.addWidget(self.manual_extent_panel, 2, 0, 1, 4)
        self.area_map = StudyAreaMap()
        layout.addWidget(self.area_map, 3, 0, 1, 4)
        hint = QLabel("Zoom changes the preview only, not the simulation area. Fit study area follows coordinate edits.\nOffline overview coastlines; not a landmask or forcing-coverage check.")
        hint.setWordWrap(True)
        hint.setProperty("role", "field-hint")
        layout.addWidget(hint, 4, 0, 1, 4)
        for field in (self.min_lon, self.max_lon, self.min_lat, self.max_lat):
            field.valueChanged.connect(self._refresh_area_map)
            field.setSuffix(" deg")

    def _refresh_area_map(self, *_):
        self.area_map.set_bounds(self.min_lon.value(), self.max_lon.value(),
                                 self.min_lat.value(), self.max_lat.value())

    def _update_area_panels(self, *_):
        derived = self.coverage_toggle.isChecked()
        self.coverage_group.setVisible(derived)
        self.manual_extent_panel.setVisible(not derived)

    def _build_environmental_coverage(self) -> None:
        self.coverage_group = QGroupBox("Environmental coverage")
        layout = QGridLayout(self.coverage_group)
        layout.setColumnStretch(1, 1)
        self.coverage_toggle = AnimatedToggle(
            "Derive the simulation area from overlapping environmental files"
        )
        self.coverage_toggle.setChecked(True)
        self.coverage_toggle.setVisible(False)
        self.coverage_buffer = self._float_box(0.0, 30.0, 0.0)
        self.coverage_buffer.setSuffix(" deg")
        self.coverage_status = QLabel(
            "Detect and apply environmental overlap to preview the modelling area."
        )
        self.coverage_status.setWordWrap(True)
        self.coverage_status.setProperty("role", "muted")
        self.apply_detected_extent_button = ActionButton(
            "Detect and apply coverage", variant="secondary"
        )
        self.apply_detected_extent_button.setIcon(line_icon("search", "#0b2e43", 17))
        layout.addWidget(self.coverage_toggle, 0, 0, 1, 2)
        self._add_form_field(layout, 1, "Outward buffer", self.coverage_buffer, span=2)
        layout.addWidget(self.coverage_status, 2, 0, 1, 2)
        layout.addWidget(self.apply_detected_extent_button, 3, 0, 1, 2)

    def _build_initial_position(self) -> None:
        self.initial_position_group = QGroupBox("Initial position")
        layout = QVBoxLayout(self.initial_position_group)
        self.position_search_toggle = AnimatedToggle(
            "Search nearby water for observations on land"
        )
        copy = QLabel(
            "When disabled, the recorded coordinates are seeded directly. Enable this "
            "for coastal observations that may fall on the landmask."
        )
        copy.setWordWrap(True)
        copy.setProperty("role", "muted")
        self.position_search_advanced = QFrame()
        grid = QGridLayout(self.position_search_advanced)
        grid.setContentsMargins(0, 8, 0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.position_radial_step = self._float_box(0.0001, 10.0, 0.01)
        self.position_max_radius = self._float_box(0.0001, 30.0, 0.5)
        self.position_radial_step.setSuffix(" deg")
        self.position_max_radius.setSuffix(" deg")
        self.position_angle_step = QSpinBox()
        self.position_angle_step.setRange(1, 360)
        self.position_angle_step.setValue(10)
        self.position_angle_step.setSuffix(" deg")
        self.position_max_attempts = QSpinBox()
        self.position_max_attempts.setRange(1, 1_000_000)
        self.position_max_attempts.setValue(5000)
        self.position_failure_behavior = AnimatedComboBox()
        self.position_failure_behavior.addItem(
            "Skip this observation and continue", "skip"
        )
        self.position_failure_behavior.addItem(
            "Stop the run and report the observation", "stop"
        )
        self._add_field_pair(
            grid,
            0,
            "Radial step",
            self.position_radial_step,
            "Maximum radius",
            self.position_max_radius,
        )
        self._add_field_pair(
            grid,
            1,
            "Angular spacing",
            self.position_angle_step,
            "Maximum search attempts",
            self.position_max_attempts,
        )
        self._add_form_field(grid, 2, "If no water point is found", self.position_failure_behavior)
        layout.addWidget(self.position_search_toggle)
        layout.addWidget(copy)
        self.position_direct_policy = AnimatedComboBox()
        self.position_direct_policy.setAccessibleName("Initial position policy without nearby-water search")
        self.position_direct_policy.addItem("Use recorded positions", "direct")
        self.position_direct_policy.addItem("Skip observations whose positions are on land", "skip_if_invalid")
        self.position_direct_policy.currentIndexChanged.connect(self._update_summaries)
        layout.addWidget(self.position_direct_policy)
        layout.addWidget(self.position_search_advanced)

    def _build_observation_selection(self) -> None:
        self.selection_group = QGroupBox("Observations to simulate")
        layout = QVBoxLayout(self.selection_group)
        intro = QLabel(
            "Run every valid row, draw a reproducible random sample, or keep rows "
            "that match one or more dataset conditions."
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        self.selection_mode = AnimatedComboBox()
        self.selection_mode.addItem("All valid observations", "all")
        self.selection_mode.addItem("Reproducible random sample", "random")
        self.selection_mode.addItem("Rows matching conditions", "filter")

        self.selection_random_panel = QFrame()
        random_layout = QGridLayout(self.selection_random_panel)
        random_layout.setContentsMargins(0, 8, 0, 0)
        self.selection_sample_size = QSpinBox()
        self.selection_sample_size.setRange(1, 10_000_000)
        self.selection_sample_size.setValue(100)
        self.selection_random_seed = QSpinBox()
        self.selection_random_seed.setRange(0, 2_147_483_647)
        self.selection_random_seed.setValue(42)
        self._add_field_pair(
            random_layout,
            0,
            "Number of observations",
            self.selection_sample_size,
            "Random seed",
            self.selection_random_seed,
        )

        self.selection_filter_panel = QFrame()
        filter_layout = QVBoxLayout(self.selection_filter_panel)
        filter_layout.setContentsMargins(0, 8, 0, 0)
        self.filter_rows_layout = _SetupFilterRowsLayout()
        self.filter_condition_rows: list[object] = []
        self.add_filter_condition_button = ActionButton(
            "Add condition", variant="secondary"
        )
        self.add_filter_condition_button.setIcon(line_icon("add", "#0b2e43", 16))
        filter_layout.addLayout(self.filter_rows_layout)
        filter_layout.addWidget(self.add_filter_condition_button, 0, Qt.AlignLeft)
        self.selection_count_label = QLabel(
            "Selection is evaluated when the configuration is checked."
        )
        self.selection_count_label.setProperty("role", "muted")
        self.selection_count_label.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self.selection_mode)
        layout.addWidget(self.selection_random_panel)
        layout.addWidget(self.selection_filter_panel)
        layout.addWidget(self.selection_count_label)

    def _build_duration(self) -> None:
        self.sst_column = self._column_selector("Select SST column")
        self.duration_group = QGroupBox("Drift duration")
        layout = QGridLayout(self.duration_group)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(1, 1)
        self.duration_mode = AnimatedComboBox()
        self.duration_mode.addItem("Use one duration for all observations", "fixed")
        self.duration_mode.addItem(
            "Estimate from SST and decomposition state", "estimated"
        )
        self.duration_mode.addItem("Read duration from a dataset column", "dataset")
        self.duration_mode.setCurrentIndex(self.duration_mode.findData("estimated"))
        self.fixed_duration_days = QSpinBox()
        self.fixed_duration_days.setRange(1, 3650)
        self.fixed_duration_days.setValue(7)
        self.fixed_duration_days.setSuffix(" days")
        self.duration_column = self._column_selector("Select duration column")
        self.duration_threshold = self._float_box(-5.0, 50.0, 24.0)
        self.duration_threshold.setSuffix(" °C")
        self.duration_boundaries = [24.0]
        self.temperature_boundary_fields = [self.duration_threshold]
        self.temperature_boundaries_container = QFrame()
        self.temperature_boundaries_layout = QVBoxLayout(self.temperature_boundaries_container)
        self.temperature_boundaries_layout.setContentsMargins(0, 0, 0, 0)
        self.temperature_boundaries_layout.addWidget(self.duration_threshold)
        self.duration_threshold.valueChanged.connect(
            lambda value, field=self.duration_threshold: self._boundary_edited(field, value)
        )
        self.duration_table = QTableWidget(5, 4)
        self.duration_table.setMaximumHeight(205)
        self.duration_table.setMinimumHeight(190)
        self.duration_table.setMinimumWidth(0)
        self.duration_table.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.duration_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.duration_table.verticalHeader().setVisible(False)
        self.duration_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.duration_table.setHorizontalHeaderLabels(
            ["Dataset value", "Model code", "≤ 24°C", "> 24°C"]
        )
        defaults = [(1, 2, 2), (2, 3, 2), (3, 4, 3), (4, 7, 6), (5, 12, 8)]
        for row, values in enumerate(defaults):
            for column, value in enumerate((values[0], values[0], *values[1:])):
                self.duration_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.add_duration_state_button = ActionButton(
            "Add decomposition state", variant="secondary"
        )
        self.remove_duration_state_button = ActionButton("Remove selected row", variant="secondary")
        self.add_temperature_band_button = ActionButton("Add temperature boundary", variant="secondary")
        self.remove_temperature_band_button = ActionButton("Remove selected band", variant="secondary")
        self._add_form_field(layout, 0, "Method", self.duration_mode, span=2)
        self.fixed_duration_panel = QFrame()
        fixed_layout = QGridLayout(self.fixed_duration_panel)
        fixed_layout.setContentsMargins(0, 0, 0, 0)
        self._add_form_field(fixed_layout, 0, "Maximum reverse-drift duration", self.fixed_duration_days, span=2)
        layout.addWidget(self.fixed_duration_panel, 1, 0, 1, 2)

        self.duration_column_panel = QFrame()
        column_layout = QGridLayout(self.duration_column_panel)
        column_layout.setContentsMargins(0, 0, 0, 0)
        self.duration_column_label = QLabel("Duration column")
        self._add_form_field(column_layout, 0, self.duration_column_label, self.duration_column, span=2)
        layout.addWidget(self.duration_column_panel, 2, 0, 1, 2)

        self.duration_profile_panel = QFrame()
        profile_layout = QGridLayout(self.duration_profile_panel)
        profile_layout.setContentsMargins(0, 0, 0, 0)
        self.sst_column_label = QLabel("Temperature column")
        self._add_form_field(profile_layout, 0, self.sst_column_label, self.sst_column, span=2)
        self.duration_threshold_label = QLabel("New temperature boundary")
        self._add_form_field(profile_layout, 1, self.duration_threshold_label, self.temperature_boundaries_container, span=2)
        profile_layout.addWidget(self.duration_table, 2, 0, 1, 2)
        duration_actions = QVBoxLayout()
        for button in (self.add_duration_state_button, self.remove_duration_state_button,
                       self.add_temperature_band_button, self.remove_temperature_band_button):
            duration_actions.addWidget(button, 0, Qt.AlignLeft)
        profile_layout.addLayout(duration_actions, 3, 0, 1, 2)
        self.duration_profile_scroll = QScrollArea()
        self.duration_profile_scroll.setWidgetResizable(True)
        self.duration_profile_scroll.setFrameShape(QFrame.NoFrame)
        self.duration_profile_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.duration_profile_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.duration_profile_scroll.setWidget(self.duration_profile_panel)
        layout.addWidget(self.duration_profile_scroll, 3, 0, 1, 2)
        self.duration_profile_widgets = [
            self.sst_column_label,
            self.sst_column,
            self.duration_threshold_label,
            self.duration_threshold,
            self.temperature_boundaries_container,
            self.duration_table,
            self.add_duration_state_button,
            self.remove_duration_state_button,
            self.add_temperature_band_button,
            self.remove_temperature_band_button,
        ]
        self.duration_column_widgets = [
            self.duration_column_label,
            self.duration_column,
        ]

    def _build_windage(self) -> None:
        self.wind_column = self._column_selector("Select windage column")
        self.windage_group = QGroupBox("Windage")
        layout = QGridLayout(self.windage_group)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        self.wind_mode = AnimatedComboBox()
        self.wind_mode.addItem("Do not apply windage", "none")
        self.wind_mode.addItem("Read windage from a dataset column", "dataset")
        self.wind_mode.addItem("Use the same windage for every record", "fixed")
        self.wind_mode.addItem(
            "Estimate windage from specimen measurement", "measurement"
        )
        self.wind_mode.setCurrentIndex(self.wind_mode.findData("dataset"))
        self.wind_scale = AnimatedComboBox()
        self.wind_scale.addItem("Decimal fraction (0.015 = 1.5%)", "fraction")
        self.wind_scale.addItem("Percentage (1.5 = 1.5%)", "percent")
        self.fixed_wind_percent = self._float_box(0.0, 100.0, 1.5)
        self.fixed_wind_percent.setSuffix(" %")
        self.measurement_column = self._column_selector("Select measurement column")
        self.measurement_unit = AnimatedComboBox()
        self.measurement_unit.addItem("Centimetres (cm)", "centimeters")
        self.measurement_unit.addItem("Metres (m)", "meters")
        self.measurement_minimum = self._float_box(-1_000_000.0, 1_000_000.0, 0.0)
        self.measurement_maximum = self._float_box(-1_000_000.0, 1_000_000.0, 1.0)
        self.wind_min_percent = self._float_box(0.0, 100.0, 0.0)
        self.wind_min_percent.setSuffix(" %")
        self.wind_max_percent = self._float_box(0.0, 100.0, 1.5)
        self.wind_max_percent.setSuffix(" %")
        self.wind_range_behavior = AnimatedComboBox()
        self.wind_range_behavior.addItem("Clamp outside thresholds", "clamp")
        self.wind_range_behavior.addItem(
            "Extrapolate outside thresholds", "extrapolate"
        )
        self.windage_dataset_widgets = [
            QLabel("Column"),
            self.wind_column,
            QLabel("Column scale"),
            self.wind_scale,
        ]
        self.windage_fixed_widgets = [
            QLabel("Fixed wind drift"),
            self.fixed_wind_percent,
        ]
        self.windage_measurement_widgets = [
            QLabel("Measurement column"),
            self.measurement_column,
            QLabel("Measurement unit"),
            self.measurement_unit,
            QLabel("Minimum measurement"),
            self.measurement_minimum,
            QLabel("Maximum measurement"),
            self.measurement_maximum,
            QLabel("Minimum wind drift"),
            self.wind_min_percent,
            QLabel("Maximum wind drift"),
            self.wind_max_percent,
            QLabel("Outside range"),
            self.wind_range_behavior,
        ]
        self._add_form_field(layout, 0, "Method", self.wind_mode)
        self.windage_dataset_panel = QFrame()
        dataset_layout = QGridLayout(self.windage_dataset_panel)
        dataset_layout.setContentsMargins(0, 0, 0, 0)
        for index in range(0, len(self.windage_dataset_widgets), 2):
            self._add_form_field(dataset_layout, index // 2,
                                 *self.windage_dataset_widgets[index:index + 2])
        layout.addWidget(self.windage_dataset_panel, 1, 0, 1, 4)

        self.windage_fixed_panel = QFrame()
        fixed_layout = QGridLayout(self.windage_fixed_panel)
        fixed_layout.setContentsMargins(0, 0, 0, 0)
        self._add_form_field(fixed_layout, 0, *self.windage_fixed_widgets)
        layout.addWidget(self.windage_fixed_panel, 2, 0, 1, 4)

        self.windage_measurement_panel = QFrame()
        measurement_layout = QGridLayout(self.windage_measurement_panel)
        measurement_layout.setContentsMargins(0, 0, 0, 0)
        for index in range(0, len(self.windage_measurement_widgets), 2):
            self._add_form_field(measurement_layout, index // 2,
                                 *self.windage_measurement_widgets[index:index + 2])
        self.windage_measurement_scroll = QScrollArea()
        self.windage_measurement_scroll.setWidgetResizable(True)
        self.windage_measurement_scroll.setFrameShape(QFrame.NoFrame)
        self.windage_measurement_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.windage_measurement_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.windage_measurement_scroll.setWidget(self.windage_measurement_panel)
        layout.addWidget(self.windage_measurement_scroll, 3, 0, 1, 4)
        for combo in (
            self.duration_mode,
            self.wind_mode,
            self.wind_scale,
            self.wind_range_behavior,
        ):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(16)

    def add_duration_state(self, label: str | None = None) -> None:
        row = self.duration_table.rowCount()
        self.duration_table.insertRow(row)
        values = [label or f"State {row + 1}", row + 1] + [1] * (self.duration_table.columnCount() - 2)
        for column, value in enumerate(values):
            self.duration_table.setItem(row, column, QTableWidgetItem(str(value)))

    def remove_selected_duration_state(self) -> None:
        row = self.duration_table.currentRow()
        if row >= 0:
            self.duration_table.removeRow(row)

    def add_temperature_boundary(self, value: float | None = None) -> None:
        boundary = float((max(self.duration_boundaries) + 1.0) if value is None else value)
        if any(abs(boundary - current) < 1e-9 for current in self.duration_boundaries):
            return
        self.duration_boundaries.append(boundary)
        self.duration_boundaries.sort()
        band_column = self.duration_boundaries.index(boundary) + 2
        self.duration_table.insertColumn(band_column)
        for row in range(self.duration_table.rowCount()):
            self.duration_table.setItem(row, band_column, QTableWidgetItem("1"))
        self._rebuild_temperature_boundary_fields()
        self._refresh_duration_headers()

    def remove_selected_temperature_band(self) -> None:
        column = self.duration_table.currentColumn()
        if len(self.duration_boundaries) <= 1:
            return
        if column <= 1:
            column = self.duration_table.columnCount() - 1
        boundary_index = min(column - 2, len(self.duration_boundaries) - 1)
        self.duration_boundaries.pop(boundary_index)
        self.duration_table.removeColumn(column)
        self._rebuild_temperature_boundary_fields()
        self._refresh_duration_headers()

    def _boundary_edited(self, field: QDoubleSpinBox, value: float) -> None:
        try:
            index = self.temperature_boundary_fields.index(field)
        except ValueError:
            return
        self.duration_boundaries[index] = float(value)
        self._refresh_duration_headers()

    def _rebuild_temperature_boundary_fields(self) -> None:
        while self.temperature_boundaries_layout.count():
            item = self.temperature_boundaries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.duration_threshold:
                widget.deleteLater()
        fields: list[QDoubleSpinBox] = []
        for index, boundary in enumerate(self.duration_boundaries):
            field = self.duration_threshold if index == 0 else self._float_box(-5.0, 50.0, boundary)
            field.blockSignals(True)
            minimum = self.duration_boundaries[index - 1] + 0.1 if index else -5.0
            maximum = (
                self.duration_boundaries[index + 1] - 0.1
                if index < len(self.duration_boundaries) - 1
                else 50.0
            )
            field.setRange(minimum, maximum)
            field.setValue(boundary)
            field.setSuffix(" °C")
            field.blockSignals(False)
            if index > 0:
                field.valueChanged.connect(
                    lambda value, field=field: self._boundary_edited(field, value)
                )
            self.temperature_boundaries_layout.addWidget(field)
            fields.append(field)
        self.temperature_boundary_fields = fields
        QTimer.singleShot(0, self._sync_compact_scroll)

    def _refresh_duration_headers(self) -> None:
        bounds = self.duration_boundaries
        headers = ["Dataset value", "Model code"]
        headers.append(f"≤ {bounds[0]:g}°C")
        headers.extend(
            f"{lower:g}–{upper:g}°C"
            for lower, upper in zip(bounds, bounds[1:])
        )
        headers.append(f"> {bounds[-1]:g}°C")
        self.duration_table.setHorizontalHeaderLabels(headers)

    def set_decomposition_values(self, values: list[object]) -> None:
        labels = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if not labels:
            return
        existing: dict[str, list[str]] = {}
        for row in range(self.duration_table.rowCount()):
            items = [self.duration_table.item(row, column) for column in range(self.duration_table.columnCount())]
            if items[0] is not None:
                existing[items[0].text().strip()] = [item.text() if item is not None else "1" for item in items]
        self.duration_table.setRowCount(0)
        for label in labels:
            if label not in existing:
                self.add_duration_state(label)
                continue
            row = self.duration_table.rowCount()
            self.duration_table.insertRow(row)
            for column, value in enumerate(existing[label]):
                self.duration_table.setItem(row, column, QTableWidgetItem(value))

    def decomposition_mapping(self) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for row in range(self.duration_table.rowCount()):
            label_item = self.duration_table.item(row, 0)
            code_item = self.duration_table.item(row, 1)
            if label_item is None or code_item is None:
                continue
            label = label_item.text().strip()
            try:
                mapping[label] = int(code_item.text().strip())
            except ValueError as exc:
                raise ValueError(
                    f"Row {row + 1} ('{label}') has an invalid Model Code. Use an integer."
                ) from exc
        return mapping

    def duration_profile_data(self) -> tuple[list[float], dict[int, list[int]], dict[str, int]]:
        if any(
            current >= following
            for current, following in zip(self.duration_boundaries, self.duration_boundaries[1:])
        ):
            raise ValueError("Temperature boundaries must be strictly ascending.")
        mapping = self.decomposition_mapping()
        scenarios: dict[int, list[int]] = {}
        for row in range(self.duration_table.rowCount()):
            label_item = self.duration_table.item(row, 0)
            if label_item is None or not label_item.text().strip():
                raise ValueError("Every duration-profile row needs a decomposition state.")
            label = label_item.text().strip()
            days: list[int] = []
            for column in range(2, self.duration_table.columnCount()):
                item = self.duration_table.item(row, column)
                if item is None or not item.text().strip() or int(item.text()) < 1:
                    raise ValueError("Every temperature band needs a positive duration in days.")
                days.append(int(item.text()))
            scenarios[mapping[label]] = days
        return list(self.duration_boundaries), scenarios, mapping

    def set_duration_profile(self, boundaries: list[float], scenarios: dict[int, list[int]],
                             value_map: dict[str, int]) -> None:
        if not boundaries or not scenarios:
            return
        self.duration_boundaries = sorted(float(value) for value in boundaries)
        self._rebuild_temperature_boundary_fields()
        self.duration_table.setColumnCount(len(self.duration_boundaries) + 3)
        reverse_labels = {code: label for label, code in value_map.items()}
        self.duration_table.setRowCount(0)
        for code in sorted(scenarios):
            row = self.duration_table.rowCount()
            self.duration_table.insertRow(row)
            values = [reverse_labels.get(code, str(code)), code, *scenarios[code]]
            for column, value in enumerate(values):
                self.duration_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._refresh_duration_headers()

    def _build_release_and_physics(self) -> None:
        self.release_group = QGroupBox("Scenario and particle release")
        layout = QGridLayout(self.release_group)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        self.iteration_count = QSpinBox()
        self.iteration_count.setRange(1, 999)
        self.iteration_count.setValue(15)
        self.iteration_interval = self._float_box(0.0, 8760.0, 1.0)
        self.iteration_interval.setSuffix(" h")
        self.model_time_step = self._float_box(0.01, 24.0, 1.0)
        self.model_time_step.setSuffix(" h")
        self.model_time_step.setToolTip(
            "Time between successive calculated positions in each trajectory."
        )
        self.release_strategy = AnimatedComboBox()
        self.release_strategy.addItem("Single start time", "single")
        self.release_strategy.addItem("Multiple start-time scenarios", "multiple")
        self.release_strategy.addItem("Fixed clock time on observation date", "fixed_hour")
        self.release_strategy.addItem("Multiple scenarios from a fixed clock time", "multiple_fixed")
        self.release_strategy.setCurrentIndex(
            self.release_strategy.findData("multiple")
        )
        self.start_time_mode = AnimatedComboBox()
        self.start_time_mode.addItem(
            "Recorded observation date and time", "observation_time"
        )
        self.start_time_mode.addItem(
            "Fixed hour on the observation date", "fixed_hour"
        )
        self.fixed_start_hour = QSpinBox()
        self.fixed_start_hour.setRange(0, 23)
        self.fixed_start_hour.setValue(9)
        self.fixed_start_hour.setSuffix(":00")
        self.particle_count = QSpinBox()
        self.particle_count.setRange(1, 100000)
        self.particle_count.setValue(1)
        self.release_radius = self._float_box(0.0, 1_000_000.0, 0.0)
        self.release_radius.setSuffix(" m")
        self._add_form_field(layout, 0, "Temporal release strategy", self.release_strategy)
        self.release_scenarios_panel = QFrame()
        scenario_layout = QGridLayout(self.release_scenarios_panel)
        scenario_layout.setContentsMargins(0, 0, 0, 0)
        self._add_field_pair(
            scenario_layout, 0, "Start-time scenarios", self.iteration_count,
            "Time shift between scenarios", self.iteration_interval,
        )
        layout.addWidget(self.release_scenarios_panel, 1, 0, 1, 4)
        self.fixed_start_panel = QFrame()
        fixed_start_layout = QGridLayout(self.fixed_start_panel)
        fixed_start_layout.setContentsMargins(0, 0, 0, 0)
        self._add_form_field(fixed_start_layout, 0, "Fixed start hour", self.fixed_start_hour)
        layout.addWidget(self.fixed_start_panel, 2, 0, 1, 4)
        self._add_field_pair(
            layout,
            3,
            "Particles per scenario",
            self.particle_count,
            "Initial spread radius",
            self.release_radius,
        )

        self.advanced_group = QGroupBox("Model physics")
        advanced = QGridLayout(self.advanced_group)
        advanced.setColumnStretch(1, 1)
        advanced.setColumnStretch(3, 1)
        self.current_uncertainty = self._float_box(0.0, 5.0, 0.05)
        self.current_uncertainty.setDecimals(3)
        self.current_uncertainty.setSingleStep(0.01)
        self.wind_uncertainty = self._float_box(0.0, 5.0, 0.10)
        self.wind_uncertainty.setDecimals(3)
        self.wind_uncertainty.setSingleStep(0.01)
        self.current_uncertainty_toggle = AnimatedToggle("Apply current uncertainty")
        self.current_uncertainty_toggle.setChecked(True)
        self.wind_uncertainty_toggle = AnimatedToggle("Apply wind uncertainty")
        self.wind_uncertainty_toggle.setChecked(True)
        self.coastline_action = AnimatedComboBox()
        self.coastline_action.addItem(
            "Return to previous ocean position", "previous"
        )
        self.coastline_action.addItem(
            "Stop particles when reaching land", "stranding"
        )
        self.coastline_action.addItem("Allow movement across land", "none")
        self._add_form_field(advanced, 0, "Model timestep", self.model_time_step)
        timestep_hint = QLabel("Time between calculated positions in each trajectory")
        timestep_hint.setProperty("role", "field-hint")
        timestep_hint.setWordWrap(True)
        advanced.addWidget(timestep_hint, 1, 0, 1, 4)
        self._add_form_field(advanced, 2, "Coastline behavior", self.coastline_action)
        advanced.addWidget(self.current_uncertainty_toggle, 3, 0, 1, 4)
        self.current_uncertainty_panel = QFrame()
        current_layout = QVBoxLayout(self.current_uncertainty_panel)
        current_layout.setContentsMargins(0, 0, 0, 0)
        current_layout.addWidget(QLabel("Current uncertainty"))
        current_layout.addWidget(self.current_uncertainty)
        advanced.addWidget(self.current_uncertainty_panel, 4, 0, 1, 4)
        advanced.addWidget(self.wind_uncertainty_toggle, 5, 0, 1, 4)
        self.wind_uncertainty_panel = QFrame()
        wind_layout = QVBoxLayout(self.wind_uncertainty_panel)
        wind_layout.setContentsMargins(0, 0, 0, 0)
        wind_layout.addWidget(QLabel("Wind uncertainty"))
        wind_layout.addWidget(self.wind_uncertainty)
        advanced.addWidget(self.wind_uncertainty_panel, 6, 0, 1, 4)

        self.environment_export_group = QGroupBox("Trajectory environmental values")
        environment_export_layout = QGridLayout(self.environment_export_group)
        environment_export_hint = QLabel(
            "Store selected values at every particle timestep for later table export. "
            "More variables increase trajectory file size."
        )
        environment_export_hint.setWordWrap(True)
        environment_export_hint.setProperty("role", "field-hint")
        environment_export_layout.addWidget(environment_export_hint, 0, 0, 1, 2)
        self.environment_export_checks: dict[str, QCheckBox] = {}
        for index, (name, definition) in enumerate(ENVIRONMENT_EXPORT_CATALOGUE.items()):
            checkbox = QCheckBox(definition.label)
            checkbox.setToolTip(definition.description)
            checkbox.setProperty("environmentVariable", name)
            self.environment_export_checks[name] = checkbox
            environment_export_layout.addWidget(checkbox, 1 + index, 0, 1, 2)
        advanced.addWidget(self.environment_export_group, 7, 0, 1, 4)

        self.fallback_group = QGroupBox("Missing forcing behavior (optional)")
        fallback = QVBoxLayout(self.fallback_group)
        fallback.setSpacing(10)
        fallback_hint = QLabel(
            "Use constants only where an environmental reader has no value. "
            "This does not extrapolate or select the nearest edge value."
        )
        fallback_hint.setWordWrap(True)
        fallback_hint.setProperty("role", "field-hint")
        fallback.addWidget(fallback_hint)

        self.current_fallback_toggle = AnimatedToggle("Fallback currents")
        self.wind_fallback_toggle = AnimatedToggle("Fallback wind")
        self.stokes_fallback_toggle = AnimatedToggle("Fallback Stokes drift")
        self.depth_fallback_toggle = AnimatedToggle("Fallback seafloor depth")
        self.current_fallback_x = self._float_box(-20.0, 20.0, 0.0)
        self.current_fallback_y = self._float_box(-20.0, 20.0, 0.0)
        self.wind_fallback_x = self._float_box(-100.0, 100.0, 0.0)
        self.wind_fallback_y = self._float_box(-100.0, 100.0, 0.0)
        self.stokes_fallback_x = self._float_box(-20.0, 20.0, 0.0)
        self.stokes_fallback_y = self._float_box(-20.0, 20.0, 0.0)
        self.depth_fallback_value = self._float_box(0.1, 12_000.0, 25.0)
        for box in (
            self.current_fallback_x, self.current_fallback_y,
            self.wind_fallback_x, self.wind_fallback_y,
            self.stokes_fallback_x, self.stokes_fallback_y,
        ):
            box.setDecimals(3)
            box.setSuffix(" m/s")
        self.depth_fallback_value.setDecimals(1)
        self.depth_fallback_value.setSuffix(" m")

        vector_rows = (
            (self.current_fallback_toggle, self.current_fallback_x, self.current_fallback_y),
            (self.wind_fallback_toggle, self.wind_fallback_x, self.wind_fallback_y),
            (self.stokes_fallback_toggle, self.stokes_fallback_x, self.stokes_fallback_y),
        )
        for toggle, eastward, northward in vector_rows:
            row = QFrame()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            row_layout.addWidget(toggle)
            for label_text, field in (("Eastward velocity", eastward), ("Northward velocity", northward)):
                field_group = QWidget()
                field_layout = QVBoxLayout(field_group)
                field_layout.setContentsMargins(0, 0, 0, 0)
                field_layout.setSpacing(3)
                label = QLabel(label_text)
                label.setProperty("role", "field-hint")
                field_layout.addWidget(label)
                field_layout.addWidget(field)
                row_layout.addWidget(field_group, 1)
            fallback.addWidget(row)
        depth_row = QFrame()
        depth_layout = QVBoxLayout(depth_row)
        depth_layout.setContentsMargins(0, 0, 0, 0)
        depth_layout.addWidget(self.depth_fallback_toggle)
        depth_field = QWidget()
        depth_field_layout = QVBoxLayout(depth_field)
        depth_field_layout.setContentsMargins(0, 0, 0, 0)
        depth_field_layout.setSpacing(3)
        depth_label = QLabel("Seafloor depth")
        depth_label.setProperty("role", "field-hint")
        depth_field_layout.addWidget(depth_label)
        depth_field_layout.addWidget(self.depth_fallback_value)
        depth_layout.addWidget(depth_field, 1)
        depth_layout.addStretch(1)
        fallback.addWidget(depth_row)
        self.fallback_vector_fields = {
            self.current_fallback_toggle: (self.current_fallback_x, self.current_fallback_y),
            self.wind_fallback_toggle: (self.wind_fallback_x, self.wind_fallback_y),
            self.stokes_fallback_toggle: (self.stokes_fallback_x, self.stokes_fallback_y),
            self.depth_fallback_toggle: (self.depth_fallback_value,),
        }
        advanced.addWidget(self.fallback_group, 8, 0, 1, 4)
        self._update_fallback_panels()

    def _build_model_builder(self) -> QWidget:
        workspace = QFrame()
        workspace.setObjectName("ModelBuilder")
        workspace.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QGridLayout(workspace)
        self.builder_layout = layout
        self._compact_builder = None
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        progress = QFrame()
        self.progress_panel = progress
        progress.setObjectName("SetupProgress")
        progress.setMinimumWidth(190)
        progress.setMaximumWidth(260)
        progress_layout = QVBoxLayout(progress)
        progress_layout.addWidget(QLabel("Setup progress"))
        progress_copy = QLabel("Complete each modelling decision before review.")
        progress_copy.setWordWrap(True)
        progress_copy.setProperty("role", "field-hint")
        progress_layout.addWidget(progress_copy)
        self.internal_step_list = QListWidget()
        self.internal_step_list.setObjectName("InternalStepList")
        self.internal_step_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.internal_step_list.setWordWrap(True)
        self.step_items: list[QListWidgetItem] = []
        for index, title in enumerate(self.STEP_TITLES):
            item = QListWidgetItem(f"{index + 1}  {title}\nNot started")
            item.setIcon(line_icon(("study-area", "observation-selection", "drift-duration",
                                    "windage", "particle-release", "model-physics")[index], "#0b2e43"))
            self.internal_step_list.addItem(item)
            self.step_items.append(item)
        self.internal_step_list.setCurrentRow(0)
        progress_layout.addWidget(self.internal_step_list, 1)

        center = QFrame()
        self.configuration_panel = center
        center.setObjectName("SetupConfiguration")
        center.setMinimumWidth(360)
        center.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.compact_step_selector = AnimatedComboBox()
        self.compact_step_selector.setAccessibleName("Simulation setup step")
        self.compact_step_selector.addItems(list(self.STEP_TITLES))
        self.compact_step_selector.hide()
        builder_controls = QHBoxLayout()
        builder_controls.addWidget(self.compact_step_selector, 1)
        builder_controls.addStretch(1)
        self.summary_toggle_button = ActionButton("Hide summary", variant="secondary")
        self.summary_toggle_button.setCheckable(True)
        self.summary_toggle_button.setChecked(True)
        self.summary_toggle_button.setAccessibleName("Show model summary")
        self.summary_toggle_button.toggled.connect(self._set_summary_visible)
        builder_controls.addWidget(self.summary_toggle_button)
        center_layout.addLayout(builder_controls)
        self.configuration_stack = AnimatedStackedWidget()
        self.configuration_stack.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        pages = (
            self._configuration_page(
                "Study area", "Choose the spatial domain and optional environmental overlap.",
                (self.study_area_group,),
            ),
            self._configuration_page(
                "Observations", "Choose which records run and how coastal positions are handled.",
                (self.selection_group, self.initial_position_group),
            ),
            self._configuration_page(
                "Drift duration", "Define how reverse-drift duration is assigned.",
                (self.duration_group,),
            ),
            self._configuration_page(
                "Windage", "Choose whether and how windage is applied.",
                (self.windage_group,),
            ),
            self._configuration_page(
                "Particle release", "Configure temporal starts and the particle ensemble.",
                (self.release_group,),
            ),
            self._configuration_page(
                "Model physics", "Set the calculation timestep, coastline behavior, uncertainty, and optional missing-data fallbacks.",
                (self.advanced_group,),
            ),
        )
        for page in pages:
            self.configuration_stack.addWidget(page)
        center_layout.addWidget(self.configuration_stack, 1)
        self.step_feedback = QLabel("")
        self.step_feedback.setObjectName("SetupStepFeedback")
        self.step_feedback.setWordWrap(True)
        self.step_feedback.hide()
        center_layout.addWidget(self.step_feedback)
        navigation = QHBoxLayout()
        self.back_step_button = ActionButton("Back", variant="secondary")
        self.continue_step_button = ActionButton("Continue", variant="primary")
        navigation.addWidget(self.back_step_button)
        navigation.addStretch(1)
        navigation.addWidget(self.continue_step_button)
        center_layout.addLayout(navigation)

        summary = QFrame()
        self.summary_panel = summary
        summary.setObjectName("SetupSummary")
        summary.setMinimumWidth(220)
        summary.setMaximumWidth(280)
        summary_layout = QVBoxLayout(summary)
        summary_layout.addWidget(QLabel("Model summary"))
        summary_copy = QLabel("Live overview of the current assumptions.")
        summary_copy.setWordWrap(True)
        summary_copy.setProperty("role", "field-hint")
        summary_layout.addWidget(summary_copy)
        self.summary_scroll = QScrollArea()
        self.summary_scroll.setObjectName("SetupSummaryScroll")
        self.summary_scroll.setWidgetResizable(True)
        self.summary_scroll.setFrameShape(QFrame.NoFrame)
        self.summary_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        summary_content = QWidget()
        summary_items_layout = QVBoxLayout(summary_content)
        summary_items_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_labels: list[QLabel] = []
        for title in self.STEP_TITLES:
            label = QLabel(title)
            label.setObjectName("SetupSummaryItem")
            label.setWordWrap(True)
            label.setProperty("state", "not_started")
            summary_items_layout.addWidget(label)
            self.summary_labels.append(label)
        summary_items_layout.addStretch(1)
        self.summary_scroll.setWidget(summary_content)
        summary_layout.addWidget(self.summary_scroll, 1)

        layout.addWidget(progress, 0, 0)
        layout.addWidget(center, 0, 1)
        layout.addWidget(summary, 0, 2)
        layout.setColumnStretch(1, 1)
        self.internal_step_list.currentRowChanged.connect(self.set_current_step)
        self.compact_step_selector.currentIndexChanged.connect(self.set_current_step)
        self.back_step_button.clicked.connect(self._go_to_previous_step)
        self.continue_step_button.clicked.connect(self._continue_from_step)
        self._refresh_step_ui()
        return workspace

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "builder_layout"):
            return
        compact = self.viewport().width() < 1100
        if compact != self._compact_builder:
            self._compact_builder = compact
            self._arrange_builder()
        QTimer.singleShot(0, self._sync_compact_scroll)

    def _set_summary_visible(self, visible: bool) -> None:
        self.summary_panel.setVisible(visible)
        self.summary_toggle_button.setText("Hide summary" if visible else "Show summary")
        self._arrange_builder()
        QTimer.singleShot(0, self._sync_compact_scroll)

    def _arrange_builder(self) -> None:
        compact = bool(self._compact_builder)
        for panel in (self.progress_panel, self.configuration_panel, self.summary_panel):
            self.builder_layout.removeWidget(panel)
        self.progress_panel.setVisible(not compact)
        self.compact_step_selector.setVisible(compact)
        self.configuration_panel.setMinimumHeight(0)
        self.summary_panel.setMinimumHeight(0)
        self.summary_panel.setMaximumWidth(16777215 if compact else 280)
        for column in range(3):
            self.builder_layout.setColumnStretch(column, 0)
        if compact:
            self.builder_layout.addWidget(self.configuration_panel, 0, 0)
            self.builder_layout.addWidget(self.summary_panel, 1, 0)
            self.builder_layout.setColumnStretch(0, 1)
        else:
            self.builder_layout.addWidget(self.progress_panel, 0, 0)
            self.builder_layout.addWidget(self.configuration_panel, 0, 1)
            self.builder_layout.addWidget(self.summary_panel, 0, 2)
            self.builder_layout.setColumnStretch(1, 1)

    def _sync_compact_scroll(self) -> None:
        """Use the outer page scrollbar rather than nested scrollers on small windows."""
        compact = getattr(self, "_compact_builder", False)
        page = self.configuration_stack.currentWidget()
        if page is None:
            return
        self.area_map.setFixedHeight(max(260, min(400, (self.area_map.width() - 24) // 2 + 100)))
        # Keep legacy panel references, but let the page own vertical scrolling.
        for scroll in (self.duration_profile_scroll, self.windage_measurement_scroll):
            layout = scroll.widget().layout()
            width = max(1, scroll.viewport().width())
            height = max(layout.sizeHint().height(), layout.totalHeightForWidth(width))
            scroll.setFixedHeight(height + 2 * scroll.frameWidth())
        page.widget().layout().activate()
        if compact:
            layout = page.widget().layout()
            height = max(layout.sizeHint().height(), layout.totalHeightForWidth(max(1, page.viewport().width()))) + 12
            self.configuration_stack.setFixedHeight(height)
            self.summary_scroll.setMinimumHeight(self.summary_scroll.widget().sizeHint().height() + 8)
            page.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.configuration_stack.setMinimumHeight(0)
            self.configuration_stack.setMaximumHeight(16777215)
            self.summary_scroll.setMinimumHeight(0)
            page.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    @staticmethod
    def _configuration_page(title: str, copy: str, widgets: tuple[QWidget, ...]) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page = QWidget()
        page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(page)
        heading = QLabel(title)
        heading.setProperty("role", "configuration-title")
        description = QLabel(copy)
        description.setWordWrap(True)
        description.setProperty("role", "field-hint")
        layout.addWidget(heading)
        layout.addWidget(description)
        for widget in widgets:
            layout.addWidget(widget)
            for field in widget.findChildren(QSpinBox) + widget.findChildren(QDoubleSpinBox):
                SimulationSetupPage._compact_numeric_field(field)
            for selector in widget.findChildren(QComboBox):
                selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
                selector.setMinimumContentsLength(18)
                selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            for label in widget.findChildren(QLabel):
                label.setWordWrap(True)
        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def _connect_builder_updates(self) -> None:
        self.add_duration_state_button.clicked.connect(lambda: self.add_duration_state())
        self.remove_duration_state_button.clicked.connect(self.remove_selected_duration_state)
        self.add_temperature_band_button.clicked.connect(lambda: self.add_temperature_boundary())
        self.remove_temperature_band_button.clicked.connect(self.remove_selected_temperature_band)
        self.duration_mode.currentIndexChanged.connect(self._update_duration_panels)
        self.wind_mode.currentIndexChanged.connect(self._update_windage_panels)
        self.release_strategy.currentIndexChanged.connect(self._update_release_panels)
        self.current_uncertainty_toggle.toggled.connect(self._update_uncertainty_panels)
        self.wind_uncertainty_toggle.toggled.connect(self._update_uncertainty_panels)
        for toggle in self.fallback_vector_fields:
            toggle.toggled.connect(self._update_fallback_panels)
        for combo in (
            self.coverage_toggle, self.position_search_toggle,
            self.selection_mode, self.duration_mode, self.wind_mode,
            self.release_strategy, self.coastline_action,
            self.current_uncertainty_toggle, self.wind_uncertainty_toggle,
            *self.fallback_vector_fields.keys(),
        ):
            signal = combo.toggled if isinstance(combo, AnimatedToggle) else combo.currentIndexChanged
            signal.connect(self._update_summaries)
        for field in (
            self.min_lon, self.max_lon, self.min_lat, self.max_lat,
            self.selection_sample_size, self.fixed_duration_days,
            self.duration_threshold, self.fixed_wind_percent,
            self.iteration_count, self.iteration_interval, self.model_time_step, self.fixed_start_hour,
            self.particle_count, self.release_radius,
            self.current_uncertainty, self.wind_uncertainty,
            self.current_fallback_x, self.current_fallback_y,
            self.wind_fallback_x, self.wind_fallback_y,
            self.stokes_fallback_x, self.stokes_fallback_y,
            self.depth_fallback_value,
        ):
            field.valueChanged.connect(self._update_summaries)
        for selector in (self.duration_column, self.sst_column, self.wind_column, self.measurement_column):
            selector.currentTextChanged.connect(self._update_summaries)
        for checkbox in self.environment_export_checks.values():
            checkbox.toggled.connect(self._update_summaries)

    def selected_environment_export_variables(self) -> list[str]:
        return [
            name for name, checkbox in self.environment_export_checks.items()
            if checkbox.isChecked()
        ]

    def set_current_step(self, index: int) -> None:
        if not 0 <= index < len(self.STEP_TITLES):
            return
        self.current_step_index = index
        self.configuration_stack.setCurrentIndex(index)
        if self.step_states[index] == "not_started":
            self.step_states[index] = "incomplete"
        if self.internal_step_list.currentRow() != index:
            self.internal_step_list.setCurrentRow(index)
        self.step_feedback.hide()
        self._refresh_step_ui()
        QTimer.singleShot(0, self._sync_compact_scroll)

    def _go_to_previous_step(self) -> None:
        self.set_current_step(max(0, self.current_step_index - 1))

    def _continue_from_step(self) -> None:
        state, message = self.validate_step(self.current_step_index)
        self._set_step_state(self.current_step_index, state)
        if state not in {"valid", "warning"}:
            self.step_feedback.setText(message)
            self.step_feedback.setProperty("level", state)
            self.step_feedback.show()
            self._refresh_widget_style(self.step_feedback)
            return
        self.step_feedback.hide()
        if self.current_step_index < len(self.STEP_TITLES) - 1:
            self.set_current_step(self.current_step_index + 1)
        elif self.validate_all_steps():
            self.setup_finished.emit()

    def validate_step(self, index: int) -> tuple[str, str]:
        if index == 0:
            if self.min_lon.value() >= self.max_lon.value() or self.min_lat.value() >= self.max_lat.value():
                return "error", "Minimum longitude and latitude must be lower than maximum bounds."
            return "valid", "Study area configured."
        if index == 1:
            if self.selection_mode.currentData() == "random" and self.selection_sample_size.value() < 1:
                return "error", "Random selection requires at least one observation."
            if self.selection_mode.currentData() == "filter" and not self.filter_condition_rows:
                return "incomplete", "Add at least one dataset condition or choose another selection method."
            if self.position_search_toggle.isChecked() and self.position_max_radius.value() < self.position_radial_step.value():
                return "error", "Nearby-water maximum radius must be at least the radial step."
            return "valid", "Observation selection configured."
        if index == 2:
            mode = self.duration_mode.currentData()
            if mode == "fixed" and self.fixed_duration_days.value() < 1:
                return "error", "Fixed duration must be at least one day."
            if mode == "dataset" and not self.duration_column.currentText().strip():
                return "incomplete", "Select the dataset column containing drift duration."
            if mode == "estimated" and not self.sst_column.currentText().strip():
                return "incomplete", "Select the temperature column used by the duration profile."
            return "valid", "Drift duration configured."
        if index == 3:
            mode = self.wind_mode.currentData()
            if mode == "dataset" and not self.wind_column.currentText().strip():
                return "incomplete", "Select the dataset column containing windage."
            if mode == "measurement" and not self.measurement_column.currentText().strip():
                return "incomplete", "Select the specimen measurement column."
            if mode == "measurement" and self.measurement_minimum.value() >= self.measurement_maximum.value():
                return "error", "Minimum measurement must be lower than maximum measurement."
            return "valid", "Windage configured."
        if index == 4:
            if self.particle_count.value() < 1:
                return "error", "Particles per start must be at least one."
            if self.release_strategy.currentData() == "multiple" and self.iteration_count.value() < 2:
                return "error", "Multiple start-time scenarios require at least two starts."
            if self.iteration_count.value() * self.particle_count.value() >= 1_000_000:
                return (
                    "warning",
                    "This particle workload may require substantial processing time and storage.",
                )
            return "valid", "Particle release configured."
        if self.current_uncertainty_toggle.isChecked() and self.current_uncertainty.value() < 0:
            return "error", "Current uncertainty cannot be negative."
        if self.wind_uncertainty_toggle.isChecked() and self.wind_uncertainty.value() < 0:
            return "error", "Wind uncertainty cannot be negative."
        return "valid", "Model physics configured."

    def validate_all_steps(self) -> bool:
        first_invalid: int | None = None
        for index in range(len(self.STEP_TITLES)):
            state, _ = self.validate_step(index)
            self._set_step_state(index, state)
            if state not in {"valid", "warning"} and first_invalid is None:
                first_invalid = index
        if first_invalid is not None:
            self.set_current_step(first_invalid)
            _, message = self.validate_step(first_invalid)
            self.step_feedback.setText(message)
            self.step_feedback.setProperty("level", self.step_states[first_invalid])
            self.step_feedback.show()
            self._refresh_widget_style(self.step_feedback)
            return False
        return True

    def _set_step_state(self, index: int, state: str) -> None:
        if state not in self.STEP_STATES:
            raise ValueError(state)
        self.step_states[index] = state
        self._refresh_step_ui()

    def _refresh_step_ui(self) -> None:
        labels = {
            "not_started": "Not started", "incomplete": "Needs input",
            "valid": "Ready", "warning": "Review", "error": "Fix required",
        }
        for index, item in enumerate(self.step_items):
            state = self.step_states[index]
            issues = getattr(self, "validation_step_issues", {}).get(index, [])
            levels = {getattr(issue, "level", "error") for issue in issues}
            levels.add(state)
            if "error" in levels:
                state = "error"
            elif "warning" in levels:
                state = "warning"
            color = {"error": "#b34444", "warning": "#946200"}.get(state, "#0b2e43")
            icon_name = ("error" if state == "error" else "warning" if state == "warning"
                         else ("study-area", "observation-selection", "drift-duration",
                               "windage", "particle-release", "model-physics")[index])
            item.setForeground(QColor(color))
            item.setIcon(line_icon(icon_name, color))
            item.setText(f"{index + 1}  {self.STEP_TITLES[index]}\n{labels[state]}")
            item.setData(Qt.UserRole, state)
            self.compact_step_selector.setItemText(
                index, f"{index + 1}. {self.STEP_TITLES[index]} - {labels[state]}"
            )
            self.compact_step_selector.setItemIcon(index, line_icon(icon_name, color))
            self.compact_step_selector.setItemData(index, QColor(color), Qt.ForegroundRole)
            self.summary_labels[index].setProperty("state", state)
            self._refresh_widget_style(self.summary_labels[index])
        self.compact_step_selector.blockSignals(True)
        self.compact_step_selector.setCurrentIndex(self.current_step_index)
        self.compact_step_selector.blockSignals(False)
        self.back_step_button.setEnabled(self.current_step_index > 0)
        self.continue_step_button.setText(
            "Finish setup" if self.current_step_index == len(self.STEP_TITLES) - 1 else "Continue"
        )

    def _update_duration_panels(self, *_: object) -> None:
        mode = self.duration_mode.currentData()
        self.fixed_duration_panel.setVisible(mode == "fixed")
        self.duration_column_panel.setVisible(mode == "dataset")
        self.duration_profile_scroll.setVisible(mode == "estimated")
        self._update_summaries()

    def _update_windage_panels(self, *_: object) -> None:
        mode = self.wind_mode.currentData()
        self.windage_dataset_panel.setVisible(mode == "dataset")
        self.windage_fixed_panel.setVisible(mode == "fixed")
        self.windage_measurement_scroll.setVisible(mode == "measurement")
        self._update_summaries()

    def _update_release_panels(self, *_: object) -> None:
        strategy = self.release_strategy.currentData()
        self.release_scenarios_panel.setVisible(strategy in {"multiple", "multiple_fixed"})
        self.fixed_start_panel.setVisible(strategy in {"fixed_hour", "multiple_fixed"})
        if strategy in {"multiple", "multiple_fixed"}:
            self.iteration_count.setValue(max(2, self.iteration_count.value()))
            mode = "fixed_hour" if strategy == "multiple_fixed" else "observation_time"
            self.start_time_mode.setCurrentIndex(self.start_time_mode.findData(mode))
        else:
            self.iteration_count.setValue(1)
            mode = "fixed_hour" if strategy == "fixed_hour" else "observation_time"
            self.start_time_mode.setCurrentIndex(self.start_time_mode.findData(mode))
        self._update_summaries()

    def _update_uncertainty_panels(self, *_: object) -> None:
        self.current_uncertainty_panel.setVisible(self.current_uncertainty_toggle.isChecked())
        self.wind_uncertainty_panel.setVisible(self.wind_uncertainty_toggle.isChecked())
        self._update_summaries()

    def _update_fallback_panels(self, *_: object) -> None:
        for toggle, fields in self.fallback_vector_fields.items():
            for field in fields:
                field.setEnabled(toggle.isChecked())
        self._update_summaries()

    def _update_summaries(self, *_: object) -> None:
        if not hasattr(self, "summary_labels"):
            return
        QTimer.singleShot(0, self._sync_compact_scroll)
        area_method = "Environmental overlap" if self.coverage_toggle.isChecked() else "Manual extent"
        self.summary_labels[0].setText(
            f"Study area\n{area_method}\n{self.min_lon.value():g} to {self.max_lon.value():g} lon"
        )
        selection = self.selection_mode.currentText()
        snap = ("Nearby-water correction on" if self.position_search_toggle.isChecked()
                else self.position_direct_policy.currentText())
        self.summary_labels[1].setText(f"Observations\n{selection}\n{snap}")
        duration_mode = self.duration_mode.currentData()
        duration_detail = {
            "fixed": f"{self.fixed_duration_days.value()} days",
            "dataset": self.duration_column.currentText().strip() or "Select duration column",
            "estimated": "SST and decomposition profile",
        }.get(duration_mode, "Not configured")
        self.summary_labels[2].setText(f"Drift duration\n{duration_detail}")
        wind_mode = self.wind_mode.currentData()
        if wind_mode == "none":
            wind_detail = "No windage"
        elif wind_mode == "fixed":
            percent = self.fixed_wind_percent.value()
            wind_detail = f"Fixed {percent:g}% / {percent / 100:g} fraction"
        else:
            wind_detail = self.wind_mode.currentText()
        self.summary_labels[3].setText(f"Windage\n{wind_detail}")
        strategy = self.release_strategy.currentText()
        starts = self.iteration_count.value()
        self.summary_labels[4].setText(
            f"Particle release\n{strategy}\n{starts} start(s), {self.particle_count.value()} particle(s) each"
        )
        current = "on" if self.current_uncertainty_toggle.isChecked() else "off"
        wind = "on" if self.wind_uncertainty_toggle.isChecked() else "off"
        fallbacks = [
            label for toggle, label in (
                (self.current_fallback_toggle, "currents"),
                (self.wind_fallback_toggle, "wind"),
                (self.stokes_fallback_toggle, "Stokes drift"),
                (self.depth_fallback_toggle, "depth"),
            ) if toggle.isChecked()
        ]
        fallback_summary = ", ".join(fallbacks) if fallbacks else "none"
        self.summary_labels[5].setText(
            f"Model physics\nCoastline: {self.coastline_action.currentText()}\n"
            f"Uncertainty: current {current}, wind {wind}\nFallbacks: {fallback_summary}"
        )

    @staticmethod
    def _refresh_widget_style(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    @staticmethod
    def _float_box(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        field = CompactDoubleSpinBox()
        field.setDecimals(4)
        field.setRange(minimum, maximum)
        field.setValue(value)
        field.setSingleStep(0.1)
        SimulationSetupPage._compact_numeric_field(field)
        return field

    @staticmethod
    def _compact_numeric_field(field: QSpinBox | QDoubleSpinBox) -> None:
        field.setMinimumWidth(140)
        field.setMaximumWidth(190)
        field.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    @staticmethod
    def _field_layout(label: str | QLabel, field: QWidget) -> QVBoxLayout:
        label = QLabel(label) if isinstance(label, str) else label
        label.setWordWrap(True)
        label.setBuddy(field)
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addWidget(field)
        return layout

    @staticmethod
    def _add_form_field(layout: QGridLayout, row: int, label: str | QLabel,
                        field: QWidget, *, span: int = 4) -> None:
        layout.addLayout(SimulationSetupPage._field_layout(label, field), row, 0, 1, span)

    @staticmethod
    def _add_field_pair(
        layout: QGridLayout,
        row: int,
        left_label: str,
        left_field,
        right_label: str,
        right_field,
    ) -> None:
        fields = QVBoxLayout()
        fields.addLayout(SimulationSetupPage._field_layout(left_label, left_field))
        fields.addLayout(SimulationSetupPage._field_layout(right_label, right_field))
        layout.addLayout(fields, row, 0, 1, 4)

    @staticmethod
    def _column_selector(placeholder: str) -> SearchableColumnComboBox:
        return SearchableColumnComboBox(placeholder)
