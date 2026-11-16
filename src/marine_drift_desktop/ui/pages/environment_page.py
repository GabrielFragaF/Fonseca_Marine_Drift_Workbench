from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ..components import ActionButton
from ...core.forcing_validation import ForcingReadiness
from ..environment_catalog import (
    ROLE_OPTIONS,
    EnvironmentalCatalogEntry,
    EnvironmentalCatalogModel,
)
from ..icons import line_icon
from .base import WorkflowStagePage


class EnvironmentPage(WorkflowStagePage):
    """Scalable environmental dataset catalog and selected-file inspector."""

    _COMPACT_BREAKPOINT = 1_000

    browse_directory_requested = Signal(object)
    add_files_requested = Signal()
    add_folder_requested = Signal()
    remove_selected_requested = Signal()
    coverage_preview_requested = Signal()
    catalog_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Environmental forcing",
            "Add local environmental datasets, assign model roles, and inspect coverage.",
            step_number="02",
            category="ENVIRONMENT",
            icon_name="forcing",
            parent=parent,
        )
        self._syncing_roles = False
        self._compact_layout = False
        self.catalog_model = EnvironmentalCatalogModel(self)
        self.catalog_model.catalogChanged.connect(self._catalog_updated)
        self._build_output_controls()
        self.content_layout.addWidget(self._build_catalog_workspace())
        self.readiness_group = self._build_readiness_summary()
        self.content_layout.addWidget(self.readiness_group)
        self.content_layout.addStretch(1)

    def _build_output_controls(self) -> None:
        self.output_group = QGroupBox("Output folder")
        layout = QGridLayout(self.output_group)
        layout.setColumnStretch(1, 1)
        self.output_directory = QLineEdit()
        self.output_directory.setPlaceholderText(
            "Choose a directory for generated trajectories and reports"
        )
        browse = QPushButton("Browse")
        browse.setProperty("variant", "secondary")
        browse.clicked.connect(
            lambda: self.browse_directory_requested.emit(self.output_directory)
        )
        layout.addWidget(QLabel("Output directory"), 0, 0)
        layout.addWidget(self.output_directory, 0, 1)
        layout.addWidget(browse, 0, 2)

    def _build_catalog_workspace(self) -> QGroupBox:
        group = QGroupBox("Environmental datasets")
        self.catalog_group = group
        group.setObjectName("ReaderCatalog")
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        group.setMaximumHeight(380)
        layout = QVBoxLayout(group)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        self.add_files_button = ActionButton("Add NetCDF files", variant="primary")
        self.add_files_button.setIcon(line_icon("netcdf", "#ffffff", 18))
        self.add_folder_button = ActionButton("Add folder", variant="secondary")
        self.add_folder_button.setIcon(line_icon("folder", "#159ab5", 18))
        self.remove_selected_button = ActionButton("Remove selected", variant="ghost")
        self.remove_selected_button.setIcon(line_icon("close", "#c95f5f", 17))
        self.remove_selected_button.setEnabled(False)
        self.catalog_count = QLabel("0 datasets")
        self.catalog_count.setProperty("role", "field-hint")
        toolbar.addWidget(self.add_files_button)
        toolbar.addWidget(self.add_folder_button)
        toolbar.addWidget(self.remove_selected_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.catalog_count)
        layout.addLayout(toolbar)

        self.catalog_splitter = QSplitter(Qt.Horizontal)
        self.catalog_splitter.setChildrenCollapsible(False)
        self.catalog_splitter.addWidget(self._build_table_panel())
        self.catalog_splitter.addWidget(self._build_inspector_panel())
        self.catalog_splitter.setStretchFactor(0, 2)
        self.catalog_splitter.setStretchFactor(1, 1)
        self.catalog_splitter.setSizes([850, 410])
        self.catalog_splitter.setMinimumHeight(220)
        layout.addWidget(self.catalog_splitter)

        self.empty_state = QLabel(
            "Add one or more .nc or .nc4 files. Files are inspected locally and are never uploaded."
        )
        self.empty_state.setProperty("role", "field-hint")
        self.empty_state.setWordWrap(True)
        layout.addWidget(self.empty_state)
        self.add_files_button.clicked.connect(self.add_files_requested.emit)
        self.add_folder_button.clicked.connect(self.add_folder_requested.emit)
        self.remove_selected_button.clicked.connect(self.remove_selected_requested.emit)
        return group

    def _build_table_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("DatasetTablePanel")
        panel.setMinimumWidth(360)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        title = QLabel("Dataset catalog")
        title.setProperty("role", "dataset-title")
        layout.addWidget(title)
        self.catalog_view = QTableView()
        self.catalog_view.setObjectName("EnvironmentCatalogView")
        self.catalog_view.setModel(self.catalog_model)
        self.catalog_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.catalog_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.catalog_view.setSortingEnabled(True)
        self.catalog_view.setAlternatingRowColors(True)
        self.catalog_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.catalog_view.verticalHeader().setVisible(False)
        header = self.catalog_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
        self.catalog_view.setColumnWidth(1, 108)
        self.catalog_view.setColumnWidth(2, 180)
        self.catalog_view.setColumnWidth(3, 185)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.catalog_view.selectionModel().selectionChanged.connect(
            self._selection_changed
        )
        layout.addWidget(self.catalog_view)
        return panel

    def _build_inspector_panel(self) -> QWidget:
        panel = QFrame()
        self.inspector_panel = panel
        panel.setObjectName("DatasetInspectorPanel")
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(420)
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(10, 6, 6, 6)
        self.inspector_scroll = QScrollArea()
        self.inspector_scroll.setWidgetResizable(True)
        self.inspector_scroll.setFrameShape(QFrame.NoFrame)
        self.inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(0, 0, 8, 0)
        self.inspector_scroll.setWidget(body)
        outer.addWidget(self.inspector_scroll)
        self.inspector_title = QLabel("Select a dataset")
        self.inspector_title.setProperty("role", "dataset-title")
        self.inspector_path = QLabel(
            "Choose a catalog row to inspect its roles, variables, and coverage."
        )
        self.inspector_path.setProperty("role", "field-hint")
        self.inspector_path.setWordWrap(True)
        self.inspector_path.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.inspector_title)
        layout.addWidget(self.inspector_path)
        role_title = QLabel("Model roles")
        role_title.setProperty("role", "section-kicker")
        layout.addWidget(role_title)
        self.role_list = QListWidget()
        self.role_list.setMinimumHeight(84)
        self.role_list.setMaximumHeight(108)
        self.role_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.role_list.setWordWrap(True)
        self.role_items: list[QListWidgetItem] = []
        for role in ROLE_OPTIONS:
            item = QListWidgetItem(role)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.role_list.addItem(item)
            self.role_items.append(item)
        self.role_list.itemChanged.connect(self._roles_changed)
        layout.addWidget(self.role_list)
        self.role_source = QLabel("Role assignment: needs review")
        self.role_source.setProperty("role", "field-hint")
        layout.addWidget(self.role_source)
        self.time_coverage = QLabel("Time coverage: not inspected")
        self.spatial_coverage = QLabel("Spatial coverage: not inspected")
        self.grid_summary = QLabel("Grid: not inspected")
        self.compatibility = QLabel("OpenDrift compatibility: not inspected")
        self.variables_summary = QLabel("Recognized variables: not inspected")
        for label in (
            self.time_coverage,
            self.spatial_coverage,
            self.grid_summary,
            self.compatibility,
            self.variables_summary,
        ):
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            layout.addWidget(label)
        self.preview_coverage_button = ActionButton(
            "Preview coverage", variant="secondary"
        )
        self.preview_coverage_button.setIcon(line_icon("location", "#159ab5", 17))
        self.preview_coverage_button.setEnabled(False)
        self.preview_coverage_button.clicked.connect(
            self.coverage_preview_requested.emit
        )
        layout.addWidget(self.preview_coverage_button)
        layout.addStretch(1)
        return panel

    def set_compact_layout(self, compact: bool) -> None:
        if compact == self._compact_layout:
            return
        self._compact_layout = compact
        self.catalog_splitter.setOrientation(Qt.Horizontal)
        for column in (2, 3):
            self.catalog_view.setColumnHidden(column, compact)
        self.catalog_view.setToolTip(
            "Select a dataset to see its full time and spatial coverage in the inspector."
            if compact else "Select a dataset to inspect its variables, roles, and coverage."
        )
        if compact:
            self.catalog_view.setColumnWidth(1, 80)
            self.catalog_view.setColumnWidth(2, 125)
            self.catalog_view.setColumnWidth(3, 125)
            self.inspector_panel.setMinimumWidth(240)
            self.inspector_panel.setMaximumWidth(300)
            self.inspector_panel.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            self.catalog_group.setMaximumHeight(380)
            self.catalog_splitter.setSizes([530, 250])
        else:
            self.catalog_view.setColumnWidth(1, 108)
            self.catalog_view.setColumnWidth(2, 180)
            self.catalog_view.setColumnWidth(3, 185)
            self.inspector_panel.setMinimumWidth(280)
            self.inspector_panel.setMaximumWidth(420)
            self.inspector_panel.setSizePolicy(
                QSizePolicy.Ignored, QSizePolicy.Preferred
            )
            maximum_height = 380 if self.catalog_model.rowCount() <= 2 else 470
            self.catalog_group.setMaximumHeight(maximum_height)
            self.catalog_splitter.setSizes([850, 410])

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.set_compact_layout(event.size().width() < self._COMPACT_BREAKPOINT)

    def _build_readiness_summary(self) -> QGroupBox:
        group = QGroupBox("Forcing readiness")
        group.setObjectName("ForcingReadiness")
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(10)
        keys = (
            ("required_currents", "Required currents"),
            ("temporal_coverage", "Temporal coverage"),
            ("spatial_coverage", "Spatial coverage"),
            ("optional_forcing", "Optional forcing"),
            ("unused_datasets", "Unused datasets"),
        )
        self.readiness_labels: dict[str, QLabel] = {}
        for column, (key, title) in enumerate(keys):
            label = QLabel(f"{title}\nNot evaluated")
            label.setObjectName("ForcingCheck")
            label.setProperty("level", "idle")
            label.setWordWrap(True)
            label.setMinimumHeight(64)
            self.readiness_labels[key] = label
            layout.addWidget(label, 0, column)
            layout.setColumnStretch(column, 1)
        return group

    def selected_rows(self) -> list[int]:
        return sorted(
            {index.row() for index in self.catalog_view.selectionModel().selectedRows()}
        )

    def refresh_selected_entry(self) -> None:
        rows = self.selected_rows()
        self._show_entry(self.catalog_model.entry_at(rows[0]) if rows else None)

    def selected_entry(self) -> EnvironmentalCatalogEntry | None:
        rows = self.selected_rows()
        return self.catalog_model.entry_at(rows[0]) if rows else None

    def set_readiness(self, readiness: ForcingReadiness | None) -> None:
        checks = {check.key: check for check in readiness.checks} if readiness else {}
        for key, label in self.readiness_labels.items():
            check = checks.get(key)
            if check is None:
                title = label.text().splitlines()[0]
                label.setText(f"{title}\nNot evaluated")
                label.setProperty("level", "idle")
            else:
                label.setText(f"{check.title}\n{check.detail}")
                label.setProperty("level", check.level)
            label.style().unpolish(label)
            label.style().polish(label)

    def _selection_changed(self, *_: object) -> None:
        rows = self.selected_rows()
        self.remove_selected_button.setEnabled(bool(rows))
        self._show_entry(self.catalog_model.entry_at(rows[0]) if rows else None)

    def _catalog_updated(self) -> None:
        count = self.catalog_model.rowCount()
        self.catalog_count.setText(f"{count} dataset{'s' if count != 1 else ''}")
        self.empty_state.setVisible(count == 0)
        maximum_height = (
            380 if self._compact_layout or count <= 2 else 470
        )
        self.catalog_group.setMaximumHeight(maximum_height)
        self.refresh_selected_entry()
        self.catalog_changed.emit()

    def _show_entry(self, entry: EnvironmentalCatalogEntry | None) -> None:
        self._syncing_roles = True
        try:
            roles = set(entry.roles) if entry else set()
            for item in self.role_items:
                item.setCheckState(Qt.Checked if item.text() in roles else Qt.Unchecked)
        finally:
            self._syncing_roles = False
        if entry is None:
            self.inspector_title.setText("Select a dataset")
            self.inspector_path.setText(
                "Choose a catalog row to inspect its roles, variables, and coverage."
            )
            self.role_source.setText("Role assignment: needs review")
            self.preview_coverage_button.setEnabled(False)
            return
        self.inspector_title.setText(entry.path.name)
        self.inspector_path.setText(str(entry.path))
        self.role_source.setText(
            f"Role assignment: {entry.role_source.replace('_', ' ')}"
        )
        inspection = entry.inspection
        if inspection is None:
            state = entry.error_message or "Inspection pending"
            self.time_coverage.setText(f"Time coverage: {state}")
            self.spatial_coverage.setText("Spatial coverage: not available")
            self.grid_summary.setText("Grid: not available")
            self.compatibility.setText("OpenDrift compatibility: not available")
            self.variables_summary.setText("Recognized variables: not available")
            self.preview_coverage_button.setEnabled(False)
            return
        temporal = (
            f"{inspection.time_start} to {inspection.time_end}"
            if inspection.time_start and inspection.time_end
            else "not available"
        )
        self.time_coverage.setText(f"Time coverage: {temporal}")
        if inspection.extent is not None:
            extent = inspection.extent
            spatial = (
                f"lon {extent.min_longitude:.3f} to {extent.max_longitude:.3f}; "
                f"lat {extent.min_latitude:.3f} to {extent.max_latitude:.3f}"
            )
        else:
            spatial = inspection.coverage_warning or "not available"
        self.spatial_coverage.setText(f"Spatial coverage: {spatial}")
        resolution = (
            f"{inspection.longitude_resolution:g} x {inspection.latitude_resolution:g} degrees"
            if inspection.longitude_resolution is not None
            and inspection.latitude_resolution is not None
            else "resolution unavailable"
        )
        self.grid_summary.setText(
            f"Grid: {inspection.grid_type}; {resolution}; CRS {inspection.crs or 'not declared'}"
        )
        self.compatibility.setText(inspection.compatibility_message)
        variables = ", ".join(inspection.recognized_opendrift_variables) or "none"
        self.variables_summary.setText(f"Recognized variables: {variables}")
        self.preview_coverage_button.setEnabled(inspection.extent is not None)

    def _roles_changed(self, *_: object) -> None:
        if self._syncing_roles:
            return
        rows = self.selected_rows()
        if not rows:
            return
        entry = self.catalog_model.entry_at(rows[0])
        roles = [
            item.text() for item in self.role_items if item.checkState() == Qt.Checked
        ]
        self.catalog_model.update_roles(entry.path, roles, source="user")
