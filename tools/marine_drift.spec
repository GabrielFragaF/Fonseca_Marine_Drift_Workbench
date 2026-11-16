from pathlib import Path
import sys
import os
import shutil
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
native = Path(sys.prefix) / 'Library/bin'
os.environ['PATH'] = str(native) + os.pathsep + os.environ.get('PATH', '')
datas = [(str(root / 'src/marine_drift_desktop/ui/assets'), 'marine_drift_desktop/ui/assets')]
hidden = []
for package in ('opendrift', 'roaring_landmask', 'xarray', 'netCDF4', 'pyarrow', 'openpyxl', 'pynucos', 'trajan', 'cmocean', 'tzdata'):
    datas += collect_data_files(package)
for package in ('marine-drift-desktop', 'opendrift', 'PySide6', 'numpy', 'netCDF4', 'pandas', 'pyarrow', 'xarray'):
    datas += copy_metadata(package)
for package in ('opendrift.models', 'opendrift.readers', 'opendrift.export', 'xarray.backends', 'scipy.integrate'):
    hidden += collect_submodules(package)
for directory in ('proj', 'gdal'):
    source = Path(sys.prefix) / 'Library/share' / directory
    if source.is_dir():
        datas.append((str(source), directory))
a = Analysis([str(root / 'tools/windows_entry.py')], pathex=[str(root / 'src')],
             binaries=[(str(path), '.') for pattern in ('gdal*.dll', 'proj*.dll', 'netcdf*.dll', 'hdf5*.dll')
                       for path in native.glob(pattern)], datas=datas, hiddenimports=hidden,
             runtime_hooks=[str(root / 'tools/frozen_runtime.py')],
             excludes=['PyQt5', 'PyQt6', 'PySide2', 'tkinter', 'IPython', 'notebook',
                       'jupyter', 'pytest', 'torch', 'tensorflow', 'bokeh', 'distributed'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Marine Drift Workbench',
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / 'tools/installer/app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Marine Drift Workbench')
internal = Path(DISTPATH) / 'Marine Drift Workbench/_internal'
import PySide6
for path in Path(PySide6.__file__).parent.glob('*.dll'):
    if path.name.lower().startswith(('msvcp140', 'vcruntime140')):
        shutil.copy2(path, internal / path.name)
sys.path.insert(0, str(root / 'tools'))
from isolate_icu import isolate_icu
isolate_icu(internal)
