"""Inspect trajectory headers without relying on checkpoint order or file names."""
from pathlib import Path
import re

from .trajectory_provenance import read_trajectory_provenance
from .planning import stranding_event_token


def inspect_existing_outputs(jobs, directory, fingerprint, progress):
    from netCDF4 import Dataset

    expected = {}
    expected_events = {}
    for job in jobs:
        key = (job.observation.stranding_identifier, job.observation.observed_at,
               job.iteration.iteration_index)
        expected.setdefault(key, []).append(job.iteration.output_path)
        expected_events[job.iteration.output_path] = stranding_event_token(job.observation)
    expected_paths = {path for paths in expected.values() for path in paths}
    complete = set()
    superseded = []
    conflicts = invalid = unrelated = 0
    changed = False
    files = list(directory.glob("*.nc"))
    for index, path in enumerate(files, 1):
        if path.stem.endswith(".partial"):
            invalid += 1
            continue
        structurally_complete = False
        try:
            with Dataset(path) as dataset:
                if ("time" not in dataset.dimensions or not len(dataset.dimensions["time"])
                        or "lon" not in dataset.variables or "lat" not in dataset.variables):
                    raise ValueError("Incomplete trajectory")
                signature = getattr(dataset, "marine_drift_request_fingerprint", "")
                structurally_complete = True
            provenance = read_trajectory_provenance(path)
            key = (provenance.stranding_identifier, provenance.observed_at,
                   provenance.iteration_index)
            candidates = expected.get(key, [])
            planned_path = path if path in candidates else (candidates[0] if len(candidates) == 1 else None)
            if candidates and planned_path is None:
                conflicts += 1
                continue
            if planned_path is not None:
                filename_event = re.search(r"_EV([0-9a-f]{16})_\d+\.nc$", path.name, re.IGNORECASE)
                token = provenance.event_token or (filename_event.group(1).lower() if filename_event else "")
                if token != expected_events[planned_path] or (filename_event and provenance.event_token and filename_event.group(1).lower() != provenance.event_token):
                    conflicts += 1
                    if path not in expected_paths:
                        superseded.append(str(path))
                    continue
            if planned_path is not None and path not in expected_paths:
                superseded.append(str(path))
            if planned_path is None:
                if path in expected_paths:
                    conflicts += 1
                else:
                    unrelated += 1
            elif planned_path in complete:
                conflicts += 1
            else:
                complete.add(planned_path)
                changed |= signature != fingerprint
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            if path in expected_paths and not structurally_complete:
                invalid += 1
            elif path in expected_paths:
                # Unknown valid files must not be silently overwritten in preserve mode.
                conflicts += 1
            else:
                unrelated += 1
        if index % 100 == 0 or index == len(files):
            progress({"event": "resume_scan", "processed": index, "total_jobs": len(files)})
    return complete, {"completed": len(complete), "pending": len(expected_paths) - len(complete),
                      "invalid": invalid, "conflicts": conflicts, "unrelated": unrelated,
                      "total_jobs": len(expected_paths), "configuration_changed": changed,
                      "superseded_files": superseded}
