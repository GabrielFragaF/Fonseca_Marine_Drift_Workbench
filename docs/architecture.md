# Architecture Notes

## Intent

The desktop app should preserve the simulation flow from the notebook while separating concerns cleanly:

1. UI for collecting user inputs and showing progress.
2. Application services for validation, orchestration, and reporting.
3. Core simulation logic for dataset loading and OpenDrift execution.

## Generic Terminology

The app should avoid species-specific wording in the main interface.

- `stranding identifier` instead of `turtle_id`
- `taxon label` instead of `species`
- `observation dataset` instead of `turtle spreadsheet`
- `wind drift factor` remains domain-appropriate and generic

## Generalized Product Behavior

The application should default to a portable, user-neutral experience:

- blank or generic field mappings by default
- user-selected absolute paths instead of working-directory assumptions
- reusable presets for legacy compatibility and common study areas
- validation that explains what is missing before any simulation begins

## Proposed Refactor Path

### 1. Notebook extraction

The core package now contains the first generalized extraction of notebook logic:

- `core/duration.py`
- `core/records.py`
- `core/planning.py`
- `core/landmask.py`
- `core/validation.py`
- `core/workflow.py`

The remaining execution-oriented notebook logic should continue moving into modules like:

- `core/io.py`
- `core/environment.py`
- `core/simulation.py`
- `core/reporting.py`

Extracted notebook behavior now includes:

- decomposition-code and SST duration rules
- generic observation canonicalization through user-controlled column mappings
- per-observation reverse-drift iteration planning and output filenames
- spatial extent checks and land-to-nearby-water adjustment without turtle-specific naming
- environmental-reader coverage intersection and buffered automatic bounds
- deterministic observation selection before canonicalization and job planning
- request-driven nearby-water correction before OpenDrift seeding

### 2. Column mapping

The notebook currently expects columns such as:

- `turtle_id`
- `species`
- `decomposition_code`
- `SST`
- `Wind_drift`
- `lon`
- `lat`
- `date_str`
- `time`

The application layer should expose generic field names and map them to source columns through a user-editable or profile-based column map.

The current scaffold already includes:

- a generic marine-fauna preset
- a Fonseca notebook compatibility preset

### 3. Configuration model

Separate:

- observation file paths
- environmental NetCDF file paths
- output directory
- iteration count
- geographic extent
- fallback values
- uncertainty values

The current scaffold also treats path validation as a first-class concern so installed users are not tied to this repository layout.

### 3a. Environmental Reader Inspection

Environmental data must be managed through a flexible reader catalog instead of fixed primary/secondary file slots.

Each added NetCDF reader should be inspected in two stages before it can be used:

1. Metadata inspection with xarray, without loading the complete data array:
   - raw variable names, dimensions, units, and CF `standard_name` attributes
   - longitude/latitude or projected coordinate variables and CRS metadata
   - time coverage, spatial coverage, grid shape, and file size
2. OpenDrift compatibility inspection:
   - variables automatically recognized by the OpenDrift CF reader
   - recognized OpenDrift roles such as currents, SST, wind, waves, Stokes drift, and bathymetry
   - unsupported or ambiguous variables requiring a user mapping override

One reader may provide several roles. For example, a single file containing currents and sea-surface temperature should be selected once and assigned both roles. The reader catalog must support an unlimited number of sources, file patterns, or compatible multi-file time series.

### 3b. Wind-Drift Factor Inputs And Scaling

OpenDrift stores `wind_drift_factor` as a dimensionless fraction of the wind vector. The interface must present a clear user-facing percent value and preserve the internal decimal value:

- `1.5%` in the interface is passed to OpenDrift as `0.015`.
- `0.02` in OpenDrift represents `2%` wind drift.
- Every review, manifest, and run log should display both values, for example `1.5% (0.015 fraction)`.

The app should support three wind-drift modes:

1. `Dataset column`: user chooses a searchable source column and explicitly confirms its scale as either percentage (`0–100`) or decimal fraction (`0–1`). Automatic scale detection may suggest a choice but must require confirmation because values between zero and one are ambiguous.
2. `Animal measurement estimate`: user chooses a measurement column and defines a linear relationship using minimum and maximum measurement thresholds plus their corresponding minimum and maximum wind-drift percentages. The app converts the percentages to fractions, applies linear interpolation, and clearly states whether values outside the measurement range are clamped or extrapolated.
3. `Fixed value`: user enters one wind-drift percentage that is converted to the OpenDrift fraction before execution.

Validation should report source-column minimum/maximum values, detected missing/non-numeric values, selected scale, converted model range, and any implausible fraction values before a run can begin.

### 4. Execution model

The UI should build a `SimulationRequest`, then pass it to an engine service that:

- validates the request
- loads data
- runs the workflow
- streams progress updates
- returns a structured result with output file paths and skipped records

The current scaffold already routes preview behavior through a shared core workflow engine rather than keeping validation rules inside the UI layer.

The execution order is now fixed and shared by GUI and worker: read source rows, apply observation selection, resolve environmental coverage when enabled, canonicalize records, correct land positions when enabled, validate final seed coordinates, plan iterations, and execute atomic batch outputs. This prevents preview, progress counts, and model inputs from using different interpretations of the request.

## UI Direction

The first version should already support:

- visual hierarchy
- branded theming
- multi-panel composition
- future navigation and settings growth

That is why the app is scaffolded with a theme system and separate UI sections now instead of a minimal form-only window.

## Brand Direction

The new visual identity should guide all UI work from this point forward:

- Product name: `Marine Drift Workbench`
- Tagline direction: `Trace drift. Test scenarios. Export evidence.`
- Core attributes: scientific, flexible, trustworthy, reproducible
- Palette: deep navy, ocean blue, muted cyan, sea-glass green, pale sand/off-white, and slate-gray utility states
- Graphic language: bathymetry contours, coastline maps, current vectors, particle trails, source-probability fields, and reproducibility bundles
- UI mood: premium research dashboard, not generic data-entry software

The PySide6 GUI should translate this into dark map-oriented preview areas, pale configuration cards, clear workflow steps, strong primary actions, validation badges, and report/export surfaces.

## Windows Packaging Target

The first downloadable release should be a Windows one-folder installer:

- The installer creates a normal installation directory such as `C:\Program Files\Marine Drift Workbench`.
- The user launches a single app shortcut, while the folder contains the bundled Python runtime, PySide6, scientific packages, model code, and assets.
- This is preferred over a single-file executable for the first release because OpenDrift, NetCDF, NumPy, pandas, and geospatial libraries are large and easier to debug in one-folder form.

Packaging milestones:

1. Build a reproducible local runtime for the app and modeling engine.
2. Produce a one-folder app bundle with PyInstaller or an equivalent packaging tool.
3. Wrap the bundle with an installer such as Inno Setup or NSIS.
4. Add a desktop shortcut, Start Menu entry, app icon, bundled assets, and example configuration.
5. Add smoke tests that launch the installed app and validate a small sample workflow.
