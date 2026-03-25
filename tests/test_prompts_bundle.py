from __future__ import annotations

from importlib import resources
from pathlib import Path

import pytest

from prompt_polisher.config import get_settings
from prompt_polisher.llm import FakeLLMClient
from prompt_polisher.nodes import node_radar
from prompt_polisher.prompts_bundle import clear_prompt_bundle_cache, prompt_bundle


def test_package_prompt_txt_readable() -> None:
    root = resources.files("prompt_polisher") / "prompts"
    base = root.joinpath("radar_system_base.txt").read_text(encoding="utf-8")
    assert "Node1 Radar" in base
    assert root.joinpath("gate_abort_workflow_blueprint.txt").is_file()


def test_prompts_dir_env_empty_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("PROMPTS_DIR", "")
    get_settings.cache_clear()
    assert get_settings().prompts_dir is None


class _CaptureFakeLLM(FakeLLMClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        self.calls.append(messages)
        return super().chat(messages, temperature=temperature)


def test_prompts_dir_overrides_single_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    marker = "PP_OVERRIDE_RADAR_TRUSTED_XQ9Z"
    (tmp_path / "radar_system_trusted.txt").write_text(marker, encoding="utf-8")

    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("PROMPTS_DIR", str(tmp_path))
    get_settings.cache_clear()
    clear_prompt_bundle_cache()

    settings = get_settings()
    assert settings.prompts_dir is not None

    radar_json = (
        '{"negations_flipped":"x","threats":[],"alignment_risk":"low",'
        '"summary":"s"}'
    )
    llm = _CaptureFakeLLM([radar_json])
    node_radar({"raw_prompt": "hello"}, llm, settings)  # type: ignore[arg-type]
    system = llm.calls[0][0]["content"]
    assert marker in system
    assert "Node1 Radar" in system

    monkeypatch.delenv("PROMPTS_DIR", raising=False)
    get_settings.cache_clear()
    clear_prompt_bundle_cache()


def test_prompt_bundle_cached_per_resolved_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("PROMPTS_DIR", raising=False)
    get_settings.cache_clear()
    clear_prompt_bundle_cache()
    s = get_settings()
    b1 = prompt_bundle(s)
    b2 = prompt_bundle(s)
    assert b1 is b2
