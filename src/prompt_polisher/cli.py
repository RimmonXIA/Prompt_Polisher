from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from prompt_polisher.config import get_settings
from prompt_polisher.graph import run_compiler
from prompt_polisher.llm import build_llm_client
from prompt_polisher.logging_config import configure_logging
from prompt_polisher.report import compilation_report_dict, render_compilation_report

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-polisher",
        description=(
            "LLM-backed heuristic prompt compiler (radar → route → compile → critic). "
            "Does not guarantee task success, formal safety, or optimality; see docs/THEORY.zh.md."
        ),
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Raw prompt text (optional if --file or stdin)",
    )
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        default=None,
        help="Read raw prompt from file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved settings and exit without calling the LLM",
    )
    out_group = parser.add_mutually_exclusive_group()
    out_group.add_argument(
        "--json",
        action="store_true",
        help="Print full graph state as JSON",
    )
    out_group.add_argument(
        "--markdown",
        action="store_true",
        help="Print human-readable Markdown compilation report",
    )
    out_group.add_argument(
        "--report-json",
        action="store_true",
        help="Print structured compilation report as JSON (subset of state)",
    )
    parser.add_argument(
        "--report-before-after",
        action="store_true",
        help="Include raw vs final prompt sections (Markdown or --report-json)",
    )
    parser.add_argument(
        "--no-report-summary",
        action="store_true",
        help="Omit executive summary from Markdown / structured report",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings)
    settings.apply_langchain_env()

    raw: str | None = args.prompt
    if args.file is not None:
        raw = args.file.read_text(encoding="utf-8")
    if raw is None:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    if raw is None or not str(raw).strip():
        parser.error("Provide prompt as argument, --file, or stdin")

    if args.dry_run:
        payload = {
            "llm_provider": settings.llm_provider,
            "model": settings.resolved_model(),
            "base_url": settings.resolved_base_url(),
            "max_critic_iterations": settings.max_critic_iterations,
            "critic_use_prm": settings.critic_use_prm,
            "prm_min_score": settings.prm_min_score,
            "prm_model": settings.resolved_prm_model(),
        }
        print(json.dumps(payload, indent=2))
        return 0

    llm = build_llm_client(settings)
    result = run_compiler(raw.strip(), settings, llm)

    if args.json:
        printable = {k: v for k, v in result.items()}
        print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
        return 0

    if args.markdown:
        md = render_compilation_report(
            result,
            settings=settings,
            include_summary=not args.no_report_summary,
            include_before_after=args.report_before_after,
        )
        print(md, end="")
        return 0

    if args.report_json:
        payload = compilation_report_dict(
            result,
            settings=settings,
            include_summary=not args.no_report_summary,
            include_before_after=args.report_before_after,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 0

    print(result.get("final_prompt", ""))
    return 0
