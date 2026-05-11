from __future__ import annotations

from types import SimpleNamespace

import httpx
import openai
import pytest

from prompt_polisher.llm.adapters.anthropic import AnthropicAdapter, _split_system_messages
from prompt_polisher.llm.adapters.google_gemini import GeminiAdapter, _to_gemini_payload
from prompt_polisher.llm.adapters.openai_compat import OpenAICompatibleAdapter
from prompt_polisher.llm.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def test_openai_compat_adapter_success(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = OpenAICompatibleAdapter(
        api_key="k",
        base_url="https://example.com",
        default_model="m",
    )
    fake_message = SimpleNamespace(content="ok")
    fake_choice = SimpleNamespace(message=fake_message)
    fake_response = SimpleNamespace(choices=[fake_choice])
    monkeypatch.setattr(adapter._sync_client.chat.completions, "create", lambda **_: fake_response)
    out = adapter.complete(
        [{"role": "user", "content": "hi"}],
        model="m",
        temperature=0.0,
        timeout=10.0,
    )
    assert out == "ok"


@pytest.mark.parametrize(
    ("error_factory", "expected"),
    [
        (
            lambda req, resp: openai.APIConnectionError(message="x", request=req),
            ProviderConnectionError,
        ),
        (
            lambda req, resp: openai.APITimeoutError(request=req),
            ProviderTimeoutError,
        ),
        (
            lambda req, resp: openai.RateLimitError(message="x", response=resp, body=None),
            ProviderRateLimitError,
        ),
        (
            lambda req, resp: openai.AuthenticationError(message="x", response=resp, body=None),
            ProviderAuthError,
        ),
        (
            lambda req, resp: openai.APIStatusError(message="x", response=resp, body=None),
            ProviderResponseError,
        ),
    ],
)
def test_openai_compat_adapter_maps_errors(
    monkeypatch: pytest.MonkeyPatch,
    error_factory: object,
    expected: type[Exception],
) -> None:
    adapter = OpenAICompatibleAdapter(
        api_key="k",
        base_url="https://example.com",
        default_model="m",
    )
    request = httpx.Request("POST", "https://example.com/v1/chat/completions")
    response = httpx.Response(429, request=request)

    def _raise(**_: object) -> object:
        factory = error_factory
        assert callable(factory)
        raise factory(request, response)

    monkeypatch.setattr(adapter._sync_client.chat.completions, "create", _raise)
    with pytest.raises(expected):
        adapter.complete(
            [{"role": "user", "content": "hi"}],
            model="m",
            temperature=0.0,
            timeout=10.0,
        )


def test_anthropic_split_system_messages() -> None:
    system, converted = _split_system_messages(
        [
            {"role": "system", "content": "s1"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
            {"role": "system", "content": "s2"},
        ]
    )
    assert system == "s1\n\ns2"
    assert converted == [{"role": "user", "content": "u"}, {"role": "assistant", "content": "a"}]


def test_anthropic_adapter_maps_connection_error() -> None:
    adapter = AnthropicAdapter.__new__(AnthropicAdapter)

    class _FakeConnectionError(Exception):
        pass

    class _FakeAnthropicModule:
        APITimeoutError = TimeoutError
        APIConnectionError = _FakeConnectionError
        RateLimitError = RuntimeError
        AuthenticationError = PermissionError
        APIStatusError = ValueError

    adapter._anthropic = _FakeAnthropicModule()  # type: ignore[attr-defined]
    mapped = adapter._map_error(_FakeConnectionError("boom"))  # type: ignore[attr-defined]
    assert isinstance(mapped, ProviderConnectionError)


def test_gemini_payload_conversion() -> None:
    system, payload = _to_gemini_payload(
        [
            {"role": "system", "content": "policy"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
    )
    assert system == "policy"
    assert payload[0]["role"] == "user"
    assert payload[1]["role"] == "model"


def test_gemini_adapter_maps_timeout_error() -> None:
    adapter = GeminiAdapter.__new__(GeminiAdapter)
    mapped = adapter._map_error(TimeoutError("late"))  # type: ignore[attr-defined]
    assert isinstance(mapped, ProviderTimeoutError)
