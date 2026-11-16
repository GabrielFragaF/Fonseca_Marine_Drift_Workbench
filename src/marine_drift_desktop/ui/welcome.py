from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from typing import NamedTuple

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QLayout, QProgressBar, QScrollArea, QToolButton, QVBoxLayout, QWidget

from .components import ActionButton
from .icons import line_icon


@lru_cache(maxsize=4)
def _partner_icon(asset: str) -> QIcon:
    reader = QImageReader(str(Path(__file__).parent / "assets" / "partners" / f"{asset}.png"))
    reader.setScaledSize(reader.size().scaled(QSize(280, 152), Qt.KeepAspectRatio))
    return QIcon(QPixmap.fromImage(reader.read()))


class BrandLockup(QWidget):
    """Scale the complete horizontal mark together, preserving its proportions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setMaximumHeight(285)
        self.setAccessibleName("Marine Drift Workbench")
        self.logo = line_icon("marine-drift-workbench-logo", size=560).pixmap(560, 560)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scale = min(self.width() / 700, self.height() / 280, 1.0)
        painter.translate(0, (self.height() - 280 * scale) / 2)
        painter.scale(scale, scale)
        painter.drawPixmap(QRectF(0, 0, 270, 280), self.logo, QRectF(self.logo.rect()))

        def word(text, top, color, spacing, weight):
            font = QFont(self.font().family())
            font.setPixelSize(70)
            font.setWeight(weight)
            font.setLetterSpacing(QFont.AbsoluteSpacing, spacing)
            path = QPainterPath()
            path.addText(0, 0, font, text)
            bounds = path.boundingRect()
            painter.save()
            painter.translate(302, top)
            factor = 388 / bounds.width()
            painter.scale(factor, factor)
            painter.translate(-bounds.left(), -bounds.top())
            painter.fillPath(path, QColor(color))
            painter.restore()

        word("MARINE", 34, "#102d46", 8, QFont.Bold)
        word("DRIFT", 119, "#346b8c", 13, QFont.DemiBold)
        painter.setPen(QPen(QColor("#69b4a4"), 2.5))
        painter.drawLine(302, 218, 690, 218)
        word("WORKBENCH", 237, "#102d46", 33, QFont.Medium)


class WelcomePage(QScrollArea):
    new_project_requested = Signal()
    open_project_requested = Signal()
    tutorial_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("WelcomePage")
        layout = QVBoxLayout(page)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.addStretch()
        content = QWidget()
        content.setMaximumWidth(1440)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(22)
        hero = QBoxLayout(QBoxLayout.LeftToRight)
        self.hero_layout = hero
        hero.setSpacing(36)
        introduction = QVBoxLayout()
        introduction.setSpacing(12)
        introduction.addStretch()
        introduction.addWidget(BrandLockup())
        description = QLabel(
            "Build reproducible reverse-drift workflows to estimate probable "
            "at-sea mortality origins from marine megafauna stranding records."
        )
        description.setObjectName("WelcomeDescription")
        description.setWordWrap(True)
        description.setMaximumWidth(740)
        introduction.addWidget(description)
        introduction.addStretch()
        hero.addLayout(introduction, 2)
        action_panel = QFrame()
        action_panel.setObjectName("WelcomeActions")
        action_panel.setMinimumWidth(320)
        self.action_panel = action_panel
        actions = QVBoxLayout(action_panel)
        actions.setSizeConstraint(QLayout.SetMinimumSize)
        actions.setContentsMargins(30, 30, 30, 30)
        actions.setSpacing(13)
        eyebrow = QLabel("GET STARTED")
        eyebrow.setObjectName("WelcomeActionEyebrow")
        actions.addWidget(eyebrow)
        heading = QLabel("Start a new project")
        heading.setObjectName("WelcomeActionTitle")
        heading.setWordWrap(True)
        actions.addWidget(heading)
        action_copy = QLabel(
            "Import stranding records, connect environmental datasets, and "
            "configure a reproducible reverse-drift workflow."
        )
        action_copy.setWordWrap(True)
        actions.addWidget(action_copy)
        actions.addSpacing(8)
        self.new_project_button = ActionButton("Create new project", variant="primary")
        self.open_project_button = ActionButton("Open existing project", variant="ghost")
        self.tutorial_button = ActionButton("Explore the tutorial", variant="ghost")
        self.modelling_button = self.new_project_button
        for button in (
            self.new_project_button,
            self.open_project_button,
            self.tutorial_button,
        ):
            button.setMinimumHeight(54)
            actions.addWidget(button)
        hero.addWidget(action_panel, 1)
        content_layout.addLayout(hero)
        self.new_project_button.clicked.connect(self.new_project_requested.emit)
        self.open_project_button.clicked.connect(self.open_project_requested.emit)
        self.tutorial_button.clicked.connect(self.tutorial_requested.emit)
        divider = QFrame()
        divider.setObjectName("WelcomeDivider")
        divider.setFixedHeight(1)
        content_layout.addWidget(divider)
        references = QBoxLayout(QBoxLayout.LeftToRight)
        self.references_layout = references
        references.setSpacing(16)
        citations = QBoxLayout(QBoxLayout.LeftToRight)
        self.citations_layout = citations
        citations.setSpacing(16)
        for title, text in (
            ("Powered by OpenDrift", 'Dagestad et al. (2018). OpenDrift v1.0: a generic framework '
             'for trajectory modelling. <i>Geoscientific Model Development</i>, 11, 1405-1420. '
             '<a href="https://doi.org/10.5194/gmd-11-1405-2018">Read the paper</a>.'),
            ("Methodology", "Fonseca et al. (forthcoming manuscript). "
             "<i>Scalable reverse-drift framework transforms sea turtle strandings "
             "into indicators of at-sea mortality in the southwestern Atlantic.</i>"),
        ):
            card = QFrame()
            card.setObjectName("WelcomeReferenceCard")
            column = QVBoxLayout(card)
            column.setSizeConstraint(QLayout.SetMinimumSize)
            column.setContentsMargins(20, 18, 20, 18)
            column.setSpacing(10)
            header = QHBoxLayout()
            header.setSpacing(12)
            if title == "Powered by OpenDrift":
                self.framework_logo = QLabel()
                self.framework_logo.setPixmap(_partner_icon("opendrift").pixmap(68, 56))
                self.framework_logo.setFixedSize(68, 56)
                self.framework_logo.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                header.addWidget(self.framework_logo)
            else:
                method_icon = QLabel()
                method_icon.setPixmap(line_icon("netcdf", color="#146b86", size=32).pixmap(32, 32))
                method_icon.setFixedSize(40, 56)
                method_icon.setAlignment(Qt.AlignCenter)
                header.addWidget(method_icon)
            title_label = QLabel(title)
            title_label.setObjectName("WelcomeReferenceTitle")
            label = QLabel(text)
            label.setProperty("role", "muted")
            label.setWordWrap(True)
            label.setMinimumHeight(90)
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            label.setOpenExternalLinks(True)
            label.setText(text.replace('<a href=', '<a style="color:#146b86" href='))
            header.addWidget(title_label, 1)
            column.addLayout(header)
            column.addWidget(label)
            column.addStretch()
            citations.addWidget(card, 1)
        references.addLayout(citations, 2)
        partners = QFrame()
        partners.setObjectName("WelcomePartners")
        partner_layout = QHBoxLayout(partners)
        partner_layout.setContentsMargins(12, 18, 12, 18)
        partner_layout.setSpacing(4)
        self.partner_buttons = []
        for name, asset, url in (
            ("LEC - UFPR", "lec", "https://www.lecufpr.net/"),
            ("Labirinto", "labirinto", "https://thelabirinto.com/"),
            ("Pelagis", "pelagis", "https://www.observatoire-pelagis.cnrs.fr/?lang=en"),
        ):
            button = QToolButton()
            button.setObjectName("PartnerLogo")
            button.setProperty("brand", asset)
            button.setText(name)
            button.setAccessibleName(f"Visit {name} website")
            button.setToolTip(url)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(_partner_icon(asset))
            button.setIconSize(QSize(108, 64))
            button.setMinimumSize(108, 112)
            button.clicked.connect(lambda checked=False, url=url: QDesktopServices.openUrl(QUrl(url)))
            partner_layout.addWidget(button, 1)
            self.partner_buttons.append(button)
        references.addWidget(partners, 1)
        content_layout.addLayout(references)
        content_row = QHBoxLayout()
        content_row.addStretch()
        content_row.addWidget(content, 1)
        content_row.addStretch()
        layout.addLayout(content_row)
        layout.addStretch()
        self.setWidget(page)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "hero_layout"):
            return
        width = self.viewport().width()
        self.hero_layout.setDirection(
            QBoxLayout.TopToBottom if width < 900 else QBoxLayout.LeftToRight
        )
        self.references_layout.setDirection(
            QBoxLayout.TopToBottom if width < 1300 else QBoxLayout.LeftToRight
        )
        self.citations_layout.setDirection(
            QBoxLayout.TopToBottom if width < 700 else QBoxLayout.LeftToRight
        )


class TutorialStep(NamedTuple):
    key: str
    stage: int
    internal_step: int | None
    target_path: str
    title: str
    detail: str
    placement: str = "auto"


class GuidedTour(QWidget):
    """Read-only tutorial of actual controls, with a spotlight and keyboard navigation."""

    def __init__(self, window):
        super().__init__(window.centralWidget())
        self.window = window
        self.setFocusPolicy(Qt.StrongFocus)
        self.steps = [
            TutorialStep("observation-source", 0, None, "observation_page.data_source_card", "Choose the observation table",
                         "Select a CSV, Excel, or Parquet table. Only its header is read here, so large datasets remain responsive."),
            TutorialStep("observation-records", 0, None, "observation_page.record_information_card", "Identify each observation",
                         "Map the observation identifier, taxon label, and decomposition code. Searchable selectors list columns detected in your table."),
            TutorialStep("observation-time", 0, None, "observation_page.observation_time_card", "Describe observation time",
                         "Choose separate date and time columns or one timestamp column. Explicit offsets are converted to UTC; timestamps without an offset use the selected input time zone."),
            TutorialStep("observation-position", 0, None, "observation_page.spatial_position_card", "Map recorded positions",
                         "Select latitude and longitude, then declare their coordinate notation so positions are interpreted consistently."),
            TutorialStep("forcing-catalog", 1, None, "environment_page.catalog_group", "Add environmental datasets",
                         "Add NetCDF files or a folder. Each file is inspected locally and listed with its detected coverage and status."),
            TutorialStep("forcing-inspector", 1, None, "environment_page.inspector_panel", "Assign forcing roles",
                         "Select a dataset and review its variables. Assign Ocean circulation, Wind, Waves, or other roles that match the data it contains."),
            TutorialStep("forcing-readiness", 1, None, "environment_page.readiness_group", "Check forcing coverage",
                         "Readiness checks compare required currents, time coverage, spatial coverage, and optional forcing before a run."),
            TutorialStep("setup-area", 2, 0, "simulation_setup_page.study_area_group", "Set the study area",
                         "Use overlapping environmental coverage with a buffer, or switch to manual bounds. The map updates to show the selected extent."),
            TutorialStep("setup-selection", 2, 1, "simulation_setup_page.selection_group", "Choose observations to simulate",
                         "Run all valid rows, take a reproducible random sample, or filter by table values. The nearby-water options control records located on land."),
            TutorialStep("setup-duration", 2, 2, "simulation_setup_page.duration_group", "Define reverse-drift duration",
                         "Use one duration, read it from a column, or estimate scenarios from temperature and decomposition state."),
            TutorialStep("setup-windage", 2, 3, "simulation_setup_page.windage_group", "Configure windage",
                         "Disable windage, use a fixed percentage, read values from the table, or estimate them from body measurements. The app converts percentages to model fractions."),
            TutorialStep("setup-release", 2, 4, "simulation_setup_page.release_group", "Design particle releases",
                         "Set start-time scenarios, spacing between starts, particles per release, release radius, and any fixed observation-day clock time."),
            TutorialStep("setup-physics", 2, 5, "simulation_setup_page.advanced_group", "Set timestep and model physics",
                         "Choose the calculation timestep, coastline behavior, uncertainty, and optional constants for missing forcing values. Finish setup then opens Review & run."),
            TutorialStep("review-destination", 3, None, "review_run_page.destination_card", "Choose the run destination",
                         "Select a writable folder for trajectories, checkpoints, logs, and the reproducibility manifest."),
            TutorialStep("review-action", 3, None, "review_run_page.primary_action_card", "Validate and run",
                         "Validate first, resolve blocking checks, and review the workload. Run simulations starts continuous local batches; this tutorial never starts a run."),
            TutorialStep("results-export", 4, None, "results_export_page.formats_card", "Create analysis-ready tables",
                         "Inspect completed trajectories, choose positions per drift day, and export canonical weighted Parquet with optional CSV or Excel copies."),
            TutorialStep("results-map", 4, None, "results_export_page.trajectory_map", "Preview sampled trajectories",
                         "Generate a map for randomly selected distinct individuals, using one available simulation run per individual. No simulation is rerun."),
        ]
        self.target = None
        self.card = QFrame(self)
        self.card.setObjectName("TourCard")
        box = QVBoxLayout(self.card)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(12)
        self.counter = QLabel()
        self.counter.setProperty("role", "muted")
        self.progress = QProgressBar()
        self.progress.setObjectName("TourProgress")
        self.progress.setRange(0, len(self.steps))
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.title = QLabel()
        self.title.setObjectName("TourTitle")
        self.title.setWordWrap(True)
        self.description = QLabel()
        self.description.setWordWrap(True)
        box.addWidget(self.counter)
        box.addWidget(self.progress)
        box.addWidget(self.title)
        box.addWidget(self.description)
        buttons = QHBoxLayout()
        self.exit_button = ActionButton("Exit tutorial")
        self.back_button = ActionButton("Back")
        self.next_button = ActionButton("Next", variant="primary")
        for button in (self.exit_button, self.back_button, self.next_button):
            buttons.addWidget(button)
        box.addLayout(buttons)
        self.exit_button.clicked.connect(self.finish)
        self.back_button.clicked.connect(lambda: self.show_step(self.index - 1))
        self.next_button.clicked.connect(self.advance)
        self.parent().installEventFilter(self)
        self.hide()

    def start(self):
        if self.isVisible():
            return
        self.original_stage = self.window.stage_navigation.currentRow()
        self.original_step = self.window.simulation_setup_page.current_step_index
        self.original_states = self.window.simulation_setup_page.step_states.copy()
        self.original_scroll_positions = {
            scroll: (scroll.horizontalScrollBar().value(), scroll.verticalScrollBar().value())
            for scroll in self.window.findChildren(QScrollArea)
        }
        for scroll in self.original_scroll_positions:
            scroll.horizontalScrollBar().valueChanged.connect(self._refresh_visible_spotlight)
            scroll.verticalScrollBar().valueChanged.connect(self._refresh_visible_spotlight)
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self.show_step(0)

    def show_step(self, index):
        self.index = max(0, min(index, len(self.steps) - 1))
        step = self.steps[self.index]
        self.window.stage_navigation.setCurrentRow(step.stage)
        if step.internal_step is not None:
            setup = self.window.simulation_setup_page
            states = setup.step_states.copy()
            setup.set_current_step(step.internal_step)
            setup.step_states = states
            setup._refresh_step_ui()
        self.target = self.resolve_target(step.target_path)
        self.counter.setText(f"TUTORIAL  /  {self.index + 1} OF {len(self.steps)}")
        self.progress.setValue(self.index + 1)
        self.title.setText(step.title)
        self.description.setText(step.detail if self.target is not None else
                                 "This tutorial section is temporarily unavailable in the current layout. Continue to the next step.")
        self.back_button.setEnabled(self.index > 0)
        self.next_button.setText("Finish tutorial" if self.index == len(self.steps) - 1 else "Next")
        QTimer.singleShot(0, self._position)

    def resolve_target(self, path):
        target = self.window
        try:
            for name in path.split("."):
                target = getattr(target, name)
        except AttributeError:
            return None
        return target if isinstance(target, QWidget) else None

    def _position(self):
        if not self.isVisible():
            return
        if self.target is None:
            self._place_card(QRectF())
            self.update()
            return
        ancestor = self.target.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                ancestor.ensureWidgetVisible(self.target, 16, 16)
            ancestor = ancestor.parentWidget()
        self.card.setFixedWidth(min(420, self.width() - 32))
        self.card.adjustSize()
        self._place_card(self.spotlight_rect())
        self.update()

    def spotlight_rect(self):
        if self.target is None or not self.target.isVisibleTo(self.window):
            return QRectF()
        bounds = QRectF(self.target.rect())
        target_origin = self.mapFromGlobal(self.target.mapToGlobal(QPoint(0, 0)))
        bounds.moveTopLeft(target_origin)
        bounds = bounds.adjusted(-5, -5, 5, 5).intersected(QRectF(self.rect()))
        ancestor = self.target.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, QScrollArea):
                viewport = ancestor.viewport()
                clip = QRectF(viewport.rect())
                clip.moveTopLeft(self.mapFromGlobal(viewport.mapToGlobal(QPoint(0, 0))))
                bounds = bounds.intersected(clip)
            ancestor = ancestor.parentWidget()
        return bounds

    def _refresh_visible_spotlight(self, *_):
        if self.isVisible():
            self._place_card(self.spotlight_rect())
            self.update()

    def _place_card(self, spotlight):
        margin, gap = 18, 14
        width, height = self.card.width(), self.card.height()
        available = QRect(margin, margin, max(0, self.width() - margin * 2),
                          max(0, self.height() - margin * 2))
        candidates = []
        if not spotlight.isEmpty():
            target = spotlight.toRect()
            candidates = [
                QRect(target.right() + gap, target.center().y() - height // 2, width, height),
                QRect(target.left() - width - gap, target.center().y() - height // 2, width, height),
                QRect(target.center().x() - width // 2, target.bottom() + gap, width, height),
                QRect(target.center().x() - width // 2, target.top() - height - gap, width, height),
            ]
        for candidate in candidates:
            if available.contains(candidate) and not candidate.intersects(spotlight.toRect()):
                self.card.move(candidate.topLeft())
                return
        corners = [available.topLeft(),
                   QPoint(available.right() - width, available.top()),
                   QPoint(available.left(), available.bottom() - height),
                   QPoint(available.right() - width, available.bottom() - height)]
        valid = [QRect(point, QSize(width, height)) for point in corners]
        chosen = min(valid, key=lambda rect: rect.intersected(spotlight.toRect()).width() *
                     rect.intersected(spotlight.toRect()).height())
        self.card.move(chosen.topLeft())

    def advance(self):
        if self.index == len(self.steps) - 1:
            self.finish()
        else:
            self.show_step(self.index + 1)

    def finish(self):
        self.hide()
        setup = self.window.simulation_setup_page
        setup.set_current_step(self.original_step)
        setup.step_states = self.original_states
        setup._refresh_step_ui()
        self.window.stage_navigation.setCurrentRow(self.original_stage)
        for scroll, (horizontal, vertical) in self.original_scroll_positions.items():
            scroll.horizontalScrollBar().valueChanged.disconnect(self._refresh_visible_spotlight)
            scroll.verticalScrollBar().valueChanged.disconnect(self._refresh_visible_spotlight)
            scroll.horizontalScrollBar().setValue(horizontal)
            scroll.verticalScrollBar().setValue(vertical)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(self.parent().rect())
            self._position()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.finish()
        elif event.key() == Qt.Key_Right:
            self.advance()
        elif event.key() == Qt.Key_Left:
            self.show_step(self.index - 1)
        else:
            super().keyPressEvent(event)

    def focusNextPrevChild(self, forward):
        buttons = [button for button in (self.exit_button, self.back_button, self.next_button)
                   if button.isEnabled()]
        current = next((i for i, button in enumerate(buttons) if button.hasFocus()), -1)
        buttons[(current + (1 if forward else -1)) % len(buttons)].setFocus()
        return True

    def paintEvent(self, event):
        bounds = self.spotlight_rect()
        if bounds.isEmpty():
            return
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        spotlight = QPainterPath()
        spotlight.addRoundedRect(bounds, 10, 10)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillPath(shade.subtracted(spotlight), QColor(7, 28, 43, 175))
        painter.setPen(QPen(QColor("#53d1bc"), 3))
        painter.drawPath(spotlight)
