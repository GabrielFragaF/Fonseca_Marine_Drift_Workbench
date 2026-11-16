"""Offline GUI-only packaging check; never starts a modelling worker."""
import json
from pathlib import Path
import sys
import traceback


def run_gui_check(output_directory: str) -> int:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    report = {"frozen": bool(getattr(sys, "frozen", False)), "checks": []}
    window = None
    try:
        from .app import create_application

        app, window = create_application()
        window.show()
        app.processEvents()
        assert window.workspace_stack.currentWidget() is window.welcome_page
        assert len(window.welcome_page.partner_buttons) == 3
        assert all(not button.icon().isNull() for button in window.welcome_page.partner_buttons)
        assert window.grab().save(str(output / "welcome.png"))
        report["checks"].append("Welcome screen and three bundled partner logos")
        window.welcome_page.modelling_button.click()
        assert window.workspace_stack.currentIndex() == 1
        window.start_tutorial()
        app.processEvents()
        assert window.guided_tour.isVisible()
        window.guided_tour.finish()
        assert window._simulation_process is None
        assert window._preflight_worker is None
        report["checks"].append("Modelling navigation and tutorial, without running simulations")
        window.stage_navigation.setCurrentRow(3)
        window._start_preflight()
        app.processEvents()
        progress = window.review_run_page.inline_validation
        button = window.review_run_page.validate_button
        report["validation_diagnostic"] = {
            "state": window.review_run_page.state.value,
            "stage_index": window.stage_navigation.currentRow(),
            "stage_stack_index": window.stage_stack.currentIndex(),
            "page_visible": window.review_run_page.isVisible(),
            "card_visible": window.review_run_page.primary_action_card.isVisible(),
            "progress_visible": progress.isVisible(),
            "progress_hidden": progress.isHidden(),
            "button_visible": button.isVisible(),
        }
        assert window._preflight_worker is not None
        assert progress.isVisible()
        assert not progress.geometry().isEmpty()
        assert progress.geometry().right() < button.geometry().left()
        assert window.grab().save(str(output / "validation-progress.png"))
        report["validation_progress"] = {
            "visible": progress.isVisible(),
            "geometry": [
                progress.x(), progress.y(), progress.width(), progress.height()
            ],
            "button_geometry": [button.x(), button.y(), button.width(), button.height()],
        }
        report["checks"].append("Real preflight displays inline validation progress beside the validation button")
        window._preflight_worker.requestInterruption()
        window._preflight_worker.wait(5000)
        app.processEvents()
        from .core.preflight import PreflightCheck, PreflightResult
        from .ui.components import ActionButton
        from .version import VERSION, BUILD_ID
        from PySide6.QtTest import QTest
        report.update(version=VERSION, build_id=BUILD_ID)
        issues = (
            PreflightCheck("wind_column", "error", "Windage column missing", "Choose the observation column containing windage values.",
                           "simulation_setup", True, 3, ("wind_column",)),
            PreflightCheck("temperature", "error", "Temperature column missing", "Choose the temperature column used to estimate drift duration.",
                           "simulation_setup", True, 2, ("sst_column",)),
        )
        window._preflight_minimum_until = 0
        window._preflight_completed(window._preflight_generation, PreflightResult(checks=issues))
        window.resize(1440, 900)
        window.preview_health.click()
        QTest.qWait(250)
        assert window.stage_navigation.currentRow() == 3
        assert "Not evaluated" in window.review_run_page.observation_summary.text()
        assert window.grab().save(str(output / "validation-errors.png"))
        row = window.review_run_page.readiness_rows.itemAt(0).widget()
        row.findChild(ActionButton).click()
        QTest.qWait(300)
        assert window.stage_navigation.currentRow() == 2
        assert window.simulation_setup_page.current_step_index == 3
        assert window.wind_column.property("validationState") == "error"
        assert window.grab().save(str(output / "windage-correction.png"))
        report["checks"].append("Review errors opens individual errors; correction opens Windage and highlights the exact field")
        for width, height in ((1440, 900), (1080, 760)):
            window.resize(width, height)
            for index in range(6):
                window.simulation_setup_page.set_current_step(index)
                QTest.qWait(100)
                scroll = window.simulation_setup_page.configuration_stack.currentWidget()
                assert scroll.horizontalScrollBar().maximum() == 0
            assert window.grab().save(str(output / f"setup-{width}.png"))
        report["checks"].append("All six setup subsections fit horizontally at 1440 and 1080 pixels")
        report["success"] = True
    except Exception:
        report.update(success=False, error=traceback.format_exc())
    finally:
        if window is not None:
            window.project_dirty = False
            window.close()
    (output / "gui-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["success"] else 1
