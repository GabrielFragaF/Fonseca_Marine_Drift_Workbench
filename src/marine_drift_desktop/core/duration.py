from __future__ import annotations

from dataclasses import dataclass, field
from bisect import bisect_right
import math

from ..domain.models import DurationSettings


@dataclass(slots=True)
class ThermalDurationProfile:
    """
    Generic duration profile based on decomposition category and SST.

    The default values preserve the current notebook logic while exposing the
    rule as a reusable profile instead of hard-coding it inside a script cell.
    """

    warm_water_threshold_celsius: float = 24.0
    warm_water_days: dict[int, int] = field(
        default_factory=lambda: {
            1: 2,
            2: 2,
            3: 3,
            4: 6,
            5: 8,
        }
    )
    cool_water_days: dict[int, int] = field(
        default_factory=lambda: {
            1: 2,
            2: 3,
            3: 4,
            4: 7,
            5: 12,
        }
    )
    temperature_boundaries_celsius: list[float] = field(default_factory=lambda: [24.0])
    scenario_days: dict[int, list[int]] = field(default_factory=dict)

    def duration_for(
        self,
        decomposition_code: int,
        sea_surface_temperature: float | None,
    ) -> int:
        if sea_surface_temperature is None or not math.isfinite(sea_surface_temperature):
            raise ValueError("Sea surface temperature is required for estimated drift duration.")
        temperature = sea_surface_temperature
        if self.scenario_days:
            band = bisect_right(self.temperature_boundaries_celsius, temperature)
            try:
                return self.scenario_days[decomposition_code][band]
            except (KeyError, IndexError) as exc:
                raise ValueError(
                    f"Unsupported decomposition code `{decomposition_code}` for the active duration profile."
                ) from exc
        table = self.warm_water_days if temperature > self.warm_water_threshold_celsius else self.cool_water_days
        try:
            return table[decomposition_code]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported decomposition code `{decomposition_code}` for the active duration profile."
            ) from exc


def build_default_duration_profile() -> ThermalDurationProfile:
    return ThermalDurationProfile()


def build_duration_profile(settings: DurationSettings) -> ThermalDurationProfile:
    return ThermalDurationProfile(
        warm_water_threshold_celsius=settings.temperature_threshold_celsius,
        warm_water_days=dict(settings.warm_water_days),
        cool_water_days=dict(settings.cool_water_days),
        temperature_boundaries_celsius=sorted(settings.temperature_boundaries_celsius),
        scenario_days={int(code): list(days) for code, days in settings.scenario_days.items()},
    )
