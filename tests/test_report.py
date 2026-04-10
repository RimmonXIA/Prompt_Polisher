from __future__ import annotations

import json

from prompt_polisher.report import compilation_report_dict, render_compilation_report
from prompt_polisher.state import GraphState


def test_fence_block_escapes_embedded_triple_backticks() -> None:
    from prompt_polisher.report import _fence_block

    inner = "foo\n```\nbar\n```\n"
    out = _fence_block(inner)
    assert out.startswith("````")
    assert out.endswith("````\n")
    assert inner in out


def test_render_compilation_report_includes_sections() -> None:
    state: GraphState = {
        "raw_prompt": "do the thing",
        "radar_analysis": {"alignment_risk": "low", "threats": []},
        "routing_decision": {"complexity": "low", "multi_node_recommended": False},
        "draft": "<user_context>do the thing</user_context>",
        "critic_passed": True,
        "critic_iterations": 1,
        "critic_feedback": "ok",
        "output_route": "instance",
        "final_prompt": "FINAL",
        "workflow_blueprint": "step 1",
        "dspy_sketch": "sketch",
    }
    md = render_compilation_report(state, include_summary=True, include_before_after=False)
    assert "# Prompt Polisher Compilation Report" in md
    assert "## Executive Summary" in md
    assert "### Radar Analysis" in md
    assert "### Routing and Anchoring" in md
    assert "### Critic Loop Details" in md
    assert "## 📦 Deliverables" in md
    assert "FINAL" in md
    assert "### ✨ Final Compiled Prompt" in md


def test_render_before_after_shows_raw_input_in_diagnostics() -> None:
    state: GraphState = {
        "raw_prompt": "RAW",
        "final_prompt": "FINAL",
        "output_route": "instance",
    }
    md = render_compilation_report(state, include_before_after=True)
    assert "### Raw Input" in md
    assert "RAW" in md
    assert "## 📦 Deliverables" in md
    assert "## 🔍 Compilation Diagnostics" in md


def test_compilation_report_dict_json_roundtrip() -> None:
    state: GraphState = {
        "raw_prompt": "x",
        "final_prompt": "y",
        "output_route": "dspy",
        "critic_passed": False,
        "critic_iterations": 2,
    }
    d = compilation_report_dict(state, include_summary=True, include_before_after=True)
    json.dumps(d)
    assert d["summary"] is not None
    assert d["before_after"] == {"raw_prompt": "x", "final_prompt": "y"}
    assert d["deliverables"]["output_route"] == "dspy"


def test_no_summary_omits_section() -> None:
    state: GraphState = {"raw_prompt": "a", "final_prompt": "b", "output_route": "instance"}
    md = render_compilation_report(state, include_summary=False)
    assert "## Executive Summary" not in md


def test_summary_shows_abort_when_flagged() -> None:
    state: GraphState = {
        "raw_prompt": "x",
        "final_prompt": "stopped",
        "output_route": "instance",
        "compilation_aborted": True,
        "abort_reason": "heuristic_prompt_injection",
        "abort_detail": "heuristic_prompt_injection: summary",
    }
    md = render_compilation_report(state, include_summary=True)
    assert "Compilation aborted" in md
    assert "heuristic_prompt_injection" in md
    d = compilation_report_dict(state, include_summary=True)
    assert d["summary"] is not None
    assert d["summary"]["compilation_aborted"] is True
    assert d["summary"]["abort_reason"] == "heuristic_prompt_injection"
