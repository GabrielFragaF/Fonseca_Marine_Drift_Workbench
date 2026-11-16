# World overview

world.json contains simplified exterior rings from Natural Earth's 1:110m
country dataset, via the project's existing Tippecanoe test fixture
Website/tippecanoe-1.36.0/tests/ne_110m_admin_0_countries/in.json.gz.
Natural Earth geographic data is public domain. Rebuild with
desktop_app/tools/build_world_outline.py (requires Shapely).

This approximate equirectangular overview is for orienting the user only.
It must not be used for position snapping, land detection, or data coverage
validation. Those remain responsibilities of the modelling code and readers.

trajectory_land.json is a simplified, bundled Natural Earth 1:10m land layer
for offline trajectory-map previews and PNG exports. Natural
Earth data is public domain: https://www.naturalearthdata.com/about/terms-of-use/.
Rebuild with tools/build_trajectory_basemap.py and ne_10m_land.shp. It is a
cartographic reference, not a landmask or navigational chart.
