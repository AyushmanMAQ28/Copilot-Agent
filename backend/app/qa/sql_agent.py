"""SQL path: turn a question into one audited, read-only DuckDB query.

Guarantees enforced here:

* only a single ``SELECT``/``WITH`` statement ever reaches DuckDB;
* the result set is wrapped in a bounded subquery, so a careless ``SELECT *``
  over 1 lakh rows can never be pulled into memory or into a prompt;
* failures are fed back to the model up to two times before giving up;
* when no model is configured a deterministic planner builds the SQL instead, so
  the pipeline still answers aggregate questions exactly.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import duckdb

from .ingest import ROW_ID, quote_identifier, quote_literal
from .llm import LLMClient, LLMUnavailable
from .schema import ColumnCard, SchemaCard, TableCard, is_numeric

logger = logging.getLogger(__name__)

MAX_RESULT_ROWS = 100
DEFAULT_TIMEOUT_SECONDS = 30
MAX_SQL_ATTEMPTS = 3

_FENCE = re.compile(r"```(?:sql)?\s*(.*?)\s*```", re.S | re.I)
_FORBIDDEN = re.compile(
    r"\b(alter|attach|begin|call|checkpoint|commit|copy|create|delete|detach|drop|execute|export|"
    r"import|insert|install|load|pragma|prepare|reset|rollback|set|truncate|update|use|vacuum)\b",
    re.I,
)
_FILE_FUNCTIONS = re.compile(
    r"\b(read_csv\w*|read_parquet|parquet_scan|read_json\w*|read_text|read_blob|read_ndjson\w*|"
    r"glob|sniff_csv|delta_scan|iceberg_scan|postgres_scan\w*|mysql_scan|sqlite_scan\w*|"
    r"duckdb_\w+|shell|getenv|system)\s*\(",
    re.I,
)
_WORD = re.compile(r"[a-z0-9]+")

_SYSTEM = "You translate questions into DuckDB SQL. Reply with SQL only, no prose, no code fences."
_TEMPLATE = """{schema_card}

Rules:
- Emit exactly one DuckDB SELECT statement (a leading WITH clause is fine).
- Use only the tables and columns above; quote identifiers with double quotes.
- Aggregate in SQL - never plan to read the rows yourself.
- Add `LIMIT {max_rows}` whenever the query returns individual rows.
- Alias computed columns with clear snake_case names.
- Dates are real DATE/TIMESTAMP columns: use date_trunc, year(), etc.
{extra}
Question: {question}

SQL:"""


class SQLSafetyError(ValueError):
    """The generated statement is not a single read-only SELECT."""


class SQLGenerationError(RuntimeError):
    """No valid SQL could be produced for the question."""


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    elapsed_ms: int = 0

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_csv(self, max_rows: int = MAX_RESULT_ROWS) -> str:
        """CSV is the most token-efficient tabular format for a prompt."""
        import csv
        import io

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(self.columns)
        for row in self.rows[:max_rows]:
            writer.writerow(["" if value is None else str(value) for value in row])
        return buffer.getvalue()

    def to_records(self) -> list[dict]:
        return [dict(zip(self.columns, row)) for row in self.rows]


@dataclass
class SQLOutcome:
    sql: str
    result: QueryResult
    attempts: int = 1
    errors: list[str] = field(default_factory=list)
    source: str = "llm"


# --------------------------------------------------------------------------- safety
def clean_sql(text: str) -> str:
    """Strip code fences and trailing punctuation from a model response."""
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1)
    candidate = re.sub(r"^\s*(sql|duckdb)\s*[:\n]", "", candidate, flags=re.I).strip()
    return candidate.rstrip(";").strip()


def validate(connection: duckdb.DuckDBPyConnection, sql: str) -> str:
    """Reject anything that is not one read-only SELECT statement."""
    statement = clean_sql(sql)
    if not statement:
        raise SQLSafetyError("The query is empty")
    if ";" in statement:
        raise SQLSafetyError("Only a single statement is allowed")
    if _FILE_FUNCTIONS.search(statement):
        raise SQLSafetyError("File and system functions are not allowed")
    try:
        parsed = connection.extract_statements(statement)
    except duckdb.Error as error:
        raise SQLSafetyError(f"The query could not be parsed: {error}") from error
    if len(parsed) != 1:
        raise SQLSafetyError("Only a single statement is allowed")
    statement_type = getattr(parsed[0], "type", None)
    if statement_type is not None and statement_type != duckdb.StatementType.SELECT:
        raise SQLSafetyError("Only SELECT statements are allowed")
    if statement_type is None and _FORBIDDEN.search(statement):  # pragma: no cover - very old DuckDB
        raise SQLSafetyError("Only SELECT statements are allowed")
    return statement


def run(connection: duckdb.DuckDBPyConnection, sql: str, *, max_rows: int = MAX_RESULT_ROWS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> QueryResult:
    """Validate, execute and truncate a query. Never returns more than max_rows."""
    statement = validate(connection, sql)
    bounded = f"SELECT * FROM (\n{statement}\n) AS bounded_result LIMIT {int(max_rows) + 1}"
    watchdog = threading.Timer(timeout_seconds, connection.interrupt)
    watchdog.daemon = True
    started = time.perf_counter()
    watchdog.start()
    try:
        cursor = connection.execute(bounded)
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description or []]
    finally:
        watchdog.cancel()
    elapsed = int((time.perf_counter() - started) * 1000)
    truncated = len(rows) > max_rows
    logger.info("sql executed rows=%d truncated=%s ms=%d", min(len(rows), max_rows), truncated, elapsed)
    return QueryResult(sql=statement, columns=columns, rows=rows[:max_rows],
                       truncated=truncated, elapsed_ms=elapsed)


# --------------------------------------------------------------------------- generation
def _row_id_clause(table: str, row_ids: Sequence[int]) -> str:
    joined = ", ".join(str(int(row_id)) for row_id in row_ids)
    return f"{quote_identifier(table)}.{quote_identifier(ROW_ID)} IN ({joined})"


def rows_sql(table: str, columns: Iterable[str], row_ids: Sequence[int], limit: int = MAX_RESULT_ROWS) -> str:
    """SQL that fetches the rows a vector search matched, in match order."""
    selected = ", ".join(quote_identifier(column) for column in columns)
    ordered = ", ".join(str(int(row_id)) for row_id in row_ids[:limit])
    return (
        f"SELECT {quote_identifier(ROW_ID)}, {selected} FROM {quote_identifier(table)} "
        f"WHERE {_row_id_clause(table, row_ids[:limit])} "
        f"ORDER BY list_position([{ordered}], {quote_identifier(ROW_ID)}) LIMIT {int(limit)}"
    )


def generate(question: str, card: SchemaCard, llm: LLMClient, *, row_ids: Sequence[int] | None = None,
             row_id_table: str | None = None, previous_sql: str | None = None,
             error: str | None = None, max_rows: int = MAX_RESULT_ROWS) -> str:
    """Ask the model for SQL, optionally constrained to vector-matched rows."""
    extra = ""
    if row_ids and row_id_table:
        joined = ", ".join(str(int(row_id)) for row_id in row_ids[:200])
        extra += (
            f"- Semantic search already matched rows in `{row_id_table}`. Restrict the query with "
            f"`{quote_identifier(row_id_table)}.\"{ROW_ID}\" IN ({joined})`.\n"
        )
    if previous_sql and error:
        extra += f"- Your previous SQL failed.\nPrevious SQL: {previous_sql}\nDuckDB error: {error}\nFix it.\n"
    prompt = _TEMPLATE.format(schema_card=card.to_markdown(), extra=extra,
                              question=question.strip(), max_rows=max_rows)
    return clean_sql(llm.complete("sql", _SYSTEM, prompt, max_tokens=500).text)


def answer_with_sql(connection: duckdb.DuckDBPyConnection, question: str, card: SchemaCard,
                    llm: LLMClient | None, *, row_ids: Sequence[int] | None = None,
                    row_id_table: str | None = None, max_rows: int = MAX_RESULT_ROWS,
                    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> SQLOutcome:
    """Generate and execute SQL, retrying up to two times with the error text."""
    errors: list[str] = []
    if llm is not None and llm.available:
        previous_sql: str | None = None
        for attempt in range(1, MAX_SQL_ATTEMPTS + 1):
            sql = None
            try:
                sql = generate(question, card, llm, row_ids=row_ids, row_id_table=row_id_table,
                               previous_sql=previous_sql, error=errors[-1] if errors else None,
                               max_rows=max_rows)
                result = run(connection, sql, max_rows=max_rows, timeout_seconds=timeout_seconds)
                return SQLOutcome(sql=result.sql, result=result, attempts=attempt, errors=errors, source="llm")
            except LLMUnavailable as error:
                errors.append(str(error))
                logger.warning("sql model unavailable: %s", error)
                break
            except (SQLSafetyError, duckdb.Error) as error:
                previous_sql = sql
                errors.append(str(error))
                logger.warning("sql attempt %d failed: %s", attempt, error)
    fallback = plan_offline(question, card, row_ids=row_ids, row_id_table=row_id_table)
    try:
        result = run(connection, fallback, max_rows=max_rows, timeout_seconds=timeout_seconds)
    except (SQLSafetyError, duckdb.Error) as error:
        errors.append(str(error))
        raise SQLGenerationError(f"Could not answer the question with SQL: {'; '.join(errors)}") from error
    return SQLOutcome(sql=result.sql, result=result, attempts=len(errors) + 1, errors=errors,
                      source="deterministic")


# --------------------------------------------------------------------------- offline planner
_COUNT_WORDS = ("how many", "count", "number of", "how much")
_SUM_WORDS = ("total", "sum", "revenue", "combined")
_AVERAGE_WORDS = ("average", "avg", "mean", "typical")
_MAX_WORDS = ("maximum", "max ", "highest", "largest", "biggest", "peak")
_MIN_WORDS = ("minimum", "min ", "lowest", "smallest", "cheapest")
_GROUP_MARKERS = ("by ", "per ", "for each ", "each ", "across ")
_LIST_WORDS = ("list", "show me", "show the rows", "examples", "sample rows", "which rows")
_STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "is", "are", "was",
              "were", "what", "which", "how", "many", "much", "me", "please", "show", "give"}


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _tokens(text: str) -> set[str]:
    return {_stem(word) for word in _WORD.findall(text.lower()) if word not in _STOPWORDS}


def _flatten(text: str) -> str:
    """Lowercase text with punctuation collapsed to single spaces, space padded."""
    return " " + " ".join(_WORD.findall(text.lower())) + " "


def _name_score(name: str, tokens: set[str]) -> float:
    parts = {_stem(part) for part in name.split("_") if part and part not in _STOPWORDS}
    if not parts:
        return 0.0
    return len(parts & tokens) / len(parts)


def _qualified(table: str, column: str) -> str:
    return f"{quote_identifier(table)}.{quote_identifier(column)}"


def _pick_table(card: SchemaCard, tokens: set[str]) -> TableCard:
    """Prefer the table that owns the measure being asked about, then the largest."""
    def name_score(table: TableCard) -> float:
        return max(_name_score(table.name, tokens), _name_score(table.source_sheet.lower(), tokens))

    with_metric = [table for table in card.tables if _metric_column(table, tokens, set())]
    candidates = with_metric or list(card.tables)
    return max(candidates, key=lambda table: (name_score(table), table.row_count))


def _mentioned_columns(table: TableCard, tokens: set[str]) -> list[str]:
    return [column.name for column in table.columns if _name_score(column.name, tokens) >= 0.999]


def _group_tokens(question: str) -> list[set[str]]:
    """Token sets that follow a grouping marker such as "by" or "per"."""
    lowered = question.lower()
    tails: list[set[str]] = []
    for marker in _GROUP_MARKERS:
        position = lowered.find(marker)
        while position != -1:
            tails.append(_tokens(lowered[position + len(marker):position + len(marker) + 40]))
            position = lowered.find(marker, position + 1)
    return tails


def _names_a_value(column: ColumnCard, flattened: str) -> bool:
    """True when the question quotes one of the column's own values."""
    return any(len(_flatten(value).strip()) >= 3 and f" {_flatten(value).strip()} " in flattened
               for value, _ in column.top_values)


def _group_candidates(table: TableCard, question: str, tokens: set[str]) -> list[str]:
    """Columns that could be the GROUP BY key, most explicit first."""
    flattened = _flatten(question)
    explicit: list[str] = []
    for tail in _group_tokens(question):
        explicit.extend(column.name for column in table.columns
                        if _name_score(column.name, tail) >= 0.999 and column.distinct_count <= 200)
    found = list(explicit)
    for name in _mentioned_columns(table, tokens):
        column = table.column(name)
        if column is None or is_numeric(column.dtype) or not 1 < column.distinct_count <= 50:
            continue
        # "how many orders used the Partner channel" filters on a value; it does not group
        if name in explicit or not _names_a_value(column, flattened):
            found.append(name)
    return list(dict.fromkeys(found))


def _lookup_join(card: SchemaCard, table: TableCard, question: str,
                 tokens: set[str]) -> tuple[TableCard, str, str] | None:
    """Find (lookup table, group column, shared key) when grouping needs a join."""
    keys = {column.name for column in table.columns}
    for other in card.tables:
        if other.name == table.name:
            continue
        shared = [name for name in keys & {column.name for column in other.columns}
                  if name != ROW_ID]
        if not shared:
            continue
        candidates = _group_candidates(other, question, tokens)
        if candidates:
            shared.sort(key=lambda name: (not name.endswith("_id"), name))
            return other, candidates[0], shared[0]
    return None


def _metric_column(table: TableCard, tokens: set[str], skip: set[str]) -> str | None:
    ranked = [
        (_name_score(column.name, tokens), column.distinct_count, column.name)
        for column in table.columns
        if is_numeric(column.dtype) and column.name not in skip and column.name != ROW_ID
    ]
    ranked = [candidate for candidate in ranked if candidate[0] >= 0.999]
    if not ranked:
        return None
    ranked.sort(key=lambda candidate: (-candidate[0], -candidate[1], candidate[2]))
    return ranked[0][2]


def _structural_words(card: SchemaCard) -> set[str]:
    """Words that name part of the schema, so they are not data values."""
    words: set[str] = set()
    for table in card.tables:
        words.update(_stem(part) for part in table.name.split("_") if part)
        words.update(_stem(part) for part in _WORD.findall(table.source_sheet.lower()))
        for column in table.columns:
            words.update(_stem(part) for part in column.name.split("_") if part)
    return words


def _filters(table: TableCard, question: str, skip: set[str], structural: set[str]) -> list[str]:
    """Equality filters for literal values that appear in the question."""
    flattened = _flatten(question)
    clauses: list[str] = []
    for column in table.columns:
        if column.name in skip or not column.top_values:
            continue
        for value, _ in column.top_values:
            needle = _flatten(value).strip()
            if len(needle) < 3 or _stem(needle) in structural:
                continue
            if f" {needle} " in flattened or f" {needle}s " in flattened:
                clauses.append(
                    f"lower({_qualified(table.name, column.name)}) = lower({quote_literal(value)})")
                break
    return clauses


def plan_offline(question: str, card: SchemaCard, *, row_ids: Sequence[int] | None = None,
                 row_id_table: str | None = None, max_rows: int = MAX_RESULT_ROWS) -> str:
    """Deterministic fallback planner: schema-driven, never free-form text.

    It covers the common aggregate shapes - count, sum, average, min/max,
    group-by, literal filters and a single lookup-table join - so the engine
    still returns exact numbers when no model is configured.
    """
    lowered = _flatten(question)
    tokens = _tokens(question)
    table = (card.table(row_id_table) if row_id_table else None) or _pick_table(card, tokens)
    listing = any(word in lowered for word in _LIST_WORDS) and not any(
        word in lowered for word in _COUNT_WORDS + _SUM_WORDS + _AVERAGE_WORDS)

    group_table, group = table, next(iter(_group_candidates(table, question, tokens)), None)
    join: tuple[TableCard, str, str] | None = None
    if group is None:
        join = _lookup_join(card, table, question, tokens)
        if join:
            group_table, group, _ = join

    metric = _metric_column(table, tokens, skip={group} if group_table is table and group else set())
    metric_reference = _qualified(table.name, metric) if metric else ""
    if any(word in lowered for word in _SUM_WORDS) and metric:
        aggregate, label = f"sum({metric_reference})", f"total_{metric}"
    elif any(word in lowered for word in _AVERAGE_WORDS) and metric:
        aggregate, label = f"avg({metric_reference})", f"average_{metric}"
    elif any(word in lowered for word in _MAX_WORDS) and metric:
        aggregate, label = f"max({metric_reference})", f"max_{metric}"
    elif any(word in lowered for word in _MIN_WORDS) and metric:
        aggregate, label = f"min({metric_reference})", f"min_{metric}"
    elif any(word in lowered for word in _COUNT_WORDS) or not metric:
        aggregate, label = "count(*)", "row_count"
    else:
        aggregate, label = f"sum({metric_reference})", f"total_{metric}"

    grouped_here = group_table is table and group and not listing
    conditions = _filters(table, question, {group} if grouped_here else set(), _structural_words(card))
    if row_ids:
        conditions.append(_row_id_clause(table.name, row_ids))
    source = quote_identifier(table.name)
    if join:
        lookup, _, key = join
        source += (f" JOIN {quote_identifier(lookup.name)} ON "
                   f"{_qualified(table.name, key)} = {_qualified(lookup.name, key)}")
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

    if listing:
        columns = ", ".join(_qualified(table.name, column.name) for column in table.columns[:8])
        return f"SELECT {columns} FROM {source}{where} LIMIT {int(max_rows)}"
    if group:
        return (
            f"SELECT {_qualified(group_table.name, group)}, {aggregate} AS {quote_identifier(label)} "
            f"FROM {source}{where} GROUP BY 1 ORDER BY 2 DESC LIMIT {int(max_rows)}"
        )
    return f"SELECT {aggregate} AS {quote_identifier(label)} FROM {source}{where}"


__all__ = [
    "MAX_RESULT_ROWS", "QueryResult", "SQLGenerationError", "SQLOutcome", "SQLSafetyError",
    "answer_with_sql", "clean_sql", "generate", "plan_offline", "rows_sql", "run", "validate",
]
