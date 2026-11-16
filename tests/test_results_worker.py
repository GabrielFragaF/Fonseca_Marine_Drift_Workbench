from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from marine_drift_desktop.core.results_serialization import write_results_export_request
from marine_drift_desktop.results_worker import RESULTS_EVENT_PREFIX, run_worker
from tests.results_test_support import make_results_fixture


def capture_worker(operation: str, request_path: Path) -> tuple[int, list[dict]]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = run_worker(operation, str(request_path))
    events = [
        json.loads(line.removeprefix(RESULTS_EVENT_PREFIX))
        for line in output.getvalue().splitlines()
        if line.startswith(RESULTS_EVENT_PREFIX)
    ]
    return exit_code, events


class ResultsWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "results_worker"
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True)

    def _request_path(self) -> Path:
        return write_results_export_request(
            make_results_fixture(self.root), self.root / "request.json"
        )

    def test_inspect_worker_emits_serializable_capacity_event(self) -> None:
        exit_code, events = capture_worker("inspect", self._request_path())

        self.assertEqual(exit_code, 0)
        self.assertEqual(events[-1]["event"], "inspection")
        self.assertEqual(events[-1]["accepted_file_count"], 1)
        self.assertEqual(events[-1]["particle_trajectory_count"], 2)
        self.assertEqual(events[-1]["max_positions_per_drift_day"], 24)
        self.assertEqual(events[-1]["estimated_rows"], 8)

    def test_export_worker_emits_finished_parquet_path(self) -> None:
        exit_code, events = capture_worker("export", self._request_path())

        self.assertEqual(exit_code, 0)
        self.assertEqual(events[-1]["event"], "finished")
        self.assertTrue(Path(events[-1]["parquet_path"]).is_file())
        self.assertEqual(events[-1]["row_count"], 8)
        self.assertTrue(any(event["event"] == "progress" for event in events))

    def test_worker_emits_one_fatal_event_for_invalid_operation(self) -> None:
        exit_code, events = capture_worker("invalid", self._request_path())

        self.assertEqual(exit_code, 1)
        self.assertEqual(events, [{"event": "fatal", "message": "Unsupported results operation: invalid"}])

    def test_main_dispatches_results_worker_without_creating_gui(self) -> None:
        from marine_drift_desktop import main

        with patch.object(sys, "argv", ["app", "--results-worker", "inspect", "request.json"]), patch(
            "marine_drift_desktop.results_worker.run_worker", return_value=7
        ) as worker:
            exit_code = main.run()

        self.assertEqual(exit_code, 7)
        worker.assert_called_once_with("inspect", "request.json")


if __name__ == "__main__":
    unittest.main()
