from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ResultsExportRequest:
    results_directory: Path
    output_directory: Path
    positions_per_drift_day: int = 1
    write_csv: bool = False
    write_xlsx: bool = False
    output_basename: str = "mortality_positions"
    observation_dataset_override: Path | None = None
    environmental_variables: list[str] = field(default_factory=list)

    def validate(self) -> None:
        from ..core.environment_export import validate_environment_variables

        self.environmental_variables = validate_environment_variables(
            self.environmental_variables
        )
        if self.positions_per_drift_day < 1:
            raise ValueError("positions_per_drift_day must be at least 1")
        if not self.output_basename.strip():
            raise ValueError("output_basename must not be blank")
        if not self.results_directory.is_dir():
            raise ValueError("results_directory must be an existing directory")
        if self.output_directory.exists() and not self.output_directory.is_dir():
            raise ValueError("output_directory must not be an existing file")


@dataclass(frozen=True, slots=True)
class ResultsExportPaths:
    parquet: Path
    csv: Path | None = None
    xlsx: Path | None = None
    failures: Path | None = None
    manifest: Path | None = None
