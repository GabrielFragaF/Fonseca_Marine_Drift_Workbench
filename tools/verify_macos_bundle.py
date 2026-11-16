"""Exercise the macOS application bundle without development runtime paths."""
import json
import os
from pathlib import Path
import subprocess
import sys


def clean_environment() -> dict[str, str]:
    prefixes = ("PYTHON", "CONDA", "PROJ", "GDAL", "QT_", "DYLD_")
    environment = {
        key: value for key, value in os.environ.items() if not key.upper().startswith(prefixes)
    }
    environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["MPLCONFIGDIR"] = "/tmp/marine-drift-matplotlib"
    return environment


def run_worker(executable: Path, output: Path, arguments: list[str], prefix: str) -> None:
    worker = subprocess.run(
        [str(executable), *arguments], cwd=output, env=clean_environment(),
        capture_output=True, timeout=60,
    )
    message = worker.stdout.decode("utf-8", errors="replace")
    assert worker.returncode == 1 and prefix in message and "fatal" in message, message
    print("Worker error/progress pipe verified:", arguments[0])


def verify_production_workers(executable: Path, output: Path) -> None:
    """Run real frozen simulation, inspection, export, and map workers."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.results_test_support import make_results_fixture
    from marine_drift_desktop.core.results_serialization import write_results_export_request
    from marine_drift_desktop.core.request_serialization import write_simulation_request
    from marine_drift_desktop.domain.models import ColumnMapping, EnvironmentalReaderConfig, SimulationRequest
    import numpy as np
    import pandas as pd
    import xarray as xr

    production = output / "production-example"
    production.mkdir()
    with xr.open_dataset(output / "example_forcing.nc") as dataset:
        base = dataset.isel(time=0, drop=True).load()
    times = np.datetime64("2024-04-12T00:00", "ns") + np.arange(40).astype("timedelta64[h]")
    forcing_path = production / "currents.nc"
    forcing = base.expand_dims(time=times)
    forcing.time.attrs["standard_name"] = "time"
    forcing.to_netcdf(forcing_path)
    observations = production / "observations.csv"
    pd.DataFrame([{
        "id": "example-001", "taxon": "Marine fauna", "decomposition": 3,
        "lon": -37.2, "lat": -12.5, "date": "2024-04-13", "time": "12:00",
    }]).to_csv(observations, index=False)
    simulation = SimulationRequest()
    simulation.data_sources.observation_dataset = observations
    simulation.data_sources.output_directory = production / "results"
    simulation.data_sources.environment_readers = [
        EnvironmentalReaderConfig(forcing_path, roles=["currents"])
    ]
    simulation.column_mapping = ColumnMapping(
        stranding_identifier="id", taxon_label="taxon", decomposition_code="decomposition",
        longitude="lon", latitude="lat", observed_date="date", observed_time="time",
    )
    simulation.settings.duration.mode = "fixed"
    simulation.settings.duration.fixed_days = 1
    simulation.settings.wind_drift.mode = "none"
    simulation.settings.iteration_count = 1
    simulation.settings.particle_count = 2
    simulation.settings.current_uncertainty_enabled = False
    simulation.settings.wind_uncertainty_enabled = False
    simulation.settings.fallback_values.stokes_drift_enabled = True
    simulation.settings.fallback_values.seafloor_depth_enabled = True
    simulation_path = write_simulation_request(simulation, production / "request.json")
    for resumed in (False, True):
        worker = subprocess.run(
            [str(executable), "--simulation-worker", str(simulation_path)],
            cwd=output, env=clean_environment(), capture_output=True, timeout=120,
        )
        message = worker.stdout.decode("utf-8", errors="replace")
        events = [json.loads(line.split("=", 1)[1]) for line in message.splitlines()
                  if line.startswith("MARINE_DRIFT_EVENT=")]
        assert worker.returncode == 0 and events[-1]["event"] == "finished", message
        assert events[-1]["failed"] == 0 and events[-1]["total_jobs"] == 1, message
        assert events[-1]["existing" if resumed else "completed"] == 1, message
        print("Production reverse-drift worker verified; resumed:", resumed)

    request = make_results_fixture(output / "weighted-export")
    request_path = write_results_export_request(request, output / "export-request.json")
    map_path = output / "map-request.json"
    map_path.write_text(json.dumps({
        "results_directory": str(request.results_directory),
        "individual_count": 1,
        "seed": 42,
    }), encoding="utf-8")
    for operation in ("inspect", "export", "map"):
        operation_path = map_path if operation == "map" else request_path
        worker = subprocess.run(
            [str(executable), "--results-worker", operation, str(operation_path)],
            cwd=output, env=clean_environment(), capture_output=True, timeout=120,
        )
        message = worker.stdout.decode("utf-8", errors="replace")
        assert worker.returncode == 0 and "fatal" not in message, (
            message + worker.stderr.decode("utf-8", errors="replace")
        )
        print("Frozen results worker succeeded:", operation)


def main(bundle: Path, output: Path) -> None:
    executable = bundle / "Contents/MacOS/Marine Drift Workbench"
    if not executable.is_file():
        raise SystemExit(f"No bundled executable at {executable}")
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(executable), "--self-test", str(output)], cwd=output,
        env=clean_environment(), capture_output=True, timeout=240,
    )
    print("Self-test exit:", result.returncode)
    print(result.stderr.decode("utf-8", errors="replace")[-5000:])
    report_path = output / "installation-check.json"
    if not report_path.exists():
        raise SystemExit("No self-test report was produced")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    print(json.dumps(report, indent=2))
    assert result.returncode == 0 and report["success"]
    run_worker(executable, output, ["--simulation-worker", "missing.json"], "MARINE_DRIFT_EVENT=")
    run_worker(executable, output, ["--results-worker", "inspect", "missing.json"], "MARINE_DRIFT_RESULTS_EVENT=")
    verify_production_workers(executable, output)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: verify_macos_bundle.py BUNDLE_PATH OUTPUT_DIRECTORY")
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
