import io
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .analysis import analyze_frame
from .config import CORS_ORIGINS, DATABASE_PATH, UPLOADS_DIR


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
STATIC_DIR = Path(__file__).resolve().parent / "static"


def initialize_storage() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                prompt TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    yield


app = FastAPI(title="CSV Insights Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    prompt: str = Form(""),
) -> dict:
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() != ".csv":
        raise HTTPException(status_code=415, detail="Only CSV files are allowed.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="The CSV file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The CSV file exceeds the 10 MB limit.")

    try:
        frame = pd.read_csv(io.BytesIO(content))
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=400, detail="The CSV file could not be read.") from error
    if frame.empty or not len(frame.columns):
        raise HTTPException(status_code=400, detail="The CSV file has no data rows.")

    analysis_id = str(uuid4())
    (UPLOADS_DIR / f"{analysis_id}.csv").write_bytes(content)
    result = analyze_frame(frame, prompt)
    result.update(
        {
            "id": analysis_id,
            "filename": filename,
            "row_count": len(frame),
            "column_count": len(frame.columns),
        }
    )
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "INSERT INTO analyses VALUES (?, ?, ?, ?, ?)",
            (
                analysis_id,
                filename,
                prompt,
                json.dumps(result),
                datetime.now(UTC).isoformat(),
            ),
        )
    return result


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> Response:
    blocked_prefixes = ("api/", "docs", "openapi.json", "redoc", "static/")
    if full_path.startswith(blocked_prefixes):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"},
    )
