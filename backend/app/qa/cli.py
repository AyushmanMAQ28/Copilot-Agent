"""Command line entry point for the Excel Q&A pipeline.

    python -m app.qa.cli schema sample_data/excel/retail_orders_2024.xlsx
    python -m app.qa.cli ask sample_data/excel/retail_orders_2024.xlsx "How many orders were returned?"
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ..config import get_settings
from .engine import QAEngine
from .ingest import IngestError


def _engine(arguments: argparse.Namespace) -> QAEngine:
    settings = get_settings()
    return QAEngine(
        arguments.file,
        cache_root=arguments.cache_dir or settings.qa_cache_dir,
        settings=None if arguments.no_llm else settings,
        max_rows=settings.max_dataset_rows,
        memory_limit=settings.duckdb_memory_limit,
        threads=settings.duckdb_threads,
        max_result_rows=settings.qa_max_result_rows,
        query_timeout_seconds=settings.qa_query_timeout_seconds,
        vector_max_rows=settings.qa_vector_max_rows,
        refresh=arguments.refresh,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.qa.cli", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache-dir", help="where Parquet/schema/embedding caches are written")
    parser.add_argument("--refresh", action="store_true", help="ignore any cached artefacts")
    parser.add_argument("--no-llm", action="store_true", help="force the deterministic path")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON")
    parser.add_argument("-v", "--verbose", action="store_true", help="log pipeline activity")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("ingest", "convert a workbook to cached Parquet"),
                            ("schema", "print the schema card"),
                            ("ask", "answer a question")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("file", type=Path)
        if name == "ask":
            command.add_argument("question")
    arguments = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if arguments.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s %(message)s")

    try:
        engine = _engine(arguments)
    except (IngestError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        if arguments.command == "ingest":
            payload = {
                "file": engine.workbook.file_name, "digest": engine.workbook.digest,
                "cached": engine.workbook.from_cache, "ingest_ms": engine.workbook.ingest_ms,
                "tables": [table.to_dict() for table in engine.workbook.tables],
            }
            print(json.dumps(payload, indent=2) if arguments.as_json else
                  "\n".join(f"{table.name}: {table.row_count:,} rows, {len(table.columns)} columns"
                            for table in engine.workbook.tables))
            return 0
        if arguments.command == "schema":
            print(json.dumps(engine.schema_card.to_dict(), indent=2, default=str)
                  if arguments.as_json else engine.schema_markdown)
            return 0
        answer = engine.ask(arguments.question)
        if arguments.as_json:
            print(json.dumps(answer.to_dict(), indent=2, default=str))
        else:
            print(answer.text)
            print(f"\nroute: {answer.route} ({answer.route_reason})")
            print(f"sql:\n{answer.sql}")
            print(f"\nresult ({len(answer.rows)} rows{' truncated' if answer.truncated else ''}):")
            print(answer.csv.rstrip())
            print(f"\ntokens: {answer.tokens['total_tokens']} in {answer.tokens['calls']} call(s) · "
                  f"{answer.elapsed_ms} ms")
            for warning in answer.warnings:
                print(f"warning: {warning}", file=sys.stderr)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
