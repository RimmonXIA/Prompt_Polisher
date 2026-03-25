from __future__ import annotations

from typing import Literal, TypedDict

OutputRoute = Literal["instance", "template", "dspy"]


class GraphState(TypedDict, total=False):
    """LangGraph state for the prompt compiler workflow."""

    raw_prompt: str

    radar_analysis: dict[str, object]
    routing_decision: dict[str, object]

    draft: str
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
