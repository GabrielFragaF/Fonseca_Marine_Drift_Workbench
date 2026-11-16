"""Refresh the release ZIP atomically after updating its assembled folder."""
import hashlib
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
name = 'Marine-Drift-Workbench-0.1.0-Windows-x64'
folder = root / 'release' / name
archive = root / 'release' / f'{name}.zip'
temporary = archive.with_suffix('.zip.new')
with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as target:
    for source in folder.rglob('*'):
        if source.is_file():
            target.write(source, Path(name) / source.relative_to(folder))
with zipfile.ZipFile(temporary) as target:
    if target.testzip() is not None:
        raise RuntimeError('Refreshed release ZIP failed its integrity check')
temporary.replace(archive)
checksum = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
checksum_path = archive.with_name(archive.name + '.sha256')
checksum_path.write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
print(f'ZIP: {archive}\nSHA256: {checksum}')
