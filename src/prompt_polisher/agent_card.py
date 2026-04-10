"""A2A Agent Card generator (spec §8.5).

Produces a dict matching the AgentCard schema from the official
Agent2Agent Protocol Specification.
Reference: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version


def _package_version() -> str:
    try:
        return pkg_version("prompt-polisher")
    except PackageNotFoundError:
        return "0.0.0"


def build_agent_card() -> dict[str, object]:
    """Return a spec-compliant A2A Agent Card dict.

    Fields follow §4.4.1 AgentCard and §8.5 Sample Agent Card.
    ``supportedInterfaces`` is empty here for CLI/static use. The live
    FastAPI A2A server overwrites this with the JSON-RPC endpoint URL.
    """
    return {
        "name": "Prompt Polisher",
        "description": (
            "Multi-node LangGraph prompt compiler. "
            "Pipeline: radar → threat gate → routing → compile → critic. "
            "Accepts raw user intent and produces structured, safe, "
            "compute-optimized LLM prompts, workflow blueprints, "
            "or DSPy-style sketches."
        ),
        "version": _package_version(),
        "provider": {
            "organization": "RimmonXIA",
            "url": "https://github.com/RimmonXIA/Prompt_Polisher",
        },
        "documentationUrl": (
            "https://github.com/RimmonXIA/Prompt_Polisher/blob/main/docs/THEORY.en.md"
        ),
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": [
            "application/json",
            "text/plain",
            "text/markdown",
        ],
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "skills": [
            {
                "id": "prompt-compile",
                "name": "Prompt Compilation",
                "description": (
                    "Compiles raw intent into structured, safe, "
                    "compute-optimized LLM prompts. Includes threat "
                    "detection, complexity routing, CoT injection, "
                    "and a Critic feedback loop."
                ),
                "tags": [
                    "prompt-engineering",
                    "compiler",
                    "safety",
                    "langgraph",
                    "critic",
                ],
                "examples": [
                    "Summarize this repo for a release note",
                    "Help me write a Python web scraper",
                    "Design a system prompt for a customer support chatbot",
                ],
                "inputModes": ["text/plain"],
                "outputModes": [
                    "application/json",
                    "text/plain",
                    "text/markdown",
                ],
            }
        ],
        "supportedInterfaces": [],
    }
