from pathlib import Path


def test_health_models_and_chat_analysis_contract(monkeypatch):
    database = Path("backend/tests/api-contract.db")
    database.unlink(missing_ok=True)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///./{database}")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.database import Base, engine
    from app.main import app
    from fastapi.testclient import TestClient

    Base.metadata.create_all(bind=engine)
    client = TestClient(app)
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/models").json()["default_model"] == "qwen-3.6-27b"
    project = client.post("/api/projects", json={"name": "Contract test"}).json()
    dataset = client.post(f"/api/projects/{project['id']}/datasets",
                          files={"file": ("data.csv", b"team,value\nA,2\nB,4\n", "text/csv")}).json()
    chat = client.post(f"/api/projects/{project['id']}/chats", json={"title": "Analyze"}).json()
    response = client.post(f"/api/chats/{chat['id']}/analyze",
                           json={"dataset_id": dataset["id"], "prompt": "Show the trend"})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"summary", "insights", "charts", "next_steps", "table", "meta"}
    assert payload["charts"][0]["x_key"] == "team"
    assert client.get(f"/api/projects/{project['id']}/datasets/{dataset['id']}/profile").status_code == 200
    assert client.get(f"/api/projects/{project['id']}/datasets/{dataset['id']}/preview").json()["rows"][0]["team"] == "A"
    database.unlink(missing_ok=True)
