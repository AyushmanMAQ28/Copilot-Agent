import pytest
from app.services.chart_builder import ChartSpecError, execute_chart_spec


ROWS = [{"team": "A", "sales": "2"}, {"team": "A", "sales": "4"}, {"team": "B", "sales": "3"}]


def test_aggregates_only_allowed_chart_operations():
    chart = execute_chart_spec(ROWS, ["team", "sales"],
                               {"chart_type": "bar", "x": "team", "y": "sales", "aggregation": "sum"})
    assert chart["data"] == [{"x": "A", "y": 6.0}, {"x": "B", "y": 3.0}]


@pytest.mark.parametrize("spec", [
    {"chart_type": "script", "x": "team"},
    {"chart_type": "bar", "x": "__import__", "aggregation": "count"},
    {"chart_type": "bar", "x": "team", "y": "sales", "aggregation": "eval"},
])
def test_rejects_unsafe_or_unknown_specs(spec):
    with pytest.raises(ChartSpecError):
        execute_chart_spec(ROWS, ["team", "sales"], spec)
