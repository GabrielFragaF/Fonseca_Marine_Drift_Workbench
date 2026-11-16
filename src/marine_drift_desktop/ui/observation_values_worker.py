from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.io import read_observation_values


class ObservationValuesWorker(QThread):
    completed = Signal(str, str, list)
    failed = Signal(str, str)

    def __init__(self, path: Path, column: str, parent=None) -> None:
        super().__init__(parent)
        self.path = path
        self.column = column

    def run(self) -> None:
        try:
            values = read_observation_values(self.path, self.column)
        except Exception as exc:
            self.failed.emit(self.column, str(exc))
        else:
            self.completed.emit(str(self.path), self.column, values)
