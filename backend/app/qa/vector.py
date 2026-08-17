"""Vector path: semantic lookup over free-text columns only.

Numbers are never answered from here. The index exists so that "which tickets
are about duplicate invoices?" can be turned into a bounded list of `row_id`s,
which the SQL path then uses via ``WHERE row_id IN (...)``.

Embeddings are cached next to the Parquet files, keyed by the workbook digest.
``sentence-transformers`` is used when installed; otherwise a deterministic
hashing embedder keeps the path working with no heavyweight dependency.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

import duckdb
import numpy as np

from .ingest import ROW_ID, Workbook, quote_identifier
from .schema import SchemaCard, is_text

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIMENSIONS = 384
DEFAULT_MAX_INDEX_ROWS = 50_000
DEFAULT_TOP_K = 25
VALUE_TRUNCATION = 120
_WORD = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str

    def encode(self, documents: Sequence[str]) -> np.ndarray:  # pragma: no cover - protocol
        ...


class HashingEmbedder:
    """Deterministic hashed bag-of-words embedder (unigrams + bigrams).

    Python's ``hash`` is salted per process, so blake2b is used instead: the same
    text always lands in the same bucket, which keeps cached vectors valid across
    restarts.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions
        self.name = f"hashing-{dimensions}"

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") % self.dimensions

    def encode(self, documents: Sequence[str]) -> np.ndarray:
        matrix = np.zeros((len(documents), self.dimensions), dtype=np.float32)
        for index, document in enumerate(documents):
            words = _WORD.findall(document.lower())
            for word in words:
                matrix[index, self._bucket(word)] += 1.0
            for first, second in zip(words, words[1:]):
                matrix[index, self._bucket(f"{first}_{second}")] += 0.5
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.maximum(norms, 1e-9)


class SentenceTransformerEmbedder:
    """Small local sentence-transformers model, loaded lazily."""

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.name = model_name

    def encode(self, documents: Sequence[str]) -> np.ndarray:
        vectors = self._model.encode(list(documents), normalize_embeddings=True,
                                     convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


def get_embedder(model_name: str | None = DEFAULT_MODEL) -> Embedder:
    """Prefer the local sentence-transformers model, fall back to hashing."""
    if model_name:
        try:
            return SentenceTransformerEmbedder(model_name)
        except Exception as error:  # noqa: BLE001 - optional dependency or offline
            logger.info("sentence-transformers unavailable (%s); using the hashing embedder", error)
    return HashingEmbedder()


@dataclass(frozen=True)
class TextColumn:
    table: str
    column: str


@dataclass(frozen=True)
class Match:
    table: str
    row_id: int
    score: float


def detect_text_columns(card: SchemaCard, *, min_avg_length: float = 30.0,
                        min_distinct_ratio: float = 0.4) -> list[TextColumn]:
    """Free-text columns: VARCHAR, long values, and high cardinality."""
    return [
        TextColumn(table=table, column=column)
        for table, column in card.text_columns(min_avg_length=min_avg_length,
                                               min_distinct_ratio=min_distinct_ratio)
    ]


def _documents(connection: duckdb.DuckDBPyConnection, card: SchemaCard, table: str,
               text_columns: Sequence[str], limit: int) -> tuple[list[int], list[str]]:
    """Row-as-document: `col: value | col: value`, header names included."""
    table_card = card.table(table)
    assert table_card is not None
    columns = [column.name for column in table_card.columns
               if column.name in text_columns or column.distinct_count <= 200 or not is_text(column.dtype)]
    columns = [column for column in columns if column != ROW_ID][:12]
    for column in text_columns:
        if column not in columns:
            columns.append(column)
    predicate = " OR ".join(f"{quote_identifier(column)} IS NOT NULL" for column in text_columns)
    selected = ", ".join(quote_identifier(column) for column in [ROW_ID, *columns])
    rows = connection.execute(
        f"SELECT {selected} FROM {quote_identifier(table)} WHERE {predicate} "
        f"ORDER BY {quote_identifier(ROW_ID)} LIMIT {int(limit)}"
    ).fetchall()
    row_ids: list[int] = []
    documents: list[str] = []
    for row in rows:
        row_ids.append(int(row[0]))
        parts = []
        for name, value in zip(columns, row[1:]):
            if value is None:
                continue
            text = str(value).replace("\n", " ").strip()
            parts.append(f"{name}: {text[:VALUE_TRUNCATION]}")
        documents.append(" | ".join(parts))
    return row_ids, documents


@dataclass
class VectorIndex:
    """Row vectors for one table, persisted as a compressed .npz file."""

    table: str
    row_ids: np.ndarray
    vectors: np.ndarray
    embedder_name: str
    columns: tuple[str, ...]

    def search(self, embedder: Embedder, query: str, top_k: int = DEFAULT_TOP_K) -> list[Match]:
        if not len(self.row_ids):
            return []
        query_vector = embedder.encode([query])[0]
        scores = self.vectors @ query_vector
        count = min(top_k, len(scores))
        top = np.argpartition(-scores, count - 1)[:count]
        ordered = top[np.argsort(-scores[top])]
        return [Match(table=self.table, row_id=int(self.row_ids[index]), score=float(scores[index]))
                for index in ordered if scores[index] > 0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, row_ids=self.row_ids, vectors=self.vectors,
                            meta=np.array([self.table, self.embedder_name, ",".join(self.columns)]))

    @classmethod
    def load(cls, path: Path) -> "VectorIndex | None":
        try:
            with np.load(path, allow_pickle=False) as payload:
                meta = [str(item) for item in payload["meta"]]
                return cls(table=meta[0], row_ids=payload["row_ids"], vectors=payload["vectors"],
                           embedder_name=meta[1], columns=tuple(part for part in meta[2].split(",") if part))
        except (OSError, ValueError, KeyError, IndexError):
            logger.warning("ignoring unreadable vector cache at %s", path)
            return None


def build_index(connection: duckdb.DuckDBPyConnection, workbook: Workbook, card: SchemaCard, table: str,
                text_columns: Sequence[str], *, embedder: Embedder | None = None,
                max_rows: int = DEFAULT_MAX_INDEX_ROWS, refresh: bool = False) -> VectorIndex:
    """Build (or load) the vector index for one table's free-text columns."""
    embedder = embedder or get_embedder()
    path = workbook.cache.vector_path(table)
    if not refresh and path.exists():
        cached = VectorIndex.load(path)
        if cached and cached.embedder_name == embedder.name and cached.columns == tuple(text_columns):
            logger.info("vector cache hit table=%s rows=%d", table, len(cached.row_ids))
            return cached
    row_ids, documents = _documents(connection, card, table, text_columns, max_rows)
    vectors = embedder.encode(documents) if documents else np.zeros((0, 1), dtype=np.float32)
    index = VectorIndex(table=table, row_ids=np.asarray(row_ids, dtype=np.int64),
                        vectors=np.asarray(vectors, dtype=np.float32),
                        embedder_name=embedder.name, columns=tuple(text_columns))
    index.save(path)
    logger.info("vector index built table=%s rows=%d model=%s", table, len(row_ids), embedder.name)
    return index


def search_workbook(connection: duckdb.DuckDBPyConnection, workbook: Workbook, card: SchemaCard,
                    question: str, *, embedder: Embedder | None = None, top_k: int = DEFAULT_TOP_K,
                    max_rows: int = DEFAULT_MAX_INDEX_ROWS) -> list[Match]:
    """Search every table that has free-text columns and return the best rows."""
    columns = detect_text_columns(card)
    if not columns:
        return []
    embedder = embedder or get_embedder()
    grouped: dict[str, list[str]] = {}
    for entry in columns:
        grouped.setdefault(entry.table, []).append(entry.column)
    matches: list[Match] = []
    for table, text_columns in grouped.items():
        index = build_index(connection, workbook, card, table, text_columns,
                            embedder=embedder, max_rows=max_rows)
        matches.extend(index.search(embedder, question, top_k=top_k))
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches[:top_k]
