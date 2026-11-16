from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import xarray as xr
from xarray.coding.times import decode_cf_datetime

from ..domain.models import SpatialExtent


@dataclass(frozen=True, slots=True)
class EnvironmentalDiagnostic:
    level: Literal["error", "warning", "info"]
    code: str
    message: str


@dataclass(slots=True)
class EnvironmentalReaderInspection:
    path: Path
    variables: list[str] = field(default_factory=list)
    standard_names: dict[str, str] = field(default_factory=dict)
    dimensions: dict[str, int] = field(default_factory=dict)
    coordinate_variables: list[str] = field(default_factory=list)
    recognized_opendrift_variables: list[str] = field(default_factory=list)
    compatibility_message: str = "Not tested"
    extent: SpatialExtent | None = None
    longitude_name: str = ""
    latitude_name: str = ""
    longitude_convention: str = "unknown"
    coverage_warning: str = ""
    variable_units: dict[str, str] = field(default_factory=dict)
    variable_dimensions: dict[str, tuple[str, ...]] = field(default_factory=dict)
    time_name: str = ""
    time_start: str = ""
    time_end: str = ""
    time_count: int = 0
    temporal_resolution_seconds: float | None = None
    time_is_monotonic: bool | None = None
    time_is_regular: bool | None = None
    grid_type: str = "unknown"
    longitude_resolution: float | None = None
    latitude_resolution: float | None = None
    crs: str = ""
    diagnostics: list[EnvironmentalDiagnostic] = field(default_factory=list)


def inspect_environment_reader(path: Path) -> EnvironmentalReaderInspection:
    """Inspect NetCDF metadata and OpenDrift recognition without running a model."""

    if not path.exists() or not path.is_file():
        raise ValueError(f"Environmental reader file does not exist: {path}")

    with xr.open_dataset(path, decode_times=False) as dataset:
        variables = [str(name) for name in dataset.variables]
        standard_names = {
            str(name): str(variable.attrs["standard_name"])
            for name, variable in dataset.variables.items()
            if "standard_name" in variable.attrs
        }
        coordinate_variables = [
            str(name)
            for name, variable in dataset.variables.items()
            if str(variable.attrs.get("standard_name", ""))
            in {"longitude", "latitude", "time", "depth"}
            or str(variable.attrs.get("axis", "")) in {"X", "Y", "Z", "T"}
            or str(name).lower() in {"lon", "longitude", "lat", "latitude", "time"}
        ]
        dimensions = {str(name): int(size) for name, size in dataset.sizes.items()}
        variable_units = {
            str(name): str(variable.attrs["units"])
            for name, variable in dataset.variables.items()
            if "units" in variable.attrs
        }
        variable_dimensions = {
            str(name): tuple(str(dimension) for dimension in variable.dims)
            for name, variable in dataset.variables.items()
        }
        (
            extent,
            longitude_name,
            latitude_name,
            longitude_convention,
            coverage_warning,
        ) = _inspect_spatial_coverage(dataset)
        (
            time_name,
            time_start,
            time_end,
            time_count,
            temporal_resolution_seconds,
            time_is_monotonic,
            time_is_regular,
            temporal_diagnostics,
        ) = _inspect_temporal_coverage(dataset)
        grid_type, longitude_resolution, latitude_resolution = _inspect_grid(dataset)
        crs = _inspect_crs(dataset)

    diagnostics = list(temporal_diagnostics)
    if coverage_warning:
        diagnostics.append(
            EnvironmentalDiagnostic(
                "warning", "spatial_coverage_unavailable", coverage_warning
            )
        )

    inspection = EnvironmentalReaderInspection(
        path=path,
        variables=variables,
        standard_names=standard_names,
        dimensions=dimensions,
        coordinate_variables=coordinate_variables,
        extent=extent,
        longitude_name=longitude_name,
        latitude_name=latitude_name,
        longitude_convention=longitude_convention,
        coverage_warning=coverage_warning,
        variable_units=variable_units,
        variable_dimensions=variable_dimensions,
        time_name=time_name,
        time_start=time_start,
        time_end=time_end,
        time_count=time_count,
        temporal_resolution_seconds=temporal_resolution_seconds,
        time_is_monotonic=time_is_monotonic,
        time_is_regular=time_is_regular,
        grid_type=grid_type,
        longitude_resolution=longitude_resolution,
        latitude_resolution=latitude_resolution,
        crs=crs,
        diagnostics=diagnostics,
    )
    try:
        from opendrift.readers.reader_netCDF_CF_generic import Reader

        reader = Reader(str(path))
        inspection.recognized_opendrift_variables = sorted(reader.variables)
        inspection.compatibility_message = "OpenDrift reader initialized successfully."
    except (ImportError, ValueError, OSError) as exc:
        inspection.compatibility_message = f"OpenDrift compatibility warning: {exc}"
        inspection.diagnostics.append(
            EnvironmentalDiagnostic(
                "warning", "opendrift_compatibility", str(exc)
            )
        )
    return inspection


def resolve_environment_extent(
    paths: list[Path], buffer_degrees: float = 0.0
) -> SpatialExtent:
    if not paths:
        raise ValueError("Add at least one environmental reader to detect coverage.")
    extents: list[SpatialExtent] = []
    for path in dict.fromkeys(paths):
        inspection = inspect_environment_reader(path)
        if inspection.extent is None:
            detail = inspection.coverage_warning or "spatial coordinates were not detected"
            raise ValueError(f"Could not detect coverage for `{path.name}`: {detail}.")
        extents.append(inspection.extent)
    return intersect_extents(extents, buffer_degrees)


def intersect_extents(
    extents: list[SpatialExtent], buffer_degrees: float = 0.0
) -> SpatialExtent:
    if not extents:
        raise ValueError("No environmental coverages were supplied.")
    if buffer_degrees < 0:
        raise ValueError("Environmental coverage buffer cannot be negative.")

    minimum_longitude = max(extent.min_longitude for extent in extents)
    maximum_longitude = min(extent.max_longitude for extent in extents)
    minimum_latitude = max(extent.min_latitude for extent in extents)
    maximum_latitude = min(extent.max_latitude for extent in extents)
    if minimum_longitude >= maximum_longitude or minimum_latitude >= maximum_latitude:
        raise ValueError("Environmental reader coverages do not overlap.")

    return SpatialExtent(
        min_longitude=max(-180.0, minimum_longitude - buffer_degrees),
        max_longitude=min(180.0, maximum_longitude + buffer_degrees),
        min_latitude=max(-90.0, minimum_latitude - buffer_degrees),
        max_latitude=min(90.0, maximum_latitude + buffer_degrees),
    )


def _inspect_spatial_coverage(
    dataset: xr.Dataset,
) -> tuple[SpatialExtent | None, str, str, str, str]:
    longitude_name = _find_coordinate_name(dataset, "longitude", "X", {"lon", "longitude"})
    latitude_name = _find_coordinate_name(dataset, "latitude", "Y", {"lat", "latitude"})
    if not longitude_name or not latitude_name:
        return None, longitude_name, latitude_name, "unknown", "longitude or latitude coordinate is missing"

    longitude = dataset[longitude_name]
    latitude = dataset[latitude_name]
    if longitude.ndim != 1 or latitude.ndim != 1:
        return None, longitude_name, latitude_name, "unknown", "curvilinear coordinates require manual extent"

    longitude_values = np.asarray(longitude.values, dtype=float)
    latitude_values = np.asarray(latitude.values, dtype=float)
    longitude_values = longitude_values[np.isfinite(longitude_values)]
    latitude_values = latitude_values[np.isfinite(latitude_values)]
    if longitude_values.size == 0 or latitude_values.size == 0:
        return None, longitude_name, latitude_name, "unknown", "coordinate values are empty"

    convention = "-180_to_180"
    if float(longitude_values.min()) >= 0 and float(longitude_values.max()) > 180:
        convention = "0_to_360"
        normalized = ((longitude_values + 180.0) % 360.0) - 180.0
        if float(normalized.max() - normalized.min()) > 180:
            return None, longitude_name, latitude_name, convention, "antimeridian coverage requires manual extent"
        longitude_values = normalized

    extent = SpatialExtent(
        min_longitude=float(longitude_values.min()),
        max_longitude=float(longitude_values.max()),
        min_latitude=float(latitude_values.min()),
        max_latitude=float(latitude_values.max()),
    )
    if not extent.is_valid():
        return None, longitude_name, latitude_name, convention, "coordinate coverage has no area"
    return extent, longitude_name, latitude_name, convention, ""


def _find_coordinate_name(
    dataset: xr.Dataset,
    standard_name: str,
    axis: str,
    common_names: set[str],
) -> str:
    for name, variable in dataset.variables.items():
        if str(variable.attrs.get("standard_name", "")).lower() == standard_name:
            return str(name)
        if str(variable.attrs.get("axis", "")).upper() == axis:
            return str(name)
    for name in dataset.variables:
        if str(name).lower() in common_names:
            return str(name)
    return ""


def _inspect_temporal_coverage(
    dataset: xr.Dataset,
) -> tuple[str, str, str, int, float | None, bool | None, bool | None, list[EnvironmentalDiagnostic]]:
    diagnostics: list[EnvironmentalDiagnostic] = []
    time_name = _find_coordinate_name(dataset, "time", "T", {"time"})
    if not time_name:
        diagnostics.append(
            EnvironmentalDiagnostic(
                "warning",
                "temporal_coordinate_missing",
                "No time coordinate was detected; temporal coverage cannot be evaluated.",
            )
        )
        return "", "", "", 0, None, None, None, diagnostics

    time = dataset[time_name]
    values = np.asarray(time.values).reshape(-1)
    count = int(values.size)
    units = str(time.attrs.get("units", "")).strip()
    if not units:
        diagnostics.append(
            EnvironmentalDiagnostic(
                "warning",
                "temporal_units_missing",
                "The time coordinate has no CF units, so its dates cannot be decoded.",
            )
        )
        return time_name, "", "", count, None, None, None, diagnostics

    try:
        decoded = decode_cf_datetime(
            values,
            units,
            calendar=str(time.attrs.get("calendar", "standard")),
        )
        seconds = _time_differences_seconds(decoded)
        monotonic = bool(np.all(seconds > 0)) if seconds.size else True
        regular = bool(np.allclose(seconds, seconds[0])) if seconds.size else True
        resolution = float(abs(seconds[0])) if seconds.size and regular else None
        if count == 1:
            diagnostics.append(
                EnvironmentalDiagnostic(
                    "info",
                    "single_time_step",
                    "The dataset contains one time step; temporal resolution is unavailable.",
                )
            )
        if not monotonic:
            diagnostics.append(
                EnvironmentalDiagnostic(
                    "warning",
                    "non_monotonic_time",
                    "Time coordinates are not strictly increasing.",
                )
            )
        if not regular:
            diagnostics.append(
                EnvironmentalDiagnostic(
                    "warning",
                    "irregular_time_step",
                    "Time-step intervals are not regular.",
                )
            )
        ordered = sorted(decoded)
        return (
            time_name,
            _time_to_iso(ordered[0]) if count else "",
            _time_to_iso(ordered[-1]) if count else "",
            count,
            resolution,
            monotonic,
            regular,
            diagnostics,
        )
    except (OverflowError, TypeError, ValueError) as exc:
        diagnostics.append(
            EnvironmentalDiagnostic(
                "warning",
                "temporal_decode_failed",
                f"Time coordinates could not be decoded: {exc}",
            )
        )
        return time_name, "", "", count, None, None, None, diagnostics


def _time_differences_seconds(values: np.ndarray) -> np.ndarray:
    if values.size < 2:
        return np.asarray([], dtype=float)
    if np.issubdtype(values.dtype, np.datetime64):
        return np.diff(values).astype("timedelta64[ns]").astype(np.int64) / 1e9
    differences = np.diff(values)
    return np.asarray(
        [difference.total_seconds() for difference in differences], dtype=float
    )


def _time_to_iso(value: object) -> str:
    if isinstance(value, np.datetime64):
        return np.datetime_as_string(value, unit="s")
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)


def _inspect_grid(dataset: xr.Dataset) -> tuple[str, float | None, float | None]:
    longitude_name = _find_coordinate_name(dataset, "longitude", "X", {"lon", "longitude"})
    latitude_name = _find_coordinate_name(dataset, "latitude", "Y", {"lat", "latitude"})
    if not longitude_name or not latitude_name:
        return "unknown", None, None
    longitude = dataset[longitude_name]
    latitude = dataset[latitude_name]
    if longitude.ndim == 2 or latitude.ndim == 2:
        return "curvilinear", None, None
    if longitude.ndim != 1 or latitude.ndim != 1:
        return "unknown", None, None
    return (
        "rectilinear",
        _coordinate_resolution(longitude.values),
        _coordinate_resolution(latitude.values),
    )


def _coordinate_resolution(values: object) -> float | None:
    numeric = np.asarray(values, dtype=float).reshape(-1)
    numeric = numeric[np.isfinite(numeric)]
    if numeric.size < 2:
        return None
    differences = np.abs(np.diff(numeric))
    differences = differences[differences > 0]
    return float(np.median(differences)) if differences.size else None


def _inspect_crs(dataset: xr.Dataset) -> str:
    candidates: list[xr.DataArray] = []
    for variable in dataset.variables.values():
        grid_mapping = str(variable.attrs.get("grid_mapping", "")).strip()
        if grid_mapping and grid_mapping in dataset.variables:
            candidates.append(dataset[grid_mapping])
    candidates.extend(
        variable
        for name, variable in dataset.variables.items()
        if str(name).lower() in {"crs", "spatial_ref"}
    )
    for variable in candidates:
        for attribute in ("spatial_ref", "crs_wkt", "epsg_code"):
            value = str(variable.attrs.get(attribute, "")).strip()
            if value:
                return value
    for attribute in ("spatial_ref", "crs_wkt", "epsg_code"):
        value = str(dataset.attrs.get(attribute, "")).strip()
        if value:
            return value
    return ""
