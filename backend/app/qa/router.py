"""Question router: decide how a question should be answered.

``AGGREGATE`` counts/sums/filters/joins            -> SQL only
``SEMANTIC``  fuzzy lookup inside free-text columns -> vector search, then SQL by row_id
``HYBRID``    find rows about X, then compute       -> vector search -> row_ids -> SQL

A hard rule is enforced in code, not left to the model: anything that needs a
number is never answered from vector search alone.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .llm import LLMClient, LLMUnavailable
from .schema import SchemaCard

logger = logging.getLogger(__name__)

AGGREGATE = "AGGREGATE"
SEMANTIC = "SEMANTIC"
HYBRID = "HYBRID"
ROUTES = (AGGREGATE, SEMANTIC, HYBRID)

_AGGREGATION_WORDS = {
    "average", "avg", "breakdown", "compare", "count", "distribution", "growth", "highest",
    "how many", "how much", "least", "lowest", "maximum", "mean", "median", "minimum", "most",
    "percentage", "percent", "per", "rank", "rate", "share", "sum", "top", "total", "trend",
    "worst", "best", "number of", "many", "each", "group",
}
_SEMANTIC_WORDS = {
    "about", "complain", "complaining", "complaints", "describe", "describing", "similar",
    "mention", "mentioning", "mentions", "regarding", "related to", "talk about", "wording",
    "like ", "sounds like", "semantically", "free text", "comments about", "notes about",
}
_QUOTED = re.compile(r"[\"“”']([^\"“”']{4,})[\"“”']")

_SYSTEM = (
    "You are a query router for a spreadsheet question answering system. "
    "Reply with exactly one word: AGGREGATE, SEMANTIC or HYBRID."
)
_TEMPLATE = """Classify the question against this workbook.

AGGREGATE - counts, sums, averages, filters, rankings, joins: answerable in SQL alone.
SEMANTIC - find rows whose free-text column is *about* something; no numbers needed.
HYBRID - first find rows about something in free text, then compute a number over them.

Free-text columns available: {text_columns}

Question: {question}

Answer with one word."""


@dataclass(frozen=True)
class RouteDecision:
    route: str
    reason: str
    source: str = "heuristic"


def _contains(question: str, vocabulary: set[str]) -> bool:
    return any(word in question for word in vocabulary)


def heuristic_route(question: str, card: SchemaCard) -> RouteDecision:
    """Keyword routing used when no model is configured, or as a safety net."""
    lowered = f" {question.lower().strip()} "
    has_text = bool(card.text_columns())
    numeric = _contains(lowered, _AGGREGATION_WORDS)
    fuzzy = _contains(lowered, _SEMANTIC_WORDS) or bool(_QUOTED.search(question))
    if fuzzy and has_text:
        return RouteDecision(HYBRID if numeric else SEMANTIC,
                             "free-text wording detected in the question")
    return RouteDecision(AGGREGATE, "no free-text lookup required")


def enforce_policy(decision: RouteDecision, question: str, card: SchemaCard) -> RouteDecision:
    """Never answer a counting/aggregation question from vector search alone."""
    lowered = f" {question.lower().strip()} "
    if not card.text_columns() and decision.route != AGGREGATE:
        return RouteDecision(AGGREGATE, "workbook has no free-text columns to search", decision.source)
    if decision.route == SEMANTIC and _contains(lowered, _AGGREGATION_WORDS):
        return RouteDecision(HYBRID, "aggregation wording requires SQL over the matched rows", decision.source)
    return decision


def classify(question: str, card: SchemaCard, llm: LLMClient | None = None) -> RouteDecision:
    """One LLM call (when available) to pick the route, then policy enforcement."""
    decision = heuristic_route(question, card)
    if llm is not None and llm.available:
        columns = ", ".join(f"{table}.{column}" for table, column in card.text_columns()) or "none"
        try:
            response = llm.complete(
                "route", _SYSTEM,
                _TEMPLATE.format(text_columns=columns, question=question.strip()),
                max_tokens=8,
            )
            answer = response.text.strip().upper()
            match = next((route for route in ROUTES if route in answer), None)
            if match:
                decision = RouteDecision(match, "classified by the router model", "llm")
            else:
                logger.warning("router model returned an unusable route: %r", response.text)
        except LLMUnavailable:
            logger.info("router model unavailable, using heuristics")
    decision = enforce_policy(decision, question, card)
    logger.info("route=%s source=%s reason=%s", decision.route, decision.source, decision.reason)
    return decision
