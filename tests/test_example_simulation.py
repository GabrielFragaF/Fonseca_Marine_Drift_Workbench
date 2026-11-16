from __future__ import annotations

import unittest
from pathlib import Path

from marine_drift_desktop.core.example_simulation import run_example_simulation


class ExampleSimulationTests(unittest.TestCase):
    def test_short_example_writes_a_real_trajectory_netcdf(self) -> None:
        output = Path(__file__).resolve().parents[1] / ".tmp_tests" / "example_run"

        result = run_example_simulation(output, steps=2, particle_count=3)

        self.assertTrue(result.trajectory_path.exists())
        self.assertGreater(result.trajectory_path.stat().st_size, 0)
        self.assertEqual(result.particle_count, 3)
        self.assertEqual(result.steps, 2)


if __name__ == "__main__":
    unittest.main()
