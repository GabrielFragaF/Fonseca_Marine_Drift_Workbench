# Marine Drift Workbench

This folder is a separate workspace for the downloadable desktop application that will run reverse-drift simulations locally.

The app is being designed around the existing notebook workflow while keeping the interface generic enough for any marine fauna stranding use case.

## Goals

- Run locally on the user's machine.
- Let users choose the observation dataset, environmental data locations, and simulation parameters.
- Keep terminology generic, such as `stranding identifier` instead of turtle-specific labels.
- Use a design-friendly UI architecture from the start so visual improvements do not require a framework rewrite later.
- Package first as a Windows one-folder installer so large scientific Python dependencies remain reliable.
- Follow the new Marine Drift Workbench visual identity: oceanographic, research-grade, map-driven, and polished.

## Stack

- Python
- PySide6 for the desktop UI
- A separate simulation engine layer that can absorb notebook logic as it is refactored into modules
- Windows installer target using a bundled one-folder runtime before attempting any single-file executable.

## Visual Identity

The app should use the brand-kit direction created for Marine Drift Workbench:

- deep navy and ocean blue workspace surfaces
- sea-glass green and cyan action accents
- pale scientific panels with clean grids and strong hierarchy
- bathymetry contours, current vectors, drift trajectories, and particle paths as the graphic language
- validation/status badges for ready, warning, error, info, and disabled states
- desktop-app UI components that feel like a premium scientific instrument rather than a generic form

## Suggested Local Setup

From this folder:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m marine_drift_desktop
```

If `py` is not available on your machine, use the Python interpreter path you normally use for this project.

## Repository Layout

- `src/marine_drift_desktop/`: application, modelling, validation, and export code.
- `tests/`: deterministic unit and GUI tests.
- `tools/`: development launchers and platform packaging utilities.
- `design/`: editable brand and icon sources.
- `docs/`: architecture, scientific assumptions, and implementation plans.

Generated environments, installers, simulation outputs, and scientific datasets are
intentionally excluded from Git. Windows releases are distributed as downloadable
release assets, while macOS builds must be generated natively on Apple Silicon.

## Cross-platform Development

Use feature branches for platform-specific packaging work. Shared modelling and UI code
stays in `src/`; Windows and macOS build scripts remain separate under `tools/`.

```bash
git switch -c macos-apple-silicon
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[package]"
marine-drift-desktop
```

Do not commit generated `build`, `dist`, or `release` folders. Attach `.zip`, `.exe`,
`.app`, and `.dmg` deliverables to a GitHub Release after platform testing.

## Current State

Version `0.1.0` is a runnable alpha. It includes:

- a dedicated app package
- a themed main window
- generic domain and configuration models
- reusable column-mapping and study-area presets
- absolute-path-oriented file selection and schema-aware validation
- data loading for CSV, Excel, and Parquet observation files
- a reusable core workflow layer for record parsing, duration rules, spatial checks, and simulation execution
- direct local OpenDrift execution in automatic batches of 5,000 simulations
- checkpoint-based resume, output skipping, cancellation, and live progress reporting
- a focused five-step interface with animated searchable selectors and icon navigation
- a real deterministic OpenDrift example that runs outside the GUI process and writes trajectory NetCDF output
- dirty-state handling that revokes run readiness whenever users change the setup
- all-row, reproducible random-sample, and multi-condition observation selection
- simulation bounds derived from overlapping NetCDF coverage with an optional degree buffer
- configurable nearby-water spiral search for observation coordinates that fall on land
- keyboard-accessible animated toggles and progressive advanced settings
- automated tests for validation, mapping, land/water adjustment, and manifest generation
- architecture notes for extracting notebook logic into reusable code
- metadata-first inspection of completed Workbench trajectory folders
- selectable positions-per-drift-day sampling with consistent timestamps across particles
- weighted mortality-position Parquet exports with optional CSV and Excel copies
- export diagnostics and a reproducibility manifest, generated in a background worker

The alpha can inspect NetCDF metadata and geographic coverage, configure environmental reader roles, convert coordinate formats, define duration scenarios, and source windage from a column, fixed percentage, or linear body-size estimate. Both the bundled example and configured production runs launch the real OpenDrift solver in isolated worker processes so the interface stays responsive.

## Observation And Position Controls

`All valid observations` processes every usable row. `Reproducible random sample` uses the requested count and seed. `Rows matching conditions` evaluates conditions from top to bottom with explicit `AND` or `OR` connectors; filter columns come from the selected observation file.

Spatial bounds can be entered manually or derived from the shared coverage of active environmental readers. The optional buffer is expressed in coordinate degrees and expands the detected overlap. For coastal records, nearby-water search follows a configurable radial spiral and either skips an unresolved observation or stops the run, according to the selected failure behavior.

The serialized request used for validation is also passed to the bundled worker. Source, selected, valid, skipped, adjusted-position, and failed-search counts are reported during execution. Runs continue automatically in batches of 5,000 and retain atomic outputs plus a resume checkpoint.

## Results And Export

### Trajectory Map

In `Results & export`, choose the results folder and scroll to `Trajectory map`.
Enter how many distinct individuals to plot (1-50), then click `Generate map`.
The app samples distinct normalized stranding identifiers first, then randomly
chooses one existing run per identifier. Distinctness is based on the supplied
identifiers, not inferred biological identity. If fewer identifiers are available,
all are selected and a notice explains the shortfall.

Use the same random seed to reproduce a selection from an unchanged results folder,
or click `New random sample`. No table export or new simulation is required. The
background worker reads compatible Workbench NetCDF files directly, without
requiring the original observation table to still be present.

The offline map includes a generalized Natural Earth coastline, a run legend,
and first/last displayed position markers. `Save map as PNG` embeds the selected
identifiers, run paths, particle indices, seed, and notices in PNG text metadata.
For responsiveness, previews show at most 12 randomly sampled particles per run
and thin long tracks; missing coordinates and date-line crossings break lines.
Highly fragmented tracks may be truncated with a notice. These are display-only
limits: original trajectories and weighted position tables remain unchanged.
The preview is not a mortality-probability map or a detailed coastal landmask.

### Position Tables

After a run completes, open `Results & export`. The app inspects compatible trajectory metadata without loading every particle position into memory, calculates the maximum sampling density supported by the output interval, and shows an estimated table size. Enter the number of mortality positions to retain per drift day for each simulation.

The export worker creates one canonical weighted Parquet table. Every stranding identifier has a total weight of one across all retained simulations and positions. Optional CSV and Excel files are converted from that completed Parquet table rather than rebuilding the data independently. Very large Excel requests are skipped safely because worksheets have a fixed row limit; Parquet remains available.

## Windows Bundle

The self-contained Windows x64 preview is assembled by `tools/assemble_windows_release.py`
after the executable passes `tools/verify_windows_bundle.py`. The resulting ZIP includes
`Install.cmd`, a per-user installer, and the complete application folder. Users do not
need Python or Conda. Existing Python installations are not used or modified.

This preview preserves the tested Python 3.11.10 / OpenDrift 1.11.13 runtime. The broad
source dependencies below are not a release lock: use the recorded build environment
to reproduce this bundle, and validate upgrades separately. Compatibility with arbitrary
future Python interpreters is not implied by the standalone executable.

Run `Verify installation.cmd` in the extracted ZIP to check the bundled GUI, landmask,
NetCDF, OpenDrift solver and table writers. Supply your own environmental and observation
datasets for scientific work. Another physical Windows machine is still needed for
independent installation acceptance testing.

The project includes a first one-folder PyInstaller build script. From an environment containing the app dependencies and packaging tools:

```powershell
pip install -e ".[package]"
.\tools\build_windows_bundle.ps1
```

This creates `dist\Marine Drift Workbench\`. A later installer step can wrap this folder with Inno Setup or NSIS to create the normal Windows install experience with desktop and Start Menu shortcuts.

## Next Build Step

The next practical step is packaging and installer validation on a clean Windows machine, followed by broader OpenDrift reader compatibility testing and signed distribution.

## Apple Silicon macOS Bundle

On an Apple Silicon Mac with Python 3.11 and the packaging dependencies installed,
build the self-contained application with:

```bash
PYTHON_BIN="$PWD/.venv/bin/python" tools/build_macos_bundle.sh
```

The unsigned local-testing bundle is written to
`dist/Marine Drift Workbench.app`. It contains Python, OpenDrift, Qt, and the
scientific runtime dependencies; users do not need a separate Python installation.

The packaging path should start with a one-folder Windows installer, then evolve toward update tooling, signed executables, and optional cross-platform builds after the modeling engine is stable.

## License

Copyright (C) 2026 Gabriel Fraga da Fonseca.

Marine Drift Workbench is free software licensed under the [GNU General Public
License version 3 or later](LICENSE). You may use, study, modify, and
redistribute the software under those terms. Distributed modified versions must
preserve the GPL freedoms and corresponding source-code obligations.
