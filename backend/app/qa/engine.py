"""``QAEngine`` - the facade that ties the pipeline together.

    engine = QAEngine("orders.xlsx")
    answer = engine.ask("How many orders were returned in October?")
    print(answer.text, answer.sql)

Ingest, schema card and embeddings are all cached by file digest, so the second
question about a 1 lakh row workbook starts instantly.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import duckdb

from . import answer as answer_module
from . import router as router_module
from . import schema as schema_module
from . import sql_agent, vector
from .cache import WorkbookCache
from .ingest import DEFAULT_MAX_ROWS, ROW_ID, Workbook, ingest
from .llm import LLMClient, UsageLog
from .schema import SchemaCard
from .sql_agent import MAX_RESULT_ROWS, QueryResult, SQLOutcome

logger = logging.getLogger(__name__)


@dataclass
class Answer:
    """Everything needed to display and audit one answer."""

    question: str
    text: str
    route: str
    route_reason: str
    sql: str
    columns: list[str]
    rows: list[dict]
    csv: str
    truncated: bool = False
    matched_row_ids: list[int] = field(default_factory=list)
    sql_attempts: int = 1
    sql_source: str = "deterministic"
    answer_source: str = "deterministic"
    usage: list[dict] = field(default_factory=list)
    tokens: dict = field(default_factory=dict)
    elapsed_ms: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "question": self.question, "answer": self.text, "route": self.route,
            "route_reason": self.route_reason, "sql": self.sql, "columns": self.columns,
            "rows": self.rows, "csv": self.csv, "truncated": self.truncated,
            "matched_row_ids": self.matched_row_ids, "sql_attempts": self.sql_attempts,
            "sql_source": self.sql_source, "answer_source": self.answer_source,
            "usage": self.usage, "tokens": self.tokens, "elapsed_ms": self.elapsed_ms,
            "warnings": self.warnings,
        }


class QAEngine:
    """Question answering over one workbook, without raw rows in the prompt."""

    def __init__(self, path: str | Path, *, cache_root: str | Path = "./data/cache",
                 llm: LLMClient | None = None, settings: Any | None = None,
                 embedder: vector.Embedder | None = None, max_result_rows: int = MAX_RESULT_ROWS,
                 query_timeout_seconds: int = sql_agent.DEFAULT_TIMEOUT_SECONDS,
                 max_rows: int = DEFAULT_MAX_ROWS, memory_limit: str | None = None,
                 threads: int | None = None, vector_max_rows: int = vector.DEFAULT_MAX_INDEX_ROWS,
                 refresh: bool = False) -> None:
        self.usage_log = UsageLog()
        if llm is None and settings is not None:
            llm = LLMClient.from_settings(settings, usage_log=self.usage_log)
        elif llm is not None:
            self.usage_log = llm.usage_log
        self.llm = llm
        self.max_result_rows = max_result_rows
        self.query_timeout_seconds = query_timeout_seconds
        self.vector_max_rows = vector_max_rows
        self._embedder = embedder
        self.workbook: Workbook = ingest(path, cache_root=cache_root, max_rows=max_rows, refresh=refresh)
        self.connection: duckdb.DuckDBPyConnection = self.workbook.connect(
            memory_limit=memory_limit, threads=threads)
        self.schema_card: SchemaCard = schema_module.load_or_build(
            self.connection, self.workbook, refresh=refresh)

    # ------------------------------------------------------------------ helpers
    @property
    def cache(self) -> WorkbookCache:
        return self.workbook.cache

    @property
    def schema_markdown(self) -> str:
        return self.schema_card.to_markdown()

    @property
    def tables(self) -> list[str]:
        return [table.name for table in self.workbook.tables]

    @property
    def embedder(self) -> vector.Embedder:
        if self._embedder is None:
            self._embedder = vector.get_embedder()
        return self._embedder

    def run_sql(self, sql: str) -> QueryResult:
        """Execute an audited, read-only query directly (used by the API layer)."""
        return sql_agent.run(self.connection, sql, max_rows=self.max_result_rows,
                             timeout_seconds=self.query_timeout_seconds)

    def close(self) -> None:
        self.workbook.close()

    def __enter__(self) -> "QAEngine":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ------------------------------------------------------------------ pipeline
    def _semantic_matches(self, question: str) -> tuple[str | None, list[int], list[str]]:
        warnings: list[str] = []
        matches = vector.search_workbook(self.connection, self.workbook, self.schema_card, question,
                                         embedder=self.embedder, max_rows=self.vector_max_rows)
        if not matches:
            warnings.append("No free-text matches were found; answered with SQL over the whole sheet.")
            return None, [], warnings
        table = matches[0].table
        row_ids = [match.row_id for match in matches if match.table == table]
        return table, row_ids, warnings

    def _semantic_rows(self, table: str, row_ids: Sequence[int]) -> QueryResult:
        table_card = self.schema_card.table(table)
        assert table_card is not None
        text_columns = {column for _, column in self.schema_card.text_columns()}
        columns = [column.name for column in table_card.columns
                   if column.name in text_columns or column.distinct_count <= 50][:6]
        for column in table_card.columns:
            if column.name in text_columns and column.name not in columns:
                columns.append(column.name)
        columns = [column for column in columns if column != ROW_ID] or table_card.column_names[:6]
        sql = sql_agent.rows_sql(table, columns, list(row_ids), limit=self.max_result_rows)
        return sql_agent.run(self.connection, sql, max_rows=self.max_result_rows,
                             timeout_seconds=self.query_timeout_seconds)

    def ask(self, question: str) -> Answer:
        """Answer a natural-language question about the workbook."""
        if not question or not question.strip():
            raise ValueError("The question must not be empty")
        started = time.perf_counter()
        first_call = len(self.usage_log.calls)
        warnings: list[str] = []

        decision = router_module.classify(question, self.schema_card, self.llm)
        route, matched_table, row_ids = decision.route, None, []
        if route in (router_module.SEMANTIC, router_module.HYBRID):
            matched_table, row_ids, semantic_warnings = self._semantic_matches(question)
            warnings.extend(semantic_warnings)
            if not row_ids:
                route = router_module.AGGREGATE

        if route == router_module.SEMANTIC and matched_table:
            result = self._semantic_rows(matched_table, row_ids)
            outcome = SQLOutcome(sql=result.sql, result=result, source="row_id lookup")
        else:
            outcome = sql_agent.answer_with_sql(
                self.connection, question, self.schema_card, self.llm,
                row_ids=row_ids if route == router_module.HYBRID else None,
                row_id_table=matched_table if route == router_module.HYBRID else None,
                max_rows=self.max_result_rows, timeout_seconds=self.query_timeout_seconds,
            )
            result = outcome.result
        if outcome.errors:
            warnings.extend(f"SQL retry: {error}" for error in outcome.errors)

        text, answer_source = answer_module.compose(question, result, self.llm,
                                                    max_rows=self.max_result_rows)
        calls = self.usage_log.calls[first_call:]
        answer = Answer(
            question=question.strip(), text=text, route=route, route_reason=decision.reason,
            sql=result.sql, columns=result.columns, rows=result.to_records(),
            csv=result.to_csv(self.max_result_rows), truncated=result.truncated,
            matched_row_ids=list(row_ids), sql_attempts=outcome.attempts, sql_source=outcome.source,
            answer_source=answer_source, usage=[call.to_dict() for call in calls],
            tokens={
                "calls": len(calls),
                "prompt_tokens": sum(call.prompt_tokens for call in calls),
                "completion_tokens": sum(call.completion_tokens for call in calls),
                "total_tokens": sum(call.total_tokens for call in calls),
            },
            elapsed_ms=int((time.perf_counter() - started) * 1000), warnings=warnings,
        )
        logger.info("answered route=%s rows=%d tokens=%d ms=%d", answer.route, len(answer.rows),
                    answer.tokens["total_tokens"], answer.elapsed_ms)
        return answer
