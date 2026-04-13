from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from prompt_polisher.config import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stderr)
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"),
        )
    root.addHandler(handler)

    # Silence LiteLLM's verbose internal loggers.
    # LiteLLM emits INFO-level "completion() model=…; provider=…" lines via its
    # own named loggers AND prints "Provider List: …" via print() calls.
    # Both must be suppressed so they don't pollute the rich UX on stderr.
    for _noisy_logger in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy"):
        logging.getLogger(_noisy_logger).setLevel(logging.WARNING)

    try:
        import litellm

        litellm.suppress_debug_info = True
        litellm.set_verbose = False  # type: ignore[attr-defined]
    except Exception:
        pass
