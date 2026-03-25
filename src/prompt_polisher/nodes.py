from __future__ import annotations

import json
import logging
from typing import Any

from prompt_polisher.config import Settings
from prompt_polisher.llm import LLMClient
from prompt_polisher.prompts_bundle import prompt_bundle
from prompt_polisher.state import GraphState, OutputRoute
from prompt_polisher.text import looks_like_injection, parse_json_object, preview_text

logger = logging.getLogger(__name__)


def _system_user(system: str, user: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def node_radar(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    raw = state["raw_prompt"]
    heuristic_injection = looks_like_injection(raw)
    bundle = prompt_bundle(settings)
    system = bundle.radar_system(settings.author_trust_mode)
    user = bundle.radar_user(raw, heuristic_injection)
    if settings.log_prompt_previews:
        logger.info("radar input preview: %s", preview_text(user))
    text = llm.chat(_system_user(system, user))
    try:
        data = parse_json_object(text)
    except (json.JSONDecodeError, ValueError):
        data = {
            "negations_flipped": raw,
            "threats": ["json_parse_error"],
            "alignment_risk": "medium",
            "summary": preview_text(text, 400),
        }
    if heuristic_injection:
        threats = list(data.get("threats") or [])
        if "possible_prompt_injection" not in threats:
            threats.append("possible_prompt_injection")
        data["threats"] = threats
    return {"radar_analysis": data}


def node_routing(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    radar = state.get("radar_analysis") or {}
    bundle = prompt_bundle(settings)
    system = bundle.routing_system(settings.author_trust_mode)
    radar_json = json.dumps(radar, ensure_ascii=False)
    user = bundle.routing_user(radar_json, state["raw_prompt"])
    if settings.log_prompt_previews:
        logger.info("routing input preview: %s", preview_text(user))
    text = llm.chat(_system_user(system, user))
    try:
        data = parse_json_object(text)
    except (json.JSONDecodeError, ValueError):
        data = {
            "complexity": "medium",
            "multi_node_recommended": True,
            "anchor_persona": "careful expert assistant",
            "rationale": preview_text(text, 400),
        }
    return {"routing_decision": data}


def node_compile(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    radar = state.get("radar_analysis") or {}
    routing = state.get("routing_decision") or {}
    critic_fb = state.get("critic_feedback") or ""
    bundle = prompt_bundle(settings)
    system = bundle.compile_system(settings.author_trust_mode)
    payload = {
        "radar": radar,
        "routing": routing,
        "critic_feedback": critic_fb,
        "raw_prompt": state["raw_prompt"],
    }
    user = f"Compile from:\n{json.dumps(payload, ensure_ascii=False)}"
    if settings.log_prompt_previews:
        logger.info("compile input preview: %s", preview_text(user))
    text = llm.chat(_system_user(system, user))
    try:
        data = parse_json_object(text)
        draft = str(data.get("draft") or "").strip()
    except (json.JSONDecodeError, TypeError, ValueError):
        draft = text.strip()
    if not draft:
        draft = state["raw_prompt"]
    return {"draft": draft}


def _rule_check_draft(draft: str) -> tuple[bool, str]:
    if len(draft.strip()) < 20:
        return False, "draft_too_short"
    lower = draft.lower()
    if "<user_context>" in lower and "</user_context>" not in lower:
        return False, "unclosed_user_context"
    return True, ""


def node_critic(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    draft = state.get("draft") or ""
    iterations = int(state.get("critic_iterations") or 0)

    ok, reason = _rule_check_draft(draft)
    if not ok:
        return {
            "critic_passed": False,
            "critic_feedback": f"rule_fail:{reason}",
            "critic_iterations": iterations + 1,
        }

    bundle = prompt_bundle(settings)
    system = bundle.critic_system(settings.author_trust_mode)
    user = bundle.critic_user(draft, state["raw_prompt"])
    if settings.log_prompt_previews:
        logger.info("critic input preview: %s", preview_text(user))
    text = llm.chat(_system_user(system, user))
    try:
        data = parse_json_object(text)
        passed = bool(data.get("pass"))
        feedback = str(data.get("feedback") or "")
    except (json.JSONDecodeError, ValueError):
        passed = False
        feedback = "critic_json_parse_error"

    return {
        "critic_passed": passed,
        "critic_feedback": feedback,
        "critic_iterations": iterations + 1,
    }


def _pick_route(routing: dict[str, object]) -> OutputRoute:
    if bool(routing.get("multi_node_recommended")):
        return "template"
    complexity = str(routing.get("complexity") or "medium").lower()
    if complexity == "high":
        return "dspy"
    return "instance"


def node_router(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    routing = state.get("routing_decision") or {}
    route = _pick_route(routing)
    draft = state.get("draft") or ""
    iterations = int(state.get("critic_iterations") or 0)
    halted = (not bool(state.get("critic_passed"))) and iterations >= settings.max_critic_iterations

    bundle = prompt_bundle(settings)
    system = bundle.router_system(settings.author_trust_mode)
    user = json.dumps(
        {
            "output_route": route,
            "draft": draft,
            "routing": routing,
            "radar": state.get("radar_analysis") or {},
            "raw_prompt": state["raw_prompt"],
            "critic_passed": state.get("critic_passed"),
            "critic_halted_max": halted,
        },
        ensure_ascii=False,
    )
    if settings.log_prompt_previews:
        logger.info("router input preview: %s", preview_text(user))
    text = llm.chat(_system_user(system, user))
    try:
        data = parse_json_object(text)
    except (json.JSONDecodeError, ValueError):
        data = {
            "final_prompt": draft,
            "workflow_blueprint": bundle.router_fallback_workflow(route),
            "dspy_sketch": bundle.router_fallback_dspy(),
        }

    return {
        "output_route": route,
        "final_prompt": str(data.get("final_prompt") or draft),
        "workflow_blueprint": str(data.get("workflow_blueprint") or ""),
        "dspy_sketch": str(data.get("dspy_sketch") or ""),
        "critic_halted_max": halted,
    }
