from app.services.analyzer import fallback_analysis, repair_json


def test_repairs_fenced_json_and_trailing_comma():
    assert repair_json('text ```json\n{"summary":"ok","findings":[],}\n``` more') == {
        "summary": "ok", "findings": []
    }


def test_returns_none_when_no_json_object_exists():
    assert repair_json("not a json payload") is None


def test_fallback_is_deterministic():
    profile = {"row_count": 1, "column_count": 1, "columns": {"x": {"type": "number", "min": 1, "max": 1, "mean": 1}}}
    assert fallback_analysis("what?", profile) == fallback_analysis("what?", profile)
