import json
import re
import time
from typing import Any
from ..config import get_settings
from .chart_builder import ChartSpecError, execute_chart_spec


def repair_json(text: str) -> dict[str, Any] | None:
    """Extract and repair common LLM JSON wrappers without executing content."""
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = candidate[start:end + 1]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        result = json.loads(candidate)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _chart_result(headers: list[str], rows: list[dict[str, str]], profile: dict) -> list[dict[str, Any]]:
    columns = profile["columns"]
    numeric = [name for name, info in columns.items() if info["type"] == "number"]
    categorical = [name for name, info in columns.items() if info["type"] == "string"]
    if not headers:
        return []
    x = categorical[0] if categorical else headers[0]
    y = numeric[0] if numeric else None
    try:
        spec = execute_chart_spec(rows, headers, {
            "chart_type": "bar", "x": x, "y": y, "aggregation": "sum" if y else "count", "limit": 12,
        })
    except ChartSpecError:
        return []
    series_key = y or "count"
    return [{
        "id": "primary-chart",
        "title": f"{series_key.title()} by {x}",
        "description": f"Aggregated {spec.get('aggregation', 'count')} values from the uploaded CSV.",
        "chart_type": "bar",
        "x_key": x,
        "series": [{"key": series_key, "label": series_key.title(), "color": "#5b7cfa"}],
        "data": [{x: point["x"], series_key: point["y"]} for point in spec["data"]],
    }]


def fallback_analysis(prompt: str, profile: dict, headers: list[str] | None = None,
                      rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Return the frontend's complete analysis contract without an LLM."""
    headers, rows = headers or list(profile["columns"]), rows or []
    columns = profile["columns"]
    numeric = [name for name, info in columns.items() if info["type"] == "number"]
    categorical = [name for name, info in columns.items() if info["type"] == "string"]
    insights = [{
        "id": "dataset-size",
        "title": "Dataset coverage",
        "body": f"Dataset contains {profile['row_count']} rows across {profile['column_count']} columns.",
        "category": "Overview",
        "severity": "info",
        "confidence": 1.0,
    }]
    if numeric:
        name, info = numeric[0], columns[numeric[0]]
        insights.append({
            "id": f"{name}-range", "title": f"{name} distribution",
            "body": f"Values range from {info['min']:.4g} to {info['max']:.4g}, with a mean of {info['mean']:.4g}.",
            "category": "Trend", "severity": "info", "confidence": 1.0,
        })
    if categorical:
        name, info = categorical[0], columns[categorical[0]]
        insights.append({
            "id": f"{name}-segments", "title": f"{name} segments",
            "body": f"{name} has {info['unique_count']} distinct non-empty values.",
            "category": "Composition", "severity": "info", "confidence": 1.0,
        })
    return {
        "summary": f"Deterministic analysis for: {prompt}",
        "insights": insights,
        "charts": _chart_result(headers, rows, profile),
        "next_steps": [
            {"id": "compare-segments", "question": "Which segments are strongest and weakest?", "rationale": "Compare groups in the uploaded data."},
            {"id": "missing-values", "question": "Where are the missing values?", "rationale": "Check data quality before decisions."},
        ],
        "table": {"columns": headers, "rows": rows[:50]},
        "meta": {"model": "deterministic", "duration_ms": 0},
    }


def analyze(prompt: str, profile: dict, headers: list[str] | None = None,
            rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    settings = get_settings()
    fallback = fallback_analysis(prompt, profile, headers, rows)
    if not settings.llm_api_key:
        return fallback
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
        request = ("Return only a JSON object containing summary and optionally an insights array. "
                   "Each insight needs title, body, category, severity, and confidence. "
                   f"Question: {prompt}\nCSV profile: {json.dumps(profile, ensure_ascii=False)}")
        models = [settings.llm_default_model, settings.llm_default_model, settings.llm_fallback_model]
        for attempt, model in enumerate(models):
            try:
                output = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": "You are a careful data analyst."}, {"role": "user", "content": request}],
                    response_format={"type": "json_object"},
                    temperature=0,
                ).choices[0].message.content or ""
                repaired = repair_json(output)
                if repaired:
                    if isinstance(repaired.get("summary"), str):
                        fallback["summary"] = repaired["summary"]
                    if isinstance(repaired.get("insights"), list):
                        cleaned = []
                        for index, insight in enumerate(repaired["insights"][:8]):
                            if isinstance(insight, dict) and isinstance(insight.get("title"), str) and isinstance(insight.get("body"), str):
                                cleaned.append({"id": str(insight.get("id", f"llm-{index}")), "title": insight["title"],
                                                "body": insight["body"], "category": str(insight.get("category", "Insight")),
                                                "severity": str(insight.get("severity", "info")),
                                                "confidence": float(insight.get("confidence", 0.8))})
                        if cleaned:
                            fallback["insights"] = cleaned
                    fallback["meta"]["model"] = model
                    return fallback
            except Exception:
                if attempt == len(models) - 1:
                    break
                time.sleep(2 ** attempt)
    except Exception:
        pass
    return fallback
