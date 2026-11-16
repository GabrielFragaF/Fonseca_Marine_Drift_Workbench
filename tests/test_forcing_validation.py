from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from marine_drift_desktop.core.environment import EnvironmentalReaderInspection
from marine_drift_desktop.core.forcing_validation import evaluate_forcing_readiness
from marine_drift_desktop.domain.models import EnvironmentalReaderConfig, SpatialExtent


class ForcingReadinessTests(unittest.TestCase):
    def test_partial_wind_coverage_is_warning_not_blocking_error(self) -> None:
        wind = self._reader("wind.nc", ["Atmospheric forcing"])
        inspection = self._inspection(
            "wind.nc",
            start="2024-01-02T00:00:00",
            end="2024-01-03T00:00:00",
            extent=SpatialExtent(-10.0, 10.0, -10.0, 10.0),
        )
        inspection.recognized_opendrift_variables = ["x_wind", "y_wind"]

        result = evaluate_forcing_readiness(
            [wind],
            [inspection],
            study_extent=SpatialExtent(-20, 20, -20, 20),
            required_start=datetime(2024, 1, 1),
            required_end=datetime(2024, 1, 4),
            require_wind=True,
        )

        self.assertEqual(result.check("wind_temporal_coverage").level, "warning")
        self.assertFalse(result.check("wind_temporal_coverage").blocks_run)
        self.assertEqual(result.check("wind_spatial_coverage").level, "warning")
        self.assertFalse(result.check("wind_spatial_coverage").blocks_run)

    def test_explicit_wind_fallback_makes_coverage_findings_non_blocking(self) -> None:
        from marine_drift_desktop.domain.models import FallbackValues

        wind = self._reader("wind.nc", ["Wind"])
        inspection = self._inspection(
            "wind.nc",
            start="2024-01-02T00:00:00", end="2024-01-03T00:00:00",
            extent=SpatialExtent(-10.0, 10.0, -10.0, 10.0),
        )
        inspection.recognized_opendrift_variables = ["x_wind", "y_wind"]
        fallback = FallbackValues(wind_enabled=True)
        result = evaluate_forcing_readiness(
            [wind], [inspection], study_extent=SpatialExtent(-20, 20, -20, 20),
            required_start=datetime(2024, 1, 1), required_end=datetime(2024, 1, 4),
            require_wind=True, fallback_values=fallback,
        )
        wind_coverage = [check for check in result.checks if check.key.startswith("wind_")]
        self.assertTrue(wind_coverage)
        self.assertFalse(any(check.blocks_run for check in wind_coverage))

    def _reader(self, name: str, roles: list[str]) -> EnvironmentalReaderConfig:
        return EnvironmentalReaderConfig(Path(name), roles)

    def _inspection(
        self,
        name: str,
        *,
        start: str = "2026-01-01T00:00:00",
        end: str = "2026-01-03T00:00:00",
        extent: SpatialExtent | None = None,
        step: float = 21_600.0,
    ) -> EnvironmentalReaderInspection:
        return EnvironmentalReaderInspection(
            path=Path(name),
            time_start=start,
            time_end=end,
            temporal_resolution_seconds=step,
            extent=extent or SpatialExtent(-45.0, -30.0, -20.0, -5.0),
            recognized_opendrift_variables=[
                "x_sea_water_velocity",
                "y_sea_water_velocity",
            ],
            compatibility_message="OpenDrift reader initialized successfully.",
        )

    def test_missing_required_currents_is_blocking(self) -> None:
        reader = self._reader("wind.nc", ["Atmospheric forcing"])

        result = evaluate_forcing_readiness(
            [reader],
            [self._inspection("wind.nc")],
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
        )

        check = result.check("required_currents")
        self.assertEqual(check.level, "error")
        self.assertTrue(check.blocks_run)
        self.assertFalse(result.is_ready)

    def test_assigned_currents_without_both_components_blocks_run(self) -> None:
        reader = self._reader("currents.nc", ["Ocean circulation"])
        inspection = self._inspection("currents.nc")
        inspection.recognized_opendrift_variables = ["x_sea_water_velocity"]

        result = evaluate_forcing_readiness(
            [reader],
            [inspection],
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
        )

        check = result.check("opendrift_compatibility")
        self.assertEqual(check.level, "error")
        self.assertTrue(check.blocks_run)
        self.assertFalse(result.is_ready)

    def test_current_components_cannot_be_split_across_assigned_readers(self) -> None:
        readers = [
            self._reader("eastward.nc", ["Ocean circulation"]),
            self._reader("northward.nc", ["Ocean circulation"]),
        ]
        eastward = self._inspection("eastward.nc")
        eastward.recognized_opendrift_variables = ["x_sea_water_velocity"]
        northward = self._inspection("northward.nc")
        northward.recognized_opendrift_variables = ["y_sea_water_velocity"]

        result = evaluate_forcing_readiness(
            readers,
            [eastward, northward],
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
        )

        check = result.check("opendrift_compatibility")
        self.assertEqual(check.level, "error")
        self.assertTrue(check.blocks_run)

    def test_sequential_current_files_cover_required_temporal_window(self) -> None:
        readers = [
            self._reader("currents_a.nc", ["Ocean circulation"]),
            self._reader("currents_b.nc", ["Ocean circulation"]),
        ]
        inspections = [
            self._inspection(
                "currents_a.nc",
                start="2026-01-01T00:00:00",
                end="2026-01-02T00:00:00",
            ),
            self._inspection(
                "currents_b.nc",
                start="2026-01-02T06:00:00",
                end="2026-01-03T00:00:00",
            ),
        ]

        result = evaluate_forcing_readiness(
            readers,
            inspections,
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
            required_start=datetime(2026, 1, 1),
            required_end=datetime(2026, 1, 3),
        )

        self.assertEqual(result.check("temporal_coverage").level, "success")
        self.assertFalse(any(check.key == "temporal_gap" for check in result.checks))

    def test_temporal_gap_and_overlap_are_reported(self) -> None:
        readers = [
            self._reader("a.nc", ["Currents"]),
            self._reader("b.nc", ["Currents"]),
            self._reader("c.nc", ["Currents"]),
        ]
        inspections = [
            self._inspection("a.nc", end="2026-01-01T06:00:00"),
            self._inspection(
                "b.nc",
                start="2026-01-01T18:00:00",
                end="2026-01-02T12:00:00",
            ),
            self._inspection(
                "c.nc",
                start="2026-01-02T06:00:00",
                end="2026-01-03T00:00:00",
            ),
        ]

        result = evaluate_forcing_readiness(
            readers,
            inspections,
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
        )

        self.assertEqual(result.check("temporal_gap").level, "warning")
        self.assertEqual(result.check("temporal_overlap").level, "info")

    def test_spatial_coverage_distinguishes_partial_and_no_overlap(self) -> None:
        reader = self._reader("currents.nc", ["Ocean circulation"])
        partial = evaluate_forcing_readiness(
            [reader],
            [
                self._inspection(
                    "currents.nc",
                    extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
                )
            ],
            study_extent=SpatialExtent(-42.0, -36.0, -16.0, -11.0),
        )
        none = evaluate_forcing_readiness(
            [reader],
            [
                self._inspection(
                    "currents.nc",
                    extent=SpatialExtent(10.0, 20.0, 10.0, 20.0),
                )
            ],
            study_extent=SpatialExtent(-42.0, -36.0, -16.0, -11.0),
        )

        self.assertEqual(partial.check("spatial_coverage").level, "warning")
        self.assertFalse(partial.check("spatial_coverage").blocks_run)
        self.assertEqual(none.check("spatial_coverage").level, "error")
        self.assertTrue(none.check("spatial_coverage").blocks_run)

    def test_optional_and_unused_roles_are_summarized(self) -> None:
        readers = [
            self._reader("currents.nc", ["Ocean circulation"]),
            self._reader("wind.nc", ["Atmospheric forcing"]),
            self._reader("custom.nc", ["Other / custom"]),
        ]
        inspections = [
            self._inspection("currents.nc"),
            self._inspection("wind.nc"),
            self._inspection("custom.nc"),
        ]

        result = evaluate_forcing_readiness(
            readers,
            inspections,
            study_extent=SpatialExtent(-40.0, -35.0, -15.0, -10.0),
        )

        self.assertIn("Atmospheric forcing", result.check("optional_forcing").detail)
        self.assertIn("1", result.check("unused_datasets").detail)


if __name__ == "__main__":
    unittest.main()
