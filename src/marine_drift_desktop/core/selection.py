from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from ..domain.models import FilterCondition, ObservationSelectionSettings

SUPPORTED_FILTER_OPERATORS = frozenset({
    "equals",
    "not_equals",
    "<",
    "<=",
    ">",
    ">=",
    "contains",
    "is_blank",
    "is_not_blank",
    "in_values",
})


@dataclass(frozen=True, slots=True)
class SelectionResult:
    records: list[dict[str, Any]]
    source_count: int
    selected_count: int


def select_observation_records(
    records: list[dict[str, Any]],
    settings: ObservationSelectionSettings,
) -> SelectionResult:
    source_records = list(records)
    if settings.mode == "all":
        selected = source_records
    elif settings.mode == "random":
        if not 1 <= settings.sample_size <= len(source_records):
            raise ValueError(
                "Random sample size must be between 1 and "
                f"{len(source_records)}."
            )
        selected = random.Random(settings.random_seed).sample(
            source_records, settings.sample_size
        )
    elif settings.mode == "filter":
        if not settings.conditions:
            raise ValueError("Add at least one condition for filtered observations.")
        selected = [
            record
            for record in source_records
            if matches_conditions(record, settings.conditions)
        ]
    else:
        raise ValueError(f"Unsupported observation selection mode `{settings.mode}`.")

    return SelectionResult(selected, len(source_records), len(selected))


def matches_conditions(
    record: dict[str, Any], conditions: list[FilterCondition]
) -> bool:
    result: bool | None = None
    for condition in conditions:
        matched = _matches_condition(record, condition)
        if result is None:
            result = matched
        elif condition.connector == "and":
            result = result and matched
        elif condition.connector == "or":
            result = result or matched
        else:
            raise ValueError(f"Unsupported filter connector `{condition.connector}`.")
    return bool(result)


def _matches_condition(record: dict[str, Any], condition: FilterCondition) -> bool:
    if condition.operator not in SUPPORTED_FILTER_OPERATORS:
        raise ValueError(f"Unsupported filter operator `{condition.operator}`.")
    if condition.column not in record:
        raise ValueError(f"Filter column `{condition.column}` was not found.")

    actual = record[condition.column]
    if condition.operator == "is_blank":
        return _is_blank(actual)
    if condition.operator == "is_not_blank":
        return not _is_blank(actual)
    if condition.operator == "contains":
        return _text(condition.value) in _text(actual)
    if condition.operator == "in_values":
        return any(_equal(actual, value) for value in condition.values)
    if condition.operator == "equals":
        return _equal(actual, condition.value)
    if condition.operator == "not_equals":
        return not _equal(actual, condition.value)

    left = _number(actual, condition.column)
    right = _number(condition.value, condition.column)
    return {
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
    }[condition.operator]


def _equal(left: Any, right: Any) -> bool:
    try:
        return float(left) == float(right)
    except (TypeError, ValueError):
        return _text(left) == _text(right)


def _number(value: Any, column: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Filter comparison for column `{column}` requires numeric values."
        ) from exc
    if not math.isfinite(number):
        raise ValueError(
            f"Filter comparison for column `{column}` requires finite values."
        )
    return number


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return not str(value).strip()


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip().casefold()
