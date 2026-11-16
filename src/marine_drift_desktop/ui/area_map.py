from functools import lru_cache
import json
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget, QSizePolicy, QHBoxLayout, QVBoxLayout, QPushButton


@lru_cache(maxsize=1)
def _outlines():
    return json.loads((Path(__file__).parent / "assets/world.json").read_text(encoding="utf-8"))


class StudyAreaMap(QWidget):
    """Offline equirectangular overview; not the simulation landmask."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bounds = (-180.0, 180.0, -90.0, 90.0)
        self.view_bounds = self.bounds
        self.follow_bounds = True
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Modelling area world map")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        toolbar = QHBoxLayout()
        for text, name, action in (
            ("+", "Zoom in", lambda: self.zoom(0.5)),
            ("-", "Zoom out", lambda: self.zoom(2)),
            ("Fit study area", "Fit study area", self.fit_to_bounds),
            ("World", "Show world", self.show_world),
        ):
            button = QPushButton(text)
            button.setAccessibleName(name)
            button.setToolTip(name + " (view only)")
            button.clicked.connect(action)
            toolbar.addWidget(button)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        layout.addStretch()

    def _valid_bounds(self):
        w, e, s, n = self.bounds
        return -180 <= w < e <= 180 and -90 <= s < n <= 90

    def _set_view(self, cx, cy, width):
        width = max(0.02, min(360, width))
        height = width / 2
        cx = max(-180 + width / 2, min(180 - width / 2, cx))
        cy = max(-90 + height / 2, min(90 - height / 2, cy))
        self.view_bounds = (cx - width / 2, cx + width / 2,
                            cy - height / 2, cy + height / 2)
        self.update()

    def fit_to_bounds(self):
        self.follow_bounds = True
        if self._valid_bounds():
            w, e, s, n = self.bounds
            self._set_view((w + e) / 2, (s + n) / 2, max(e - w, 2 * (n - s)) * 1.3)

    def show_world(self):
        self.follow_bounds = False
        self._set_view(0, 0, 360)

    def zoom(self, factor):
        self.follow_bounds = False
        w, e, s, n = self.view_bounds
        self._set_view((w + e) / 2, (s + n) / 2, (e - w) * factor)

    def set_bounds(self, west, east, south, north):
        self.bounds = (west, east, south, north)
        self.setAccessibleDescription(
            f"Longitude {west:g} to {east:g}; latitude {south:g} to {north:g}."
        )
        if self.follow_bounds:
            self.fit_to_bounds()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = max(1, min(self.width() - 24, (self.height() - 100) * 2))
        box = QRectF((self.width() - width) / 2, 60, width, width / 2)
        vw, ve, vs, vn = self.view_bounds

        def project(lon, lat):
            return QPointF(box.left() + (lon - vw) / (ve - vw) * box.width(),
                           box.top() + (vn - lat) / (vn - vs) * box.height())

        ocean = QLinearGradient(box.topLeft(), box.bottomRight())
        ocean.setColorAt(0, QColor("#f4fafb"))
        ocean.setColorAt(1, QColor("#e8f4f7"))
        painter.setPen(QPen(QColor("#c9e0e5"), 1))
        painter.setBrush(ocean)
        painter.drawRoundedRect(box, 8, 8)
        painter.save()
        painter.setClipRect(box)
        painter.setPen(QPen(QColor("#bddde5"), .5, Qt.DotLine))
        for i in range(1, 6):
            lon = vw + (ve - vw) * i / 6
            painter.drawLine(project(lon, -90), project(lon, 90))
        for i in range(1, 4):
            lat = vs + (vn - vs) * i / 4
            painter.drawLine(project(-180, lat), project(180, lat))
        painter.setBrush(QColor("#c9deda"))
        painter.setPen(QPen(QColor("#8faea8"), .75))
        for ring in _outlines():
            painter.drawPolygon(QPolygonF([project(*point) for point in ring]))
        west, east, south, north = self.bounds
        valid = -180 <= west < east <= 180 and -90 <= south < north <= 90
        if valid:
            painter.setPen(QPen(QColor("#05869d"), 2))
            painter.setBrush(QColor(5, 150, 172, 45))
            selected = QRectF(project(west, north), project(east, south))
            painter.drawRect(selected)
            painter.setBrush(QColor("#ffffff"))
            for point in (selected.topLeft(), selected.topRight(), selected.bottomLeft(), selected.bottomRight()):
                painter.drawEllipse(point, 2.5, 2.5)
        painter.restore()
        painter.setPen(QColor("#526d7c" if valid else "#b34444"))
        caption = (f"{west:g}° to {east:g}° lon  |  {south:g}° to {north:g}° lat" if valid
                   else "Set minimum coordinates below maximum coordinates")
        painter.drawText(QRectF(0, box.bottom() + 6, self.width(), 24), Qt.AlignCenter, caption)
        painter.end()
