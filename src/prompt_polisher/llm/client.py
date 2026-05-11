from __future__ import annotations

import logging
import os
from typing import Protocol, cast, runtime_checkable

from tenacity import (
    AsyncRetrying,
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from prompt_polisher.config import Settings
from prompt_polisher.llm.errors import ProviderConnectionError
from prompt_polisher.llm.protocol import ChatMessage
from prompt_polisher.llm.registry import build_adapter
from prompt_polisher.observability import start_llm_span
from prompt_polisher.text import preview_text

logger = logging.getLogger(__name__)


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


def _normalize_socks_proxy() -> None:
    proxy_vars = [
        "ALL_PROXY",
        "all_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
    ]
    for env_var in proxy_vars:
        val = os.environ.get(env_var)
        if val and val.startswith("socks://"):
            os.environ[env_var] = val.replace("socks://", "socks5://", 1)


def _to_chat_messages(messages: list[dict[str, str]]) -> list[ChatMessage]:
    return [cast(ChatMessage, {"role": m["role"], "content": m["content"]}) for m in messages]


class UniversalLLMClient:
    def __init__(self, settings: Settings) -> None:
        _normalize_socks_proxy()
        self._settings = settings
        self._provider_config = settings.resolve_provider_config()
        self._adapter = build_adapter(self._provider_config)

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        temp = self._settings.llm_temperature if temperature is None else temperature
        request_model = model or self._provider_config.model
        preview = preview_text(str(messages)) if self._settings.log_prompt_previews else None
        span = start_llm_span(self._settings, name="llm.chat", input_preview=preview)
        try:
            for attempt in Retrying(
                retry=retry_if_exception_type(ProviderConnectionError),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                stop=stop_after_attempt(5),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            ):
                with attempt:
                    response = self._adapter.complete(
                        _to_chat_messages(messages),
                        model=request_model,
                        temperature=temp,
                        timeout=self._provider_config.timeout,
                    )
            span.end(output=preview_text(response) if self._settings.log_prompt_previews else None)
            return response
        except Exception:
            span.end(output=None)
            raise

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        temp = self._settings.llm_temperature if temperature is None else temperature
        request_model = model or self._provider_config.model
        preview = preview_text(str(messages)) if self._settings.log_prompt_previews else None
        span = start_llm_span(self._settings, name="llm.achat", input_preview=preview)
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(ProviderConnectionError),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                stop=stop_after_attempt(5),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            ):
                with attempt:
                    response = await self._adapter.acomplete(
                        _to_chat_messages(messages),
                        model=request_model,
                        temperature=temp,
                        timeout=self._provider_config.timeout,
                    )
            span.end(output=preview_text(response) if self._settings.log_prompt_previews else None)
            return response
        except Exception:
            span.end(output=None)
            raise


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
    return UniversalLLMClient(settings)
