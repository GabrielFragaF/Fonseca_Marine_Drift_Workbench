from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvironmentVariableDefinition:
    label: str
    description: str


ENVIRONMENT_EXPORT_CATALOGUE = {
    "x_sea_water_velocity": EnvironmentVariableDefinition("Eastward current", "Eastward sea-water velocity at the particle position."),
    "y_sea_water_velocity": EnvironmentVariableDefinition("Northward current", "Northward sea-water velocity at the particle position."),
    "x_wind": EnvironmentVariableDefinition("Eastward wind", "Eastward wind velocity at the particle position."),
    "y_wind": EnvironmentVariableDefinition("Northward wind", "Northward wind velocity at the particle position."),
    "sea_water_temperature": EnvironmentVariableDefinition("Sea-water temperature", "Water temperature at the particle position."),
    "sea_water_salinity": EnvironmentVariableDefinition("Sea-water salinity", "Water salinity at the particle position."),
    "sea_surface_wave_significant_height": EnvironmentVariableDefinition("Significant wave height", "Significant wave height at the particle position."),
    "sea_floor_depth_below_sea_level": EnvironmentVariableDefinition("Seafloor depth", "Seafloor depth below sea level at the particle position."),
    "sea_surface_wave_stokes_drift_x_velocity": EnvironmentVariableDefinition("Eastward Stokes drift", "Eastward surface-wave Stokes drift velocity."),
    "sea_surface_wave_stokes_drift_y_velocity": EnvironmentVariableDefinition("Northward Stokes drift", "Northward surface-wave Stokes drift velocity."),
}


def validate_environment_variables(names: list[str] | tuple[str, ...]) -> list[str]:
    ordered = list(dict.fromkeys(names))
    unknown = [name for name in ordered if name not in ENVIRONMENT_EXPORT_CATALOGUE]
    if unknown:
        raise ValueError(f"Unsupported environmental export variable(s): {', '.join(unknown)}")
    return ordered
