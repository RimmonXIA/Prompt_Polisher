from __future__ import annotations

import json
import re
from typing import Any, cast


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    raw = strip_code_fence(text)
    parsed: object = json.loads(raw)
    if not isinstance(parsed, dict):
        msg = "expected JSON object"
        raise ValueError(msg)
    return cast(dict[str, Any], parsed)


def preview_text(text: str, max_len: int = 200) -> str:
    t = text.replace("\n", "\\n")
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"


_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(the\s+)?(above|system)",
    r"you\s+are\s+now\s+(DAN|evil)",
)


def looks_like_injection(user_text: str) -> bool:
    lower = user_text.lower()
    return any(re.search(p, lower) for p in _INJECTION_PATTERNS)
