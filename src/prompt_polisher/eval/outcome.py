from __future__ import annotations

import json
from dataclasses import dataclass

from prompt_polisher.eval.schema import GoldSpec


@dataclass(frozen=True)
class OutcomeResult:
    score: float
    detail: str


def score_outcome(raw_text: str, gold: GoldSpec) -> OutcomeResult:
    """Tier B: map executor output to [0,1] given gold spec."""
    text = raw_text.strip()
    if gold.type == "none":
        return OutcomeResult(score=1.0, detail="gold type none (skipped)")
    if gold.type == "exact_match":
        want = gold.value.strip()
        ok = text == want
        return OutcomeResult(1.0 if ok else 0.0, "exact_match ok" if ok else "exact_match mismatch")
    if gold.type == "contains_all":
        missing = [s for s in gold.values if s not in text]
        if not missing:
            return OutcomeResult(1.0, "contains_all ok")
        return OutcomeResult(0.0, f"missing substrings: {missing!r}")
    if gold.type == "json_keys":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            return OutcomeResult(0.0, f"invalid json: {exc}")
        if not isinstance(obj, dict):
            return OutcomeResult(0.0, "json root not an object")
        for key in gold.keys:
            if key not in obj:
                return OutcomeResult(0.0, f"missing key {key!r}")
        for key, want in gold.key_values.items():
            if str(obj.get(key)) != str(want):
                return OutcomeResult(
                    0.0,
                    f"key {key!r} want {want!r} got {obj.get(key)!r}",
                )
        return OutcomeResult(1.0, "json_keys ok")
    return OutcomeResult(0.0, f"unknown gold type {gold.type!r}")
