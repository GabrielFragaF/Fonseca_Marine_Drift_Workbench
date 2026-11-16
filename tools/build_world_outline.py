"""Build a compact geographic overview from the local Natural Earth fixture."""
import gzip
import json
from pathlib import Path
from shapely.geometry import shape

root = Path(__file__).resolve().parents[2]
source = root / "Website/tippecanoe-1.36.0/tests/ne_110m_admin_0_countries/in.json.gz"
with gzip.open(source, "rt", encoding="utf-8") as stream:
    features = json.load(stream)["features"]
rings = []
for feature in features:
    geometry = shape(feature["geometry"]).simplify(0.25, preserve_topology=True)
    polygons = [geometry] if geometry.geom_type == "Polygon" else geometry.geoms
    for polygon in polygons:
        rings.append([[round(x, 3), round(y, 3)] for x, y in polygon.exterior.coords])
target = root / "desktop_app/src/marine_drift_desktop/ui/assets/world.json"
target.write_text(json.dumps(rings, separators=(",", ":")), encoding="utf-8")
print(f"{len(rings)} outline polygons: {target.stat().st_size} bytes")
