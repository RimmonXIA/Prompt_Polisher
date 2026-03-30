"""Terminal UX layer — zero external dependencies.

Provides a lightweight async ANSI spinner and contextual node-to-message
mapping for the human-interactive CLI mode. All output goes to *stderr*
only and is completely silent when stderr is not a TTY or when ANSI
escape codes are unsupported (e.g. Windows cmd without VT mode).
"""

from __future__ import annotations

import asyncio
import sys
import time
from typing import TextIO

# ── ANSI helpers ──────────────────────────────────────────────────────────────

_RESET = "\033[0m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_CLEAR_LINE = "\033[2K"  # erase entire current line


def _ansi_supported(stream: TextIO) -> bool:
    """Return True when the stream is a real TTY that likely honours ANSI."""
    return stream.isatty()


# ── Node → human-readable message map ─────────────────────────────────────────

NODE_MESSAGES: dict[str, str] = {
    "radar": "正在拆解分析指令并进行安全雷达扫描",
    "routing": "正在评估语义复杂度并动态加载处理模型",
    "compile": "正在注入高阶结构约束并执行深度编译",
    "critic": "蓝军机制发起自我审查与对抗检验",
    "router": "正在组装沙盒与最终工作流",
    "early_abort": "安全闸门已触发，提前终止编译流程",
}

_NODE_EMOJI: dict[str, str] = {
    "radar": "🔍",
    "routing": "🧭",
    "compile": "🏗️",
    "critic": "⚖️",
    "router": "📦",
    "early_abort": "🚨",
}

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_INTERVAL = 0.08  # seconds per frame


# ── TerminalSpinner ────────────────────────────────────────────────────────────


class TerminalSpinner:
    """Async ANSI spinner for a single stage. Creates a background task."""

    def __init__(self, message: str, *, stream: TextIO = sys.stderr) -> None:
        self._message = message
        self._stream = stream
        self._active = _ansi_supported(stream)
        self._task: asyncio.Task[None] | None = None
        self._frame_idx = 0

    async def _spin(self) -> None:
        while True:
            frame = _SPINNER_FRAMES[self._frame_idx % len(_SPINNER_FRAMES)]
            self._frame_idx += 1
            self._stream.write(f"\r{_CLEAR_LINE}{_CYAN}{frame}{_RESET} {self._message}")
            self._stream.flush()
            await asyncio.sleep(_SPINNER_INTERVAL)

    def start(self) -> None:
        if self._active:
            self._task = asyncio.get_event_loop().create_task(self._spin())
        else:
            self._stream.write(f"  → {self._message}\n")
            self._stream.flush()

    def _stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def succeed(self, done_message: str | None = None) -> None:
        self._stop()
        if self._active:
            label = done_message or self._message
            self._stream.write(f"\r{_CLEAR_LINE}{_GREEN}✅{_RESET} {label}\n")
            self._stream.flush()

    def warn(self, warn_message: str) -> None:
        """Mark stage as completed-with-warning (used for critic retry)."""
        self._stop()
        if self._active:
            self._stream.write(f"\r{_CLEAR_LINE}{_YELLOW}⚠️  {warn_message}{_RESET}\n")
            self._stream.flush()
        else:
            self._stream.write(f"  ⚠️  {warn_message}\n")
            self._stream.flush()

    def fail(self, fail_message: str | None = None) -> None:
        self._stop()
        label = fail_message or self._message
        self._stream.write(f"\r{_CLEAR_LINE}🚨 {label}\n")
        self._stream.flush()


# ── Session-level renderer ─────────────────────────────────────────────────────


class SessionRenderer:
    """Tracks node events across a full compiler run and drives spinners.

    Usage::

        renderer = SessionRenderer()
        renderer.on_node_start("radar")
        await asyncio.sleep(...)  # while LLM is running
        renderer.on_node_done("radar")
        renderer.finish(elapsed=3.7)
    """

    def __init__(self, *, stream: TextIO = sys.stderr) -> None:
        self._stream = stream
        self._active = _ansi_supported(stream)
        self._current_spinner: TerminalSpinner | None = None
        self._node_counts: dict[str, int] = {}
        self._started_at: float = time.monotonic()

    def on_node_start(self, node_name: str) -> None:
        count = self._node_counts.get(node_name, 0)
        self._node_counts[node_name] = count + 1
        emoji = _NODE_EMOJI.get(node_name, "⚙️")
        base_msg = NODE_MESSAGES.get(node_name, node_name)
        message = f"{emoji}  {base_msg}"
        self._current_spinner = TerminalSpinner(message, stream=self._stream)
        self._current_spinner.start()

    def on_node_done(self, node_name: str, *, next_node: str | None = None) -> None:
        sp = self._current_spinner
        if sp is None:
            return

        # Critic retry detection: if compile or critic fires a 2nd time, surface it.
        if node_name == "critic" and self._node_counts.get("critic", 0) > 1:
            retry_n = self._node_counts["critic"] - 1
            sp.warn(f"审查未通过，触发第 {retry_n} 次自我修复回炉重写...")
        elif node_name == "early_abort":
            sp.fail("安全闸门触发 — 编译已中止")
        else:
            sp.succeed()
        self._current_spinner = None

    def finish(self, *, elapsed: float, was_aborted: bool = False) -> None:
        """Print the final summary line to stderr."""
        if self._current_spinner is not None:
            self._current_spinner.succeed()
            self._current_spinner = None
        if not self._active:
            return
        if was_aborted:
            self._stream.write(f"\n{_YELLOW}🚫 编译流程已中止 (历时 {elapsed:.1f}s){_RESET}\n\n")
        else:
            critic_iters = self._node_counts.get("critic", 0)
            correction_note = f"，历经 {critic_iters} 次蓝军自检" if critic_iters > 1 else ""
            self._stream.write(
                f"\n{_GREEN}✨ 提示词编译完成 (历时 {elapsed:.1f}s{correction_note}){_RESET}\n\n"
            )
        self._stream.flush()
