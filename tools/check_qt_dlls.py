from pathlib import Path
import os
import pefile

base = Path('dist/Marine Drift Workbench/_internal').resolve()
folders = [base, base / 'PySide6', base / 'shiboken6', Path(os.environ['SystemRoot']) / 'System32']
pending = [base / 'PySide6/QtGui.pyd']
seen = set()
while pending:
    path = pending.pop()
    if path in seen:
        continue
    seen.add(path)
    pe = pefile.PE(str(path), fast_load=True)
    pe.parse_data_directories(directories=[1])
    for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        name = entry.dll.decode()
        if name.lower().startswith(('api-', 'ext-')):
            continue
        dependency = next((folder / name for folder in folders if (folder / name).exists()), None)
        if dependency is None:
            print('MISSING DLL', path.name, name)
            continue
        target = pefile.PE(str(dependency), fast_load=True)
        target.parse_data_directories(directories=[0])
        exports = {symbol.name for symbol in getattr(getattr(target, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])}
        missing = [symbol.name.decode() for symbol in entry.imports if symbol.name and symbol.name not in exports]
        if missing:
            print('MISSING SYMBOLS', path.name, '->', str(dependency), missing[:12])
        if dependency.is_relative_to(base):
            pending.append(dependency)
