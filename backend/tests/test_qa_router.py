from app.qa import router as router_module
from app.qa.router import AGGREGATE, HYBRID, SEMANTIC
from app.qa.schema import ColumnCard, SchemaCard, TableCard


def card_with_text(has_text: bool = True) -> SchemaCard:
    columns = [
        ColumnCard(name="region", source_name="region", dtype="VARCHAR", null_pct=0.0,
                   distinct_count=4, top_values=[("North", 10)]),
        ColumnCard(name="amount", source_name="amount", dtype="DOUBLE", null_pct=0.0, distinct_count=90),
    ]
    if has_text:
        columns.append(ColumnCard(name="note", source_name="note", dtype="VARCHAR", null_pct=0.0,
                                  distinct_count=95, avg_length=120.0))
    return SchemaCard(file_name="tickets.xlsx", digest="1" * 64,
                      tables=[TableCard(name="tickets", source_sheet="Tickets", row_count=100, columns=columns)])


def test_counting_questions_use_the_sql_path():
    decision = router_module.classify("How many tickets were closed last month?", card_with_text())
    assert decision.route == AGGREGATE


def test_fuzzy_lookups_use_the_vector_path():
    decision = router_module.classify("Which tickets mention a broken screen?", card_with_text())
    assert decision.route == SEMANTIC


def test_counting_plus_fuzzy_wording_becomes_hybrid():
    decision = router_module.classify("How many tickets mention a broken screen?", card_with_text())
    assert decision.route == HYBRID


def test_vector_search_is_never_used_for_counting():
    """Policy is enforced in code, even if the model insists on SEMANTIC."""
    decision = router_module.RouteDecision(SEMANTIC, "model said so", "llm")
    enforced = router_module.enforce_policy(decision, "How many rows mention delays?", card_with_text())
    assert enforced.route == HYBRID


def test_workbooks_without_free_text_always_use_sql():
    decision = router_module.RouteDecision(SEMANTIC, "model said so", "llm")
    enforced = router_module.enforce_policy(decision, "rows about delays", card_with_text(has_text=False))
    assert enforced.route == AGGREGATE


def test_router_uses_the_model_when_available():
    from tests.test_qa_sql_agent import StubLLM

    llm = StubLLM(["SEMANTIC"])
    decision = router_module.classify("Find rows describing damaged packaging", card_with_text(), llm)
    assert decision.route == SEMANTIC
    assert decision.source == "llm"
    assert llm.prompts[0][0] == "route"
    assert "tickets.note" in llm.prompts[0][1]


def test_router_falls_back_to_heuristics_on_unusable_output():
    from tests.test_qa_sql_agent import StubLLM

    decision = router_module.classify("What is the total amount?", card_with_text(), StubLLM(["maybe"]))
    assert decision.route == AGGREGATE
    assert decision.source == "heuristic"
