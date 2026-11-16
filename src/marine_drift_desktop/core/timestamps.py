"""Normalize source timestamps to the UTC-naive values expected by OpenDrift."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def source_time_to_utc(value: datetime, timezone_name: str = "UTC") -> datetime:
    """Apply the selected source zone only when the timestamp has no offset."""
    if value.tzinfo is not None:
        return utc_naive(value)
    if timezone_name == "as_recorded":
        return value
    try:
        source_zone = ZoneInfo(timezone_name or "UTC")
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown input time zone `{timezone_name}`.") from exc
    return utc_naive(value.replace(tzinfo=source_zone))
