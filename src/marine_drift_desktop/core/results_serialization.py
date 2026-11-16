from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..domain.results import ResultsExportRequest


def results_export_request_to_dict(
    request: ResultsExportRequest,
) -> dict[str, Any]:
    return {
        "results_directory": str(request.results_directory),
        "output_directory": str(request.output_directory),
        "positions_per_drift_day": request.positions_per_drift_day,
        "write_csv": request.write_csv,
        "write_xlsx": request.write_xlsx,
        "output_basename": request.output_basename,
        "observation_dataset_override": (
            str(request.observation_dataset_override)
            if request.observation_dataset_override is not None
            else None
        ),
        "environmental_variables": list(request.environmental_variables),
    }


def write_results_export_request(
    request: ResultsExportRequest,
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(
                results_export_request_to_dict(request),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return path


def read_results_export_request(path: Path) -> ResultsExportRequest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid results export request JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("results export request JSON must be a JSON object")

    results_directory = _required_string(payload, "results_directory")
    output_directory = _required_string(payload, "output_directory")
    positions_per_drift_day = _optional_integer(
        payload, "positions_per_drift_day", 1
    )
    write_csv = _optional_boolean(payload, "write_csv", False)
    write_xlsx = _optional_boolean(payload, "write_xlsx", False)
    output_basename = _optional_string(
        payload, "output_basename", "mortality_positions"
    )
    observation_override = payload.get("observation_dataset_override")
    environmental_variables = payload.get("environmental_variables", [])
    if not isinstance(environmental_variables, list) or not all(
        isinstance(value, str) for value in environmental_variables
    ):
        raise ValueError("environmental_variables must be a list of strings")
    if observation_override is not None and not isinstance(
        observation_override, str
    ):
        raise ValueError(
            "observation_dataset_override must be a string or null"
        )

    return ResultsExportRequest(
        results_directory=Path(results_directory),
        output_directory=Path(output_directory),
        positions_per_drift_day=positions_per_drift_day,
        write_csv=write_csv,
        write_xlsx=write_xlsx,
        output_basename=output_basename,
        observation_dataset_override=(
            Path(observation_override) if observation_override is not None else None
        ),
        environmental_variables=environmental_variables,
    )


def _required_string(payload: dict[str, Any], key: str) -> str:
    if key not in payload:
        raise ValueError(f"missing required key: {key}")
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_string(
    payload: dict[str, Any], key: str, default: str
) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_integer(
    payload: dict[str, Any], key: str, default: int
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_boolean(
    payload: dict[str, Any], key: str, default: bool
) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value
