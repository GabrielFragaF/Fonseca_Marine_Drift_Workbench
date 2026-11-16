"""Exercise the executable with developer Python paths removed."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.stdout.reconfigure(errors='replace')

exe = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
env = {key: value for key, value in os.environ.items()
       if not key.upper().startswith(('PYTHON', 'CONDA', 'PROJ', 'GDAL', 'QT_'))}
env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
env['QT_QPA_PLATFORM'] = 'offscreen'
result = subprocess.run([str(exe), '--self-test', str(output)], cwd=output,
                        env=env, capture_output=True, timeout=240)
print('Self-test exit:', result.returncode)
print(result.stderr.decode('utf-8', errors='replace')[-5000:])
report_path = output / 'installation-check.json'
if not report_path.exists():
    raise SystemExit('No self-test report was produced')
report = json.loads(report_path.read_text(encoding='utf-8'))
print(json.dumps(report, indent=2))
assert result.returncode == 0 and report['success']
for args, prefix in ((['--simulation-worker', 'missing.json'], 'MARINE_DRIFT_EVENT='),
                     (['--results-worker', 'inspect', 'missing.json'], 'MARINE_DRIFT_RESULTS_EVENT=')):
    worker = subprocess.run([str(exe), *args], cwd=output, env=env,
                            capture_output=True, timeout=60)
    message = worker.stdout.decode('utf-8', errors='replace')
    assert worker.returncode == 1 and prefix in message and 'fatal' in message, message
    print('Worker error/progress pipe verified:', args[0])

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.results_test_support import make_results_fixture
from marine_drift_desktop.core.results_serialization import write_results_export_request
from marine_drift_desktop.core.request_serialization import write_simulation_request
from marine_drift_desktop.domain.models import SimulationRequest, ColumnMapping, EnvironmentalReaderConfig
import numpy as np
import pandas as pd
import xarray as xr

production = output / 'production-example'
production.mkdir()
with xr.open_dataset(output / 'example_forcing.nc') as dataset:
    base = dataset.isel(time=0, drop=True).load()
times = np.datetime64('2024-04-12T00:00', 'ns') + np.arange(40).astype('timedelta64[h]')
forcing = base.expand_dims(time=times)
forcing.time.attrs['standard_name'] = 'time'
forcing_path = production / 'currents.nc'
forcing.to_netcdf(forcing_path)
observations = production / 'observations.csv'
pd.DataFrame([dict(id='example-001', taxon='Marine fauna', decomposition=3,
                   lon=-37.2, lat=-12.5, date='2024-04-13', time='12:00')]).to_csv(observations, index=False)
simulation = SimulationRequest()
simulation.data_sources.observation_dataset = observations
simulation.data_sources.output_directory = production / 'results'
simulation.data_sources.environment_readers = [EnvironmentalReaderConfig(forcing_path, roles=['currents'])]
simulation.column_mapping = ColumnMapping(stranding_identifier='id', taxon_label='taxon',
    decomposition_code='decomposition', longitude='lon', latitude='lat', observed_date='date', observed_time='time')
simulation.settings.duration.mode = 'fixed'
simulation.settings.duration.fixed_days = 1
simulation.settings.wind_drift.mode = 'none'
simulation.settings.iteration_count = 1
simulation.settings.particle_count = 2
simulation.settings.current_uncertainty_enabled = False
simulation.settings.wind_uncertainty_enabled = False
# This synthetic fixture supplies only currents, not waves or bathymetry.
simulation.settings.fallback_values.stokes_drift_enabled = True
simulation.settings.fallback_values.seafloor_depth_enabled = True
simulation_path = write_simulation_request(simulation, production / 'request.json')
for resumed in (False, True):
    worker = subprocess.run([str(exe), '--simulation-worker', str(simulation_path)],
                            cwd=output, env=env, capture_output=True, timeout=120,
                            input=b'{"decision":"preserve"}\n')
    message = worker.stdout.decode('utf-8', errors='replace')
    events = [json.loads(line.split('=', 1)[1]) for line in message.splitlines() if line.startswith('MARINE_DRIFT_EVENT=')]
    assert worker.returncode == 0 and events[-1]['event'] == 'finished', message
    assert events[-1]['failed'] == 0 and events[-1]['total_jobs'] == 1, message
    assert events[-1]['existing' if resumed else 'completed'] == 1, message
    print('Production reverse-drift worker verified; resumed:', resumed)

request = make_results_fixture(output / 'weighted-export')
request_path = write_results_export_request(request, output / 'export-request.json')
for operation in ('inspect', 'export'):
    worker = subprocess.run([str(exe), '--results-worker', operation, str(request_path)],
                            cwd=output, env=env, capture_output=True, timeout=120)
    message = worker.stdout.decode('utf-8', errors='replace')
    assert worker.returncode == 0 and 'fatal' not in message, message + worker.stderr.decode('utf-8', errors='replace')
    print('Frozen results worker succeeded:', operation)
