import json

from app.qa import schema as schema_module
from app.qa.ingest import ingest


def build_card(path, cache_root):
    workbook = ingest(path, cache_root=cache_root)
    connection = workbook.connect()
    card = schema_module.load_or_build(connection, workbook)
    return workbook, card


def test_schema_card_summarises_every_sheet(small_workbook, tmp_path):
    workbook, card = build_card(small_workbook, tmp_path / "cache")
    try:
        assert [table.name for table in card.tables] == ["q1_sales", "regions"]
        sales = card.table("q1_sales")
        assert sales.row_count == 4
        amount = sales.column("amount")
        assert amount.dtype == "DOUBLE"
        assert amount.null_pct == 0.0
        assert amount.distinct_count == 4
        assert float(amount.minimum) == 45.25
        assert float(amount.maximum) == 940.0
        assert amount.mean is not None and round(amount.mean, 2) == 296.48
        region = sales.column("region")
        assert dict(region.top_values)["North"] == 2
        assert len(sales.column("comment").samples) <= schema_module.SAMPLE_LIMIT
    finally:
        workbook.close()


def test_schema_card_markdown_is_compact_and_row_free(small_workbook, tmp_path):
    workbook, card = build_card(small_workbook, tmp_path / "cache")
    try:
        markdown = card.to_markdown()
        assert "# Workbook" in markdown
        assert "`q1_sales`" in markdown and "`regions`" in markdown
        assert "row_id" in markdown
        # only up to three sample values per column may appear, never whole rows
        assert "Bulk order shipped early with a discounted freight rate." not in markdown
        assert len(markdown) < 4000
    finally:
        workbook.close()


def test_schema_card_is_cached_next_to_the_parquet(small_workbook, tmp_path):
    cache_root = tmp_path / "cache"
    workbook, card = build_card(small_workbook, cache_root)
    try:
        assert workbook.cache.schema_json_path.exists()
        assert workbook.cache.schema_markdown_path.exists()
        payload = json.loads(workbook.cache.schema_json_path.read_text(encoding="utf-8"))
        assert schema_module.SchemaCard.from_dict(payload).to_markdown() == card.to_markdown()
    finally:
        workbook.close()


def test_free_text_columns_are_detected_for_the_vector_path(small_workbook, tmp_path):
    workbook, card = build_card(small_workbook, tmp_path / "cache")
    try:
        assert ("q1_sales", "comment") in card.text_columns()
        assert ("q1_sales", "region") not in card.text_columns()
    finally:
        workbook.close()


def test_large_workbook_schema_card_stays_small(large_engine):
    card = large_engine.schema_card
    assert card.table("sales").row_count == 100_000
    assert card.table("regions").row_count == 4
    markdown = card.to_markdown()
    assert "100,000 rows" in markdown
    assert len(markdown) < 6000  # roughly 1.5k tokens for a 1 lakh row workbook
