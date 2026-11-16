from __future__ import annotations

import json
import sys
from pathlib import Path

from .core.example_simulation import run_example_simulation


def run_worker(output_directory: str) -> int:
    try:
        result = run_example_simulation(Path(output_directory))
    except Exception as exc:
        print(f"MARINE_DRIFT_ERROR={exc}", flush=True)
        return 1
    payload = {
        "trajectory_path": str(result.trajectory_path),
        "forcing_path": str(result.forcing_path),
        "particle_count": result.particle_count,
        "steps": result.steps,
    }
    print(f"MARINE_DRIFT_RESULT={json.dumps(payload)}", flush=True)
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Example worker requires one output-directory argument.", file=sys.stderr)
        return 2
    return run_worker(sys.argv[1])


if __name__ == "__main__":
    raise SystemExit(main())
