"""Render real Qt controls and workflow screens for visual review."""
from pathlib import Path
from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from marine_drift_desktop.ui.components import ActionButton, AnimatedStackedWidget
from marine_drift_desktop.ui.main_window import MarineDriftMainWindow
from marine_drift_desktop.ui.theme import build_stylesheet
from marine_drift_desktop.app import _select_ui_font
from render_gui_review import configure_environment_review_state, configure_observation_review_state

app = QApplication([])
app.setStyle("Fusion")
family = _select_ui_font(app)
assert family == "Source Sans 3", family
app.setFont(QFont(family, 10))
app.setStyleSheet(build_stylesheet(family))
output = Path(".tmp_tests/visual_controls")
output.mkdir(parents=True, exist_ok=True)
stack = AnimatedStackedWidget()
stack.addWidget(QWidget())
page = QWidget()
page.setStyleSheet("background: #f4f8fa;")
layout = QHBoxLayout(page)
buttons = []
for variant in ("primary", "secondary", "ghost", "danger"):
    button = ActionButton(variant.title() + " action", variant=variant)
    layout.addWidget(button)
    buttons.append(button)
stack.addWidget(page)
stack.resize(850, 100)
stack.show()
stack.setCurrentIndex(1)
QTest.qWait(220)
assert page.graphicsEffect() is None
stack.grab().save(str(output / "buttons-rest.png"))
for index, button in enumerate(buttons):
    for repeat in range(6):
        QTest.mouseMove(button, button.rect().center())
        QTest.qWait(30)
        assert button.isVisible() and button.graphicsEffect() is None
        stack.grab().save(str(output / f"hover-{index}.png"))
        QTest.mouseMove(stack, QPoint(2, 2))
        QTest.qWait(20)
stack.close()
window = MarineDriftMainWindow()
window.show()
for width, height in ((1440, 960), (1080, 760)):
    window.resize(width, height)
    for index in range(window.stage_navigation.count()):
        window.stage_navigation.setCurrentRow(index)
        QTest.qWait(250)
        window.grab().save(str(output / f"stage-{index + 1}-{width}.png"))
    for name, configure, state in (
        ("observations-loaded", configure_observation_review_state, "loaded_mapped"),
        ("environment-selected", configure_environment_review_state, "selected"),
    ):
        configure(window, state)
        QTest.qWait(250)
        window.grab().save(str(output / f"{name}-{width}.png"))
window.close()
print(f"Hover checks and fourteen workflow renders completed with {family}: {output.resolve()}")
