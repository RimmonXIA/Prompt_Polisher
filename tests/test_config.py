from __future__ import annotations

import pytest

from prompt_polisher.config import get_settings


def test_resolved_model_openai_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resolved_model() == "gpt-4o-mini"


def test_author_trust_mode_defaults_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("AUTHOR_TRUST_MODE", raising=False)
    get_settings.cache_clear()
    assert get_settings().author_trust_mode is True


def test_resolved_prm_model_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "main-model")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resolved_prm_model() == "main-model"
    monkeypatch.setenv("PRM_MODEL", "reward-model")
    get_settings.cache_clear()
    assert get_settings().resolved_prm_model() == "reward-model"


def test_critic_use_prm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("CRITIC_USE_PRM", "true")
    get_settings.cache_clear()
    assert get_settings().critic_use_prm is True


def test_resolved_model_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "custom")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resolved_model() == "custom"


def test_deepseek_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    get_settings.cache_clear()
    s = get_settings()
    assert s.resolved_base_url() == "https://api.deepseek.com/v1"


def test_apply_langchain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "p")
    get_settings.cache_clear()
    s = get_settings()
    s.apply_langchain_env()
    import os

    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert os.environ.get("LANGCHAIN_PROJECT") == "p"


def test_resolved_api_key_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    s = get_settings()
    with pytest.raises(ValueError):
        s.resolved_api_key()
