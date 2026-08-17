"""Content-addressed cache for Parquet files, schema cards, and embeddings.

Everything the pipeline derives from a workbook is keyed by ``sha256(file)`` so
re-uploading the same workbook never repeats the expensive conversion work.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

CACHE_VERSION = 2
_CHUNK = 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def file_digest(path: str | os.PathLike[str]) -> str:
    """Return the sha256 of a file, read in bounded chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_name(name: str) -> str:
    """Normalise a table name so it can be used as a cache file name."""
    cleaned = _SAFE_NAME.sub("_", name).strip("._-")
    return cleaned or "table"


@dataclass(frozen=True)
class WorkbookCache:
    """Filesystem layout for one workbook digest."""

    root: Path
    digest: str

    @property
    def directory(self) -> Path:
        return self.root / f"v{CACHE_VERSION}" / self.digest[:2] / self.digest

    @property
    def manifest_path(self) -> Path:
        return self.directory / "manifest.json"

    @property
    def schema_markdown_path(self) -> Path:
        return self.directory / "schema.md"

    @property
    def schema_json_path(self) -> Path:
        return self.directory / "schema.json"

    def parquet_path(self, table: str) -> Path:
        return self.directory / f"{safe_name(table)}.parquet"

    def vector_path(self, table: str) -> Path:
        return self.directory / "vectors" / f"{safe_name(table)}.npz"

    def prepare(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        return self.directory

    def read_manifest(self) -> dict | None:
        try:
            with self.manifest_path.open("r", encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return manifest if isinstance(manifest, dict) and manifest.get("version") == CACHE_VERSION else None

    def write_manifest(self, manifest: dict) -> None:
        self.prepare()
        write_json(self.manifest_path, {**manifest, "version": CACHE_VERSION, "digest": self.digest})

    def clear(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


def write_json(path: Path, payload: dict) -> None:
    """Write JSON atomically so a crash never leaves a half-written cache entry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
