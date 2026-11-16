"""Avoid Conda ICU shadowing the Windows ICU API used by Qt 6.11."""
from pathlib import Path
import pefile


def isolate_icu(base):
    base = Path(base)
    source = base / 'icuuc.dll'
    if not source.exists():
        return
    for path in list(base.rglob('*.dll')) + list(base.rglob('*.pyd')):
        if 'PySide6' in path.parts:
            continue
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[1, 13])
        offsets = []
        for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
            if entry.dll.lower() == b'icuuc.dll':
                offsets.append(pe.get_offset_from_rva(entry.struct.Name))
        for entry in getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
            if entry.dll.lower() == b'icuuc.dll':
                offsets.append(pe.get_offset_from_rva(entry.struct.szName))
        pe.close()
        if offsets:
            data = bytearray(path.read_bytes())
            for offset in offsets:
                data[offset:offset + 9] = b'icu78.dll'
            path.write_bytes(data)
            print('Isolated Conda ICU import:', path.name)
    source.rename(base / 'icu78.dll')


if __name__ == '__main__':
    import sys
    isolate_icu(sys.argv[1])
