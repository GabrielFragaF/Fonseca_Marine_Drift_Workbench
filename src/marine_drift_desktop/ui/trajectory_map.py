"""Offline trajectory rendering and independent results-map controls."""
import json
from math import ceil, cos, radians
from pathlib import Path
import random
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt, QTemporaryDir
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QProgressBar,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from .area_map import _outlines
from .components import ActionButton
from .icons import line_icon
from .results_export_controller import ResultsExportController


@lru_cache(maxsize=1)
def _basemap_land():
    path = Path(__file__).parent / "assets" / "trajectory_land.json"
    return json.loads(path.read_text(encoding="utf-8"))


class TrajectoryMapCanvas(QWidget):
    PALETTE = (
        "#088395", "#e86a33", "#2e8a57", "#845ec2",
        "#00a8cc", "#d65a31", "#0c9463", "#4b6587",
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.payload = None
        self._cached_image = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumHeight(450)
        self.setAccessibleName("Random individuals trajectory map")

    def set_payload(self, payload):
        self.payload = payload
        self._cached_image = None
        count = len(payload["runs"]) if payload else 0
        self.setMinimumHeight(430 + ceil(count / 2) * 24)
        self.setAccessibleDescription(
            "; ".join(f"{run['identifier']}, run {run['run_index']}" for run in payload["runs"])
            if payload else "Generate a map to preview existing trajectories."
        )
        self.update()

    def paintEvent(self, event):
        ratio = self.devicePixelRatioF()
        width, height = round(self.width() * ratio), round(self.height() * ratio)
        cached = self._cached_image
        if (cached is None or cached.width() != width or cached.height() != height
                or cached.devicePixelRatio() != ratio):
            cached = QImage(width, height, QImage.Format_ARGB32)
            cached.setDevicePixelRatio(ratio)
            cached.fill(QColor("#f8fbfc"))
            renderer = QPainter(cached)
            self._draw(renderer, QRectF(self.rect()))
            renderer.end()
            self._cached_image = cached
        painter = QPainter(self)
        painter.drawImage(QPointF(0, 0), cached)
        painter.end()

    def _draw(self, painter, rect):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(rect, QColor("#f8fbfc"))
        if not self.payload:
            ghost = QRectF(rect.left() + 28, rect.top() + 34, rect.width() - 56, rect.height() - 68)
            painter.save()
            painter.setClipRect(ghost)
            painter.setPen(QPen(QColor(162, 190, 187, 64), .75))
            painter.setBrush(QColor(201, 222, 218, 24))
            for ring in _outlines():
                points = [QPointF(ghost.left() + (lon + 180) / 360 * ghost.width(),
                                  ghost.top() + (90 - lat) / 180 * ghost.height()) for lon, lat in ring]
                painter.drawPolygon(QPolygonF(points))
            painter.restore()
            banner = QRectF(rect.center().x() - 230, rect.center().y() - 28, 460, 56)
            painter.setPen(QPen(QColor("#c8dde4"), 1))
            painter.setBrush(QColor(255, 255, 255, 224))
            painter.drawRoundedRect(banner, 12, 12)
            painter.setPen(QColor("#527180"))
            painter.drawText(banner.adjusted(16, 8, -16, -8), Qt.AlignCenter,
                             "Inspect a results folder above to preview\nreverse-drift trajectories.")
            return
        runs = self.payload["runs"]
        columns = 3 if rect.width() >= 1000 else 2
        legend_rows = ceil(len(runs) / columns)
        points = [point for run in runs for track in run["tracks"] for point in track if point is not None]
        xs, ys = zip(*points)
        dx, dy = max(max(xs) - min(xs), .2), max(max(ys) - min(ys), .2)
        west, east = max(-180, min(xs) - dx * .12), min(180, max(xs) + dx * .12)
        south, north = max(-90, min(ys) - dy * .12), min(90, max(ys) + dy * .12)
        area = QRectF(rect.left() + 56, rect.top() + 80, rect.width() - 90,
                      max(80, rect.height() - 185 - legend_rows * 24))
        aspect = (east - west) * max(.1, cos(radians((south + north) / 2))) / (north - south)
        width = min(area.width(), area.height() * aspect)
        height = min(area.height(), area.width() / aspect)
        box = QRectF(area.center().x() - width / 2, area.center().y() - height / 2, width, height)

        def project(lon, lat):
            return QPointF(box.left() + (lon - west) / (east - west) * box.width(),
                           box.top() + (north - lat) / (north - south) * box.height())

        font = QFont(self.font())
        font.setPixelSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#0b2e43"))
        painter.drawText(QRectF(18, 12, rect.width() - 36, 28), Qt.AlignLeft, "Sampled reverse-drift trajectories")
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(QRectF(18, 42, rect.width() - 36, 24), Qt.AlignLeft,
                         f"{len(runs)} distinct individuals | One run each | Seed {self.payload['seed']}")
        ocean = QLinearGradient(box.topLeft(), box.bottomRight())
        ocean.setColorAt(0, QColor("#f4fafb"))
        ocean.setColorAt(1, QColor("#e8f4f7"))
        painter.fillRect(box, ocean)
        painter.save()
        painter.setClipRect(box)
        painter.setPen(QPen(QColor("#8faea8"), .75))
        painter.setBrush(QColor("#c9deda"))
        for bounds, rings in _basemap_land():
            if bounds[2] < west or bounds[0] > east or bounds[3] < south or bounds[1] > north:
                continue
            shape = QPainterPath()
            shape.setFillRule(Qt.OddEvenFill)
            for ring in rings:
                shape.addPolygon(QPolygonF([project(*point) for point in ring]))
            painter.drawPath(shape)
        painter.setPen(QPen(QColor("#bddde5"), .5, Qt.DotLine))
        for step in range(1, 4):
            x = west + (east - west) * step / 4
            y = south + (north - south) * step / 4
            painter.drawLine(project(x, south), project(x, north))
            painter.drawLine(project(west, y), project(east, y))
        for index, run in enumerate(runs):
            color = self._color(index)
            for track in run["tracks"]:
                path = QPainterPath()
                move = True
                valid = []
                for point in track:
                    if point is None:
                        move = True
                        continue
                    position = project(*point)
                    if move:
                        path.moveTo(position)
                    else:
                        path.lineTo(position)
                    move = False
                    valid.append(position)
                painter.setBrush(Qt.NoBrush)
                halo = QColor(color)
                halo.setAlpha(45)
                painter.setPen(QPen(halo, 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                core = QColor(color)
                core.setAlpha(240)
                painter.setPen(QPen(core, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                painter.drawPath(path)
                if valid:
                    painter.setBrush(color)
                    painter.setPen(QPen(QColor("#ffffff"), 1.5))
                    painter.drawEllipse(valid[0], 4, 4)
                    painter.setBrush(QColor("#ffffff"))
                    painter.setPen(QPen(color, 1.5))
                    painter.drawRect(QRectF(valid[-1].x() - 3, valid[-1].y() - 3, 6, 6))
        painter.restore()
        painter.setPen(QPen(QColor("#97b7c2"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(box)
        painter.setPen(QColor("#526d7c"))
        painter.drawText(QRectF(rect.left() + 18, box.bottom() + 4, rect.width() - 36, 20), Qt.AlignCenter,
                         f"Longitude {west:.2f}° to {east:.2f}° | Latitude {south:.2f}° to {north:.2f}°")
        top = area.bottom() + 34
        painter.drawText(QRectF(18, top, rect.width() - 36, 22), Qt.AlignLeft,
                         "Filled circle: first displayed position   |   Square: last displayed position")
        cell_width = (rect.width() - 36) / columns
        for index, run in enumerate(runs):
            x = 18 + (index % columns) * cell_width
            y = top + 26 + (index // columns) * 24
            painter.fillRect(QRectF(x, y + 3, 14, 4), self._color(index))
            painter.setPen(QColor("#173b4d"))
            label = f"{run['identifier']} / run {run['run_index']} ({len(run['tracks'])}/{run['particle_count']} particles)"
            label = painter.fontMetrics().elidedText(label, Qt.ElideRight, int(cell_width - 26))
            painter.drawText(QRectF(x + 21, y - 3, cell_width - 26, 23), Qt.AlignLeft, label)
        painter.setPen(QColor("#627985"))
        painter.drawText(QRectF(18, rect.bottom() - 26, rect.width() - 36, 23), Qt.AlignLeft,
                         "Preview may be simplified; not mortality probability. Basemap: Natural Earth, 1:10m.")

    @staticmethod
    def _color(index):
        if index < len(TrajectoryMapCanvas.PALETTE):
            return QColor(TrajectoryMapCanvas.PALETTE[index])
        return QColor.fromHsv((190 + (index - len(TrajectoryMapCanvas.PALETTE)) * 137) % 360, 175, 175)

    def save_png(self, path):
        if not self.payload:
            raise ValueError("Generate a map before saving it.")
        height = 900 + ceil(len(self.payload["runs"]) / 3) * 24
        image = QImage(1600, height, QImage.Format_ARGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        self._draw(painter, QRectF(0, 0, 1600, height))
        painter.end()
        selection = dict(self.payload)
        selection["runs"] = [{key: value for key, value in run.items() if key != "tracks"}
                             for run in selection["runs"]]
        image.setText("Marine Drift Workbench selection", json.dumps(selection))
        if not image.save(str(path), "PNG"):
            raise OSError("The map image could not be saved to this location.")


class TrajectoryMapCard(QGroupBox):
    def __init__(self, source_field, output_field, parent=None):
        super().__init__("Trajectory map", parent)
        self.setObjectName("TrajectoryMapCard")
        self.source_field, self.output_field = source_field, output_field
        self.controller = ResultsExportController(self)
        self.controller.event_received.connect(self._event)
        self.controller.operation_failed.connect(self._failed)
        self.controller.operation_finished.connect(self._finished)
        self._temporary = None
        self._ready_received = False
        self._stale = False
        self._external_busy = False
        self._busy = False
        layout = QVBoxLayout(self)
        copy = QLabel("Randomly choose distinct stranding identifiers, then one available simulation run for each. No simulation is rerun.")
        copy.setWordWrap(True)
        copy.setProperty("role", "muted")
        layout.addWidget(copy)
        controls = QGridLayout()
        self.count = QSpinBox()
        self.count.setRange(1, 50)
        self.count.setValue(5)
        self.count.setAccessibleName("Distinct individuals to plot")
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_647)
        self.seed.setValue(42)
        self.seed.setAccessibleName("Map random seed")
        controls.addWidget(QLabel("Number of individuals (maximum 50)"), 0, 0)
        controls.addWidget(QLabel("Random seed (repeat a selection)"), 0, 1)
        controls.addWidget(self.count, 1, 0)
        controls.addWidget(self.seed, 1, 1)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        layout.addLayout(controls)
        actions = QHBoxLayout()
        self.generate_button = ActionButton("Generate map", variant="primary")
        self.generate_button.setIcon(line_icon("trajectory", "#ffffff", 18))
        self.resample_button = ActionButton("New random sample", variant="secondary")
        self.cancel_button = ActionButton("Cancel map", variant="danger")
        self.save_button = ActionButton("Save map as PNG", variant="secondary")
        for button in (self.generate_button, self.resample_button, self.cancel_button, self.save_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.status = QLabel("Choose a results folder above, then generate a map. Table export is not required.")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "muted")
        layout.addWidget(self.status)
        self.canvas = TrajectoryMapCanvas()
        self.canvas.hide()
        layout.addWidget(self.canvas)
        self.generate_button.clicked.connect(self.generate)
        self.resample_button.clicked.connect(self.resample)
        self.cancel_button.clicked.connect(self.cancel)
        self.save_button.clicked.connect(self.save)
        self.source_field.textChanged.connect(self.invalidate)
        self.count.valueChanged.connect(self.invalidate)
        self.seed.valueChanged.connect(self.invalidate)
        self._update_controls()

    def _update_controls(self):
        enabled = not self._busy and not self._external_busy
        has_source = bool(self.source_field.text().strip())
        self.generate_button.setEnabled(enabled and has_source)
        self.resample_button.setEnabled(enabled and has_source)
        self.save_button.setEnabled(enabled and self.canvas.payload is not None)
        self.cancel_button.setVisible(self._busy)
        self.progress.setVisible(self._busy)
        self.count.setEnabled(enabled)
        self.seed.setEnabled(enabled)

    def set_external_busy(self, busy):
        self._external_busy = busy
        if busy and self._busy:
            self.cancel()
        self._update_controls()

    def invalidate(self, *_):
        self.canvas.set_payload(None)
        self.canvas.hide()
        if self._busy:
            self._stale = True
            self.controller.cancel()
        self.status.setText("Selection changed. Generate a map using the current folder, count, and seed.")
        self._update_controls()

    def generate(self):
        if self._busy or self._external_busy:
            return
        directory = Path(self.source_field.text().strip())
        if not self.source_field.text().strip() or not directory.is_dir():
            self._failed("Choose an existing results folder above.")
            return
        self._temporary = QTemporaryDir()
        if not self._temporary.isValid():
            self._failed("Unable to create a temporary map workspace.")
            return
        path = Path(self._temporary.path()) / "map-request.json"
        try:
            path.write_text(json.dumps({"results_directory": str(directory.resolve()),
                                      "individual_count": self.count.value(), "seed": self.seed.value()}), encoding="utf-8")
        except OSError as exc:
            self._failed(str(exc))
            return
        self._ready_received = False
        self._stale = False
        self._busy = True
        self.canvas.set_payload(None)
        self.canvas.hide()
        self.status.setText("Inspecting existing results and selecting individuals in the background...")
        self._update_controls()
        if not self.controller.start("map", path):
            self._busy = False
            self._failed("Another map operation is already running.")
            self._update_controls()

    def resample(self):
        self.seed.setValue(random.SystemRandom().randrange(2_147_483_648))
        self.generate()

    def cancel(self):
        self._stale = True
        self.status.setText("Map generation cancelled. Existing trajectory files are unchanged.")
        self.controller.cancel()

    def _event(self, event):
        if self._stale:
            return
        if event.get("event") == "fatal":
            self._failed(event.get("message", "Map generation failed."))
        elif event.get("event") == "map_indexed":
            self.status.setText(f"Found {event['candidates']} candidate identifiers; checking selected runs...")
        elif event.get("event") == "map_inspecting":
            self.status.setText(f"Inspecting results: {event['completed']} of {event['total']} files...")
        elif event.get("event") == "map_progress":
            self.status.setText(f"Reading selected runs: {event['completed']} of {event['total']}...")
        elif event.get("event") == "map_ready":
            try:
                payload = json.loads(Path(event["path"]).read_text(encoding="utf-8"))
                self.canvas.set_payload(payload)
                self.canvas.show()
                self._ready_received = True
                self.status.setText(
                    f"Showing {len(payload['runs'])} of {payload['available_individuals']} "
                    f"{'candidate' if payload.get('available_individuals_are_candidates') else 'available'} identifiers; one run each. "
                    + " ".join(payload["warnings"][:3])
                    + (f" {len(payload['warnings']) - 3} additional notices (hover for details)." if len(payload["warnings"]) > 3 else "")
                )
                self.status.setToolTip("\n".join(payload["warnings"]) or "All selected runs loaded.")
            except (OSError, ValueError, KeyError) as exc:
                self._failed(f"Could not read the generated map: {exc}")

    def _failed(self, message):
        if not self._stale:
            self.status.setText(str(message))

    def _finished(self, operation, code):
        self._busy = False
        if not self._stale and not code and not self._ready_received:
            self.status.setText("The worker finished without producing a map. Please retry.")
        self._temporary = None
        self._update_controls()

    def save(self):
        if not self.canvas.payload or self._busy:
            return
        directory = self.output_field.text().strip() or self.source_field.text().strip()
        path, _ = QFileDialog.getSaveFileName(self, "Save trajectory map", str(Path(directory) / "trajectory_map.png"), "PNG image (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            try:
                self.canvas.save_png(path)
                self.status.setText(f"Map saved: {path}. Selection metadata is embedded in the PNG.")
            except (OSError, ValueError) as exc:
                self._failed(str(exc))

    def shutdown(self):
        self.controller.shutdown()
        self._temporary = None
