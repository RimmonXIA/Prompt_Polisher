from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

from rich_argparse import RawDescriptionRichHelpFormatter

from prompt_polisher.config import Settings, get_settings
from prompt_polisher.graph import run_compiler_async
from prompt_polisher.llm import build_llm_client
from prompt_polisher.logging_config import configure_logging
from prompt_polisher.report import compilation_report_dict, render_compilation_report
from prompt_polisher.state import GraphState
from prompt_polisher.text import sanitize_user_input
from prompt_polisher.ux import SessionRenderer

logger = logging.getLogger(__name__)

# Apply our application's branding to the help groups
RawDescriptionRichHelpFormatter.styles["argparse.groups"] = "bold cyan"

# Exit codes (documented in README — keep stable for automation).
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_COMPILATION_ABORTED = 2

ENVELOPE_SCHEMA_VERSION = 1

_HELP_DESC = """\
[bold]Prompt Polisher[/bold] ✦ Elevate your raw ideas into professional-grade AI prompts.
Automatically infuses structured logic, persona constraints, and systemic best practices.

[bold]Examples:[/bold]
  $ prompt-polisher "help me write a python script"
  $ prompt-polisher -f my_draft.txt --markdown > output.md
"""


_HELP_EPILOG = """\
[bold cyan]Automation & Exit Codes[/bold cyan]
  [dim]• Exit:[/dim] [green]0[/green] Success, [yellow]2[/yellow] Abort, [red]1[/red] Error.
    (Payload on stdout, logs on stderr)
  [dim]• Env:[/dim]  [bold]PROMPT_POLISHER_AGENT=1[/bold] forces `--envelope` output.
  [dim]• Docs:[/dim] See "Agents and automation" in README.md for schema.

[bold cyan]Evaluation harness[/bold cyan]
  [dim]•[/dim] [bold]prompt-polisher-eval --help[/bold] — bundled eval CLI reference.
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
    """True when primary stdout is JSON for agents (--envelope, or env)."""
    if args.envelope:
        return True
    if args.report:
        return False
    return _truthy_env("PROMPT_POLISHER_AGENT")


def _dampen_http_client_loggers() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)


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
        "compiled": not aborted,
        "version": ENVELOPE_SCHEMA_VERSION,
        "report": data,
        "abort_reason": err,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prompt-polisher",
        formatter_class=RawDescriptionRichHelpFormatter,
        description=_HELP_DESC,
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
        "Output Formats", "At most one; default is final prompt text on stdout"
    )
    output_g.add_argument(
        "-m",
        "--markdown",
        "--report",
        dest="report",
        action="store_true",
        help="Prints a rich Markdown analytical report (includes deliverables, diff & summary)",
    )
    output_g.add_argument(
        "--envelope",
        action="store_true",
        help="Prints a structured API JSON envelope (for Agents/CI)",
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
        help=(
            "stderr: keep httpx/httpcore INFO (JSON modes normally hide it); "
            "in interactive TTY mode, show the full input in the splash panel"
        ),
    )

    other_g = parser.add_argument_group("Other")
    other_g.add_argument(
        "-V",
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    other_g.add_argument(
        "--agent-card",
        action="store_true",
        help="Print A2A Agent Card JSON (spec §8.5) and exit",
    )
    other_g.add_argument(
        "--serve",
        action="store_true",
        help="Start A2A HTTP Server (e.g. 'prompt-polisher --serve --port 8000')",
    )
    other_g.add_argument(
        "--host",
        default="0.0.0.0",
        help="A2A Server host (default: 0.0.0.0)",
    )
    other_g.add_argument(
        "--port",
        type=int,
        default=8000,
        help="A2A Server port (default: 8000)",
    )

    try:
        args = parser.parse_args(argv)
        formats_count = sum([bool(args.report), bool(args.envelope)])
        if formats_count > 1:
            parser.error("argument -m/--markdown/--report/--envelope: mutually exclusive")
    except argparse.ArgumentError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.version:
        print(_package_version())
        return EXIT_SUCCESS

    if args.serve:
        import uvicorn

        from prompt_polisher.a2a_server import app

        print(f"🚀 Starting A2A Server on {args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port)
        return EXIT_SUCCESS

    if args.agent_card:
        from prompt_polisher.agent_card import build_agent_card

        print(json.dumps(build_agent_card(), indent=2, ensure_ascii=False))
        return EXIT_SUCCESS

    settings = get_settings()
    configure_logging(settings)
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    if not args.verbose:
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

    use_envelope = bool(args.envelope)
    if not (args.report or args.envelope):
        if _truthy_env("PROMPT_POLISHER_AGENT"):
            use_envelope = True

    # Interactive UX: spinner + contextual messages when a human is watching.
    # Must be disabled in machine/pipe mode so stderr stays clean.
    _interactive = not _machine_json_stdout(args) and sys.stderr.isatty()

    try:
        llm = build_llm_client(settings)
        sanitized = sanitize_user_input(raw.strip())
        source_label = args.file.name if args.file is not None else None
        renderer = (
            SessionRenderer(
                raw_prompt=sanitized,
                version=_package_version(),
                verbose=bool(args.verbose),
                source_label=source_label,
            )
            if _interactive
            else None
        )

        def _on_start(node_name: str, event: dict[str, object]) -> None:
            if renderer:
                renderer.on_node_start(node_name)

        def _on_done(node_name: str, event: dict[str, object]) -> None:
            if renderer:
                renderer.on_node_done(node_name, event=event)

        t0 = time.monotonic()
        try:
            result = asyncio.run(
                run_compiler_async(
                    sanitized,
                    settings,
                    llm,
                    on_node_start=_on_start if renderer else None,
                    on_node_done=_on_done if renderer else None,
                )
            )
            if renderer:
                # Robust comparison: ignore extra whitespace or trailing dots/newlines
                f_p = result.get("final_prompt", "").strip().rstrip(". \n\r")
                s_p = sanitized.strip().rstrip(". \n\r")
                was_fallback = (not bool(result.get("critic_passed"))) and (f_p == s_p)
                renderer.finish(
                    elapsed=time.monotonic() - t0,
                    was_aborted=bool(result.get("compilation_aborted")),
                    was_fallback=was_fallback,
                )
        except KeyboardInterrupt:
            if renderer:
                renderer.interrupt()
            return 130
    except ValueError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except Exception:
        logger.exception("pipeline error")
        print(f"{parser.prog}: error: unexpected failure during compilation", file=sys.stderr)
        return EXIT_ERROR

    code = exit_code_for_state(result)

    if args.report:
        md = render_compilation_report(
            result,
            settings=settings,
            include_summary=True,
            include_before_after=True,
        )
        print(md, end="")
        return code

    if use_envelope:
        env_payload = compilation_envelope(
            result,
            settings=settings,
            include_summary=True,
            include_before_after=True,
        )
        print(json.dumps(env_payload, indent=2, ensure_ascii=False, default=str))
        return code

    if renderer:
        renderer.print_result_header()

    print(result.get("final_prompt", ""))

    if renderer:
        renderer.print_result_footer()

    return code
