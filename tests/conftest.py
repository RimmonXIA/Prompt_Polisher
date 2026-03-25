from __future__ import annotations

import pytest

from prompt_polisher.config import Settings, get_settings
from prompt_polisher.prompts_bundle import clear_prompt_bundle_cache


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    clear_prompt_bundle_cache()
    yield
    get_settings.cache_clear()
    clear_prompt_bundle_cache()


@pytest.fixture()
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    return get_settings()
