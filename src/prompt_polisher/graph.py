from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from prompt_polisher.config import Settings
from prompt_polisher.gate import node_safety_abort_gate, should_abort_after_intent_sniffer
from prompt_polisher.llm import LLMClient
from prompt_polisher.nodes import (
    node_artifact_dispatcher,
    node_compute_aware_router,
    node_intent_sniffer,
    node_red_team_critic,
    node_structured_compiler,
)
from prompt_polisher.state import GraphState

logger = logging.getLogger(__name__)

# Callback type: receives (node_name, event) on each stream tick.
NodeEventCallback = Callable[[str, dict[str, Any]], None]


class _CountingLLMClient:
    """Wrap an LLM client and count total chat/achat invocations."""

    def __init__(self, inner: LLMClient, counter: dict[str, int]) -> None:
        self._inner = inner
        self._counter = counter

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        self._counter["calls"] = self._counter.get("calls", 0) + 1
        return self._inner.chat(messages, temperature=temperature, model=model)

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        self._counter["calls"] = self._counter.get("calls", 0) + 1
        return await self._inner.achat(messages, temperature=temperature, model=model)


def _word_set(text: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-z0-9_]{3,}", text.lower())}


def _bool_word_hint(text: str, hints: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(h in lowered for h in hints)


def _compute_quality_signals(raw_prompt: str, result: GraphState) -> dict[str, object]:
    final_prompt = str(result.get("final_prompt") or "")
    raw_len = max(len(raw_prompt), 1)
    ratio = len(final_prompt) / raw_len
    target = str(result.get("optimization_target") or "general")
    prompt_type = str(result.get("prompt_type") or "unknown")

    if target == "concise":
        if ratio > 3.0:
            over_expansion_risk = "high"
        elif ratio > 2.0:
            over_expansion_risk = "medium"
        else:
            over_expansion_risk = "low"
    else:
        if ratio > 6.0:
            over_expansion_risk = "high"
        elif ratio > 3.0:
            over_expansion_risk = "medium"
        else:
            over_expansion_risk = "low"

    raw_words = _word_set(raw_prompt)
    final_words = _word_set(final_prompt)
    if len(raw_words) < 4:
        intent_preserved: bool | str = "unknown"
    else:
        overlap = len(raw_words & final_words) / max(len(raw_words), 1)
        intent_preserved = overlap >= 0.2

    introduced_unrequested_role = (
        _bool_word_hint(final_prompt, ("you are ", "act as ", "role:"))
        and not _bool_word_hint(raw_prompt, ("you are ", "act as ", "role:"))
    )
    introduced_unrequested_steps = (
        _bool_word_hint(final_prompt, ("step 1", "step-1", "1.", "2.", "first,", "second,"))
        and not _bool_word_hint(raw_prompt, ("step 1", "1.", "2.", "first,", "second,"))
    )

    if prompt_type == "json_extraction_prompt":
        format_strengthened: bool | str = (
            _bool_word_hint(final_prompt, ("json", "only", "schema", "null"))
        )
    elif target == "strict_format":
        format_strengthened = True
    else:
        format_strengthened = "unknown"

    return {
        "intent_preserved": intent_preserved,
        "format_strengthened": format_strengthened,
        "over_expansion_risk": over_expansion_risk,
        "introduced_unrequested_role": introduced_unrequested_role,
        "introduced_unrequested_steps": introduced_unrequested_steps,
        "length_ratio": round(ratio, 3),
    }


def build_graph(settings: Settings, llm: LLMClient) -> Any:
    graph = StateGraph(GraphState)

    async def intent_sniffer(s: GraphState) -> dict[str, Any]:
        return await node_intent_sniffer(s, llm, settings)

    async def compute_aware_router(s: GraphState) -> dict[str, Any]:
        return await node_compute_aware_router(s, llm, settings)

    async def structured_compiler(s: GraphState) -> dict[str, Any]:
        return await node_structured_compiler(s, llm, settings)

    async def red_team_critic(s: GraphState) -> dict[str, Any]:
        return await node_red_team_critic(s, llm, settings)

    async def artifact_dispatcher(s: GraphState) -> dict[str, Any]:
        return await node_artifact_dispatcher(s, llm, settings)

    def safety_abort_gate(s: GraphState) -> dict[str, Any]:
        return node_safety_abort_gate(s, settings)

    graph.add_node("intent_sniffer", cast(Any, intent_sniffer))
    graph.add_node("compute_aware_router", cast(Any, compute_aware_router))
    graph.add_node("structured_compiler", cast(Any, structured_compiler))
    graph.add_node("red_team_critic", cast(Any, red_team_critic))
    graph.add_node("artifact_dispatcher", cast(Any, artifact_dispatcher))
    graph.add_node("safety_abort_gate", cast(Any, safety_abort_gate))

    graph.add_edge(START, "intent_sniffer")

    def route_after_intent_sniffer(s: GraphState) -> str:
        if s.get("fatal_error"):
            return END
        abort, _ = should_abort_after_intent_sniffer(s, settings)
        return "safety_abort_gate" if abort else "compute_aware_router"

    graph.add_conditional_edges(
        "intent_sniffer",
        cast(Any, route_after_intent_sniffer),
        {
            "safety_abort_gate": "safety_abort_gate",
            "compute_aware_router": "compute_aware_router",
            END: END,
        },
    )

    def route_after_compute_aware_router(s: GraphState) -> str:
        if s.get("fatal_error"):
            return END
        return "structured_compiler"

    graph.add_conditional_edges(
        "compute_aware_router",
        cast(Any, route_after_compute_aware_router),
        {"structured_compiler": "structured_compiler", END: END},
    )

    def route_after_structured_compiler(s: GraphState) -> str:
        if s.get("fatal_error"):
            return END
        if settings.execution_mode == "fast":
            return "artifact_dispatcher"
        return "red_team_critic"

    graph.add_conditional_edges(
        "structured_compiler",
        cast(Any, route_after_structured_compiler),
        {
            "artifact_dispatcher": "artifact_dispatcher",
            "red_team_critic": "red_team_critic",
            END: END,
        },
    )

    def route_after_red_team_critic(state: GraphState) -> str:
        if state.get("fatal_error"):
            return END
        if state.get("red_team_critic_passed"):
            return "artifact_dispatcher"
        it = int(state.get("red_team_critic_iterations") or 0)
        if it >= settings.max_critic_iterations:
            return "artifact_dispatcher"
        return "structured_compiler"

    graph.add_conditional_edges(
        "red_team_critic",
        route_after_red_team_critic,
        {
            "artifact_dispatcher": "artifact_dispatcher",
            "structured_compiler": "structured_compiler",
            END: END,
        },
    )
    graph.add_edge("artifact_dispatcher", END)
    graph.add_edge("safety_abort_gate", END)

    return graph.compile()


async def run_compiler_async(
    raw_prompt: str,
    settings: Settings,
    llm: LLMClient,
    *,
    on_node_start: NodeEventCallback | None = None,
    on_node_done: NodeEventCallback | None = None,
) -> GraphState:
    """Run the compiler graph asynchronously.

    Args:
        raw_prompt: The sanitised user prompt.
        settings: Application settings.
        llm: LLM client implementation.
        on_node_start: Optional callback invoked *before* each node runs,
            receiving ``(node_name, raw_event_dict)``.
        on_node_done: Optional callback invoked *after* each node completes,
            receiving ``(node_name, raw_event_dict)``.

    Returns:
        The merged :class:`GraphState` after the graph finishes.
    """
    llm_counter: dict[str, int] = {"calls": 0}
    counted_llm = cast(LLMClient, _CountingLLMClient(llm, llm_counter))
    app = build_graph(settings, counted_llm)
    initial: GraphState = {
        "raw_prompt": raw_prompt,
        "optimization_target": settings.optimization_target,
    }
    final_state: GraphState = cast(GraphState, dict(initial))
    nodes_executed: list[str] = []

    if on_node_start is not None:
        on_node_start("intent_sniffer", {})

    async for event in app.astream(initial, stream_mode="updates"):
        for node_name, node_update in event.items():
            final_state.update(node_update)
            nodes_executed.append(node_name)
            if on_node_done is not None:
                on_node_done(node_name, node_update)

            # Predict next node to drive the interactive spinner accurately
            next_node = None
            if node_name == "intent_sniffer":
                from prompt_polisher.gate import should_abort_after_intent_sniffer

                abort, _ = should_abort_after_intent_sniffer(final_state, settings)
                next_node = "safety_abort_gate" if abort else "compute_aware_router"
            elif node_name == "compute_aware_router":
                next_node = "structured_compiler"
            elif node_name == "structured_compiler":
                next_node = "red_team_critic"
            elif node_name == "red_team_critic":
                max_iters_reached = (
                    int(final_state.get("red_team_critic_iterations", 0))
                    >= settings.max_critic_iterations
                )
                if final_state.get("red_team_critic_passed") or max_iters_reached:
                    next_node = "artifact_dispatcher"
                else:
                    next_node = "structured_compiler"

            if next_node and on_node_start is not None:
                on_node_start(next_node, {})

    result = final_state
    result["execution_mode"] = settings.execution_mode
    result["optimization_target"] = str(
        result.get("optimization_target") or settings.optimization_target
    )
    result["nodes_executed"] = nodes_executed
    result["llm_call_count"] = int(llm_counter.get("calls", 0))
    result["cost_signals"] = {
        "raw_prompt_chars": len(raw_prompt),
        "final_prompt_chars": len(str(result.get("final_prompt") or "")),
    }
    result["quality_signals"] = _compute_quality_signals(raw_prompt, result)

    logger.info(
        "compiler finished route=%s critic_iters=%s passed=%s aborted=%s llm_calls=%s nodes=%s",
        result.get("output_route"),
        result.get("red_team_critic_iterations"),
        result.get("red_team_critic_passed"),
        bool(result.get("compilation_aborted")),
        result.get("llm_call_count"),
        len(nodes_executed),
    )
    return result


def run_compiler(raw_prompt: str, settings: Settings, llm: LLMClient) -> GraphState:
    """Synchronous convenience wrapper — runs the async compiler in a new event loop."""
    return asyncio.run(run_compiler_async(raw_prompt, settings, llm))
