# Contributing

Marine Drift Workbench uses one shared Python/PySide6 codebase for Windows and macOS.
Keep scientific behaviour in `src/marine_drift_desktop/core` and platform packaging in
`tools`. Avoid embedding study-specific names, locations, paths, or assumptions in the
application.

## Development workflow

1. Start from the latest `main` branch and create a focused feature branch.
2. Install the project in an isolated Python 3.11 environment.
3. Add or update tests when scientific or data-processing behaviour changes.
4. Run the relevant test modules before committing.
5. Keep datasets and generated model outputs outside the repository.

## Commit scope

Commit source code, tests, documentation, icons, and reproducible build scripts. Do not
commit Python environments, build folders, installers, credentials, observation tables,
environmental NetCDF files, or simulation results.

## Platform releases

Build Windows packages on Windows and Apple Silicon packages on an Apple Silicon Mac.
Test each frozen application without relying on a developer Python environment before
publishing it as a release asset.
