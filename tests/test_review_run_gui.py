from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox

from marine_drift_desktop.core.preflight import PreflightCheck, PreflightResult, run_preflight
from marine_drift_desktop.core.validation import validate_output_destination
from marine_drift_desktop.domain.models import EnvironmentalReaderConfig, SimulationRequest
from marine_drift_desktop.ui.pages.review_run_page import (
    ReviewRunPage,
    ReviewRunState,
    RunSummaryValues,
)
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from tools.render_gui_review import (
    REVIEW_RUN_REVIEW_CASES,
    REVIEW_RUN_REVIEW_SIZES,
    configure_review_run_state,
)


class ReviewRunPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = ReviewRunPage(QGroupBox("Output destination"))

    def tearDown(self) -> None:
        self.page.close()

    def test_primary_action_is_selected_exclusively_by_page_state(self) -> None:
        expected = {
            ReviewRunState.UNVALIDATED: "validate",
            ReviewRunState.VALIDATING: "validate",
            ReviewRunState.BLOCKED: "validate",
            ReviewRunState.READY_WITH_WARNINGS: "run",
            ReviewRunState.READY: "run",
            ReviewRunState.RUNNING: "cancel",
            ReviewRunState.CANCELLING: "cancel",
            ReviewRunState.COMPLETED: "open",
            ReviewRunState.COMPLETED_WITH_ERRORS: "open",
            ReviewRunState.FAILED: "validate",
        }
        actions = {
            "validate": self.page.validate_button,
            "run": self.page.run_simulations_button,
            "cancel": self.page.cancel_run_button,
            "open": self.page.open_results_button,
        }

        for state, visible_action in expected.items():
            with self.subTest(state=state):
                self.page.set_state(state)
                visible = [name for name, button in actions.items() if not button.isHidden()]
                self.assertEqual(visible, [visible_action])

    def test_busy_states_use_loading_labels_and_restore_action_text(self) -> None:
        self.page.set_state(ReviewRunState.VALIDATING)
        self.assertEqual(self.page.validate_button.text(), "Validating...")
        self.assertFalse(self.page.validate_button.isEnabled())

        self.page.set_state(ReviewRunState.READY)
        self.assertEqual(self.page.validate_button.text(), "Validate project")

        self.page.set_state(ReviewRunState.CANCELLING)
        self.assertEqual(self.page.cancel_run_button.text(), "Stopping...")
        self.assertFalse(self.page.cancel_run_button.isEnabled())

    def test_readiness_distinguishes_blocking_checks_from_warnings(self) -> None:
        checks = (
            PreflightCheck(
                key="observations", level="warning", title="Observation data",
                detail="Two selected rows will be skipped.",
                target_step="stranding_data", blocks_run=False,
            ),
            PreflightCheck(
                key="forcing", level="error", title="Environmental forcing",
                detail="Currents do not cover the requested dates.",
                target_step="environmental_forcing", blocks_run=True,
            ),
        )

        self.page.set_readiness(checks)

        self.assertEqual(self.page.readiness_warning_count.text(), "1 warning")
        self.assertEqual(self.page.readiness_blocking_count.text(), "1 blocking")
        self.assertEqual(self.page.readiness_rows.count(), 2)
        self.assertEqual(
            self.page.readiness_rows.itemAt(0).widget().property("targetStep"),
            "environmental_forcing",
        )

    def test_summary_is_derived_from_request_and_preflight_workload(self) -> None:
        request = SimulationRequest()
        request.settings.iteration_count = 3
        request.settings.particle_count = 5
        request.settings.duration.mode = "fixed"
        request.settings.duration.fixed_days = 8
        request.settings.wind_drift.mode = "none"
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(Path("currents.nc"), ["Currents"]),
            EnvironmentalReaderConfig(Path("wind.nc"), ["Wind"]),
        ]
        result = PreflightResult(
            preparation_performed=True,
            source_rows=10,
            selected_rows=6,
            runnable_observations=4,
            skipped_observations=2,
            planned_model_iterations=12,
            planned_particle_trajectories=60,
        )

        summary = RunSummaryValues.from_request(request, result)
        self.page.set_run_summary(summary)

        self.assertEqual(summary.selected_rows, 6)
        self.assertEqual(summary.valid_rows, 4)
        self.assertEqual(summary.scenarios_per_observation, 3)
        self.assertEqual(summary.expected_trajectories, 60)
        self.assertIn("60", self.page.trajectory_summary.text())
        self.assertIn("8 days", self.page.duration_summary.text())
        self.assertIn("2 datasets", self.page.forcing_summary.text())

    def test_activity_payload_updates_human_readable_progress(self) -> None:
        self.page.set_state(ReviewRunState.RUNNING)

        self.page.update_activity({
            "event": "progress", "processed": 25, "total_jobs": 100,
            "completed": 23, "failed": 2, "batch": 1,
            "elapsed_seconds": 12.5,
        })

        self.assertEqual(self.page.run_progress.value(), 25)
        self.assertIn("25 of 100", self.page.activity_trajectories.text())
        self.assertIn("2 failed", self.page.activity_failures.text())
        self.assertIn("12s", self.page.activity_elapsed.text())

    def test_visual_review_contract_covers_required_states_and_sizes(self) -> None:
        self.assertEqual(
            {case.name for case in REVIEW_RUN_REVIEW_CASES},
            {
                "unvalidated", "blocked", "ready", "running",
                "completed", "completed_with_warnings",
            },
        )
        self.assertEqual(
            REVIEW_RUN_REVIEW_SIZES,
            {"wide": (1440, 900), "compact": (1080, 760)},
        )

    def test_review_configurator_preserves_state_specific_hierarchy(self) -> None:
        window = MarineDriftMainWindow()
        actions = {
            "validate": window.review_run_page.validate_button,
            "run": window.review_run_page.run_simulations_button,
            "cancel": window.review_run_page.cancel_run_button,
            "open": window.review_run_page.open_results_button,
        }
        expected_actions = {
            "unvalidated": "validate",
            "blocked": "validate",
            "ready": "run",
            "running": "cancel",
            "completed": "open",
            "completed_with_warnings": "open",
        }
        try:
            for case in REVIEW_RUN_REVIEW_CASES:
                with self.subTest(state=case.name):
                    configure_review_run_state(window, case.name)
                    visible = [
                        name for name, button in actions.items()
                        if not button.isHidden()
                    ]
                    self.assertEqual(visible, [expected_actions[case.name]])
                    self.assertEqual(
                        window.review_run_page.activity_card.isHidden(),
                        case.name in {"unvalidated", "blocked", "ready"},
                    )
        finally:
            window.project_dirty = False
            window.close()

    def test_primary_action_and_active_progress_precede_detail_cards(self) -> None:
        self.page.set_state(ReviewRunState.READY)
        self.assertLess(
            self.page.content_layout.indexOf(self.page.primary_action_card),
            self.page.content_layout.indexOf(self.page.summary_row),
        )

        self.page.set_state(ReviewRunState.RUNNING)
        self.assertLess(
            self.page.content_layout.indexOf(self.page.activity_card),
            self.page.content_layout.indexOf(self.page.summary_row),
        )

    def test_compact_mode_stacks_summary_cards_without_horizontal_clipping(self) -> None:
        self.page.set_compact_layout(True)

        positions = [
            self.page.summary_layout.getItemPosition(index)
            for index in range(self.page.summary_layout.count())
        ]
        self.assertEqual([position[0] for position in positions], [0, 1, 2])
        self.assertTrue(all(position[1] == 0 for position in positions))

    def test_primary_action_card_carries_semantic_state_without_detail_rows(self) -> None:
        expected = {
            ReviewRunState.BLOCKED: "error",
            ReviewRunState.READY: "ready",
            ReviewRunState.RUNNING: "running",
            ReviewRunState.COMPLETED_WITH_ERRORS: "warning",
        }
        for state, semantic in expected.items():
            with self.subTest(state=state):
                self.page.set_state(state)
                self.assertEqual(
                    self.page.primary_action_card.property("state"), semantic
                )


class OutputDestinationValidationTests(unittest.TestCase):
    def test_preflight_exposes_output_as_a_routable_readiness_check(self) -> None:
        result = run_preflight(SimulationRequest())

        output_check = next(
            check for check in result.checks if check.key == "output_destination"
        )
        self.assertTrue(output_check.blocks_run)
        self.assertEqual(output_check.target_step, "review_run")

    def test_existing_file_is_a_blocking_output_destination(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "review_run"
        root.mkdir(parents=True, exist_ok=True)
        file_path = root / "not-a-directory.txt"
        file_path.write_text("occupied", encoding="utf-8")

        message = validate_output_destination(file_path)

        self.assertEqual(message.level, "error")
        self.assertIn("file", message.text.lower())

    def test_creatable_output_destination_reports_ready(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "review_run"
        destination = root / "new-output" / "nested"

        message = validate_output_destination(destination)

        self.assertEqual(message.level, "info")
        self.assertIn("created", message.text.lower())


if __name__ == "__main__":
    unittest.main()
