import json
import re
import time
from typing import Any
from ..config import get_settings


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


def fallback_analysis(prompt: str, profile: dict) -> dict[str, Any]:
    columns = profile["columns"]
    numeric = [name for name, info in columns.items() if info["type"] == "number"]
    categorical = [name for name, info in columns.items() if info["type"] == "string"]
    findings = [f"Dataset has {profile['row_count']} rows and {profile['column_count']} columns."]
    if numeric:
        name, info = numeric[0], columns[numeric[0]]
        findings.append(f"{name} ranges from {info['min']:.4g} to {info['max']:.4g} (mean {info['mean']:.4g}).")
    if categorical:
        name, info = categorical[0], columns[categorical[0]]
        findings.append(f"{name} has {info['unique_count']} distinct non-empty values.")
    return {"summary": "Deterministic CSV profile analysis.", "findings": findings, "answer": f"Question: {prompt}", "source": "fallback"}


def analyze(prompt: str, profile: dict) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return fallback_analysis(prompt, profile)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        request = ("Return only JSON object with summary (string), findings (array of strings), and answer (string). "
                   f"Question: {prompt}\nCSV profile: {json.dumps(profile, ensure_ascii=False)}")
        for attempt in range(3):
            try:
                output = client.chat.completions.create(
                    model=settings.openai_model,
                    messages=[{"role": "system", "content": "You are a careful data analyst."}, {"role": "user", "content": request}],
                    response_format={"type": "json_object"},
                    temperature=0,
                ).choices[0].message.content or ""
                repaired = repair_json(output)
                if repaired:
                    repaired["source"] = "llm"
                    return repaired
            except Exception:
                if attempt == 2:
                    break
                time.sleep(2 ** attempt)
    except Exception:
        pass
    return fallback_analysis(prompt, profile)
