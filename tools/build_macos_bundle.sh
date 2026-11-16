#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This build must run on an Apple Silicon (arm64) Mac." >&2
  exit 1
fi

if [[ -n "${PYTHON_BIN:-}" ]]; then
  "$PYTHON_BIN" -m PyInstaller --noconfirm tools/marine_drift_macos.spec
else
  python -m PyInstaller --noconfirm tools/marine_drift_macos.spec
fi

echo "Bundle created at: $project_root/dist/Marine Drift Workbench.app"
