from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ASSETS = Path(__file__).parent / "assets" / "icons"
_ALIASES = dict(observations="stranding-data", forcing="environmental-forcing",
                setup="simulation-setup", review="review-run", output="results-export",
                currents="ocean-currents", netcdf="netcdf-dataset",
                validation="validated", search="search-inspect", clock="date-time")


@lru_cache(maxsize=128)
def _svg_icon(name: str, color: str, size: int) -> QIcon | None:
    path = _ASSETS / f"{_ALIASES.get(name, name)}.svg"
    if not path.is_file():
        return None
    source = path.read_bytes()
    # Light foregrounds occur on the navy navigation/header surfaces.
    if QColor(color).lightnessF() > .55:
        source = source.replace(b"#0F2A44", b"#D9F4F7").replace(b"#287FA3", b"#83D8E3")
    renderer = QSvgRenderer(source)
    if not renderer.isValid():
        return None
    icon = QIcon()
    for scale in (1, 2, 3):
        pixmap = QPixmap(size * scale, size * scale)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        if name == "marine-drift-workbench-logo":
            # Qt SVG does not reliably honor Illustrator's CSS clip-path.
            painter.setRenderHint(QPainter.Antialiasing)
            unit = size * scale / 1024
            painter.scale(unit, unit)
            painter.translate(64, 18)
            clip = QPainterPath()
            clip.moveTo(448, 0)
            for x, y in ((896, 259), (896, 729), (448, 988), (0, 729), (0, 259)):
                clip.lineTo(x, y)
            clip.closeSubpath()
            painter.setClipPath(clip)
            renderer.render(painter, QRectF(-154, 0, 1143.5, 988))
            painter.setClipping(False)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#0f2a44"), 24, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(clip)
        else:
            renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        icon.addPixmap(pixmap)
    return icon

ICON_NAMES = frozenset({
    "observations", "forcing", "setup", "review", "location", "run",
    "currents", "wind", "waves", "bathymetry", "netcdf", "uncertainty",
    "validation", "folder", "search", "close", "chevron", "info",
    "warning", "error", "output", "particles", "clock", "export",
})


def line_icon(name: str, color: str = "#58c8d8", size: int = 24) -> QIcon:
    branded = _svg_icon(name, color, size)
    if branded is not None:
        return branded
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    stroke = max(1.5, size / 14)
    painter.setPen(QPen(QColor(color), stroke, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    s = float(size)

    if name == "observations":
        painter.drawRoundedRect(QRectF(s * .18, s * .18, s * .64, s * .64), 2, 2)
        for y in (.34, .5, .66): painter.drawLine(QPointF(s * .29, s * y), QPointF(s * .71, s * y))
    elif name in {"forcing", "currents", "wind", "waves"}:
        amplitude = {"forcing": .12, "currents": .08, "wind": .05, "waves": .15}[name]
        for y in (.32, .5, .68):
            path = QPainterPath(QPointF(s * .14, s * y))
            path.cubicTo(s * .34, s * (y - amplitude), s * .63, s * (y + amplitude), s * .86, s * y)
            painter.drawPath(path)
        if name == "currents":
            painter.drawLine(QPointF(s * .73, s * .39), QPointF(s * .86, s * .5))
            painter.drawLine(QPointF(s * .73, s * .61), QPointF(s * .86, s * .5))
    elif name == "setup":
        for y, x in ((.3, .62), (.5, .38), (.7, .58)):
            painter.drawLine(QPointF(s * .18, s * y), QPointF(s * .82, s * y)); painter.drawEllipse(QPointF(s * x, s * y), s * .055, s * .055)
    elif name in {"review", "validation"}:
        if name == "validation":
            path = QPainterPath(QPointF(s * .5, s * .12)); path.lineTo(s * .78, s * .24); path.lineTo(s * .73, s * .66)
            path.quadTo(s * .5, s * .88, s * .27, s * .66); path.lineTo(s * .22, s * .24); path.closeSubpath(); painter.drawPath(path)
        else: painter.drawRoundedRect(QRectF(s * .2, s * .16, s * .6, s * .68), 3, 3)
        painter.drawLine(QPointF(s * .34, s * .51), QPointF(s * .46, s * .63)); painter.drawLine(QPointF(s * .46, s * .63), QPointF(s * .69, s * .36))
    elif name == "location":
        painter.drawEllipse(QPointF(s * .5, s * .4), s * .2, s * .2); painter.drawEllipse(QPointF(s * .5, s * .4), s * .055, s * .055)
        painter.drawLine(QPointF(s * .36, s * .54), QPointF(s * .5, s * .82)); painter.drawLine(QPointF(s * .64, s * .54), QPointF(s * .5, s * .82))
    elif name == "run":
        painter.drawEllipse(QRectF(s * .14, s * .14, s * .72, s * .72)); path = QPainterPath(QPointF(s * .42, s * .32))
        path.lineTo(s * .7, s * .5); path.lineTo(s * .42, s * .68); path.closeSubpath(); painter.drawPath(path)
    elif name == "bathymetry":
        for inset in (.14, .25, .36): painter.drawEllipse(QRectF(s * inset, s * inset, s * (1 - 2 * inset), s * (1 - 2 * inset)))
    elif name == "netcdf":
        path = QPainterPath(QPointF(s * .25, s * .12)); path.lineTo(s * .62, s * .12); path.lineTo(s * .78, s * .28)
        path.lineTo(s * .78, s * .86); path.lineTo(s * .25, s * .86); path.closeSubpath(); painter.drawPath(path)
        painter.drawText(QRectF(s * .24, s * .32, s * .56, s * .4), Qt.AlignCenter, "{}")
    elif name == "uncertainty":
        painter.setPen(QPen(QColor(color), stroke, Qt.DashLine)); painter.drawEllipse(QRectF(s * .15, s * .15, s * .7, s * .7))
        painter.setPen(QPen(QColor(color), stroke)); painter.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, "?")
    elif name in {"folder", "output"}:
        path = QPainterPath(QPointF(s * .14, s * .3)); path.lineTo(s * .39, s * .3); path.lineTo(s * .47, s * .2)
        path.lineTo(s * .83, s * .2); path.lineTo(s * .86, s * .76); path.lineTo(s * .14, s * .76); path.closeSubpath(); painter.drawPath(path)
    elif name == "search":
        painter.drawEllipse(QRectF(s * .18, s * .18, s * .46, s * .46)); painter.drawLine(QPointF(s * .57, s * .57), QPointF(s * .82, s * .82))
    elif name == "close":
        painter.drawLine(QPointF(s * .25, s * .25), QPointF(s * .75, s * .75)); painter.drawLine(QPointF(s * .75, s * .25), QPointF(s * .25, s * .75))
    elif name == "chevron":
        painter.drawLine(QPointF(s * .34, s * .25), QPointF(s * .62, s * .5)); painter.drawLine(QPointF(s * .62, s * .5), QPointF(s * .34, s * .75))
    elif name == "particles":
        for x, y, r in ((.25, .63, .06), (.43, .49, .05), (.6, .37, .045), (.75, .27, .04)): painter.drawEllipse(QPointF(s * x, s * y), s * r, s * r)
    elif name == "clock":
        painter.drawEllipse(QRectF(s * .15, s * .15, s * .7, s * .7)); painter.drawLine(QPointF(s * .5, s * .5), QPointF(s * .5, s * .28)); painter.drawLine(QPointF(s * .5, s * .5), QPointF(s * .67, s * .59))
    elif name in {"info", "warning", "error"}:
        painter.drawEllipse(QRectF(s * .15, s * .15, s * .7, s * .7)); painter.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, {"info": "i", "warning": "!", "error": "x"}[name])
    else: painter.drawEllipse(QRectF(s * .2, s * .2, s * .6, s * .6))
    painter.end()
    return QIcon(pixmap)
