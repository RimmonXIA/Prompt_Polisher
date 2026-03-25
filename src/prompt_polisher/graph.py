from __future__ import annotations

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

    def radar(s: GraphState) -> dict[str, Any]:
        return node_radar(s, llm, settings)

    def routing(s: GraphState) -> dict[str, Any]:
        return node_routing(s, llm, settings)

    def compile_(s: GraphState) -> dict[str, Any]:
        return node_compile(s, llm, settings)

    def critic(s: GraphState) -> dict[str, Any]:
        return node_critic(s, llm, settings)

    def router(s: GraphState) -> dict[str, Any]:
        return node_router(s, llm, settings)

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


def run_compiler(raw_prompt: str, settings: Settings, llm: LLMClient) -> GraphState:
    app = build_graph(settings, llm)
    initial: GraphState = {"raw_prompt": raw_prompt}
    out = app.invoke(initial)
    logger.info(
        "compiler finished route=%s critic_iters=%s passed=%s aborted=%s",
        out.get("output_route"),
        out.get("critic_iterations"),
        out.get("critic_passed"),
        out.get("compilation_aborted"),
    )
    return cast(GraphState, out)
