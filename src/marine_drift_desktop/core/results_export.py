from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import os
import uuid
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..domain.results import ResultsExportPaths, ResultsExportRequest
from .results_inspection import (
    ResultsInspection,
    inspect_results_directory,
    validate_sampling_capacity,
)
from .results_source import SourceObservationLookup, load_source_observation_lookup
from .trajectory_sampling import _GENERATED_FIELDS, iter_sampled_positions


EXCEL_MAX_DATA_ROWS = 1_048_575
_ROW_BUFFER_SIZE = 4_096
ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]


class ResultsExportCancelled(RuntimeError):
    """Raised when a results export is cancelled at a safe batch boundary."""


@dataclass(frozen=True, slots=True)
class ResultsExportResult:
    paths: ResultsExportPaths
    row_count: int
    accepted_files: int
    failed_files: int
    omitted_positions: int
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ExtractionResult:
    path: Path
    counts: Mapping[str, int]
    row_count: int
    accepted_files: int
    failed_files: int
    omitted_positions: int
    diagnostics: tuple[dict[str, str], ...]


def generate_mortality_positions(
    request: ResultsExportRequest,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ResultsExportResult:
    """Generate a canonical weighted Parquet and optional derived formats."""
    request.validate()
    _validate_output_basename(request.output_basename)
    request.output_directory.mkdir(parents=True, exist_ok=True)
    operation = uuid.uuid4().hex
    unweighted = request.output_directory / f".{request.output_basename}.{operation}.unweighted.partial.parquet"
    weighted_partial = request.output_directory / f".{request.output_basename}.{operation}.weighted.partial.parquet"
    temporary_paths = {unweighted, weighted_partial}

    try:
        _check_cancel(cancel_check)
        _emit(progress_callback, "inspecting", files=0, rows=0)
        inspection = inspect_results_directory(
            request.results_directory,
            observation_dataset_override=request.observation_dataset_override,
        )
        validate_sampling_capacity(inspection, request.positions_per_drift_day)
        source_path = request.observation_dataset_override or inspection.observation_dataset
        source_lookup = load_source_observation_lookup(source_path, inspection.identifier_column)
        extraction = _write_unweighted_batches(
            request,
            inspection,
            source_lookup,
            unweighted,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        _write_weighted_parquet(
            extraction.path,
            extraction.counts,
            weighted_partial,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        unweighted.unlink(missing_ok=True)
        temporary_paths.discard(unweighted)
        return _convert_and_finalize(
            weighted_partial,
            extraction,
            request,
            inspection,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    except Exception:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        raise


def _write_unweighted_batches(
    request: ResultsExportRequest,
    inspection: ResultsInspection,
    source_lookup: SourceObservationLookup,
    output_path: Path,
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> _ExtractionResult:
    schema, source_fields = _export_schema(
        source_lookup, request.environmental_variables, inspection
    )
    writer = pq.ParquetWriter(output_path, schema, compression="zstd")
    counts: Counter[str] = Counter()
    diagnostics: list[dict[str, str]] = [
        {"kind": "inspection", "source": str(issue.path), "message": issue.message}
        for issue in inspection.issues
    ]
    failed_files = len(inspection.issues)
    accepted_files = 0
    omitted_positions = 0
    row_count = 0
    try:
        for file_number, metadata in enumerate(inspection.files, start=1):
            _check_cancel(cancel_check)
            file_path = output_path.with_name(
                f".{output_path.name}.{file_number}.file.partial.parquet"
            )
            try:
                file_counts, file_rows, file_omitted, file_diagnostics = _stage_file_rows(
                    metadata,
                    request,
                    source_lookup,
                    file_path,
                    schema,
                    source_fields,
                    cancel_check=cancel_check,
                )
                staged = pq.ParquetFile(file_path)
                try:
                    for batch in staged.iter_batches(batch_size=_ROW_BUFFER_SIZE):
                        writer.write_batch(batch)
                finally:
                    staged.close()
                counts.update(file_counts)
                row_count += file_rows
                omitted_positions += file_omitted
                diagnostics.extend(file_diagnostics)
                accepted_files += 1
            except ResultsExportCancelled:
                raise
            except (OSError, RuntimeError, ValueError) as exc:
                failed_files += 1
                diagnostics.append({
                    "kind": "file_failure",
                    "source": str(metadata.path),
                    "message": str(exc),
                })
            finally:
                file_path.unlink(missing_ok=True)
            _emit(progress_callback, "extracting", files=file_number, rows=row_count)
    finally:
        writer.close()

    if row_count == 0:
        output_path.unlink(missing_ok=True)
        failures = [
            item["message"]
            for item in diagnostics
            if item.get("kind") == "file_failure"
        ]
        if failures:
            raise ValueError(
                "No valid mortality positions were retained for export: "
                + failures[0]
            )
        raise ValueError("No valid mortality positions were retained for export.")
    return _ExtractionResult(
        path=output_path,
        counts=dict(counts),
        row_count=row_count,
        accepted_files=accepted_files,
        failed_files=failed_files,
        omitted_positions=omitted_positions,
        diagnostics=tuple(diagnostics),
    )


def _write_weighted_parquet(
    unweighted_path: Path,
    counts: Mapping[str, int],
    output_path: Path,
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> Path:
    source = pq.ParquetFile(unweighted_path)
    output_schema = source.schema_arrow.append(pa.field("weight", pa.float64()))
    writer = pq.ParquetWriter(output_path, output_schema, compression="zstd")
    weighted_rows = 0
    remaining = Counter(counts)
    assigned: defaultdict[str, float] = defaultdict(float)
    try:
        for batch in source.iter_batches(batch_size=_ROW_BUFFER_SIZE):
            _check_cancel(cancel_check)
            identifiers = batch.column(batch.schema.get_field_index("stranding_identifier")).to_pylist()
            observed = batch.column(batch.schema.get_field_index("observed_at")).to_pylist()
            values: list[float] = []
            for value, observed_at in zip(identifiers, observed, strict=True):
                event_key = _weight_group_key(value, observed_at)
                if remaining[event_key] == 1:
                    weight = 1.0 - assigned[event_key]
                else:
                    weight = 1.0 / counts[event_key]
                values.append(weight)
                assigned[event_key] += weight
                remaining[event_key] -= 1
            weights = pa.array(values, type=pa.float64())
            table = pa.Table.from_batches([batch]).append_column("weight", weights)
            writer.write_table(table)
            weighted_rows += batch.num_rows
            _emit(progress_callback, "weighting", rows=weighted_rows)
    finally:
        writer.close()
    return output_path


def _convert_and_finalize(
    parquet_source: Path,
    extraction: _ExtractionResult,
    request: ResultsExportRequest,
    inspection: ResultsInspection,
    *,
    progress_callback: ProgressCallback | None,
    cancel_check: CancelCheck | None,
) -> ResultsExportResult:
    parquet_path = request.output_directory / f"{request.output_basename}.parquet"
    operation = uuid.uuid4().hex
    csv_ready = request.output_directory / f".{request.output_basename}.{operation}.ready.csv"
    xlsx_ready = request.output_directory / f".{request.output_basename}.{operation}.ready.xlsx"
    failures_ready = request.output_directory / f".{request.output_basename}.{operation}.ready.failures.csv"
    manifest_ready = request.output_directory / f".{request.output_basename}.{operation}.ready.manifest.json"
    ready_paths = {csv_ready, xlsx_ready, failures_ready, manifest_ready}
    warnings: list[str] = []
    csv_path: Path | None = None
    xlsx_path: Path | None = None
    if any(item["kind"] == "missing_source" for item in extraction.diagnostics):
        warnings.append("One or more trajectories had no matching source observation row.")
    if extraction.failed_files:
        warnings.append(f"{extraction.failed_files} trajectory file(s) could not be exported.")
    if extraction.omitted_positions:
        warnings.append(f"{extraction.omitted_positions} invalid position(s) were omitted.")
    for name in request.environmental_variables:
        descriptor = inspection.environmental_variables.get(name)
        available = descriptor.available_file_count if descriptor is not None else 0
        if available < inspection.accepted_file_count:
            warnings.append(
                f"Environmental variable `{name}` was available in {available} of "
                f"{inspection.accepted_file_count} trajectory files; unavailable values are null."
            )

    if request.write_csv:
        _check_cancel(cancel_check)
        try:
            csv_path = request.output_directory / f"{request.output_basename}.csv"
            convert_parquet_to_csv(parquet_source, csv_ready, cancel_check=cancel_check)
            _emit(progress_callback, "converting_csv", rows=extraction.row_count)
        except ResultsExportCancelled:
            for path in ready_paths:
                path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            csv_path = None
            warnings.append(f"CSV was not generated: {exc}")

    if request.write_xlsx:
        if extraction.row_count > EXCEL_MAX_DATA_ROWS:
            warnings.append("XLSX was not generated: result exceeds Excel row limit.")
        else:
            _check_cancel(cancel_check)
            try:
                xlsx_path = request.output_directory / f"{request.output_basename}.xlsx"
                convert_parquet_to_xlsx(parquet_source, xlsx_ready, cancel_check=cancel_check)
                _emit(progress_callback, "converting_xlsx", rows=extraction.row_count)
            except ResultsExportCancelled:
                for path in ready_paths:
                    path.unlink(missing_ok=True)
                raise
            except Exception as exc:
                xlsx_path = None
                warnings.append(f"XLSX was not generated: {exc}")

    failures_path = None
    if extraction.diagnostics or extraction.omitted_positions:
        failures_path = request.output_directory / "mortality_position_export_failures.csv"
        diagnostics = list(extraction.diagnostics)
        if extraction.omitted_positions:
            diagnostics.append({
                "kind": "omitted_positions",
                "source": "trajectory coordinates",
                "message": f"{extraction.omitted_positions} masked or non-finite positions were omitted.",
            })
        _write_diagnostics(failures_ready, diagnostics)

    manifest_path = request.output_directory / f"{request.output_basename}_manifest.json"
    paths = ResultsExportPaths(
        parquet=parquet_path,
        csv=csv_path,
        xlsx=xlsx_path,
        failures=failures_path,
        manifest=manifest_path,
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "positions_per_drift_day": request.positions_per_drift_day,
            "results_directory": str(request.results_directory),
            "observation_dataset": str(request.observation_dataset_override or inspection.observation_dataset),
            "environmental_variables": list(request.environmental_variables),
        },
        "environmental_variables": {
            name: {
                "units": inspection.environmental_variables[name].units,
                "long_name": inspection.environmental_variables[name].long_name,
                "standard_name": inspection.environmental_variables[name].standard_name,
                "available_file_count": inspection.environmental_variables[name].available_file_count,
                "total_file_count": inspection.accepted_file_count,
            }
            for name in request.environmental_variables
            if name in inspection.environmental_variables
        },
        "trajectory_fallback_configurations": [
            json.loads(value)
            for value in sorted({
                json.dumps(file.provenance.fallback_values, sort_keys=True)
                for file in inspection.files
                if file.provenance.fallback_values
            })
        ],
        "row_count": extraction.row_count,
        "accepted_files": extraction.accepted_files,
        "failed_files": extraction.failed_files,
        "omitted_positions": extraction.omitted_positions,
        "paths": {
            "parquet": str(parquet_path),
            "csv": str(csv_path) if csv_path else None,
            "xlsx": str(xlsx_path) if xlsx_path else None,
            "failures": str(failures_path) if failures_path else None,
        },
        "warnings": warnings,
        "software_versions": _software_versions(),
    }
    try:
        _atomic_write_json(manifest_ready, manifest)
        _check_cancel(cancel_check)
        os.replace(parquet_source, parquet_path)
        if csv_path is not None:
            os.replace(csv_ready, csv_path)
        if xlsx_path is not None:
            os.replace(xlsx_ready, xlsx_path)
        if failures_path is not None:
            os.replace(failures_ready, failures_path)
        os.replace(manifest_ready, manifest_path)
    except Exception:
        for path in ready_paths:
            path.unlink(missing_ok=True)
        raise
    _emit(
        progress_callback,
        "complete",
        rows=extraction.row_count,
        files=extraction.accepted_files,
    )
    return ResultsExportResult(
        paths=paths,
        row_count=extraction.row_count,
        accepted_files=extraction.accepted_files,
        failed_files=extraction.failed_files,
        omitted_positions=extraction.omitted_positions,
        warnings=tuple(warnings),
    )


def convert_parquet_to_csv(
    parquet_path: Path,
    output_path: Path,
    *,
    cancel_check: CancelCheck | None = None,
) -> Path:
    partial = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.partial")
    source = pq.ParquetFile(parquet_path)
    wrote_header = False
    try:
        for batch in source.iter_batches(batch_size=_ROW_BUFFER_SIZE):
            _check_cancel(cancel_check)
            batch.to_pandas().to_csv(
                partial,
                mode="a" if wrote_header else "w",
                header=not wrote_header,
                index=False,
                encoding="utf-8",
            )
            wrote_header = True
        os.replace(partial, output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return output_path


def convert_parquet_to_xlsx(
    parquet_path: Path,
    output_path: Path,
    *,
    cancel_check: CancelCheck | None = None,
) -> Path:
    from openpyxl import Workbook

    partial = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.partial")
    source = pq.ParquetFile(parquet_path)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Mortality positions")
    sheet.append(source.schema_arrow.names)
    try:
        for batch in source.iter_batches(batch_size=_ROW_BUFFER_SIZE):
            _check_cancel(cancel_check)
            for row in zip(*(column.to_pylist() for column in batch.columns)):
                sheet.append([_excel_value(value) for value in row])
        workbook.save(partial)
        os.replace(partial, output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return output_path


def _export_schema(
    source_lookup: SourceObservationLookup,
    environmental_variables: list[str],
    inspection: ResultsInspection,
) -> tuple[pa.Schema, Mapping[str, pa.DataType]]:
    fields = [
        pa.field("stranding_identifier", pa.string()),
        pa.field("taxon_label", pa.string()),
        pa.field("decomposition_code", pa.int64()),
        pa.field("decomposition_state", pa.string()),
        pa.field("observed_at", pa.string()),
        pa.field("drift_duration_days", pa.int64()),
        pa.field("simulation_iteration", pa.int64()),
        pa.field("particle_index", pa.int64()),
        pa.field("sample_index", pa.int64()),
        pa.field("positions_per_drift_day", pa.int64()),
        pa.field("drift_day", pa.int64()),
        pa.field("hours_before_stranding", pa.float64()),
        pa.field("actual_time", pa.string()),
        pa.field("mortality_longitude", pa.float64()),
        pa.field("mortality_latitude", pa.float64()),
        pa.field("status", pa.int64()),
        pa.field("source_file", pa.string()),
    ]
    for name in environmental_variables:
        descriptor = inspection.environmental_variables.get(name)
        metadata = None if descriptor is None else {
            key.encode("utf-8"): value.encode("utf-8")
            for key, value in {
                "units": descriptor.units,
                "long_name": descriptor.long_name,
                "standard_name": descriptor.standard_name,
            }.items()
            if value
        }
        fields.append(pa.field(name, pa.float64(), metadata=metadata))
    used = set(_GENERATED_FIELDS) | set(environmental_variables)
    source_fields: dict[str, pa.DataType] = {}
    for column in source_lookup.columns:
        output_name = str(column)
        while output_name in used:
            output_name = f"source_{output_name}"
        used.add(output_name)
        values = [row.get(column) for row in source_lookup.values()]
        field_type = _infer_arrow_type(values)
        source_fields[output_name] = field_type
        fields.append(pa.field(output_name, field_type))
    return pa.schema(fields), source_fields


def _infer_arrow_type(values: list[object]) -> pa.DataType:
    present = [_python_scalar(value) for value in values if not _is_missing(value)]
    if not present:
        return pa.string()
    if all(isinstance(value, bool) for value in present):
        return pa.bool_()
    if all(isinstance(value, int) and not isinstance(value, bool) for value in present):
        return pa.int64()
    if all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in present):
        return pa.float64()
    if all(isinstance(value, (date, datetime)) for value in present):
        return pa.timestamp("us")
    return pa.string()


def _normalise_export_row(row: Mapping[str, object], source_fields: Mapping[str, pa.DataType]) -> dict[str, object]:
    normalised: dict[str, object] = {}
    for name, value in row.items():
        if _is_missing(value) or (name in source_fields and value == ""):
            normalised[name] = None
            continue
        value = _python_scalar(value)
        if name in source_fields and pa.types.is_string(source_fields[name]):
            if isinstance(value, (list, tuple, dict, set)):
                value = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
            elif not isinstance(value, str):
                value = str(value)
        normalised[name] = value
    normalised.setdefault("status", None)
    return normalised


def _stage_file_rows(
    metadata: object,
    request: ResultsExportRequest,
    source_lookup: SourceObservationLookup,
    output_path: Path,
    schema: pa.Schema,
    source_fields: Mapping[str, pa.DataType],
    *,
    cancel_check: CancelCheck | None,
) -> tuple[Counter[str], int, int, list[dict[str, str]]]:
    counts: Counter[str] = Counter()
    row_count = 0
    omitted_count = 0
    diagnostics: list[dict[str, str]] = []
    buffer: list[dict[str, object]] = []

    def omitted() -> None:
        nonlocal omitted_count
        omitted_count += 1

    def missing(identifier: str) -> None:
        diagnostics.append({
            "kind": "missing_source",
            "source": identifier,
            "message": "No matching source observation row was found.",
        })

    writer = pq.ParquetWriter(output_path, schema, compression="zstd")
    try:
        for row in iter_sampled_positions(
            metadata,
            positions_per_day=request.positions_per_drift_day,
            source_lookup=source_lookup,
            omitted_position_counter=omitted,
            missing_source_callback=missing,
            environmental_variables=request.environmental_variables,
        ):
            _check_cancel(cancel_check)
            counts[_weight_group_key(
                row["stranding_identifier"], row["observed_at"]
            )] += 1
            buffer.append(_normalise_export_row(row, source_fields))
            row_count += 1
            if len(buffer) >= _ROW_BUFFER_SIZE:
                writer.write_table(pa.Table.from_pylist(buffer, schema=schema))
                buffer.clear()
        if buffer:
            writer.write_table(pa.Table.from_pylist(buffer, schema=schema))
    finally:
        writer.close()
    return counts, row_count, omitted_count, diagnostics


def _weight_group_key(identifier: object, observed_at: object) -> str:
    """Keep reused identifiers separate when they represent different observations."""
    return f"{identifier}\x1f{observed_at}"


def _python_scalar(value: object) -> object:
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
        return bool(missing) if np.ndim(missing) == 0 else False
    except (TypeError, ValueError):
        return False


def _excel_value(value: object) -> object:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _write_diagnostics(path: Path, rows: list[dict[str, str]]) -> None:
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        with partial.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=("kind", "source", "message"))
            writer.writeheader()
            writer.writerows(rows)
        os.replace(partial, path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    partial = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        partial.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(partial, path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _validate_output_basename(value: str) -> None:
    if Path(value).name != value or value in {".", ".."}:
        raise ValueError("Output base name must not contain a path.")


def _check_cancel(cancel_check: CancelCheck | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ResultsExportCancelled("Results export was cancelled.")


def _emit(callback: ProgressCallback | None, stage: str, **values: object) -> None:
    if callback is not None:
        callback({"event": "progress", "stage": stage, **values})


def _software_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("marine-drift-desktop", "pyarrow", "pandas", "netCDF4"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "development"
    return versions
