"""Fast Excel question answering: Parquet + DuckDB for numbers, vectors for text.

The pipeline never puts raw sheet rows into a prompt. An LLM only ever sees the
schema card, the SQL it generated, and a bounded result table.
"""
from .answer import compose, deterministic_answer
from .engine import Answer, QAEngine
from .ingest import IngestError, Workbook, ingest
from .llm import LLMClient, TokenUsage, UsageLog
from .router import AGGREGATE, HYBRID, SEMANTIC, RouteDecision, classify
from .schema import SchemaCard
from .sql_agent import QueryResult, SQLSafetyError

__all__ = [
    "AGGREGATE", "Answer", "HYBRID", "IngestError", "LLMClient", "QAEngine", "QueryResult",
    "RouteDecision", "SEMANTIC", "SQLSafetyError", "SchemaCard", "TokenUsage", "UsageLog",
    "Workbook", "classify", "compose", "deterministic_answer", "ingest",
]
