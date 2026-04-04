from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prompt_polisher.config import Settings
from prompt_polisher.eval.load import EvalSet
from prompt_polisher.eval.outcome import OutcomeResult, score_outcome
from prompt_polisher.eval.schema import EvalItem, GoldSpec
from prompt_polisher.eval.structural import (
    StructuralResult,
    compute_structural,
    structural_expect_passed,
)
from prompt_polisher.graph import run_compiler_async
from prompt_polisher.llm import LLMClient
from prompt_polisher.state import GraphState

DEFAULT_EXECUTOR_SYSTEM = (
    "You follow instructions with high precision. "
    "Produce only the output format the user asked for."
)


def _raw_user_block(user_intent: str) -> str:
    ui = user_intent.strip()
    return f"Complete the following task. Follow it exactly.\n\n---\n{ui}\n---"


def _compiled_user_block(final_prompt: str) -> str:
    fp = final_prompt.strip()
    return f"Execute the following compiled specification. Follow it exactly.\n\n---\n{fp}\n---"


@dataclass
class ArmResult:
    arm: str
    executor_output: str
    outcome: OutcomeResult | None
    error: str | None = None


@dataclass
class ExampleReport:
    item_id: str
    tags: list[str]
    structural: dict[str, Any]
    structural_mismatches: list[str]
    structural_expect_passed: bool
    compiled_available: bool
    raw: ArmResult | None
    compiled: ArmResult | None
    outcome_delta: float | None


@dataclass
class SuiteReport:
    evalset_version: str
    evalset_dir: str
    structural_only: bool
    model_compile: str | None
    model_executor: str | None
    examples: list[ExampleReport] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        tier_a_passed = sum(1 for e in self.examples if e.structural_expect_passed)
        return {
            "evalset_version": self.evalset_version,
            "evalset_dir": self.evalset_dir,
            "structural_only": self.structural_only,
            "model_compile": self.model_compile,
            "model_executor": self.model_executor,
            "counts": {
                "examples": len(self.examples),
                "tier_a_passed": tier_a_passed,
                "tier_a_failed": len(self.examples) - tier_a_passed,
            },
            "examples": [self._example_dict(e) for e in self.examples],
        }

    @staticmethod
    def _example_dict(e: ExampleReport) -> dict[str, Any]:
        def arm(a: ArmResult | None) -> dict[str, Any] | None:
            if a is None:
                return None
            od = None
            if a.outcome is not None:
                od = {"score": a.outcome.score, "detail": a.outcome.detail}
            return {
                "arm": a.arm,
                "executor_output": a.executor_output,
                "outcome": od,
                "error": a.error,
            }

        return {
            "id": e.item_id,
            "tags": e.tags,
            "structural": e.structural,
            "structural_mismatches": e.structural_mismatches,
            "structural_expect_passed": e.structural_expect_passed,
            "compiled_available": e.compiled_available,
            "outcome_delta": e.outcome_delta,
            "raw": arm(e.raw),
            "compiled": arm(e.compiled),
        }


def _structural_dict(sr: StructuralResult) -> dict[str, Any]:
    return {
        "compilation_aborted": sr.compilation_aborted,
        "critic_passed": sr.critic_passed,
        "final_prompt_nonempty": sr.final_prompt_nonempty,
        "draft_nonempty": sr.draft_nonempty,
    }


async def _run_executor_arm(
    *,
    arm: str,
    llm: LLMClient,
    system: str,
    user_content: str,
    gold: GoldSpec,
    executor_temperature: float | None,
) -> ArmResult:
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    try:
        out_text = await llm.achat(messages, temperature=executor_temperature)
        oc = score_outcome(out_text, gold)
        return ArmResult(arm=arm, executor_output=out_text, outcome=oc, error=None)
    except Exception as exc:
        return ArmResult(arm=arm, executor_output="", outcome=None, error=str(exc))


async def run_single_item(
    item: EvalItem,
    *,
    settings: Settings,
    compile_llm: LLMClient,
    executor_llm: LLMClient | None,
    structural_only: bool,
    executor_temperature: float | None,
) -> ExampleReport:
    system = item.executor_system or DEFAULT_EXECUTOR_SYSTEM
    state: GraphState = await run_compiler_async(
        item.user_intent.strip(),
        settings,
        compile_llm,
    )
    sr = compute_structural(state, item)
    struct_pass = structural_expect_passed(sr)
    final_prompt = str(state.get("final_prompt") or "").strip()
    aborted = bool(state.get("compilation_aborted"))
    compiled_available = bool(not aborted and final_prompt)

    raw_arm: ArmResult | None = None
    compiled_arm: ArmResult | None = None
    delta: float | None = None

    use_executor = executor_llm is not None and not structural_only and item.gold.type != "none"

    if use_executor:
        exec_lm = executor_llm
        assert exec_lm is not None
        raw_arm = await _run_executor_arm(
            arm="raw",
            llm=exec_lm,
            system=system,
            user_content=_raw_user_block(item.user_intent),
            gold=item.gold,
            executor_temperature=executor_temperature,
        )
        if compiled_available:
            compiled_arm = await _run_executor_arm(
                arm="compiled",
                llm=exec_lm,
                system=system,
                user_content=_compiled_user_block(final_prompt),
                gold=item.gold,
                executor_temperature=executor_temperature,
            )
        rs = raw_arm.outcome.score if raw_arm.outcome else None
        cs = compiled_arm.outcome.score if compiled_arm and compiled_arm.outcome else None
        if rs is not None and cs is not None:
            delta = cs - rs

    return ExampleReport(
        item_id=item.id,
        tags=list(item.tags),
        structural=_structural_dict(sr),
        structural_mismatches=list(sr.structural_mismatches),
        structural_expect_passed=struct_pass,
        compiled_available=compiled_available,
        raw=raw_arm,
        compiled=compiled_arm,
        outcome_delta=delta,
    )


async def run_eval_suite(
    evalset: EvalSet,
    *,
    settings: Settings,
    compile_llm: LLMClient,
    executor_llm: LLMClient | None = None,
    structural_only: bool = False,
    executor_temperature: float | None = None,
    log: Callable[[str], None] | None = None,
) -> SuiteReport:
    temp = settings.llm_temperature if executor_temperature is None else executor_temperature
    examples: list[ExampleReport] = []
    for i, item in enumerate(evalset.items, start=1):
        if log is not None:
            log(f"item {i}/{len(evalset.items)} {item.id!r} …")
        ex = await run_single_item(
            item,
            settings=settings,
            compile_llm=compile_llm,
            executor_llm=executor_llm,
            structural_only=structural_only,
            executor_temperature=temp,
        )
        examples.append(ex)

    model_c = settings.resolved_model()
    model_e = model_c if executor_llm is not None else None
    return SuiteReport(
        evalset_version=evalset.manifest.version,
        evalset_dir=str(evalset.source_dir),
        structural_only=structural_only,
        model_compile=model_c,
        model_executor=model_e,
        examples=examples,
    )
