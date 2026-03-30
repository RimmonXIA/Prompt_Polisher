from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol, cast, runtime_checkable

import httpx
from openai import APIConnectionError, AsyncOpenAI, OpenAI

from prompt_polisher.config import Settings
from prompt_polisher.observability import start_llm_span
from prompt_polisher.text import preview_text

logger = logging.getLogger(__name__)

# Extra attempts after the SDK exhausts its own retries.
# We set the SDK's internal max_retries to 0 so we don't multiply these!
_TRANSPORT_ATTEMPTS = 3
_TRANSPORT_BACKOFF_SEC = 2.0


@runtime_checkable
class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str: ...

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str: ...


class OpenAICompatibleClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        api_key = settings.resolved_api_key()
        base_url = settings.resolved_base_url()
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": 0,
            "timeout": httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0),
        }
        if base_url is not None:
            client_kwargs["base_url"] = base_url
        self._client = OpenAI(**client_kwargs)
        self._async_client = AsyncOpenAI(**client_kwargs)
        self._model = settings.resolved_model()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        temp = self._settings.llm_temperature if temperature is None else temperature
        resolved_model = model if model else self._model
        preview = None
        if self._settings.log_prompt_previews:
            preview = preview_text(str(messages))

        span = start_llm_span(self._settings, name="llm.chat", input_preview=preview)
        last_conn: APIConnectionError | None = None
        for transport_try in range(_TRANSPORT_ATTEMPTS):
            try:
                resp = self._client.chat.completions.create(
                    model=resolved_model,
                    messages=cast(Any, messages),
                    temperature=temp,
                )
                content = resp.choices[0].message.content or ""
                span.end(
                    output=preview_text(content) if self._settings.log_prompt_previews else None,
                )
                return content
            except APIConnectionError as exc:
                last_conn = exc
                if transport_try >= _TRANSPORT_ATTEMPTS - 1:
                    break
                delay = _TRANSPORT_BACKOFF_SEC * (2**transport_try)
                logger.warning(
                    "LLM connection error (attempt %s/%s), retrying in %.1fs: %s",
                    transport_try + 1,
                    _TRANSPORT_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)
            except Exception:
                span.end(output=None)
                raise
        span.end(output=None)
        if last_conn is not None:
            raise last_conn
        msg = "LLM transport retries exhausted without error state"
        raise RuntimeError(msg)

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        temp = self._settings.llm_temperature if temperature is None else temperature
        resolved_model = model if model else self._model
        preview = None
        if self._settings.log_prompt_previews:
            preview = preview_text(str(messages))

        span = start_llm_span(self._settings, name="llm.achat", input_preview=preview)
        last_conn: APIConnectionError | None = None
        for transport_try in range(_TRANSPORT_ATTEMPTS):
            try:
                resp = await self._async_client.chat.completions.create(
                    model=resolved_model,
                    messages=cast(Any, messages),
                    temperature=temp,
                )
                content = resp.choices[0].message.content or ""
                span.end(
                    output=preview_text(content) if self._settings.log_prompt_previews else None,
                )
                return content
            except APIConnectionError as exc:
                last_conn = exc
                if transport_try >= _TRANSPORT_ATTEMPTS - 1:
                    break
                delay = _TRANSPORT_BACKOFF_SEC * (2**transport_try)
                logger.warning(
                    "LLM async connection error (attempt %s/%s), retrying in %.1fs: %s",
                    transport_try + 1,
                    _TRANSPORT_ATTEMPTS,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
            except Exception:
                span.end(output=None)
                raise
        span.end(output=None)
        if last_conn is not None:
            raise last_conn
        msg = "LLM async transport retries exhausted without error state"
        raise RuntimeError(msg)


class FakeLLMClient:
    """Test double: returns scripted assistant messages in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        if not self._responses:
            msg = "FakeLLMClient has no scripted responses left"
            raise RuntimeError(msg)
        return self._responses.pop(0)

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        return self.chat(messages, temperature=temperature, model=model)


def build_llm_client(settings: Settings) -> LLMClient:
    return OpenAICompatibleClient(settings)
