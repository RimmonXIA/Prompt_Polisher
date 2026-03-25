from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from string import Template
from typing import Final

from prompt_polisher.config import Settings

_PROMPTS_SUBDIR: Final = "prompts"


def _read_builtin(name: str) -> str:
    root = resources.files("prompt_polisher") / _PROMPTS_SUBDIR
    return root.joinpath(name).read_text(encoding="utf-8")


def _load_text(name: str, override_dir: Path | None) -> str:
    if override_dir is not None:
        candidate = override_dir / name
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return _read_builtin(name)


class PromptBundle:
    """Loads `.txt` prompts from package data, with optional directory override per file."""

    __slots__ = (
        "_radar_base",
        "_radar_trusted",
        "_radar_untrusted",
        "_routing_base",
        "_routing_trusted",
        "_routing_untrusted",
        "_compile_base",
        "_compile_trusted",
        "_compile_untrusted",
        "_critic_base",
        "_critic_trusted",
        "_critic_untrusted",
        "_router_base",
        "_router_trusted",
        "_router_untrusted",
        "_radar_user",
        "_routing_user",
        "_critic_user",
        "_gate_abort_user",
        "_gate_abort_wf",
        "_router_fallback_wf",
        "_router_fallback_dspy",
    )

    def __init__(self, override_dir: Path | None) -> None:
        def load(name: str) -> str:
            return _load_text(name, override_dir)

        self._radar_base = load("radar_system_base.txt")
        self._radar_trusted = load("radar_system_trusted.txt")
        self._radar_untrusted = load("radar_system_untrusted.txt")
        self._routing_base = load("routing_system_base.txt")
        self._routing_trusted = load("routing_system_trusted.txt")
        self._routing_untrusted = load("routing_system_untrusted.txt")
        self._compile_base = load("compile_system_base.txt")
        self._compile_trusted = load("compile_system_trusted.txt")
        self._compile_untrusted = load("compile_system_untrusted.txt")
        self._critic_base = load("critic_system_base.txt")
        self._critic_trusted = load("critic_system_trusted.txt")
        self._critic_untrusted = load("critic_system_untrusted.txt")
        self._router_base = load("router_system_base.txt")
        self._router_trusted = load("router_system_trusted.txt")
        self._router_untrusted = load("router_system_untrusted.txt")
        self._radar_user = Template(load("radar_user.txt"))
        self._routing_user = Template(load("routing_user.txt"))
        self._critic_user = Template(load("critic_user.txt"))
        self._gate_abort_user = Template(load("gate_abort_user_message.txt"))
        self._gate_abort_wf = load("gate_abort_workflow_blueprint.txt")
        self._router_fallback_wf = Template(load("router_fallback_workflow.txt"))
        self._router_fallback_dspy = load("router_fallback_dspy.txt")

    def radar_system(self, author_trust_mode: bool) -> str:
        trust = self._radar_trusted if author_trust_mode else self._radar_untrusted
        return self._radar_base + trust

    def routing_system(self, author_trust_mode: bool) -> str:
        trust = self._routing_trusted if author_trust_mode else self._routing_untrusted
        return self._routing_base + trust

    def compile_system(self, author_trust_mode: bool) -> str:
        trust = self._compile_trusted if author_trust_mode else self._compile_untrusted
        return self._compile_base + trust

    def critic_system(self, author_trust_mode: bool) -> str:
        trust = self._critic_trusted if author_trust_mode else self._critic_untrusted
        return self._critic_base + trust

    def router_system(self, author_trust_mode: bool) -> str:
        trust = self._router_trusted if author_trust_mode else self._router_untrusted
        return self._router_base + trust

    def radar_user(self, raw: str, heuristic_injection: bool) -> str:
        return self._radar_user.substitute(raw=raw, heuristic_injection=heuristic_injection)

    def routing_user(self, radar_json: str, original: str) -> str:
        return self._routing_user.substitute(radar_json=radar_json, original=original)

    def critic_user(self, draft: str, original_intent: str) -> str:
        return self._critic_user.substitute(draft=draft, original_intent=original_intent)

    def gate_abort_user_message(self, reason: str) -> str:
        return self._gate_abort_user.substitute(reason=reason)

    def gate_abort_workflow_blueprint(self) -> str:
        return self._gate_abort_wf

    def router_fallback_workflow(self, route: str) -> str:
        return self._router_fallback_wf.substitute(route=route)

    def router_fallback_dspy(self) -> str:
        return self._router_fallback_dspy


@lru_cache(maxsize=16)
def _cached_bundle(prompts_dir_resolved: str) -> PromptBundle:
    override = Path(prompts_dir_resolved) if prompts_dir_resolved else None
    return PromptBundle(override)


def prompt_bundle(settings: Settings) -> PromptBundle:
    key = str(settings.prompts_dir.resolve()) if settings.prompts_dir is not None else ""
    return _cached_bundle(key)


def clear_prompt_bundle_cache() -> None:
    """For tests or reload after changing files under PROMPTS_DIR."""
    _cached_bundle.cache_clear()
