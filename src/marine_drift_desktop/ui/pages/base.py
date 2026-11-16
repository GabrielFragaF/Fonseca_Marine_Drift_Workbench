from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
)

from ..icons import line_icon


class WorkflowStagePage(QScrollArea):
    """Shared scrollable shell and hero for one global workflow stage."""

    def __init__(
        self,
        title: str,
        description: str,
        *,
        step_number: str,
        category: str,
        icon_name: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        page = QFrame()
        page.setObjectName("StagePage")
        self.content_layout = QVBoxLayout(page)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self.content_layout.setSpacing(12)
        self.content_layout.addWidget(
            self._build_hero(
                title,
                description,
                step_number=step_number,
                category=category,
                icon_name=icon_name,
            )
        )
        self.setWidget(page)

    def _build_hero(
        self,
        title: str,
        description: str,
        *,
        step_number: str,
        category: str,
        icon_name: str,
    ) -> QFrame:
        hero = QFrame()
        hero.setObjectName("StageHero")
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(13)

        icon = QLabel()
        icon.setObjectName("StageHeroIcon")
        icon.setPixmap(line_icon(icon_name, "#0b2e43", 30).pixmap(30, 30))
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(48, 48)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        kicker = QLabel(f"STEP {step_number}  /  {category}")
        kicker.setProperty("role", "hero-kicker")
        title_label = QLabel(title)
        title_label.setObjectName("StageTitle")
        copy = QLabel(description)
        copy.setObjectName("StageCopy")
        copy.setWordWrap(True)
        kicker.setParent(hero)
        kicker.hide()
        text_layout.addWidget(title_label)
        text_layout.addWidget(copy)

        layout.addWidget(icon)
        layout.addLayout(text_layout, 1)
        return hero
