"""API tests for the disk-backed Excel path."""
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient with its own SQLite file, upload directory and Parquet cache."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("QA_CACHE_DIR", str(tmp_path / "cache"))
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings
    from app.database import Base, get_db
    from app.main import app
    from fastapi.testclient import TestClient

    get_settings.cache_clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'excel-api.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()
    get_settings.cache_clear()


def upload(client, path: Path):
    project = client.post("/api/projects", json={"name": "Excel"}).json()
    with path.open("rb") as handle:
        response = client.post(
            f"/api/projects/{project['id']}/datasets",
            files={"file": (path.name, handle,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert response.status_code == 201, response.text
    return project, response.json()


def test_excel_upload_is_profiled_without_loading_rows(client, small_workbook):
    _, dataset = upload(client, small_workbook)
    assert dataset["row_count"] == 4
    assert dataset["columns"] == ["order_id", "order_date", "region", "units", "amount", "comment"]
    assert dataset["profile"]["columns"]["amount"]["type"] == "number"
    assert dataset["profile"]["columns"]["order_date"]["type"] == "date"
    assert {sheet["sheet"] for sheet in dataset["sheets"]} == {"Q1 Sales", "Regions"}


def test_preview_reads_from_parquet(client, small_workbook):
    project, dataset = upload(client, small_workbook)
    preview = client.get(f"/api/projects/{project['id']}/datasets/{dataset['id']}/preview?limit=2").json()
    assert preview["row_count"] == 4
    assert len(preview["rows"]) == 2
    assert preview["rows"][0]["region"] == "North"
    assert preview["rows"][0]["order_date"] == "2024-01-05"


def test_preview_can_select_another_sheet(client, small_workbook):
    project, dataset = upload(client, small_workbook)
    preview = client.get(
        f"/api/projects/{project['id']}/datasets/{dataset['id']}/preview?sheet=regions").json()
    assert preview["sheet"] == "Regions"
    assert preview["rows"][0]["manager"] == "Ada"


def test_analysis_answers_with_sql_and_keeps_the_ui_contract(client, small_workbook):
    project, dataset = upload(client, small_workbook)
    chat = client.post(f"/api/projects/{project['id']}/chats", json={"title": "Excel"}).json()
    payload = client.post(f"/api/chats/{chat['id']}/analyze",
                          json={"dataset_id": dataset["id"],
                                "prompt": "What is the total amount by region?"}).json()
    assert set(payload) == {"summary", "insights", "charts", "next_steps", "table", "meta"}
    assert payload["meta"]["engine"] == "duckdb"
    assert payload["meta"]["sql"].lower().startswith("select")
    assert payload["meta"]["route"] == "AGGREGATE"
    assert payload["charts"][0]["x_key"] == "region"
    totals = {row["region"]: row["total_amount"] for row in payload["table"]["rows"]}
    assert totals == {"North": pytest.approx(1060.55), "South": pytest.approx(80.10),
                      "West": pytest.approx(45.25)}


def test_schema_card_endpoint_exposes_the_llm_view(client, small_workbook):
    project, dataset = upload(client, small_workbook)
    card = client.get(f"/api/projects/{project['id']}/datasets/{dataset['id']}/schema").json()
    assert "# Workbook" in card["markdown"]
    assert card["total_rows"] == 7
    assert len(card["tables"]) == 2


def test_export_streams_csv_from_parquet(client, small_workbook):
    project, dataset = upload(client, small_workbook)
    response = client.get(f"/api/projects/{project['id']}/datasets/{dataset['id']}/export?format=csv")
    assert response.status_code == 200
    lines = response.text.strip().splitlines()
    assert lines[0] == "Order ID,Order Date,Region,Units,Amount,Comment"
    assert len(lines) == 5


def test_deleting_a_dataset_removes_the_stored_file(client, small_workbook, tmp_path):
    project, dataset = upload(client, small_workbook)
    uploads = list((tmp_path / "uploads").iterdir())
    assert len(uploads) == 1
    assert client.delete(f"/api/projects/{project['id']}/datasets/{dataset['id']}").status_code == 204
    assert list((tmp_path / "uploads").iterdir()) == []


def test_unsupported_file_types_are_rejected(client):
    project = client.post("/api/projects", json={"name": "Excel"}).json()
    response = client.post(f"/api/projects/{project['id']}/datasets",
                           files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")})
    assert response.status_code == 422
    assert ".xlsx" in response.json()["detail"]
