from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ..core.preflight import run_preflight
from ..domain.models import SimulationRequest


class PreflightWorker(QThread):
    """Run a complete request preflight without blocking the Qt event loop."""

    completed = Signal(int, object)
    failed = Signal(int, str)
    progress_changed = Signal(int, int, int, int)

    def __init__(
        self,
        request: SimulationRequest,
        *,
        generation: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.request = request
        self.generation = generation

    def run(self) -> None:
        try:
            result = run_preflight(self.request, progress=lambda stage, done, total: self.progress_changed.emit(self.generation, stage, done, total))
        except Exception as exc:  # Keep unexpected worker failures out of the GUI thread.
            self.failed.emit(self.generation, str(exc))
            return
        self.completed.emit(self.generation, result)
