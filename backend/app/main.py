from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .database import Base, engine, ensure_schema
from .routers import analyses, chat_analysis, chats, datasets, exports, projects

Base.metadata.create_all(bind=engine)
ensure_schema()
settings = get_settings()
app = FastAPI(title="CSV Insights Agent API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=[item.strip() for item in settings.cors_origins.split(",")],
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router)
app.include_router(chats.router)
app.include_router(chat_analysis.router)
app.include_router(datasets.router)
app.include_router(analyses.router)
app.include_router(exports.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/models")
def models():
    return {
        "models": [
            {"id": settings.llm_default_model, "role": "default"},
            {"id": settings.llm_fallback_model, "role": "fallback"},
        ],
        "default_model": settings.llm_default_model,
        "fallback_model": settings.llm_fallback_model,
    }
