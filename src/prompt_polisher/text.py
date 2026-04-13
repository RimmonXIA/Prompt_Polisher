from __future__ import annotations

import re


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def preview_text(text: str, max_len: int = 200) -> str:
    t = text.replace("\n", "\\n")
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"


def sanitize_user_input(text: str) -> str:
    """Basic XML tag escaping for common sandbox boundaries to prevent escape."""
    escaped = text
    for tag in ("user_context", "system", "task_context", "draft"):
        escaped = re.sub(rf"<{tag}[^>]*>", rf"&lt;{tag}&gt;", escaped, flags=re.IGNORECASE)
        escaped = re.sub(rf"</{tag}\s*>", rf"&lt;/{tag}&gt;", escaped, flags=re.IGNORECASE)
    return escaped


_INJECTION_PATTERNS = (
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(the\s+)?(above|system)",
    r"you\s+are\s+now\s+(DAN|evil)",
    r"system\s+override",
    r"bypass\s+(the\s+)?rules",
)


def looks_like_injection(user_text: str) -> bool:
    lower = user_text.lower()
    return any(re.search(p, lower) for p in _INJECTION_PATTERNS)
