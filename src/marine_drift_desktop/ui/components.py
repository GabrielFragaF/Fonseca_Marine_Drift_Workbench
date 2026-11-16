from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QCompleter, QDoubleSpinBox, QFrame,
    QGraphicsOpacityEffect, QLabel, QPushButton, QSizePolicy, QStackedWidget,
    QStyle, QStyleOption, QToolButton,
)

from .icons import line_icon


class CompactDoubleSpinBox(QDoubleSpinBox):
    """Keep numerical precision while suppressing insignificant trailing zeros."""

    def textFromValue(self, value: float) -> str:
        text = super().textFromValue(value)
        separator = self.locale().decimalPoint()
        if separator in text:
            text = text.rstrip(self.locale().zeroDigit()).rstrip(separator)
        return text


def style_selector_popup(view) -> None:
    # QCompleter creates its own top-level popup, outside the combo's stylesheet scope.
    view.setObjectName("SelectorPopup")
    view.setAutoFillBackground(True)
    view.viewport().setAutoFillBackground(True)
    view.setStyleSheet("""
        QAbstractItemView { background: #ffffff; color: #102733;
            border: 1px solid #7babb8; padding: 4px;
            selection-background-color: #d6efef; selection-color: #063e51; }
        QAbstractItemView::item { min-height: 30px; padding: 4px 10px;
            background: #ffffff; color: #102733; }
        QAbstractItemView::item:selected, QAbstractItemView::item:hover {
            background: #d6efef; color: #063e51; }
        QAbstractItemView QWidget { background: #ffffff; }
    """)


class AnimatedToggle(QAbstractButton):
    """Accessible switch with a softly animated sea-glass thumb."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("role", "animated-toggle")
        self.setAccessibleName(text)
        self.setMinimumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._thumb_position = 0.0
        self._animation = QPropertyAnimation(self, b"thumbPosition", self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate_thumb)

    def sizeHint(self) -> QSize:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        return QSize(58 + 12 + text_width, 38)

    def getThumbPosition(self) -> float:
        return self._thumb_position

    def setThumbPosition(self, value: float) -> None:
        self._thumb_position = value
        self.update()

    thumbPosition = Property(float, getThumbPosition, setThumbPosition)

    def _animate_thumb(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._thumb_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1.0, (self.height() - 26.0) / 2.0, 48.0, 26.0)
        track_color = QColor("#67c6b0") if self.isChecked() else QColor("#a8b8be")
        if not self.isEnabled():
            track_color.setAlpha(105)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, 13.0, 13.0)
        thumb_x = 4.0 + self._thumb_position * 22.0
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(thumb_x, track.top() + 3.0, 20.0, 20.0))
        painter.setPen(QColor("#102733") if self.isEnabled() else QColor("#84949a"))
        painter.drawText(
            QRectF(60.0, 0.0, max(0.0, self.width() - 60.0), float(self.height())),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text(),
        )
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#159ab5"), 1.5))
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)


class ActionButton(QPushButton):
    """Stable native-painted command button with loading state."""

    def __init__(self, text: str = "", parent=None, *, variant: str = "secondary") -> None:
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)
        self._resting_text = text
        self._loading = False
        self._enabled_before_loading = True
        self.setIconSize(QSize(18, 18))

    def setLoading(self, loading: bool, text: str = "Working...") -> None:
        if self._loading == loading:
            return
        self._loading = loading
        if loading:
            self._enabled_before_loading = self.isEnabled()
            self._resting_text = self.text()
            self.setText(text)
            self.setEnabled(False)
        else:
            self.setText(self._resting_text)
            self.setEnabled(self._enabled_before_loading)


class SelectionTile(QToolButton):
    """Compact checkable tile for environmental roles and method choices."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setProperty("role", "selection-tile")
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class AnimatedComboBox(QComboBox):
    """Search-friendly combo box with a short popup transition."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setMaxVisibleItems(10)
        self.setProperty("animated-selector", True)
        self.setCursor(Qt.PointingHandCursor)
        self.view().setSpacing(2)
        style_selector_popup(self.view())
        self._arrow_angle = 0.0
        self._arrow_animation = QPropertyAnimation(self, b"arrowAngle", self)
        self._arrow_animation.setDuration(140)
        self._arrow_animation.setEasingCurve(QEasingCurve.OutCubic)

    def _get_arrow_angle(self):
        return self._arrow_angle

    def _set_arrow_angle(self, value):
        self._arrow_angle = value
        self.update()

    arrowAngle = Property(float, _get_arrow_angle, _set_arrow_angle)

    def _rotate_arrow(self, angle):
        self._arrow_animation.stop()
        self._arrow_animation.setStartValue(self._arrow_angle)
        self._arrow_animation.setEndValue(angle)
        self._arrow_animation.start()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() - 19, self.height() / 2)
        painter.rotate(self._arrow_angle)
        painter.setPen(QPen(QColor("#326576" if self.isEnabled() else "#a3b3bc"), 1.8,
                            Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath()
        path.moveTo(-4, -2)
        path.lineTo(0, 2)
        path.lineTo(4, -2)
        painter.drawPath(path)
        painter.end()

    def showPopup(self) -> None:
        super().showPopup()
        self._rotate_arrow(180.0)

    def hidePopup(self):
        super().hidePopup()
        self._rotate_arrow(0.0)


class SearchableColumnComboBox(AnimatedComboBox):
    """Consistent searchable selector for columns discovered from local datasets."""

    def __init__(self, placeholder: str = "Select dataset column", parent=None) -> None:
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)
        self.lineEdit().setPlaceholderText(placeholder)
        self.addItem("")
        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)
        style_selector_popup(completer.popup())


class ValidationIndicator(QLabel):
    """Small animated valid/error marker for a field mapping."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ValidationIndicator")
        self.setFixedSize(22, 22)
        self.setAlignment(Qt.AlignCenter)
        self._state = "idle"
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self.hide()

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.setProperty("state", state)
        if state == "idle":
            self._animation.stop()
            self.hide()
            return
        icon_name = "validation" if state == "valid" else "error"
        color = "#2d9b6f" if state == "valid" else "#c95f5f"
        self.setPixmap(line_icon(icon_name, color, 18).pixmap(18, 18))
        self.setToolTip("Mapped column found" if state == "valid" else "Mapped column not found")
        self.show()
        self._animation.stop()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()


class AnimatedStackedWidget(QStackedWidget):
    """Workflow stack that softly reveals the destination page."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._page_animation: QPropertyAnimation | None = None
        self._animated_page = None

    def setCurrentIndex(self, index: int) -> None:
        if index == self.currentIndex():
            return
        if self._page_animation is not None:
            self._page_animation.stop()
            self._page_animation.deleteLater()
            self._page_animation = None
            if self._animated_page is not None:
                self._animated_page.setGraphicsEffect(None)
        super().setCurrentIndex(index)
        page = self.currentWidget()
        if page is None or not self.isVisible():
            return
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(160)
        animation.setStartValue(0.35)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        self._page_animation = animation
        self._animated_page = page
        animation.finished.connect(self._finish_transition)
        animation.start()

    def _finish_transition(self):
        if self._animated_page is not None:
            self._animated_page.setGraphicsEffect(None)
        if self._page_animation is not None:
            self._page_animation.deleteLater()
        self._page_animation = None
        self._animated_page = None


class OceanBackdrop(QFrame):
    """Low-contrast bathymetric contours behind the workspace."""

    def paintEvent(self, event) -> None:
        option = QStyleOption()
        option.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, option, painter, self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(21, 154, 181, 22), 1.2))
        width = float(self.width())
        height = float(self.height())
        for offset in range(0, 150, 24):
            path = QPainterPath()
            path.moveTo(width * 0.58, height - 10 - offset)
            path.cubicTo(
                width * 0.72, height * 0.70 - offset,
                width * 0.83, height * 0.96 - offset,
                width + 20, height * 0.70 - offset,
            )
            painter.drawPath(path)
        painter.end()
