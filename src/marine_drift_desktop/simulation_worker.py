from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core.batch_execution import DEFAULT_BATCH_SIZE, run_simulation_batches
from .core.request_serialization import read_simulation_request

EVENT_PREFIX = "MARINE_DRIFT_EVENT="


def _emit(event: dict[str, Any]) -> None:
    print(EVENT_PREFIX + json.dumps(event), flush=True)


def run_worker(request_path: str) -> int:
    started = time.monotonic()
    status_path = Path(request_path).parent / ".marine_drift_run.json"
    def record(state: str, **details: Any) -> None:
        payload = {"state": state, "updated_utc": datetime.now(timezone.utc).isoformat(), "request": str(request_path), **details}
        temporary = status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(status_path)
    try:
        record("started")
        _emit({"event": "dispatch_started", "message": "Simulation worker started"})
        request = read_simulation_request(Path(request_path))

        def choose_existing(review: dict[str, Any]) -> str:
            _emit({"event": "resume_review", **review})
            # The GUI answers through the worker's stdin; no model runs before consent.
            reply = sys.stdin.readline()
            return str(json.loads(reply).get("decision", "cancel")) if reply else "cancel"

        def report(event: dict[str, Any]) -> None:
            event = dict(event)
            event.setdefault("elapsed_seconds", time.monotonic() - started)
            if event.get("event") in {"workload", "batch_started", "job_failed"}:
                record("running", detail=event)
            # Updating the GUI every job would add avoidable IPC overhead on large runs.
            if event.get("event") != "progress" or (
                int(event.get("processed", 0)) % 25 == 0
                or event.get("processed") == event.get("total_jobs")
            ):
                _emit(event)

        result = run_simulation_batches(
            request,
            batch_size=DEFAULT_BATCH_SIZE,
            progress_callback=report,
            existing_output_decision=choose_existing,
        )
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("Simulation start cancelled;"):
            record("cancelled", message=str(exc))
            _emit({"event": "start_cancelled", "message": str(exc)})
            return 0
        try:
            record("failed", message=str(exc))
        except OSError:
            pass
        _emit({"event": "fatal", "message": str(exc)})
        return 1

    record("completed_with_errors" if result.failed_jobs else "completed", completed=result.completed_jobs, failed=result.failed_jobs)
    _emit({
        "event": "finished",
        "total_jobs": result.total_jobs,
        "completed": result.completed_jobs,
        "failed": result.failed_jobs,
        "existing": result.existing_jobs,
        "skipped_records": result.skipped_records,
        "source_rows": result.source_rows,
        "selected_rows": result.selected_rows,
        "positions_adjusted": result.positions_adjusted,
        "position_search_failed": result.position_search_failed,
        "elapsed_seconds": result.elapsed_seconds,
        "completion_status": result.completion_status,
        "manifest_path": str(result.manifest_path or ""),
        "checkpoint_path": str(result.checkpoint_path),
        "failure_log_path": str(result.failure_log_path),
    })
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m marine_drift_desktop.simulation_worker REQUEST.json")
    raise SystemExit(run_worker(sys.argv[1]))
