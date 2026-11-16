from __future__ import annotations

from copy import deepcopy
import json
import time
from dataclasses import dataclass
from pathlib import Path
import sys

from PySide6.QtCore import QEventLoop, QProcess, QSignalBlocker, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.environment import intersect_extents, resolve_environment_extent
from ..core.preflight import PreflightResult
from ..core.request_serialization import write_simulation_request
from ..core.project_files import ProjectDocument, ProjectFileError, read_project, write_project
from ..core.results_serialization import write_results_export_request
from ..domain.results import ResultsExportRequest
from ..version import VERSION, BUILD_ID
from ..domain.models import (
    EnvironmentalReaderConfig,
    FilterCondition,
    SimulationRequest,
    SimulationSummary,
    SpatialExtent,
)
from ..domain.presets import (
    get_column_mapping_preset,
    get_study_area_preset,
)
from ..core.io import read_observation_columns
from .components import (
    ActionButton,
    AnimatedComboBox,
    AnimatedStackedWidget,
    SearchableColumnComboBox,
)
from .icons import line_icon
from .environment_catalog import EnvironmentInspectionWorker
from .pages.environment_page import EnvironmentPage
from .pages.observation_page import ObservationPage
from .pages.review_run_page import ReviewRunPage, ReviewRunState, RunSummaryValues
from .pages.results_export_page import ResultsExportPage, ResultsExportState
from .pages.simulation_setup_page import SimulationSetupPage
from .preflight_worker import PreflightWorker
from .observation_values_worker import ObservationValuesWorker
from .results_export_controller import ResultsExportController
from .welcome import GuidedTour, WelcomePage
from .validation_feedback import ValidationFeedbackMixin


@dataclass(slots=True)
class _FilterConditionRow:
    container: QWidget
    column: AnimatedComboBox
    operator: AnimatedComboBox
    value: QLineEdit
    connector: AnimatedComboBox
    remove_button: ActionButton


class MarineDriftMainWindow(ValidationFeedbackMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Marine Drift Workbench {VERSION} ({BUILD_ID})")
        self.resize(1500, 920)
        self.setMinimumSize(1024, 700)

        self.request = SimulationRequest()
        self.active_project_path: Path | None = None
        self.project_dirty = False
        self._restoring_project = False
        self._is_validated = False
        self._simulation_process: QProcess | None = None
        self._simulation_process_buffer = ""
        self._simulation_finished_event = False
        self._simulation_cancelled = False
        self._preflight_worker: PreflightWorker | None = None
        self._preflight_generation = 0
        self._preflight_minimum_until = 0.0
        self._last_preflight_result: PreflightResult | None = None
        self._environment_inspection_workers: set[EnvironmentInspectionWorker] = set()
        self._observation_value_workers: set[ObservationValuesWorker] = set()
        self._results_controller = ResultsExportController(self)
        self._results_controller.event_received.connect(self._handle_results_event)
        self._results_controller.operation_failed.connect(self._results_operation_failed)
        self._results_controller.operation_finished.connect(self._results_operation_finished)
        self.request_state = QPushButton("Draft")
        self.request_state.setCursor(Qt.PointingHandCursor)
        self.request_state.setToolTip("Open Review & run to check the current configuration")
        self.request_state.clicked.connect(lambda: self.stage_navigation.setCurrentRow(3))
        self.stage_state = QLabel("Stranding data")
        self.preview_health = ActionButton("Not checked", variant="quiet")
        self.preview_health.setCursor(Qt.PointingHandCursor)
        self.preview_health.clicked.connect(self._show_validation_issues)
        self.dataset_inspection_timer = QTimer(self)
        self.dataset_inspection_timer.setSingleShot(True)
        self.dataset_inspection_timer.setInterval(300)
        self.dataset_inspection_timer.timeout.connect(
            self._inspect_observation_dataset
        )

        root = QFrame()
        root.setObjectName("RootFrame")
        self.workspace_stack = QStackedWidget()
        self.setCentralWidget(self.workspace_stack)
        self.welcome_page = WelcomePage()
        self.workspace_stack.addWidget(self.welcome_page)
        self.workspace_stack.addWidget(root)
        self.workspace_stack.setCurrentIndex(1)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(self._build_status_header(), 0)
        layout.addWidget(self._build_body(), 1)
        layout.addWidget(self._build_workflow_footer(), 0)
        self._connect_dirty_tracking()
        self._build_project_actions()
        self.guided_tour = GuidedTour(self)
        self.welcome_page.new_project_requested.connect(self.new_project)
        self.welcome_page.open_project_requested.connect(self.open_project)
        self.welcome_page.tutorial_requested.connect(self.start_tutorial)

    def show_home(self) -> None:
        if self.guided_tour.isVisible():
            self.guided_tour.finish()
        self.workspace_stack.setCurrentIndex(0)

    def show_workbench(self) -> None:
        self.workspace_stack.setCurrentIndex(1)

    def start_tutorial(self) -> None:
        self.show_workbench()
        self.guided_tour.start()

    def apply_project(self, document: ProjectDocument) -> None:
        self._clear_validation_feedback()
        self._restoring_project = True
        self._preflight_generation += 1
        blockers = [QSignalBlocker(widget) for widget in self.findChildren(QWidget)]
        try:
            self.request = deepcopy(document.request)
            self.project_name.setText(document.name)
            self._update_project_title()
            source = self.request.data_sources
            self.dataset_path.setText(str(source.observation_dataset or ""))
            self.output_directory.setText(str(source.output_directory or ""))
            self.dataset_inspection_timer.stop()

            mapping = self.request.column_mapping
            for selector in (self.identifier_column, self.taxon_column, self.decomposition_column,
                             self.sst_column, self.wind_column, self.lon_column, self.lat_column,
                             self.date_column, self.time_column, self.observed_datetime_column,
                             self.duration_column, self.measurement_column):
                selector.clear()
                selector.addItem("")
            for selector, value in (
                (self.identifier_column, mapping.stranding_identifier),
                (self.taxon_column, mapping.taxon_label),
                (self.decomposition_column, mapping.decomposition_code),
                (self.sst_column, mapping.sea_surface_temperature),
                (self.wind_column, mapping.wind_drift_factor),
                (self.lon_column, mapping.longitude),
                (self.lat_column, mapping.latitude),
                (self.date_column, mapping.observed_date),
                (self.time_column, mapping.observed_time),
                (self.observed_datetime_column, mapping.observed_datetime),
            ):
                self._set_selector_text(selector, value)
            self._set_combo_data(self.datetime_mode, mapping.datetime_mode)
            self._set_combo_data(self.input_timezone, mapping.input_timezone)
            self.observation_page._datetime_mode_changed()

            self.environment_readers = deepcopy(source.environment_readers)
            self.environment_catalog_model.set_configs(self.environment_readers)

            settings = self.request.settings
            strategy = "multiple" if settings.iteration_count > 1 else "single"
            if settings.start_time_mode == "fixed_hour":
                strategy = "multiple_fixed" if settings.iteration_count > 1 else "fixed_hour"
            self._set_combo_data(self.release_strategy, strategy)
            self.iteration_count.setValue(settings.iteration_count)
            self.iteration_interval.setValue(settings.iteration_interval_hours)
            self.model_time_step.setValue(settings.model_time_step_hours)
            self._set_combo_data(self.start_time_mode, settings.start_time_mode)
            self.fixed_start_hour.setValue(settings.fixed_start_hour)
            self.particle_count.setValue(settings.particle_count)
            self.release_radius.setValue(settings.release_radius_meters)
            self.current_uncertainty_toggle.setChecked(settings.current_uncertainty_enabled)
            self.current_uncertainty.setValue(settings.current_uncertainty)
            self.wind_uncertainty_toggle.setChecked(settings.wind_uncertainty_enabled)
            self.wind_uncertainty.setValue(settings.wind_uncertainty)
            self._set_combo_data(self.coastline_action, settings.coastline_action)
            for name, checkbox in self.simulation_setup_page.environment_export_checks.items():
                checkbox.setChecked(name in settings.environment_export_variables)
            self._set_combo_data(self.coordinate_format, settings.coordinate_format)
            fallback = settings.fallback_values
            self.current_fallback_toggle.setChecked(fallback.currents_enabled)
            self.wind_fallback_toggle.setChecked(fallback.wind_enabled)
            self.stokes_fallback_toggle.setChecked(fallback.stokes_drift_enabled)
            self.depth_fallback_toggle.setChecked(fallback.seafloor_depth_enabled)
            self.current_fallback_x.setValue(fallback.x_sea_water_velocity)
            self.current_fallback_y.setValue(fallback.y_sea_water_velocity)
            self.wind_fallback_x.setValue(fallback.x_wind)
            self.wind_fallback_y.setValue(fallback.y_wind)
            self.stokes_fallback_x.setValue(fallback.stokes_drift_x_velocity)
            self.stokes_fallback_y.setValue(fallback.stokes_drift_y_velocity)
            self.depth_fallback_value.setValue(fallback.sea_floor_depth_below_sea_level)

            extent = settings.extent
            self.min_lon.setValue(extent.min_longitude)
            self.max_lon.setValue(extent.max_longitude)
            self.min_lat.setValue(extent.min_latitude)
            self.max_lat.setValue(extent.max_latitude)
            environmental = settings.coverage.mode == "environment_intersection"
            self._set_combo_data(self.study_area_preset, "environment_intersection" if environmental else "manual")
            self.coverage_toggle.setChecked(environmental)
            self.coverage_buffer.setValue(settings.coverage.buffer_degrees)

            search = settings.position_search
            self._set_combo_data(self.simulation_setup_page.position_direct_policy,
                                 "skip_if_invalid" if search.mode == "skip_if_invalid" else "direct")
            self.position_search_toggle.setChecked(search.mode == "search_nearby_water")
            self.position_radial_step.setValue(search.radial_step_degrees)
            self.position_max_radius.setValue(search.max_radius_degrees)
            self.position_angle_step.setValue(search.angle_step_degrees)
            self.position_max_attempts.setValue(search.max_attempts)
            self._set_combo_data(self.position_failure_behavior, search.failure_behavior)

            duration = settings.duration
            self._set_combo_data(self.duration_mode, duration.mode)
            self.fixed_duration_days.setValue(duration.fixed_days)
            self._set_selector_text(self.duration_column, duration.duration_column)
            boundaries = duration.temperature_boundaries_celsius or [duration.temperature_threshold_celsius]
            scenarios = duration.scenario_days or {
                state: [duration.cool_water_days.get(state, 1), duration.warm_water_days.get(state, 1)]
                for state in sorted(set(duration.cool_water_days) | set(duration.warm_water_days))
            }
            self.simulation_setup_page.set_duration_profile(
                boundaries, scenarios, duration.decomposition_value_map
            )

            wind = settings.wind_drift
            self._set_combo_data(self.wind_mode, wind.mode)
            self._set_combo_data(self.wind_scale, wind.source_scale)
            self.fixed_wind_percent.setValue(wind.fixed_percent)
            self._set_selector_text(self.measurement_column, wind.measurement_column)
            self._set_combo_data(self.measurement_unit, wind.measurement_unit)
            self.measurement_minimum.setValue(wind.measurement_minimum)
            self.measurement_maximum.setValue(wind.measurement_maximum)
            self.wind_min_percent.setValue(wind.wind_drift_minimum_percent)
            self.wind_max_percent.setValue(wind.wind_drift_maximum_percent)
            self._set_combo_data(self.wind_range_behavior, wind.outside_range_behavior)

            selection = settings.observation_selection
            self._set_combo_data(self.selection_mode, selection.mode)
            self.selection_sample_size.setValue(selection.sample_size)
            self.selection_random_seed.setValue(selection.random_seed)
            for row in list(self.filter_condition_rows):
                self._remove_filter_condition(row)
            for condition in selection.conditions:
                self._add_filter_condition()
                row = self.filter_condition_rows[-1]
                self._set_selector_text(row.column, condition.column)
                self._set_combo_data(row.operator, condition.operator)
                row.value.setText(", ".join(map(str, condition.values)) if condition.values else
                                  str(condition.value if condition.value is not None else ""))
                self._set_combo_data(row.connector, condition.connector)

            self._update_coverage_controls(environmental)
            self.simulation_setup_page._update_area_panels()
            self.simulation_setup_page._refresh_area_map()
            self._update_position_search_controls(self.position_search_toggle.isChecked())
            self._update_selection_controls()
            self._update_duration_controls()
            self._update_windage_controls()
            self.review_run_page.continue_errors_toggle.setChecked(settings.job_error_policy == "continue")
            self.simulation_setup_page.release_scenarios_panel.setVisible(strategy in {"multiple", "multiple_fixed"})
            self.simulation_setup_page.fixed_start_panel.setVisible(strategy in {"fixed_hour", "multiple_fixed"})
            self.simulation_setup_page._update_uncertainty_panels()
            self.simulation_setup_page._update_fallback_panels()
            self.observation_page._refresh_mapping_states()
            self.simulation_setup_page._update_summaries()
            self._is_validated = False
            self._last_preflight_result = None
            self.request_state.setText("Draft")
            self.preview_health.setText("Not checked")
            self.review_run_page.set_state(ReviewRunState.UNVALIDATED)
            self.review_run_page.reset_run_summary("Validate this project to calculate")
            self.environment_page.set_readiness(None)
            self.preview_output.clear()
            self.stage_navigation.setCurrentRow(0)
            self.show_workbench()
        finally:
            for blocker in blockers:
                blocker.unblock()
            self._restoring_project = False
        self.project_dirty = False
        self.dataset_inspection_timer.start()
        self.stage_stack.setCurrentIndex(0)
        self._update_stage_status(0)
        self.simulation_setup_page.set_current_step(0)
        self.results_export_page.set_latest_run(None)
        self.results_export_page.results_directory.clear()
        self.results_export_page.output_directory.clear()
        self.results_export_page.mark_inspection_dirty()
        self.project_dirty = False

    def reset_project(self) -> None:
        self.active_project_path = None
        request = SimulationRequest()
        request.settings.coverage.mode = "environment_intersection"
        self.apply_project(ProjectDocument("New reverse-drift project", request))

    def _build_project_actions(self) -> None:
        self.new_project_action = QAction("New project", self)
        self.new_project_action.setShortcut(QKeySequence.StandardKey.New)
        self.new_project_action.triggered.connect(self.new_project)
        self.open_project_action = QAction("Open project...", self)
        self.open_project_action.setShortcut(QKeySequence.StandardKey.Open)
        self.open_project_action.triggered.connect(self.open_project)
        self.save_project_action = QAction("Save project", self)
        self.save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_project_action.triggered.connect(self.save_project)
        self.save_as_project_action = QAction("Save project as...", self)
        self.save_as_project_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.save_as_project_action.triggered.connect(self.save_project_as)
        self.addActions([
            self.new_project_action,
            self.open_project_action,
            self.save_project_action,
            self.save_as_project_action,
        ])
        project_menu = self.menuBar().addMenu("Project")
        project_menu.addActions([self.new_project_action, self.open_project_action,
                                 self.save_project_action, self.save_as_project_action])

    def new_project(self) -> None:
        if not self._can_switch_project():
            return
        if not self._confirm_replace_project():
            return
        self.reset_project()

    def open_project(self) -> None:
        if not self._can_switch_project():
            return
        if not self._confirm_replace_project():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Marine Drift project", "", "Marine Drift projects (*.mdwproj)"
        )
        if not path:
            return
        try:
            document = read_project(Path(path))
        except ProjectFileError as exc:
            QMessageBox.critical(self, "Could not open project", str(exc))
            return
        self.apply_project(document)
        self.active_project_path = Path(path)
        missing = self._missing_project_paths(document.request)
        if missing:
            QMessageBox.warning(
                self,
                "Some files need relinking",
                "The project was loaded, but these referenced paths were not found:\n\n"
                + "\n".join(str(item) for item in missing),
            )

    def save_project(self) -> bool:
        if self.active_project_path is None:
            return self.save_project_as()
        if not self._collect_request_from_ui():
            return False
        try:
            self.active_project_path = write_project(
                ProjectDocument(self.project_name.text().strip(), deepcopy(self.request)),
                self.active_project_path,
            )
        except ProjectFileError as exc:
            QMessageBox.critical(self, "Could not save project", str(exc))
            return False
        self.project_dirty = False
        self._update_project_title()
        return True

    def save_project_as(self) -> bool:
        suggested = self.active_project_path or Path(
            f"{self.project_name.text().strip() or 'marine-drift-project'}.mdwproj"
        )
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Marine Drift project",
            str(suggested),
            "Marine Drift projects (*.mdwproj)",
        )
        if not path:
            return False
        previous = self.active_project_path
        self.active_project_path = Path(path)
        if self.save_project():
            return True
        self.active_project_path = previous
        return False

    def _can_switch_project(self) -> bool:
        if self._simulation_process is not None or self._results_controller.process is not None:
            QMessageBox.information(self, "Operation in progress",
                                    "Finish or cancel the current run or export before changing projects.")
            return False
        if any(worker.isRunning() for worker in self._environment_inspection_workers):
            QMessageBox.information(self, "Reading environmental metadata",
                                    "Wait for the dataset inspection to finish before changing projects.")
            return False
        return True

    def _confirm_replace_project(self) -> bool:
        if not self.project_dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Save project changes?",
            "The current configuration has unsaved changes.",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Cancel:
            return False
        return self.save_project() if choice == QMessageBox.Save else True

    @staticmethod
    def _missing_project_paths(request: SimulationRequest) -> list[Path]:
        paths = [path for path in request.data_sources.input_sources().values() if path]
        paths.extend(reader.path for reader in request.data_sources.environment_readers)
        return [path for path in paths if not path.exists()]

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _build_status_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("StatusHeader")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        brand_mark = QLabel()
        brand_mark.setObjectName("BrandLogo")
        brand_mark.setPixmap(line_icon("marine-drift-workbench-logo", size=44).pixmap(44, 44))
        brand_mark.setFixedSize(44, 48)
        brand_mark.setAlignment(Qt.AlignCenter)
        brand_mark.setAccessibleName("Marine Drift Workbench logo")

        title_block = QVBoxLayout()
        title_block.setSpacing(2)

        title = QLabel("Marine Drift Workbench")
        title.setObjectName("HeaderTitle")

        subtitle = QLabel(f"Local reverse-drift modelling | {VERSION}")
        subtitle.setToolTip(f"Build: {BUILD_ID}")
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setWordWrap(True)

        title_block.addWidget(title)
        title_block.addWidget(subtitle)

        layout.addWidget(brand_mark)
        layout.addLayout(title_block)
        project = QLineEdit("New reverse-drift project")
        self.project_name = project
        project.setObjectName("HeaderProject")
        project.setAccessibleName("Project name")
        project.setToolTip("Edit the name for this session. This does not rename output files.")
        project.setMinimumWidth(100)
        project.editingFinished.connect(self._update_project_title)
        project.textChanged.connect(self._mark_request_dirty)
        layout.addWidget(project, 1)
        self.home_button = ActionButton("Home")
        self.home_button.clicked.connect(self.show_home)
        self.tutorial_button = ActionButton("Tutorial")
        self.tutorial_button.clicked.connect(self.start_tutorial)
        self.save_button = ActionButton("Save")
        self.save_button.setToolTip("Save this project configuration (Ctrl+S)")
        self.save_button.clicked.connect(self.save_project)
        layout.addWidget(self.home_button)
        layout.addWidget(self.tutorial_button)
        layout.addWidget(self.save_button)
        # Keep the state label for existing status updates, without repeating navigation.
        self.stage_state.setParent(header)
        self.stage_state.hide()
        for label_text, value_widget in [
            ("CONFIGURATION", self.request_state),
            ("RUN HEALTH", self.preview_health),
        ]:
            pill, _ = self._status_pill(label_text, "", value_widget)
            layout.addWidget(pill, 0, Qt.AlignVCenter)
        return header

    def _update_project_title(self) -> None:
        name = self.project_name.text().strip() or "New reverse-drift project"
        self.project_name.setText(name)
        self.setWindowTitle(f"{name} | Marine Drift Workbench {VERSION} ({BUILD_ID})")

    def _status_pill(
        self, label_text: str, value_text: str, value_widget: QLabel | QPushButton | None = None
    ) -> tuple[QFrame, QLabel | QPushButton]:
        pill = QFrame()
        pill.setObjectName("StatusPill")

        layout = QHBoxLayout(pill)
        layout.setContentsMargins(12, 6, 12, 6)
        pill.setToolTip(label_text.capitalize())

        value = value_widget or QLabel(value_text)
        value.setProperty("role", "pill-value")

        value.setAccessibleName(label_text.capitalize())
        layout.addWidget(value)
        return pill, value

    def _build_body(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        self.workbench_splitter = splitter
        splitter.setObjectName("WorkbenchSplitter")
        splitter.setChildrenCollapsible(False)

        self.stage_stack = AnimatedStackedWidget()
        self.stage_stack.setObjectName("StageStack")
        self.simulation_setup_page = SimulationSetupPage()
        self._bind_simulation_setup_page(self.simulation_setup_page)
        self.observation_page = ObservationPage()
        self._bind_observation_page(self.observation_page)
        self.stage_stack.addWidget(self.observation_page)
        self.environment_page = EnvironmentPage()
        self._bind_environment_page(self.environment_page)
        self.stage_stack.addWidget(self.environment_page)
        self.stage_stack.addWidget(self.simulation_setup_page)
        self.review_run_page = ReviewRunPage(self.output_group)
        self._bind_review_run_page(self.review_run_page)
        self.stage_stack.addWidget(self.review_run_page)
        self.results_export_page = ResultsExportPage()
        self._bind_results_export_page(self.results_export_page)
        self.stage_stack.addWidget(self.results_export_page)

        navigation_rail, self.stage_navigation = self._build_stage_navigation()
        self.stage_navigation.currentRowChanged.connect(self.stage_stack.setCurrentIndex)
        self.stage_navigation.currentRowChanged.connect(self._update_stage_status)

        splitter.addWidget(navigation_rail)
        splitter.addWidget(self.stage_stack)
        splitter.setSizes([210, 1250])
        return splitter

    def _build_stage_navigation(self) -> tuple[QFrame, QListWidget]:
        rail = QFrame()
        rail.setObjectName("StageRail")
        rail.setFixedWidth(232)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(10, 20, 10, 16)
        layout.setSpacing(12)

        title = QLabel("PROJECT WORKFLOW")
        title.setObjectName("RailTitle")

        nav = QListWidget(rail)
        nav.setObjectName("StageList")
        nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav.setWordWrap(True)
        nav.setTextElideMode(Qt.ElideNone)
        for label, icon_name in [
            ("01  Stranding data", "observations"),
            ("02  Environmental forcing", "forcing"),
            ("03  Simulation setup", "setup"),
            ("04  Review & run", "review"),
            ("05  Results & export", "output"),
        ]:
            item = QListWidgetItem(line_icon(icon_name), label)
            nav.addItem(item)
        nav.setCurrentRow(0)

        footer = QLabel("Local workspace\nNo upload required")
        footer.setObjectName("RailFooter")
        footer.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(nav, 1)
        layout.addWidget(footer)
        return rail, nav

    def _build_workflow_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("WorkflowFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(14, 8, 14, 8)
        self.footer_context = QLabel("Step 1 of 5 · Connect the observation dataset")
        self.footer_context.setProperty("role", "field-hint")
        self.back_button = ActionButton("Back")
        self.back_button.setProperty("variant", "secondary")
        self.back_button.setEnabled(False)
        self.back_button.clicked.connect(
            lambda: self.stage_navigation.setCurrentRow(
                max(0, self.stage_navigation.currentRow() - 1)
            )
        )
        self.next_button = ActionButton("Continue", variant="primary")
        self.next_button.setProperty("variant", "primary")
        self.next_button.clicked.connect(self._advance_workflow)
        layout.addWidget(self.footer_context, 1)
        layout.addWidget(self.back_button)
        layout.addWidget(self.next_button)
        return footer

    def _advance_workflow(self) -> None:
        current = self.stage_navigation.currentRow()
        if current == 3:
            state = self.review_run_page.state
            if state in {ReviewRunState.READY, ReviewRunState.READY_WITH_WARNINGS}:
                self._run_simulations()
            elif state == ReviewRunState.RUNNING:
                self._cancel_simulations()
            elif state in {ReviewRunState.COMPLETED, ReviewRunState.COMPLETED_WITH_ERRORS}:
                self.stage_navigation.setCurrentRow(4)
            elif state not in {ReviewRunState.VALIDATING, ReviewRunState.CANCELLING}:
                self._preview_configuration()
            return
        if current == 2 and not self.simulation_setup_page.validate_all_steps():
            return
        self.stage_navigation.setCurrentRow(min(4, current + 1))

    def _sync_review_footer(self) -> None:
        if not hasattr(self, "next_button") or self.stage_navigation.currentRow() != 3:
            return
        state = self.review_run_page.state
        labels = {
            ReviewRunState.VALIDATING: "Checking project...",
            ReviewRunState.READY: "Run simulations",
            ReviewRunState.READY_WITH_WARNINGS: "Run simulations",
            ReviewRunState.RUNNING: "Cancel run",
            ReviewRunState.CANCELLING: "Stopping...",
            ReviewRunState.COMPLETED: "Open results",
            ReviewRunState.COMPLETED_WITH_ERRORS: "Open results",
        }
        self.next_button.setText(labels.get(state, "Validate project"))
        self.next_button.setEnabled(state not in {ReviewRunState.VALIDATING, ReviewRunState.CANCELLING})

    def _bind_observation_page(self, page: ObservationPage) -> None:
        for name in (
            "mapping_preset",
            "dataset_path",
            "dataset_inspection",
            "identifier_column",
            "taxon_column",
            "decomposition_column",
            "lon_column",
            "lat_column",
            "date_column",
            "time_column",
            "observed_datetime_column",
            "datetime_mode",
            "input_timezone",
            "coordinate_format",
        ):
            setattr(self, name, getattr(page, name))
        page.mapping_preset_changed.connect(self._apply_selected_mapping_preset)
        page.dataset_path_changed.connect(self._schedule_observation_inspection)
        self.decomposition_column.currentTextChanged.connect(self._refresh_decomposition_values)
        page.browse_dataset_requested.connect(
            lambda: self._browse_file(
                page.dataset_path,
                "Datasets (*.xlsx *.xls *.csv *.parquet);;All files (*.*)",
            )
        )
        self._apply_selected_mapping_preset(page.mapping_preset.currentText())

    def _bind_environment_page(self, page: EnvironmentPage) -> None:
        for name in (
            "output_group",
            "output_directory",
            "catalog_model",
            "catalog_view",
        ):
            setattr(self, name, getattr(page, name))
        self.environment_catalog_model = page.catalog_model
        self.environment_catalog_view = page.catalog_view
        self.environment_readers: list[EnvironmentalReaderConfig] = []
        page.browse_directory_requested.connect(self._browse_directory)
        page.add_files_requested.connect(self._add_environment_files)
        page.add_folder_requested.connect(self._add_environment_folder)
        page.remove_selected_requested.connect(self._remove_environment_rows)
        page.coverage_preview_requested.connect(self._preview_environment_coverage)
        page.catalog_changed.connect(self._environment_catalog_changed)

    def _bind_simulation_setup_page(self, page: SimulationSetupPage) -> None:
        page.setup_finished.connect(lambda: self.stage_navigation.setCurrentRow(3))
        aliases = (
            "study_area_preset",
            "min_lon",
            "max_lon",
            "min_lat",
            "max_lat",
            "coverage_toggle",
            "coverage_buffer",
            "coverage_status",
            "apply_detected_extent_button",
            "position_search_toggle",
            "position_search_advanced",
            "position_radial_step",
            "position_max_radius",
            "position_angle_step",
            "position_max_attempts",
            "position_failure_behavior",
            "selection_mode",
            "selection_random_panel",
            "selection_sample_size",
            "selection_random_seed",
            "selection_filter_panel",
            "filter_rows_layout",
            "filter_condition_rows",
            "add_filter_condition_button",
            "selection_count_label",
            "sst_column",
            "duration_group",
            "duration_mode",
            "fixed_duration_days",
            "duration_column",
            "duration_threshold",
            "duration_table",
            "duration_column_label",
            "sst_column_label",
            "duration_threshold_label",
            "duration_profile_widgets",
            "duration_column_widgets",
            "add_duration_state_button",
            "wind_column",
            "windage_group",
            "wind_mode",
            "wind_scale",
            "fixed_wind_percent",
            "measurement_column",
            "measurement_unit",
            "measurement_minimum",
            "measurement_maximum",
            "wind_min_percent",
            "wind_max_percent",
            "wind_range_behavior",
            "windage_dataset_widgets",
            "windage_fixed_widgets",
            "windage_measurement_widgets",
            "iteration_count",
            "iteration_interval",
            "model_time_step",
            "release_strategy",
            "start_time_mode",
            "fixed_start_hour",
            "particle_count",
            "release_radius",
            "current_uncertainty",
            "current_uncertainty_toggle",
            "wind_uncertainty",
            "wind_uncertainty_toggle",
            "coastline_action",
            "fallback_group",
            "current_fallback_toggle",
            "wind_fallback_toggle",
            "stokes_fallback_toggle",
            "depth_fallback_toggle",
            "current_fallback_x",
            "current_fallback_y",
            "wind_fallback_x",
            "wind_fallback_y",
            "stokes_fallback_x",
            "stokes_fallback_y",
            "depth_fallback_value",
        )
        for name in aliases:
            setattr(self, name, getattr(page, name))
        self.environment_export_checks = page.environment_export_checks

        self.study_area_preset.currentTextChanged.connect(
            self._apply_selected_study_area_preset
        )
        self.coverage_toggle.toggled.connect(self._update_coverage_controls)
        self.apply_detected_extent_button.clicked.connect(
            self._apply_environment_coverage
        )
        self.position_search_toggle.toggled.connect(
            self._update_position_search_controls
        )
        page.position_direct_policy.currentIndexChanged.connect(self._mark_request_dirty)
        self.selection_mode.currentIndexChanged.connect(
            self._update_selection_controls
        )
        self.add_filter_condition_button.clicked.connect(self._add_filter_condition)
        self.duration_mode.currentIndexChanged.connect(self._update_duration_controls)
        self.duration_table.cellChanged.connect(self._mark_request_dirty)
        for button in (page.add_duration_state_button, page.remove_duration_state_button,
                       page.add_temperature_band_button, page.remove_temperature_band_button):
            button.clicked.connect(self._mark_request_dirty)
        self.wind_mode.currentIndexChanged.connect(self._update_windage_controls)

        self._apply_selected_study_area_preset(self.study_area_preset.currentText())
        self._update_coverage_controls(self.coverage_toggle.isChecked())
        self._update_position_search_controls(False)
        self._update_selection_controls()
        self._update_windage_controls()
        self._update_duration_controls()

    def _bind_review_run_page(self, page: ReviewRunPage) -> None:
        for name in (
            "preview_state",
            "validate_button",
            "run_simulations_button",
            "cancel_run_button",
            "preview_output",
        ):
            setattr(self, name, getattr(page, name))
        page.validate_requested.connect(self._preview_configuration)
        page.run_requested.connect(self._run_simulations)
        page.cancel_requested.connect(self._cancel_simulations)
        page.open_results_requested.connect(self._open_results)
        page.continue_errors_changed.connect(self._set_continue_errors)
        page.state_changed.connect(self._sync_review_footer)
        page.issue_requested.connect(self._go_to_validation_issue)

    def _bind_results_export_page(self, page: ResultsExportPage) -> None:
        page.inspect_requested.connect(lambda: self._start_results_operation("inspect"))
        page.export_requested.connect(lambda: self._start_results_operation("export"))
        page.cancel_requested.connect(self._results_controller.cancel)
        page.browse_results_requested.connect(lambda: self._browse_directory(page.results_directory))
        page.browse_output_requested.connect(lambda: self._browse_directory(page.output_directory))
        page.open_output_requested.connect(self._open_export_directory)

    def _results_request(self) -> ResultsExportRequest:
        page = self.results_export_page
        results_directory = Path(page.results_directory.text().strip())
        output_text = page.output_directory.text().strip()
        if not output_text and page.results_directory.text().strip():
            output_text = str(results_directory / "exports")
            page.output_directory.setText(output_text)
        request = ResultsExportRequest(
            results_directory=results_directory,
            output_directory=Path(output_text),
            positions_per_drift_day=page.positions_per_day.value(),
            write_csv=page.csv_toggle.isChecked(),
            write_xlsx=page.xlsx_toggle.isChecked(),
            environmental_variables=page.selected_environmental_variables(),
        )
        request.validate()
        return request

    def _start_results_operation(self, operation: str) -> None:
        try:
            request = self._results_request()
            request_path = write_results_export_request(
                request, request.output_directory / ".marine_drift_results_request.json"
            )
        except (OSError, ValueError) as exc:
            self.results_export_page.apply_failure(str(exc))
            return
        state = ResultsExportState.INSPECTING if operation == "inspect" else ResultsExportState.EXPORTING
        self.results_export_page.set_state(state)
        if not self._results_controller.start(operation, request_path):
            self.results_export_page.apply_failure("Another results operation is already running.")

    @Slot(dict)
    def _handle_results_event(self, event: dict[str, object]) -> None:
        name = event.get("event")
        if name == "inspection":
            self.results_export_page.apply_inspection(event)
        elif name == "finished":
            self.results_export_page.apply_completion(event)
        elif name == "fatal":
            self.results_export_page.apply_failure(str(event.get("message", "Results operation failed.")))
        else:
            self.results_export_page.apply_progress(event)

    @Slot(str)
    def _results_operation_failed(self, message: str) -> None:
        self.results_export_page.apply_failure(message)

    @Slot(str, int)
    def _results_operation_finished(self, operation: str, exit_code: int) -> None:
        if exit_code and self.results_export_page.state not in {ResultsExportState.FAILED}:
            self.results_export_page.apply_failure(f"The {operation} operation stopped unexpectedly.")

    def _open_export_directory(self) -> None:
        raw = self.results_export_page.output_directory.text().strip()
        if raw:
            QDesktopServices.openUrl(QUrl.fromLocalFile(raw))

    def _set_continue_errors(self, enabled: bool) -> None:
        self.request.settings.job_error_policy = "continue" if enabled else "stop"
        self._mark_request_dirty()

    def _open_results(self) -> None:
        output = self.request.data_sources.output_directory
        if output is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))

    def _run_simulations(self) -> None:
        if self._simulation_process is not None:
            return
        if not self._is_validated:
            self._preview_configuration()
            if not self._is_validated:
                return
        output_directory = self.request.data_sources.output_directory
        if output_directory is None:
            return

        try:
            request_path = write_simulation_request(
                self.request, output_directory / ".marine_drift_request.json"
            )
        except OSError as exc:
            self.preview_output.setPlainText(f"Could not start simulations:\n\n{exc}")
            return

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_simulation_process_output)
        process.finished.connect(self._simulation_process_finished)
        process.errorOccurred.connect(self._simulation_process_error)
        self._simulation_process = process
        self._simulation_process_buffer = ""
        self._simulation_diagnostics = ""
        self._simulation_finished_event = False
        self._simulation_cancelled = False
        self.review_run_page.set_state(ReviewRunState.RUNNING)
        self.review_run_page.run_progress.setRange(0, 0)
        self.review_run_page.run_progress.setFormat("Inspecting observations...")
        self.review_run_page.run_progress.setVisible(True)
        self.preview_state.setText("Starting simulations")
        self.preview_state.setProperty("state", "running")
        self._refresh_style(self.preview_state)
        self.request_state.setText("Running")
        self.preview_health.setText("Running")
        self.preview_output.setPlainText(
            "Reading observations and environmental forcing. The run will continue "
            "automatically after every 5,000 simulations."
        )
        arguments = (
            ["--simulation-worker", str(request_path)]
            if getattr(sys, "frozen", False)
            else ["-m", "marine_drift_desktop.simulation_worker", str(request_path)]
        )
        process.start(self._simulation_worker_program(), arguments)

    @staticmethod
    def _simulation_worker_program() -> str:
        """Use Python's windowless launcher during source runs on Windows."""
        if getattr(sys, "frozen", False) or sys.platform != "win32":
            return sys.executable
        windowless = Path(sys.executable).with_name("pythonw.exe")
        return str(windowless) if windowless.is_file() else sys.executable

    @Slot(QProcess.ProcessError)
    def _simulation_process_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.FailedToStart:
            return
        self.review_run_page.set_state(ReviewRunState.FAILED)
        self.preview_state.setText("Run could not start")
        message = self._simulation_process.errorString() if self._simulation_process else "Unknown process error"
        self.preview_output.setPlainText(f"The simulation worker process could not be started: {message}")
        self._simulation_process = None

    @Slot()
    def _read_simulation_process_output(self) -> None:
        if self._simulation_process is None:
            return
        chunk = bytes(self._simulation_process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        self._simulation_process_buffer += chunk.replace("\r\n", "\n")
        while "\n" in self._simulation_process_buffer:
            line, self._simulation_process_buffer = self._simulation_process_buffer.split("\n", 1)
            if line.startswith("MARINE_DRIFT_EVENT="):
                try:
                    self._handle_simulation_event(json.loads(line.split("=", 1)[1]))
                except (ValueError, TypeError):
                    continue
            else:
                self._simulation_diagnostics = (getattr(self, "_simulation_diagnostics", "") + line + "\n")[-16000:]

    def _handle_simulation_event(self, event: dict[str, object]) -> None:
        event_name = event.get("event")
        if event_name == "start_cancelled":
            self._simulation_finished_event = True
            self.review_run_page.set_state(ReviewRunState.READY)
            self.preview_state.setText("Start cancelled; existing trajectories unchanged")
            self.request_state.setText("Validated")
            self.preview_health.setText("Ready")
            return
        if event_name == "resume_scan":
            self.review_run_page.run_progress.setRange(0, max(1, int(event["total_jobs"])))
            self.review_run_page.run_progress.setValue(int(event["processed"]))
            self.review_run_page.run_progress.setFormat("Checking existing trajectories: %v / %m")
            return
        if event_name == "resume_review":
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Existing simulation results")
            dialog.setText(
                f"{int(event['completed']):,} completed trajectories found.\n"
                f"{int(event['pending']):,} trajectories remain to be generated.\n"
                f"{int(event['invalid']):,} incomplete files; {int(event['conflicts']):,} unidentified/conflicting files.\n"
                f"{int(event.get('unrelated', 0)):,} other files will be left unchanged.\n"
                "Overwrite recalculates current project jobs only. Older filenames for those jobs are moved to history; unrelated files stay unchanged.")
            if event.get("configuration_changed"):
                dialog.setInformativeText(
                    "The configuration or input files differ from the previous checkpoint, or compatibility cannot be verified. "
                    "Keeping completed trajectories means new trajectories use the CURRENT settings, while existing ones remain unchanged. "
                    "This can mix results from different model configurations. Use a new folder for a fully separate run.")
                dialog.setDetailedText("Changed settings: " + ", ".join(
                    str(value) for value in event.get("changed_sections", []))
                    + "\nInput-file or software changes may also invalidate compatibility.")
            keep = dialog.addButton("Keep completed; run missing", QMessageBox.AcceptRole)
            keep.setEnabled(not int(event["conflicts"]))
            overwrite = dialog.addButton("Recalculate and overwrite", QMessageBox.DestructiveRole)
            cancel = dialog.addButton(QMessageBox.Cancel)
            dialog.setDefaultButton(cancel)
            dialog.exec()
            decision = "preserve" if dialog.clickedButton() == keep else (
                "overwrite" if dialog.clickedButton() == overwrite else "cancel")
            if self._simulation_process is not None:
                self._simulation_process.write((json.dumps({"decision": decision}) + "\n").encode())
            return
        self.review_run_page.update_activity(event)
        if event_name == "workload":
            total = int(event.get("total_jobs", 0))
            resumed = int(event.get("resume_index", 0))
            self.review_run_page.run_progress.setRange(0, max(total, 1))
            self.review_run_page.run_progress.setValue(resumed)
            self.review_run_page.run_progress.setFormat(f"%v of {total:,} simulations")
        elif event_name == "batch_started":
            batch = int(event.get("batch", 0))
            self.preview_state.setText(f"Running batch {batch}")
            self.preview_output.setPlainText(
                f"Batch {batch} is running locally.\n\n"
                f"Range: {int(event.get('start', 0)) + 1:,} to "
                f"{int(event.get('end', 0)):,}\n"
                "The next batch starts automatically after this checkpoint."
            )
        elif event_name == "progress":
            processed = int(event.get("processed", 0))
            self.review_run_page.run_progress.setValue(processed)
        elif event_name == "fatal":
            self.review_run_page.set_state(ReviewRunState.FAILED)
            self.preview_state.setText("Run failed")
            self.preview_state.setProperty("state", "attention")
            self._refresh_style(self.preview_state)
            self.preview_output.setPlainText(
                f"The simulation worker stopped:\n\n{event.get('message', 'Unknown error')}"
            )
        elif event_name == "finished":
            self._simulation_finished_event = True
            failed = int(event.get("failed", 0))
            self.review_run_page.set_state(
                ReviewRunState.COMPLETED_WITH_ERRORS
                if failed
                else ReviewRunState.COMPLETED
            )
            self.preview_state.setText(
                "Completed with warnings" if failed else "Run complete"
            )
            self.preview_state.setProperty("state", "ready")
            self._refresh_style(self.preview_state)
            self.request_state.setText("Complete")
            self.preview_health.setText("Complete")
            self.preview_output.setPlainText(
                "\n".join([
                    "Reverse-drift simulations complete",
                    "",
                    f"Total simulations: {int(event.get('total_jobs', 0)):,}",
                    f"Completed now: {int(event.get('completed', 0)):,}",
                    f"Existing outputs: {int(event.get('existing', 0)):,}",
                    f"Failed: {int(event.get('failed', 0)):,}",
                    f"Skipped observations: {int(event.get('skipped_records', 0)):,}",
                    f"Checkpoint: {event.get('checkpoint_path', '')}",
                ])
            )

    def _cancel_simulations(self) -> None:
        process = self._simulation_process
        if process is None:
            return
        self._simulation_cancelled = True
        self.review_run_page.set_state(ReviewRunState.CANCELLING)
        self.preview_state.setText("Stopping safely")
        self.preview_output.setPlainText(
            "Stopping the worker. Finished output files are retained; the next run "
            "will resume from the latest 5,000-simulation checkpoint."
        )
        process.terminate()
        QTimer.singleShot(
            3000,
            lambda: process.kill()
            if process.state() != QProcess.ProcessState.NotRunning
            else None,
        )

    @Slot(int, QProcess.ExitStatus)
    def _simulation_process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        self._read_simulation_process_output()
        self._simulation_process = None
        self.cancel_run_button.setEnabled(False)
        if self._simulation_cancelled:
            self.review_run_page.set_state(ReviewRunState.FAILED)
            self.preview_state.setText("Run stopped")
            self.preview_state.setProperty("state", "attention")
            self._refresh_style(self.preview_state)
            self.request_state.setText("Paused")
            self.preview_health.setText("Checkpoint saved")
        elif not self._simulation_finished_event:
            self.review_run_page.set_state(ReviewRunState.FAILED)
            self.preview_state.setText("Run interrupted")
            self.preview_state.setProperty("state", "attention")
            self._refresh_style(self.preview_state)
            if exit_code != 0 and "worker stopped" not in self.preview_output.toPlainText().lower():
                self.preview_output.setPlainText(
                    f"The simulation process exited unexpectedly with code {exit_code}.\n\n"
                    + getattr(self, "_simulation_diagnostics", "")
                    + self._simulation_process_buffer
                )
        elif self.request.data_sources.output_directory is not None:
            self.results_export_page.set_latest_run(self.request.data_sources.output_directory)
        if process := self.sender():
            if isinstance(process, QProcess):
                process.deleteLater()
        self._update_run_actions()

    def _column_selector(self, placeholder: str) -> SearchableColumnComboBox:
        return SearchableColumnComboBox(placeholder)

    def _selector_text(self, selector: QComboBox) -> str:
        return selector.currentText().strip()

    def _set_selector_text(self, selector: QComboBox, value: str) -> None:
        if value and selector.findText(value) < 0:
            selector.addItem(value)
        selector.setCurrentText(value)

    def _schedule_observation_inspection(self, raw_path: str) -> None:
        self.dataset_inspection_timer.stop()
        path = self._clean_path_input(raw_path)
        if path is None or not path.exists() or not path.is_file():
            self.dataset_inspection.setText(
                "Select an existing dataset to detect its available columns."
            )
            self.observation_page.set_dataset_metadata(
                "No dataset selected", "Not detected", "Checked during validation", 0
            )
            self.observation_page.update_mapping_states(set())
            return
        self.dataset_inspection.setText("Detecting column names...")
        self.dataset_inspection_timer.start()

    def _inspect_observation_dataset(self) -> None:
        path = self._clean_path_input(self.dataset_path.text())
        if path is None or not path.exists() or not path.is_file():
            self.dataset_inspection.setText(
                "Select an existing dataset to detect its available columns."
            )
            self.observation_page.set_dataset_metadata(
                "No dataset selected", "Not detected", "Checked during validation", 0
            )
            self.observation_page.update_mapping_states(set())
            return

        try:
            columns = sorted(read_observation_columns(path), key=str.casefold)
        except (OSError, ValueError, ImportError) as exc:
            self.dataset_inspection.setText(f"Could not inspect dataset: {exc}")
            return

        selectors = [
            self.identifier_column,
            self.taxon_column,
            self.decomposition_column,
            self.sst_column,
            self.wind_column,
            self.measurement_column,
            self.duration_column,
            self.lon_column,
            self.lat_column,
            self.date_column,
            self.time_column,
            self.observed_datetime_column,
        ]
        for selector in selectors:
            selected = self._selector_text(selector)
            selector.blockSignals(True)
            selector.clear()
            selector.addItem("")
            selector.addItems(columns)
            if selected:
                self._set_selector_text(selector, selected)
            selector.blockSignals(False)

        for row in self.filter_condition_rows:
            selected = row.column.currentText().strip()
            row.column.blockSignals(True)
            row.column.clear()
            row.column.addItem("")
            row.column.addItems(columns)
            row.column.setCurrentText(selected)
            row.column.blockSignals(False)

        self.dataset_inspection.setText(
            f"Detected {len(columns)} columns from file metadata. Records remain unloaded "
            "until validation or execution."
        )
        self.observation_page.set_dataset_metadata(
            path.name,
            path.suffix.removeprefix(".").upper(),
            "Checked during validation",
            len(columns),
        )
        self.observation_page.update_mapping_states(columns)
        self._refresh_decomposition_values()

    def _refresh_decomposition_values(self, *_: object) -> None:
        path = self._clean_path_input(self.dataset_path.text())
        column = self._selector_text(self.decomposition_column)
        if path is None or not path.is_file() or not column:
            return
        worker = ObservationValuesWorker(path, column, self)
        worker.completed.connect(self._decomposition_values_loaded)
        worker.finished.connect(lambda worker=worker: self._observation_value_worker_finished(worker))
        self._observation_value_workers.add(worker)
        worker.start()

    def _decomposition_values_loaded(self, path_text: str, column: str, values: list) -> None:
        current_path = self._clean_path_input(self.dataset_path.text())
        if current_path is None or str(current_path) != path_text:
            return
        if self._selector_text(self.decomposition_column) != column:
            return
        self.simulation_setup_page.set_decomposition_values(values)

    def _observation_value_worker_finished(self, worker: ObservationValuesWorker) -> None:
        self._observation_value_workers.discard(worker)
        worker.deleteLater()

    def _browse_file(self, target: QLineEdit, file_filter: str) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select file",
            target.text().strip(),
            file_filter,
        )
        if selected:
            target.setText(selected)

    def _browse_directory(self, target: QLineEdit) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select directory",
            target.text().strip(),
        )
        if selected:
            target.setText(selected)

    def _add_environment_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Add environmental datasets",
            "",
            "NetCDF (*.nc *.nc4);;All files (*.*)",
        )
        if selected:
            self._add_environment_paths([Path(path) for path in selected])

    def _add_environment_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self, "Add environmental dataset folder", ""
        )
        if not selected:
            return
        folder = Path(selected)
        paths = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in {".nc", ".nc4"}
        )
        self._add_environment_paths(paths)

    def _add_environment_paths(self, paths: list[Path]) -> None:
        result = self.environment_catalog_model.add_paths(paths)
        if not result.added_paths:
            return
        for path in result.added_paths:
            self.environment_catalog_model.mark_inspecting(path)
        worker = EnvironmentInspectionWorker(list(result.added_paths), parent=self)
        worker.inspected.connect(self._environment_inspection_completed)
        worker.failed.connect(self._environment_inspection_failed)
        worker.finished.connect(
            lambda worker=worker: self._environment_inspection_finished(worker)
        )
        self._environment_inspection_workers.add(worker)
        first_row = next(
            row
            for row in range(self.environment_catalog_model.rowCount())
            if self.environment_catalog_model.entry_at(row).path == result.added_paths[0]
        )
        self.environment_catalog_view.selectRow(first_row)
        worker.start()

    def _remove_environment_rows(self) -> None:
        rows = self.environment_page.selected_rows()
        self.environment_catalog_model.remove_rows(rows)

    @Slot(object, object)
    def _environment_inspection_completed(self, path: Path, inspection: object) -> None:
        try:
            self.environment_catalog_model.apply_inspection(path, inspection)
        except KeyError:
            return
        self.environment_page.refresh_selected_entry()

    @Slot(object, str)
    def _environment_inspection_failed(self, path: Path, message: str) -> None:
        try:
            self.environment_catalog_model.apply_error(path, message)
        except KeyError:
            return
        self.environment_page.refresh_selected_entry()

    def _environment_inspection_finished(
        self, worker: EnvironmentInspectionWorker
    ) -> None:
        self._environment_inspection_workers.discard(worker)
        worker.deleteLater()

    def _environment_catalog_changed(self) -> None:
        self.environment_readers = self.environment_catalog_model.to_configs()
        self._mark_request_dirty()

    def _preview_environment_coverage(self) -> None:
        entry = self.environment_page.selected_entry()
        if entry is None or entry.inspection is None or entry.inspection.extent is None:
            return
        reader = entry.inspection.extent
        study = SpatialExtent(
            self.min_lon.value(),
            self.max_lon.value(),
            self.min_lat.value(),
            self.max_lat.value(),
        )
        if (
            reader.min_longitude <= study.min_longitude
            and reader.max_longitude >= study.max_longitude
            and reader.min_latitude <= study.min_latitude
            and reader.max_latitude >= study.max_latitude
        ):
            relationship = "Full coverage"
            explanation = "The reader contains the complete configured study extent."
        elif (
            reader.min_longitude < study.max_longitude
            and reader.max_longitude > study.min_longitude
            and reader.min_latitude < study.max_latitude
            and reader.max_latitude > study.min_latitude
        ):
            relationship = "Partial coverage"
            explanation = "The reader intersects only part of the configured study extent."
        else:
            relationship = "No overlap"
            explanation = "The reader does not intersect the configured study extent."
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Coverage preview - {entry.path.name}")
        dialog.resize(560, 300)
        layout = QVBoxLayout(dialog)
        title = QLabel(relationship)
        title.setObjectName("PreviewState")
        title.setProperty(
            "state", "ready" if relationship == "Full coverage" else "attention"
        )
        detail = QLabel(
            "\n".join(
                [
                    explanation,
                    "",
                    f"Reader longitude: {reader.min_longitude:.4f} to {reader.max_longitude:.4f}",
                    f"Reader latitude: {reader.min_latitude:.4f} to {reader.max_latitude:.4f}",
                    f"Study longitude: {study.min_longitude:.4f} to {study.max_longitude:.4f}",
                    f"Study latitude: {study.min_latitude:.4f} to {study.max_latitude:.4f}",
                ]
            )
        )
        detail.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(title)
        layout.addWidget(detail)
        layout.addStretch(1)
        layout.addWidget(buttons)
        dialog.exec()

    def _apply_selected_mapping_preset(self, preset_name: str) -> None:
        mapping = get_column_mapping_preset(preset_name)
        self._set_selector_text(self.identifier_column, mapping.stranding_identifier)
        self._set_selector_text(self.taxon_column, mapping.taxon_label)
        self._set_selector_text(self.decomposition_column, mapping.decomposition_code)
        self._set_selector_text(self.sst_column, mapping.sea_surface_temperature)
        self._set_selector_text(self.wind_column, mapping.wind_drift_factor)
        self._set_selector_text(self.lon_column, mapping.longitude)
        self._set_selector_text(self.lat_column, mapping.latitude)
        self._set_selector_text(self.date_column, mapping.observed_date)
        self._set_selector_text(self.time_column, mapping.observed_time)
        mode_index = self.datetime_mode.findData(mapping.datetime_mode)
        self.datetime_mode.setCurrentIndex(max(0, mode_index))
        self._set_selector_text(
            self.observed_datetime_column, mapping.observed_datetime
        )
        self.observation_page._refresh_mapping_states()

    def _apply_selected_study_area_preset(self, preset_name: str) -> None:
        mode = self.study_area_preset.currentData()
        if mode == "environment_intersection":
            self.coverage_toggle.setChecked(True)
            self._update_coverage_controls(True)
            return
        self.coverage_toggle.setChecked(False)
        try:
            extent = get_study_area_preset(preset_name)
        except KeyError:
            return
        self.min_lon.setValue(extent.min_longitude)
        self.max_lon.setValue(extent.max_longitude)
        self.min_lat.setValue(extent.min_latitude)
        self.max_lat.setValue(extent.max_latitude)

    def _update_coverage_controls(self, checked: bool) -> None:
        for field in (
            self.min_lon,
            self.max_lon,
            self.min_lat,
            self.max_lat,
        ):
            field.setEnabled(not checked)
        self.coverage_buffer.setEnabled(checked)
        self.apply_detected_extent_button.setVisible(checked)
        if checked:
            self.coverage_status.setText(
                "The simulation area will use the overlapping environmental coverage plus the buffer below."
            )
        else:
            self.coverage_status.setText(
                "Manual longitude and latitude bounds define the simulation area."
            )

    def _apply_environment_coverage(self) -> None:
        paths = [reader.path for reader in self.environment_readers]
        cached_by_path = {
            str(entry.path.resolve()).casefold(): entry.inspection.extent
            for row in range(self.environment_catalog_model.rowCount())
            if (entry := self.environment_catalog_model.entry_at(row)).inspection is not None
            and entry.inspection.extent is not None
        }
        cached_extents = [
            cached_by_path.get(str(path.resolve()).casefold())
            for path in dict.fromkeys(paths)
        ]
        try:
            if paths and all(extent is not None for extent in cached_extents):
                extent = intersect_extents(cached_extents, self.coverage_buffer.value())
            else:
                self.coverage_status.setText(
                    "Environmental coverage is still being inspected. Wait for every dataset to finish."
                )
                return
        except (OSError, ValueError, ImportError) as exc:
            self.coverage_status.setText(f"Coverage could not be detected: {exc}")
            return
        self.min_lon.setValue(extent.min_longitude)
        self.max_lon.setValue(extent.max_longitude)
        self.min_lat.setValue(extent.min_latitude)
        self.max_lat.setValue(extent.max_latitude)
        self.coverage_status.setText(
            "Detected overlap: "
            f"{extent.min_longitude:.3f} to {extent.max_longitude:.3f} longitude, "
            f"{extent.min_latitude:.3f} to {extent.max_latitude:.3f} latitude."
        )
        self._mark_request_dirty()

    def _update_position_search_controls(self, checked: bool) -> None:
        self.position_search_advanced.setVisible(checked)
        self.simulation_setup_page.position_direct_policy.setVisible(not checked)

    def _update_selection_controls(self, *_: object) -> None:
        mode = self.selection_mode.currentData()
        self.selection_random_panel.setVisible(mode == "random")
        self.selection_filter_panel.setVisible(mode == "filter")

    def _add_filter_condition(self) -> None:
        container = QFrame()
        container.setProperty("role", "filter-row")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 4, 0, 4)
        column = self._column_selector("Select dataset column")
        operator = AnimatedComboBox()
        for label, value in [
            ("equals", "equals"), ("does not equal", "not_equals"),
            ("is less than", "<"), ("is at most", "<="),
            ("is greater than", ">"), ("is at least", ">="),
            ("contains text", "contains"), ("is blank", "is_blank"),
            ("is not blank", "is_not_blank"),
            ("is one of (comma separated)", "in_values"),
        ]:
            operator.addItem(label, value)
        value = QLineEdit()
        value.setPlaceholderText("Comparison value")
        connector = AnimatedComboBox()
        connector.addItem("AND", "and")
        connector.addItem("OR", "or")
        remove_button = ActionButton("Remove", variant="ghost")
        row = _FilterConditionRow(
            container, column, operator, value, connector, remove_button
        )
        remove_button.clicked.connect(lambda: self._remove_filter_condition(row))
        operator.currentIndexChanged.connect(
            lambda: value.setEnabled(operator.currentData() not in {"is_blank", "is_not_blank"})
        )
        for combo in (column, operator, connector):
            combo.currentIndexChanged.connect(self._mark_request_dirty)
        value.textChanged.connect(self._mark_request_dirty)
        layout.addWidget(connector, 0)
        layout.addWidget(column, 2)
        layout.addWidget(operator, 1)
        layout.addWidget(value, 2)
        layout.addWidget(remove_button, 0)
        self.filter_condition_rows.append(row)
        self.filter_rows_layout.addWidget(container)
        self._inspect_filter_row_columns(row)
        self._mark_request_dirty()

    def _inspect_filter_row_columns(self, row: _FilterConditionRow) -> None:
        source = self.identifier_column
        columns = [source.itemText(index) for index in range(1, source.count())]
        row.column.addItems(columns)

    def _remove_filter_condition(self, row: _FilterConditionRow) -> None:
        if row not in self.filter_condition_rows:
            return
        self.filter_condition_rows.remove(row)
        row.container.deleteLater()
        self._mark_request_dirty()

    def _clean_path_input(self, value: str) -> Path | None:
        text = value.strip()
        return Path(text) if text else None

    def _sync_observation_mapping_from_ui(self) -> None:
        mapping = self.request.column_mapping
        mapping.stranding_identifier = self._selector_text(self.identifier_column)
        mapping.taxon_label = self._selector_text(self.taxon_column)
        mapping.decomposition_code = self._selector_text(self.decomposition_column)
        mapping.sea_surface_temperature = self._selector_text(self.sst_column)
        mapping.wind_drift_factor = self._selector_text(self.wind_column)
        mapping.longitude = self._selector_text(self.lon_column)
        mapping.latitude = self._selector_text(self.lat_column)
        mapping.datetime_mode = self.datetime_mode.currentData()
        if self.input_timezone.currentData() is None:
            self.preview_output.setPlainText("Select a time interpretation or source timezone from the list.")
            return False
        mapping.input_timezone = self.input_timezone.currentData()
        mapping.observed_date = self._selector_text(self.date_column)
        mapping.observed_time = self._selector_text(self.time_column)
        mapping.observed_datetime = self._selector_text(
            self.observed_datetime_column
        )

    def _collect_request_from_ui(self) -> bool:
        self.request.data_sources.observation_dataset = self._clean_path_input(
            self.dataset_path.text()
        )
        self.request.data_sources.output_directory = self._clean_path_input(
            self.output_directory.text()
        )
        self.environment_readers = self.environment_catalog_model.to_configs()
        self.request.data_sources.environment_readers = list(self.environment_readers)

        self._sync_observation_mapping_from_ui()

        self.request.settings.iteration_count = self.iteration_count.value()
        self.request.settings.iteration_interval_hours = self.iteration_interval.value()
        self.request.settings.model_time_step_hours = self.model_time_step.value()
        self.request.settings.start_time_mode = self.start_time_mode.currentData()
        self.request.settings.fixed_start_hour = self.fixed_start_hour.value()
        self.request.settings.particle_count = self.particle_count.value()
        self.request.settings.release_radius_meters = self.release_radius.value()
        self.request.settings.current_uncertainty = self.current_uncertainty.value()
        self.request.settings.wind_uncertainty = self.wind_uncertainty.value()
        self.request.settings.current_uncertainty_enabled = (
            self.current_uncertainty_toggle.isChecked()
        )
        self.request.settings.wind_uncertainty_enabled = (
            self.wind_uncertainty_toggle.isChecked()
        )
        self.request.settings.coastline_action = self.coastline_action.currentData()
        self.request.settings.environment_export_variables = (
            self.simulation_setup_page.selected_environment_export_variables()
        )
        self.request.settings.coordinate_format = self.coordinate_format.currentData()
        fallback = self.request.settings.fallback_values
        fallback.currents_enabled = self.current_fallback_toggle.isChecked()
        fallback.wind_enabled = self.wind_fallback_toggle.isChecked()
        fallback.stokes_drift_enabled = self.stokes_fallback_toggle.isChecked()
        fallback.seafloor_depth_enabled = self.depth_fallback_toggle.isChecked()
        fallback.x_sea_water_velocity = self.current_fallback_x.value()
        fallback.y_sea_water_velocity = self.current_fallback_y.value()
        fallback.x_wind = self.wind_fallback_x.value()
        fallback.y_wind = self.wind_fallback_y.value()
        fallback.stokes_drift_x_velocity = self.stokes_fallback_x.value()
        fallback.stokes_drift_y_velocity = self.stokes_fallback_y.value()
        fallback.sea_floor_depth_below_sea_level = self.depth_fallback_value.value()
        self.request.settings.wind_drift.mode = self.wind_mode.currentData()
        self.request.settings.wind_drift.source_scale = self.wind_scale.currentData()
        self.request.settings.wind_drift.fixed_percent = self.fixed_wind_percent.value()
        self.request.settings.wind_drift.measurement_column = self._selector_text(
            self.measurement_column
        )
        self.request.settings.wind_drift.measurement_unit = self.measurement_unit.currentData()
        self.request.settings.wind_drift.measurement_minimum = self.measurement_minimum.value()
        self.request.settings.wind_drift.measurement_maximum = self.measurement_maximum.value()
        self.request.settings.wind_drift.wind_drift_minimum_percent = self.wind_min_percent.value()
        self.request.settings.wind_drift.wind_drift_maximum_percent = self.wind_max_percent.value()
        self.request.settings.wind_drift.outside_range_behavior = (
            self.wind_range_behavior.currentData()
        )
        self.request.settings.duration.mode = self.duration_mode.currentData()
        self.request.settings.duration.fixed_days = self.fixed_duration_days.value()
        self.request.settings.duration.duration_column = self._selector_text(
            self.duration_column
        )
        try:
            boundaries, scenarios, value_map = self.simulation_setup_page.duration_profile_data()
        except ValueError as exc:
            if self.request.settings.duration.mode == "estimated":
                self.preview_output.setPlainText(f"Invalid duration profile:\n\n{exc}")
                self._is_validated = False
                self._update_run_actions()
                return False
        else:
            duration = self.request.settings.duration
            duration.temperature_boundaries_celsius = boundaries
            duration.temperature_threshold_celsius = boundaries[0]
            duration.scenario_days = scenarios
            duration.decomposition_value_map = value_map
            duration.cool_water_days = {code: days[0] for code, days in scenarios.items()}
            duration.warm_water_days = {code: days[-1] for code, days in scenarios.items()}
        self.request.settings.extent.min_longitude = self.min_lon.value()
        self.request.settings.extent.max_longitude = self.max_lon.value()
        self.request.settings.extent.min_latitude = self.min_lat.value()
        self.request.settings.extent.max_latitude = self.max_lat.value()
        self.request.settings.coverage.mode = (
            "environment_intersection" if self.coverage_toggle.isChecked() else "manual"
        )
        self.request.settings.coverage.buffer_degrees = self.coverage_buffer.value()
        self.request.settings.position_search.mode = (
            "search_nearby_water" if self.position_search_toggle.isChecked()
            else self.simulation_setup_page.position_direct_policy.currentData()
        )
        self.request.settings.position_search.radial_step_degrees = (
            self.position_radial_step.value()
        )
        self.request.settings.position_search.max_radius_degrees = (
            self.position_max_radius.value()
        )
        self.request.settings.position_search.angle_step_degrees = (
            self.position_angle_step.value()
        )
        self.request.settings.position_search.max_attempts = (
            self.position_max_attempts.value()
        )
        self.request.settings.position_search.failure_behavior = (
            self.position_failure_behavior.currentData()
        )
        selection = self.request.settings.observation_selection
        selection.mode = self.selection_mode.currentData()
        selection.sample_size = self.selection_sample_size.value()
        selection.random_seed = self.selection_random_seed.value()
        selection.conditions = []
        for row in self.filter_condition_rows:
            raw_value = row.value.text().strip()
            selection.conditions.append(FilterCondition(
                column=row.column.currentText().strip(),
                operator=row.operator.currentData(),
                value=raw_value,
                values=[item.strip() for item in raw_value.split(",") if item.strip()],
                connector=row.connector.currentData(),
            ))
        self.request.settings.job_error_policy = (
            "continue" if self.review_run_page.continue_errors_toggle.isChecked() else "stop"
        )

        return True

    def _preview_configuration(self) -> None:
        if not self._collect_request_from_ui():
            return
        self.stage_navigation.setCurrentRow(3)
        self._start_preflight()

    def _start_preflight(self) -> None:
        if self._preflight_worker is not None and self._preflight_worker.isRunning():
            return
        self._preflight_generation += 1
        generation = self._preflight_generation
        worker = PreflightWorker(
            deepcopy(self.request), generation=generation, parent=self
        )
        worker.completed.connect(self._preflight_completed)
        worker.failed.connect(self._preflight_failed)
        worker.progress_changed.connect(self._preflight_progress)
        worker.finished.connect(
            lambda worker=worker: self._preflight_worker_finished(worker)
        )
        self._preflight_worker = worker
        self._last_preflight_result = None
        self._is_validated = False
        self.review_run_page.set_state(ReviewRunState.VALIDATING)
        self.review_run_page.show_validation_overlay()
        self._preflight_minimum_until = time.monotonic() + 0.65
        self.preview_state.setText("Checking configuration")
        self.preview_state.setProperty("state", "running")
        self._refresh_style(self.preview_state)
        self.preview_health.setText("Checking")
        self.request_state.setText("Checking")
        self.review_run_page.reset_run_summary("Calculating during validation")
        self.preview_output.setPlainText(
            "Checking the current request in the background. You can continue "
            "reviewing the configuration while observation and NetCDF metadata are read."
        )
        # Paint the validation state before metadata inspection can occupy the worker.
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        worker.start()

    @Slot(int, int, int, int)
    def _preflight_progress(self, generation: int, stage: int, done: int, total: int) -> None:
        if generation == self._preflight_generation:
            self.review_run_page.update_validation_progress(stage, done, total)

    @Slot(int, object)
    def _preflight_completed(self, generation: int, result: PreflightResult) -> None:
        if generation != self._preflight_generation:
            return
        remaining = self._preflight_minimum_until - time.monotonic()
        if remaining > 0:
            self._preflight_minimum_until = 0.0
            QTimer.singleShot(
                max(1, round(remaining * 1000)),
                lambda: self._preflight_completed(generation, result),
            )
            return
        self._preflight_minimum_until = 0.0
        self._last_preflight_result = result
        self.environment_page.set_readiness(result.forcing_readiness)
        summary = result.to_summary(self.request)
        self.review_run_page.set_readiness(result.checks)
        self._apply_validation_feedback(result.checks)
        self.review_run_page.set_run_summary(
            RunSummaryValues.from_request(self.request, result)
        )
        self.preview_output.setPlainText(self._format_preflight(result, summary))
        self._update_preview_summary(summary)
        has_warnings = any(
            check.level == "warning" for check in result.checks
        ) or any(message.level == "warning" for message in result.validation_messages)
        self.review_run_page.set_state(
            ReviewRunState.READY_WITH_WARNINGS
            if result.is_ready and has_warnings
            else ReviewRunState.READY
            if result.is_ready
            else ReviewRunState.BLOCKED
        )
    @Slot(int, str)
    def _preflight_failed(self, generation: int, message: str) -> None:
        if generation != self._preflight_generation:
            return
        self._is_validated = False
        self.review_run_page.set_state(ReviewRunState.FAILED)
        self.preview_state.setText("Check failed")
        self.preview_state.setProperty("state", "attention")
        self._refresh_style(self.preview_state)
        self.preview_health.setText("Check failed")
        self.request_state.setText("Draft")
        self.review_run_page.reset_run_summary("Validation unavailable")
        from ..core.preflight import PreflightCheck
        checks = (PreflightCheck("validation_failed", "error", "Validation could not complete", message,
                                 "review_run", True),)
        self.review_run_page.set_readiness(checks)
        self._apply_validation_feedback(checks)
        self.preview_output.setPlainText(f"Preflight failed:\n\n{message}")
        self._update_run_actions()

    def _preflight_worker_finished(self, worker: PreflightWorker) -> None:
        if self._preflight_worker is worker:
            self._preflight_worker = None
            self.validate_button.setEnabled(self._simulation_process is None)
        worker.deleteLater()

    def _format_preflight(
        self, result: PreflightResult, summary: SimulationSummary
    ) -> str:
        lines = [
            self._format_summary(summary),
            "",
            "Preflight workload",
            f"Source rows: {result.source_rows:,}",
            f"Selected rows: {result.selected_rows:,}",
            f"Runnable observations: {result.runnable_observations:,}",
            f"Skipped observations: {result.skipped_observations:,}",
            f"Model iterations: {result.planned_model_iterations:,}",
            f"Particle trajectories: {result.planned_particle_trajectories:,}",
            "",
            "Readiness checks",
        ]
        lines.extend(
            f"[{check.level.title()}] {check.title}: {check.detail}"
            for check in result.checks
        )
        return "\n".join(lines)

    def _format_summary(self, summary: SimulationSummary) -> str:
        errors = sum(1 for message in summary.messages if message.level == "error")
        warnings = sum(1 for message in summary.messages if message.level == "warning")
        infos = sum(1 for message in summary.messages if message.level == "info")

        lines = [
            "Validation preview",
            "",
            f"Status: {'Ready to run simulations' if summary.is_valid else 'Needs attention'}",
            f"Messages: {errors} error(s), {warnings} warning(s), {infos} info",
            f"Output directory: {summary.output_directory or 'not selected'}",
            "",
        ]
        for message in summary.messages:
            prefix = {
                "error": "[Error]",
                "warning": "[Warning]",
                "info": "[Info]",
            }[message.level]
            lines.append(f"{prefix} {message.text}")
        return "\n".join(lines)

    def _update_preview_summary(self, summary: SimulationSummary) -> None:
        if summary.is_valid:
            state = "ready"
            status = "Ready to run"
            preview = "Ready"
        else:
            state = "attention"
            status = "Needs attention"
            preview = "Review errors"

        self.preview_state.setText(status)
        self.preview_state.setProperty("state", state)
        self._refresh_style(self.preview_state)

        self.preview_health.setText(preview)
        self.request_state.setText("Validated" if summary.is_valid else "Draft")
        self._is_validated = summary.is_valid
        self._update_run_actions()

    def _update_stage_status(self, index: int) -> None:
        stage_names = [
            "Stranding data",
            "Environmental forcing",
            "Simulation setup",
            "Review & run",
            "Results & export",
        ]
        if 0 <= index < len(stage_names):
            self.stage_state.setText(stage_names[index])
        if hasattr(self, "back_button"):
            contexts = [
                "Connect the observation dataset",
                "Add environmental forcing",
                "Define assumptions and model physics",
                "Validate configuration and run",
                "Sample trajectories and export weighted positions",
            ]
            self.footer_context.setText(f"Step {index + 1} of 5 · {contexts[index]}")
            self.back_button.setEnabled(index > 0)
            self.next_button.setEnabled(index < 4)
            self.next_button.setText("Review project" if index == 2 else "Continue")
            self._sync_review_footer()
            if index == 3:
                self.review_run_page.verticalScrollBar().setValue(0)

    def _update_windage_controls(self) -> None:
        self.simulation_setup_page._update_windage_panels()
        mode = self.wind_mode.currentData()
        groups = {
            "dataset": self.windage_dataset_widgets,
            "fixed": self.windage_fixed_widgets,
            "measurement": self.windage_measurement_widgets,
        }
        for group_mode, widgets in groups.items():
            for widget in widgets:
                widget.setVisible(group_mode == mode)
        self.simulation_setup_page.windage_measurement_scroll.setVisible(mode == "measurement")

    def _update_duration_controls(self) -> None:
        self.simulation_setup_page._update_duration_panels()
        estimated = self.duration_mode.currentData() == "estimated"
        for widget in self.duration_profile_widgets:
            widget.setVisible(estimated)
        for widget in self.duration_column_widgets:
            widget.setVisible(not estimated)

    def _update_duration_headers(self, threshold: float) -> None:
        self.duration_table.setHorizontalHeaderLabels(
            [
                "Decomposition state",
                f"Temperature <= {threshold:g} C",
                f"Temperature > {threshold:g} C",
            ]
        )

    def _add_duration_state(self) -> None:
        row = self.duration_table.rowCount()
        self.duration_table.insertRow(row)
        for column, value in enumerate([row + 1, 1, 1]):
            self.duration_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._mark_request_dirty()

    def _duration_days_from_table(self) -> tuple[dict[int, int], dict[int, int]]:
        cool_days: dict[int, int] = {}
        warm_days: dict[int, int] = {}
        for row in range(self.duration_table.rowCount()):
            items = [self.duration_table.item(row, column) for column in range(3)]
            if any(item is None or not item.text().strip() for item in items):
                raise ValueError(
                    "Every duration-profile row needs a decomposition state and two durations."
                )
            decomposition = int(items[0].text())
            cool_days[decomposition] = int(items[1].text())
            warm_days[decomposition] = int(items[2].text())
        return cool_days, warm_days

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _connect_dirty_tracking(self) -> None:
        fields = [
            self.dataset_path,
            self.output_directory,
        ]
        for field in fields:
            field.textChanged.connect(self._mark_request_dirty)

        for field in [
            self.mapping_preset,
            self.study_area_preset,
            self.coastline_action,
            self.start_time_mode,
            self.identifier_column,
            self.taxon_column,
            self.decomposition_column,
            self.sst_column,
            self.wind_column,
            self.measurement_column,
            self.measurement_unit,
            self.duration_column,
            self.lon_column,
            self.lat_column,
            self.date_column,
            self.time_column,
            self.observed_datetime_column,
            self.datetime_mode,
            self.input_timezone,
            self.coordinate_format,
            self.wind_mode,
            self.wind_scale,
            self.wind_range_behavior,
            self.duration_mode,
            self.release_strategy,
            self.position_failure_behavior,
            self.selection_mode,
        ]:
            field.currentIndexChanged.connect(self._mark_request_dirty)

        for role_check in [
            self.coverage_toggle,
            self.position_search_toggle,
            self.current_uncertainty_toggle,
            self.wind_uncertainty_toggle,
            self.current_fallback_toggle,
            self.wind_fallback_toggle,
            self.stokes_fallback_toggle,
            self.depth_fallback_toggle,
        ]:
            role_check.toggled.connect(self._mark_request_dirty)

        for field in [
            self.iteration_count,
            self.iteration_interval,
            self.model_time_step,
            self.fixed_start_hour,
            self.particle_count,
            self.release_radius,
            self.current_uncertainty,
            self.wind_uncertainty,
            self.current_fallback_x,
            self.current_fallback_y,
            self.wind_fallback_x,
            self.wind_fallback_y,
            self.stokes_fallback_x,
            self.stokes_fallback_y,
            self.depth_fallback_value,
            self.min_lon,
            self.max_lon,
            self.min_lat,
            self.max_lat,
            self.fixed_wind_percent,
            self.measurement_minimum,
            self.measurement_maximum,
            self.wind_min_percent,
            self.wind_max_percent,
            self.duration_threshold,
            self.fixed_duration_days,
            self.coverage_buffer,
            self.position_radial_step,
            self.position_max_radius,
            self.position_angle_step,
            self.position_max_attempts,
            self.selection_sample_size,
            self.selection_random_seed,
        ]:
            field.valueChanged.connect(self._mark_request_dirty)

    def _mark_request_dirty(self, *_: object) -> None:
        if self._restoring_project:
            return
        self.project_dirty = True
        self._invalidate_validation_feedback()
        if self._simulation_process is not None:
            return
        self._preflight_generation += 1
        had_result = self._last_preflight_result is not None
        self._last_preflight_result = None
        self.environment_page.set_readiness(None)
        preflight_running = (
            self._preflight_worker is not None
            and self._preflight_worker.isRunning()
        )
        if not self._is_validated:
            if preflight_running or had_result:
                self.request_state.setText("Draft")
                self.preview_health.setText("Not checked")
                self.review_run_page.set_state(ReviewRunState.UNVALIDATED)
                self.preview_state.setText("Setup changed")
                self.preview_state.setProperty("state", "idle")
                self._refresh_style(self.preview_state)
                self.review_run_page.reset_run_summary("Validate the updated setup")
            return

        self._is_validated = False
        self.request_state.setText("Draft")
        self.preview_health.setText("Not run")
        self.review_run_page.set_state(ReviewRunState.UNVALIDATED)
        self.preview_state.setText("Setup changed")
        self.preview_state.setProperty("state", "idle")
        self._refresh_style(self.preview_state)
        self.review_run_page.reset_run_summary("Validate changes")
        self._update_run_actions()

    def _update_run_actions(self) -> None:
        if self._simulation_process is not None:
            return
        if self.review_run_page.state in {
            ReviewRunState.COMPLETED,
            ReviewRunState.COMPLETED_WITH_ERRORS,
            ReviewRunState.FAILED,
        }:
            return
        if self._preflight_worker is not None and self._preflight_worker.isRunning():
            self.review_run_page.set_state(ReviewRunState.VALIDATING)
        elif self._is_validated:
            result = self._last_preflight_result
            has_warnings = bool(result) and (
                any(check.level == "warning" for check in result.checks)
                or any(
                    message.level == "warning"
                    for message in result.validation_messages
                )
            )
            self.review_run_page.set_state(
                ReviewRunState.READY_WITH_WARNINGS
                if has_warnings
                else ReviewRunState.READY
            )
        else:
            self.review_run_page.set_state(ReviewRunState.UNVALIDATED)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._confirm_replace_project():
            event.ignore()
            return
        if self._simulation_process is not None:
            self._simulation_process.terminate()
            if not self._simulation_process.waitForFinished(1500):
                self._simulation_process.kill()
                self._simulation_process.waitForFinished(1500)
        self._results_controller.shutdown()
        self.results_export_page.trajectory_map.shutdown()
        worker = self._preflight_worker
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(1500)
        for inspection_worker in tuple(self._environment_inspection_workers):
            if inspection_worker.isRunning():
                inspection_worker.requestInterruption()
                inspection_worker.wait(1500)
        for value_worker in tuple(self._observation_value_workers):
            if value_worker.isRunning():
                value_worker.requestInterruption()
                value_worker.wait(5000)
        super().closeEvent(event)
