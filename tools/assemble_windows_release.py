"""Assemble a new, self-contained installer folder and ZIP without overwriting a release."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys
import zipfile
import argparse

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--name', default='Marine-Drift-Workbench-0.1.0-Windows-x64')
parser.add_argument('--bundle', type=Path, default=root / 'dist/Marine Drift Workbench')
args = parser.parse_args()
name = args.name
if not name or Path(name).name != name or name in {'.', '..'}:
    parser.error('--name must be a single folder name')
release = root / 'release' / name
release.mkdir(parents=True, exist_ok=False)
bundle = args.bundle
shutil.copytree(bundle, release / bundle.name)
shutil.copy2(root / 'LICENSE', release / 'LICENSE')
shutil.copy2(root / 'COPYRIGHT', release / 'COPYRIGHT')
for source in (root / 'tools/installer').iterdir():
    shutil.copy2(source, release / source.name)
notices = release / 'THIRD-PARTY-NOTICES'
notices.mkdir()
versions = []
for dist in sorted(metadata.distributions(), key=lambda item: item.metadata.get('Name', '').lower()):
    package = dist.metadata.get('Name', 'unknown')
    versions.append(f'{package}=={dist.version}')
    for relative in dist.files or []:
        if any(word in relative.name.lower() for word in ('license', 'copying', 'notice')):
            source = Path(dist.locate_file(relative))
            if source.is_file() and source.suffix.lower() not in ('.py', '.pyc', '.pyd', '.exe', '.dll'):
                destination = notices / package / str(relative).replace('..', '_parent_')
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
conda_licenses = Path(sys.prefix) / 'info/licenses'
if conda_licenses.is_dir():
    shutil.copytree(conda_licenses, notices / 'conda-runtime')
(release / 'BUILD-ENVIRONMENT.txt').write_text(
    'Build environment inventory (includes build-time and optional packages).\n'
    f'Bundled Python: {sys.version}\n\n' + '\n'.join(versions), encoding='utf-8')
conda_meta = Path(sys.prefix) / 'conda-meta'
if conda_meta.is_dir():
    records = [json.loads(path.read_text(encoding='utf-8')) for path in conda_meta.glob('*.json')]
    (release / 'CONDA-PACKAGES.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
archive = release.with_name(release.name + '.zip')
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=5) as target:
    for source in release.rglob('*'):
        if source.is_file():
            target.write(source, Path(name) / source.relative_to(release))
checksum = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
archive.with_name(archive.name + '.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
print(f'Folder: {release}\nZIP: {archive}\nSHA256: {checksum}')
