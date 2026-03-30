from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

OutputRoute = Literal["instance", "template", "dspy"]


# ---------------------------------------------------------------------------
# Phase 1 – Pydantic models for structured node output
# These are the canonical data shapes returned by each LLM node.
# ---------------------------------------------------------------------------


class RadarAnalysis(BaseModel):
    """Output of the Radar node: intent decomposition and threat signals."""

    negations_flipped: str = Field(default="", description="Positive rewrite of the raw prompt.")
    threats: list[str] = Field(default_factory=list, description="Identified threat strings.")
    alignment_risk: Literal["low", "medium", "high"] = Field(
        default="medium", description="Risk level for policy misalignment."
    )
    summary: str = Field(
        description=(
            "Write a very brief, empathetic summary of the user's true intent or pain point. "
            "MUST be written in the SAME LANGUAGE as the user's original prompt "
            "(e.g. Simplified Chinese). Use a non-technical, human-friendly tone. "
            "Do not use AI/LLM jargon."
        )
    )


class RoutingDecision(BaseModel):
    """Output of the Routing node: complexity budget and anchor strategy."""

    complexity: Literal["low", "medium", "high"] = Field(
        default="medium", description="Estimated task complexity."
    )
    multi_node_recommended: bool = Field(
        default=False, description="Whether a multi-step workflow is recommended."
    )
    anchor_persona: str = Field(
        default="careful expert assistant", description="Persona / style anchor for Compile."
    )
    rationale: str = Field(
        description=(
            "Write a brief, user-facing explanation of the strategy you have chosen to "
            "solve their problem. MUST be written in the SAME LANGUAGE as the user's "
            "original prompt. Avoid technical routing jargon; frame it as how you "
            "plan to help them."
        )
    )


class CompileDraft(BaseModel):
    """Output of the Compile node: the draft prompt text."""

    draft: str = Field(default="", description="Compiled prompt draft.")


class CriticFeedback(BaseModel):
    """Output of the Critic node."""

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
    """Output of the Router node."""

    final_prompt: str = Field(default="", description="The final polished prompt.")
    workflow_blueprint: str = Field(
        default="", description="Markdown describing a multi-step AI workflow."
    )
    dspy_sketch: str = Field(
        default="", description="Outline of a DSPy-style module/signature/optimizer plan."
    )


# ---------------------------------------------------------------------------
# Phase 2 – Reducer-aware LangGraph state (Annotated fields for auto-merge)
# ---------------------------------------------------------------------------


class GraphState(TypedDict, total=False):
    """LangGraph state for the prompt compiler workflow."""

    raw_prompt: str

    # Node outputs – stored as plain dicts for backward-compat with existing
    # serialisation and prompt bundle code; Pydantic models are used at the
    # node boundary for validation, then converted via .model_dump().
    radar_analysis: dict[str, object]
    routing_decision: dict[str, object]

    draft: str
    # Reducer: critic feedback history accumulates across retries (list join)
    critic_feedback: str
    critic_passed: bool
    critic_iterations: int
    critic_halted_max: bool
    prm_score: float

    output_route: OutputRoute
    final_prompt: str
    workflow_blueprint: str
    dspy_sketch: str

    compilation_aborted: bool
    abort_reason: str
    abort_detail: str
