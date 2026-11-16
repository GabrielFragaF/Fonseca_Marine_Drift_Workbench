from __future__ import annotations

from dataclasses import replace

from .models import ColumnMapping, SpatialExtent


_COLUMN_MAPPING_PRESETS = {
    "Map columns manually": ColumnMapping(),
}

_STUDY_AREA_PRESETS = {
    "Global extent": SpatialExtent(),
}


def list_column_mapping_presets() -> list[str]:
    return list(_COLUMN_MAPPING_PRESETS)


def list_study_area_presets() -> list[str]:
    return list(_STUDY_AREA_PRESETS)


def get_column_mapping_preset(name: str) -> ColumnMapping:
    return replace(_COLUMN_MAPPING_PRESETS[name])


def get_study_area_preset(name: str) -> SpatialExtent:
    return replace(_STUDY_AREA_PRESETS[name])
