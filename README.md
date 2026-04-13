# Prompt Polisher: The Compiler for LLM Prompts

[![CI](https://github.com/RimmonXIA/Prompt_Polisher/actions/workflows/ci.yml/badge.svg)](https://github.com/RimmonXIA/Prompt_Polisher/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![A2A Compliant](https://img.shields.io/badge/A2A-Compliant-success.svg)](https://github.com/a2aproject/A2A)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

🌐 English | [简体中文](./README.zh.md)

A **multi-node LangGraph compiler** that turns rough intent into structured, safe, and high-performance instructions. Built for prompt engineers and autonomous agents.

---

## 🚀 Why Prompt Polisher?

Most prompts fail because they lack structure, trigger negative constraints, or exhaust the model's single-pass reasoning limit. **Prompt Polisher** treats prompt engineering as a **structured intervention** on attention, compute, and safety:

- 🎯 **Attention Management**: Combats "Lost in the Middle" by reinforcing instructions at **Head/Tail** positions and applying **Anchor Persona** (manifold addressing) to stabilize style and detail.
- 🛡️ **Built-in Safety**: A **heuristic pre-scan** augments a model-based **Intent Sniffer (Radar)** for injections and alignment signals. Uses **XML Sandboxing** for isolation and optional **PRM-style scalar gating** for process-level quality control (heuristics, not a formal guarantee).
- ⚙️ **Compute-Optimized**: Injects `<task_context>` blocks and ICL few-shots to trade sequence length for reasoning quality. Uses **Positive Framing** (Radar-driven negation flipping) to neutralize instruction failure.
- 🎨 **Style Mirroring Intervention**: Detects low-entropy inputs (Perspective Mimesis) and actively intervenes via **Vocabulary Elevation** and **Structural Priming** to ensure the target model mirrors expert-level cognitive standards.
- 🤖 **Multi-track & A2A Native**: Emits prompts, **LangGraph blueprints**, and **DSPy sketches** for automation. The sketches align with in-repo declarative signatures ([`DraftCompile` / `DraftCritic`](src/prompt_polisher/compiler_dspy.py)); full DSPy optimization loops are out of scope. Designed as a tool protocol (JSON envelope) and a spec-compliant **A2A Participant** with JSON-RPC and SSE support.
- 🔌 **Provider-agnostic compilation**: Internal graph calls go through **LiteLLM** ([`llm.py`](src/prompt_polisher/llm.py))—one configuration surface for OpenAI, Anthropic, Gemini, DeepSeek, and many other backends.
- 📐 **Schema-guided node I/O**: Radar, routing, and related steps request **JSON shaped by Pydantic schemas** (schema text in the prompt, then validation and tolerant parsing). Radar **falls back safely** when the model returns invalid JSON; this complements—but does not replace—API-level structured decoding in your own stack.

---

## 🏗️ Architecture & Entities

To ensure robust prompt compilation without role-confusion interventions, Prompt Polisher distinguishes five core entities:
1. **Invoker**: Triggers the compilation request.
2. **Author**: Provides the initial `raw_prompt` intent.
3. **Orchestrator**: The LangGraph engine acting as an architectural analyst.
4. **Inference Engine (LLM)**: Executes the internal compilation graph.
5. **Target (Executor)**: The downstream model running the polished result.

The orchestrator (this compiler) acts as an analyst: it **does not role-play** as the final assistant that will execute the polished prompt. That separation reduces identity drift and “compiler as chatbot” confusion—see the [English theory bridge](docs/THEORY.en.md) for the full role taxonomy.

---

## 🗺️ Workflow Architecture

```mermaid
graph LR
    classDef node fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef critic fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    classDef gate fill:#ffebee,stroke:#c62828,stroke-width:2px;
    classDef output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    subgraph A2A_Interface [A2A Protocol Interface]
        direction LR
        Discovery([/.well-known/agent-card.json])
        JSONRPC[POST /a2a/v1 JSON-RPC]
    end

    Raw([Raw Input]) --> JSONRPC
    JSONRPC --> Sniffer[Node 1: Intent Sniffer]
    Sniffer --> Gate{Safety Gate}
    Gate -->|Abort| Stop([Early Abort])
    Gate -->|Pass| Router[Node 2: Compute-Aware Router]
    Router --> Compiler[Node 3: Structured Compiler]
    Compiler --> Critic[Node 4: Red-Team Critic]
    Critic -->|Retry| Compiler
    Critic -->|Pass| Dispatcher[Artifact Dispatcher]
    Dispatcher --> Final([Final Product])

    class Sniffer,Router,Compiler node;
    class Critic critic;
    class Gate gate;
    class Stop,Final output;
    class Discovery,JSONRPC output;
```

---

## ⚡ Quickstart

### 1. Setup
```bash
# Sync dependencies
uv sync --all-groups

# Configure environment
cp .env.example .env   # Edit API keys (OpenAI, DeepSeek, Claude, Gemini, etc.)
```

### 2. Usage
```bash
# Basic: Get the compiled prompt
uv run prompt-polisher "Summarize this repo for a release note"

# Professional: Get a Markdown report with full audit trail
uv run prompt-polisher -m "Your requirement"

# Agent-Ready: Output as a versioned JSON envelope
uv run prompt-polisher --envelope "Your requirement"

# Service Mode: Launch A2A HTTP Server
uv run prompt-polisher --serve --port 8000
```

### 3. Example reports & library use

- **Sample outputs**: [examples/](examples/README.md) covers a normal run, a **threat-gate abort**, and a **multi-node routing** hint (`01_happy_path`, `02_aborted_gate`, `03_multi_node_hint`).
- **Embed in Python**: Call [`run_compiler_async`](src/prompt_polisher/graph.py) with your `Settings` and [`LLMClient`](src/prompt_polisher/llm.py). Optional `on_node_start` / `on_node_done` callbacks receive each graph node’s name and update dict (the CLI uses this for progress). Code-accurate sequence and state flow: **[docs/CLI_INVOCATION_FLOW.md](docs/CLI_INVOCATION_FLOW.md)**.

---

## 🛠️ Developer & Automation Guide

### CLI as Tool Protocol
For scripts and coding agents (Cursor, Windsurf, custom workers), treat the CLI as a protocol:
- **stdout**: Carries the primary payload (Text, Markdown, or JSON).
- **stderr**: Carries logs and diagnostic info (use `--quiet` to minimize noise).
- **Interactive TTY** (human mode, not `--envelope` / agent JSON on stdout): stderr prints a Rich splash panel with a **terminal-width-aware** preview of your input (up to four **logical** lines of text, plus a dim **stats** line).
  - Stats include **character count** and **logical line count** (newline-separated segments in the input). That count is **not** the number of **wrapped rows** Rich draws inside the panel; long lines wrap, so the panel can look taller than the line count (especially with **`-v` / `--verbose`**, which shows the **full** input in the panel).
  - With **`-f` / `--file`**, the stats line can start with **`source:`** plus the file basename (for example `notes.md`).
  - If the bounded preview omits content, stats include **`preview truncated`**.
  - **`-v` / `--verbose`** also enables noisier HTTP client logging on stderr (httpx/httpcore INFO).

#### Exit Codes (Stable for Automation)

| Code | Meaning |
| --- | --- |
| `0` | Success: Compilation finished without being aborted by the threat gate. |
| `2` | Aborted: Run finished but compilation was stopped by the threat gate. |
| `1` | Error: Misconfiguration, I/O failure, or invalid CLI usage. |

#### Envelope Shape (`--envelope`)

The standard JSON envelope includes:
- `compiled`: `true` if and only if the threat gate did not abort.
- `version`: Currently `1`.
- `report`: The full compilation report (**intent_sniffer**, **compute_aware_router**, **red_team_critic**, deliverables).
- `abort_reason`: `null` on success, or an object with `code`, `message`, and `detail`.

### Implementation Mapping (Theory → Code)

| Node | Primary Implementation |
| --- | --- |
| **Node 1: Intent Sniffer** | [`src/prompt_polisher/nodes.py`](src/prompt_polisher/nodes.py) (`node_intent_sniffer`) |
| **Safety Gate** | [`src/prompt_polisher/gate.py`](src/prompt_polisher/gate.py) |
| **Node 2: Compute-Aware Router** | `nodes.py` (`node_compute_aware_router`) |
| **Node 3: Structured Compiler** | `nodes.py` (`node_structured_compiler`) |
| **Node 4: Red-Team Critic** | `nodes.py` (`node_red_team_critic`) |
| **Artifact Dispatcher** | `nodes.py` (`node_artifact_dispatcher`) |
| **Global State** | [`src/prompt_polisher/state.py`](src/prompt_polisher/state.py) |
| **Interactive stderr UX** (splash, spinners) | [`src/prompt_polisher/ux.py`](src/prompt_polisher/ux.py) (`SessionRenderer`) |
| **Eval harness** | [`src/prompt_polisher/eval/`](src/prompt_polisher/eval/), [`evalsets/bundled/`](evalsets/bundled/README.md) |

**CI quality bar**: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs **Ruff**, **Mypy**, and **pytest** on **Python 3.11 and 3.12**.

### CLI invocation flow (Mermaid reference)

Code-accurate sequence and flow diagrams for `uv run prompt-polisher`: CLI bootstrap, LangGraph edges, [`prompts/`](src/prompt_polisher/prompts/) via [`prompts_bundle.py`](src/prompt_polisher/prompts_bundle.py), stdout/stderr modes, and `GraphState` updates — see **[docs/CLI_INVOCATION_FLOW.md](docs/CLI_INVOCATION_FLOW.md)**.

### Evaluation harness

Versioned tasks under `evalsets/bundled/` with **Tier A** structural checks (compile graph only) and optional **Tier B** paired **Raw vs Compiled** executor scoring where `gold` is set in `items.jsonl`.

```bash
# Rich CLI reference (tiers, discovery, exit codes, examples)
uv run prompt-polisher-eval --help

# No extra executor LLM calls — suitable for fast regression checks
uv run prompt-polisher-eval --structural-only --fail-on-structural

# Full run: Tier B uses the same API as compilation (extra cost)
uv run prompt-polisher-eval --output eval-report.json
```

Override directory with `PROMPT_POLISHER_EVALSET` or `--evalset-dir`. Details: [`evalsets/bundled/README.md`](evalsets/bundled/README.md). Optional CI: [`.github/workflows/eval-live.yml`](.github/workflows/eval-live.yml).


> [!TIP]
> Set `PROMPT_POLISHER_AGENT=1` in your environment to default to `--envelope` output for all calls.

### Configuration
Key settings in your `.env`:
- `LLM_PROVIDER`: `openai` (default), `deepseek`, `anthropic`, `google`, `zhipu`, `aliyun`, etc.
- `LLM_MODEL`: The target model name (e.g., `gpt-4o-mini`, `claude-3-5-sonnet-20240620`, `gemini/gemini-1.5-pro`).
- `LLM_API_KEY`: Universal API key. Still supports `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, etc., for backward compatibility.
- `AUTHOR_TRUST_MODE`: Set to `true` to disable strict safety gates for known authors.
- `MAX_CRITIC_ITERATIONS`: Control the feedback loop depth (default: 3).
- `CRITIC_USE_PRM`: Enable optional scalar-based process reward gating (heuristic).
- `PRM_MODEL`: Optional model override for the built-in LLM PRM path when `CRITIC_USE_PRM` is on (defaults follow the same resolution rules as the main compiler model when unset).
- `PRM_MIN_SCORE`: Minimum PRM score in `[0, 1]` to pass the gate (default: `0.45`).
- `EXTERNAL_PRM_ENDPOINT`: Optional URL for a **bring-your-own** process scorer. The client `POST`s JSON `{"draft": "...", "intent": "..."}` and expects JSON with a numeric `score` and optional `note`; see [`prm.py`](src/prompt_polisher/prm.py). When set, this is tried **before** the built-in LLM PRM call.
- **Langfuse** (optional tracing): Set `LANGFUSE_TRACING=true` plus `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (optional `LANGFUSE_BASE_URL`). Install with `uv sync --extra langfuse`; verify connectivity with `uv run prompt-polisher-langfuse-check`.

### Scope & non-claims

Prompt Polisher is a **staged, auditable compiler-shaped workflow** over black-box language models. It does **not** guarantee downstream task success, formal safety certifications, or universally optimal prompts across models and deployments. **Intent sniffer**, **safety gates**, and **critics** are **heuristic**; they complement—but do not replace—system design, monitoring, and task-specific benchmarks. For explicit limits and when **not** to rely on this tool alone, read **[docs/THEORY.en.md](docs/THEORY.en.md)**.

> [!IMPORTANT]
> **Implementation scope**: Prompt Polisher emits **text artifacts only**. It does not perform constrained decoding (logits masking) or sampling within the tool; configure those in your downstream decoder/API client. The internal `<task_context>` tag is reserved for Orchestrator-to-Executor briefings and is sanitized from Author inputs.

---

## 🤝 A2A Integration

Prompt Polisher is a [Full A2A Participant](https://github.com/a2aproject/A2A) (Agent-to-Agent Protocol).

- **Discovery**: `uv run prompt-polisher --agent-card` or `GET /.well-known/agent-card.json`
- **A2A Server**: `uv run prompt-polisher --serve --port 8000`
- **Service API**: JSON-RPC 2.0 endpoints for `SendMessage`, `GetTask`, `ListTasks`, and `SendStreamingMessage` (SSE).
- **Compliance Status**: Full A2A participant implementation (live protocol features).

---

## 📖 Deep Dives & Theory

| Language | Artifact | Scope |
| --- | --- | --- |
| **Chinese (Canonical)** | [docs/THEORY.zh.md](docs/THEORY.zh.md) | **Source of Truth**: Full architecture, evidence grades, and theory map. |
| **English (Summary)** | [docs/THEORY.en.md](docs/THEORY.en.md) | **Bridge**: Scope, non-claims, and architectural overview for international teams. |
| **English (Operational)** | [docs/CLI_INVOCATION_FLOW.md](docs/CLI_INVOCATION_FLOW.md) | **Implementation map**: Mermaid views of CLI → graph → API, prompt file wiring, outputs, and `GraphState` fields. |

---

**Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md).  
**Security:** see [SECURITY.md](SECURITY.md).  
**Code of Conduct:** [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
