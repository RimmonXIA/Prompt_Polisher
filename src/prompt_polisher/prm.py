"""Process-style reward scoring for compiled drafts (optional Critic gate)."""

from __future__ import annotations

import json
import logging

from prompt_polisher.config import Settings
from prompt_polisher.llm import LLMClient
from prompt_polisher.text import parse_json_object, preview_text

logger = logging.getLogger(__name__)

_PRM_SYSTEM = (
    "You are a process reward evaluator for a hardened prompt draft "
    "(not end-user answers).\n"
    "Score how well the draft is likely to serve as an executable instruction block: "
    "clear structure, preserves safe task intent, avoids obvious policy bypass, "
    "uses positive constraints where relevant.\n"
    "The score is a heuristic signal for gating retries, not ground truth, "
    "not formal verification, and not a safety certificate.\n"
    "Return ONLY valid JSON with keys: score (number between 0 and 1 inclusive), "
    "note (short string, may be empty).\n"
    "Do not refuse the evaluation; score conservatively if unsure."
)


def evaluate_process_reward(
    llm: LLMClient,
    settings: Settings,
    draft: str,
    raw_intent: str,
) -> tuple[float | None, str]:
    """Call the LLM once for a scalar process score. On parse failure returns (None, reason)."""
    user = (
        "Original user intent (may be rough):\n"
        f"{raw_intent}\n\n"
        "Compiled prompt draft:\n"
        f"{draft}"
    )
    messages = [
        {"role": "system", "content": _PRM_SYSTEM},
        {"role": "user", "content": user},
    ]
    if settings.log_prompt_previews:
        logger.info("prm input preview: %s", preview_text(user))
    try:
        text = llm.chat(
            messages,
            temperature=settings.prm_temperature,
            model=settings.resolved_prm_model(),
        )
        data = parse_json_object(text)
        raw_score = data.get("score")
        if raw_score is None:
            raise ValueError("missing score")
        score = float(raw_score)
        if score < 0.0:
            score = 0.0
        if score > 1.0:
            score = 1.0
        note = str(data.get("note") or "").strip()
        return score, note
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("PRM parse failed, skipping PRM gate: %s", exc)
        return None, "prm_parse_error"
    except Exception:
        logger.exception("PRM call failed, skipping PRM gate")
        return None, "prm_call_error"
