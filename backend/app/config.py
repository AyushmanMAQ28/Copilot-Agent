import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_DIR / path


DATABASE_PATH = project_path(os.getenv("DATABASE_PATH", "data/insights.db"))
UPLOADS_DIR = project_path(os.getenv("UPLOADS_DIR", "uploads"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if origin.strip()
]
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://llm.maqsoftware.net/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-3.6-27b")
