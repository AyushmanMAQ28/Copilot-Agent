import pytest

from app.qa.ingest import IngestError, ROW_ID, ingest, sanitize_identifier


def test_excel_ingest_creates_typed_parquet_tables(small_workbook, tmp_path):
    workbook = ingest(small_workbook, cache_root=tmp_path / "cache")
    try:
        assert [table.name for table in workbook.tables] == ["q1_sales", "regions"]
        sales = workbook.table("q1_sales")
        assert sales.row_count == 4
        types = {column.name: column.dtype for column in sales.columns}
        assert types["order_id"] == "VARCHAR"
        assert types["order_date"] == "DATE"
        assert types["units"] == "BIGINT"
        assert types["amount"] == "DOUBLE"
        assert ROW_ID not in types  # exposed by the table, not part of the sheet columns
        assert sales.column("order_id").source_name == "Order ID"
    finally:
        workbook.close()


def test_ingested_values_survive_the_round_trip(small_workbook, tmp_path):
    workbook = ingest(small_workbook, cache_root=tmp_path / "cache")
    try:
        connection = workbook.connect()
        total, rows = connection.execute("SELECT sum(amount), count(*) FROM q1_sales").fetchone()
        assert round(total, 2) == 1185.90
        assert rows == 4
        managers = connection.execute("SELECT count(*) FROM regions").fetchone()[0]
        assert managers == 3
    finally:
        workbook.close()


def test_row_ids_are_stable_and_zero_based(small_workbook, tmp_path):
    workbook = ingest(small_workbook, cache_root=tmp_path / "cache")
    try:
        connection = workbook.connect()
        ids = [row[0] for row in connection.execute(
            f"SELECT {ROW_ID} FROM q1_sales ORDER BY {ROW_ID}").fetchall()]
        assert ids == [0, 1, 2, 3]
    finally:
        workbook.close()


def test_second_ingest_reuses_the_cache(small_workbook, tmp_path):
    cache_root = tmp_path / "cache"
    first = ingest(small_workbook, cache_root=cache_root)
    first.close()
    second = ingest(small_workbook, cache_root=cache_root)
    try:
        assert second.from_cache is True
        assert second.digest == first.digest
        assert [table.name for table in second.tables] == [table.name for table in first.tables]
    finally:
        second.close()


def test_csv_ingest_infers_types_without_data_loss(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("code,amount,when\n007,34035.15,2024-05-01\n008,1.05,2024-05-02\n", encoding="utf-8")
    workbook = ingest(path, cache_root=tmp_path / "cache")
    try:
        table = workbook.largest_table
        types = {column.name: column.dtype for column in table.columns}
        assert types["code"] == "VARCHAR"  # leading zeros must not become integers
        assert types["amount"] == "DOUBLE"
        assert types["when"] == "DATE"
        connection = workbook.connect()
        total = connection.execute(f"SELECT sum(amount) FROM {table.name}").fetchone()[0]
        assert total == pytest.approx(34036.20)
    finally:
        workbook.close()


def test_unsupported_and_missing_files_are_rejected(tmp_path):
    unsupported = tmp_path / "notes.json"
    unsupported.write_text("{}", encoding="utf-8")
    with pytest.raises(IngestError):
        ingest(unsupported, cache_root=tmp_path / "cache")
    with pytest.raises(IngestError):
        ingest(tmp_path / "missing.xlsx", cache_root=tmp_path / "cache")


def test_row_limit_is_enforced(small_workbook, tmp_path):
    with pytest.raises(IngestError):
        ingest(small_workbook, cache_root=tmp_path / "cache", max_rows=2)


def test_sanitize_identifier_produces_unique_sql_names():
    taken: set[str] = set()
    assert sanitize_identifier("Order ID", taken) == "order_id"
    assert sanitize_identifier("Order-ID", taken) == "order_id_2"
    assert sanitize_identifier("2024", taken) == "column_2024"
    assert sanitize_identifier("   ", taken, fallback="sheet").startswith("sheet")
