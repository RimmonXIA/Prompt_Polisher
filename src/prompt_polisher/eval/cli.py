from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from rich_argparse import RawDescriptionRichHelpFormatter

from prompt_polisher.config import get_settings
from prompt_polisher.eval.load import EvalSet, load_evalset, resolve_evalset_dir
from prompt_polisher.eval.runner import run_eval_suite
from prompt_polisher.llm import build_llm_client

RawDescriptionRichHelpFormatter.styles["argparse.groups"] = "bold cyan"

_EVAL_HELP_DESC = """\
[bold]prompt-polisher-eval[/bold] — Run the bundled eval suite; print one JSON report to stdout.

[bold]Important[/bold]  Default is [bold]full[/bold] eval (many API calls per item).
  JSON is printed [bold]once at the end[/bold] — stdout may look idle for minutes.
  Stderr shows a startup line by default; add [bold]-v[/bold] for each item.

[bold]Quick start[/bold] (needs a working LLM — same credentials as [dim]prompt-polisher[/dim])
  1. [bold]cd[/bold] to the repo root so [dim]evalsets/bundled[/dim] is found, OR set
     [bold]PROMPT_POLISHER_EVALSET[/bold] / [bold]--evalset-dir[/bold].
  2. Configure [dim].env[/dim] (see [dim].env.example[/dim]), e.g. [dim]OPENAI_API_KEY[/dim].
  3. Run:
       [dim]$ uv run prompt-polisher-eval --structural-only[/dim]
     Optional: [bold]--output report.json[/bold]. For CI, [bold]--fail-on-structural[/bold] exits
     [yellow]2[/yellow] when a structural check fails.
  4. Full run (more API calls for items with [dim]gold[/dim]):
       [dim]$ uv run prompt-polisher-eval --output report.json[/dim]
  No API key? Offline: [dim]uv run pytest tests/test_eval.py[/dim]

[bold]What it measures[/bold]
  • [bold]Tier A[/bold]: After compile, check [dim]structural_expect[/dim] in
    [dim]items.jsonl[/dim].
  • [bold]Tier B[/bold] (if not [bold]--structural-only[/bold]): Score [bold]raw[/bold] vs
    [bold]compiled[/bold] outputs for non-[dim]none[/dim] [dim]gold[/dim].

[bold]More examples[/bold]
  $ prompt-polisher-eval --evalset-dir ./evalsets/bundled --structural-only --fail-on-structural
  $ PROMPT_POLISHER_EVALSET=/path/to/evalsets/bundled prompt-polisher-eval --structural-only
"""

_EVAL_HELP_EPILOG = """\
[bold cyan]Eval set layout[/bold cyan]
  Directory with [bold]manifest.json[/bold] and [bold]items.jsonl[/bold] (one JSON object per line).
  See [dim]evalsets/bundled/README.md[/dim].

[bold cyan]Discovery order[/bold cyan]
  1. [bold]--evalset-dir[/bold] if passed
  2. [bold]PROMPT_POLISHER_EVALSET[/bold]
  3. Walk upward from CWD for [dim]evalsets/bundled[/dim]

[bold cyan]Credentials[/bold cyan]
  Same [dim].env[/dim] as the main CLI ([dim]OPENAI_API_KEY[/dim], [dim]LLM_MODEL[/dim], …).
  Tier A still runs the full compile pipeline (several LLM calls per item).

[bold cyan]Output timing[/bold cyan]
  The full JSON prints once at the end. Until then you may see only stderr (default one-line
  banner, or [bold]-v[/bold] per-item lines).

[bold cyan]Exit codes[/bold cyan]
  [green]0[/green]  Success (with [bold]--fail-on-structural[/bold]: all structural checks passed).
  [red]1[/red]  Error (missing eval set, bad JSONL, bad config, …).
  [yellow]2[/yellow]  Tier A regression ([bold]--fail-on-structural[/bold] only).

[bold cyan]See also[/bold cyan]
  [dim]README.md[/dim] (Evaluation harness); [dim]docs/THEORY.en.md[/dim] (harness, non-claims).
"""


def _package_version() -> str:
    try:
        return pkg_version("prompt-polisher")
    except PackageNotFoundError:
        return "0.0.0"


def _slice_evalset(
    evalset: EvalSet,
    *,
    id_regex: str | None,
    max_items: int | None,
) -> EvalSet:
    items = list(evalset.items)

    if id_regex:
        try:
            pattern = re.compile(id_regex)
        except re.error as exc:
            msg = f"invalid --id-regex pattern: {exc}"
            raise ValueError(msg) from exc
        items = [item for item in items if pattern.search(item.id)]

    if max_items is not None:
        if max_items <= 0:
            msg = "--max-items must be >= 1"
            raise ValueError(msg)
        items = items[:max_items]

    if not items:
        msg = "no eval items selected (check --id-regex / --max-items)"
        raise ValueError(msg)

    return EvalSet(manifest=evalset.manifest, items=items, source_dir=evalset.source_dir)


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
        help="Explicit directory (default: PROMPT_POLISHER_EVALSET or discover evalsets/bundled)",
    )

    run_g = parser.add_argument_group("Run mode")
    run_g.add_argument(
        "--structural-only",
        action="store_true",
        help="Skip Tier B: no executor LLM calls (only compile graph + structural checks)",
    )
    run_g.add_argument(
        "--id-regex",
        default=None,
        metavar="REGEX",
        help="Run only items whose id matches REGEX",
    )
    run_g.add_argument(
        "--max-items",
        type=int,
        default=None,
        metavar="N",
        help="Run only the first N items after filtering",
    )
    run_g.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print per-item progress lines to stderr (stdout stays JSON only)",
    )
    run_g.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="No stderr banner or progress (stdout JSON only when done)",
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
        total_items = len(evalset.items)
        evalset = _slice_evalset(
            evalset,
            id_regex=args.id_regex,
            max_items=args.max_items,
        )
    except (OSError, ValueError) as exc:
        print(f"prompt-polisher-eval: {exc}", file=sys.stderr)
        return 1

    log_fn = None
    if args.verbose and not args.quiet:

        def _log_progress(msg: str) -> None:
            print(msg, file=sys.stderr)

        log_fn = _log_progress
    if not args.quiet:
        mode = "structural-only" if args.structural_only else "full"
        n = len(evalset.items)
        print(
            "prompt-polisher-eval: starting "
            f"{n} item(s) selected from {total_items}, mode={mode!r}. "
            "JSON on stdout when done.",
            file=sys.stderr,
        )

    report = asyncio.run(
        run_eval_suite(
            evalset,
            settings=settings,
            compile_llm=compile_llm,
            executor_llm=executor_llm,
            structural_only=args.structural_only,
            log=log_fn,
        )
    )

    data = report.to_json_dict()
    data["selection"] = {
        "total_items": total_items,
        "selected_items": len(evalset.items),
        "id_regex": args.id_regex,
        "max_items": args.max_items,
    }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
        sys.stdout.flush()

    if args.fail_on_structural and data["counts"]["tier_a_failed"] > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
