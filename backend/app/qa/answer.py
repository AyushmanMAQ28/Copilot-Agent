"""Final answer composition.

The model sees the question, the SQL that ran, and the result table as CSV -
never the sheet itself. The SQL is always returned alongside the answer so the
number can be audited.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from .llm import LLMClient, LLMUnavailable
from .sql_agent import MAX_RESULT_ROWS, QueryResult

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a precise data analyst. Answer only from the result table you are given. "
    "Never invent numbers, never mention SQL syntax, and keep it under four sentences."
)
_TEMPLATE = """Question: {question}

SQL that produced the result:
{sql}

Result as CSV{note}:
{csv}

Write the answer for a business user. Quote the exact numbers from the CSV."""


def _format(value: object) -> str:
    if value is None:
        return "no value"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, Decimal)):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}" if abs(value) >= 0.01 else f"{value:g}"
    return str(value)


def deterministic_answer(question: str, result: QueryResult) -> str:
    """Readable summary of a bounded result set, computed without a model."""
    if not result.rows:
        return "No rows matched that question."
    if result.columns and result.columns[0] == "row_id":
        longest = [max((str(value) for value in row[1:] if value is not None), key=len, default="")
                   for row in result.rows[:2]]
        examples = "; ".join(text[:160] for text in longest if text)
        suffix = f" Closest matches: {examples}" if examples else ""
        return (f"Found {len(result.rows)} matching row(s) by meaning"
                f"{' (showing the closest ones)' if result.truncated else ''}.{suffix}")
    if len(result.rows) == 1 and len(result.columns) == 1:
        return f"{result.columns[0].replace('_', ' ')}: {_format(result.rows[0][0])}."
    if len(result.rows) == 1:
        pairs = ", ".join(f"{name.replace('_', ' ')} {_format(value)}"
                          for name, value in zip(result.columns, result.rows[0]))
        return f"{pairs}."
    label, *rest = result.columns
    numeric_pair = len(result.columns) == 2 and isinstance(result.rows[0][1], (int, float, Decimal))
    highlights = []
    for row in result.rows[:3]:
        if rest:
            highlights.append(f"{_format(row[0])} ({rest[0].replace('_', ' ')} {_format(row[1])})")
        else:
            highlights.append(_format(row[0]))
    suffix = " (result truncated)" if result.truncated else ""
    if numeric_pair:
        return (f"{len(result.rows)} rows grouped by {label.replace('_', ' ')}. "
                f"Top results: {', '.join(highlights)}.{suffix}")
    return (f"Returned {len(result.rows)} rows covering {', '.join(result.columns[:6])}. "
            f"First rows: {', '.join(highlights)}.{suffix}")


def compose(question: str, result: QueryResult, llm: LLMClient | None, *,
            max_rows: int = MAX_RESULT_ROWS) -> tuple[str, str]:
    """Return (answer text, source) for a completed query."""
    fallback = deterministic_answer(question, result)
    if llm is None or not llm.available:
        return fallback, "deterministic"
    note = f" (first {max_rows} rows only)" if result.truncated else ""
    prompt = _TEMPLATE.format(question=question.strip(), sql=result.sql,
                              csv=result.to_csv(max_rows), note=note)
    try:
        response = llm.complete("answer", _SYSTEM, prompt, max_tokens=350)
    except LLMUnavailable as error:
        logger.info("answer model unavailable (%s); using the deterministic summary", error)
        return fallback, "deterministic"
    text = response.text.strip()
    return (text, "llm") if text else (fallback, "deterministic")
