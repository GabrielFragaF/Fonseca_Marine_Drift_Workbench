from __future__ import annotations

import re
import hashlib
from datetime import timedelta
from pathlib import Path

from ..domain.models import (
    CanonicalObservation,
    SimulationIterationPlan,
    SimulationSettings,
)


def plan_simulation_runs(
    observation: CanonicalObservation,
    settings: SimulationSettings,
    output_directory: Path,
) -> list[SimulationIterationPlan]:
    base_start_time = observation.observed_at
    if settings.start_time_mode == "fixed_hour":
        base_start_time = base_start_time.replace(
            hour=settings.fixed_start_hour,
            minute=0,
            second=0,
            microsecond=0,
        )

    identifier_fragment = _slugify_fragment(observation.stranding_identifier)
    taxon_fragment = _slugify_fragment(observation.taxon_label)
    # Distinguish separate stranding events while retaining duplicate-event checks.
    event_token = stranding_event_token(observation)

    plans: list[SimulationIterationPlan] = []
    for iteration_index in range(1, settings.iteration_count + 1):
        start_time = base_start_time - timedelta(
            hours=settings.iteration_interval_hours * (iteration_index - 1)
        )
        output_name = (
            f"{identifier_fragment}_{taxon_fragment}"
            f"_DEC{observation.decomposition_code}"
            f"_DUR{observation.reverse_drift_duration_days}d"
            f"_EV{event_token}"
            f"_{iteration_index:02d}.nc"
        )
        plans.append(
            SimulationIterationPlan(
                iteration_index=iteration_index,
                start_time=start_time,
                output_path=output_directory / output_name,
            )
        )
    return plans


def stranding_event_token(observation: CanonicalObservation) -> str:
    event = f"{observation.observed_at.isoformat()}|{observation.longitude:.10f}|{observation.latitude:.10f}"
    return hashlib.sha256(event.encode("utf-8")).hexdigest()[:16]


def _slugify_fragment(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip("-._")
    return cleaned or "observation"
