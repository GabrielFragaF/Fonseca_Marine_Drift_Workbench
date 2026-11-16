from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
import math
import re
from typing import Any

from ..domain.models import CanonicalObservation, ColumnMapping, WindDriftSettings
from .duration import ThermalDurationProfile
from .windage import wind_drift_factor_for_record
from .timestamps import source_time_to_utc

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
DATE_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
)
TIME_FORMATS = ("%H:%M:%S", "%H:%M")


def canonicalize_observation(
    raw_row: Mapping[str, Any],
    column_mapping: ColumnMapping,
    duration_profile: ThermalDurationProfile,
    wind_drift_settings: WindDriftSettings | None = None,
    coordinate_format: str = "decimal_degrees",
    duration_column: str = "",
    fixed_duration_days: int | None = None,
    decomposition_value_map: Mapping[str, int] | None = None,
) -> CanonicalObservation:
    stranding_identifier = _coerce_text(
        _get_value(raw_row, column_mapping.stranding_identifier, "stranding identifier"),
        "stranding identifier",
    )
    taxon_label = _coerce_text(
        _get_value(raw_row, column_mapping.taxon_label, "taxon label"),
        "taxon label",
    )
    raw_decomposition = _get_value(
        raw_row, column_mapping.decomposition_code, "decomposition code"
    )
    if decomposition_value_map:
        label = _coerce_text(raw_decomposition, "decomposition state")
        try:
            decomposition_code = int(decomposition_value_map[label])
        except KeyError as exc:
            raise ValueError(
                f"Decomposition state `{label}` is not mapped in the duration profile."
            ) from exc
    else:
        decomposition_code = _coerce_int(raw_decomposition, "decomposition code")
    if duration_column or fixed_duration_days is not None:
        sea_surface_temperature = None
    else:
        sea_surface_temperature = _coerce_optional_float(
            _get_value(
                raw_row,
                column_mapping.sea_surface_temperature,
                "sea surface temperature",
            )
        )
    wind_drift_factor = wind_drift_factor_for_record(
        dict(raw_row),
        column_mapping.wind_drift_factor,
        wind_drift_settings or WindDriftSettings(),
    )
    longitude = _coerce_coordinate(
        _get_value(raw_row, column_mapping.longitude, "longitude"),
        "longitude",
        coordinate_format,
    )
    latitude = _coerce_coordinate(
        _get_value(raw_row, column_mapping.latitude, "latitude"),
        "latitude",
        coordinate_format,
    )
    if column_mapping.datetime_mode == "combined":
        observed_at = _parse_combined_datetime(
            _get_value(
                raw_row,
                column_mapping.observed_datetime,
                "observed datetime",
            ),
            column_mapping.input_timezone,
        )
    elif column_mapping.datetime_mode == "separate":
        observed_at = _combine_date_and_time(
            _get_value(raw_row, column_mapping.observed_date, "observed date"),
            _get_value(raw_row, column_mapping.observed_time, "observed time"),
            column_mapping.input_timezone,
        )
    else:
        raise ValueError(
            "Unsupported observation datetime mapping mode "
            f"`{column_mapping.datetime_mode}`."
        )

    if fixed_duration_days is not None:
        if fixed_duration_days < 1:
            raise ValueError("Fixed drift duration must be at least 1 day.")
        reverse_drift_duration_days = fixed_duration_days
    elif duration_column:
        reverse_drift_duration_days = _coerce_int(
            _get_value(raw_row, duration_column, "reverse-drift duration"),
            "reverse-drift duration",
        )
    else:
        reverse_drift_duration_days = duration_profile.duration_for(
            decomposition_code=decomposition_code,
            sea_surface_temperature=sea_surface_temperature,
        )

    return CanonicalObservation(
        stranding_identifier=stranding_identifier,
        taxon_label=taxon_label,
        decomposition_code=decomposition_code,
        sea_surface_temperature=sea_surface_temperature,
        wind_drift_factor=wind_drift_factor,
        longitude=longitude,
        latitude=latitude,
        observed_at=observed_at,
        reverse_drift_duration_days=reverse_drift_duration_days,
    )


def _get_value(raw_row: Mapping[str, Any], column_name: str, label: str) -> Any:
    try:
        return raw_row[column_name]
    except Exception as exc:
        raise KeyError(f"Column `{column_name}` for {label} was not found in the dataset row.") from exc


def _coerce_text(value: Any, label: str) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        raise ValueError(f"{label.capitalize()} cannot be empty.")
    return text


def _coerce_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label.capitalize()} must be an integer.") from exc


def _coerce_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label.capitalize()} must be numeric.") from exc


def _coerce_coordinate(value: Any, label: str, coordinate_format: str) -> float:
    if coordinate_format == "decimal_degrees":
        return _coerce_float(value, label)
    if coordinate_format != "degrees_minutes_seconds":
        raise ValueError(f"Unsupported coordinate format `{coordinate_format}`.")

    text = str(value).strip()
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not matches:
        raise ValueError(f"{label.capitalize()} must use degrees, minutes, seconds values.")

    values = [float(match) for match in matches]
    if len(values) == 1:
        return values[0]
    if len(values) > 3:
        raise ValueError(f"{label.capitalize()} has too many coordinate components.")

    sign = -1.0 if values[0] < 0 or any(marker in text.upper() for marker in ("S", "W")) else 1.0
    degrees = abs(values[0])
    minutes = values[1]
    seconds = values[2] if len(values) == 3 else 0.0
    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"{label.capitalize()} minutes and seconds must be below 60.")
    return sign * (degrees + minutes / 60.0 + seconds / 3600.0)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    text = str(value).strip().lower()
    if text == "nan":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Sea surface temperature must be numeric when provided.") from exc


def _combine_date_and_time(date_value: Any, time_value: Any, timezone_name: str = "UTC") -> datetime:
    date_time_value = _as_python_datetime(date_value)
    if date_time_value is not None and _is_time_blank(time_value):
        return source_time_to_utc(date_time_value, timezone_name)

    if _is_time_blank(time_value):
        text = str(date_value).strip()
        try:
            return source_time_to_utc(datetime.fromisoformat(text.replace("Z", "+00:00")), timezone_name)
        except ValueError:
            pass
        for fmt in DATE_TIME_FORMATS:
            try:
                return source_time_to_utc(datetime.strptime(text, fmt), timezone_name)
            except ValueError:
                continue

    parsed_date = _parse_date(date_value)
    parsed_time = _parse_time(time_value)
    return source_time_to_utc(datetime.combine(parsed_date, parsed_time), timezone_name)


def _parse_combined_datetime(value: Any, timezone_name: str = "UTC") -> datetime:
    date_time_value = _as_python_datetime(value)
    if date_time_value is not None:
        return source_time_to_utc(date_time_value, timezone_name)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric_value = float(value)
        if math.isfinite(numeric_value) and 1 <= numeric_value <= 2_958_465:
            try:
                return source_time_to_utc(
                    datetime(1899, 12, 30) + timedelta(days=numeric_value), timezone_name
                )
            except OverflowError:
                pass

    text = str(value).strip()
    try:
        return source_time_to_utc(datetime.fromisoformat(text.replace("Z", "+00:00")), timezone_name)
    except ValueError:
        pass
    for fmt in DATE_TIME_FORMATS:
        try:
            return source_time_to_utc(datetime.strptime(text, fmt), timezone_name)
        except ValueError:
            continue
    raise ValueError(
        "Observed datetime must be a datetime value, Excel datetime, or text such as "
        "YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM."
    )


def _parse_date(value: Any) -> date:
    date_time_value = _as_python_datetime(value)
    if date_time_value is not None:
        return date_time_value.date()
    try:
        missing = bool(value != value)
    except (TypeError, ValueError):
        missing = False
    if missing:
        raise ValueError(
            "Observed date must be a date value, Excel date, or text such as "
            "YYYY-MM-DD, DD/MM/YYYY, or DD/MM/YYYY HH:MM."
        )
    if isinstance(value, date):
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric_value = float(value)
        if math.isfinite(numeric_value) and 1 <= numeric_value <= 2_958_465:
            return (datetime(1899, 12, 30) + timedelta(days=numeric_value)).date()

    text = str(value).strip()
    for fmt in (*DATE_FORMATS, *DATE_TIME_FORMATS):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        "Observed date must be a date value, Excel date, or text such as "
        "YYYY-MM-DD, DD/MM/YYYY, or DD/MM/YYYY HH:MM."
    )


def _parse_time(value: Any) -> time:
    if isinstance(value, datetime):
        return value.timetz()
    if isinstance(value, time):
        return value

    text = str(value).strip()
    try:
        return time.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(
        "Observed time must be a time value or a string formatted like HH:MM or HH:MM:SS."
    )


def _is_time_blank(value: Any) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _as_python_datetime(value: Any) -> datetime | None:
    # pandas uses NaT for blank Excel cells. It passes datetime checks but can
    # produce year 1 when combined with a separate time value.
    try:
        if bool(value != value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, datetime):
        return value
    converter = getattr(value, "to_pydatetime", None)
    if callable(converter):
        converted = converter()
        if isinstance(converted, datetime):
            return converted
    return None
