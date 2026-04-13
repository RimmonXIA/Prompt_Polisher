from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class StructuralExpect(BaseModel):
    """Optional expectations on graph output for Tier A regression checks."""

    compilation_aborted: bool | None = None
    red_team_critic_passed: bool | None = None
    final_prompt_nonempty: bool | None = None


GoldType = Literal["none", "exact_match", "contains_all", "json_keys"]


class GoldSpec(BaseModel):
    """Tier B: score executor output against a reference."""

    type: GoldType = "none"
    value: str = ""
    values: list[str] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    key_values: dict[str, Any] = Field(default_factory=dict)

    @field_validator("values", mode="before")
    @classmethod
    def _coerce_values(cls, v: object) -> object:
        if v is None:
            return []
        return v


class EvalItem(BaseModel):
    """One eval example: user intent, optional structural checks, optional outcome gold."""

    id: str
    user_intent: str
    tags: list[str] = Field(default_factory=list)
    structural_expect: StructuralExpect | None = None
    gold: GoldSpec = Field(default_factory=lambda: GoldSpec(type="none"))
    executor_system: str | None = None
