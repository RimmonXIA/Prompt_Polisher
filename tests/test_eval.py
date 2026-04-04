from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from prompt_polisher.config import get_settings
from prompt_polisher.eval.load import load_evalset, resolve_evalset_dir
from prompt_polisher.eval.outcome import score_outcome
from prompt_polisher.eval.runner import run_eval_suite
from prompt_polisher.eval.schema import EvalItem, GoldSpec, StructuralExpect
from prompt_polisher.eval.structural import compute_structural
from prompt_polisher.graph import run_compiler
from prompt_polisher.llm import FakeLLMClient


class CountingFakeLLM(FakeLLMClient):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.chat_calls = 0

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        self.chat_calls += 1
        return super().chat(messages, temperature=temperature, model=model)

    async def achat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        model: str | None = None,
    ) -> str:
        self.chat_calls += 1
        return super().chat(messages, temperature=temperature, model=model)


def _happy_path_responses() -> list[str]:
    compile_out = (
        '{"draft":"'
        "<thinking>reason step by step</thinking>"
        "<user_context>user</user_context>"
        'Please answer with clarity and structure."}'
    )
    tail = [
        '{"passed":true,"feedback":"","verification_steps":[]}',
        '{"final_prompt":"FINAL_PROMPT","workflow_blueprint":"WF","dspy_sketch":"DSPY"}',
    ]
    return [
        '{"negations_flipped":"Do X clearly","threats":[],"alignment_risk":"low","summary":"ok"}',
        '{"complexity":"low","multi_node_recommended":false,'
        '"anchor_persona":"expert","rationale":"simple"}',
        compile_out,
        *tail,
    ]


def _repo_evalset_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "evalsets" / "bundled"


def test_load_evalset_from_repo() -> None:
    es = load_evalset(_repo_evalset_dir())
    assert es.manifest.version == "1"
    ids = [i.id for i in es.items]
    assert "smoke-structural-01" in ids
    assert "gate-heuristic-01" in ids


def test_score_outcome_exact_and_contains() -> None:
    assert score_outcome("yes", GoldSpec(type="exact_match", value="yes")).score == 1.0
    assert score_outcome("no", GoldSpec(type="exact_match", value="yes")).score == 0.0
    g = GoldSpec(type="contains_all", values=["a", "b"])
    assert score_outcome("x a y b", g).score == 1.0
    assert score_outcome("only a", g).score == 0.0


def test_score_outcome_json_keys() -> None:
    g = GoldSpec(type="json_keys", keys=["x"], key_values={"x": "1"})
    assert score_outcome('{"x": 1}', g).score == 1.0
    assert score_outcome('{"x": 2}', g).score == 0.0
    assert score_outcome("not json", g).score == 0.0


def test_structural_expect_detects_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    settings = get_settings()
    llm = CountingFakeLLM(_happy_path_responses())
    state = run_compiler("hello", settings, llm)
    item = EvalItem(
        id="x",
        user_intent="hello",
        structural_expect=StructuralExpect(compilation_aborted=True),
    )
    sr = compute_structural(state, item)
    assert sr.structural_expect_ok is False
    assert sr.structural_mismatches


def test_run_eval_suite_structural_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("MAX_CRITIC_ITERATIONS", "2")
    monkeypatch.setenv("ABORT_ON_HEURISTIC_INJECTION", "true")
    get_settings.cache_clear()
    settings = get_settings()

    responses = (
        _happy_path_responses()
        + [
            '{"negations_flipped":"x","threats":[],"alignment_risk":"low","summary":"s"}',
        ]
        + _happy_path_responses()
    )
    llm = CountingFakeLLM(responses)
    evalset = load_evalset(_repo_evalset_dir())
    report = asyncio.run(
        run_eval_suite(
            evalset,
            settings=settings,
            compile_llm=llm,
            executor_llm=None,
            structural_only=True,
        )
    )
    data = report.to_json_dict()
    assert data["counts"]["tier_a_passed"] == len(evalset.items)
    assert data["counts"]["tier_a_failed"] == 0
    assert llm.chat_calls == len(responses)


def test_resolve_evalset_dir_explicit() -> None:
    d = resolve_evalset_dir(_repo_evalset_dir())
    assert (d / "manifest.json").is_file()


def test_eval_cli_structural_only_writes_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("MAX_CRITIC_ITERATIONS", "2")
    monkeypatch.setenv("ABORT_ON_HEURISTIC_INJECTION", "true")
    get_settings.cache_clear()
    responses = (
        _happy_path_responses()
        + [
            '{"negations_flipped":"x","threats":[],"alignment_risk":"low","summary":"s"}',
        ]
        + _happy_path_responses()
    )
    import prompt_polisher.eval.cli as eval_cli

    monkeypatch.setattr(
        eval_cli,
        "build_llm_client",
        lambda _settings: CountingFakeLLM(list(responses)),
    )
    out = tmp_path / "rep.json"
    code = eval_cli.main(
        [
            "--evalset-dir",
            str(_repo_evalset_dir()),
            "--structural-only",
            "--output",
            str(out),
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["counts"]["tier_a_passed"] == 3


def test_eval_cli_version_exits_zero() -> None:
    import prompt_polisher.eval.cli as eval_cli

    code = eval_cli.main(["--version"])
    assert code == 0

