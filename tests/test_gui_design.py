from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGroupBox, QLabel, QPushButton,
    QSizePolicy, QTableView,
)

from marine_drift_desktop.ui.components import (
    ActionButton,
    AnimatedComboBox,
    AnimatedStackedWidget,
    AnimatedToggle,
    OceanBackdrop,
    SelectionTile,
)
from marine_drift_desktop.ui.icons import ICON_NAMES
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from marine_drift_desktop.core.preflight import PreflightResult
from marine_drift_desktop.core.environment import EnvironmentalReaderInspection
from marine_drift_desktop.core.forcing_validation import ForcingCheck, ForcingReadiness
from marine_drift_desktop.ui.pages.environment_page import EnvironmentPage
from marine_drift_desktop.ui.pages.observation_page import ObservationPage
from marine_drift_desktop.ui.pages.review_run_page import ReviewRunPage
from marine_drift_desktop.ui.pages.simulation_setup_page import SimulationSetupPage
from marine_drift_desktop.ui.theme import build_stylesheet
from marine_drift_desktop.ui.trajectory_map import TrajectoryMapCanvas
from marine_drift_desktop.domain.presets import (
    list_column_mapping_presets,
    list_study_area_presets,
)
from tools.render_gui_review import (
    ENVIRONMENT_REVIEW_SIZES,
    ENVIRONMENT_REVIEW_STATES,
    OBSERVATION_REVIEW_SIZES,
    OBSERVATION_REVIEW_STATES,
    configure_observation_review_state,
    configure_environment_review_state,
)


class GuiDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = MarineDriftMainWindow()

    def tearDown(self) -> None:
        self.window.project_dirty = False
        self.window.close()

    def test_shell_uses_two_panes_without_persistent_run_panel(self) -> None:
        self.assertEqual(self.window.workbench_splitter.count(), 2)

    def test_model_physics_exposes_environmental_trajectory_fields(self) -> None:
        page = self.window.simulation_setup_page
        self.assertIn("sea_water_temperature", page.environment_export_checks)
        page.environment_export_checks["sea_water_temperature"].setChecked(True)
        self.window._collect_request_from_ui()
        self.assertEqual(
            self.window.request.settings.environment_export_variables,
            ["sea_water_temperature"],
        )

    def test_shell_supports_true_1080_pixel_compact_layout(self) -> None:
        self.assertLessEqual(self.window.minimumWidth(), 1080)
        self.window.resize(1080, 760)
        self.window.show()
        self.app.processEvents()
        self.assertEqual(self.window.width(), 1080)

    def test_navigation_lists_never_expose_horizontal_scrollbars(self) -> None:
        self.assertEqual(
            self.window.stage_navigation.horizontalScrollBarPolicy(),
            Qt.ScrollBarAlwaysOff,
        )
        self.assertEqual(
            self.window.simulation_setup_page.internal_step_list.horizontalScrollBarPolicy(),
            Qt.ScrollBarAlwaysOff,
        )

    def test_stage_hero_uses_compact_visual_chrome(self) -> None:
        icon = self.window.observation_page.findChild(QLabel, "StageHeroIcon")
        self.assertIsNotNone(icon)
        self.assertLessEqual(icon.width(), 50)

    def test_header_uses_the_branded_vector_logo(self) -> None:
        logo = self.window.findChild(QLabel, "BrandLogo")
        self.assertIsNotNone(logo)
        self.assertFalse(logo.pixmap().isNull())
        self.assertEqual(logo.width(), 44)
        image = logo.pixmap().toImage()
        self.assertEqual(image.pixelColor(0, image.height() // 2).alpha(), 0)

    def test_review_errors_header_opens_review_and_readiness_rows_navigate_to_step(self) -> None:
        self.window.show_workbench()
        self.window.preview_health.setText("Review errors")
        self.window.preview_health.click()
        self.assertEqual(self.window.stage_navigation.currentRow(), 3)

        from marine_drift_desktop.core.preflight import PreflightCheck
        self.window.review_run_page.set_readiness((PreflightCheck(
            key="observation-data", level="error", title="Observation data",
            detail="No observations selected.", target_step="stranding_data", blocks_run=True,
        ),))
        row = self.window.review_run_page.readiness_rows.itemAt(0).widget()
        row.findChild(ActionButton).click()
        self.assertEqual(self.window.stage_navigation.currentRow(), 0)

    def test_validation_issue_marks_and_opens_specific_setup_field(self) -> None:
        from marine_drift_desktop.core.preflight import PreflightCheck
        issue = PreflightCheck("windage", "error", "Missing windage", "Select the windage column.",
                               "simulation_setup", True, 3, ("wind_column",))
        self.window._apply_validation_feedback((issue,))
        self.assertEqual(self.window.wind_column.property("validationState"), "error")
        self.assertIn("1 errors", self.window.stage_navigation.item(2).text())
        self.window._go_to_validation_issue(issue)
        self.assertEqual(self.window.stage_navigation.currentRow(), 2)
        self.assertEqual(self.window.simulation_setup_page.current_step_index, 3)
        self.assertIn("Select the windage column", self.window.simulation_setup_page.step_feedback.text())

    def test_incomplete_preflight_does_not_claim_zero_source_records(self) -> None:
        from marine_drift_desktop.ui.pages.review_run_page import RunSummaryValues
        values = RunSummaryValues.from_request(self.window.request, PreflightResult())
        self.window.review_run_page.set_run_summary(values)
        self.assertIn("Not evaluated yet", self.window.review_run_page.observation_summary.text())

    def test_stranding_stage_is_owned_by_observation_page(self) -> None:
        self.assertIsInstance(self.window.observation_page, ObservationPage)
        self.assertIs(self.window.stage_stack.widget(0), self.window.observation_page)
        self.assertIs(self.window.dataset_path, self.window.observation_page.dataset_path)
        self.assertIs(
            self.window.identifier_column,
            self.window.observation_page.identifier_column,
        )

    def test_stranding_page_uses_semantic_source_and_mapping_cards(self) -> None:
        page = self.window.observation_page
        object_names = {
            widget.objectName() for widget in page.findChildren(QFrame)
        }
        self.assertTrue({
            "DataSourceCard", "FieldMappingCard", "RecordInformationCard",
            "ObservationTimeCard", "SpatialPositionCard",
        }.issubset(object_names))
        self.assertFalse(any(
            widget.title() == "Choose observations"
            for widget in page.findChildren(QGroupBox)
        ))

    def test_stranding_mapping_selectors_are_searchable_without_fixed_glyphs(self) -> None:
        selectors = [
            self.window.identifier_column,
            self.window.taxon_column,
            self.window.decomposition_column,
            self.window.date_column,
            self.window.time_column,
            self.window.observed_datetime_column,
            self.window.lon_column,
            self.window.lat_column,
        ]
        for selector in selectors:
            self.assertIsInstance(selector, AnimatedComboBox)
            self.assertEqual(selector.__class__.__name__, "SearchableColumnComboBox")
            self.assertTrue(selector.isEditable())
            self.assertEqual(selector.lineEdit().actions(), [])

    def test_all_column_selectors_share_the_same_searchable_component(self) -> None:
        selectors = (
            self.window.sst_column,
            self.window.wind_column,
            self.window.measurement_column,
            self.window.duration_column,
        )
        self.window.selection_mode.setCurrentIndex(
            self.window.selection_mode.findData("filter")
        )
        self.window.add_filter_condition_button.click()
        selectors += (self.window.filter_condition_rows[0].column,)
        self.assertTrue(all(
            selector.__class__.__name__ == "SearchableColumnComboBox"
            for selector in selectors
        ))

    def test_combined_datetime_mode_synchronizes_into_request_mapping(self) -> None:
        self.window.datetime_mode.setCurrentIndex(
            self.window.datetime_mode.findData("combined")
        )
        self.window.observed_datetime_column.setCurrentText("observed_at")

        self.window._sync_observation_mapping_from_ui()

        mapping = self.window.request.column_mapping
        self.assertEqual(mapping.datetime_mode, "combined")
        self.assertEqual(mapping.observed_datetime, "observed_at")

    def test_stranding_compact_mode_stacks_mapping_groups(self) -> None:
        page = self.window.observation_page
        page.set_compact_layout(True)

        positions = [
            page.mapping_groups_layout.getItemPosition(index)
            for index in range(page.mapping_groups_layout.count())
        ]
        self.assertEqual([position[0] for position in positions], [0, 1, 2])
        self.assertTrue(all(position[1] == 0 for position in positions))

    def test_stranding_metadata_and_group_states_are_explicit(self) -> None:
        page = self.window.observation_page
        page.set_dataset_metadata(
            "coastal_stranding_observations_2026.csv", "CSV", "1,248 rows", 9
        )
        page.update_mapping_states({
            "record_id", "taxon", "decomp", "date", "time", "lon", "lat"
        })

        self.assertIn("coastal_stranding", page.source_filename.text())
        self.assertEqual(page.source_format.text(), "CSV")
        self.assertEqual(page.source_rows.text(), "1,248 rows")
        self.assertEqual(page.source_columns.text(), "9 columns")
        self.assertEqual(page.record_information_card.property("state"), "incomplete")

    def test_stranding_page_exposes_required_mapping_progress(self) -> None:
        page = self.window.observation_page
        self.assertIsNotNone(getattr(page, "mapping_progress", None))
        self.assertIsNotNone(getattr(page, "mapping_progress_label", None))
        self.assertIsInstance(getattr(page, "mapping_indicators", None), dict)

    def test_decomposition_is_required_for_record_mapping_completion(self) -> None:
        configure_observation_review_state(self.window, "loaded_mapped")
        page = self.window.observation_page
        page.decomposition_column.setCurrentText("")
        page.update_mapping_states({
            "record_id", "taxon", "decomposition_code", "observed_date",
            "observed_time", "latitude", "longitude",
        })

        self.assertEqual(page.record_information_card.property("state"), "incomplete")

    def test_observation_review_contract_covers_default_and_mapped_sizes(self) -> None:
        self.assertEqual(OBSERVATION_REVIEW_STATES, ("default", "loaded_mapped"))
        self.assertEqual(OBSERVATION_REVIEW_SIZES["wide"], (1440, 900))
        self.assertLess(OBSERVATION_REVIEW_SIZES["compact"][0], 1440)

    def test_loaded_observation_review_state_is_complete_and_readable(self) -> None:
        configure_observation_review_state(self.window, "loaded_mapped")
        page = self.window.observation_page

        self.assertIn("coastal_stranding_observations", page.source_filename.text())
        self.assertEqual(page.source_filename.toolTip(), page.source_filename.text())
        self.assertEqual(page.source_format.text(), "CSV")
        self.assertTrue(all(
            card.property("state") == "valid"
            for card in (
                page.record_information_card,
                page.observation_time_card,
                page.spatial_position_card,
            )
        ))

    def test_compact_observation_source_keeps_browse_inside_card(self) -> None:
        self.window.resize(*OBSERVATION_REVIEW_SIZES["compact"])
        self.window.show()
        configure_observation_review_state(self.window, "loaded_mapped")
        self.app.processEvents()
        page = self.window.observation_page
        browse_right = page.browse_button.mapTo(
            page.data_source_card, page.browse_button.rect().bottomRight()
        ).x()
        self.assertLessEqual(browse_right, page.data_source_card.contentsRect().right())
        self.assertTrue(page._compact_layout)

    def test_environment_stage_is_owned_by_environment_page(self) -> None:
        self.assertIsInstance(self.window.environment_page, EnvironmentPage)
        self.assertIs(self.window.stage_stack.widget(1), self.window.environment_page)
        self.assertIs(
            self.window.environment_catalog_view,
            self.window.environment_page.catalog_view,
        )
        self.assertIs(
            self.window.output_directory,
            self.window.environment_page.output_directory,
        )

    def test_environment_catalog_fits_without_horizontal_scrolling(self) -> None:
        self.window.resize(1440, 900)
        self.window.show()
        configure_environment_review_state(self.window, "selected")
        self.app.processEvents()
        self.assertEqual(
            self.window.environment_catalog_view.horizontalScrollBar().maximum(), 0
        )

    def test_environment_compact_layout_preserves_inspector_without_overflow(self) -> None:
        self.window.resize(*ENVIRONMENT_REVIEW_SIZES["compact"])
        self.window.show()
        configure_environment_review_state(self.window, "selected")
        self.app.processEvents()
        page = self.window.environment_page

        self.assertEqual(page.catalog_splitter.orientation(), Qt.Horizontal)
        self.assertEqual(page.catalog_view.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(page.inspector_panel.width(), 240)

    def test_simulation_stage_is_owned_by_simulation_setup_page(self) -> None:
        self.assertIsInstance(self.window.simulation_setup_page, SimulationSetupPage)
        self.assertIs(
            self.window.stage_stack.widget(2),
            self.window.simulation_setup_page,
        )
        self.assertIs(
            self.window.particle_count,
            self.window.simulation_setup_page.particle_count,
        )
        self.assertIs(
            self.window.duration_mode,
            self.window.simulation_setup_page.duration_mode,
        )

    def test_review_stage_is_owned_by_review_run_page(self) -> None:
        self.assertIsInstance(self.window.review_run_page, ReviewRunPage)
        self.assertIs(self.window.stage_stack.widget(3), self.window.review_run_page)
        self.assertIs(
            self.window.preview_output,
            self.window.review_run_page.preview_output,
        )
        self.assertIs(
            self.window.run_simulations_button,
            self.window.review_run_page.run_simulations_button,
        )

    def test_shell_uses_quiet_canvas_and_animated_workflow(self) -> None:
        self.assertIsInstance(self.window.centralWidget(), QFrame)
        self.assertNotIsInstance(self.window.centralWidget(), OceanBackdrop)
        self.assertIsInstance(self.window.stage_stack, AnimatedStackedWidget)

    def test_header_exposes_only_operational_status_pills(self) -> None:
        pills = self.window.findChildren(QFrame, "StatusPill")
        self.assertEqual(len(pills), 2)
        self.assertTrue(self.window.stage_state.isHidden())

    def test_header_project_name_and_review_action(self) -> None:
        self.window.project_name.setText("Coastal drift study")
        self.window.project_name.editingFinished.emit()
        self.assertIn("Coastal drift study", self.window.windowTitle())
        self.window.project_name.setText("  ")
        self.window.project_name.editingFinished.emit()
        self.assertEqual(self.window.project_name.text(), "New reverse-drift project")
        self.window.request_state.click()
        self.assertEqual(self.window.stage_navigation.currentRow(), 3)
        self.window.request_state.setText("Validated")
        self.assertEqual(self.window.request_state.text(), "Validated")

    def test_workflow_uses_clear_step_names_and_icons(self) -> None:
        labels = [
            self.window.stage_navigation.item(index).text()
            for index in range(self.window.stage_navigation.count())
        ]
        self.assertEqual(
            labels,
            [
                "01  Stranding data",
                "02  Environmental forcing",
                "03  Simulation setup",
                "04  Review & run",
                "05  Results & export",
            ],
        )
        self.assertTrue(
            all(not self.window.stage_navigation.item(index).icon().isNull() for index in range(5))
        )

    def test_column_mapping_uses_animated_searchable_selectors(self) -> None:
        self.assertIsInstance(self.window.identifier_column, AnimatedComboBox)
        self.assertTrue(self.window.identifier_column.isEditable())

    def test_environment_uses_table_catalog_and_selected_reader_inspector(self) -> None:
        self.assertIsInstance(self.window.environment_catalog_view, QTableView)
        self.assertIsNotNone(self.window.environment_catalog_model)
        self.assertTrue(self.window.environment_page.role_items)
        self.assertFalse(hasattr(self.window.environment_page, "reader_role_checks"))

    def test_environment_catalog_is_the_simulation_request_source(self) -> None:
        path = Path(__file__).resolve().parents[1] / ".tmp_tests" / "catalog_ui.nc"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        self.window.environment_catalog_model.add_paths([path])
        self.window.environment_catalog_model.apply_inspection(
            path,
            EnvironmentalReaderInspection(
                path=path,
                recognized_opendrift_variables=["x_sea_water_velocity"],
            ),
        )
        self.window.environment_catalog_model.update_roles(
            path, ["Ocean circulation"], source="user"
        )

        self.assertEqual(len(self.window.environment_readers), 1)
        self.assertEqual(
            self.window.environment_readers[0].roles, ["Ocean circulation"]
        )

    def test_environment_page_exposes_coverage_preview_and_readiness_checks(self) -> None:
        page = self.window.environment_page
        self.assertFalse(page.preview_coverage_button.isEnabled())
        self.assertLessEqual(page.catalog_group.maximumHeight(), 390)
        self.assertEqual(
            set(page.readiness_labels),
            {
                "required_currents",
                "temporal_coverage",
                "spatial_coverage",
                "optional_forcing",
                "unused_datasets",
            },
        )
        page.set_readiness(
            ForcingReadiness(
                (
                    ForcingCheck(
                        "required_currents",
                        "success",
                        "Required currents",
                        "Two datasets are ready.",
                    ),
                )
            )
        )
        self.assertIn(
            "Two datasets are ready",
            page.readiness_labels["required_currents"].text(),
        )

    def test_environment_review_defines_every_required_visual_state(self) -> None:
        self.assertEqual(
            ENVIRONMENT_REVIEW_STATES,
            ("empty", "populated", "selected", "warning", "readiness"),
        )
        self.assertEqual(ENVIRONMENT_REVIEW_SIZES["wide"], (1440, 900))
        self.assertLess(ENVIRONMENT_REVIEW_SIZES["compact"][0], 1440)

    def test_environment_layout_keeps_catalog_actions_and_readiness_visible(self) -> None:
        for width, height in ENVIRONMENT_REVIEW_SIZES.values():
            with self.subTest(width=width, height=height):
                self.window.resize(width, height)
                self.window.show()
                self.window.stage_navigation.setCurrentRow(1)
                self.app.processEvents()
                page = self.window.environment_page
                table_width, inspector_width = page.catalog_splitter.sizes()
                self.assertGreater(table_width, inspector_width)
                self.assertTrue(page.add_files_button.isVisibleTo(self.window))
                self.assertTrue(page.add_folder_button.isVisibleTo(self.window))
                self.assertLess(
                    page.readiness_labels["required_currents"].mapTo(
                        self.window, page.readiness_labels["required_currents"].rect().topLeft()
                    ).y(),
                    height,
                )

    def test_environment_selected_and_error_states_keep_context_visible(self) -> None:
        configure_environment_review_state(self.window, "selected")
        page = self.window.environment_page
        selected = page.selected_entry()
        self.assertIsNotNone(selected)
        self.assertEqual(page.inspector_title.text(), selected.path.name)
        self.assertTrue(page.preview_coverage_button.isEnabled())

        configure_environment_review_state(self.window, "warning")
        statuses = [
            page.catalog_model.data(page.catalog_model.index(row, 4))
            for row in range(page.catalog_model.rowCount())
        ]
        self.assertIn("Review", statuses)
        self.assertIn("Blocking error", statuses)
        self.assertTrue(page.inspector_title.text())
        self.assertFalse(page.empty_state.isVisible())

    def test_selected_environment_reader_does_not_squeeze_catalog_table(self) -> None:
        for width, height in ENVIRONMENT_REVIEW_SIZES.values():
            with self.subTest(width=width, height=height):
                self.window.resize(width, height)
                self.window.show()
                configure_environment_review_state(self.window, "selected")
                self.app.processEvents()
                table_width, inspector_width = (
                    self.window.environment_page.catalog_splitter.sizes()
                )
                self.assertGreater(table_width, inspector_width)

    def test_primary_navigation_and_run_actions_use_shared_button_component(self) -> None:
        self.assertIsInstance(self.window.next_button, ActionButton)
        self.assertIsInstance(self.window.run_simulations_button, ActionButton)
        self.assertIsInstance(self.window.cancel_run_button, ActionButton)

    def test_icon_vocabulary_covers_the_scientific_workflow(self) -> None:
        self.assertTrue({
            "observations", "forcing", "setup", "review", "location", "run",
            "currents", "wind", "waves", "bathymetry", "netcdf", "uncertainty",
            "validation", "folder", "search", "close", "chevron",
        }.issubset(ICON_NAMES))

    def test_loading_button_restores_its_previous_enabled_state(self) -> None:
        button = ActionButton("Run")
        button.setEnabled(False)
        button.setLoading(True)
        button.setLoading(False)
        self.assertFalse(button.isEnabled())

    def test_selection_tiles_expand_to_fill_the_role_grid(self) -> None:
        tile = SelectionTile("Currents")
        self.assertEqual(
            tile.sizePolicy().horizontalPolicy(), QSizePolicy.Policy.Expanding
        )
        self.assertEqual(tile.property("role"), "selection-tile")
        self.assertIn(
            'QToolButton[role="selection-tile"]:checked',
            build_stylesheet("Segoe UI"),
        )

    def test_animated_toggle_changes_checked_state_with_keyboard(self) -> None:
        toggle = AnimatedToggle("Use environmental coverage")
        toggle.show()
        toggle.setFocus()
        QTest.keyClick(toggle, Qt.Key_Space)
        self.assertTrue(toggle.isChecked())

    def test_toggle_uses_the_shared_sea_glass_checked_style(self) -> None:
        self.assertIn(
            'QAbstractButton[role="animated-toggle"]:checked',
            build_stylesheet("Segoe UI"),
        )

    def test_extent_controls_switch_to_environmental_coverage(self) -> None:
        self.window.coverage_toggle.setChecked(True)
        self.assertFalse(self.window.min_lon.isEnabled())
        self.assertFalse(self.window.apply_detected_extent_button.isHidden())

    def test_position_search_controls_only_show_when_enabled(self) -> None:
        self.window.position_search_toggle.setChecked(False)
        self.assertTrue(self.window.position_search_advanced.isHidden())
        self.window.position_search_toggle.setChecked(True)
        self.assertFalse(self.window.position_search_advanced.isHidden())

    def test_stale_preflight_result_cannot_mark_edited_request_ready(self) -> None:
        self.window._preflight_generation = 2
        stale_result = PreflightResult(
            preparation_performed=True,
            runnable_observations=1,
        )

        self.window._preflight_completed(1, stale_result)

        self.assertFalse(self.window._is_validated)

    def test_edit_during_preflight_replaces_checking_state_with_dirty_state(self) -> None:
        class RunningWorker:
            @staticmethod
            def isRunning() -> bool:
                return True

            @staticmethod
            def wait() -> None:
                return None

        self.window._preflight_worker = RunningWorker()
        self.window._is_validated = False
        self.window.preview_state.setText("Checking configuration")

        self.window._mark_request_dirty()

        self.assertEqual(self.window.preview_state.text(), "Setup changed")
        self.window._preflight_worker = None

    def test_filter_selection_adds_searchable_column_condition(self) -> None:
        self.window.selection_mode.setCurrentIndex(
            self.window.selection_mode.findData("filter")
        )
        self.window.add_filter_condition_button.click()
        self.assertEqual(len(self.window.filter_condition_rows), 1)
        self.assertIsInstance(
            self.window.filter_condition_rows[0].column, AnimatedComboBox
        )

    def test_new_model_controls_are_synchronized_into_the_run_request(self) -> None:
        self.window.coverage_toggle.setChecked(True)
        self.window.coverage_buffer.setValue(0.25)
        self.window.position_search_toggle.setChecked(True)
        self.window.position_max_radius.setValue(0.75)
        self.window.selection_mode.setCurrentIndex(
            self.window.selection_mode.findData("random")
        )
        self.window.selection_sample_size.setValue(12)
        self.window.selection_random_seed.setValue(77)

        self.window._preview_configuration()

        settings = self.window.request.settings
        self.assertEqual(settings.coverage.mode, "environment_intersection")
        self.assertEqual(settings.coverage.buffer_degrees, 0.25)
        self.assertEqual(settings.position_search.mode, "search_nearby_water")
        self.assertEqual(settings.position_search.max_radius_degrees, 0.75)
        self.assertEqual(settings.observation_selection.mode, "random")
        self.assertEqual(settings.observation_selection.sample_size, 12)
        self.assertEqual(settings.observation_selection.random_seed, 77)

    def test_button_remains_visible_without_graphics_effect_during_hover(self) -> None:
        button = ActionButton("Run")
        button.resize(120, 44)
        button.show()
        QTest.mouseMove(button)
        QTest.qWait(180)
        initial_size = button.size()
        self.assertIsNone(button.graphicsEffect())
        QTest.mousePress(button, Qt.LeftButton)
        QTest.qWait(100)
        self.assertTrue(button.isVisible())
        QTest.mouseRelease(button, Qt.LeftButton)
        self.assertEqual(button.size(), initial_size)
        self.assertIsNone(button.graphicsEffect())
        button.close()

    def test_user_facing_presets_do_not_expose_legacy_project_or_region(self) -> None:
        self.assertEqual(list_column_mapping_presets(), ["Map columns manually"])
        self.assertEqual(list_study_area_presets(), ["Global extent"])

    def test_visible_copy_uses_generalized_current_workflow_language(self) -> None:
        text = " ".join(
            [label.text() for label in self.window.stage_stack.findChildren(QLabel)]
            + [
                combo.itemText(index)
                for combo in self.window.stage_stack.findChildren(QComboBox)
                for index in range(combo.count())
            ]
        ).lower()
        for forbidden in ("fonseca", "turtle_id", "southwest atlantic"):
            self.assertNotIn(forbidden, text)
        self.assertIn("specimen measurement", text)
        self.assertIn("spatial extent", text)

    def test_palette_uses_one_harmonized_ink_and_sea_glass_system(self) -> None:
        stylesheet = build_stylesheet("Segoe UI")
        self.assertIn("#102733", stylesheet)
        self.assertIn("#67c6b0", stylesheet)
        self.assertNotIn("#1d1d1f", stylesheet)
        self.assertNotIn("#54c6c7", stylesheet)

    def test_visual_system_defines_clear_navigation_focus_and_status_states(self) -> None:
        stylesheet = build_stylesheet("Segoe UI")
        self.assertIn("qlineargradient(x1:0, y1:0, x2:1, y2:0", stylesheet)
        self.assertIn("border-left: 4px solid #5fc8b5", stylesheet)
        self.assertIn("background: #eef8f9", stylesheet)
        self.assertIn('QLabel#MappingGroupState[state="valid"]', stylesheet)
        self.assertIn("font-size: 10.5px", stylesheet)

    def test_trajectory_palette_is_curated_and_distinguishes_adjacent_runs(self) -> None:
        expected = ("#088395", "#e86a33", "#2e8a57", "#845ec2")
        colors = tuple(TrajectoryMapCanvas._color(index).name() for index in range(4))
        self.assertEqual(colors, expected)
        self.assertEqual(len(set(colors)), len(colors))

    def test_notes_and_duplicate_prepare_buttons_are_removed(self) -> None:
        labels = [button.text() for button in self.window.findChildren(QPushButton)]
        self.assertNotIn("Notes", labels)
        self.assertNotIn("Prepare run", labels)
        self.assertNotIn("Export run plan", labels)
        self.assertIn("Run simulations", labels)
        self.assertIn("Cancel run", labels)
        self.assertNotIn("Load example project", labels)
        self.assertNotIn("Run example simulation", labels)

    def test_obsolete_gui_orchestration_paths_are_removed(self) -> None:
        for attribute in (
            "run_buttons",
            "simulation_service",
            "_example_loaded",
            "_example_process",
            "example_run_button",
            "summary_validity",
            "summary_output",
            "summary_messages",
        ):
            self.assertFalse(hasattr(self.window, attribute), attribute)
        self.assertFalse(hasattr(self.window.review_run_page, "example_run_button"))


if __name__ == "__main__":
    unittest.main()
