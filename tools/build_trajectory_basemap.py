"""Prepare an offline Natural Earth land layer from its public-domain shapefile."""
import json
import sys
from pathlib import Path

import geopandas as gpd

source = Path(sys.argv[1])
target = Path(__file__).resolve().parents[1] / "src/marine_drift_desktop/ui/assets/trajectory_land.json"
features = []
for geometry in gpd.read_file(source).geometry:
    for polygon in (geometry.geoms if geometry.geom_type == "MultiPolygon" else [geometry]):
        polygon = polygon.simplify(.005, preserve_topology=True)
        rings = [polygon.exterior, *polygon.interiors]
        features.append([list(polygon.bounds), [[[round(x, 4), round(y, 4)] for x, y in ring.coords] for ring in rings]])
target.write_text(json.dumps(features, separators=(",", ":")), encoding="utf-8")
print(f"Wrote {len(features)} land polygons to {target} ({target.stat().st_size:,} bytes)")
