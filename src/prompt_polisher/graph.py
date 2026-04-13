from __future__ import annotations

import asyncio
import logging
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
        abort, _ = should_abort_after_intent_sniffer(s, settings)
        return "safety_abort_gate" if abort else "compute_aware_router"

    graph.add_conditional_edges(
        "intent_sniffer",
        cast(Any, route_after_intent_sniffer),
        {"safety_abort_gate": "safety_abort_gate", "compute_aware_router": "compute_aware_router"},
    )
    graph.add_edge("compute_aware_router", "structured_compiler")
    graph.add_edge("structured_compiler", "red_team_critic")

    def route_after_red_team_critic(state: GraphState) -> str:
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
    app = build_graph(settings, llm)
    initial: GraphState = {"raw_prompt": raw_prompt}

    if on_node_start is not None or on_node_done is not None:
        # Stream mode: use astream so callers get per-node lifecycle hooks.
        final_state: GraphState = dict(initial)  # type: ignore

        if on_node_start is not None:
            on_node_start("intent_sniffer", {})

        async for event in app.astream(initial, stream_mode="updates"):
            for node_name, node_update in event.items():
                final_state.update(node_update)
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
    else:
        result = cast(GraphState, await app.ainvoke(initial))

    logger.info(
        "compiler finished route=%s critic_iters=%s passed=%s aborted=%s",
        result.get("output_route"),
        result.get("red_team_critic_iterations"),
        result.get("red_team_critic_passed"),
        bool(result.get("compilation_aborted")),
    )
    return result


def run_compiler(raw_prompt: str, settings: Settings, llm: LLMClient) -> GraphState:
    """Synchronous convenience wrapper — runs the async compiler in a new event loop."""
    return asyncio.run(run_compiler_async(raw_prompt, settings, llm))
