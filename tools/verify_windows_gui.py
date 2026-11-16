"""Check the frozen GUI without developer paths or a simulation run."""
import json
import os
from pathlib import Path
import subprocess
import sys


exe = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
environment = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PYTHON", "CONDA", "PROJ", "GDAL", "QT_"))}
environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
environment["QT_QPA_PLATFORM"] = "offscreen"
result = subprocess.run([str(exe), "--gui-check", str(output)], cwd=output,
                        env=environment, capture_output=True, timeout=90)
report = json.loads((output / "gui-check.json").read_text(encoding="utf-8"))
print(json.dumps(report, indent=2))
if result.returncode != 0 or not report.get("success") or not report.get("frozen"):
    raise SystemExit("Frozen GUI check failed")
