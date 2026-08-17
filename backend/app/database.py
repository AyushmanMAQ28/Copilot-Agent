from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

settings = get_settings()
if settings.database_url.startswith("sqlite:///"):
    Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> None:
    """Add columns introduced after a database was first created.

    The project has no migration tool, so new nullable columns are added in place
    to keep existing SQLite development databases usable.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "datasets" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("datasets")}
    additions = {"file_hash": "VARCHAR(64)", "storage_path": "TEXT", "sheets_json": "TEXT"}
    missing = {name: ddl for name, ddl in additions.items() if name not in existing}
    if not missing:
        return
    with engine.begin() as connection:
        for name, ddl in missing.items():
            connection.execute(text(f"ALTER TABLE datasets ADD COLUMN {name} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
