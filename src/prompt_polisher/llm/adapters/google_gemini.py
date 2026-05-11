from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from prompt_polisher.llm.errors import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from prompt_polisher.llm.protocol import ChatMessage


def _to_gemini_payload(messages: Sequence[ChatMessage]) -> tuple[str | None, list[dict[str, Any]]]:
    system_chunks: list[str] = []
    converted: list[dict[str, Any]] = []
    for msg in messages:
        role = str(msg.get("role", "")).strip().lower()
        content = str(msg.get("content", ""))
        if role == "system":
            if content:
                system_chunks.append(content)
            continue
        gemini_role = "model" if role == "assistant" else "user"
        converted.append({"role": gemini_role, "parts": [{"text": content}]})
    if not converted:
        converted = [{"role": "user", "parts": [{"text": ""}]}]
    system_instruction = "\n\n".join(system_chunks) if system_chunks else None
    return system_instruction, converted


class GeminiAdapter:
    def __init__(self, *, api_key: str, default_model: str) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - only when dependency missing
            msg = "google-genai package is required for LLM_PROVIDER=gemini/google"
            raise RuntimeError(msg) from exc

        self._genai = genai
        self._default_model = default_model
        self._sync_client = genai.Client(api_key=api_key)
        self._async_client = genai.Client(api_key=api_key).aio

    @staticmethod
    def _extract_text(response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str):
            return text

        candidates = getattr(response, "candidates", None)
        if not isinstance(candidates, list) or not candidates:
            raise ProviderResponseError("Gemini response has no candidates")
        parts = getattr(getattr(candidates[0], "content", None), "parts", None)
        if not isinstance(parts, list):
            raise ProviderResponseError("Gemini response has no parts")
        out: list[str] = []
        for part in parts:
            p_text = getattr(part, "text", None)
            if isinstance(p_text, str):
                out.append(p_text)
        return "".join(out)

    def _map_error(self, exc: Exception) -> Exception:
        name = exc.__class__.__name__
        lowered = name.lower()
        if "timeout" in lowered:
            return ProviderTimeoutError(str(exc))
        if "connection" in lowered or "transport" in lowered:
            return ProviderConnectionError(str(exc))
        return ProviderResponseError(str(exc))

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str:
        request_model = model or self._default_model
        system_instruction, converted = _to_gemini_payload(messages)
        try:
            config = self._genai.types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction,
            )
            response = self._sync_client.models.generate_content(
                model=request_model,
                contents=converted,
                config=config,
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
        system_instruction, converted = _to_gemini_payload(messages)
        try:
            config = self._genai.types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction,
            )
            coro = self._async_client.models.generate_content(
                model=request_model,
                contents=converted,
                config=config,
            )
            response = await asyncio.wait_for(coro, timeout=timeout)
            return self._extract_text(response)
        except TimeoutError as exc:
            raise ProviderTimeoutError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - covered by unit tests
            raise self._map_error(exc) from exc
