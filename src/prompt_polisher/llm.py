from __future__ import annotations

import logging
import os
from typing import Any, Protocol, cast, runtime_checkable

import litellm
from litellm import acompletion, completion
from openai import APIConnectionError
from tenacity import (
    AsyncRetrying,
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from prompt_polisher.config import Settings
from prompt_polisher.observability import start_llm_span
from prompt_polisher.text import preview_text

logger = logging.getLogger(__name__)

# Extra attempts after the SDK exhausts its own retries.
# We set the SDK's internal max_retries to 0 so we don't multiply these!


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
    """Normalize 'socks://' to 'socks5://' in environment variables for httpx compatibility."""
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
            new_val = val.replace("socks://", "socks5://", 1)
            logger.debug("Normalizing proxy %s: %s -> %s", env_var, val, new_val)
            os.environ[env_var] = new_val


class UniversalLLMClient:
    def __init__(self, settings: Settings) -> None:
        _normalize_socks_proxy()
        self._settings = settings
        self._api_key = settings.resolved_api_key()
        self._base_url = settings.resolved_base_url()

    def _resolve_model_name(self, model: str | None) -> str:
        resolved = model if model else self._settings.resolved_model()
        provider = self._settings.llm_provider
        if provider and "/" not in resolved:
            # LiteLLM needs provider prefixes for most non-standard models
            if provider == "openai" and resolved.startswith("gpt-"):
                return resolved
            return f"{provider}/{resolved}"
        return resolved

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        temp = self._settings.llm_temperature if temperature is None else temperature
        resolved_model = self._resolve_model_name(model)
        preview = None
        if self._settings.log_prompt_previews:
            preview = preview_text(str(messages))

        span = start_llm_span(self._settings, name="llm.chat", input_preview=preview)
        try:
            for attempt in Retrying(
                retry=retry_if_exception_type(
                    (APIConnectionError, litellm.exceptions.APIConnectionError)
                ),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                stop=stop_after_attempt(5),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            ):
                with attempt:
                    resp = completion(
                        model=resolved_model,
                        messages=cast(Any, messages),
                        temperature=temp,
                        api_key=self._api_key,
                        base_url=self._base_url,
                        timeout=180.0,
                    )
            content = resp.choices[0].message.content or ""
            span.end(
                output=preview_text(content) if self._settings.log_prompt_previews else None,
            )
            return content
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
        resolved_model = self._resolve_model_name(model)
        preview = None
        if self._settings.log_prompt_previews:
            preview = preview_text(str(messages))

        span = start_llm_span(self._settings, name="llm.achat", input_preview=preview)
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (APIConnectionError, litellm.exceptions.APIConnectionError)
                ),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                stop=stop_after_attempt(5),
                before_sleep=before_sleep_log(logger, logging.WARNING),
                reraise=True,
            ):
                with attempt:
                    resp = await acompletion(
                        model=resolved_model,
                        messages=cast(Any, messages),
                        temperature=temp,
                        api_key=self._api_key,
                        base_url=self._base_url,
                        timeout=180.0,
                    )
            content = resp.choices[0].message.content or ""
            span.end(
                output=preview_text(content) if self._settings.log_prompt_previews else None,
            )
            return content
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
