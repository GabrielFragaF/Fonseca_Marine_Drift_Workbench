from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..domain.models import (
    ColumnMapping,
    CoverageSettings,
    DataSourcePaths,
    DurationSettings,
    EnvironmentalReaderConfig,
    FallbackValues,
    FilterCondition,
    ObservationSelectionSettings,
    PositionSearchSettings,
    SimulationRequest,
    SimulationSettings,
    SpatialExtent,
    WindDriftSettings,
)


def simulation_request_to_dict(request: SimulationRequest) -> dict[str, Any]:
    return _json_ready(asdict(request))


def write_simulation_request(request: SimulationRequest, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(simulation_request_to_dict(request), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def read_simulation_request(path: Path) -> SimulationRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return simulation_request_from_dict(payload)


def simulation_request_from_dict(payload: dict[str, Any]) -> SimulationRequest:
    source = payload["data_sources"]
    readers = [
        EnvironmentalReaderConfig(
            path=Path(reader["path"]),
            roles=list(reader.get("roles", [])),
            recognized_variables=list(reader.get("recognized_variables", [])),
            role_source=reader.get("role_source", "needs_review"),
            group_id=str(reader.get("group_id", "")),
            priority=int(reader.get("priority", 0)),
        )
        for reader in source.get("environment_readers", [])
    ]
    data_sources = DataSourcePaths(
        **{
            key: Path(value) if value else None
            for key, value in source.items()
            if key != "environment_readers"
        },
        environment_readers=readers,
    )
    settings_payload = dict(payload["settings"])
    extent_payload = settings_payload.pop("extent")
    fallback_payload = settings_payload.pop("fallback_values", {})
    wind_payload = settings_payload.pop("wind_drift")
    duration_payload = settings_payload.pop("duration")
    coverage_payload = settings_payload.pop("coverage", {})
    position_search_payload = settings_payload.pop("position_search", {})
    selection_payload = settings_payload.pop("observation_selection", {})
    condition_payloads = selection_payload.pop("conditions", [])
    duration_payload["cool_water_days"] = {
        int(key): int(value)
        for key, value in duration_payload["cool_water_days"].items()
    }
    duration_payload["warm_water_days"] = {
        int(key): int(value)
        for key, value in duration_payload["warm_water_days"].items()
    }
    duration_payload["scenario_days"] = {
        int(key): [int(day) for day in values]
        for key, values in duration_payload.get("scenario_days", {}).items()
    }
    duration_payload["decomposition_value_map"] = {
        str(key): int(value)
        for key, value in duration_payload.get("decomposition_value_map", {}).items()
    }
    settings = SimulationSettings(
        **settings_payload,
        extent=SpatialExtent(**extent_payload),
        fallback_values=FallbackValues(**fallback_payload),
        wind_drift=WindDriftSettings(**wind_payload),
        duration=DurationSettings(**duration_payload),
        coverage=CoverageSettings(**coverage_payload),
        position_search=PositionSearchSettings(**position_search_payload),
        observation_selection=ObservationSelectionSettings(
            **selection_payload,
            conditions=[FilterCondition(**condition) for condition in condition_payloads],
        ),
    )
    return SimulationRequest(
        data_sources=data_sources,
        column_mapping=ColumnMapping(**payload["column_mapping"]),
        settings=settings,
    )


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
