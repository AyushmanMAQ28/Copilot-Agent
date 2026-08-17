"""Analysis for disk-backed datasets.

Questions are answered by the DuckDB-powered QA pipeline (`app.qa`) instead of by
loading the whole file into memory, but the response keeps the exact shape the
frontend already consumes: summary, insights, charts, next_steps, table, meta.
"""
from __future__ import annotations

import time
from typing import Any

from ..config import Settings, get_settings
from ..models import Dataset
from ..qa.engine import Answer
from . import dataset_store
from .analyzer import fallback_analysis

CHART_LIMIT = 12
TABLE_ROW_LIMIT = 50


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _chart_from_answer(answer: Answer) -> list[dict[str, Any]]:
    """Use the query result as the chart when it looks like a grouped aggregate."""
    if len(answer.columns) != 2 or len(answer.rows) < 2:
        return []
    label, measure = answer.columns
    if label == "row_id":
        return []
    points = [row for row in answer.rows[:CHART_LIMIT] if _is_number(row.get(measure))]
    if len(points) < 2:
        return []
    return [{
        "id": "primary-chart",
        "title": f"{measure.replace('_', ' ').title()} by {label.replace('_', ' ')}",
        "description": "Computed by DuckDB from the full dataset, not a sample.",
        "chart_type": "bar",
        "x_key": label,
        "series": [{"key": measure, "label": measure.replace("_", " ").title(), "color": "#5b7cfa"}],
        "data": [{label: str(row[label]), measure: row[measure]} for row in points],
    }]


def _chart_from_profile(dataset: Dataset, profile: dict[str, Any],
                        settings: Settings) -> list[dict[str, Any]]:
    columns = profile.get("columns", {})
    numeric = [name for name, info in columns.items() if info["type"] == "number"]
    categorical = [name for name, info in columns.items() if info["type"] == "string"]
    if not columns:
        return []
    x = categorical[0] if categorical else next(iter(columns))
    y = numeric[0] if numeric else None
    try:
        points = dataset_store.aggregate(dataset.storage_path or "", x=x, y=y,
                                         aggregation="sum" if y else "count",
                                         limit=CHART_LIMIT, settings=settings)
    except dataset_store.DatasetError:
        return []
    if not points:
        return []
    series_key = y or "count"
    return [{
        "id": "primary-chart",
        "title": f"{series_key.title()} by {x}",
        "description": "Aggregated by DuckDB across every row in the dataset.",
        "chart_type": "bar",
        "x_key": x,
        "series": [{"key": series_key, "label": series_key.title(), "color": "#5b7cfa"}],
        "data": [{x: str(point["x"]), series_key: point["y"]} for point in points],
    }]


def _next_steps(answer: Answer, profile: dict[str, Any]) -> list[dict[str, str]]:
    steps = [
        {"id": "compare-segments", "question": "Which segments are strongest and weakest?",
         "rationale": "Compare groups with a GROUP BY over the whole dataset."},
        {"id": "missing-values", "question": "Where are the missing values?",
         "rationale": "Check data quality before making decisions."},
    ]
    sheets = profile.get("sheets") or []
    if len(sheets) > 1:
        names = ", ".join(sheet["sheet"] for sheet in sheets[:4])
        steps.append({"id": "join-sheets", "question": f"How do the sheets ({names}) relate?",
                      "rationale": "Shared key columns can be joined in a single SQL query."})
    if answer.route in {"SEMANTIC", "HYBRID"}:
        steps.append({"id": "quantify-matches", "question": "How many rows match that description?",
                      "rationale": "Turn the semantic match into an exact count."})
    return steps


def analyze_dataset(prompt: str, dataset: Dataset, profile: dict[str, Any],
                    settings: Settings | None = None) -> dict[str, Any]:
    """Answer a question about a stored dataset and return the UI contract."""
    settings = settings or get_settings()
    started = time.perf_counter()
    engine = dataset_store.open_engine(dataset.storage_path or "", settings)
    try:
        answer = engine.ask(prompt)
    finally:
        engine.close()
    result = fallback_analysis(prompt, profile, list(profile.get("columns", {})), [])
    result["summary"] = answer.text
    result["charts"] = _chart_from_answer(answer) or _chart_from_profile(dataset, profile, settings)
    result["next_steps"] = _next_steps(answer, profile)
    result["table"] = {
        "columns": answer.columns,
        "rows": [{name: dataset_store.json_safe(row.get(name)) for name in answer.columns}
                 for row in answer.rows[:TABLE_ROW_LIMIT]],
    }
    result["meta"] = {
        "model": answer.answer_source if answer.answer_source != "deterministic" else "deterministic",
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "engine": "duckdb",
        "route": answer.route,
        "route_reason": answer.route_reason,
        "sql": answer.sql,
        "sql_source": answer.sql_source,
        "sql_attempts": answer.sql_attempts,
        "truncated": answer.truncated,
        "row_count": dataset.row_count,
        "tokens": answer.tokens,
        "usage": answer.usage,
        "warnings": answer.warnings,
    }
    return result
