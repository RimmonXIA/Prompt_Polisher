from __future__ import annotations

from typing import Any

from prompt_polisher.config import Settings
from prompt_polisher.prompts_bundle import prompt_bundle
from prompt_polisher.state import GraphState
from prompt_polisher.text import looks_like_injection


def _threat_tokens(state: GraphState) -> list[str]:
    analysis = dict(state.get("intent_sniffer_analysis") or {})
    raw = analysis.get("threats")
    if not isinstance(raw, list):
        return []
    return [str(t).strip() for t in raw if str(t).strip()]


def should_abort_after_intent_sniffer(state: GraphState, settings: Settings) -> tuple[bool, str]:
    """Return whether to skip routing/compile/critic/router after Intent Sniffer has run."""
    raw = str(state.get("raw_prompt") or "")

    if settings.abort_on_heuristic_injection and looks_like_injection(raw):
        return True, "heuristic_prompt_injection"

    analysis = dict(state.get("intent_sniffer_analysis") or {})
    alignment = str(analysis.get("alignment_risk") or "medium").strip().lower()
    threat_list = _threat_tokens(state)
    threat_lower = [t.lower() for t in threat_list]

    if "possible_prompt_injection" in threat_lower:
        return True, "sniffer_possible_prompt_injection"

    if settings.abort_on_sniffer_high and alignment == "high":
        return True, "sniffer_alignment_risk_high"

    if not settings.author_trust_mode and alignment == "high" and threat_list:
        return True, "sniffer_high_with_threats_untrusted"

    return False, ""


def _abort_detail(reason: str, state: GraphState) -> str:
    analysis = dict(state.get("intent_sniffer_analysis") or {})
    summary = analysis.get("summary")
    if isinstance(summary, str) and summary.strip():
        return f"{reason}: {summary.strip()}"
    return reason


def node_safety_abort_gate(state: GraphState, settings: Settings) -> dict[str, Any]:
    """Terminal node: deterministic message, no LLM. Expects should_abort to be true."""
    abort, reason = should_abort_after_intent_sniffer(state, settings)
    if not abort:
        reason = "graph_miswired_early_abort_without_trigger"
    detail = _abort_detail(reason, state)
    bundle = prompt_bundle(settings)
    return {
        "compilation_aborted": True,
        "abort_reason": reason,
        "abort_detail": detail,
        "final_prompt": bundle.gate_abort_user_message(reason),
        "workflow_blueprint": bundle.gate_abort_workflow_blueprint(),
        "dspy_sketch": "",
        "compiler_draft": "",
        "red_team_critic_passed": False,
        "red_team_critic_iterations": 0,
        "red_team_critic_feedback": "",
        "red_team_critic_halted_max": False,
        "output_route": "instance",
    }
