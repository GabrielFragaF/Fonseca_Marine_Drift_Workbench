from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from ..domain.models import EnvironmentalReaderConfig, FallbackValues, SpatialExtent
from .environment import EnvironmentalReaderInspection
from .timestamps import utc_naive

ForcingLevel = Literal["success", "error", "warning", "info"]


@dataclass(frozen=True, slots=True)
class ForcingCheck:
    key: str
    level: ForcingLevel
    title: str
    detail: str
    affected_paths: tuple[Path, ...] = ()
    blocks_run: bool = False


@dataclass(frozen=True, slots=True)
class ForcingReadiness:
    checks: tuple[ForcingCheck, ...] = ()

    @property
    def is_ready(self) -> bool:
        return not any(check.blocks_run for check in self.checks)

    def check(self, key: str) -> ForcingCheck:
        return next(check for check in self.checks if check.key == key)


def evaluate_forcing_readiness(
    readers: list[EnvironmentalReaderConfig],
    inspections: list[EnvironmentalReaderInspection],
    *,
    study_extent: SpatialExtent,
    required_start: datetime | None = None,
    required_end: datetime | None = None,
    require_wind: bool = False,
    fallback_values: FallbackValues | None = None,
) -> ForcingReadiness:
    """Evaluate active reader metadata without loading environmental data arrays."""
    checks: list[ForcingCheck] = []
    required_start = utc_naive(required_start) if required_start else None
    required_end = utc_naive(required_end) if required_end else None
    if require_wind:
        wind = [item for item in inspections
                if {"x_wind", "y_wind"}.issubset(item.recognized_opendrift_variables)]
        checks.append(ForcingCheck(
            "required_wind", "success" if wind else "error", "Wind for active windage",
            "Both horizontal wind components are available." if wind else
            "Active windage requires a dataset exposing both x_wind and y_wind.",
            tuple(item.path for item in wind), blocks_run=not wind,
        ))
        if wind:
            coverage_checks = _temporal_checks(wind, required_start=required_start, required_end=required_end)
            coverage_checks.append(_spatial_check(wind, study_extent))
            for check in coverage_checks:
                fallback_enabled = bool(
                    fallback_values is not None and fallback_values.wind_enabled
                )
                blocked = check.blocks_run and not fallback_enabled
                level = (
                    "warning"
                    if fallback_enabled and check.level == "error"
                    else check.level
                )
                checks.append(ForcingCheck(
                    "wind_" + check.key, level,
                    "Wind " + check.title.lower(),
                    check.detail.replace("Current", "Wind").replace("current", "wind"),
                    check.affected_paths, blocks_run=blocked,
                ))
    inspection_by_path = {_path_key(item.path): item for item in inspections}
    current_readers = [reader for reader in readers if _has_role(reader, "currents")]
    current_paths = tuple(reader.path for reader in current_readers)
    if not current_readers:
        checks.append(
            ForcingCheck(
                "required_currents",
                "error",
                "Required currents",
                "Add at least one dataset assigned to Ocean circulation.",
                blocks_run=True,
            )
        )
        checks.extend(_optional_and_unused_checks(readers))
        return ForcingReadiness(tuple(checks))

    checks.append(
        ForcingCheck(
            "required_currents",
            "success",
            "Required currents",
            f"{len(current_readers)} ocean-circulation dataset(s) are assigned.",
            current_paths,
        )
    )
    current_inspections = [
        inspection_by_path[_path_key(reader.path)]
        for reader in current_readers
        if _path_key(reader.path) in inspection_by_path
    ]
    checks.extend(
        _temporal_checks(
            current_inspections,
            required_start=required_start,
            required_end=required_end,
        )
    )
    checks.append(_spatial_check(current_inspections, study_extent))
    checks.append(_compatibility_check(current_readers, current_inspections))
    checks.extend(_optional_and_unused_checks(readers))
    return ForcingReadiness(tuple(checks))


def _temporal_checks(
    inspections: list[EnvironmentalReaderInspection],
    *,
    required_start: datetime | None,
    required_end: datetime | None,
) -> list[ForcingCheck]:
    intervals: list[tuple[datetime, datetime, float | None, Path]] = []
    missing: list[Path] = []
    for inspection in inspections:
        start = _parse_time(inspection.time_start)
        end = _parse_time(inspection.time_end)
        if start is None or end is None or end < start:
            missing.append(inspection.path)
            continue
        intervals.append(
            (start, end, inspection.temporal_resolution_seconds, inspection.path)
        )
    checks: list[ForcingCheck] = []
    if not intervals:
        checks.append(
            ForcingCheck(
                "temporal_coverage",
                "warning",
                "Temporal coverage",
                "Current datasets do not expose usable temporal bounds.",
                tuple(missing),
            )
        )
        return checks

    intervals.sort(key=lambda item: item[0])
    gap_paths: list[Path] = []
    overlap_paths: list[Path] = []
    merged_start, merged_end, merged_step, merged_path = intervals[0]
    merged: list[tuple[datetime, datetime]] = []
    for start, end, step, path in intervals[1:]:
        tolerance = max(value for value in (merged_step, step, 0.0) if value is not None)
        separation = (start - merged_end).total_seconds()
        if start < merged_end:
            overlap_paths.extend([merged_path, path])
        if separation > tolerance * 1.5:
            gap_paths.extend([merged_path, path])
            merged.append((merged_start, merged_end))
            merged_start, merged_end, merged_step, merged_path = start, end, step, path
        else:
            if end > merged_end:
                merged_end = end
            merged_step = max(value for value in (merged_step, step, 0.0) if value is not None)
            merged_path = path
    merged.append((merged_start, merged_end))

    covers_required = True
    if required_start is not None and required_end is not None:
        covers_required = any(
            start <= required_start and end >= required_end for start, end in merged
        )
    if gap_paths:
        checks.append(
            ForcingCheck(
                "temporal_gap",
                "warning",
                "Temporal gaps",
                "A gap larger than the expected timestep exists between current datasets.",
                tuple(dict.fromkeys(gap_paths)),
            )
        )
    if overlap_paths:
        checks.append(
            ForcingCheck(
                "temporal_overlap",
                "info",
                "Temporal overlap",
                "Current datasets contain overlapping timestamps; source priority may apply.",
                tuple(dict.fromkeys(overlap_paths)),
            )
        )
    if missing:
        level: ForcingLevel = "warning"
        detail = f"{len(missing)} current dataset(s) have unavailable time metadata."
    elif not covers_required:
        level = "warning"
        detail = "Current datasets do not fully cover the required reverse-drift window."
    elif gap_paths:
        level = "warning"
        detail = "The overall time range is present, but internal gaps require review."
    else:
        level = "success"
        detail = (
            f"Current data cover {merged[0][0].isoformat()} to "
            f"{merged[-1][1].isoformat()}."
        )
    checks.insert(
        0,
        ForcingCheck(
            "temporal_coverage",
            level,
            "Temporal coverage",
            detail,
            tuple(item.path for item in inspections),
        ),
    )
    return checks


def _spatial_check(
    inspections: list[EnvironmentalReaderInspection], study: SpatialExtent
) -> ForcingCheck:
    with_extent = [item for item in inspections if item.extent is not None]
    paths = tuple(item.path for item in inspections)
    if not with_extent:
        return ForcingCheck(
            "spatial_coverage",
            "warning",
            "Spatial coverage",
            "Current datasets do not expose a usable spatial extent.",
            paths,
        )
    if any(_contains(item.extent, study) for item in with_extent):
        return ForcingCheck(
            "spatial_coverage",
            "success",
            "Spatial coverage",
            "At least one current dataset fully covers the configured study extent.",
            tuple(item.path for item in with_extent),
        )
    if any(_intersects(item.extent, study) for item in with_extent):
        return ForcingCheck(
            "spatial_coverage",
            "warning",
            "Spatial coverage",
            "Current data overlap only part of the configured study extent.",
            tuple(item.path for item in with_extent),
        )
    return ForcingCheck(
        "spatial_coverage",
        "error",
        "Spatial coverage",
        "Current data do not overlap the configured study extent.",
        tuple(item.path for item in with_extent),
        blocks_run=True,
    )


def _compatibility_check(
    readers: list[EnvironmentalReaderConfig],
    inspections: list[EnvironmentalReaderInspection],
) -> ForcingCheck:
    inspections_by_path = {_path_key(inspection.path): inspection for inspection in inspections}
    required_components = {
        "x_sea_water_velocity",
        "y_sea_water_velocity",
    }
    incompatible_paths: list[Path] = []
    warnings = sum(
        diagnostic.level == "warning"
        for inspection in inspections
        for diagnostic in inspection.diagnostics
    )
    for reader in readers:
        inspection = inspections_by_path.get(_path_key(reader.path))
        recognized = (
            set(inspection.recognized_opendrift_variables)
            if inspection is not None
            else set()
        )
        if not required_components.issubset(recognized):
            incompatible_paths.append(reader.path)
    if incompatible_paths:
        level: ForcingLevel = "error"
        detail = (
            "Each Ocean circulation reader must independently expose both "
            "horizontal current components."
        )
    elif not warnings:
        level: ForcingLevel = "success"
        detail = "OpenDrift recognizes both horizontal current components."
    else:
        level = "warning"
        detail = "Review OpenDrift variable recognition and reader diagnostics."
    return ForcingCheck(
        "opendrift_compatibility",
        level,
        "OpenDrift compatibility",
        detail,
        tuple(incompatible_paths or [reader.path for reader in readers]),
        blocks_run=bool(incompatible_paths),
    )


def _optional_and_unused_checks(
    readers: list[EnvironmentalReaderConfig],
) -> list[ForcingCheck]:
    optional_labels = [
        label
        for role, label in (
            ("atmosphere", "Atmospheric forcing"),
            ("waves", "Waves"),
            ("temperature", "Temperature & hydrography"),
            ("bathymetry", "Bathymetry"),
            ("biogeochemistry", "Biogeochemistry"),
        )
        if any(_has_role(reader, role) for reader in readers)
    ]
    unused = [
        reader
        for reader in readers
        if not reader.roles or all(_canonical_role(role) == "other" for role in reader.roles)
    ]
    optional_detail = (
        "Available optional roles: " + ", ".join(optional_labels) + "."
        if optional_labels
        else "No optional wind, wave, temperature, bathymetry, or biogeochemistry roles are assigned."
    )
    return [
        ForcingCheck(
            "optional_forcing",
            "info",
            "Optional forcing",
            optional_detail,
        ),
        ForcingCheck(
            "unused_datasets",
            "info" if not unused else "warning",
            "Unused datasets",
            f"{len(unused)} dataset(s) are unassigned or marked Other / custom.",
            tuple(reader.path for reader in unused),
        ),
    ]


def _has_role(reader: EnvironmentalReaderConfig, canonical: str) -> bool:
    return any(_canonical_role(role) == canonical for role in reader.roles)


def _canonical_role(role: str) -> str:
    normalized = role.strip().casefold()
    aliases = {
        "currents": "currents",
        "ocean circulation": "currents",
        "wind": "atmosphere",
        "atmospheric forcing": "atmosphere",
        "waves": "waves",
        "stokes drift": "waves",
        "sea-surface temperature": "temperature",
        "temperature & hydrography": "temperature",
        "bathymetry": "bathymetry",
        "biogeochemistry": "biogeochemistry",
        "other / custom": "other",
    }
    return aliases.get(normalized, normalized)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return utc_naive(parsed)


def _contains(container: SpatialExtent | None, target: SpatialExtent) -> bool:
    return bool(
        container is not None
        and container.min_longitude <= target.min_longitude
        and container.max_longitude >= target.max_longitude
        and container.min_latitude <= target.min_latitude
        and container.max_latitude >= target.max_latitude
    )


def _intersects(first: SpatialExtent | None, second: SpatialExtent) -> bool:
    return bool(
        first is not None
        and first.min_longitude < second.max_longitude
        and first.max_longitude > second.min_longitude
        and first.min_latitude < second.max_latitude
        and first.max_latitude > second.min_latitude
    )


def _path_key(path: Path) -> str:
    return str(path.resolve()).casefold()
