"""Disk-backed storage for uploaded datasets.

Large CSV/Excel uploads are streamed to disk, converted to Parquet once and then
queried through DuckDB, so a 1 lakh row workbook never has to be held in memory
(or in the database) as text. The legacy inline-CSV datasets keep working: any
dataset row without a ``storage_path`` falls back to the original code paths.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from ..config import Settings, get_settings
from ..qa import schema as schema_module
from ..qa.cache import file_digest
from ..qa.engine import QAEngine
from ..qa.ingest import IngestError, ROW_ID, Table, Workbook, ingest, quote_identifier

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (".csv", ".xlsx", ".xlsm")
CHUNK_BYTES = 1024 * 1024


class DatasetError(ValueError):
    """Raised when an upload cannot be stored or read."""


@dataclass
class StoredDataset:
    """The result of ingesting one upload."""

    filename: str
    storage_path: str
    file_hash: str
    row_count: int
    columns: list[str]
    profile: dict[str, Any]
    sheets: list[dict[str, Any]] = field(default_factory=list)


def _suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DatasetError(f"Only {', '.join(SUPPORTED_SUFFIXES)} files are accepted")
    return suffix


def upload_dir(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_stream(chunks: Iterator[bytes], filename: str, settings: Settings | None = None) -> Path:
    """Write an upload to disk in bounded chunks and return its path."""
    settings = settings or get_settings()
    suffix = _suffix(filename)
    target = upload_dir(settings) / f"{uuid4().hex}{suffix}"
    written = 0
    try:
        with target.open("wb") as handle:
            for chunk in chunks:
                if not chunk:
                    continue
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise DatasetError(f"File exceeds the {settings.max_upload_bytes} byte upload limit")
                handle.write(chunk)
    except DatasetError:
        target.unlink(missing_ok=True)
        raise
    except OSError as exc:  # pragma: no cover - disk failures
        target.unlink(missing_ok=True)
        raise DatasetError("Could not store the uploaded file") from exc
    if not written:
        target.unlink(missing_ok=True)
        raise DatasetError("The uploaded file is empty")
    return target


def _column_profile(column: schema_module.ColumnCard, row_count: int) -> dict[str, Any]:
    if schema_module.is_numeric(column.dtype):
        kind = "number"
    elif schema_module.is_temporal(column.dtype):
        kind = "date"
    else:
        kind = "string"
    missing = int(round(column.null_pct / 100.0 * row_count))
    info: dict[str, Any] = {
        "type": kind,
        "missing_count": missing,
        "unique_count": column.distinct_count,
        "examples": column.samples[:3],
        "dtype": column.dtype,
    }
    if kind == "number":
        info["min"] = _number(column.minimum)
        info["max"] = _number(column.maximum)
        info["mean"] = column.mean if column.mean is not None else 0.0
    else:
        if column.minimum:
            info["min"] = column.minimum
        if column.maximum:
            info["max"] = column.maximum
        info["top_values"] = [{"value": value, "count": count} for value, count in column.top_values[:5]]
    return info


def _number(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def legacy_profile(card: schema_module.SchemaCard) -> dict[str, Any]:
    """Profile in the shape the existing API and frontend already understand."""
    primary = card.largest_table
    columns = {column.name: _column_profile(column, primary.row_count)
               for column in primary.columns if column.name != ROW_ID}
    sheets = [{"table": table.name, "sheet": table.source_sheet, "row_count": table.row_count,
               "columns": [column.name for column in table.columns if column.name != ROW_ID]}
              for table in card.tables]
    return {
        "row_count": primary.row_count,
        "column_count": len(columns),
        "columns": columns,
        "primary_table": primary.name,
        "sheets": sheets,
        "total_rows": card.total_rows,
    }


def ingest_upload(path: Path, filename: str, settings: Settings | None = None) -> StoredDataset:
    """Convert an uploaded file to Parquet and summarise it with a schema card."""
    settings = settings or get_settings()
    try:
        workbook = ingest(path, cache_root=settings.qa_cache_dir, max_rows=settings.max_dataset_rows,
                          display_name=filename)
    except IngestError as exc:
        raise DatasetError(str(exc)) from exc
    try:
        connection = workbook.connect(memory_limit=settings.duckdb_memory_limit,
                                      threads=settings.duckdb_threads)
        card = schema_module.load_or_build(connection, workbook)
        profile = legacy_profile(card)
        primary = card.largest_table
        columns = [column.name for column in primary.columns if column.name != ROW_ID]
        return StoredDataset(
            filename=filename, storage_path=str(path), file_hash=workbook.digest,
            row_count=primary.row_count, columns=columns, profile=profile,
            sheets=profile["sheets"],
        )
    finally:
        workbook.close()


def open_workbook(storage_path: str, settings: Settings | None = None) -> Workbook:
    """Reopen a stored dataset; the Parquet cache makes this a fast operation."""
    settings = settings or get_settings()
    path = Path(storage_path)
    if not path.exists():
        raise DatasetError("The stored dataset file is missing from disk")
    return ingest(path, cache_root=settings.qa_cache_dir, max_rows=settings.max_dataset_rows)


def open_engine(storage_path: str, settings: Settings | None = None) -> QAEngine:
    """A QAEngine bound to a stored dataset, configured from app settings."""
    settings = settings or get_settings()
    if not Path(storage_path).exists():
        raise DatasetError("The stored dataset file is missing from disk")
    return QAEngine(storage_path, cache_root=settings.qa_cache_dir, settings=settings,
                    max_result_rows=settings.qa_max_result_rows,
                    query_timeout_seconds=settings.qa_query_timeout_seconds,
                    max_rows=settings.max_dataset_rows,
                    memory_limit=settings.duckdb_memory_limit, threads=settings.duckdb_threads,
                    vector_max_rows=settings.qa_vector_max_rows)


def schema_card_markdown(storage_path: str, settings: Settings | None = None) -> dict[str, Any]:
    """Cached schema card for a stored dataset, as Markdown plus structured JSON."""
    settings = settings or get_settings()
    workbook = open_workbook(storage_path, settings)
    try:
        connection = workbook.connect(memory_limit=settings.duckdb_memory_limit,
                                      threads=settings.duckdb_threads)
        card = schema_module.load_or_build(connection, workbook)
        return {"markdown": card.to_markdown(), "tables": card.to_dict()["tables"],
                "digest": card.digest, "total_rows": card.total_rows}
    finally:
        workbook.close()


def json_safe(value: Any) -> Any:
    """Convert DuckDB values into something FastAPI can serialise."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    return str(value)


def _table(workbook: Workbook, table_name: str | None) -> Table:
    if table_name:
        table = workbook.table(table_name)
        if table is None:
            raise DatasetError(f"Unknown sheet '{table_name}'")
        return table
    return workbook.largest_table


def preview(storage_path: str, limit: int = 50, table_name: str | None = None,
            settings: Settings | None = None) -> dict[str, Any]:
    """First N rows of a sheet, read straight from Parquet."""
    settings = settings or get_settings()
    workbook = open_workbook(storage_path, settings)
    try:
        connection = workbook.connect(memory_limit=settings.duckdb_memory_limit,
                                      threads=settings.duckdb_threads)
        table = _table(workbook, table_name)
        columns = [column.name for column in table.columns if column.name != ROW_ID]
        selected = ", ".join(quote_identifier(name) for name in columns)
        rows = connection.execute(
            f"SELECT {selected} FROM {quote_identifier(table.name)} "
            f"ORDER BY {quote_identifier(ROW_ID)} LIMIT {int(limit)}"
        ).fetchall()
        return {
            "columns": columns,
            "rows": [{name: json_safe(value) for name, value in zip(columns, row)} for row in rows],
            "row_count": table.row_count,
            "table": table.name,
            "sheet": table.source_sheet,
        }
    finally:
        workbook.close()


def aggregate(storage_path: str, x: str, y: str | None = None, aggregation: str = "count",
              limit: int = 25, table_name: str | None = None,
              settings: Settings | None = None) -> list[dict[str, Any]]:
    """Group-by aggregation pushed down to DuckDB instead of Python."""
    settings = settings or get_settings()
    if aggregation not in {"count", "sum", "mean", "min", "max"}:
        raise DatasetError("aggregation must be count, sum, mean, min or max")
    workbook = open_workbook(storage_path, settings)
    try:
        connection = workbook.connect(memory_limit=settings.duckdb_memory_limit,
                                      threads=settings.duckdb_threads)
        table = _table(workbook, table_name)
        names = table.column_names
        if x not in names:
            raise DatasetError(f"Unknown column '{x}'")
        if aggregation == "count":
            measure = "count(*)"
        else:
            if not y or y not in names:
                raise DatasetError(f"Unknown column '{y}'")
            function = "avg" if aggregation == "mean" else aggregation
            measure = f"{function}(TRY_CAST({quote_identifier(y)} AS DOUBLE))"
        rows = connection.execute(
            f"SELECT {quote_identifier(x)} AS bucket, {measure} AS measure "
            f"FROM {quote_identifier(table.name)} GROUP BY 1 ORDER BY 2 DESC NULLS LAST LIMIT {int(limit)}"
        ).fetchall()
        return [{"x": json_safe(bucket), "y": float(measure) if measure is not None else 0.0}
                for bucket, measure in rows]
    finally:
        workbook.close()


def iter_csv(storage_path: str, table_name: str | None = None, chunk_rows: int = 10_000,
             settings: Settings | None = None) -> Iterator[str]:
    """Stream a sheet back as CSV without materialising it in memory."""
    settings = settings or get_settings()
    workbook = open_workbook(storage_path, settings)
    try:
        connection = workbook.connect(memory_limit=settings.duckdb_memory_limit,
                                      threads=settings.duckdb_threads)
        table = _table(workbook, table_name)
        columns = [column.name for column in table.columns if column.name != ROW_ID]
        headers = [column.source_name for column in table.columns if column.name != ROW_ID]
        selected = ", ".join(quote_identifier(name) for name in columns)
        cursor = connection.execute(
            f"SELECT {selected} FROM {quote_identifier(table.name)} ORDER BY {quote_identifier(ROW_ID)}")
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(headers)
        while True:
            rows = cursor.fetchmany(chunk_rows)
            if not rows:
                break
            writer.writerows([[json_safe(value) if value is not None else "" for value in row] for row in rows])
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
        remaining = buffer.getvalue()
        if remaining:
            yield remaining
    finally:
        workbook.close()


def delete_stored_file(storage_path: str | None) -> None:
    if not storage_path:
        return
    try:
        Path(storage_path).unlink(missing_ok=True)
    except OSError:  # pragma: no cover - best effort cleanup
        logger.warning("could not delete stored dataset %s", storage_path)


def clear_uploads(settings: Settings | None = None) -> None:  # pragma: no cover - maintenance helper
    settings = settings or get_settings()
    shutil.rmtree(upload_dir(settings), ignore_errors=True)


def sheet_json(sheets: list[dict[str, Any]]) -> str:
    return json.dumps(sheets)
