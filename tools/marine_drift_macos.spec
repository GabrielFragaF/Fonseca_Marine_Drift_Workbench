"""PyInstaller recipe for the unsigned Apple Silicon macOS application."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata


root = Path(SPECPATH).parent
datas = [(str(root / "src/marine_drift_desktop/ui/assets"), "marine_drift_desktop/ui/assets")]
hidden = []
for package in ("opendrift", "roaring_landmask", "xarray", "netCDF4", "pyarrow", "openpyxl", "pynucos", "trajan", "cmocean"):
    datas += collect_data_files(package)
for package in ("marine-drift-desktop", "opendrift", "PySide6", "numpy", "netCDF4", "pandas", "pyarrow", "xarray"):
    datas += copy_metadata(package)
for package in ("netCDF4", "pyproj", "pyogrio", "shapely"):
    datas += collect_dynamic_libs(package)
for package in ("opendrift.models", "opendrift.readers", "opendrift.export", "xarray.backends", "scipy.integrate"):
    hidden += collect_submodules(package)

a = Analysis(
    [str(root / "tools/macos_entry.py")],
    pathex=[str(root / "src")],
    datas=datas,
    hiddenimports=hidden,
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "notebook", "jupyter", "pytest", "torch", "tensorflow", "bokeh", "distributed"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Marine Drift Workbench",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
app = BUNDLE(
    exe,
    a.binaries,
    a.datas,
    name="Marine Drift Workbench.app",
    bundle_identifier="org.marine-drift.workbench",
    icon=str(root / "tools/installer/app.icns"),
)
