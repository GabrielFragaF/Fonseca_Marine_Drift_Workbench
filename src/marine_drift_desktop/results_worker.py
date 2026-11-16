from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .core.results_export import generate_mortality_positions
from .core.results_inspection import inspect_results_directory
from .core.results_serialization import read_results_export_request
from .core.environment_export import ENVIRONMENT_EXPORT_CATALOGUE


RESULTS_EVENT_PREFIX = "MARINE_DRIFT_RESULTS_EVENT="


def _emit(event: dict[str, Any]) -> None:
    print(RESULTS_EVENT_PREFIX + json.dumps(event), flush=True)


def run_worker(operation: str, request_path: str) -> int:
    try:
        if operation == "map":
            from .core.trajectory_map import prepare_trajectory_map
            path = Path(request_path)
            parameters = json.loads(path.read_text(encoding="utf-8"))
            result = prepare_trajectory_map(parameters["results_directory"],
                                            parameters["individual_count"], parameters["seed"], _emit)
            output = path.with_name("trajectory-map.json")
            output.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
            _emit({"event": "map_ready", "path": str(output)})
            return 0
        request = read_results_export_request(Path(request_path))
        if operation == "inspect":
            inspection = inspect_results_directory(request.results_directory)
            _emit({
                "event": "inspection",
                "total_file_count": inspection.total_file_count,
                "accepted_file_count": inspection.accepted_file_count,
                "simulation_count": inspection.simulation_count,
                "particle_trajectory_count": inspection.particle_trajectory_count,
                "unique_identifier_count": len(inspection.unique_identifiers),
                "minimum_output_interval_seconds": inspection.minimum_output_interval_seconds,
                "max_positions_per_drift_day": inspection.max_positions_per_drift_day,
                "estimated_rows": inspection.estimated_rows(request.positions_per_drift_day),
                "observation_dataset": str(inspection.observation_dataset),
                "observation_dataset_available": inspection.observation_dataset_available,
                "identifier_column": inspection.identifier_column,
                "environmental_variables": [
                    {
                        "name": name,
                        "label": ENVIRONMENT_EXPORT_CATALOGUE[name].label,
                        "units": metadata.units,
                        "long_name": metadata.long_name,
                        "standard_name": metadata.standard_name,
                        "availability": (
                            "common" if metadata.available_file_count == inspection.accepted_file_count
                            else "partial"
                        ),
                    }
                    for name, metadata in inspection.environmental_variables.items()
                ],
                "issues": [
                    {"path": str(issue.path), "level": issue.level, "message": issue.message}
                    for issue in inspection.issues
                ],
            })
            return 0
        if operation == "export":
            result = generate_mortality_positions(request, progress_callback=_emit)
            _emit({
                "event": "finished",
                "parquet_path": str(result.paths.parquet),
                "csv_path": str(result.paths.csv) if result.paths.csv else None,
                "xlsx_path": str(result.paths.xlsx) if result.paths.xlsx else None,
                "failures_path": str(result.paths.failures) if result.paths.failures else None,
                "manifest_path": str(result.paths.manifest) if result.paths.manifest else None,
                "row_count": result.row_count,
                "accepted_files": result.accepted_files,
                "failed_files": result.failed_files,
                "omitted_positions": result.omitted_positions,
                "warnings": list(result.warnings),
            })
            return 0
        raise ValueError(f"Unsupported results operation: {operation}")
    except Exception as exc:
        _emit({"event": "fatal", "message": str(exc)})
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python -m marine_drift_desktop.results_worker inspect|export|map REQUEST.json"
        )
    raise SystemExit(run_worker(sys.argv[1], sys.argv[2]))
