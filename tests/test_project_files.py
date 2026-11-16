import json
import tempfile
import unittest
from pathlib import Path

from marine_drift_desktop.core.project_files import (
    PROJECT_FORMAT,
    ProjectDocument,
    ProjectFileError,
    read_project,
    write_project,
)
from marine_drift_desktop.domain.models import EnvironmentalReaderConfig, SimulationRequest


class ProjectFileTests(unittest.TestCase):
    def test_round_trip_preserves_configuration_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = SimulationRequest()
            request.data_sources.observation_dataset = root / "observations.csv"
            request.data_sources.output_directory = root / "results"
            request.data_sources.environment_readers = [
                EnvironmentalReaderConfig(
                    path=root / "currents.nc",
                    roles=["Ocean circulation"],
                    priority=2,
                )
            ]
            request.settings.model_time_step_hours = 0.5

            path = write_project(ProjectDocument("Atlantic survey", request), root / "survey.mdwproj")
            restored = read_project(path)

            self.assertEqual(restored.name, "Atlantic survey")
            self.assertEqual(restored.request, request)

    def test_project_envelope_contains_configuration_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_project(
                ProjectDocument("Survey", SimulationRequest()),
                Path(directory) / "survey.mdwproj",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["format"], PROJECT_FORMAT)
            self.assertEqual(set(payload), {"format", "version", "name", "configuration"})

    def test_unsupported_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.mdwproj"
            path.write_text(json.dumps({
                "format": PROJECT_FORMAT,
                "version": 99,
                "name": "Future",
                "configuration": {},
            }), encoding="utf-8")

            with self.assertRaisesRegex(ProjectFileError, "version"):
                read_project(path)

    def test_invalid_json_is_reported_as_project_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.mdwproj"
            path.write_text("not json", encoding="utf-8")

            with self.assertRaises(ProjectFileError):
                read_project(path)


if __name__ == "__main__":
    unittest.main()
