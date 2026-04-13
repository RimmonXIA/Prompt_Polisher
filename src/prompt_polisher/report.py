from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from prompt_polisher.config import Settings
from prompt_polisher.state import GraphState


@dataclass(frozen=True)
class _ReportParts:
    raw: str
    final: str
    sniffer: dict[str, object]
    routing: dict[str, object]
    route: object
    blueprint: str
    dspy: str
    draft: str
    red_team_critic_passed: object
    critic_iters: object
    critic_fb: str
    prm_score: object
    halted: object
    compilation_aborted: bool
    abort_reason: str
    abort_detail: str


def _parts_from_state(state: GraphState) -> _ReportParts:
    return _ReportParts(
        raw=str(state.get("raw_prompt") or "").strip(),
        final=str(state.get("final_prompt") or "").strip(),
        sniffer=dict(state.get("intent_sniffer_analysis") or {}),
        routing=dict(state.get("compute_aware_routing_decision") or {}),
        route=state.get("output_route"),
        blueprint=str(state.get("workflow_blueprint") or "").strip(),
        dspy=str(state.get("dspy_sketch") or "").strip(),
        draft=str(state.get("compiler_draft") or "").strip(),
        red_team_critic_passed=state.get("red_team_critic_passed"),
        critic_iters=state.get("red_team_critic_iterations"),
        critic_fb=str(state.get("red_team_critic_feedback") or "").strip(),
        prm_score=state.get("prm_score"),
        halted=state.get("red_team_critic_halted_max"),
        compilation_aborted=bool(state.get("compilation_aborted")),
        abort_reason=str(state.get("abort_reason") or "").strip(),
        abort_detail=str(state.get("abort_detail") or "").strip(),
    )


def _fence_block(content: str) -> str:
    """Wrap content in a Markdown fenced code block, lengthening fences if needed."""
    fence = "```"
    while fence in content:
        fence = fence + "`"
    return f"{fence}\n{content.rstrip()}\n{fence}\n"


def _bullet_line(label: str, value: object) -> str:
    if value is None or value == "":
        return f"- **{label}:** (none)"
    if isinstance(value, bool):
        return f"- **{label}:** {'yes' if value else 'no'}"
    return f"- **{label}:** {value}"


def _format_dict_section(title: str, data: dict[str, object]) -> str:
    if not data:
        return f"### {title}\n\n*(empty)*\n\n"
    pretty = json.dumps(data, ensure_ascii=False, indent=2)
    return f"### {title}\n\n{_fence_block(pretty)}"


def compilation_report_dict(
    state: GraphState,
    *,
    settings: Settings | None = None,
    include_summary: bool = True,
    include_before_after: bool = False,
) -> dict[str, Any]:
    """Structured, JSON-serializable compilation report (subset of full graph state)."""
    p = _parts_from_state(state)
    settings_dict: dict[str, Any] | None = None
    if settings is not None:
        settings_dict = {
            "llm_provider": settings.llm_provider,
            "model": settings.resolved_model(),
            "api_base_url": settings.resolved_base_url(),
            "llm_temperature": settings.llm_temperature,
            "max_red_team_critic_iterations": settings.max_critic_iterations,
        }
    out: dict[str, Any] = {
        "summary": None,
        "before_after": None,
        "settings": settings_dict,
        "intent_sniffer_analysis": p.sniffer,
        "compute_aware_routing_decision": p.routing,
        "critic": {
            "passed": p.red_team_critic_passed,
            "iterations": p.critic_iters,
            "halted_at_max": p.halted,
            "feedback": p.critic_fb,
            "prm_score": p.prm_score,
        },
        "compiler_draft": p.draft,
        "deliverables": {
            "output_route": p.route,
            "final_prompt": p.final,
            "workflow_blueprint": p.blueprint,
            "dspy_sketch": p.dspy,
        },
    }
    if include_summary:
        out["summary"] = {
            "compilation_aborted": p.compilation_aborted,
            "abort_reason": p.abort_reason or None,
            "abort_detail": p.abort_detail or None,
            "output_route": p.route,
            "red_team_critic_passed": p.red_team_critic_passed,
            "red_team_critic_iterations": p.critic_iters,
            "red_team_critic_halted_max": p.halted,
            "alignment_risk": p.sniffer.get("alignment_risk"),
            "threats": p.sniffer.get("threats"),
            "complexity": p.routing.get("complexity"),
            "multi_node_recommended": p.routing.get("multi_node_recommended"),
        }
    if include_before_after:
        out["before_after"] = {"raw_prompt": p.raw, "final_prompt": p.final}
    return out


def render_compilation_report(
    state: GraphState,
    *,
    settings: Settings | None = None,
    include_summary: bool = True,
    include_before_after: bool = False,
) -> str:
    """Render a human-readable Markdown report from a post-invocation graph state."""
    p = _parts_from_state(state)
    lines: list[str] = ["# Prompt Polisher Compilation Report", ""]

    if include_summary:
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(_bullet_line("Compilation aborted", p.compilation_aborted))
        if p.compilation_aborted:
            lines.append(_bullet_line("Abort reason", p.abort_reason or "(none)"))
            if p.abort_detail:
                lines.append(_bullet_line("Abort detail", p.abort_detail))
        lines.append(_bullet_line("Output route", p.route))
        lines.append(_bullet_line("Critic passed", p.red_team_critic_passed))
        lines.append(_bullet_line("Critic iterations", p.critic_iters))
        lines.append(_bullet_line("PRM score (if used)", p.prm_score))
        lines.append(_bullet_line("Stopped at max critic iterations", p.halted))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 📦 Deliverables")
    lines.append("> *Ready-to-use artifacts generated from the pipeline.*")
    lines.append("")

    lines.append("### ✨ Final Compiled Prompt")
    lines.append("👇 *Copy the code block below directly into your target LLM* 👇")
    lines.append("")
    lines.append(_fence_block(p.final if p.final else "(empty)"))

    if p.blueprint:
        lines.append("### 🗺️ Workflow Blueprint")
        lines.append("")
        lines.append(_fence_block(p.blueprint))

    if p.dspy:
        lines.append("### 🪄 DSPy Sketch")
        lines.append("")
        lines.append(_fence_block(p.dspy))

    # All the verbose stuff goes into a details block
    lines.append("---")
    lines.append("")
    lines.append("## 🔍 Compilation Diagnostics")
    lines.append("<details>")
    summary_text = "Click to expand internal graph metadata (Sniffer, Routing, Critic loops)"
    lines.append(f"<summary>{summary_text}</summary>")
    lines.append("")

    if include_before_after:
        lines.append("### Raw Input")
        lines.append("")
        lines.append(_fence_block(p.raw if p.raw else "(empty)"))

    if settings is not None:
        lines.append("### Settings Snapshot")
        lines.append("")
        lines.append(_bullet_line("LLM provider", settings.llm_provider))
        lines.append(_bullet_line("Model", settings.resolved_model()))
        base = settings.resolved_base_url()
        lines.append(_bullet_line("API base URL", base if base else "(default)"))
        lines.append(_bullet_line("Temperature", settings.llm_temperature))
        lines.append(_bullet_line("Max critic iterations", settings.max_critic_iterations))
        lines.append(_bullet_line("Critic use PRM", settings.critic_use_prm))
        if settings.critic_use_prm:
            lines.append(_bullet_line("PRM min score", settings.prm_min_score))
        lines.append("")

    lines.append("### Intent Sniffer Analysis")
    lines.append("")
    lines.append(_format_dict_section("Structured fields", p.sniffer))

    lines.append("### Routing and Anchoring")
    lines.append("")
    lines.append(_format_dict_section("Structured fields", p.routing))

    lines.append("### Critic Loop Details")
    lines.append("")
    lines.append(_bullet_line("Passed", p.red_team_critic_passed))
    lines.append(_bullet_line("Iterations", p.critic_iters))
    lines.append(_bullet_line("PRM score", p.prm_score))
    lines.append(_bullet_line("Halted at cap", p.halted))
    lines.append("")
    lines.append("#### Latest feedback")
    lines.append("")
    lines.append(_fence_block(p.critic_fb if p.critic_fb else "(none)"))
    lines.append("#### Last draft (pre-router)")
    lines.append("")
    lines.append(_fence_block(p.draft if p.draft else "(none)"))

    lines.append("</details>")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"
