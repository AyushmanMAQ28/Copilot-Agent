"""Schema card: the compact, bounded description of a workbook.

The schema card is the *only* view of the data the LLM gets by default. It never
contains raw sheet rows - just per column statistics plus at most three short
sample values, which is what makes the pipeline safe and cheap on 1 lakh row
workbooks.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from .cache import write_json, write_text
from .ingest import ROW_ID, Table, Workbook, quote_identifier

logger = logging.getLogger(__name__)

EXACT_DISTINCT_LIMIT = 250_000
TOP_VALUE_CARDINALITY = 50
TOP_VALUE_LIMIT = 10
SAMPLE_LIMIT = 3
VALUE_TRUNCATION = 60
NUMERIC_TYPES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "DOUBLE", "FLOAT", "DECIMAL")
TEMPORAL_TYPES = ("DATE", "TIMESTAMP", "TIME")


def is_numeric(dtype: str) -> bool:
    return dtype.upper().startswith(NUMERIC_TYPES)


def is_temporal(dtype: str) -> bool:
    return dtype.upper().startswith(TEMPORAL_TYPES)


def is_text(dtype: str) -> bool:
    return dtype.upper().startswith("VARCHAR")


def _render(value: Any, limit: int = VALUE_TRUNCATION) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, float):
        return format(value, ".6g")
    text = str(value).replace("\n", " ").replace("|", "/").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class ColumnCard:
    name: str
    source_name: str
    dtype: str
    null_pct: float
    distinct_count: int
    distinct_is_approx: bool = False
    minimum: str = ""
    maximum: str = ""
    mean: float | None = None
    avg_length: float = 0.0
    top_values: list[tuple[str, int]] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)

    @property
    def is_text(self) -> bool:
        return is_text(self.dtype)


@dataclass
class TableCard:
    name: str
    source_sheet: str
    row_count: int
    columns: list[ColumnCard]

    def column(self, name: str) -> ColumnCard | None:
        return next((column for column in self.columns if column.name == name), None)

    @property
    def column_names(self) -> list[str]:
        return [column.name for column in self.columns]


@dataclass
class SchemaCard:
    file_name: str
    digest: str
    tables: list[TableCard]

    def table(self, name: str) -> TableCard | None:
        return next((table for table in self.tables if table.name == name), None)

    @property
    def total_rows(self) -> int:
        return sum(table.row_count for table in self.tables)

    @property
    def largest_table(self) -> TableCard:
        return max(self.tables, key=lambda table: table.row_count)

    def text_columns(self, *, min_avg_length: float = 30.0, min_distinct_ratio: float = 0.4) -> list[tuple[str, str]]:
        """Free-text columns worth embedding: long values and high cardinality."""
        found: list[tuple[str, str]] = []
        for table in self.tables:
            for column in table.columns:
                ratio = column.distinct_count / table.row_count if table.row_count else 0.0
                if column.is_text and column.avg_length >= min_avg_length and ratio >= min_distinct_ratio:
                    found.append((table.name, column.name))
        return found

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "SchemaCard":
        tables = [
            TableCard(
                name=table["name"], source_sheet=table["source_sheet"], row_count=table["row_count"],
                columns=[ColumnCard(**{**column, "top_values": [tuple(value) for value in column["top_values"]]})
                         for column in table["columns"]],
            )
            for table in payload["tables"]
        ]
        return cls(file_name=payload["file_name"], digest=payload["digest"], tables=tables)

    def to_markdown(self) -> str:
        lines = [
            f"# Workbook `{self.file_name}`",
            f"sha256 `{self.digest[:16]}` · {len(self.tables)} table(s) · {self.total_rows:,} rows total",
            "",
            "Every table has an extra `row_id` column (BIGINT, 0-based, unique per table).",
        ]
        for table in self.tables:
            lines += [
                "",
                f"## `{table.name}` — sheet \"{table.source_sheet}\" — {table.row_count:,} rows",
                "| column | type | null % | distinct | min | max | values |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for column in table.columns:
                if column.top_values:
                    values = ", ".join(f"{value or '∅'} ({count})" for value, count in column.top_values)
                elif column.samples:
                    values = "e.g. " + ", ".join(column.samples)
                else:
                    values = ""
                distinct = f"~{column.distinct_count}" if column.distinct_is_approx else str(column.distinct_count)
                lines.append(
                    f"| {column.name} | {column.dtype} | {column.null_pct:.1f} | {distinct} | "
                    f"{column.minimum} | {column.maximum} | {values} |"
                )
        free_text = self.text_columns()
        if free_text:
            joined = ", ".join(f"`{table}.{column}`" for table, column in free_text)
            lines += ["", f"Free-text columns (searchable by meaning): {joined}."]
        return "\n".join(lines) + "\n"


def _table_statistics(connection: duckdb.DuckDBPyConnection, table: Table) -> dict[str, dict[str, Any]]:
    exact = table.row_count <= EXACT_DISTINCT_LIMIT
    selects: list[str] = []
    for column in table.columns:
        quoted = quote_identifier(column.name)
        selects.append(f"count({quoted})")
        selects.append(f"count(DISTINCT {quoted})" if exact else f"approx_count_distinct({quoted})")
        if is_numeric(column.dtype) or is_temporal(column.dtype):
            selects += [f"min({quoted})", f"max({quoted})"]
        else:
            selects += ["NULL", "NULL"]
        selects.append(f"avg(length({quoted}))" if is_text(column.dtype) else "NULL")
        selects.append(f"avg({quoted})" if is_numeric(column.dtype) else "NULL")
    row = connection.execute(
        f"SELECT {', '.join(selects)} FROM {quote_identifier(table.name)}"
    ).fetchone()
    assert row is not None
    statistics: dict[str, dict[str, Any]] = {}
    for index, column in enumerate(table.columns):
        offset = index * 6
        mean = row[offset + 5]
        statistics[column.name] = {
            "non_null": int(row[offset] or 0), "distinct": int(row[offset + 1] or 0),
            "min": row[offset + 2], "max": row[offset + 3],
            "avg_length": float(row[offset + 4] or 0.0),
            "mean": float(mean) if mean is not None else None, "exact": exact,
        }
    return statistics


def _samples(connection: duckdb.DuckDBPyConnection, table: Table) -> dict[str, list[str]]:
    rows = connection.execute(
        f"SELECT * FROM {quote_identifier(table.name)} LIMIT {SAMPLE_LIMIT * 4}"
    ).fetchall()
    names = [description[0] for description in connection.description or []]
    samples: dict[str, list[str]] = {column.name: [] for column in table.columns}
    for row in rows:
        for name, value in zip(names, row):
            if name == ROW_ID or name not in samples or value is None:
                continue
            rendered = _render(value)
            if rendered and len(samples[name]) < SAMPLE_LIMIT:
                samples[name].append(rendered)
    return samples


def _top_values(connection: duckdb.DuckDBPyConnection, table: Table, column: str) -> list[tuple[str, int]]:
    rows = connection.execute(
        f"SELECT {quote_identifier(column)} AS value, count(*) AS occurrences "
        f"FROM {quote_identifier(table.name)} GROUP BY 1 ORDER BY occurrences DESC, 1 LIMIT {TOP_VALUE_LIMIT}"
    ).fetchall()
    return [(_render(value, 40), int(count)) for value, count in rows]


def build(connection: duckdb.DuckDBPyConnection, workbook: Workbook) -> SchemaCard:
    """Compute the schema card for every table in the workbook."""
    tables: list[TableCard] = []
    for table in workbook.tables:
        statistics = _table_statistics(connection, table)
        samples = _samples(connection, table)
        columns: list[ColumnCard] = []
        for column in table.columns:
            stats = statistics[column.name]
            null_pct = 100.0 * (table.row_count - stats["non_null"]) / table.row_count if table.row_count else 0.0
            card = ColumnCard(
                name=column.name, source_name=column.source_name, dtype=column.dtype,
                null_pct=round(null_pct, 2), distinct_count=stats["distinct"],
                distinct_is_approx=not stats["exact"], minimum=_render(stats["min"], 30),
                maximum=_render(stats["max"], 30), mean=stats["mean"],
                avg_length=round(stats["avg_length"], 1),
                samples=samples.get(column.name, []),
            )
            if 0 < card.distinct_count < TOP_VALUE_CARDINALITY:
                card.top_values = _top_values(connection, table, column.name)
            columns.append(card)
        tables.append(TableCard(name=table.name, source_sheet=table.source_sheet,
                                row_count=table.row_count, columns=columns))
    return SchemaCard(file_name=workbook.file_name, digest=workbook.digest, tables=tables)


def load_or_build(connection: duckdb.DuckDBPyConnection, workbook: Workbook, *,
                  refresh: bool = False) -> SchemaCard:
    """Return the cached schema card, computing and caching it when missing."""
    cache = workbook.cache
    if not refresh and cache.schema_json_path.exists():
        try:
            with cache.schema_json_path.open("r", encoding="utf-8") as handle:
                card = SchemaCard.from_dict(json.load(handle))
            logger.info("schema card cache hit digest=%s", workbook.digest[:12])
            return card
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            logger.warning("discarding unreadable schema card cache", exc_info=True)
    card = build(connection, workbook)
    write_json(cache.schema_json_path, card.to_dict())
    write_text(cache.schema_markdown_path, card.to_markdown())
    return card
