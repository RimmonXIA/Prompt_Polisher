from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from prompt_polisher.config import Settings, get_settings
from prompt_polisher.graph import run_compiler_async
from prompt_polisher.llm import build_llm_client
from prompt_polisher.logging_config import configure_logging
from prompt_polisher.report import compilation_report_dict, render_compilation_report
from prompt_polisher.state import GraphState

logger = logging.getLogger(__name__)

# Exit codes (documented in README — keep stable for automation).
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_COMPILATION_ABORTED = 2

ENVELOPE_SCHEMA_VERSION = 1

_HELP_EPILOG = """\
Automation (tool protocol):
  Exit: 0 ok, 2 threat-gate abort, 1 error. Payload on stdout; logs on stderr.
  PROMPT_POLISHER_AGENT=1 defaults to envelope JSON when no output flag is set.
  Full detail: README.md -> section "Agents and automation".
"""


def _package_version() -> str:
    try:
        return pkg_version("prompt-polisher")
    except PackageNotFoundError:
        return "0.0.0"


def _truthy_env(name: str) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _machine_json_stdout(args: argparse.Namespace) -> bool:
    """True when primary stdout is JSON for agents (--json, --report-json, --envelope, or env)."""
    if args.json or args.report_json or args.envelope:
        return True
    if args.markdown:
        return False
    return _truthy_env("PROMPT_POLISHER_AGENT")


def _dampen_http_client_loggers() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def exit_code_for_state(state: GraphState) -> int:
    if bool(state.get("compilation_aborted")):
        return EXIT_COMPILATION_ABORTED
    return EXIT_SUCCESS


def compilation_envelope(
    state: GraphState,
    *,
    settings: Settings,
    include_summary: bool,
    include_before_after: bool,
) -> dict[str, Any]:
    """Versioned JSON envelope; see README Agents and docs/AUDIT_SELF_EXPLAINING.md §3.2."""
    data = compilation_report_dict(
        state,
        settings=settings,
        include_summary=include_summary,
        include_before_after=include_before_after,
    )
    aborted = bool(state.get("compilation_aborted"))
    err: dict[str, Any] | None = None
    if aborted:
        err = {
            "code": "COMPILATION_ABORTED",
            "message": str(state.get("abort_reason") or "compilation_aborted").strip() or None,
            "detail": str(state.get("abort_detail") or "").strip() or None,
        }
    return {
        "ok": not aborted,
        "schemaVersion": ENVELOPE_SCHEMA_VERSION,
        "data": data,
        "error": err,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-polisher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Heuristic LLM prompt compiler (radar -> route -> compile -> critic). "
            "Not a guarantee of task success or safety; see docs/THEORY.zh.md."
        ),
        epilog=_HELP_EPILOG,
        exit_on_error=False,
    )

    input_g = parser.add_argument_group("Input", "Where to read the raw prompt")
    input_g.add_argument(
        "prompt",
        nargs="?",
        default=None,
        help="Text, or omit when using --file or stdin",
    )
    input_g.add_argument(
        "-f",
        "--file",
        type=Path,
        default=None,
        help="Read prompt from file (UTF-8)",
    )

    output_g = parser.add_argument_group(
        "Output",
        "At most one; default is final prompt text on stdout",
    )
    out_mx = output_g.add_mutually_exclusive_group()
    out_mx.add_argument(
        "--json",
        action="store_true",
        help="Full graph state JSON",
    )
    out_mx.add_argument(
        "--markdown",
        action="store_true",
        help="Markdown compilation report",
    )
    out_mx.add_argument(
        "--report-json",
        action="store_true",
        help="Structured report JSON (subset of state)",
    )
    out_mx.add_argument(
        "--envelope",
        "--agent",
        action="store_true",
        dest="envelope",
        help=(
            "Envelope JSON (ok, schemaVersion, data, error). "
            "See README Agents; ok=true iff threat gate did not abort."
        ),
    )

    report_g = parser.add_argument_group(
        "Report",
        "Only with --markdown, --report-json, or envelope",
    )
    report_g.add_argument(
        "--report-before-after",
        action="store_true",
        help="Include raw vs final prompt in report",
    )
    report_g.add_argument(
        "--no-report-summary",
        action="store_true",
        help="Omit executive summary block",
    )

    log_g = parser.add_argument_group("Logging")
    log_g.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="stderr: warnings and errors only",
    )
    log_g.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="stderr: keep httpx/httpcore INFO (JSON modes normally hide it)",
    )

    other_g = parser.add_argument_group("Other")
    other_g.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    other_g.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved config JSON; no LLM calls",
    )
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.version:
        print(_package_version())
        return EXIT_SUCCESS

    settings = get_settings()
    configure_logging(settings)
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    if _machine_json_stdout(args) and not args.verbose:
        _dampen_http_client_loggers()
    settings.apply_langchain_env()

    raw: str | None = args.prompt
    if args.file is not None:
        try:
            raw = args.file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.exception("failed to read --file")
            print(f"{parser.prog}: error: cannot read file: {exc}", file=sys.stderr)
            return EXIT_ERROR
    if raw is None:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    if raw is None or not str(raw).strip():
        print(
            f"{parser.prog}: error: provide prompt as argument, --file, or stdin",
            file=sys.stderr,
        )
        return EXIT_ERROR

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
        return EXIT_SUCCESS

    use_envelope = bool(args.envelope)
    if not (args.json or args.markdown or args.report_json or args.envelope):
        if _truthy_env("PROMPT_POLISHER_AGENT"):
            use_envelope = True

    # Streaming to stderr: only when output is NOT machine-consumed (no agent/json flags)
    # and the caller is an interactive terminal.
    _stream = not _machine_json_stdout(args) and sys.stderr.isatty()

    try:
        import asyncio

        from prompt_polisher.text import sanitize_user_input

        llm = build_llm_client(settings)
        sanitized = sanitize_user_input(raw.strip())
        result = asyncio.run(run_compiler_async(sanitized, settings, llm, stream_to_stderr=_stream))
    except ValueError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception:
        logger.exception("compiler failed")
        print(f"{parser.prog}: error: unexpected failure during compilation", file=sys.stderr)
        return EXIT_ERROR

    code = exit_code_for_state(result)

    if args.json:
        printable = {k: v for k, v in result.items()}
        print(json.dumps(printable, indent=2, ensure_ascii=False, default=str))
        return code

    if args.markdown:
        md = render_compilation_report(
            result,
            settings=settings,
            include_summary=not args.no_report_summary,
            include_before_after=args.report_before_after,
        )
        print(md, end="")
        return code

    if args.report_json:
        payload = compilation_report_dict(
            result,
            settings=settings,
            include_summary=not args.no_report_summary,
            include_before_after=args.report_before_after,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return code

    if use_envelope:
        env_payload = compilation_envelope(
            result,
            settings=settings,
            include_summary=not args.no_report_summary,
            include_before_after=args.report_before_after,
        )
        print(json.dumps(env_payload, indent=2, ensure_ascii=False, default=str))
        return code

    print(result.get("final_prompt", ""))
    return code
