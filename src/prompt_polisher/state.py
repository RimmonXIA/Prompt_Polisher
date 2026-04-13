from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

OutputRoute = Literal["instance", "template", "dspy"]


# ---------------------------------------------------------------------------
# Structured node outputs: Pydantic models for each LLM node.
# ---------------------------------------------------------------------------


class RadarAnalysis(BaseModel):
    """Output of the Radar node: Orchestrator analyzes Author intent and threat signals."""

    negations_flipped: str = Field(default="", description="Positive rewrite of the raw prompt.")
    threats: list[str] = Field(default_factory=list, description="Identified threat strings.")
    alignment_risk: Literal["low", "medium", "high"] = Field(
        default="medium", description="Risk level for policy misalignment."
    )
    summary: str = Field(
        description=(
            "Write a very brief, empathetic summary of the Author's true intent or pain point. "
            "MUST be written in the SAME LANGUAGE as the Author's original prompt "
            "(e.g. Simplified Chinese). Use a non-technical, human-friendly tone. "
            "Do not use AI/LLM jargon."
        )
    )
    linguistic_entropy: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Heuristic measure of input complexity to guide vocabulary elevation.",
    )


class RoutingDecision(BaseModel):
    """Output of the Routing node: Orchestrator complexity budget and anchor strategy."""

    complexity: Literal["low", "medium", "high"] = Field(
        default="medium", description="Estimated task complexity."
    )
    multi_node_recommended: bool = Field(
        default=False, description="Whether a multi-step workflow is recommended."
    )
    anchor_persona: str = Field(
        default="careful expert assistant", description="Persona / style anchor for Compile."
    )
    audience_anchor: str = Field(
        default="general public",
        description=(
            "Target receptor context to stabilize tone and reasoning depth for the Target executor."
        ),
    )
    rationale: str = Field(
        description=(
            "Brief, user-facing explanation in the SAME LANGUAGE as the Invoker's original "
            "prompt of how compilation will encode the Author's specification into the "
            "hardened prompt for the downstream Target executor—not how you behave during "
            "this routing turn. Prefer third person or neutral analyst phrasing (what the "
            "compiled artifact will require or preserve). Do not restate the author's "
            "constraints as first-person self-commitments about yourself. Avoid internal "
            "routing or compiler jargon."
        )
    )


class CompileDraft(BaseModel):
    """Output of the Compile node: the draft prompt text.
    This is an Orchestrator payload intended for the Target executor."""

    draft: str = Field(
        default="",
        description=(
            "Compiled prompt draft. Must convey instructions for the Target "
            "without Orchestrator first-person phrasing."
        ),
    )


class CriticFeedback(BaseModel):
    """Output of the Critic node: Orchestrator audits its own output."""

    passed: bool = Field(default=False, description="Whether the draft passes review.")
    feedback: str = Field(default="", description="Critic feedback or failure reason.")
    verification_steps: list[str] = Field(
        default_factory=list, description="Step-by-step reasoning trace."
    )


class PrmEvaluation(BaseModel):
    """Output of the PRM model evaluation."""

    score: float = Field(default=0.0, description="Quality score between 0.0 and 1.0.")
    note: str = Field(default="", description="Reasoning for the assigned score.")


class RouterDeliverable(BaseModel):
    """Output of the Router node: Orchestrator's final deliverables."""

    final_prompt: str = Field(default="", description="The final polished prompt for the Target.")
    workflow_blueprint: str = Field(
        default="", description="Markdown describing a multi-step AI workflow."
    )
    dspy_sketch: str = Field(
        default="", description="Outline of a DSPy-style module/signature/optimizer plan."
    )


# ---------------------------------------------------------------------------
# LangGraph workflow state (TypedDict; node payloads as plain dicts).
# ---------------------------------------------------------------------------


class GraphState(TypedDict, total=False):
    """LangGraph state for the Orchestrator's prompt compiler workflow.

    This state object transitions from Author/Invoker input (raw_prompt) through Orchestrator
    analysis and compilation phases, resulting in deliverables for the Target."""

    raw_prompt: str

    # Node outputs – stored as plain dicts for backward-compat with existing
    # serialisation and prompt bundle code; Pydantic models are used at the
    # node boundary for validation, then converted via .model_dump().
    intent_sniffer_analysis: dict[str, object]
    compute_aware_routing_decision: dict[str, object]

    compiler_draft: str
    # Reducer: critic feedback history accumulates across retries (list join)
    red_team_critic_feedback: str
    red_team_critic_passed: bool
    red_team_critic_iterations: int
    red_team_critic_halted_max: bool
    prm_score: float

    output_route: OutputRoute
    final_prompt: str
    workflow_blueprint: str
    dspy_sketch: str

    compilation_aborted: bool
    abort_reason: str
    abort_detail: str
