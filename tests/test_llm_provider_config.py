from __future__ import annotations

import pytest

from prompt_polisher.config import get_settings
from prompt_polisher.llm.config import AnthropicConfig, GeminiConfig, OpenAICompatConfig


def test_resolve_provider_config_openai_compat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    get_settings.cache_clear()

    cfg = get_settings().resolve_provider_config()
    assert isinstance(cfg, OpenAICompatConfig)
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.base_url == "https://api.deepseek.com"


def test_resolve_provider_config_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "claude-3-7-sonnet-latest")
    get_settings.cache_clear()

    cfg = get_settings().resolve_provider_config()
    assert isinstance(cfg, AnthropicConfig)
    assert cfg.model == "claude-3-7-sonnet-latest"


def test_resolve_provider_config_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "google")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    get_settings.cache_clear()

    cfg = get_settings().resolve_provider_config()
    assert isinstance(cfg, GeminiConfig)
    assert cfg.model == "gemini-2.0-flash"


def test_resolve_provider_config_errors_for_missing_provider_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(ValueError):
        get_settings().resolve_provider_config()
