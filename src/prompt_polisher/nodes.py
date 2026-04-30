from __future__ import annotations

import json
import logging
from typing import Any, TypeVar, cast

from pydantic import BaseModel

from prompt_polisher.config import Settings
from prompt_polisher.llm import LLMClient
from prompt_polisher.prm import evaluate_process_reward
from prompt_polisher.prompts_bundle import prompt_bundle
from prompt_polisher.state import (
    CompileDraft,
    CriticFeedback,
    GraphState,
    OptimizationTarget,
    OutputRoute,
    RouterDeliverable,
    RoutingDecision,
    SnifferAnalysis,
)
from prompt_polisher.text import looks_like_injection, preview_text, strip_code_fence

logger = logging.getLogger(__name__)

_M = TypeVar("_M", bound=BaseModel)


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except Exception:
        return default


def _coerce_optimization_target(
    v: object,
    default: OptimizationTarget = "general",
) -> OptimizationTarget:
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {
            "concise",
            "strict_format",
            "reasoning",
            "creative",
            "agentic",
            "small_model",
            "general",
        }:
            return cast(OptimizationTarget, s)
    return default


def _compile_strategy_block(prompt_type: str, optimization_target: str) -> str:
    base = (
        f"PromptType={prompt_type}\n"
        f"OptimizationTarget={optimization_target}\n"
        "Apply the following strategy constraints while preserving user intent."
    )
    if prompt_type == "json_extraction_prompt":
        return (
            f"{base}\n"
            "- JSON-only output contract: forbid prose outside JSON.\n"
            "- Require explicit key schema and missing/null policy.\n"
            "- Enforce deterministic field naming and type hints."
        )
    if prompt_type == "coding_prompt":
        return (
            f"{base}\n"
            "- Prefer minimal-change implementation guidance over broad rewrites.\n"
            "- Require verification steps (tests, lint, typecheck, or runtime checks).\n"
            "- Preserve constraints and acceptance criteria before style concerns."
        )
    if prompt_type == "agent_tool_prompt":
        return (
            f"{base}\n"
            "- Define tool boundaries: what tools can and cannot be used.\n"
            "- Require explicit stop conditions to avoid loops.\n"
            "- Include error-handling and recovery expectations for failed tool calls."
        )
    return (
        f"{base}\n"
        "- Use general compilation strategy with clear sections and executable constraints."
    )


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


async def node_intent_sniffer(
    state: GraphState, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    if state.get("fatal_error"):
        return {}
    raw = state["raw_prompt"]
    heuristic_injection = looks_like_injection(raw)
    bundle = prompt_bundle(settings)
    system = bundle.sniffer_system(settings.author_trust_mode)
    user = bundle.sniffer_user(raw, heuristic_injection)
    if settings.log_prompt_previews:
        logger.info("sniffer input preview: %s", preview_text(user))
    try:
        text = await llm.achat(_system_user(system, user, SnifferAnalysis))
        parsed: SnifferAnalysis | None = _parse_pydantic(SnifferAnalysis, text)
    except Exception as e:
        logger.error("LLM failure in node_intent_sniffer: %s", e)
        return {"fatal_error": True, "fatal_error_reason": str(e)}

    if parsed is None:
        parsed = SnifferAnalysis(
            negations_flipped=raw,
            threats=["json_parse_error"],
            alignment_risk="medium",
            summary=preview_text(text, 400),
            linguistic_entropy="low" if len(raw.split()) < 10 else "medium",
        )

    if heuristic_injection:
        if "possible_prompt_injection" not in parsed.threats:
            parsed.threats.append("possible_prompt_injection")

    return {"intent_sniffer_analysis": parsed.model_dump()}


async def node_compute_aware_router(
    state: GraphState, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    if state.get("fatal_error"):
        return {}
    requested_target: OptimizationTarget = _coerce_optimization_target(
        state.get("optimization_target"),
        settings.optimization_target,
    )
    sniffer = state.get("intent_sniffer_analysis") or {}
    bundle = prompt_bundle(settings)
    system = bundle.routing_system(settings.author_trust_mode)
    sniffer_json = json.dumps(sniffer, ensure_ascii=False)
    user = (
        f"{bundle.routing_user(sniffer_json, state['raw_prompt'])}\n\n"
        f"Requested optimization target: {requested_target}"
    )
    if settings.log_prompt_previews:
        logger.info("routing input preview: %s", preview_text(user))
    try:
        text = await llm.achat(_system_user(system, user, RoutingDecision))
        parsed: RoutingDecision | None = _parse_pydantic(RoutingDecision, text)
    except Exception as e:
        logger.error("LLM failure in node_compute_aware_router: %s", e)
        return {"fatal_error": True, "fatal_error_reason": str(e)}

    if parsed is None:
        parsed = RoutingDecision(
            complexity="medium",
            multi_node_recommended=True,
            anchor_persona="careful expert assistant",
            audience_anchor="general public",
            rationale=preview_text(text, 400),
            prompt_type="unknown",
            prompt_type_confidence=0.0,
            optimization_target=requested_target,
        )
    else:
        # Explicit user-selected target should override model omission/default drift.
        parsed.optimization_target = requested_target
    return {
        "compute_aware_routing_decision": parsed.model_dump(),
        "prompt_type": parsed.prompt_type,
        "prompt_type_confidence": parsed.prompt_type_confidence,
        "optimization_target": parsed.optimization_target,
    }


async def node_structured_compiler(
    state: GraphState, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    if state.get("fatal_error"):
        return {}
    sniffer = state.get("intent_sniffer_analysis") or {}
    routing = state.get("compute_aware_routing_decision") or {}
    critic_fb = state.get("red_team_critic_feedback") or ""
    prompt_type = str(state.get("prompt_type") or routing.get("prompt_type") or "unknown")
    optimization_target = _coerce_optimization_target(
        state.get("optimization_target") or routing.get("optimization_target"),
        settings.optimization_target,
    )
    bundle = prompt_bundle(settings)
    system = (
        f"{bundle.compile_system(settings.author_trust_mode)}\n\n"
        "[TYPE-SPECIFIC COMPILATION STRATEGY]\n"
        f"{_compile_strategy_block(prompt_type, optimization_target)}"
    )
    payload = {
        "sniffer": sniffer,
        "routing": routing,
        "red_team_critic_feedback": critic_fb,
        "raw_prompt": state["raw_prompt"],
        "prompt_type": prompt_type,
        "optimization_target": optimization_target,
        "strategy_hints": _compile_strategy_block(prompt_type, optimization_target),
    }
    user = f"Compile from:\n{json.dumps(payload, ensure_ascii=False)}"
    if settings.log_prompt_previews:
        logger.info("compile input preview: %s", preview_text(user))
    try:
        text = await llm.achat(_system_user(system, user, CompileDraft))
        parsed: CompileDraft | None = _parse_pydantic(CompileDraft, text)
    except Exception as e:
        logger.error("LLM failure in node_structured_compiler: %s", e)
        return {"fatal_error": True, "fatal_error_reason": str(e)}
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

    return {"compiler_draft": draft}


def _rule_check_draft(draft: str) -> tuple[bool, str]:
    if len(draft.strip()) < 20:
        return False, "draft_too_short"
    lower = draft.lower()
    if "<user_context>" in lower and "</user_context>" not in lower:
        return False, "unclosed_user_context"
    return True, ""


async def node_red_team_critic(
    state: GraphState, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    if state.get("fatal_error"):
        return {}
    draft = state.get("compiler_draft") or ""
    iterations = int(state.get("red_team_critic_iterations") or 0)

    ok, reason = _rule_check_draft(draft)
    if not ok:
        return {
            "red_team_critic_passed": False,
            "red_team_critic_feedback": f"rule_fail:{reason}",
            "red_team_critic_iterations": iterations + 1,
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
                    "red_team_critic_passed": False,
                    "red_team_critic_feedback": detail,
                    "red_team_critic_iterations": iterations + 1,
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
        logger.error("LLM failure in node_red_team_critic: %s", e)
        return {"fatal_error": True, "fatal_error_reason": str(e)}
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
        "red_team_critic_passed": passed,
        "red_team_critic_feedback": feedback,
        "red_team_critic_iterations": iterations + 1,
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


async def node_artifact_dispatcher(
    state: GraphState, llm: LLMClient, settings: Settings
) -> dict[str, Any]:
    if state.get("fatal_error"):
        return {}
    routing = state.get("compute_aware_routing_decision") or {}
    route = _pick_route(routing)
    draft = state.get("compiler_draft") or ""
    iterations = int(state.get("red_team_critic_iterations") or 0)
    halted = (not bool(state.get("red_team_critic_passed"))) and (
        iterations >= settings.max_critic_iterations
    )

    bundle = prompt_bundle(settings)
    system = bundle.router_system(settings.author_trust_mode)
    user = json.dumps(
        {
            "output_route": route,
            "compiler_draft": (
                f"[GOLDEN DRAFT - PRIORITIZE] {draft}"
                if state.get("red_team_critic_passed")
                else draft
            ),
            "routing": routing,
            "sniffer": state.get("intent_sniffer_analysis") or {},
            "raw_prompt": state["raw_prompt"],
            "red_team_critic_passed": state.get("red_team_critic_passed"),
            "red_team_critic_halted_max": halted,
        },
        ensure_ascii=False,
    )
    if settings.log_prompt_previews:
        logger.info("router input preview: %s", preview_text(user))
    try:
        text = await llm.achat(_system_user(system, user, RouterDeliverable))
        parsed: RouterDeliverable | None = _parse_pydantic(RouterDeliverable, text)
    except Exception as e:
        logger.error("LLM failure in node_artifact_dispatcher: %s", e)
        return {"fatal_error": True, "fatal_error_reason": str(e)}
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
        "red_team_critic_halted_max": halted,
        "prompt_type": str(routing.get("prompt_type") or "unknown"),
        "prompt_type_confidence": _safe_float(routing.get("prompt_type_confidence"), 0.0),
        "optimization_target": str(
            routing.get("optimization_target")
            or state.get("optimization_target")
            or "general"
        ),
    }
