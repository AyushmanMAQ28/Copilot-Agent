from app.qa import schema as schema_module
from app.qa import vector
from app.qa.ingest import ingest


def _prepare(path, cache_root):
    workbook = ingest(path, cache_root=cache_root)
    connection = workbook.connect()
    card = schema_module.load_or_build(connection, workbook)
    return workbook, connection, card


def test_only_free_text_columns_are_indexed(small_workbook, tmp_path):
    workbook, _, card = _prepare(small_workbook, tmp_path / "cache")
    try:
        detected = vector.detect_text_columns(card)
        assert [entry.column for entry in detected] == ["comment"]
    finally:
        workbook.close()


def test_documents_include_header_names_and_row_ids(small_workbook, tmp_path):
    workbook, connection, card = _prepare(small_workbook, tmp_path / "cache")
    try:
        row_ids, documents = vector._documents(connection, card, "q1_sales", ["comment"], limit=10)
        assert row_ids == [0, 1, 2, 3]
        assert documents[0].startswith("order_id: A-1")
        assert "comment: Repeat buyer asked about warranty" in documents[0]
        assert " | " in documents[0]
    finally:
        workbook.close()


def test_search_finds_the_row_that_talks_about_a_topic(small_workbook, tmp_path):
    workbook, connection, card = _prepare(small_workbook, tmp_path / "cache")
    try:
        matches = vector.search_workbook(connection, workbook, card, "who disputed an invoice?")
        assert matches
        assert matches[0].table == "q1_sales"
        assert matches[0].row_id == 3
    finally:
        workbook.close()


def test_embeddings_are_cached_by_file_hash(small_workbook, tmp_path):
    workbook, connection, card = _prepare(small_workbook, tmp_path / "cache")
    try:
        vector.search_workbook(connection, workbook, card, "installation guidance")
        cached = workbook.cache.vector_path("q1_sales")
        assert cached.exists()
        index = vector.VectorIndex.load(cached)
        assert index is not None
        assert index.columns == ("comment",)
        assert len(index.row_ids) == 4
    finally:
        workbook.close()


def test_hashing_embedder_is_deterministic_across_instances():
    first = vector.HashingEmbedder().encode(["delivery was late", "invoice dispute"])
    second = vector.HashingEmbedder().encode(["delivery was late", "invoice dispute"])
    assert (first == second).all()
    assert abs(float((first[0] * first[0]).sum()) - 1.0) < 1e-6
