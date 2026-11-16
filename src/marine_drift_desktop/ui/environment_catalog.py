from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThread, Qt, Signal

from ..core.environment import EnvironmentalReaderInspection, inspect_environment_reader
from ..domain.models import EnvironmentalReaderConfig

CatalogStatus = Literal["pending", "inspecting", "ready", "warning", "error"]
RoleSource = Literal["auto", "user", "needs_review"]

ROLE_OPTIONS = (
    "Ocean circulation",
    "Atmospheric forcing",
    "Waves",
    "Temperature & hydrography",
    "Bathymetry",
    "Biogeochemistry",
    "Other / custom",
)


@dataclass(frozen=True, slots=True)
class CatalogAddResult:
    added_paths: tuple[Path, ...] = ()
    duplicate_paths: tuple[Path, ...] = ()


@dataclass(slots=True)
class EnvironmentalCatalogEntry:
    path: Path
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    roles: list[str] = field(default_factory=list)
    role_source: RoleSource = "needs_review"
    status: CatalogStatus = "pending"
    inspection: EnvironmentalReaderInspection | None = None
    error_message: str = ""
    group_id: str = ""
    priority: int = 0
    recognized_variables: list[str] = field(default_factory=list)

    def to_config(self) -> EnvironmentalReaderConfig:
        recognized = (
            list(self.inspection.recognized_opendrift_variables)
            if self.inspection is not None
            else list(self.recognized_variables)
        )
        return EnvironmentalReaderConfig(
            path=self.path,
            roles=list(self.roles),
            recognized_variables=recognized,
            role_source=self.role_source,
            group_id=self.group_id,
            priority=self.priority,
        )


class EnvironmentalCatalogModel(QAbstractTableModel):
    catalogChanged = Signal()

    HEADERS = ("File", "Role", "Temporal coverage", "Spatial coverage", "Status")
    EntryRole = Qt.UserRole + 1
    PathRole = Qt.UserRole + 2
    StatusRole = Qt.UserRole + 3
    SortRole = Qt.UserRole + 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[EnvironmentalCatalogEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == self.EntryRole:
            return entry
        if role == self.PathRole:
            return str(entry.path)
        if role == self.StatusRole:
            return entry.status
        if role == Qt.ToolTipRole:
            return entry.error_message or str(entry.path)
        values = self._display_values(entry)
        if role == Qt.DisplayRole:
            return values[index.column()]
        if role == self.SortRole:
            return self._sort_value(entry, index.column())
        if role == Qt.TextAlignmentRole and index.column() == 4:
            return Qt.AlignCenter
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if not 0 <= column < len(self.HEADERS):
            return
        self.layoutAboutToBeChanged.emit()
        self._entries.sort(
            key=lambda entry: self._sort_value(entry, column),
            reverse=order == Qt.DescendingOrder,
        )
        self.layoutChanged.emit()

    def entry_at(self, row: int) -> EnvironmentalCatalogEntry:
        return self._entries[row]

    def add_paths(self, paths: list[Path]) -> CatalogAddResult:
        existing = {self._path_key(entry.path) for entry in self._entries}
        added: list[Path] = []
        duplicates: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            key = self._path_key(path)
            if key in existing:
                duplicates.append(path)
                continue
            row = len(self._entries)
            self.beginInsertRows(QModelIndex(), row, row)
            self._entries.append(EnvironmentalCatalogEntry(path=path))
            self.endInsertRows()
            existing.add(key)
            added.append(path)
        if added:
            self.catalogChanged.emit()
        return CatalogAddResult(tuple(added), tuple(duplicates))

    def remove_rows(self, rows: list[int]) -> tuple[Path, ...]:
        valid_rows = sorted({row for row in rows if 0 <= row < len(self._entries)}, reverse=True)
        removed: list[Path] = []
        for row in valid_rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            removed.append(self._entries.pop(row).path)
            self.endRemoveRows()
        if removed:
            self.catalogChanged.emit()
        return tuple(reversed(removed))

    def update_roles(
        self, path: Path, roles: list[str], *, source: RoleSource = "user"
    ) -> None:
        row = self._row_for_path(path)
        entry = self._entries[row]
        entry.roles = list(dict.fromkeys(role for role in roles if role in ROLE_OPTIONS))
        entry.role_source = source if entry.roles else "needs_review"
        self.dataChanged.emit(self.index(row, 1), self.index(row, 1))
        self.catalogChanged.emit()

    def mark_inspecting(self, path: Path) -> None:
        row = self._row_for_path(path)
        self._entries[row].status = "inspecting"
        self._emit_row_changed(row)

    def apply_inspection(
        self, path: Path, inspection: EnvironmentalReaderInspection
    ) -> None:
        row = self._row_for_path(path)
        entry = self._entries[row]
        entry.inspection = inspection
        entry.error_message = ""
        entry.status = (
            "warning"
            if any(item.level == "warning" for item in inspection.diagnostics)
            else "ready"
        )
        if not entry.roles:
            detected = _detect_roles(inspection.recognized_opendrift_variables)
            entry.roles = detected
            entry.role_source = "auto" if detected else "needs_review"
        self._emit_row_changed(row)
        self.catalogChanged.emit()

    def apply_error(self, path: Path, message: str) -> None:
        row = self._row_for_path(path)
        entry = self._entries[row]
        entry.status = "error"
        entry.error_message = message
        self._emit_row_changed(row)
        self.catalogChanged.emit()

    def to_configs(self) -> list[EnvironmentalReaderConfig]:
        return [entry.to_config() for entry in self._entries]

    def set_configs(self, configs: list[EnvironmentalReaderConfig]) -> None:
        self.beginResetModel()
        self._entries = [
            EnvironmentalCatalogEntry(
                path=config.path,
                roles=list(config.roles),
                role_source=config.role_source,
                status="pending",
                group_id=config.group_id,
                priority=config.priority,
                recognized_variables=list(config.recognized_variables),
            )
            for config in configs
        ]
        self.endResetModel()
        self.catalogChanged.emit()

    def _emit_row_changed(self, row: int) -> None:
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1))

    def _row_for_path(self, path: Path) -> int:
        key = self._path_key(path)
        for row, entry in enumerate(self._entries):
            if self._path_key(entry.path) == key:
                return row
        raise KeyError(path)

    @staticmethod
    def _path_key(path: Path) -> str:
        return str(path.resolve()).casefold()

    @staticmethod
    def _display_values(entry: EnvironmentalCatalogEntry) -> tuple[str, ...]:
        inspection = entry.inspection
        temporal = "Not inspected"
        spatial = "Not inspected"
        if inspection is not None:
            temporal = (
                f"{inspection.time_start} to {inspection.time_end}"
                if inspection.time_start and inspection.time_end
                else "Not available"
            )
            if inspection.extent is not None:
                extent = inspection.extent
                spatial = (
                    f"{extent.min_longitude:.2f} to {extent.max_longitude:.2f}; "
                    f"{extent.min_latitude:.2f} to {extent.max_latitude:.2f}"
                )
            else:
                spatial = "Not available"
        status_labels = {
            "pending": "Pending",
            "inspecting": "Inspecting",
            "ready": "Ready",
            "warning": "Review",
            "error": "Blocking error",
        }
        return (
            entry.path.name,
            ", ".join(entry.roles) or "Assign role",
            temporal,
            spatial,
            status_labels[entry.status],
        )

    @staticmethod
    def _sort_value(entry: EnvironmentalCatalogEntry, column: int):
        if column == 0:
            return entry.path.name.casefold()
        if column == 1:
            return ", ".join(entry.roles).casefold()
        if column == 2:
            return entry.inspection.time_start if entry.inspection else ""
        if column == 3:
            return entry.inspection.grid_type if entry.inspection else ""
        order = {"error": 0, "warning": 1, "inspecting": 2, "pending": 3, "ready": 4}
        return order[entry.status]


class EnvironmentInspectionWorker(QThread):
    inspected = Signal(object, object)
    failed = Signal(object, str)

    def __init__(self, paths: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.paths = list(paths)

    def run(self) -> None:
        for path in self.paths:
            if self.isInterruptionRequested():
                return
            try:
                inspection = inspect_environment_reader(path)
            except (ImportError, OSError, ValueError) as exc:
                self.failed.emit(path, str(exc))
                continue
            self.inspected.emit(path, inspection)


def _detect_roles(variables: list[str]) -> list[str]:
    names = set(variables)
    roles: list[str] = []
    if names & {"x_sea_water_velocity", "y_sea_water_velocity"}:
        roles.append("Ocean circulation")
    if names & {"x_wind", "y_wind"}:
        roles.append("Atmospheric forcing")
    if any("stokes" in name or "wave" in name for name in names):
        roles.append("Waves")
    if names & {"sea_water_temperature", "sea_surface_temperature", "sea_water_salinity"}:
        roles.append("Temperature & hydrography")
    if "sea_floor_depth_below_sea_level" in names:
        roles.append("Bathymetry")
    return roles
