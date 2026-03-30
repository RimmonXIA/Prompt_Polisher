"""Terminal UX layer using rich — beautiful orientation, spinners, and frames.

All output goes to *stderr* and degrades gracefully when unstyled.
"""

from __future__ import annotations

import sys
import time
from typing import Any, TextIO

from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.text import Text

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

# ── Session-level renderer ─────────────────────────────────────────────────────

class SessionRenderer:
    """Tracks node events across a full compiler run and drives rich UX."""

    def __init__(self, raw_prompt: str, version: str, *, stream: TextIO = sys.stderr) -> None:
        self._console = Console(file=stream, highlight=False)
        self._raw_prompt = raw_prompt
        self._version = version
        
        self._current_status: Status | None = None
        self._node_start_time: float = 0.0
        self._node_counts: dict[str, int] = {}
        self._started_at: float = time.monotonic()

        self._print_splash()

    def _print_splash(self) -> None:
        title = Text.assemble(("✦ Prompt Polisher ", "bold magenta"), (f"v{self._version}", "dim"))
        preview = self._raw_prompt.replace("\n", " ").strip()
        if len(preview) > 65:
            preview = preview[:62] + "..."
        
        panel = Panel(
            Text(preview, style="white"),
            title=title,
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        )
        self._console.print(panel)
        self._console.print()  # empty line spacing

    def on_node_start(self, node_name: str) -> None:
        self._node_start_time = time.monotonic()
        count = self._node_counts.get(node_name, 0)
        self._node_counts[node_name] = count + 1
        
        emoji = _NODE_EMOJI.get(node_name, "⚙️")
        base_msg = NODE_MESSAGES.get(node_name, node_name)
        
        self._current_status = self._console.status(f"[cyan]{emoji}  {base_msg}...[/cyan]", spinner="dots")
        self._current_status.start()

    def on_node_done(self, node_name: str, *, event: dict[str, Any] | None = None, next_node: str | None = None) -> None:
        if self._current_status is None:
            return

        elapsed = time.monotonic() - self._node_start_time
        
        # Stop spinner to replace with a permanent line
        self._current_status.stop()
        self._current_status = None

        base_msg = NODE_MESSAGES.get(node_name, node_name)

        if node_name == "critic" and self._node_counts.get("critic", 0) > 1:
            retry_n = self._node_counts["critic"] - 1
            self._console.print(f"[yellow]⚠️  审查未通过，触发第 {retry_n} 次自我修复回炉[/yellow] [dim]({elapsed:.1f}s)[/dim]")
            if event and "critic_feedback" in event and not event.get("critic_passed"):
                feedback = str(event["critic_feedback"]).strip().split('\n')[0]
                if len(feedback) > 60:
                    feedback = feedback[:57] + "..."
                self._console.print(f"    [dim]└──[/dim] [yellow]⚖️ 蓝军驳回意见：{feedback}[/yellow]")
        elif node_name == "early_abort":
            self._console.print("[red]🚨 安全闸门触发 — 编译已中止[/red]")
        else:
            self._console.print(f"[green]✅[/green] {base_msg} [dim]({elapsed:.1f}s)[/dim]")
            
            if event:
                if node_name == "radar" and "radar_analysis" in event:
                    raw_analysis = event["radar_analysis"]
                    if isinstance(raw_analysis, dict):
                        summary = str(raw_analysis.get("summary", "")).strip().split('\n')[0]
                        if summary:
                            if len(summary) > 75:
                                summary = summary[:72] + "..."
                            self._console.print(f"    [dim]└── 💡 识别痛点：{summary}[/dim]")
                elif node_name == "routing" and "routing_decision" in event:
                    raw_routing = event["routing_decision"]
                    if isinstance(raw_routing, dict):
                        rationale = str(raw_routing.get("rationale", "")).strip().split('\n')[0]
                        if rationale:
                            if len(rationale) > 75:
                                rationale = rationale[:72] + "..."
                            self._console.print(f"    [dim]└── 🧭 路由策略：{rationale}[/dim]")

    def interrupt(self) -> None:
        """Called when KeyboardInterrupt is caught."""
        if self._current_status:
            self._current_status.stop()
            self._current_status = None
        self._console.print("\n[bold red]🚨 流程被用户中断 (Ctrl+C)[/bold red]\n")

    def finish(self, *, elapsed: float, was_aborted: bool = False) -> None:
        if self._current_status is not None:
            self._current_status.stop()
            self._current_status = None
            
        if was_aborted:
            self._console.print(f"\n[red]🚫 编译流程已中止 (历时 {elapsed:.1f}s)[/red]\n")
        else:
            critic_iters = self._node_counts.get("critic", 0)
            correction_note = f"，历经 {critic_iters} 次蓝军自检" if critic_iters > 1 else ""
            self._console.print(f"\n[bold green]✨ 提示词编译完成 (历时 {elapsed:.1f}s{correction_note})[/bold green]\n")

    def print_result_header(self) -> None:
        """Prints the top boundary of the result block before stdout writes the payload."""
        msg = "[bold cyan]╭─ Final Compiled Prompt " + "─" * 42 + "[/bold cyan]"
        self._console.print(msg)

    def print_result_footer(self) -> None:
        """Prints the bottom boundary of the result block after stdout finishes the payload."""
        msg = "[bold cyan]╰─" + "─" * 64 + "[/bold cyan]\n"
        self._console.print(msg)
