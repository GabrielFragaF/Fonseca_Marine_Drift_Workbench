from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import SimulationRequest
from .request_serialization import simulation_request_from_dict, simulation_request_to_dict

PROJECT_FORMAT = "marine-drift-workbench-project"
PROJECT_VERSION = 1


class ProjectFileError(ValueError):
    """Raised when a project document cannot be safely read or written."""


@dataclass(slots=True)
class ProjectDocument:
    name: str
    request: SimulationRequest


def write_project(document: ProjectDocument, path: Path) -> Path:
    destination = Path(path)
    if destination.suffix.lower() != ".mdwproj":
        destination = destination.with_suffix(".mdwproj")
    payload = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "name": document.name.strip() or "New reverse-drift project",
        "configuration": simulation_request_to_dict(document.request),
    }
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ProjectFileError(f"The project could not be saved: {exc}") from exc
    return destination


def read_project(path: Path) -> ProjectDocument:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectFileError(f"The project file could not be read: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("format") != PROJECT_FORMAT:
        raise ProjectFileError("This is not a Marine Drift Workbench project file.")
    if payload.get("version") != PROJECT_VERSION:
        raise ProjectFileError(
            f"Project version {payload.get('version')!r} is not supported."
        )
    try:
        if not isinstance(payload["name"], str) or not isinstance(payload["configuration"], dict):
            raise ValueError("Expected a project name and configuration object.")
        name = payload["name"].strip() or "New reverse-drift project"
        request = simulation_request_from_dict(payload["configuration"])
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProjectFileError(f"The project configuration is invalid: {exc}") from exc
    return ProjectDocument(name=name, request=request)
