"""Process-style reward scoring for compiled drafts (optional Critic gate)."""

from __future__ import annotations

import json
import logging

from prompt_polisher.config import Settings
from prompt_polisher.llm import LLMClient
from prompt_polisher.text import parse_json_object, preview_text

logger = logging.getLogger(__name__)

_PRM_SYSTEM = (
    "You are a strict process reward evaluator for a hardened prompt draft.\n"
    "Step 1: Verify the draft's structural safety (does it have isolated XML boundaries?).\n"
    "Step 2: Verify the adherence to the original intent without policy bypass.\n"
    "Step 3: Check for positive constraints vs negative phrasing.\n"
    "Finally, assign a heuristic scalar score based on the steps.\n"
    "Return ONLY valid JSON with keys: verification_steps (list of strings), "
    "score (number between 0 and 1 inclusive), note (short string).\n"
    "Do not refuse; score conservatively."
)


def evaluate_process_reward(
    llm: LLMClient,
    settings: Settings,
    draft: str,
    raw_intent: str,
) -> tuple[float | None, str]:
    """Call the LLM once for a scalar process score. On parse failure returns (None, reason)."""
    if settings.external_prm_endpoint:
        try:
            import httpx

            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    settings.external_prm_endpoint, json={"draft": draft, "intent": raw_intent}
                )
                res.raise_for_status()
                data = res.json()
                return float(data["score"]), str(data.get("note", "external_prm_success"))
        except Exception as exc:
            logger.warning("External PRM endpoint failed: %s, falling back to LLM", exc)

    user = f"Original user intent (may be rough):\n{raw_intent}\n\nCompiled prompt draft:\n{draft}"
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
