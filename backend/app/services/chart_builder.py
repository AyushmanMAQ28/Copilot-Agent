from collections import defaultdict
from typing import Any


class ChartSpecError(ValueError):
    pass


ALLOWED_TYPES = {"bar", "line", "scatter", "pie"}
ALLOWED_AGGREGATIONS = {"count", "sum", "mean", "min", "max"}


def execute_chart_spec(rows: list[dict[str, str]], columns: list[str], spec: dict[str, Any]) -> dict[str, Any]:
    chart_type, x, y = spec.get("chart_type"), spec.get("x"), spec.get("y")
    aggregation, limit = spec.get("aggregation", "count"), spec.get("limit", 25)
    if chart_type not in ALLOWED_TYPES or x not in columns:
        raise ChartSpecError("Unsupported chart type or x column")
    if aggregation not in ALLOWED_AGGREGATIONS or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ChartSpecError("Invalid aggregation or limit")
    if aggregation != "count" and (y not in columns):
        raise ChartSpecError("A valid y column is required for this aggregation")
    if chart_type == "scatter" and (y not in columns or aggregation != "count"):
        raise ChartSpecError("Scatter charts require x and y columns with count aggregation")
    if chart_type == "scatter":
        points = []
        for row in rows[:limit]:
            try:
                points.append({"x": float(row[x]), "y": float(row[y])})
            except (TypeError, ValueError):
                continue
        return {"type": chart_type, "x": x, "y": y, "data": points}
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        label = row.get(x, "") or "(missing)"
        if aggregation == "count":
            buckets[label].append(1)
        else:
            try:
                buckets[label].append(float(row.get(y, "")))
            except (TypeError, ValueError):
                continue
    def aggregate(values: list[float]) -> float:
        if aggregation == "count": return len(values)
        if aggregation == "sum": return sum(values)
        if aggregation == "mean": return sum(values) / len(values)
        if aggregation == "min": return min(values)
        return max(values)
    data = [{"x": key, "y": aggregate(values)} for key, values in buckets.items() if values]
    data.sort(key=lambda item: item["y"], reverse=chart_type != "line")
    return {"type": chart_type, "x": x, "y": y or "count", "aggregation": aggregation, "data": data[:limit]}
