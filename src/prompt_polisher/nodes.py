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
    CompileDraft,
    CriticFeedback,
    GraphState,
    OutputRoute,
    RadarAnalysis,
    RouterDeliverable,
    RoutingDecision,
)
from prompt_polisher.text import looks_like_injection, preview_text, strip_code_fence

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)


def _system_user(
    system: str, user: str, schema_cls: type[BaseModel] | None = None
) -> list[dict[str, str]]:
    if schema_cls is not None:
        schema_json = json.dumps(schema_cls.model_json_schema(), ensure_ascii=False)
        system = (
            f"{system}\n\nYou MUST return ONLY valid JSON matching this schema:\n"
            f"```json\n{schema_json}\n```"
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_pydantic(model_cls: type[_M], text: str) -> _M | None:
    """Parse a JSON string into a Pydantic model, stripping code fences first."""
    raw = strip_code_fence(text).strip()
    try:
        return model_cls.model_validate_json(raw)
    except Exception:
        # Find all potential JSON objects in the text.
        # We look for the first '{' and the last matching '}' to be truly greedy.
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end != -1 and end > start:
                return model_cls.model_validate_json(raw[start:end])
        except Exception:
            pass
        return None


async def node_radar(state: GraphState, llm: LLMClient, settings: Settings) -> dict[str, Any]:
    raw = state["raw_prompt"]
    heuristic_injection = looks_like_injection(raw)
    bundle = prompt_bundle(settings)
    system = bundle.radar_system(settings.author_trust_mode)
    user = bundle.radar_user(raw, heuristic_injection)
    if settings.log_prompt_previews:
        logger.info("radar input preview: %s", preview_text(user))
    try:
        text = await llm.achat(_system_user(system, user, RadarAnalysis))
        parsed: RadarAnalysis | None = _parse_pydantic(RadarAnalysis, text)
    except Exception as e:
        logger.error("LLM failure in node_radar: %s", e)
        parsed = None
        text = "llm_error"

    if parsed is None:
        parsed = RadarAnalysis(
            negations_flipped=raw,
            threats=["json_parse_error"],
            alignment_risk="medium",
            summary=preview_text(text, 400),
            linguistic_entropy="low" if len(raw.split()) < 10 else "medium",
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
    try:
        text = await llm.achat(_system_user(system, user, RoutingDecision))
        parsed: RoutingDecision | None = _parse_pydantic(RoutingDecision, text)
    except Exception as e:
        logger.error("LLM failure in node_routing: %s", e)
        parsed = None
        text = "llm_error"

    if parsed is None:
        parsed = RoutingDecision(
            complexity="medium",
            multi_node_recommended=True,
            anchor_persona="careful expert assistant",
            audience_anchor="general public",
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
    try:
        text = await llm.achat(_system_user(system, user, CompileDraft))
        parsed: CompileDraft | None = _parse_pydantic(CompileDraft, text)
    except Exception as e:
        logger.error("LLM failure in node_compile: %s", e)
        return {"draft": state["raw_prompt"]}
    if parsed and parsed.draft.strip():
        draft = parsed.draft.strip()
    else:
        # Fallback for unparseable or empty draft field
        draft = text.strip()
        # First, try a direct regex search for a "draft" key if it was a JSON fail.
        import re

        match = re.search(r'"draft"\s*:\s*"(.*?)"', text, re.DOTALL)
        if match:
            draft = match.group(1).encode().decode("unicode_escape", errors="ignore").strip()

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
    try:
        text = await llm.achat(_system_user(system, user, CriticFeedback))
        parsed: CriticFeedback | None = _parse_pydantic(CriticFeedback, text)
    except Exception as e:
        logger.error("LLM failure in node_critic: %s", e)
        return {
            "critic_passed": False,
            "critic_feedback": "llm_connection_error_halting",
            "critic_iterations": settings.max_critic_iterations,  # Force halt
        }
    if parsed is None:
        logger.warning(
            "Critic node returned unparseable JSON or prose. Raw text preview: %s",
            preview_text(text, 500),
        )
        passed = False
        feedback = "critic_json_parse_error"
        steps: list[str] = []
    else:
        passed = parsed.passed
        feedback = parsed.feedback or ("" if passed else "failure_reason_unspecified")
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
            "draft": (
                f"[GOLDEN DRAFT - PRIORITIZE] {draft}" if state.get("critic_passed") else draft
            ),
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
    try:
        text = await llm.achat(_system_user(system, user, RouterDeliverable))
        parsed: RouterDeliverable | None = _parse_pydantic(RouterDeliverable, text)
    except Exception as e:
        logger.error("LLM failure in node_router: %s", e)
        parsed = None
    if not parsed:
        parsed = RouterDeliverable(
            final_prompt=draft,
            workflow_blueprint=bundle.router_fallback_workflow(route),
            dspy_sketch=bundle.router_fallback_dspy(),
        )

    return {
        "output_route": route,
        "final_prompt": parsed.final_prompt or draft,
        "workflow_blueprint": parsed.workflow_blueprint,
        "dspy_sketch": parsed.dspy_sketch,
        "critic_halted_max": halted,
    }
