from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.models import SpatialExtent

LandPredicate = Callable[[float, float], bool]


@dataclass(slots=True, frozen=True)
class PositionAdjustment:
    original_longitude: float
    original_latitude: float
    longitude: float
    latitude: float
    was_adjusted: bool
    is_within_extent: bool
    attempts: int = 0
    search_failed: bool = False


def is_position_within_extent(
    longitude: float,
    latitude: float,
    extent: SpatialExtent,
) -> bool:
    return (
        extent.min_longitude <= longitude <= extent.max_longitude
        and extent.min_latitude <= latitude <= extent.max_latitude
    )


def adjust_to_nearby_water(
    longitude: float,
    latitude: float,
    is_land: LandPredicate,
    extent: SpatialExtent,
    *,
    shift_degrees: float = 0.01,
    max_radius_degrees: float = 0.5,
    angle_step_degrees: int = 10,
    max_attempts: int = 5000,
) -> PositionAdjustment:
    """
    Move a stranded observation point to nearby water when it starts on land.

    This preserves the notebook search pattern while keeping the function pure
    and independent from a specific landmask reader implementation.
    """

    if not is_position_within_extent(longitude, latitude, extent):
        return PositionAdjustment(
            original_longitude=longitude,
            original_latitude=latitude,
            longitude=longitude,
            latitude=latitude,
            was_adjusted=False,
            is_within_extent=False,
        )

    if not is_land(longitude, latitude):
        return PositionAdjustment(
            original_longitude=longitude,
            original_latitude=latitude,
            longitude=longitude,
            latitude=latitude,
            was_adjusted=False,
            is_within_extent=True,
        )

    attempts = 0
    radius = shift_degrees
    while radius <= max_radius_degrees and attempts < max_attempts:
        for angle in range(0, 360, angle_step_degrees):
            radians = math.radians(angle)
            candidate_longitude = longitude + radius * math.cos(radians)
            candidate_latitude = latitude + radius * math.sin(radians)

            if not is_position_within_extent(
                candidate_longitude,
                candidate_latitude,
                extent,
            ):
                continue

            attempts += 1
            if not is_land(candidate_longitude, candidate_latitude):
                return PositionAdjustment(
                    original_longitude=longitude,
                    original_latitude=latitude,
                    longitude=candidate_longitude,
                    latitude=candidate_latitude,
                    was_adjusted=True,
                    is_within_extent=True,
                    attempts=attempts,
                )

            if attempts >= max_attempts:
                break

        radius += shift_degrees

    return PositionAdjustment(
        original_longitude=longitude,
        original_latitude=latitude,
        longitude=longitude,
        latitude=latitude,
        was_adjusted=False,
        is_within_extent=True,
        attempts=attempts,
        search_failed=True,
    )
