from collections import Counter
from datetime import datetime
from math import isfinite


def _number(value: str) -> float | None:
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, TypeError):
        return None


def profile_csv(headers: list[str], rows: list[dict[str, str]]) -> dict:
    column_profiles = {}
    for header in headers:
        values = [row.get(header, "") for row in rows]
        present = [value for value in values if value != ""]
        numeric = [_number(value) for value in present]
        numeric_values = [value for value in numeric if value is not None]
        is_numeric = bool(present) and len(numeric_values) == len(present)
        inferred_type = "number" if is_numeric else "string"
        if not is_numeric and present:
            try:
                for value in present:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                inferred_type = "date"
            except ValueError:
                pass
        info = {
            "type": inferred_type,
            "missing_count": len(values) - len(present),
            "unique_count": len(set(present)),
            "examples": present[:3],
        }
        if is_numeric:
            info["min"] = min(numeric_values)
            info["max"] = max(numeric_values)
            info["mean"] = sum(numeric_values) / len(numeric_values)
        else:
            info["top_values"] = [{"value": value, "count": count} for value, count in Counter(present).most_common(5)]
        column_profiles[header] = info
    return {"row_count": len(rows), "column_count": len(headers), "columns": column_profiles}
