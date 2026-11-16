"""Exercise the map worker and render the results UI using synthetic trajectories."""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from netCDF4 import Dataset
from PySide6.QtTest import QTest
from marine_drift_desktop.app import create_application
from tests.results_test_support import make_trajectory_netcdf

root = Path(".tmp_tests/trajectory_map_review").resolve()
source = root / "synthetic-results"
for individual in range(5):
    for iteration in (1, 2, 3):
        path = make_trajectory_netcdf(source / f"DEMO-{individual + 1}-{iteration}.nc",
                                     identifier=f"DEMO-{individual + 1}", iteration=iteration)
        with Dataset(path, "a") as dataset:
            t = np.linspace(0, 1, dataset.variables["time"].size)
            for particle in range(2):
                dataset.variables["lon"][particle, :] = -40.5 + individual * .15 + t * 2 + .12 * np.sin(t * 7 + iteration)
                dataset.variables["lat"][particle, :] = -21.5 + individual * .5 + t * .6 + .18 * np.sin(t * 5 + particle)

app, window = create_application()
window.resize(1440, 1100)
window.show()
window.stage_navigation.setCurrentRow(4)
page = window.results_export_page
page.results_directory.setText(str(source))
card = page.trajectory_map
card.count.setValue(3)
card.generate()
deadline = time.monotonic() + 30
while card._busy and time.monotonic() < deadline:
    QTest.qWait(40)
assert card.canvas.payload is not None, card.status.text()
card.status.setText("Visual test using synthetic trajectories only. Three distinct identifiers, one run each.")
card.canvas.save_png(root / "synthetic-map.png")
for width, height in ((1440, 1100), (1080, 950)):
    window.resize(width, height)
    QTest.qWait(250)
    page.ensureWidgetVisible(card, 0, 0)
    QTest.qWait(150)
    window.grab().save(str(root / f"results-map-{width}.png"))
window.close()
print(f"Synthetic map and GUI renders: {root}")
