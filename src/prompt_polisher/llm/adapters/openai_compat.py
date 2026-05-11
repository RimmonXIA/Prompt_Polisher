from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

import openai

from prompt_polisher.llm.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from prompt_polisher.llm.protocol import ChatMessage


def _extract_openai_content(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise ProviderResponseError("Provider response has no choices")
    message = getattr(choices[0], "message", None)
    if message is None:
        raise ProviderResponseError("Provider response has no message")

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content or "")


def _map_openai_error(exc: Exception) -> Exception:
    if isinstance(exc, openai.APITimeoutError):
        return ProviderTimeoutError(str(exc))
    if isinstance(exc, openai.APIConnectionError):
        return ProviderConnectionError(str(exc))
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimitError(str(exc))
    if isinstance(exc, openai.AuthenticationError):
        return ProviderAuthError(str(exc))
    if isinstance(exc, openai.APIStatusError):
        return ProviderResponseError(f"status={exc.status_code}: {exc}")
    return exc


class OpenAICompatibleAdapter:
    def __init__(self, *, api_key: str, base_url: str | None, default_model: str) -> None:
        self._default_model = default_model
        self._sync_client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self._async_client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=0)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        request_model = model or self._default_model
        converted_messages = [cast(dict[str, str], dict(m)) for m in messages]
        try:
            response = self._sync_client.chat.completions.create(
                model=request_model,
                messages=cast(Any, converted_messages),
                temperature=temperature,
                timeout=timeout,
            )
            return _extract_openai_content(response)
        except Exception as exc:  # pragma: no cover - exercised in adapter tests
            raise _map_openai_error(exc) from exc

    async def acomplete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        request_model = model or self._default_model
        converted_messages = [cast(dict[str, str], dict(m)) for m in messages]
        try:
            response = await self._async_client.chat.completions.create(
                model=request_model,
                messages=cast(Any, converted_messages),
                temperature=temperature,
                timeout=timeout,
            )
            return _extract_openai_content(response)
        except Exception as exc:  # pragma: no cover - exercised in adapter tests
            raise _map_openai_error(exc) from exc
