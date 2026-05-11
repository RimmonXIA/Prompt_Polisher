from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from prompt_polisher.llm.errors import (
    ProviderAuthError,
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from prompt_polisher.llm.protocol import ChatMessage


def _split_system_messages(
    messages: Sequence[ChatMessage],
) -> tuple[str | None, list[dict[str, str]]]:
    system_chunks: list[str] = []
    converted: list[dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", ""))
        if role == "system":
            if content:
                system_chunks.append(content)
            continue
        normalized_role = "assistant" if role == "assistant" else "user"
        converted.append({"role": normalized_role, "content": content})
    if not converted:
        converted = [{"role": "user", "content": ""}]
    system = "\n\n".join(system_chunks) if system_chunks else None
    return system, converted


class AnthropicAdapter:
    def __init__(self, *, api_key: str, default_model: str) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - only when dependency missing
            msg = "anthropic package is required for LLM_PROVIDER=anthropic"
            raise RuntimeError(msg) from exc

        self._anthropic = anthropic
        self._default_model = default_model
        self._sync_client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self._async_client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    def _map_error(self, exc: Exception) -> Exception:
        anthropic = self._anthropic
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderTimeoutError(str(exc))
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderConnectionError(str(exc))
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderRateLimitError(str(exc))
        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderAuthError(str(exc))
        if isinstance(exc, anthropic.APIStatusError):
            status_code = getattr(exc, "status_code", "unknown")
            return ProviderResponseError(f"status={status_code}: {exc}")
        return exc

    @staticmethod
    def _extract_text(response: Any) -> str:
        blocks = getattr(response, "content", None)
        if not isinstance(blocks, list):
            raise ProviderResponseError("Anthropic response has no content blocks")
        out: list[str] = []
        for block in blocks:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "")
                if isinstance(text, str):
                    out.append(text)
        return "".join(out)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        request_model = model or self._default_model
        system, converted = _split_system_messages(messages)
        try:
            response = self._sync_client.messages.create(
                model=request_model,
                messages=cast(Any, converted),
                temperature=temperature,
                max_tokens=2048,
                system=cast(Any, system),
                timeout=timeout,
            )
            return self._extract_text(response)
        except Exception as exc:  # pragma: no cover - covered by unit tests
            raise self._map_error(exc) from exc

    async def acomplete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        request_model = model or self._default_model
        system, converted = _split_system_messages(messages)
        try:
            response = await self._async_client.messages.create(
                model=request_model,
                messages=cast(Any, converted),
                temperature=temperature,
                max_tokens=2048,
                system=cast(Any, system),
                timeout=timeout,
            )
            return self._extract_text(response)
        except Exception as exc:  # pragma: no cover - covered by unit tests
            raise self._map_error(exc) from exc
