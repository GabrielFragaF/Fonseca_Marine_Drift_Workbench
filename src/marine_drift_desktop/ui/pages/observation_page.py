from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...domain.presets import list_column_mapping_presets
from ..components import (
    AnimatedComboBox,
    AnimatedStackedWidget,
    SearchableColumnComboBox,
    ValidationIndicator,
)
from ..icons import line_icon
from .base import WorkflowStagePage


class ObservationPage(WorkflowStagePage):
    """Observation dataset selection and canonical field mapping controls."""

    mapping_preset_changed = Signal(str)
    dataset_path_changed = Signal(str)
    browse_dataset_requested = Signal()
    _COMPACT_BREAKPOINT = 980

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Stranding data",
            "Connect your dataset and map the fields used by the reverse-drift model.",
            step_number="01",
            category="OBSERVATIONS",
            icon_name="observations",
            parent=parent,
        )
        self._available_columns: set[str] = set()
        self._compact_layout = False

        self.data_source_card, source_layout = self._card(
            "Data source",
            "Choose a local observation table. Only its header is inspected here.",
            "DataSourceCard",
            "observations",
        )
        self.source_grid = QGridLayout()
        self.source_grid.setHorizontalSpacing(12)
        self.source_grid.setVerticalSpacing(8)
        self.source_grid.setColumnStretch(1, 1)
        self.dataset_path = QLineEdit()
        self.dataset_path.setMinimumWidth(0)
        self.dataset_path.setPlaceholderText(
            "Select an observation dataset (.xlsx, .xls, .csv, or .parquet)"
        )
        self.dataset_path.textChanged.connect(self.dataset_path_changed)
        self.browse_button = QPushButton("Browse")
        self.browse_button.setProperty("variant", "secondary")
        self.browse_button.setToolTip("Select an observation dataset file.")
        self.browse_button.setMinimumWidth(92)
        self.browse_button.clicked.connect(self.browse_dataset_requested)
        self.mapping_preset = AnimatedComboBox()
        self.mapping_preset.addItems(list_column_mapping_presets())
        self.mapping_preset.currentTextChanged.connect(self.mapping_preset_changed)

        self.dataset_path_label = self._field_label("Observation dataset", True)
        self.mapping_preset_label = self._field_label("Mapping profile")
        self.source_grid.addWidget(self.dataset_path_label, 0, 0)
        self.source_grid.addWidget(self.dataset_path, 0, 1)
        self.source_grid.addWidget(self.browse_button, 0, 2)
        self.source_grid.addWidget(self.mapping_preset_label, 1, 0)
        self.source_grid.addWidget(self.mapping_preset, 1, 1, 1, 2)
        source_layout.addLayout(self.source_grid)

        metadata = QFrame()
        metadata.setObjectName("SourceMetadata")
        self.source_metadata_layout = QGridLayout(metadata)
        self.source_metadata_layout.setContentsMargins(12, 8, 12, 8)
        self.source_metadata_layout.setHorizontalSpacing(16)
        self.source_filename = self._metadata_value("No dataset selected")
        self.source_format = self._metadata_value("Not detected")
        self.source_rows = self._metadata_value("Checked during validation")
        self.source_columns = self._metadata_value("0 columns")
        self._metadata_items = (
            ("File", self.source_filename),
            ("Format", self.source_format),
            ("Records", self.source_rows),
            ("Fields", self.source_columns),
        )
        self._metadata_labels = tuple(
            self._metadata_label(label) for label, _ in self._metadata_items
        )
        for column, ((_, value), label) in enumerate(
            zip(self._metadata_items, self._metadata_labels)
        ):
            self.source_metadata_layout.addWidget(label, 0, column)
            self.source_metadata_layout.addWidget(value, 1, column)
            self.source_metadata_layout.setColumnStretch(
                column, 3 if column == 0 else 1
            )
        source_layout.addWidget(metadata)
        self.dataset_inspection = QLabel(
            "Select a dataset to detect its columns without loading its records."
        )
        self.dataset_inspection.setProperty("role", "field-hint")
        self.dataset_inspection.setWordWrap(True)
        source_layout.addWidget(self.dataset_inspection)

        self.field_mapping_card, mapping_layout = self._card(
            "Field mapping",
            "Map the basic observation fields below. Temperature, windage and measurement columns are configured in Simulation setup when the chosen method requires them.",
            "FieldMappingCard",
            "setup",
        )
        self.mapping_progress_summary = QFrame()
        self.mapping_progress_summary.setObjectName("MappingProgressSummary")
        progress_layout = QHBoxLayout(self.mapping_progress_summary)
        progress_layout.setContentsMargins(12, 8, 12, 8)
        progress_layout.setSpacing(12)
        self.mapping_progress_label = QLabel("0 of 7 required mappings complete")
        self.mapping_progress_label.setObjectName("MappingProgressLabel")
        self.mapping_progress = QProgressBar()
        self.mapping_progress.setObjectName("MappingProgress")
        self.mapping_progress.setRange(0, 7)
        self.mapping_progress.setValue(0)
        self.mapping_progress.setTextVisible(False)
        self.mapping_progress.setFixedHeight(8)
        progress_layout.addWidget(self.mapping_progress_label)
        progress_layout.addWidget(self.mapping_progress, 1)
        mapping_layout.addWidget(self.mapping_progress_summary)
        self.mapping_groups_layout = QGridLayout()
        self.mapping_groups_layout.setContentsMargins(0, 4, 0, 0)
        self.mapping_groups_layout.setHorizontalSpacing(12)
        self.mapping_groups_layout.setVerticalSpacing(12)
        mapping_layout.addLayout(self.mapping_groups_layout)

        self.identifier_column = SearchableColumnComboBox("Select identifier column")
        self.taxon_column = SearchableColumnComboBox("Select taxon column")
        self.decomposition_column = SearchableColumnComboBox("Select decomposition column")
        self.date_column = SearchableColumnComboBox("Select date column")
        self.time_column = SearchableColumnComboBox("Select time column")
        self.observed_datetime_column = SearchableColumnComboBox("Select timestamp column")
        self.lon_column = SearchableColumnComboBox("Select longitude column")
        self.lat_column = SearchableColumnComboBox("Select latitude column")
        self.mapping_indicators: dict[SearchableColumnComboBox, ValidationIndicator] = {}

        self.record_information_card, record_layout = self._mapping_group(
            "Record information",
            "Identify and classify each observation.",
            "RecordInformationCard",
            "observations",
        )
        self._add_field(record_layout, "Observation identifier", self.identifier_column, True)
        self._add_field(record_layout, "Taxon label", self.taxon_column, True)
        self._add_field(record_layout, "Decomposition code", self.decomposition_column, True)
        self.record_information_state = self._group_state_label()
        record_layout.addWidget(self.record_information_state)

        self.observation_time_card, time_layout = self._mapping_group(
            "Observation time",
            "Indicate when each observation was recorded.",
            "ObservationTimeCard",
            "clock",
        )
        self.datetime_mode = AnimatedComboBox()
        self.datetime_mode.addItem("Separate date and time columns", "separate")
        self.datetime_mode.addItem("One date and time column", "combined")
        self.datetime_mode.setToolTip(
            "Times with an explicit UTC offset are converted to UTC. "
            "Times without an offset are assumed to be UTC."
        )
        self._add_field(time_layout, "Date and time structure", self.datetime_mode, True)
        self.datetime_stack = AnimatedStackedWidget()
        self.datetime_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        separate_panel = QWidget()
        separate_layout = QVBoxLayout(separate_panel)
        separate_layout.setContentsMargins(0, 0, 0, 0)
        separate_layout.setSpacing(8)
        self._add_field(separate_layout, "Observed date", self.date_column, True)
        self._add_field(separate_layout, "Observed time", self.time_column, True)
        combined_panel = QWidget()
        combined_layout = QVBoxLayout(combined_panel)
        combined_layout.setContentsMargins(0, 0, 0, 0)
        self._add_field(combined_layout, "Observed date and time", self.observed_datetime_column, True)
        self.datetime_stack.addWidget(separate_panel)
        self.datetime_stack.addWidget(combined_panel)
        time_layout.addWidget(self.datetime_stack)
        from zoneinfo import available_timezones
        self.input_timezone = SearchableColumnComboBox("Search time interpretation or time zone")
        for label, zone in [
            ("As recorded (keep clock time)", "as_recorded"),
            ("UTC", "UTC"),
        ] + [(zone.replace("_", " "), zone) for zone in sorted(available_timezones()) if zone != "UTC"]:
            self.input_timezone.addItem(label, zone)
        self.input_timezone.setCurrentIndex(self.input_timezone.findData("as_recorded"))
        self.input_timezone.setToolTip(
            "As recorded preserves clock times, matching the original workflow. Select a source zone "
            "only to convert local civil times to UTC. Explicit timestamp offsets are always honored."
        )
        # This configures parsing; it is not a column from the observation table.
        self._add_field(time_layout, "Time interpretation / source zone", self.input_timezone, False)
        self.observation_time_state = self._group_state_label()
        time_layout.addWidget(self.observation_time_state)
        self.datetime_mode.currentIndexChanged.connect(self._datetime_mode_changed)

        self.spatial_position_card, spatial_layout = self._mapping_group(
            "Spatial position",
            "Locate each observation in a consistent coordinate notation.",
            "SpatialPositionCard",
            "location",
        )
        self._add_field(spatial_layout, "Latitude", self.lat_column, True)
        self._add_field(spatial_layout, "Longitude", self.lon_column, True)
        self.coordinate_format = AnimatedComboBox()
        self.coordinate_format.addItem("Decimal degrees (e.g. -23.55)", "decimal_degrees")
        self.coordinate_format.addItem("Degrees, minutes, seconds", "degrees_minutes_seconds")
        self._add_field(spatial_layout, "Coordinate notation", self.coordinate_format, True)
        self.spatial_position_state = self._group_state_label()
        spatial_layout.addWidget(self.spatial_position_state)

        self._mapping_cards = (
            self.record_information_card,
            self.observation_time_card,
            self.spatial_position_card,
        )
        for index, card in enumerate(self._mapping_cards):
            self.mapping_groups_layout.addWidget(card, 0, index)
        for selector in self._mapping_selectors():
            selector.currentTextChanged.connect(self._refresh_mapping_states)
        for combo in (self.mapping_preset, self.coordinate_format, self.datetime_mode, self.input_timezone):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(16)

        self.content_layout.addWidget(self.data_source_card)
        self.content_layout.addWidget(self.field_mapping_card)
        self.content_layout.addStretch(1)
        self._datetime_mode_changed()

    def _card(
        self, title: str, description: str, object_name: str, icon_name: str
    ) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName(object_name)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(line_icon(icon_name, "#087a91", 20).pixmap(20, 20))
        icon.setFixedSize(24, 24)
        text = QVBoxLayout()
        text.setSpacing(1)
        title_label = QLabel(title)
        title_label.setProperty("role", "section-title")
        copy = QLabel(description)
        copy.setProperty("role", "field-hint")
        copy.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(copy)
        heading.addWidget(icon, 0, Qt.AlignTop)
        heading.addLayout(text, 1)
        layout.addLayout(heading)
        return card, layout

    def _mapping_group(
        self, title: str, description: str, object_name: str, icon_name: str
    ) -> tuple[QFrame, QVBoxLayout]:
        card, layout = self._card(title, description, object_name, icon_name)
        card.setProperty("role", "mapping-group")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        return card, layout

    def _field_label(self, text: str, required: bool = False) -> QLabel:
        label = QLabel(f"{text}{' *' if required else ''}")
        label.setProperty("role", "field-label")
        if required:
            label.setProperty("required", True)
        return label

    def _add_field(
        self, layout: QVBoxLayout, label: str, control: QWidget, required: bool = False
    ) -> None:
        layout.addWidget(self._field_label(label, required))
        if isinstance(control, SearchableColumnComboBox) and required:
            row = QHBoxLayout()
            row.setSpacing(6)
            indicator = ValidationIndicator()
            self.mapping_indicators[control] = indicator
            row.addWidget(control, 1)
            row.addWidget(indicator)
            layout.addLayout(row)
        else:
            layout.addWidget(control)

    def _metadata_label(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setProperty("role", "metadata-label")
        return label

    def _metadata_value(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "metadata-value")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMinimumWidth(0)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setWordWrap(True)
        return label

    def _group_state_label(self) -> QLabel:
        label = QLabel()
        label.setObjectName("MappingGroupState")
        return label

    def _mapping_selectors(self) -> tuple[SearchableColumnComboBox, ...]:
        return (
            self.identifier_column,
            self.taxon_column,
            self.decomposition_column,
            self.date_column,
            self.time_column,
            self.observed_datetime_column,
            self.lon_column,
            self.lat_column,
        )

    def _datetime_mode_changed(self, *_: object) -> None:
        self.datetime_stack.setCurrentIndex(
            1 if self.datetime_mode.currentData() == "combined" else 0
        )
        self._refresh_mapping_states()

    def set_dataset_metadata(
        self, filename: str, file_format: str, row_summary: str, column_count: int
    ) -> None:
        self.source_filename.setText(filename or "No dataset selected")
        self.source_filename.setToolTip(filename)
        self.source_format.setText(file_format or "Not detected")
        self.source_rows.setText(row_summary)
        self.source_columns.setText(f"{column_count:,} columns")

    def update_mapping_states(self, columns: Iterable[str]) -> None:
        self._available_columns = {str(column).strip() for column in columns}
        self._refresh_mapping_states()

    def _refresh_mapping_states(self, *_: object) -> None:
        time_selectors = (
            (self.observed_datetime_column,)
            if self.datetime_mode.currentData() == "combined"
            else (self.date_column, self.time_column)
        )
        groups = (
            (self.record_information_card, self.record_information_state,
             (self.identifier_column, self.taxon_column, self.decomposition_column)),
            (self.observation_time_card, self.observation_time_state, time_selectors),
            (self.spatial_position_card, self.spatial_position_state,
             (self.lat_column, self.lon_column)),
        )
        for card, label, selectors in groups:
            selected = [selector.currentText().strip() for selector in selectors]
            if not all(selected):
                state, copy = "incomplete", "Complete the required mappings"
            elif not self._available_columns:
                state, copy = "incomplete", "Inspect the dataset to verify mappings"
            elif not all(
                value in self._available_columns for value in selected
            ):
                state, copy = "error", "One or more columns were not found"
            else:
                state, copy = "valid", "Required fields mapped"
            card.setProperty("state", state)
            label.setProperty("state", state)
            label.setText(copy)
            self._refresh_style(card)
            self._refresh_style(label)

        active_time_selectors = tuple(time_selectors)
        inactive_time_selectors = (
            (self.date_column, self.time_column)
            if self.datetime_mode.currentData() == "combined"
            else (self.observed_datetime_column,)
        )
        required_selectors = (
            self.identifier_column,
            self.taxon_column,
            self.decomposition_column,
            *active_time_selectors,
            self.lat_column,
            self.lon_column,
        )
        for selector, indicator in self.mapping_indicators.items():
            value = selector.currentText().strip()
            if selector in inactive_time_selectors or not value or not self._available_columns:
                indicator.set_state("idle")
            elif value in self._available_columns:
                indicator.set_state("valid")
            else:
                indicator.set_state("error")
        complete = sum(
            bool(selector.currentText().strip())
            and selector.currentText().strip() in self._available_columns
            for selector in required_selectors
        )
        total = len(required_selectors)
        self.mapping_progress.setRange(0, total)
        self.mapping_progress.setValue(complete)
        self.mapping_progress_label.setText(
            f"{complete} of {total} basic mappings complete"
        )
        progress_state = "valid" if complete == total else "incomplete"
        self.mapping_progress_summary.setProperty("state", progress_state)
        self._refresh_style(self.mapping_progress_summary)

    def set_compact_layout(self, compact: bool) -> None:
        current_rows = [
            self.mapping_groups_layout.getItemPosition(index)[0]
            for index in range(self.mapping_groups_layout.count())
        ]
        expected_rows = [0, 1, 2] if compact else [0, 0, 0]
        if self._compact_layout == compact and current_rows == expected_rows:
            return
        self._compact_layout = compact
        for widget in (
            self.dataset_path_label,
            self.dataset_path,
            self.browse_button,
            self.mapping_preset_label,
            self.mapping_preset,
        ):
            self.source_grid.removeWidget(widget)
        if compact:
            self.source_grid.addWidget(self.dataset_path_label, 0, 0, 1, 3)
            self.source_grid.addWidget(self.dataset_path, 1, 0, 1, 2)
            self.source_grid.addWidget(self.browse_button, 1, 2)
            self.source_grid.addWidget(self.mapping_preset_label, 2, 0, 1, 3)
            self.source_grid.addWidget(self.mapping_preset, 3, 0, 1, 3)
        else:
            self.source_grid.addWidget(self.dataset_path_label, 0, 0)
            self.source_grid.addWidget(self.dataset_path, 0, 1)
            self.source_grid.addWidget(self.browse_button, 0, 2)
            self.source_grid.addWidget(self.mapping_preset_label, 1, 0)
            self.source_grid.addWidget(self.mapping_preset, 1, 1, 1, 2)

        for label, (_, value) in zip(self._metadata_labels, self._metadata_items):
            self.source_metadata_layout.removeWidget(label)
            self.source_metadata_layout.removeWidget(value)
        for index, (label, (_, value)) in enumerate(
            zip(self._metadata_labels, self._metadata_items)
        ):
            row = (index // 2) * 2 if compact else 0
            column = index % 2 if compact else index
            self.source_metadata_layout.addWidget(label, row, column)
            self.source_metadata_layout.addWidget(value, row + 1, column)
        for column in range(4):
            self.source_metadata_layout.setColumnStretch(
                column, (1 if column < 2 else 0) if compact else (3 if column == 0 else 1)
            )

        for card in self._mapping_cards:
            self.mapping_groups_layout.removeWidget(card)
        for index, card in enumerate(self._mapping_cards):
            row, column = (index, 0) if compact else (0, index)
            self.mapping_groups_layout.addWidget(card, row, column)
        for column in range(3):
            self.mapping_groups_layout.setColumnStretch(column, 1 if not compact else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_compact_layout(event.size().width() < self._COMPACT_BREAKPOINT)

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
