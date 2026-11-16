from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from numbers import Integral, Real
from pathlib import Path

import pandas as pd

from .io import load_observation_table


_INTEGRAL_TEXT = re.compile(r"([+-]?\d+)\.0+")


class SourceObservationLookup(dict[str, dict[str, object]]):
    """Normalized source rows with their original column names for blank joins."""

    def __init__(
        self,
        rows: Mapping[str, dict[str, object]],
        columns: Iterable[str],
        candidates: Mapping[str, tuple[dict[str, object], ...]] | None = None,
    ) -> None:
        super().__init__(rows)
        self.columns = tuple(columns)
        self.candidates = dict(candidates or {key: (value,) for key, value in rows.items()})


def normalize_stranding_identifier(value: object) -> str:
    """Return a stable text identifier while removing spreadsheet ``.0`` noise."""
    if value is None:
        raise ValueError("Stranding identifier must not be blank.")
    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        raise ValueError("Stranding identifier must not be blank.")
    if isinstance(value, Real) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            raise ValueError("Stranding identifier must not be blank.")
        if isinstance(value, Integral) or float(value).is_integer():
            return str(int(value))

    text = str(value).strip()
    if not text:
        raise ValueError("Stranding identifier must not be blank.")
    integral_match = _INTEGRAL_TEXT.fullmatch(text)
    return integral_match.group(1) if integral_match else text


def load_source_observation_lookup(
    path: Path | str,
    identifier_column: str,
) -> SourceObservationLookup:
    """Load one complete observation row per normalized stranding identifier."""
    table = load_observation_table(Path(path))
    if identifier_column not in table.columns:
        raise ValueError(
            f"Source observation data is missing identifier column `{identifier_column}`."
        )

    candidates: dict[str, list[dict[str, object]]] = {}
    for record in table.to_dict(orient="records"):
        identifier = normalize_stranding_identifier(record[identifier_column])
        candidates.setdefault(identifier, []).append(record)

    rows = {identifier: records[0] for identifier, records in candidates.items()}
    return SourceObservationLookup(
        rows,
        (str(column) for column in table.columns),
        {identifier: tuple(records) for identifier, records in candidates.items()},
    )


def select_source_observation_row(
    lookup: SourceObservationLookup,
    identifier: str,
    observed_at: datetime,
) -> dict[str, object] | None:
    """Resolve a source row using identifier and the provenance observation time."""
    candidates = lookup.candidates.get(identifier, ())
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if all(candidate == candidates[0] for candidate in candidates[1:]):
        # Identical source rows carry no distinct event information. Keeping one
        # preserves exports without conflating genuinely different strandings.
        return candidates[0]

    scored = [
        (row, _observation_time_match_score(row, observed_at))
        for row in candidates
    ]
    best_score = max(score for _, score in scored)
    matches = [row for row, score in scored if score == best_score and score > 0]
    if len(matches) == 1:
        return matches[0]
    if best_score == 0:
        raise ValueError(
            f"duplicate normalized stranding identifier `{identifier}` cannot be "
            "resolved because none of its source records matches the trajectory "
            "observation time."
        )
    raise ValueError(
        f"duplicate normalized stranding identifier `{identifier}` remains "
        "ambiguous after matching the trajectory observation time."
    )


def _observation_time_match_score(row: Mapping[str, object], observed_at: datetime) -> int:
    from .timestamps import utc_naive
    observed_at = utc_naive(observed_at)
    date_matches = False
    exact_matches = False
    row_dates: list[date] = []
    row_times: list[time] = []
    for value in row.values():
        parsed = _parse_source_time(value)
        if parsed is None:
            continue
        if isinstance(parsed, datetime):
            if parsed.date() == observed_at.date():
                date_matches = True
                if parsed.replace(second=0, microsecond=0) == observed_at.replace(second=0, microsecond=0):
                    exact_matches = True
        elif isinstance(parsed, date):
            row_dates.append(parsed)
            if parsed == observed_at.date():
                date_matches = True
        else:
            row_times.append(parsed)

    if any(
        utc_naive(datetime.combine(value_date, value_time)).replace(second=0, microsecond=0)
        == observed_at.replace(second=0, microsecond=0)
        for value_date in row_dates
        for value_time in row_times
    ):
        exact_matches = True
    return 2 if exact_matches else 1 if date_matches else 0


def _parse_source_time(value: object) -> datetime | date | time | None:
    from .timestamps import utc_naive
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        return utc_naive(value)
    if isinstance(value, date):
        return value
    if isinstance(value, time):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?", text):
        return time.fromisoformat(text.replace("Z", "+00:00"))
    if not re.search(r"[-/]", text):
        return None
    parsed = pd.to_datetime(
        text,
        errors="coerce",
        dayfirst=not bool(re.match(r"\d{4}[-/]", text)),
    )
    if pd.isna(parsed):
        return None
    timestamp = utc_naive(pd.Timestamp(parsed).to_pydatetime())
    return timestamp if re.search(r"\d{1,2}:\d{2}", text) else timestamp.date()
