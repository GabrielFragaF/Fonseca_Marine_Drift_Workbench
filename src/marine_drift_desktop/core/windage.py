from __future__ import annotations

import math
from typing import Any

from ..domain.models import WindDriftSettings


def wind_drift_factor_for_record(
    raw_record: dict[str, Any],
    source_column: str,
    settings: WindDriftSettings,
) -> float:
    """Return the dimensionless wind fraction expected by OpenDrift."""

    if settings.mode == "none":
        return 0.0

    if settings.mode == "fixed":
        return _percent_to_fraction(settings.fixed_percent)

    if settings.mode == "measurement":
        measurement = _coerce_float(
            raw_record.get(settings.measurement_column),
            "specimen measurement",
        )
        return _measurement_to_fraction(measurement, settings)

    if settings.mode != "dataset":
        raise ValueError(f"Unsupported wind-drift mode `{settings.mode}`.")

    value = _coerce_float(raw_record.get(source_column), "wind drift factor")
    if settings.source_scale == "percent":
        return _percent_to_fraction(value)
    if settings.source_scale == "fraction":
        return _validate_fraction(value)
    raise ValueError(
        f"Choose a supported wind-drift source scale, not `{settings.source_scale}`."
    )


def _measurement_to_fraction(
    measurement: float,
    settings: WindDriftSettings,
) -> float:
    if not all(math.isfinite(value) for value in (
        measurement, settings.measurement_minimum, settings.measurement_maximum
    )):
        raise ValueError("Measurement and measurement limits must be finite.")
    if settings.measurement_maximum <= settings.measurement_minimum:
        raise ValueError("Measurement maximum must be greater than measurement minimum.")
    _validate_percent(settings.wind_drift_minimum_percent)
    _validate_percent(settings.wind_drift_maximum_percent)

    if settings.measurement_unit == "centimeters":
        measurement, minimum, maximum = (measurement / 100.0,
                                         settings.measurement_minimum / 100.0,
                                         settings.measurement_maximum / 100.0)
    elif settings.measurement_unit == "meters":
        minimum, maximum = settings.measurement_minimum, settings.measurement_maximum
    else:
        raise ValueError("Choose metres or centimetres for specimen measurements.")
    ratio = (measurement - minimum) / (
        maximum - minimum
    )
    if settings.outside_range_behavior == "clamp":
        ratio = min(1.0, max(0.0, ratio))

    percent = settings.wind_drift_minimum_percent + ratio * (
        settings.wind_drift_maximum_percent
        - settings.wind_drift_minimum_percent
    )
    return _percent_to_fraction(percent)


def _percent_to_fraction(percent: float) -> float:
    return _validate_percent(percent) / 100.0


def _validate_percent(percent: float) -> float:
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        raise ValueError("Wind drift percentage must be finite and between 0 and 100.")
    return percent


def _validate_fraction(fraction: float) -> float:
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("Wind drift factor must be finite and between 0 and 1.")
    return fraction


def _coerce_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label.capitalize()} must be numeric.") from exc
