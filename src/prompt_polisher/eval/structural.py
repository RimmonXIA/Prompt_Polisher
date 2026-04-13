from __future__ import annotations

from dataclasses import dataclass

from prompt_polisher.eval.schema import EvalItem
from prompt_polisher.state import GraphState


@dataclass(frozen=True)
class StructuralResult:
    compilation_aborted: bool
    red_team_critic_passed: bool | None
    final_prompt_nonempty: bool
    draft_nonempty: bool
    structural_expect_ok: bool | None
    structural_mismatches: list[str]


def compute_structural(state: GraphState, item: EvalItem | None = None) -> StructuralResult:
    """Tier A metrics derived from graph state, optional item-level regression expectations."""
    aborted = bool(state.get("compilation_aborted"))
    critic_raw = state.get("red_team_critic_passed")
    critic = critic_raw if isinstance(critic_raw, bool) else None
    final = str(state.get("final_prompt") or "").strip()
    draft = str(state.get("compiler_draft") or "").strip()
    mismatches: list[str] = []
    expect_ok: bool | None = None

    if item is not None and item.structural_expect is not None:
        exp = item.structural_expect
        if exp.compilation_aborted is not None and exp.compilation_aborted != aborted:
            mismatches.append(
                f"compilation_aborted want {exp.compilation_aborted} got {aborted}",
            )
        if exp.red_team_critic_passed is not None:
            if critic is None:
                mismatches.append("red_team_critic_passed expected but value is missing")
            elif exp.red_team_critic_passed != critic:
                mismatches.append(
                    f"red_team_critic_passed want {exp.red_team_critic_passed} got {critic}"
                )
        if exp.final_prompt_nonempty is not None:
            got_nonempty = bool(final)
            if exp.final_prompt_nonempty != got_nonempty:
                mismatches.append(
                    f"final_prompt_nonempty want {exp.final_prompt_nonempty} got {got_nonempty}",
                )
        expect_ok = not mismatches

    return StructuralResult(
        compilation_aborted=aborted,
        red_team_critic_passed=critic,
        final_prompt_nonempty=bool(final),
        draft_nonempty=bool(draft),
        structural_expect_ok=expect_ok,
        structural_mismatches=mismatches,
    )


def structural_expect_passed(result: StructuralResult) -> bool:
    """True if no structural expectation was violated."""
    if result.structural_expect_ok is None:
        return True
    return result.structural_expect_ok
