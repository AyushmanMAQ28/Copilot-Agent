from app.services.profiler import profile_csv


def test_profiles_numeric_categorical_dates_and_missing_values():
    profile = profile_csv(
        ["amount", "team", "when"],
        [{"amount": "2", "team": "A", "when": "2024-01-01"},
         {"amount": "4", "team": "A", "when": "2024-01-02"},
         {"amount": "", "team": "B", "when": "2024-01-03"}],
    )
    assert profile["row_count"] == 3
    assert profile["columns"]["amount"]["type"] == "number"
    assert profile["columns"]["amount"]["mean"] == 3
    assert profile["columns"]["amount"]["missing_count"] == 1
    assert profile["columns"]["team"]["top_values"][0] == {"value": "A", "count": 2}
    assert profile["columns"]["when"]["type"] == "date"
