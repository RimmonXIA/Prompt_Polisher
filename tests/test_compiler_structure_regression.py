"""F1 phase C: anchor expected compile/critic/router shape with FakeLLM (no real API)."""

from __future__ import annotations

import pytest

from prompt_polisher.config import get_settings
from prompt_polisher.graph import run_compiler
from prompt_polisher.llm import FakeLLMClient


def _happy_path_five_calls() -> list[str]:
    """Radar → routing → compile → critic → router."""
    body = (
        "<thinking>reason step by step</thinking>"
        "<user_context>preserved user block</user_context>"
        + "x" * 30
    )
    return [
        '{"negations_flipped":"Do X clearly","threats":[],"alignment_risk":"low","summary":"ok"}',
        '{"complexity":"low","multi_node_recommended":false,'
        '"anchor_persona":"expert","rationale":"simple"}',
        f'{{"draft":"{body}"}}',
        '{"pass":true,"feedback":"","issues":[]}',
        '{"final_prompt":"FINAL_PROMPT","workflow_blueprint":"WF","dspy_sketch":"DSPY"}',
    ]


def test_run_compiler_happy_path_draft_has_expected_xml_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("MAX_CRITIC_ITERATIONS", "3")
    monkeypatch.delenv("CRITIC_USE_PRM", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.critic_use_prm is False

    out = run_compiler("hello world", settings, FakeLLMClient(_happy_path_five_calls()))

    assert not out.get("compilation_aborted")
    assert out.get("critic_passed") is True
    assert out.get("final_prompt") == "FINAL_PROMPT"
    draft = str(out.get("draft") or "")
    assert "<thinking>" in draft
    assert "</thinking>" in draft
    assert "<user_context>" in draft
    assert "</user_context>" in draft
