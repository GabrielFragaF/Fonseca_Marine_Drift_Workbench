from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd


def load_observation_table(path: Path) -> pd.DataFrame:
    """Load a supported observation table without relying on notebook state."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    raise ValueError(
        "Observation datasets must use CSV, Excel, or Parquet format."
    )


def read_observation_columns(path: Path) -> set[str]:
    resolved = path.resolve()
    stat = resolved.stat()
    return set(
        _read_observation_columns_cached(
            str(resolved),
            stat.st_mtime_ns,
            stat.st_size,
        )
    )


@lru_cache(maxsize=16)
def _read_observation_columns_cached(
    path_text: str,
    modified_at_ns: int,
    file_size: int,
) -> tuple[str, ...]:
    """Read schema metadata only and invalidate when the source file changes."""

    del modified_at_ns, file_size
    path = Path(path_text)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        columns = pd.read_csv(path, nrows=0).columns
    elif suffix in {".xlsx", ".xls"}:
        columns = pd.read_excel(path, nrows=0).columns
    elif suffix == ".parquet":
        columns = _read_parquet_columns(path)
    else:
        raise ValueError(
            "Observation datasets must use CSV, Excel, or Parquet format."
        )
    return tuple(str(column) for column in columns)


def _read_parquet_columns(path: Path) -> list[str]:
    try:
        import pyarrow.parquet as parquet

        return list(parquet.read_schema(path).names)
    except ImportError:
        try:
            from fastparquet import ParquetFile

            return list(ParquetFile(path).columns)
        except ImportError:
            return [str(column) for column in pd.read_parquet(path).columns]


def read_observation_records(path: Path) -> list[dict[str, object]]:
    return load_observation_table(path).to_dict(orient="records")


def read_observation_values(path: Path, column: str) -> list[object]:
    """Read distinct non-empty values from one mapped observation column."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        series = pd.read_csv(path, usecols=[column])[column]
    elif suffix in {".xlsx", ".xls"}:
        series = pd.read_excel(path, usecols=[column])[column]
    elif suffix == ".parquet":
        series = pd.read_parquet(path, columns=[column])[column]
    else:
        raise ValueError("Observation datasets must use CSV, Excel, or Parquet format.")
    return list(dict.fromkeys(value for value in series.dropna().tolist() if str(value).strip()))
