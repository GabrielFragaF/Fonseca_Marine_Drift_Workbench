from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from marine_drift_desktop.core.batch_execution import (
    SimulationBatchResult,
    batch_ranges,
    prepare_observations,
    run_simulation_batches,
)
from marine_drift_desktop.core import batch_execution as batch_execution_module
from marine_drift_desktop.core.planning import plan_simulation_runs
from marine_drift_desktop.core.request_serialization import (
    read_simulation_request,
    simulation_request_to_dict,
    write_simulation_request,
)
from marine_drift_desktop.core.trajectory_provenance import read_trajectory_provenance
from marine_drift_desktop.domain.models import (
    ColumnMapping,
    EnvironmentalReaderConfig,
    SimulationRequest,
)
from marine_drift_desktop.domain import models as domain_models
from tests import results_test_support


class RequestSerializationTests(unittest.TestCase):
    def test_new_requests_have_no_regional_velocity_defaults(self):
        fallback = SimulationRequest().settings.fallback_values
        self.assertFalse(fallback.currents_enabled)
        self.assertFalse(fallback.wind_enabled)
        self.assertFalse(fallback.stokes_drift_enabled)
        self.assertFalse(fallback.seafloor_depth_enabled)
        self.assertEqual(fallback.x_sea_water_velocity, 0.0)
        self.assertEqual(fallback.y_sea_water_velocity, 0.0)
        self.assertEqual(fallback.stokes_drift_x_velocity, 0.0)
        self.assertEqual(fallback.stokes_drift_y_velocity, 0.0)

    def test_uncertainty_flags_and_job_error_policy_round_trip_with_legacy_defaults(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "execution_policy"
        request = SimulationRequest()
        request.settings.current_uncertainty_enabled = False
        request.settings.wind_uncertainty_enabled = False
        request.settings.job_error_policy = "stop"

        restored = read_simulation_request(
            write_simulation_request(request, root / "policy.json")
        )
        self.assertFalse(restored.settings.current_uncertainty_enabled)
        self.assertFalse(restored.settings.wind_uncertainty_enabled)
        self.assertEqual(restored.settings.job_error_policy, "stop")

        legacy_payload = simulation_request_to_dict(SimulationRequest())
        legacy_payload["settings"].pop("current_uncertainty_enabled", None)
        legacy_payload["settings"].pop("wind_uncertainty_enabled", None)
        legacy_payload["settings"].pop("job_error_policy", None)
        legacy_path = root / "legacy.json"
        legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        legacy = read_simulation_request(legacy_path)
        self.assertTrue(legacy.settings.current_uncertainty_enabled)
        self.assertTrue(legacy.settings.wind_uncertainty_enabled)
        self.assertEqual(legacy.settings.job_error_policy, "continue")

    def test_fixed_duration_and_no_windage_round_trip_with_legacy_defaults(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "method_modes"
        request = SimulationRequest()
        request.settings.duration.mode = "fixed"
        request.settings.duration.fixed_days = 6
        request.settings.wind_drift.mode = "none"

        restored = read_simulation_request(
            write_simulation_request(request, root / "methods.json")
        )
        self.assertEqual(restored.settings.duration.mode, "fixed")
        self.assertEqual(restored.settings.duration.fixed_days, 6)
        self.assertEqual(restored.settings.wind_drift.mode, "none")

        legacy_payload = simulation_request_to_dict(SimulationRequest())
        legacy_payload["settings"]["duration"].pop("fixed_days", None)
        legacy_path = root / "legacy.json"
        legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        legacy = read_simulation_request(legacy_path)
        self.assertEqual(legacy.settings.duration.mode, "estimated")
        self.assertEqual(legacy.settings.duration.fixed_days, 7)
        self.assertEqual(legacy.settings.wind_drift.mode, "dataset")

    def test_datetime_mapping_round_trip_and_legacy_defaults(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "datetime_mapping"
        request = SimulationRequest()
        request.column_mapping.datetime_mode = "combined"
        request.column_mapping.observed_datetime = "observed_at"

        restored = read_simulation_request(
            write_simulation_request(request, root / "combined.json")
        )
        self.assertEqual(restored.column_mapping.datetime_mode, "combined")
        self.assertEqual(restored.column_mapping.observed_datetime, "observed_at")

        legacy_payload = simulation_request_to_dict(SimulationRequest())
        legacy_payload["column_mapping"].pop("datetime_mode", None)
        legacy_payload["column_mapping"].pop("observed_datetime", None)
        legacy_path = root / "legacy.json"
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        legacy = read_simulation_request(legacy_path)
        self.assertEqual(legacy.column_mapping.datetime_mode, "separate")
        self.assertEqual(legacy.column_mapping.observed_datetime, "")

    def test_request_round_trip_preserves_paths_nested_settings_and_readers(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "request_roundtrip"
        root.mkdir(parents=True, exist_ok=True)
        request = SimulationRequest()
        request.data_sources.observation_dataset = root / "observations.csv"
        request.data_sources.output_directory = root / "outputs"
        request.data_sources.environment_readers = [
            EnvironmentalReaderConfig(
                root / "currents.nc",
                ["Ocean circulation", "Temperature & hydrography"],
                ["x_sea_water_velocity"],
                role_source="user",
                group_id="cmems-surface",
                priority=2,
            )
        ]
        request.column_mapping = ColumnMapping(
            stranding_identifier="id", taxon_label="taxon", decomposition_code="decomp",
            sea_surface_temperature="sst", wind_drift_factor="windage", longitude="lon",
            latitude="lat", observed_date="date", observed_time="time",
        )
        request.settings.iteration_count = 7
        request.settings.environment_export_variables = ["sea_water_temperature"]
        request.settings.duration.cool_water_days = {2: 9}

        path = write_simulation_request(request, root / "request.json")
        restored = read_simulation_request(path)

        self.assertEqual(restored.data_sources.observation_dataset, request.data_sources.observation_dataset)
        reader = restored.data_sources.environment_readers[0]
        self.assertEqual(
            reader.roles,
            ["Ocean circulation", "Temperature & hydrography"],
        )
        self.assertEqual(reader.role_source, "user")
        self.assertEqual(reader.group_id, "cmems-surface")
        self.assertEqual(reader.priority, 2)
        self.assertEqual(restored.column_mapping.longitude, "lon")
        self.assertEqual(restored.settings.iteration_count, 7)
        self.assertEqual(restored.settings.environment_export_variables, ["sea_water_temperature"])
        self.assertEqual(restored.settings.duration.cool_water_days, {2: 9})

        legacy_payload = simulation_request_to_dict(request)
        legacy_reader = legacy_payload["data_sources"]["environment_readers"][0]
        legacy_reader.pop("role_source")
        legacy_reader.pop("group_id")
        legacy_reader.pop("priority")
        legacy_path = root / "legacy_reader.json"
        legacy_path.write_text(json.dumps(legacy_payload), encoding="utf-8")
        legacy = read_simulation_request(legacy_path).data_sources.environment_readers[0]
        self.assertEqual(legacy.role_source, "needs_review")
        self.assertEqual(legacy.group_id, "")
        self.assertEqual(legacy.priority, 0)

    def test_request_round_trip_preserves_advanced_model_settings(self) -> None:
        root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "advanced_settings"
        request = SimulationRequest()
        self.assertTrue(hasattr(request.settings, "coverage"))
        self.assertTrue(hasattr(request.settings, "position_search"))
        self.assertTrue(hasattr(request.settings, "observation_selection"))

        request.settings.coverage.mode = "environment_intersection"
        request.settings.coverage.buffer_degrees = 0.5
        request.settings.coverage.contributing_paths = ["currents.nc", "wind.nc"]
        request.settings.position_search.mode = "search_nearby_water"
        request.settings.position_search.max_radius_degrees = 0.75
        request.settings.observation_selection.mode = "filter"
        request.settings.observation_selection.random_seed = 42
        request.settings.observation_selection.conditions = [
            domain_models.FilterCondition(
                column="decomp", operator=">=", value=3, connector="and"
            )
        ]

        restored = read_simulation_request(
            write_simulation_request(request, root / "request.json")
        )

        self.assertEqual(restored.settings.coverage.mode, "environment_intersection")
        self.assertEqual(restored.settings.coverage.buffer_degrees, 0.5)
        self.assertEqual(restored.settings.coverage.contributing_paths, ["currents.nc", "wind.nc"])
        self.assertEqual(restored.settings.position_search.max_radius_degrees, 0.75)
        condition = restored.settings.observation_selection.conditions[0]
        self.assertEqual((condition.column, condition.operator, condition.value), ("decomp", ">=", 3))


class BatchExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / ".tmp_tests", prefix="batch_execution-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.root.mkdir(parents=True, exist_ok=True)
        checkpoint = self.root / "outputs" / ".marine_drift_checkpoint.json"
        if checkpoint.exists():
            checkpoint.unlink()

    def _request(self, records: int = 5, iterations: int = 3) -> SimulationRequest:
        dataset = self.root / "observations.csv"
        rows = [
            f"obs-{index},Marine fauna,3,22,0.015,-38,-12,2024-04-13,07:50"
            for index in range(records)
        ]
        dataset.write_text(
            "id,taxon,decomp,sst,windage,lon,lat,date,time\n" + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
        request = SimulationRequest()
        request.data_sources.observation_dataset = dataset
        request.data_sources.output_directory = self.root / "outputs"
        request.column_mapping = ColumnMapping(
            stranding_identifier="id", taxon_label="taxon", decomposition_code="decomp",
            sea_surface_temperature="sst", wind_drift_factor="windage", longitude="lon",
            latitude="lat", observed_date="date", observed_time="time",
        )
        request.settings.iteration_count = iterations
        return request

    def _write_complete_output(self, job) -> None:
        from netCDF4 import Dataset

        job.iteration.output_path.parent.mkdir(parents=True, exist_ok=True)
        with Dataset(job.iteration.output_path, "w") as dataset:
            dataset.createDimension("time", 1)
            dataset.createVariable("lon", "f8", ("time",))[:] = [-38.0]
            dataset.createVariable("lat", "f8", ("time",))[:] = [-12.0]

    def test_global_land_predicate_uses_supported_reader_api(self) -> None:
        predicate = batch_execution_module._global_land_predicate()

        self.assertIsInstance(predicate(-37.2, -12.5), bool)

    def test_real_executor_closes_lazy_result_before_writing_provenance(self) -> None:
        request = self._request(records=1, iterations=1)
        request.settings.wind_drift.mode = "none"
        job = next(batch_execution_module._iter_jobs(
            prepare_observations(request).observations,
            request,
            request.data_sources.output_directory,
        ))

        class LazyResult:
            closed = False

            def close(self):
                self.closed = True

        lazy_result = LazyResult()

        class FakeOceanDrift:
            result = lazy_result

            def __init__(self, **_kwargs): pass
            def add_reader(self, _reader): pass
            def set_config(self, _name, _value): pass
            def seed_elements(self, **_kwargs): pass
            def run(self, *, outfile, **_kwargs):
                results_test_support.make_trajectory_netcdf(Path(outfile), marked=False)

        def assert_closed_before_provenance(*_args, **_kwargs):
            self.assertTrue(lazy_result.closed)

        with patch("opendrift.models.oceandrift.OceanDrift", FakeOceanDrift), patch(
            "marine_drift_desktop.core.batch_execution.write_trajectory_provenance",
            side_effect=assert_closed_before_provenance,
        ):
            batch_execution_module._execute_opendrift_job(job, request, [])

    def test_batch_ranges_continue_seamlessly_after_each_five_thousand(self) -> None:
        self.assertEqual(
            list(batch_ranges(12_001, 5_000)),
            [(1, 0, 5_000), (2, 5_000, 10_000), (3, 10_000, 12_001)],
        )

    def test_exact_duplicate_observations_run_once(self) -> None:
        request = self._request(records=1, iterations=1)
        dataset = request.data_sources.observation_dataset
        assert dataset is not None
        text = dataset.read_text(encoding="utf-8")
        dataset.write_text(text + text.splitlines()[1] + "\n", encoding="utf-8")

        prepared = prepare_observations(request)

        self.assertEqual(len(prepared.observations), 1)
        self.assertEqual(prepared.skip_reasons["Exact duplicate observation row."], 1)

    def test_executor_runs_every_job_across_batches_and_writes_checkpoint(self) -> None:
        executed: list[str] = []
        request = self._request(records=3, iterations=2)

        result = run_simulation_batches(
            request,
            batch_size=2,
            execute_job=lambda job, _request, _readers: executed.append(job.key),
        )

        self.assertIsInstance(result, SimulationBatchResult)
        self.assertEqual(result.total_jobs, 6)
        self.assertEqual(result.completed_jobs, 6)
        self.assertEqual(len(executed), 6)
        self.assertTrue(result.checkpoint_path.exists())

    def test_provenance_failure_does_not_publish_real_executor_output(self) -> None:
        request = self._request(records=1, iterations=1)
        job = next(batch_execution_module._iter_jobs(
            prepare_observations(request).observations,
            request,
            request.data_sources.output_directory,
        ))
        final_path = job.iteration.output_path
        partial_path = final_path.with_name(
            f"{final_path.stem}.partial{final_path.suffix}"
        )
        for path in (final_path, partial_path):
            if path.exists():
                path.unlink()

        class FakeOceanDrift:
            def __init__(self, **_kwargs):
                pass

            def add_reader(self, _reader):
                pass

            def set_config(self, _name, _value):
                pass

            def seed_elements(self, **_kwargs):
                pass

            def run(self, *, outfile, **_kwargs):
                results_test_support.make_trajectory_netcdf(
                    Path(outfile), marked=False
                )

        with patch(
            "opendrift.models.oceandrift.OceanDrift", FakeOceanDrift
        ), patch(
            "marine_drift_desktop.core.batch_execution.write_trajectory_provenance",
            side_effect=RuntimeError("stamp failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stamp failed"):
                batch_execution_module._execute_opendrift_job(
                    job, request, [type("WindReader", (), {"variables": ["x_wind", "y_wind"]})()]
                )

        self.assertTrue(partial_path.exists())
        self.assertFalse(final_path.exists())

    def test_real_executor_passes_selected_environmental_variables_to_opendrift(self) -> None:
        request = self._request(records=1, iterations=1)
        request.settings.environment_export_variables = [
            "sea_water_temperature", "x_wind"
        ]
        request.settings.wind_drift.mode = "none"
        job = next(batch_execution_module._iter_jobs(
            prepare_observations(request).observations,
            request,
            request.data_sources.output_directory,
        ))
        captured: dict[str, object] = {}

        class FakeOceanDrift:
            def __init__(self, **_kwargs): pass
            def add_reader(self, _reader): pass
            def set_config(self, _name, _value): pass
            def seed_elements(self, **_kwargs): pass
            def run(self, *, outfile, export_variables, **_kwargs):
                captured["variables"] = export_variables
                results_test_support.make_trajectory_netcdf(Path(outfile), marked=False)

        with patch("opendrift.models.oceandrift.OceanDrift", FakeOceanDrift):
            batch_execution_module._execute_opendrift_job(job, request, [])

        self.assertEqual(captured["variables"], [
            "status", "lon", "lat", "depth", "time",
            "sea_water_temperature", "x_wind",
        ])

    def test_custom_executor_netcdf_output_remains_unmarked(self) -> None:
        request = self._request(records=1, iterations=1)
        written_paths: list[Path] = []

        def execute(job, _request, _readers):
            results_test_support.make_trajectory_netcdf(
                job.iteration.output_path, marked=False
            )
            written_paths.append(job.iteration.output_path)

        run_simulation_batches(request, execute_job=execute)

        with self.assertRaisesRegex(ValueError, "unmarked"):
            read_trajectory_provenance(written_paths[0])

    def test_disabled_uncertainties_resolve_to_zero_without_losing_values(self) -> None:
        request = self._request(records=1, iterations=1)
        request.settings.current_uncertainty = 0.25
        request.settings.wind_uncertainty = 0.5
        request.settings.current_uncertainty_enabled = False
        request.settings.wind_uncertainty_enabled = True

        current, wind = batch_execution_module.resolve_uncertainty_values(
            request.settings
        )

        self.assertEqual((current, wind), (0.0, 0.5))
        self.assertEqual(request.settings.current_uncertainty, 0.25)

    def test_continue_policy_records_failure_and_runs_remaining_jobs(self) -> None:
        request = self._request(records=3, iterations=1)
        request.settings.job_error_policy = "continue"
        attempted: list[int] = []

        def execute(job, _request, _readers):
            attempted.append(job.global_index)
            if job.global_index == 0:
                raise RuntimeError("synthetic failure")

        result = run_simulation_batches(request, execute_job=execute)

        self.assertEqual(attempted, [0, 1, 2])
        self.assertEqual(result.failed_jobs, 1)
        self.assertEqual(result.completed_jobs, 2)
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["completion_status"], "completed_with_errors")

    def test_stop_policy_checkpoints_failed_job_and_aborts_remaining_jobs(self) -> None:
        request = self._request(records=3, iterations=1)
        request.settings.job_error_policy = "stop"
        failed_output = request.data_sources.output_directory / (
            "obs-0_Marine-fauna_DEC3_DUR4d_01.nc"
        )
        if failed_output.exists():
            failed_output.unlink()
        attempted: list[int] = []

        def execute(job, _request, _readers):
            attempted.append(job.global_index)
            raise RuntimeError("stop here")

        with self.assertRaisesRegex(RuntimeError, "stop here"):
            run_simulation_batches(request, execute_job=execute)

        checkpoint = json.loads(
            (request.data_sources.output_directory / ".marine_drift_checkpoint.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(attempted, [0])
        self.assertEqual(checkpoint["next_job_index"], 1)
        self.assertEqual(checkpoint["failed_jobs"], 1)
        manifest = json.loads(
            (request.data_sources.output_directory / "run_manifest.json")
            .read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["completion_status"], "failed")

        repaired = run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: self._write_complete_output(job),
        )
        repaired_manifest = json.loads(
            repaired.manifest_path.read_text(encoding="utf-8")
        )

        self.assertEqual(repaired.completed_jobs, 3)
        self.assertEqual(repaired.failed_jobs, 0)
        self.assertEqual(repaired.completed_jobs + repaired.failed_jobs, repaired.total_jobs)
        self.assertEqual(repaired.completion_status, "completed")
        self.assertEqual(repaired_manifest["completion_status"], "completed")

    def test_resume_skips_batches_recorded_by_matching_checkpoint(self) -> None:
        request = self._request(records=3, iterations=2)
        first: list[str] = []
        run_simulation_batches(
            request,
            batch_size=2,
            execute_job=lambda job, _request, _readers: (
                first.append(job.key), self._write_complete_output(job),
            ),
        )
        resumed: list[str] = []

        result = run_simulation_batches(
            request,
            batch_size=2,
            execute_job=lambda job, _request, _readers: resumed.append(job.key),
        )

        self.assertEqual(resumed, [])
        self.assertEqual(result.completed_jobs, 6)
        self.assertEqual(result.failed_jobs, 0)
        self.assertEqual(result.existing_jobs, 6)
        self.assertEqual(result.completed_jobs + result.failed_jobs, result.total_jobs)

    def test_explicit_preserve_recognizes_outputs_after_configuration_change(self):
        request = self._request(records=3, iterations=1)
        def write(job, request, readers):
            self._write_complete_output(job)
            batch_execution_module.write_trajectory_provenance(
                job.iteration.output_path, job.observation, job.iteration, request)
        run_simulation_batches(request, execute_job=write)
        request.settings.current_uncertainty_enabled = False
        executed, reviews, events = [], [], []
        result = run_simulation_batches(
            request, execute_job=lambda job, *_: executed.append(job.key),
            existing_output_decision=lambda review: (reviews.append(review) or "preserve"),
            progress_callback=events.append)
        self.assertEqual(executed, [])
        self.assertEqual(result.existing_jobs, 3)
        self.assertEqual(reviews[0]["completed"], 3)
        self.assertTrue(reviews[0]["configuration_changed"])
        self.assertEqual(next(e for e in events if e["event"] == "workload")["resume_index"], 3)

    def test_explicit_overwrite_and_cancel(self):
        request = self._request(records=1, iterations=1)
        run_simulation_batches(request, execute_job=lambda job, *_: self._write_complete_output(job))
        executed = []
        with self.assertRaisesRegex(ValueError, "cancelled"):
            run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                                   existing_output_decision=lambda _: "cancel")
        self.assertEqual(executed, [])
        run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                               existing_output_decision=lambda _: "overwrite")
        self.assertEqual(len(executed), 1)

    def test_preserve_runs_only_missing_or_corrupt_jobs_without_checkpoint(self):
        request = self._request(records=3, iterations=1)
        def write(job, request, readers):
            self._write_complete_output(job)
            batch_execution_module.write_trajectory_provenance(
                job.iteration.output_path, job.observation, job.iteration, request)
        run_simulation_batches(request, execute_job=write)
        jobs = list(batch_execution_module._iter_jobs(
            prepare_observations(request).observations, request, request.data_sources.output_directory))
        jobs[0].iteration.output_path.unlink()
        jobs[1].iteration.output_path.write_bytes(b"corrupt")
        (request.data_sources.output_directory / ".marine_drift_checkpoint.json").unlink()
        executed = []
        result = run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                                       existing_output_decision=lambda _: "preserve")
        self.assertEqual(executed, [jobs[0].key, jobs[1].key])
        self.assertEqual(result.existing_jobs, 1)
        self.assertEqual(result.completed_jobs, 3)

    def test_preserve_refuses_unidentified_valid_files(self):
        request = self._request(records=1, iterations=1)
        run_simulation_batches(request, execute_job=lambda job, *_: self._write_complete_output(job))
        executed = []
        with self.assertRaisesRegex(ValueError, "identified safely"):
            run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                                   existing_output_decision=lambda _: "preserve")
        self.assertEqual(executed, [])

    def test_overwrite_archives_old_names_before_recalculation(self):
        request = self._request(records=1, iterations=1)
        def write(job, request, readers):
            self._write_complete_output(job)
            batch_execution_module.write_trajectory_provenance(
                job.iteration.output_path, job.observation, job.iteration, request)
            job.iteration.output_path.rename(job.iteration.output_path.with_name("renamed.nc"))
        run_simulation_batches(request, execute_job=write)
        executed = []
        run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                               existing_output_decision=lambda _: "overwrite")
        output = request.data_sources.output_directory
        self.assertEqual(len(executed), 1)
        self.assertFalse((output / "renamed.nc").exists())
        self.assertEqual(len(list((output / ".marine_drift_history").glob("*/renamed.nc"))), 1)

    def test_preserve_recognizes_renamed_output(self):
        request = self._request(records=1, iterations=1)
        def write(job, request, readers):
            self._write_complete_output(job)
            batch_execution_module.write_trajectory_provenance(
                job.iteration.output_path, job.observation, job.iteration, request)
            job.iteration.output_path.rename(job.iteration.output_path.with_name("renamed.nc"))
        run_simulation_batches(request, execute_job=write)
        executed = []
        result = run_simulation_batches(request, execute_job=lambda job, *_: executed.append(job.key),
                                       existing_output_decision=lambda _: "preserve")
        self.assertEqual(executed, [])
        self.assertEqual(result.existing_jobs, 1)

    def test_resume_reruns_missing_and_corrupt_outputs_inside_checkpoint_boundary(self) -> None:
        request = self._request(records=3, iterations=1)
        run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: self._write_complete_output(job),
        )
        jobs = list(batch_execution_module._iter_jobs(
            prepare_observations(request).observations,
            request,
            request.data_sources.output_directory,
        ))
        jobs[0].iteration.output_path.unlink()
        jobs[1].iteration.output_path.write_bytes(b"corrupt")
        rerun: list[str] = []

        result = run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: (
                rerun.append(job.key), self._write_complete_output(job),
            ),
        )

        self.assertEqual(rerun, ["obs-0:1", "obs-1:1"])
        self.assertEqual(result.completed_jobs, 3)
        self.assertEqual(result.failed_jobs, 0)
        self.assertEqual(result.existing_jobs, 1)
        self.assertEqual(result.completed_jobs + result.failed_jobs, result.total_jobs)

    def test_resume_reruns_valid_output_beyond_checkpoint_boundary(self) -> None:
        request = self._request(records=3, iterations=1)
        observations = prepare_observations(request).observations
        jobs = list(batch_execution_module._iter_jobs(
            observations,
            request,
            request.data_sources.output_directory,
        ))
        self._write_complete_output(jobs[0])
        self._write_complete_output(jobs[2])
        checkpoint = request.data_sources.output_directory / ".marine_drift_checkpoint.json"
        checkpoint.write_text(json.dumps({
            "request_fingerprint": batch_execution_module._request_fingerprint(request),
            "next_job_index": 1,
            "completed_jobs": 1,
            "failed_jobs": 0,
            "existing_jobs": 0,
            "total_jobs": 3,
        }), encoding="utf-8")
        rerun: list[str] = []

        run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: (
                rerun.append(job.key), self._write_complete_output(job),
            ),
        )

        self.assertEqual(rerun, ["obs-1:1", "obs-2:1"])

    def test_partial_output_is_not_treated_as_completed(self) -> None:
        request = self._request(records=1, iterations=1)
        output_path = request.data_sources.output_directory / (
            "obs-0-Marine-fauna_DEC3_DUR4d_01.nc"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"partial netcdf")
        executed: list[str] = []

        result = run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: executed.append(job.key),
        )

        self.assertEqual(executed, ["obs-0:1"])
        self.assertEqual(result.completed_jobs, 1)

    def test_output_name_collisions_abort_before_any_job_executes(self) -> None:
        request = self._request(records=2, iterations=1)
        source = request.data_sources.observation_dataset
        assert source is not None
        source.write_text(
            "id,taxon,decomp,sst,windage,lon,lat,date,time\n"
            "same id,Marine fauna,3,22,0.015,-38,-12,2026-01-03,10:00\n"
            "same-id,Marine fauna,3,22,0.015,-38,-12,2026-01-03,10:00\n",
            encoding="utf-8",
        )
        executed: list[str] = []

        with self.assertRaisesRegex(ValueError, "Output-name collision"):
            run_simulation_batches(
                request,
                execute_job=lambda job, _request, _readers: executed.append(job.key),
            )

        self.assertEqual(executed, [])

    def test_collision_validation_checks_every_iteration_namespace(self) -> None:
        request = self._request(records=1, iterations=3)

        def duplicate_iteration_path(observation, settings, output_directory):
            plans = plan_simulation_runs(observation, settings, output_directory)
            plans[1].output_path = plans[0].output_path
            return plans

        def split_iteration_namespace(observation, settings, output_directory):
            plans = plan_simulation_runs(observation, settings, output_directory)
            plans[1].output_path = plans[1].output_path.with_name("other_02.nc")
            return plans

        for malformed_planner in (
            duplicate_iteration_path,
            split_iteration_namespace,
        ):
            with self.subTest(planner=malformed_planner.__name__), patch(
                "marine_drift_desktop.core.batch_execution.plan_simulation_runs",
                side_effect=malformed_planner,
            ):
                with self.assertRaisesRegex(ValueError, "Output planner invariant"):
                    run_simulation_batches(request, execute_job=lambda *_: None)

    def test_valid_stale_output_is_replaced_without_matching_checkpoint(self) -> None:
        request = self._request(records=1, iterations=1)
        output_path = request.data_sources.output_directory / (
            "obs-0_Marine-fauna_DEC3_DUR4d_01.nc"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        from netCDF4 import Dataset

        with Dataset(output_path, "w") as dataset:
            dataset.createDimension("time", 1)
            dataset.createVariable("lon", "f8", ("time",))[:] = [-38.0]
            dataset.createVariable("lat", "f8", ("time",))[:] = [-12.0]
        executed: list[str] = []

        result = run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: executed.append(job.key),
        )

        self.assertEqual(executed, ["obs-0:1"])
        self.assertEqual(result.completed_jobs, 1)
        self.assertEqual(result.existing_jobs, 0)

    def test_filter_selection_is_applied_before_observation_preparation(self) -> None:
        request = self._request(records=3, iterations=1)
        request.settings.observation_selection.mode = "filter"
        request.settings.observation_selection.conditions = [
            domain_models.FilterCondition(
                column="id", operator="equals", value="obs-1"
            )
        ]

        result = prepare_observations(request)

        self.assertEqual(result.source_rows, 3)
        self.assertEqual(result.selected_rows, 1)
        self.assertEqual(
            [item.stranding_identifier for item in result.observations], ["obs-1"]
        )

    def test_direct_position_mode_does_not_call_land_predicate(self) -> None:
        request = self._request(records=1, iterations=1)
        request.settings.position_search.mode = "direct"

        result = prepare_observations(
            request,
            is_land=lambda *_: (_ for _ in ()).throw(
                AssertionError("unexpected land query")
            ),
        )

        self.assertEqual(len(result.observations), 1)
        self.assertEqual(result.positions_adjusted, 0)

    def test_batch_adjusts_land_positions_before_execution(self) -> None:
        request = self._request(records=1, iterations=1)
        request.settings.position_search.mode = "search_nearby_water"
        request.settings.position_search.radial_step_degrees = 0.01
        seeded_longitudes: list[float] = []

        preparation = prepare_observations(
            request,
            is_land=lambda longitude, _latitude: longitude == -38.0,
        )
        run_simulation_batches(
            request,
            execute_job=lambda job, _request, _readers: seeded_longitudes.append(
                job.observation.longitude
            ),
            is_land=lambda longitude, _latitude: longitude == -38.0,
        )

        self.assertEqual(preparation.positions_adjusted, 1)
        self.assertNotEqual(preparation.observations[0].longitude, -38.0)
        self.assertEqual(seeded_longitudes, [preparation.observations[0].longitude])


if __name__ == "__main__":
    unittest.main()
