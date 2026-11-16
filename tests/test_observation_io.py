from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from marine_drift_desktop.core.io import read_observation_columns


class ObservationSchemaInspectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1] / ".tmp_tests" / "schema_io"
        self.root.mkdir(parents=True, exist_ok=True)

    def test_csv_schema_inspection_reads_only_the_header(self) -> None:
        dataset = self.root / "header_only.csv"
        dataset.write_text("id,latitude,longitude\n1,-12.5,-38.1\n", encoding="utf-8")

        with patch(
            "marine_drift_desktop.core.io.pd.read_csv",
            return_value=pd.DataFrame(columns=["id", "latitude", "longitude"]),
        ) as read_csv:
            columns = read_observation_columns(dataset)

        self.assertEqual(columns, {"id", "latitude", "longitude"})
        read_csv.assert_called_once_with(dataset.resolve(), nrows=0)

    def test_unchanged_schema_is_reused_without_reading_the_file_again(self) -> None:
        dataset = self.root / "cached.csv"
        dataset.write_text("id,latitude\n1,-12.5\n", encoding="utf-8")

        with patch(
            "marine_drift_desktop.core.io.pd.read_csv",
            return_value=pd.DataFrame(columns=["id", "latitude"]),
        ) as read_csv:
            first = read_observation_columns(dataset)
            second = read_observation_columns(dataset)

        self.assertEqual(first, second)
        self.assertEqual(read_csv.call_count, 1)


if __name__ == "__main__":
    unittest.main()
