from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from marine_drift_desktop.core.environment import (
    EnvironmentalDiagnostic,
    EnvironmentalReaderInspection,
)
from marine_drift_desktop.core.forcing_validation import ForcingCheck, ForcingReadiness
from marine_drift_desktop.core.preflight import PreflightCheck, PreflightResult
from marine_drift_desktop.domain.models import (
    EnvironmentalReaderConfig,
    SimulationRequest,
    SpatialExtent,
)
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from marine_drift_desktop.ui.pages.review_run_page import (
    ReviewRunState,
    RunSummaryValues,
)
from marine_drift_desktop.ui.theme import build_stylesheet

OBSERVATION_REVIEW_STATES = ("default", "loaded_mapped")
OBSERVATION_REVIEW_SIZES = {
    "wide": (1440, 900),
    "compact": (1080, 760),
}

ENVIRONMENT_REVIEW_STATES = (
    "empty",
    "populated",
    "selected",
    "warning",
    "readiness",
)
ENVIRONMENT_REVIEW_SIZES = {
    "wide": (1440, 900),
    "compact": (1080, 760),
}


@dataclass(frozen=True, slots=True)
class SimulationReviewCase:
    name: str
    step_index: int
    state: str


SIMULATION_REVIEW_SIZES = {
    "wide": (1440, 900),
    "compact": (1080, 760),
}
SIMULATION_REVIEW_CASES = (
    SimulationReviewCase("study_default", 0, "default"),
    SimulationReviewCase("observations_advanced", 1, "advanced-expanded"),
    SimulationReviewCase("duration_incomplete", 2, "incomplete"),
    SimulationReviewCase("windage_valid", 3, "valid"),
    SimulationReviewCase("release_warning", 4, "warning"),
    SimulationReviewCase("physics_valid", 5, "valid"),
)


def configure_observation_review_state(
    window: MarineDriftMainWindow,
    state: str,
) -> None:
    if state not in OBSERVATION_REVIEW_STATES:
        raise ValueError(f"Unknown observation review state: {state}")
    window.stage_navigation.setCurrentRow(0)
    page = window.observation_page
    page.dataset_path.blockSignals(True)
    page.dataset_path.clear()
    page.dataset_path.blockSignals(False)
    page.set_dataset_metadata(
        "No dataset selected", "Not detected", "Checked during validation", 0
    )
    for selector in page._mapping_selectors():
        selector.blockSignals(True)
        selector.clear()
        selector.addItem("")
        selector.blockSignals(False)
    page.datetime_mode.setCurrentIndex(page.datetime_mode.findData("separate"))
    page.update_mapping_states(set())
    if state == "default":
        return

    filename = "coastal_stranding_observations_2020_2026_quality_checked.csv"
    columns = (
        "record_id", "taxon", "decomposition_code", "observed_date",
        "observed_time", "latitude", "longitude", "observer_notes",
        "body_length_cm",
    )
    page.dataset_path.blockSignals(True)
    page.dataset_path.setText(
        f"C:/Research/Marine Drift Workbench/Observation datasets/{filename}"
    )
    page.dataset_path.blockSignals(False)
    for selector in page._mapping_selectors():
        selector.blockSignals(True)
        selector.addItems(columns)
        selector.blockSignals(False)
    mappings = (
        (page.identifier_column, "record_id"),
        (page.taxon_column, "taxon"),
        (page.decomposition_column, "decomposition_code"),
        (page.date_column, "observed_date"),
        (page.time_column, "observed_time"),
        (page.lat_column, "latitude"),
        (page.lon_column, "longitude"),
    )
    for selector, value in mappings:
        selector.setCurrentText(value)
    page.set_dataset_metadata(filename, "CSV", "1,248 rows", len(columns))
    page.dataset_inspection.setText(
        "9 columns detected from file metadata. Records will be checked during validation."
    )
    page.update_mapping_states(columns)


def render_observation_review(
    app: QApplication, output_directory: Path
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for size_name, (width, height) in OBSERVATION_REVIEW_SIZES.items():
        for state in OBSERVATION_REVIEW_STATES:
            window = MarineDriftMainWindow()
            window.resize(width, height)
            window.show()
            configure_observation_review_state(window, state)
            QTest.qWait(280)
            output_path = output_directory / f"observation_{size_name}_{state}.png"
            window.grab().save(str(output_path))
            outputs.append(output_path.resolve())
            window.close()
    return outputs


@dataclass(frozen=True, slots=True)
class ReviewRunReviewCase:
    name: str
    state: ReviewRunState


REVIEW_RUN_REVIEW_SIZES = {
    "wide": (1440, 900),
    "compact": (1080, 760),
}
REVIEW_RUN_REVIEW_CASES = (
    ReviewRunReviewCase("unvalidated", ReviewRunState.UNVALIDATED),
    ReviewRunReviewCase("blocked", ReviewRunState.BLOCKED),
    ReviewRunReviewCase("ready", ReviewRunState.READY),
    ReviewRunReviewCase("running", ReviewRunState.RUNNING),
    ReviewRunReviewCase("completed", ReviewRunState.COMPLETED),
    ReviewRunReviewCase(
        "completed_with_warnings", ReviewRunState.COMPLETED_WITH_ERRORS
    ),
)


def _inspection(
    path: Path,
    *,
    variables: list[str],
    extent: SpatialExtent,
    warning: str = "",
) -> EnvironmentalReaderInspection:
    diagnostics = (
        [EnvironmentalDiagnostic("warning", "partial_coverage", warning)]
        if warning
        else []
    )
    return EnvironmentalReaderInspection(
        path=path,
        variables=["time", "latitude", "longitude", *variables],
        dimensions={"time": 8_784, "latitude": 180, "longitude": 240},
        coordinate_variables=["time", "latitude", "longitude"],
        recognized_opendrift_variables=variables,
        compatibility_message="Recognized by OpenDrift",
        extent=extent,
        longitude_name="longitude",
        latitude_name="latitude",
        longitude_convention="-180 to 180",
        coverage_warning=warning,
        time_name="time",
        time_start="2020-01-01 00:00",
        time_end="2020-12-31 23:00",
        time_count=8_784,
        temporal_resolution_seconds=3_600.0,
        time_is_monotonic=True,
        time_is_regular=True,
        grid_type="rectilinear",
        longitude_resolution=0.25,
        latitude_resolution=0.25,
        crs="EPSG:4326",
        diagnostics=diagnostics,
    )


def _populate_environment_catalog(window: MarineDriftMainWindow, *, warning: bool) -> None:
    model = window.environment_page.catalog_model
    fixture_directory = Path(".tmp_tests/gui_redesign_review/fixtures")
    fixtures = (
        (
            fixture_directory / "regional_currents_2020.nc",
            ["x_sea_water_velocity", "y_sea_water_velocity"],
            SpatialExtent(-52.0, -32.0, -36.0, -18.0),
        ),
        (
            fixture_directory / "regional_wind_2020.nc",
            ["x_wind", "y_wind"],
            SpatialExtent(-55.0, -30.0, -38.0, -16.0),
        ),
        (
            fixture_directory / "regional_waves_2020.nc",
            ["sea_surface_wave_stokes_drift_x_velocity"],
            SpatialExtent(-49.0, -35.0, -34.0, -20.0),
        ),
        (
            fixture_directory / "temperature_2020.nc",
            ["sea_water_temperature"],
            SpatialExtent(-52.0, -32.0, -36.0, -18.0),
        ),
    )
    model.add_paths([path for path, _, _ in fixtures])
    for index, (path, variables, extent) in enumerate(fixtures):
        message = "Dataset covers only part of the configured study area." if warning and index == 0 else ""
        model.apply_inspection(
            path,
            _inspection(path, variables=variables, extent=extent, warning=message),
        )
    if warning:
        unreadable_path = fixture_directory / "unreadable_forcing.nc"
        model.add_paths([unreadable_path])
        model.apply_error(
            unreadable_path,
            "NetCDF metadata could not be read. Check the file format or permissions.",
        )


def configure_environment_review_state(
    window: MarineDriftMainWindow,
    state: str,
) -> None:
    if state not in ENVIRONMENT_REVIEW_STATES:
        raise ValueError(f"Unknown environmental review state: {state}")
    window.stage_navigation.setCurrentRow(1)
    page = window.environment_page
    page.catalog_view.clearSelection()
    page.catalog_model.remove_rows(list(range(page.catalog_model.rowCount())))
    page.set_readiness(None)
    if state == "empty":
        return

    _populate_environment_catalog(window, warning=state == "warning")
    if state in {"selected", "warning", "readiness"}:
        page.catalog_view.selectRow(0)
        page.refresh_selected_entry()

    if state == "warning":
        page.set_readiness(
            ForcingReadiness(
                (
                    ForcingCheck("required_currents", "success", "Required currents", "1 dataset available."),
                    ForcingCheck("temporal_coverage", "success", "Temporal coverage", "Required period covered."),
                    ForcingCheck("spatial_coverage", "warning", "Spatial coverage", "Partial coverage; review extent."),
                    ForcingCheck("optional_forcing", "info", "Optional forcing", "Wind, waves, and temperature available."),
                    ForcingCheck("unused_datasets", "success", "Unused datasets", "All datasets have a model role."),
                )
            )
        )
    elif state == "readiness":
        page.set_readiness(
            ForcingReadiness(
                (
                    ForcingCheck("required_currents", "success", "Required currents", "1 dataset available."),
                    ForcingCheck("temporal_coverage", "success", "Temporal coverage", "Required period covered."),
                    ForcingCheck("spatial_coverage", "success", "Spatial coverage", "Study area fully covered."),
                    ForcingCheck("optional_forcing", "info", "Optional forcing", "Wind, waves, and temperature available."),
                    ForcingCheck("unused_datasets", "success", "Unused datasets", "All datasets have a model role."),
                )
            )
        )


def render_environment_review(app: QApplication, output_directory: Path) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for size_name, (width, height) in ENVIRONMENT_REVIEW_SIZES.items():
        for state in ENVIRONMENT_REVIEW_STATES:
            window = MarineDriftMainWindow()
            window.resize(width, height)
            window.show()
            configure_environment_review_state(window, state)
            QTest.qWait(260)
            if state in {"warning", "readiness"}:
                page = window.environment_page
                page.ensureWidgetVisible(
                    page.readiness_labels["required_currents"], 0, 24
                )
                QTest.qWait(80)
            output_path = output_directory / f"environment_{size_name}_{state}.png"
            window.grab().save(str(output_path))
            outputs.append(output_path.resolve())
            window.close()
    return outputs


def configure_simulation_review_case(
    window: MarineDriftMainWindow,
    case_name: str,
) -> None:
    cases = {case.name: case for case in SIMULATION_REVIEW_CASES}
    if case_name not in cases:
        raise ValueError(f"Unknown simulation review case: {case_name}")
    case = cases[case_name]
    window.stage_navigation.setCurrentRow(2)
    page = window.simulation_setup_page
    page.step_states = {index: "not_started" for index in range(6)}
    page.step_feedback.hide()

    page.coverage_toggle.setChecked(False)
    page.position_search_toggle.setChecked(False)
    page.selection_mode.setCurrentIndex(page.selection_mode.findData("all"))
    page.duration_mode.setCurrentIndex(page.duration_mode.findData("estimated"))
    page.sst_column.setCurrentText("")
    page.wind_mode.setCurrentIndex(page.wind_mode.findData("dataset"))
    page.wind_column.setCurrentText("")
    page.release_strategy.setCurrentIndex(
        page.release_strategy.findData("multiple")
    )
    page.iteration_count.setValue(15)
    page.particle_count.setValue(1)
    page.current_uncertainty_toggle.setChecked(True)
    page.wind_uncertainty_toggle.setChecked(True)

    if case.name == "observations_advanced":
        page.position_search_toggle.setChecked(True)
    elif case.name == "windage_valid":
        page.wind_mode.setCurrentIndex(page.wind_mode.findData("none"))
    elif case.name == "release_warning":
        page.particle_count.setValue(100_000)

    page.set_current_step(case.step_index)
    if case.state in {"incomplete", "valid", "warning"}:
        state, message = page.validate_step(case.step_index)
        page._set_step_state(case.step_index, state)
        if state in {"incomplete", "warning"}:
            page.step_feedback.setText(message)
            page.step_feedback.setProperty("level", state)
            page.step_feedback.show()
            page._refresh_widget_style(page.step_feedback)
    elif case.state == "advanced-expanded":
        page._set_step_state(case.step_index, "valid")
    page._update_summaries()


def render_simulation_review(app: QApplication, output_directory: Path) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for size_name, (width, height) in SIMULATION_REVIEW_SIZES.items():
        for case in SIMULATION_REVIEW_CASES:
            window = MarineDriftMainWindow()
            window.resize(width, height)
            window.show()
            configure_simulation_review_case(window, case.name)
            QTest.qWait(280)
            page = window.simulation_setup_page
            if size_name == "compact" and case.step_index >= 4:
                page.summary_scroll.ensureWidgetVisible(
                    page.summary_labels[case.step_index], 0, 16
                )
                QTest.qWait(80)
            output_path = output_directory / f"simulation_{size_name}_{case.name}.png"
            window.grab().save(str(output_path))
            outputs.append(output_path.resolve())
            window.close()
    return outputs


def _review_request() -> tuple[SimulationRequest, PreflightResult]:
    request = SimulationRequest()
    request.data_sources.observation_dataset = Path("C:/Research/observations.csv")
    request.data_sources.output_directory = Path(
        "C:/Research/Marine Drift Workbench/Coastal strandings"
    )
    request.data_sources.environment_readers = [
        EnvironmentalReaderConfig(Path("regional_currents.nc"), ["Currents"]),
        EnvironmentalReaderConfig(Path("regional_wind.nc"), ["Wind"]),
        EnvironmentalReaderConfig(Path("regional_waves.nc"), ["Waves"]),
    ]
    request.settings.iteration_count = 12
    request.settings.particle_count = 250
    request.settings.duration.mode = "fixed"
    request.settings.duration.fixed_days = 8
    request.settings.wind_drift.mode = "measurement"
    result = PreflightResult(
        preparation_performed=True,
        source_rows=1_248,
        selected_rows=320,
        runnable_observations=314,
        skipped_observations=6,
        planned_model_iterations=3_768,
        planned_particle_trajectories=942_000,
    )
    return request, result


def configure_review_run_state(
    window: MarineDriftMainWindow,
    state_name: str,
) -> None:
    cases = {case.name: case for case in REVIEW_RUN_REVIEW_CASES}
    if state_name not in cases:
        raise ValueError(f"Unknown Review & Run state: {state_name}")
    case = cases[state_name]
    window.stage_navigation.setCurrentRow(3)
    page = window.review_run_page
    request, result = _review_request()
    window.request = request
    window.output_directory.setText(str(request.data_sources.output_directory))
    page.continue_errors_toggle.setChecked(True)
    for label in (
        page.observation_summary,
        page.trajectory_summary,
        page.duration_summary,
        page.windage_summary,
        page.forcing_summary,
        page.extent_summary,
    ):
        label.setText("Validate to calculate")
    page.preview_output.clear()
    page.run_progress.setRange(0, 100)
    page.run_progress.setValue(0)
    page.run_progress.setFormat("Waiting")

    if case.state == ReviewRunState.UNVALIDATED:
        page.set_readiness(())
        page.readiness_blocking_count.setText("Not checked")
        page.readiness_warning_count.setText("Checks pending")
        page.set_state(case.state)
        return

    checks = [
        PreflightCheck(
            "observations", "success", "Observation data",
            "314 observations are ready; 6 selected rows will be skipped.",
            "stranding_data",
        ),
        PreflightCheck(
            "forcing", "success", "Environmental forcing",
            "Currents, wind, and waves cover the requested period.",
            "environmental_forcing",
        ),
        PreflightCheck(
            "output", "success", "Output directory",
            "The selected local destination is writable.", "review_run",
        ),
    ]
    if case.state == ReviewRunState.BLOCKED:
        checks[1] = PreflightCheck(
            "forcing", "error", "Environmental forcing",
            "Currents end before 18 selected observations complete their drift window.",
            "environmental_forcing", blocks_run=True,
        )
    elif case.state == ReviewRunState.COMPLETED_WITH_ERRORS:
        checks.append(
            PreflightCheck(
                "failures", "warning", "Individual simulation failures",
                "3 trajectories failed and were recorded for review.",
                "review_run",
            )
        )
    page.set_readiness(checks)
    page.set_run_summary(RunSummaryValues.from_request(request, result))
    page.preview_output.setPlainText(
        "Project validation completed.\n"
        "Observation schema checked.\n"
        "Environmental coverage verified.\n"
        "Serialized request is ready for local execution."
    )
    page.set_state(case.state)

    if case.state == ReviewRunState.RUNNING:
        page.update_activity({
            "event": "progress", "processed": 1_695, "total_jobs": 3_768,
            "completed": 1_692, "failed": 3, "batch": 1,
            "elapsed_seconds": 1_427,
        })
    elif case.state in {
        ReviewRunState.COMPLETED,
        ReviewRunState.COMPLETED_WITH_ERRORS,
    }:
        failures = 3 if case.state == ReviewRunState.COMPLETED_WITH_ERRORS else 0
        page.update_activity({
            "event": "finished", "total_jobs": 3_768,
            "completed": 3_768 - failures, "failed": failures,
            "batch": 1, "elapsed_seconds": 3_242,
        })


def render_review_run_review(
    app: QApplication, output_directory: Path
) -> list[Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for size_name, (width, height) in REVIEW_RUN_REVIEW_SIZES.items():
        for case in REVIEW_RUN_REVIEW_CASES:
            window = MarineDriftMainWindow()
            window.resize(width, height)
            window.show()
            configure_review_run_state(window, case.name)
            QTest.qWait(280)
            output_path = (
                output_directory / f"review_run_{size_name}_{case.name}.png"
            )
            window.grab().save(str(output_path))
            outputs.append(output_path.resolve())
            window.close()
    return outputs


def main() -> None:
    output_directory = Path(".tmp_tests/gui_review")
    output_directory.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
    window = MarineDriftMainWindow()
    window.resize(1440, 900)
    window.show()
    app.processEvents()

    for index in range(window.stage_navigation.count()):
        window.stage_navigation.setCurrentRow(index)
        QTest.qWait(260)
        output_path = output_directory / f"stage_{index + 1}.png"
        window.grab().save(str(output_path))
        print(output_path.resolve())

    window.close()

    for output_path in render_observation_review(
        app, Path(".tmp_tests/gui_redesign_review")
    ):
        print(output_path)
    for output_path in render_environment_review(
        app, Path(".tmp_tests/gui_redesign_review")
    ):
        print(output_path)
    for output_path in render_simulation_review(
        app, Path(".tmp_tests/gui_redesign_review")
    ):
        print(output_path)
    for output_path in render_review_run_review(
        app, Path(".tmp_tests/gui_redesign_review")
    ):
        print(output_path)


if __name__ == "__main__":
    main()
