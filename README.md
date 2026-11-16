# Marine Drift Workbench

Marine Drift Workbench is a desktop application for configuring and running reproducible reverse-drift simulations using stranding observations and environmental datasets. It provides a graphical interface to an OpenDrift-based modelling workflow, allowing researchers to explore possible offshore origins of stranded marine megafauna.

The workbench accompanies the submitted manuscript by Fonseca et al., *Scalable reverse-drift framework transforms sea turtle strandings into indicators of at-sea mortality in the southwestern Atlantic*. The manuscript presents the wider framework for deriving mortality indicators; the software supports the reverse-drift modelling and trajectory-export components.

## Download

Download the latest available package from [GitHub Releases](https://github.com/GabrielFragaF/Fonseca_Marine_Drift_Workbench/releases). Packages will be listed there when the release is published.

- **Windows x64:** Extract the complete ZIP and run `Install.cmd`. The installer includes Python and the required application dependencies and creates shortcuts.
- **macOS Apple Silicon:** Extract the ZIP and open `Marine Drift Workbench.app`. The current build requires macOS 26 or later. It is not notarized, so macOS may block its first launch. If necessary, use **System Settings > Privacy & Security > Open Anyway** for the downloaded app.

Neither package requires a separate Python installation. Environmental datasets and observation records are not included; users supply their own.

## Workflow

1. Load a CSV, Excel, or Parquet observation dataset and map its fields.
2. Add compatible NetCDF environmental datasets and select their roles.
3. Configure the study area, observations, drift duration, windage, particle release, and model physics.
4. Validate the configuration and run simulations locally. Existing results can be reviewed before resuming or recalculating.
5. Inspect trajectories and export sampled positions and available environmental variables for further analysis.

The application includes a tutorial and saves project configurations separately from the datasets. Results depend on the input data, modelling assumptions, and environmental coverage; users should review validation messages and assess their suitability for the research question.

## Citation

**Associated manuscript:** Fonseca et al. *Scalable reverse-drift framework transforms sea turtle strandings into indicators of at-sea mortality in the southwestern Atlantic*. Submitted manuscript. Publication details will be added when available.

**OpenDrift:** Dagestad, K.-F., Rohrs, J., Breivik, O., and Adlandsvik, B. (2018). OpenDrift v1.0: a generic framework for trajectory modelling. *Geoscientific Model Development*, 11, 1405-1420. [https://doi.org/10.5194/gmd-11-1405-2018](https://doi.org/10.5194/gmd-11-1405-2018).

## Source and license

The source code, tests, and platform build tools are provided in this repository. Source development requires a compatible Python environment and dependencies; see `pyproject.toml` and the scripts in `tools/`. Building the macOS application requires an Apple Silicon Mac.

Marine Drift Workbench is distributed under the [GNU General Public License, version 3 or later](LICENSE). Copyright Gabriel Fraga da Fonseca. Bundled dependencies and assets retain their respective licenses.
