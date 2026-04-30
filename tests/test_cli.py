from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import pytest

from prompt_polisher import cli
from prompt_polisher.config import get_settings
from prompt_polisher.state import GraphState


@pytest.fixture(autouse=True)
def _cli_api_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_http_loggers() -> None:
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)
    yield  # type: ignore[misc]
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)


@pytest.fixture()
def fake_llm() -> MagicMock:
    return MagicMock()


def _happy_state() -> GraphState:
    return {
        "raw_prompt": "x",
        "final_prompt": "compiled",
        "compilation_aborted": False,
        "prompt_type": "coding_prompt",
        "prompt_type_confidence": 0.88,
        "optimization_target": "strict_format",
        "llm_call_count": 3,
        "nodes_executed": ["intent_sniffer", "compute_aware_router", "structured_compiler"],
        "cost_signals": {"raw_prompt_chars": 1, "final_prompt_chars": 8},
        "quality_signals": {"intent_preserved": True, "over_expansion_risk": "low"},
        "intent_sniffer_analysis": {},
        "compute_aware_routing_decision": {},
        "output_route": "instance",
    }


def _aborted_state() -> GraphState:
    return {
        "raw_prompt": "x",
        "final_prompt": "",
        "compilation_aborted": True,
        "abort_reason": "threat_gate",
        "abort_detail": "heuristic",
        "intent_sniffer_analysis": {},
        "compute_aware_routing_decision": {},
    }


async def _async_happy(*_a: object, **_k: object) -> GraphState:
    return _happy_state()


async def _async_aborted(*_a: object, **_k: object) -> GraphState:
    return _aborted_state()


def test_exit_success_default_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(["hi"])
    assert code == cli.EXIT_SUCCESS


def test_exit_aborted_default_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_aborted)
    code = cli.main(["hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED


@pytest.mark.parametrize(
    "mode",
    [
        ["--markdown"],
        ["--envelope"],
    ],
)
def test_exit_aborted_all_output_modes(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    mode: list[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_aborted)
    code = cli.main([*mode, "hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED


def test_envelope_ok_and_schema(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(["--envelope", "hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["compiled"] is True
    assert out["version"] == cli.ENVELOPE_SCHEMA_VERSION
    assert out["mode"] == "balanced"
    assert out["optimization_target"] == "strict_format"
    assert out["prompt_type"] == "coding_prompt"
    assert out["llm_call_count"] == 3
    assert out["nodes_executed"] == [
        "intent_sniffer",
        "compute_aware_router",
        "structured_compiler",
    ]
    assert out["cost_signals"]["final_prompt_chars"] == 8
    assert out["quality_signals"]["intent_preserved"] is True
    assert out["abort_reason"] is None
    assert "deliverables" in out["report"]
    assert "runtime" in out["report"]


def test_envelope_aborted_ok_false_and_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_aborted)
    code = cli.main(["--envelope", "hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED
    out = json.loads(capsys.readouterr().out)
    assert out["compiled"] is False
    assert out["abort_reason"]["code"] == "COMPILATION_ABORTED"
    assert out["abort_reason"]["message"] == "threat_gate"


def test_prompt_polisher_agent_env_selects_envelope(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PROMPT_POLISHER_AGENT", "1")
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(["hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert "version" in out


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--version"])
    assert code == 0
    assert capsys.readouterr().out.strip()


def test_help_exits_zero_and_groups(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "PROMPT_POLISHER_AGENT" in out
    assert "Input:" in out
    assert "Output Formats:" in out
    assert "Logging:" in out


def test_missing_prompt_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    code = cli.main([])
    assert code == cli.EXIT_ERROR


def test_exit_code_for_state() -> None:
    assert cli.exit_code_for_state({"compilation_aborted": True}) == cli.EXIT_COMPILATION_ABORTED
    assert cli.exit_code_for_state({"compilation_aborted": False}) == cli.EXIT_SUCCESS


def test_build_llm_value_error_returns_exit_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_settings: object) -> None:
        raise ValueError("missing credentials")

    monkeypatch.setattr(cli, "build_llm_client", _boom)
    code = cli.main(["hi"])
    assert code == cli.EXIT_ERROR


def test_machine_json_mode_dampens_httpx(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    cli.main(["--envelope", "hi"])
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_default_text_dampens_httpx_by_default(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.delenv("PROMPT_POLISHER_AGENT", raising=False)
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    cli.main(["hi"])
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_verbose_skips_http_dampening(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    cli.main(["--envelope", "--verbose", "hi"])
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_unreadable_file_returns_exit_error(tmp_path: object) -> None:
    p = tmp_path / "nope.txt"  # type: ignore[operator]
    p.write_text("x", encoding="utf-8")
    p.chmod(0)
    try:
        code = cli.main(["--file", str(p)])
    finally:
        p.chmod(0o644)
    assert code == cli.EXIT_ERROR


def test_agent_card_exits_zero_and_valid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["--agent-card"])
    assert code == cli.EXIT_SUCCESS
    out = capsys.readouterr().out
    card = json.loads(out)
    assert card["name"] == "Prompt Polisher"
    assert isinstance(card["skills"], list)
    assert len(card["skills"]) > 0
    assert card["skills"][0]["id"] == "prompt-compile"
    assert card["supportedInterfaces"] == []
    assert card["capabilities"]["streaming"] is False


def test_compare_json_success_with_judge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_llm = MagicMock()
    fake_llm.chat.side_effect = [
        "raw-output",
        "compiled-output",
        '{"verdict":"polished_wins","rationale":"better structured"}',
    ]
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(
        [
            "compare",
            "--raw",
            "raw prompt",
            "--task-input",
            "task input",
            "--json",
        ]
    )
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["compiled_available"] is True
    assert out["compiled_prompt_type"] == "coding_prompt"
    assert out["compiled_optimization_target"] == "strict_format"
    assert out["compiled_llm_call_count"] == 3
    assert out["compiled_nodes_executed"] == [
        "intent_sniffer",
        "compute_aware_router",
        "structured_compiler",
    ]
    assert out["compiled_cost_signals"]["raw_prompt_chars"] == 1
    assert out["compiled_quality_signals"]["over_expansion_risk"] == "low"
    assert out["raw_output"] == "raw-output"
    assert out["compiled_output"] == "compiled-output"
    assert out["judge"]["verdict"] == "polished_wins"
    assert fake_llm.chat.call_count == 3


def test_compare_structural_only_skips_judge(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_llm = MagicMock()
    fake_llm.chat.side_effect = ["raw-output", "compiled-output"]
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(
        [
            "compare",
            "--raw",
            "raw prompt",
            "--task-input",
            "task input",
            "--structural-only",
            "--json",
        ]
    )
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["judge"] is None
    assert fake_llm.chat.call_count == 2


def test_envelope_mode_override(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_happy)
    code = cli.main(["--mode", "fast", "--envelope", "hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "fast"


def test_envelope_target_override(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def _async_no_target(*_a: object, **_k: object) -> GraphState:
        return {
            "raw_prompt": "x",
            "final_prompt": "compiled",
            "compilation_aborted": False,
            "intent_sniffer_analysis": {},
            "compute_aware_routing_decision": {},
            "output_route": "instance",
        }

    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_no_target)
    code = cli.main(["--target", "concise", "--envelope", "hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["optimization_target"] == "concise"


def test_compare_returns_abort_when_compile_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_llm = MagicMock()
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler_async", _async_aborted)
    code = cli.main(
        [
            "compare",
            "--raw",
            "raw prompt",
            "--task-input",
            "task input",
            "--json",
        ]
    )
    assert code == cli.EXIT_COMPILATION_ABORTED
    out = json.loads(capsys.readouterr().out)
    assert out["compiled_available"] is False
    assert out["error"]["code"] == "COMPILATION_UNAVAILABLE"
