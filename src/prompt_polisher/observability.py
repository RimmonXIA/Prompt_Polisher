from __future__ import annotations

import logging
from typing import Any, Protocol

from prompt_polisher.config import Settings

logger = logging.getLogger(__name__)


class TraceSpan(Protocol):
    def end(self, *, output: str | None = None) -> None: ...


class NullSpan:
    def end(self, *, output: str | None = None) -> None:
        return None


def _langfuse_generation_span(client: Any, *, name: str, input_preview: str) -> TraceSpan:
    gen: Any
    try:
        gen = client.start_generation(name=name, input=input_preview or "")
    except AttributeError:
        trace = client.trace(name=name)
        gen = trace.generation(name=name, input=input_preview or "")

    class _GenSpan:
        def end(self, *, output: str | None = None) -> None:
            try:
                if output is not None:
                    update = getattr(gen, "update", None)
                    if callable(update):
                        update(output=output)
                end_fn = getattr(gen, "end", None)
                if callable(end_fn):
                    end_fn()
            except Exception as exc:  # pragma: no cover - best-effort tracing
                logger.debug("langfuse generation end failed: %s", exc)
            try:
                client.flush()
            except Exception as exc:  # pragma: no cover
                logger.debug("langfuse flush failed: %s", exc)

    return _GenSpan()


def start_llm_span(
    settings: Settings,
    *,
    name: str,
    input_preview: str | None,
) -> TraceSpan:
    if not settings.langfuse_tracing:
        return NullSpan()
    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning("LANGFUSE_TRACING enabled but langfuse is not installed")
        return NullSpan()

    public = settings.langfuse_public_key
    secret = settings.langfuse_secret_key
    if not public or secret is None:
        logger.warning("Langfuse tracing enabled but keys are missing")
        return NullSpan()

    base = settings.langfuse_base_url
    kwargs: dict[str, Any] = {
        "public_key": public,
        "secret_key": secret.get_secret_value(),
    }
    if base:
        kwargs["host"] = base.rstrip("/")

    try:
        client = Langfuse(**kwargs)
        return _langfuse_generation_span(client, name=name, input_preview=input_preview or "")
    except Exception as exc:  # pragma: no cover
        logger.warning("Langfuse client init failed: %s", exc)
        return NullSpan()
