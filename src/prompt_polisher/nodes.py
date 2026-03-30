from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from prompt_polisher.config import Settings
from prompt_polisher.llm import LLMClient
from prompt_polisher.prm import evaluate_process_reward
from prompt_polisher.prompts_bundle import prompt_bundle
from prompt_polisher.state import (
    CompileResult,
    CriticFeedback,
    GraphState,
    OutputRoute,
    RadarAnalysis,
    RoutingDecision,
)
from prompt_polisher.text import looks_like_injection, preview_text, strip_code_fence

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)


def _system_user(system: str, user: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_pydantic(model_cls: type[_M], text: str) -> _M | None:
    """Parse a JSON string into a Pydantic model, stripping code fences first."""
    raw = strip_code_fence(text)
    try:
        return model_cls.model_validate_json(raw)
    except Exception:
        # Attempt to extract a JSON object even if surrounded by prose
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return model_cls.model_validate_json(raw[start:end])
        except Exception:
            return None


async def node_radar(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    raw = state["raw_prompt"]
    heuristic_injection = looks_like_injection(raw)
    bundle = prompt_bundle(settings)
    system = bundle.radar_system(settings.author_trust_mode)
    user = bundle.radar_user(raw, heuristic_injection)
    if settings.log_prompt_previews:
        logger.info("radar input preview: %s", preview_text(user))
    text = await llm.achat(_system_user(system, user))

    parsed: RadarAnalysis | None = _parse_pydantic(RadarAnalysis, text)
    if parsed is None:
        parsed = RadarAnalysis(
            negations_flipped=raw,
            threats=["json_parse_error"],
            alignment_risk="medium",
            summary=preview_text(text, 400),
        )

    if heuristic_injection:
        if "possible_prompt_injection" not in parsed.threats:
            parsed.threats.append("possible_prompt_injection")

    return {"radar_analysis": parsed.model_dump()}


async def node_routing(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    radar = state.get("radar_analysis") or {}
    bundle = prompt_bundle(settings)
    system = bundle.routing_system(settings.author_trust_mode)
    radar_json = json.dumps(radar, ensure_ascii=False)
    user = bundle.routing_user(radar_json, state["raw_prompt"])
    if settings.log_prompt_previews:
        logger.info("routing input preview: %s", preview_text(user))
    text = await llm.achat(_system_user(system, user))

    parsed: RoutingDecision | None = _parse_pydantic(RoutingDecision, text)
    if parsed is None:
        parsed = RoutingDecision(
            complexity="medium",
            multi_node_recommended=True,
            anchor_persona="careful expert assistant",
            rationale=preview_text(text, 400),
        )
    return {"routing_decision": parsed.model_dump()}


async def node_compile(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
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
    text = await llm.achat(_system_user(system, user))

    parsed: CompileResult | None = _parse_pydantic(CompileResult, text)
    draft = (parsed.draft.strip() if parsed else "") or text.strip() or state["raw_prompt"]
    return {"draft": draft}


def _rule_check_draft(draft: str) -> tuple[bool, str]:
    if len(draft.strip()) < 20:
        return False, "draft_too_short"
    lower = draft.lower()
    if "<user_context>" in lower and "</user_context>" not in lower:
        return False, "unclosed_user_context"
    return True, ""


async def node_critic(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    draft = state.get("draft") or ""
    iterations = int(state.get("critic_iterations") or 0)

    ok, reason = _rule_check_draft(draft)
    if not ok:
        return {
            "critic_passed": False,
            "critic_feedback": f"rule_fail:{reason}",
            "critic_iterations": iterations + 1,
        }

    prm_score_val: float | None = None
    if settings.critic_use_prm:
        score, prm_note = evaluate_process_reward(llm, settings, draft, state["raw_prompt"])
        if score is not None:
            prm_score_val = score
            if score < settings.prm_min_score:
                detail = f"prm_low_score:{score:.3f}"
                if prm_note:
                    detail = f"{detail} ({prm_note})"
                return {
                    "critic_passed": False,
                    "critic_feedback": detail,
                    "critic_iterations": iterations + 1,
                    "prm_score": score,
                }

    bundle = prompt_bundle(settings)
    system = bundle.critic_system(settings.author_trust_mode)
    user = bundle.critic_user(draft, state["raw_prompt"])
    if settings.log_prompt_previews:
        logger.info("critic input preview: %s", preview_text(user))
    text = await llm.achat(_system_user(system, user))

    parsed: CriticFeedback | None = _parse_pydantic(CriticFeedback, text)
    if parsed is None:
        logger.warning("critic returned unparseable output, preview=%s", preview_text(text, 400))
        passed = False
        feedback = "critic_json_parse_error"
        steps: list[str] = []
    else:
        passed = parsed.passed
        feedback = parsed.feedback
        steps = parsed.verification_steps

    out: dict[str, Any] = {
        "critic_passed": passed,
        "critic_feedback": feedback,
        "critic_iterations": iterations + 1,
    }
    if steps:
        out["_critic_steps"] = steps  # stored for observability; not in official state schema
    if prm_score_val is not None:
        out["prm_score"] = prm_score_val
    return out


def _pick_route(routing: dict[str, object]) -> OutputRoute:
    if bool(routing.get("multi_node_recommended")):
        return "template"
    complexity = str(routing.get("complexity") or "medium").lower()
    if complexity == "high":
        return "dspy"
    return "instance"


async def node_router(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
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
    text = await llm.achat(_system_user(system, user))

    raw = strip_code_fence(text)
    try:
        data: dict[str, Any] = json.loads(raw)
    except Exception:
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
