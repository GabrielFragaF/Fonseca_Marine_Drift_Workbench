from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import QApplication

from .ui.main_window import MarineDriftMainWindow
from .ui.theme import APP_FONT_CANDIDATES, build_stylesheet
from .version import VERSION


def _select_ui_font(app: QApplication) -> str:
    if not app.property("workbench_fonts_loaded"):
        font_directory = Path(__file__).parent / "ui" / "assets" / "fonts"
        for font_path in sorted(font_directory.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(font_path))
        app.setProperty("workbench_fonts_loaded", True)
    available = set(QFontDatabase.families())
    for family in APP_FONT_CANDIDATES:
        if family in available:
            return family
    return app.font().family()


def create_application() -> tuple[QApplication, MarineDriftMainWindow]:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Marine Drift Desktop")
    app.setApplicationVersion(VERSION)
    app.setStyle("Fusion")
    logo = Path(__file__).parent / "ui" / "assets" / "icons" / "marine-drift-workbench-logo.svg"
    app.setWindowIcon(QIcon(str(logo)))

    font_family = _select_ui_font(app)
    font = QFont(font_family)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet(font_family))

    window = MarineDriftMainWindow()
    window.show_home()
    return app, window
