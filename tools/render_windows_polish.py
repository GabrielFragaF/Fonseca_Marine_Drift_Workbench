"""Render welcome, tour, selectors and setup feedback using real Qt widgets."""
from pathlib import Path

from PySide6.QtTest import QTest

from marine_drift_desktop.app import create_application
from marine_drift_desktop.ui.pages.review_run_page import ReviewRunState


def main():
    app, window = create_application()
    folder = Path(".tmp_tests/windows-polish")
    folder.mkdir(parents=True, exist_ok=True)
    window.show()

    def capture(name):
        QTest.qWait(220)
        window.grab().save(str(folder / f"{name}.png"))

    for width, height in ((1440, 900), (1024, 700)):
        window.resize(width, height)
        window.show_home()
        capture(f"welcome-{width}")
        window.show_workbench()
        window.stage_navigation.setCurrentRow(2)
        setup = window.simulation_setup_page
        setup.set_current_step(0)
        setup.study_area_preset.setCurrentIndex(0)
        capture(f"area-derived-{width}")
        setup.study_area_preset.setCurrentIndex(1)
        capture(f"area-manual-{width}")
        window.stage_navigation.setCurrentRow(3)
        window.review_run_page.set_state(ReviewRunState.VALIDATING)
        capture(f"validating-{width}")
        window.review_run_page.set_state(ReviewRunState.UNVALIDATED)
        window.start_tutorial()
        for index in range(len(window.guided_tour.steps)):
            window.guided_tour.show_step(index)
            capture(f"tour-{index:02d}-{width}")
        window.guided_tour.finish()
    window.resize(1440, 900)
    window.stage_navigation.setCurrentRow(0)
    selector = window.identifier_column
    selector.addItems(["individual_id", "observation_id", "stranding_identifier"])
    selector.setEditText("id")
    selector.completer().setCompletionPrefix("id")
    selector.completer().complete()
    QTest.qWait(200)
    selector.completer().popup().grab().save(str(folder / "completion-popup.png"))
    selector.completer().popup().hide()
    window.project_dirty = False
    window.close()
    print(folder.resolve())


if __name__ == "__main__":
    main()
