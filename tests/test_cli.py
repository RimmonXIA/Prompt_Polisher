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
    yield
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
        "radar_analysis": {},
        "routing_decision": {},
        "output_route": "instance",
    }


def _aborted_state() -> GraphState:
    return {
        "raw_prompt": "x",
        "final_prompt": "",
        "compilation_aborted": True,
        "abort_reason": "threat_gate",
        "abort_detail": "heuristic",
        "radar_analysis": {},
        "routing_decision": {},
    }


def test_exit_success_default_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    code = cli.main(["hi"])
    assert code == cli.EXIT_SUCCESS


def test_exit_aborted_default_text(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _aborted_state())
    code = cli.main(["hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED


@pytest.mark.parametrize(
    "mode",
    [
        ["--json"],
        ["--report-json"],
        ["--markdown"],
    ],
)
def test_exit_aborted_all_output_modes(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    mode: list[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _aborted_state())
    code = cli.main([*mode, "hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED


def test_envelope_ok_and_schema(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    code = cli.main(["--envelope", "hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["schemaVersion"] == cli.ENVELOPE_SCHEMA_VERSION
    assert out["error"] is None
    assert "deliverables" in out["data"]


def test_envelope_aborted_ok_false_and_error(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _aborted_state())
    code = cli.main(["--envelope", "hi"])
    assert code == cli.EXIT_COMPILATION_ABORTED
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["error"]["code"] == "COMPILATION_ABORTED"
    assert out["error"]["message"] == "threat_gate"


def test_agent_alias_same_as_envelope(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    code = cli.main(["--agent", "hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert out["schemaVersion"] == cli.ENVELOPE_SCHEMA_VERSION


def test_prompt_polisher_agent_env_selects_envelope(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PROMPT_POLISHER_AGENT", "1")
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    code = cli.main(["hi"])
    assert code == cli.EXIT_SUCCESS
    out = json.loads(capsys.readouterr().out)
    assert "schemaVersion" in out


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
    assert "Output:" in out
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
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    cli.main(["--envelope", "hi"])
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_default_text_does_not_dampen_httpx(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.delenv("PROMPT_POLISHER_AGENT", raising=False)
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    cli.main(["hi"])
    assert logging.getLogger("httpx").level == logging.NOTSET
    assert logging.getLogger("httpcore").level == logging.NOTSET


def test_verbose_skips_http_dampening(
    monkeypatch: pytest.MonkeyPatch,
    fake_llm: MagicMock,
) -> None:
    monkeypatch.setattr(cli, "build_llm_client", lambda _s: fake_llm)
    monkeypatch.setattr(cli, "run_compiler", lambda *_a, **_k: _happy_state())
    cli.main(["--envelope", "--verbose", "hi"])
    assert logging.getLogger("httpx").level == logging.NOTSET


def test_unreadable_file_returns_exit_error(tmp_path: object) -> None:
    p = tmp_path / "nope.txt"
    p.write_text("x", encoding="utf-8")
    p.chmod(0)
    try:
        code = cli.main(["--file", str(p)])
    finally:
        p.chmod(0o644)
    assert code == cli.EXIT_ERROR
