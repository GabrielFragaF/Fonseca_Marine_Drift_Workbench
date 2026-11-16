from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, Signal, Slot

from ..results_worker import RESULTS_EVENT_PREFIX


class ResultsExportController(QObject):
    event_received = Signal(dict)
    operation_failed = Signal(str)
    operation_finished = Signal(str, int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.process: QProcess | None = None
        self._buffer = ""
        self._operation = ""
        self._fatal_received = False

    def start(self, operation: str, request_path: Path) -> bool:
        if self.process is not None:
            return False
        process = QProcess(self)
        process.setProcessChannelMode(QProcess.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.process = process
        self._operation = operation
        self._buffer = ""
        self._fatal_received = False
        arguments = (
            ["--results-worker", operation, str(request_path)]
            if getattr(sys, "frozen", False)
            else ["-m", "marine_drift_desktop.results_worker", operation, str(request_path)]
        )
        program = sys.executable
        if not getattr(sys, "frozen", False) and sys.platform == "win32":
            windowless = Path(sys.executable).with_name("pythonw.exe")
            if windowless.is_file():
                program = str(windowless)
        process.start(program, arguments)
        return True

    def cancel(self) -> None:
        process = self.process
        if process is None:
            return
        process.terminate()
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)
        timer.start(3000)

    def shutdown(self) -> None:
        process = self.process
        if process is None:
            return
        process.terminate()
        if not process.waitForFinished(1500):
            process.kill()
            process.waitForFinished(1500)

    @Slot()
    def _read_output(self) -> None:
        if self.process is None:
            return
        self._buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace").replace("\r\n", "\n")
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if not line.startswith(RESULTS_EVENT_PREFIX):
                continue
            try:
                event = json.loads(line[len(RESULTS_EVENT_PREFIX):])
            except (json.JSONDecodeError, TypeError):
                continue
            if event.get("event") == "fatal":
                self._fatal_received = True
            self.event_received.emit(event)

    @Slot(QProcess.ProcessError)
    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self.operation_failed.emit("The results worker could not be started.")
            self._fatal_received = True
            self._finished(-1, QProcess.NormalExit)

    @Slot(int, QProcess.ExitStatus)
    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self.process
        self._read_output()
        operation = self._operation
        self.process = None
        if exit_code and not self._fatal_received:
            self.operation_failed.emit(f"The results worker exited unexpectedly with code {exit_code}.")
        self.operation_finished.emit(operation, exit_code)
        if process is not None:
            process.deleteLater()
