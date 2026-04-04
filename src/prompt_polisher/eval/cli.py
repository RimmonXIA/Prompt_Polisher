from __future__ import annotations

import argparse
import asyncio
import json
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from prompt_polisher.config import get_settings
from prompt_polisher.eval.load import load_evalset, resolve_evalset_dir
from prompt_polisher.eval.runner import run_eval_suite
from prompt_polisher.llm import build_llm_client

RawDescriptionRichHelpFormatter.styles["argparse.groups"] = "bold cyan"

_EVAL_HELP_DESC = """\
[bold]prompt-polisher-eval[/bold] — Phase 1 trust-base evaluation for Prompt Polisher.

[bold]What it does[/bold]
  • [bold]Tier A[/bold]: Run the compile graph per item; check [dim]structural_expect[/dim] in
    [dim]items.jsonl[/dim] (critic pass, abort, non-empty [dim]final_prompt[/dim], …).
  • [bold]Tier B[/bold] (unless [bold]--structural-only[/bold]): When [dim]gold[/dim] is not
    [dim]none[/dim], call the executor twice per item — [bold]raw[/bold] intent vs
    [bold]compiled[/bold] [dim]final_prompt[/dim] — and score (exact, contains, JSON keys, …).

[bold]Examples[/bold]
  $ prompt-polisher-eval --structural-only --fail-on-structural
  $ prompt-polisher-eval --evalset-dir ./evalsets/v1 --output report.json
  $ PROMPT_POLISHER_EVALSET=/path/to/v1 prompt-polisher-eval --structural-only
"""

_EVAL_HELP_EPILOG = """\
[bold cyan]Eval set layout[/bold cyan]
  Directory with [bold]manifest.json[/bold] and [bold]items.jsonl[/bold] (one JSON object per line).
  See [dim]evalsets/v1/README.md[/dim].

[bold cyan]Discovery order[/bold cyan]
  1. [bold]--evalset-dir[/bold] if passed
  2. [bold]PROMPT_POLISHER_EVALSET[/bold]
  3. Walk upward from CWD for [dim]evalsets/v1[/dim]

[bold cyan]Credentials[/bold cyan]
  Same [dim].env[/dim] as the main CLI ([dim]OPENAI_API_KEY[/dim], [dim]LLM_MODEL[/dim], …).
  Tier A still runs the full compile pipeline (several LLM calls per item).

[bold cyan]Exit codes[/bold cyan]
  [green]0[/green]  Success (with [bold]--fail-on-structural[/bold]: all structural checks passed).
  [red]1[/red]  Error (missing eval set, bad JSONL, bad config, …).
  [yellow]2[/yellow]  Tier A regression ([bold]--fail-on-structural[/bold] only).

[bold cyan]See also[/bold cyan]
  [dim]README.md[/dim] (Evaluation Phase 1); [dim]docs/THEORY.en.md[/dim] (harness, non-claims).
"""


def _package_version() -> str:
    try:
        return pkg_version("prompt-polisher")
    except PackageNotFoundError:
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-polisher-eval",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=_EVAL_HELP_DESC,
        epilog=_EVAL_HELP_EPILOG,
        exit_on_error=False,
    )

    set_g = parser.add_argument_group("Eval set", "Where to load manifest.json + items.jsonl")
    set_g.add_argument(
        "--evalset-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="Explicit directory (default: PROMPT_POLISHER_EVALSET or discover evalsets/v1)",
    )

    run_g = parser.add_argument_group("Run mode")
    run_g.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip Tier B: no executor LLM calls (only compile graph + structural checks)",
    )

    out_g = parser.add_argument_group("Output & exit policy")
    out_g.add_argument(
        "--output",
        type=Path,
        default=None,
        metavar="FILE",
        help="Write JSON report to FILE (default: stdout)",
    )
    out_g.add_argument(
        "--fail-on-structural",
        action="store_true",
        help="Exit with code 2 if any item fails structural_expect (CI gate)",
    )

    other_g = parser.add_argument_group("Other")
    other_g.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Print package version and exit",
    )

    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        print(f"prompt-polisher-eval: error: {exc}", file=sys.stderr)
        return 1

    if args.version:
        print(_package_version())
        return 0

    evalset_dir = args.evalset_dir
    if evalset_dir is None:
        try:
            evalset_dir = resolve_evalset_dir()
        except FileNotFoundError as exc:
            print(f"prompt-polisher-eval: {exc}", file=sys.stderr)
            return 1

    settings = get_settings()
    compile_llm = build_llm_client(settings)
    executor_llm = None if args.structural_only else compile_llm

    try:
        evalset = load_evalset(evalset_dir)
    except (OSError, ValueError) as exc:
        print(f"prompt-polisher-eval: {exc}", file=sys.stderr)
        return 1

    report = asyncio.run(
        run_eval_suite(
            evalset,
            settings=settings,
            compile_llm=compile_llm,
            executor_llm=executor_llm,
            structural_only=args.structural_only,
        )
    )

    data = report.to_json_dict()
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)

    if args.fail_on_structural and data["counts"]["tier_a_failed"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
