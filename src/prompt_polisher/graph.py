from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from prompt_polisher.config import Settings
from prompt_polisher.gate import node_early_abort, should_abort_after_radar
from prompt_polisher.llm import LLMClient
from prompt_polisher.nodes import (
    node_compile,
    node_critic,
    node_radar,
    node_router,
    node_routing,
)
from prompt_polisher.state import GraphState

logger = logging.getLogger(__name__)


def build_graph(settings: Settings, llm: LLMClient) -> Any:
    graph = StateGraph(GraphState)

    async def radar(s: GraphState) -> dict[str, Any]:
        return await node_radar(s, llm, settings)

    async def routing(s: GraphState) -> dict[str, Any]:
        return await node_routing(s, llm, settings)

    async def compile_(s: GraphState) -> dict[str, Any]:
        return await node_compile(s, llm, settings)

    async def critic(s: GraphState) -> dict[str, Any]:
        return await node_critic(s, llm, settings)

    async def router(s: GraphState) -> dict[str, Any]:
        return await node_router(s, llm, settings)

    def early_abort(s: GraphState) -> dict[str, Any]:
        return node_early_abort(s, settings)

    graph.add_node("radar", cast(Any, radar))
    graph.add_node("routing", cast(Any, routing))
    graph.add_node("compile", cast(Any, compile_))
    graph.add_node("critic", cast(Any, critic))
    graph.add_node("router", cast(Any, router))
    graph.add_node("early_abort", cast(Any, early_abort))

    graph.add_edge(START, "radar")

    def route_after_radar(s: GraphState) -> str:
        abort, _ = should_abort_after_radar(s, settings)
        return "early_abort" if abort else "routing"

    graph.add_conditional_edges(
        "radar",
        cast(Any, route_after_radar),
        {"early_abort": "early_abort", "routing": "routing"},
    )
    graph.add_edge("routing", "compile")
    graph.add_edge("compile", "critic")

    def route_after_critic(state: GraphState) -> str:
        if state.get("critic_passed"):
            return "router"
        it = int(state.get("critic_iterations") or 0)
        if it >= settings.max_critic_iterations:
            return "router"
        return "compile"

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {"router": "router", "compile": "compile"},
    )
    graph.add_edge("router", END)
    graph.add_edge("early_abort", END)

    return graph.compile()


async def run_compiler_async(
    raw_prompt: str,
    settings: Settings,
    llm: LLMClient,
    *,
    stream_to_stderr: bool = False,
) -> GraphState:
    import sys

    app = build_graph(settings, llm)
    initial: GraphState = {"raw_prompt": raw_prompt}

    if stream_to_stderr:
        out: GraphState = cast(GraphState, {})
        async for event in app.astream(initial, stream_mode="updates"):
            for node_name, _node_update in event.items():
                print(f"[prompt-polisher] ▶ {node_name}", file=sys.stderr)
            out.update(event.get(list(event.keys())[-1], {}))
        # ainvoke gives us the full merged state; stream_mode won't.
        # Run ainvoke after streaming preview so we get the authoritative result.
        result = cast(GraphState, await app.ainvoke(initial))
    else:
        result = cast(GraphState, await app.ainvoke(initial))

    logger.info(
        "compiler finished route=%s critic_iters=%s passed=%s aborted=%s",
        result.get("output_route"),
        result.get("critic_iterations"),
        result.get("critic_passed"),
        bool(result.get("compilation_aborted")),
    )
    return result


def run_compiler(raw_prompt: str, settings: Settings, llm: LLMClient) -> GraphState:
    """Synchronous entry point – runs the async compiler in a new event loop."""
    return asyncio.run(run_compiler_async(raw_prompt, settings, llm))
