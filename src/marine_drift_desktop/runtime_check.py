"""Explicit, offline installation check with a machine-readable report."""
from pathlib import Path
import importlib.metadata
import json
import sys
import traceback


def run_check(output_directory: str) -> int:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    report = {"python": sys.version, "executable": sys.executable,
              "frozen": bool(getattr(sys, "frozen", False)), "checks": []}
    try:
        import numpy as np
        import pandas as pd
        import xarray as xr
        from opendrift.readers.reader_global_landmask import Reader
        from .core.example_simulation import run_example_simulation
        from .app import create_application

        report["versions"] = {name: importlib.metadata.version(name) for name in
                              ("opendrift", "PySide6", "numpy", "netCDF4", "pandas", "pyarrow")}
        mask = Reader()
        mask.get_variables("land_binary_mask", x=np.array([-37.2]), y=np.array([-12.5]))
        report["checks"].append("Global landmask loaded")
        result = run_example_simulation(output, steps=2, particle_count=4)
        with xr.open_dataset(result.trajectory_path) as data:
            assert np.isfinite(data.lon.values).any(), "No finite positions"
            assert data.sizes["time"] >= 3, "Trajectory output missing"
            frame = pd.DataFrame({"longitude": data.lon.values.flatten(),
                                  "latitude": data.lat.values.flatten()})
        report["checks"].append("OpenDrift reverse simulation and NetCDF output")
        frame.to_parquet(output / "positions.parquet", index=False)
        restored = pd.read_parquet(output / "positions.parquet")
        restored.to_csv(output / "positions.csv", index=False)
        restored.to_excel(output / "positions.xlsx", index=False)
        assert len(pd.read_excel(output / "positions.xlsx")) == len(frame)
        report["checks"].append("Parquet, CSV and Excel export")
        app, window = create_application()
        window.show()
        app.processEvents()
        window.grab().save(str(output / "interface.png"))
        window.close()
        report["checks"].append("Qt GUI and bundled assets")
        report["success"] = True
    except Exception:
        report["success"] = False
        report["error"] = traceback.format_exc()
    (output / "installation-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["success"] else 1
