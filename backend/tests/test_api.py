import importlib

from fastapi.testclient import TestClient


def load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "insights.db"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    import app.analysis
    import app.config
    import app.main

    importlib.reload(app.config)
    importlib.reload(app.analysis)
    return importlib.reload(app.main).app


def test_health_works_without_llm_key(monkeypatch, tmp_path):
    with TestClient(load_app(monkeypatch, tmp_path)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_serves_static_index(monkeypatch, tmp_path):
    with TestClient(load_app(monkeypatch, tmp_path)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CSV Insights Agent" in response.text


def test_csv_analysis_uses_fallback(monkeypatch, tmp_path):
    with TestClient(load_app(monkeypatch, tmp_path)) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("learning.csv", b"Course,Completed\nA,8\nB,4\n")},
            data={"prompt": "Show completion data"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "pandas"
    assert body["row_count"] == 2
    assert body["chart"]["data"][0] == {"Course": "A", "Completed": 8}


def test_non_csv_upload_is_rejected(monkeypatch, tmp_path):
    with TestClient(load_app(monkeypatch, tmp_path)) as client:
        response = client.post(
            "/api/analyze",
            files={"file": ("learning.xlsx", b"not a spreadsheet")},
        )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only CSV files are allowed."
