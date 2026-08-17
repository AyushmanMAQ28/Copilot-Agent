import duckdb
import pytest

from app.qa import sql_agent
from app.qa.llm import LLMClient, LLMResponse, TokenUsage, UsageLog
from app.qa.sql_agent import SQLSafetyError


class StubLLM(LLMClient):
    """An LLMClient that replays canned completions and records its prompts."""

    def __init__(self, replies):
        super().__init__(api_key="test-key", usage_log=UsageLog())
        self.replies = list(replies)
        self.prompts = []

    @property
    def available(self) -> bool:
        return True

    def complete(self, purpose, system, user, *, json_object=False, temperature=0.0, max_tokens=700):
        self.prompts.append((purpose, user))
        text = self.replies.pop(0) if self.replies else ""
        usage = self.usage_log.add(TokenUsage(purpose=purpose, model="stub", prompt_tokens=len(user) // 4,
                                              completion_tokens=len(text) // 4, estimated=True))
        return LLMResponse(text=text, usage=usage)


@pytest.fixture
def connection():
    con = duckdb.connect(database=":memory:")
    con.execute("CREATE TABLE sales AS SELECT * FROM (VALUES ('North', 10), ('South', 20), ('North', 5)) t(region, amount)")
    yield con
    con.close()


@pytest.mark.parametrize("statement", [
    "DROP TABLE sales",
    "DELETE FROM sales",
    "UPDATE sales SET amount = 1",
    "INSERT INTO sales VALUES ('East', 1)",
    "CREATE TABLE evil AS SELECT 1",
    "ATTACH 'other.db'",
    "COPY sales TO 'out.csv'",
])
def test_non_select_statements_are_rejected(connection, statement):
    with pytest.raises(SQLSafetyError):
        sql_agent.validate(connection, statement)


def test_multiple_statements_are_rejected(connection):
    with pytest.raises(SQLSafetyError):
        sql_agent.validate(connection, "SELECT 1; DROP TABLE sales")


def test_file_and_system_functions_are_rejected(connection):
    for statement in ["SELECT * FROM read_csv_auto('/etc/passwd')",
                      "SELECT * FROM read_parquet('/etc/shadow')",
                      "SELECT * FROM glob('/etc/*')"]:
        with pytest.raises(SQLSafetyError):
            sql_agent.validate(connection, statement)


def test_code_fences_are_stripped(connection):
    cleaned = sql_agent.validate(connection, "```sql\nSELECT region FROM sales;\n```")
    assert cleaned == "SELECT region FROM sales"


def test_results_are_truncated_to_the_limit(connection):
    result = sql_agent.run(connection, "SELECT * FROM range(500)", max_rows=100)
    assert len(result.rows) == 100
    assert result.truncated is True
    assert result.to_csv().count("\n") <= 101


def test_result_csv_is_used_instead_of_json(connection):
    result = sql_agent.run(connection, "SELECT region, amount FROM sales ORDER BY amount DESC")
    assert result.to_csv().splitlines()[0] == "region,amount"
    assert result.to_csv().splitlines()[1] == "South,20"


def test_generated_sql_is_retried_with_the_error(connection):
    llm = StubLLM(["SELECT missing_column FROM sales", "SELECT sum(amount) AS total FROM sales"])
    card = _card_for(connection)
    outcome = sql_agent.answer_with_sql(connection, "total amount", card, llm)
    assert outcome.attempts == 2
    assert outcome.result.rows == [(35,)]
    assert "Binder Error" in outcome.errors[0] or "missing_column" in outcome.errors[0]
    assert "DuckDB error" in llm.prompts[-1][1]


def test_unsafe_generated_sql_falls_back_to_the_offline_planner(connection):
    llm = StubLLM(["DROP TABLE sales", "DELETE FROM sales", "TRUNCATE sales"])
    card = _card_for(connection)
    outcome = sql_agent.answer_with_sql(connection, "how many rows are there", card, llm)
    assert outcome.source == "deterministic"
    assert outcome.result.rows == [(3,)]


def test_rows_sql_preserves_match_order(connection):
    statement = sql_agent.rows_sql("sales", ["region"], [2, 0])
    assert "list_position([2, 0]" in statement
    assert '"row_id" IN (2, 0)' in statement


def _card_for(connection):
    from app.qa.schema import ColumnCard, SchemaCard, TableCard

    columns = [
        ColumnCard(name="region", source_name="region", dtype="VARCHAR", null_pct=0.0, distinct_count=2,
                   top_values=[("North", 2), ("South", 1)], samples=["North"]),
        ColumnCard(name="amount", source_name="amount", dtype="BIGINT", null_pct=0.0, distinct_count=3,
                   minimum="5", maximum="20", mean=11.67, samples=["10"]),
    ]
    return SchemaCard(file_name="sales.xlsx", digest="0" * 64,
                      tables=[TableCard(name="sales", source_sheet="Sales", row_count=3, columns=columns)])
