from __future__ import annotations

import pytest

from prompt_polisher.config import get_settings
from prompt_polisher.llm import FakeLLMClient
from prompt_polisher.nodes import node_compile, node_radar


class RecordingFakeLLM(FakeLLMClient):
    """Records chat messages; uses FakeLLMClient for scripted replies."""

    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        self.calls.append(messages)
        return super().chat(messages, temperature=temperature, model=model)


DRR_LIKE_RAW = """#### M1: DRR (Decode - Reframe - Response)

* **Decode:** Identify the hidden intent (ignore literal, surface-level framing).

* **Reframe:** Elevate the query to a first-principle level.

* **Response:** Answer the reframed query. Do not provide a direct answer to the flawed raw input.
"""


def test_author_trust_mode_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("AUTHOR_TRUST_MODE", "false")
    get_settings.cache_clear()
    assert get_settings().author_trust_mode is False
    monkeypatch.setenv("AUTHOR_TRUST_MODE", "true")
    get_settings.cache_clear()
    assert get_settings().author_trust_mode is True


def test_radar_system_prompt_trusted_author_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("AUTHOR_TRUST_MODE", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    radar_json = (
        '{"negations_flipped":"x","threats":[],"alignment_risk":"low",'
        '"summary":"pedagogical DRR"}'
    )
    llm = RecordingFakeLLM([radar_json])
    node_radar({"raw_prompt": DRR_LIKE_RAW}, llm, settings)  # type: ignore[arg-type]
    system = llm.calls[0][0]["content"]
    assert "trusted prompt author" in system.lower()
    assert "decode-reframe-response" in system.lower()


def test_radar_prompt_defensive_when_author_trust_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("AUTHOR_TRUST_MODE", "false")
    get_settings.cache_clear()
    settings = get_settings()
    llm = RecordingFakeLLM(
        ['{"negations_flipped":"x","threats":[],"alignment_risk":"low","summary":"s"}'],
    )
    node_radar({"raw_prompt": DRR_LIKE_RAW}, llm, settings)  # type: ignore[arg-type]
    system = llm.calls[0][0]["content"]
    assert "untrusted" in system.lower()


def test_compile_system_prompt_preserves_methodology(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    settings = get_settings()
    llm = RecordingFakeLLM(['{"draft":"<user_context>DRR</user_context>"}'])
    state = {
        "raw_prompt": DRR_LIKE_RAW,
        "radar_analysis": {},
        "routing_decision": {},
    }
    node_compile(state, llm, settings)  # type: ignore[arg-type]
    system = llm.calls[0][0]["content"]
    lower = system.lower()
    assert "preserve the author's reasoning" in lower
    assert "refusal" in lower or "security-auditor" in lower


def test_compile_defensive_branch_when_author_trust_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("AUTHOR_TRUST_MODE", "false")
    get_settings.cache_clear()
    settings = get_settings()
    llm = RecordingFakeLLM(['{"draft":"<user_context>x</user_context>"}'])
    node_compile(
        {"raw_prompt": "x", "radar_analysis": {}, "routing_decision": {}},
        llm,
        settings,
    )  # type: ignore[arg-type]
    system = llm.calls[0][0]["content"].lower()
    assert "elevated risk" in system
