"""End-to-end tests over a synthetic 1 lakh (100,000) row workbook.

The AGGREGATE path must produce exact numeric answers, and no raw sheet row may
ever reach a prompt.
"""
import pytest

from app.qa import QAEngine
from app.qa.router import AGGREGATE, HYBRID, SEMANTIC
from tests.conftest import large_workbook_facts

FACTS = large_workbook_facts()


def scalar(engine, sql):
    result = engine.run_sql(sql)
    return result.rows[0][0]


def test_the_whole_workbook_is_ingested(large_engine):
    assert large_engine.tables == ["sales", "regions"]
    assert scalar(large_engine, "SELECT count(*) FROM sales") == FACTS["row_count"]


def test_aggregate_answers_are_exact(large_engine):
    answer = large_engine.ask("How many rows are in sales?")
    assert answer.route == AGGREGATE
    assert answer.rows[0][answer.columns[0]] == FACTS["row_count"]


def test_totals_match_python_ground_truth(large_engine):
    total = scalar(large_engine, "SELECT round(sum(amount), 2) FROM sales")
    assert total == pytest.approx(FACTS["amount_total"], abs=0.01)
    units = scalar(large_engine, "SELECT sum(units) FROM sales")
    assert units == FACTS["units_total"]


def test_group_by_answers_match_python_ground_truth(large_engine):
    answer = large_engine.ask("What is the total amount by region?")
    assert answer.route == AGGREGATE
    label, measure = answer.columns[0], answer.columns[1]
    computed = {row[label]: row[measure] for row in answer.rows}
    assert set(computed) == set(FACTS["amount_by_region"])
    for region, expected in FACTS["amount_by_region"].items():
        assert computed[region] == pytest.approx(expected, abs=0.01)


def test_counting_by_a_category_is_exact(large_engine):
    answer = large_engine.ask("How many orders are there for each channel?")
    label, measure = answer.columns[0], answer.columns[1]
    computed = {row[label]: row[measure] for row in answer.rows}
    assert computed == FACTS["rows_by_channel"]


def test_filtered_counts_are_exact(large_engine):
    answer = large_engine.ask("How many orders used the Partner channel?")
    assert answer.rows[0][answer.columns[0]] == FACTS["rows_by_channel"]["Partner"]


def test_results_are_capped_at_one_hundred_rows(large_engine):
    result = large_engine.run_sql("SELECT order_id FROM sales")
    assert len(result.rows) == 100
    assert result.truncated is True


def test_prompts_never_contain_raw_rows(large_workbook, large_cache):
    """Every prompt is built from the schema card, never from sheet rows."""
    from tests.test_qa_sql_agent import StubLLM

    llm = StubLLM(["AGGREGATE", "SELECT count(*) AS row_count FROM sales", "There are 100,000 rows."])
    engine = QAEngine(large_workbook, cache_root=large_cache, llm=llm)
    try:
        answer = engine.ask("How many rows are in the sales sheet?")
    finally:
        engine.close()
    assert answer.rows[0]["row_count"] == FACTS["row_count"]
    assert llm.prompts, "the stub model should have been called"
    for _, prompt in llm.prompts:
        assert "ORD-050000" not in prompt
        assert prompt.count("ORD-") <= 3  # at most the three sample values from the schema card
        assert len(prompt) < 20_000


def test_token_usage_is_logged_per_call(large_workbook, large_cache):
    from tests.test_qa_sql_agent import StubLLM

    llm = StubLLM(["AGGREGATE", "SELECT count(*) AS row_count FROM sales", "There are 100,000 rows."])
    engine = QAEngine(large_workbook, cache_root=large_cache, llm=llm)
    try:
        answer = engine.ask("How many rows are in the sales sheet?")
    finally:
        engine.close()
    assert answer.tokens["calls"] == len(llm.prompts)
    assert answer.tokens["total_tokens"] > 0
    assert {call["purpose"] for call in answer.usage} == {"route", "sql", "answer"}


def test_semantic_questions_return_matching_rows(large_engine):
    answer = large_engine.ask("Which orders mention a disputed invoice?")
    assert answer.route in (SEMANTIC, HYBRID)
    assert answer.matched_row_ids
    assert answer.rows


def test_hybrid_questions_are_answered_with_sql_over_matched_rows(large_engine):
    answer = large_engine.ask("How many orders mention a disputed invoice?")
    assert answer.route == HYBRID
    assert "row_id" in answer.sql
    assert isinstance(answer.rows[0][answer.columns[0]], int)


def test_cached_reopen_is_fast(large_workbook, large_cache):
    import time

    started = time.perf_counter()
    engine = QAEngine(large_workbook, cache_root=large_cache)
    try:
        assert engine.workbook.from_cache is True
        assert scalar(engine, "SELECT count(*) FROM sales") == FACTS["row_count"]
    finally:
        engine.close()
    assert time.perf_counter() - started < 10  # Parquet cache, no Excel parsing


def test_answers_expose_the_sql_for_auditability(large_engine):
    answer = large_engine.ask("What is the average amount per region?")
    assert answer.sql.lower().startswith("select")
    assert answer.to_dict()["sql"] == answer.sql
    assert answer.csv.splitlines()[0] == ",".join(answer.columns)
