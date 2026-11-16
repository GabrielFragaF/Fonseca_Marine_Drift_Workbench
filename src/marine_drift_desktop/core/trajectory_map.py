"""Bounded, reproducible previews of existing reverse-drift results."""
from collections import defaultdict
from math import ceil, isfinite
from numbers import Integral
from pathlib import Path
import random
import re

import numpy as np
from netCDF4 import Dataset

from .results_inspection import inspect_results_directory, _read_file_metadata
from .results_source import normalize_stranding_identifier
from .trajectory_provenance import read_trajectory_provenance

MAX_INDIVIDUALS = 50
MAX_PARTICLES_PER_RUN = 12
POINT_BUDGET = 120_000

_NUMERIC_WORKBENCH_NAME = re.compile(r"^(\d+)_[^_]+_DEC\d+_DUR\d+d_EV[0-9a-f]{16}_\d+\.nc$", re.IGNORECASE)


def _sample_numeric_files(directory, individual_count, rng, progress_callback):
    """Index canonical numeric names cheaply, then validate only sampled files."""
    directory = Path(directory)
    if not directory.is_dir():
        return None
    groups = defaultdict(list)
    for path in directory.glob("*.nc"):
        if path.name.lower().endswith(".partial.nc"):
            continue
        match = _NUMERIC_WORKBENCH_NAME.fullmatch(path.name)
        if not match:
            return None
        groups[normalize_stranding_identifier(match.group(1))].append(path)
    if not groups:
        return None
    if progress_callback:
        progress_callback({"event": "map_indexed", "candidates": len(groups)})
    identifiers = sorted(groups)
    rng.shuffle(identifiers)
    chosen = {}
    warnings = ["Candidate count is based on filenames; only selected runs were checked."]
    for identifier in identifiers:
        paths = sorted(groups[identifier])
        rng.shuffle(paths)
        for path in paths:
            try:
                provenance = read_trajectory_provenance(path)
                if normalize_stranding_identifier(provenance.stranding_identifier) != identifier:
                    raise ValueError("Filename identifier does not match embedded provenance.")
                chosen[identifier] = [_read_file_metadata(path, provenance)]
                break
            except (OSError, RuntimeError, ValueError) as exc:
                warnings.append(f"{path.name}: {exc}")
        if len(chosen) == individual_count:
            break
    return chosen, warnings, len(groups)


def _read_track(dataset, particle, count, point_limit):
    """Read one particle in bounded chunks, preserving gaps and date-line breaks."""
    stride = max(1, ceil(count / point_limit))
    backwards = float(dataset.variables["time"][0]) < float(dataset.variables["time"][-1])
    starts = range(0, count, 4096)
    if backwards:
        starts = reversed(list(starts))
    track = []
    previous = None
    ordinal = 0
    truncated = False

    def finish_segment():
        if previous is not None and track and track[-1] != previous:
            track.append(previous)
        if track and track[-1] is not None:
            track.append(None)

    for start in starts:
        end = min(start + 4096, count)
        lon = np.ma.asarray(dataset.variables["lon"][particle, start:end], dtype=float).filled(np.nan)
        lat = np.ma.asarray(dataset.variables["lat"][particle, start:end], dtype=float).filled(np.nan)
        if backwards:
            lon, lat = lon[::-1], lat[::-1]
        for x, y in zip(lon, lat):
            valid = isfinite(x) and isfinite(y) and -180 <= x <= 360 and -90 <= y <= 90
            point = [float((x + 180) % 360 - 180), float(y)] if valid else None
            if not valid:
                finish_segment()
                previous = None
            else:
                if previous is not None and abs(point[0] - previous[0]) > 180:
                    finish_segment()
                    previous = None
                if previous is None or ordinal % stride == 0:
                    track.append(point)
                previous = point
            ordinal += 1
            if len(track) >= point_limit * 2:
                truncated = True
                break
        if truncated:
            break
    if previous is not None and (not track or track[-1] != previous):
        track.append(previous)
    while track and track[-1] is None:
        track.pop()
    return track, stride > 1, truncated


def prepare_trajectory_map(directory, individual_count, seed, progress_callback=None):
    if (isinstance(individual_count, bool) or not isinstance(individual_count, Integral)
            or not 1 <= individual_count <= MAX_INDIVIDUALS):
        raise ValueError(f"Choose between 1 and {MAX_INDIVIDUALS} distinct individuals.")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or not 0 <= seed <= 2_147_483_647:
        raise ValueError("Random seed must be an integer between 0 and 2147483647.")
    rng = random.Random(int(seed))
    indexed = _sample_numeric_files(directory, individual_count, rng, progress_callback)
    if indexed is None:
        inspection = inspect_results_directory(directory, progress_callback=progress_callback)
        groups = defaultdict(list)
        warnings = [f"{issue.path.name}: {issue.message}" for issue in inspection.issues]
        for metadata in inspection.files:
            identifier = normalize_stranding_identifier(metadata.provenance.stranding_identifier)
            if identifier:
                groups[identifier].append(metadata)
        available = len(groups)
        selected = rng.sample(sorted(groups), min(individual_count, available))
    else:
        groups, warnings, available = indexed
        selected = list(groups)
        provenance = [groups[identifier][0].provenance for identifier in selected]
        if len({item.observation_dataset for item in provenance}) > 1:
            raise ValueError("Selected trajectory files disagree on their embedded observation dataset.")
        if len({item.identifier_column for item in provenance}) > 1:
            raise ValueError("Selected trajectory files disagree on their embedded identifier column.")
    if individual_count > available:
        warnings.append(f"Requested {individual_count} individuals; only {available} candidate identifiers are available.")
    runs = []
    point_limit = min(1000, max(100, POINT_BUDGET // max(1, len(selected) * MAX_PARTICLES_PER_RUN)))
    for index, identifier in enumerate(selected):
        metadata = rng.choice(sorted(groups[identifier], key=lambda item: str(item.path)))
        provenance = metadata.provenance
        particle_indices = sorted(rng.sample(range(metadata.trajectory_count),
                                            min(MAX_PARTICLES_PER_RUN, metadata.trajectory_count)))
        simplified = len(particle_indices) < metadata.trajectory_count
        truncated = False
        tracks = []
        displayed_particles = []
        try:
            with Dataset(metadata.path) as dataset:
                for particle in particle_indices:
                    track, thinned, cut_short = _read_track(dataset, particle, metadata.time_count, point_limit)
                    simplified |= thinned
                    truncated |= cut_short
                    if track:
                        tracks.append(track)
                        displayed_particles.append(particle)
            if not tracks:
                warnings.append(f"{metadata.path.name}: no valid positions to plot.")
                continue
        except (OSError, RuntimeError, ValueError, IndexError) as exc:
            warnings.append(f"{metadata.path.name}: {exc}")
            continue
        if simplified:
            warnings.append(f"{identifier}: preview uses {len(tracks)} of {metadata.trajectory_count} particles; time points may be thinned. Original results are unchanged.")
        if truncated:
            warnings.append(f"{identifier}: highly fragmented trajectory preview was truncated to keep the map responsive.")
        runs.append({
            "identifier": identifier, "run_index": provenance.iteration_index,
            "taxon": provenance.taxon_label, "observed_at": provenance.observed_at.isoformat(),
            "simulation_start": provenance.simulation_start_time.isoformat(),
            "file": str(metadata.path.resolve()), "particle_count": metadata.trajectory_count,
            "displayed_particle_indices": displayed_particles, "tracks": tracks,
        })
        if progress_callback:
            progress_callback({"event": "map_progress", "completed": index + 1, "total": len(selected)})
    if not runs:
        raise ValueError("No valid positions were found in the selected runs. Check the results or choose another random seed.")
    return {"schema_version": 1, "seed": int(seed), "requested_individuals": int(individual_count),
            "available_individuals": available, "results_directory": str(Path(directory).resolve()),
            "available_individuals_are_candidates": indexed is not None,
            "selection_unit": "distinct normalized stranding identifier; one random run each",
            "runs": runs, "warnings": warnings}
