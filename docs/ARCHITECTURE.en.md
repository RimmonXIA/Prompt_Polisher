# Prompt Polisher — Architecture Bridge

**Canonical source:** All normative theory, evidence grades, limits, and the full reference map reside in **[THEORY.zh.md](THEORY.zh.md)** (Chinese). This document serves as a focused English bridge for international readers to understand the architectural philosophy and system boundaries.

---

## 1. Core Philosophy & Strict Boundaries

Prompt engineering is treated as **structured intervention** on (at least) **attention**, **test-time compute** (tokens, CoT-style scaffolding), **output distributions / decoding**, and **safety boundaries** — not as a one-shot paraphrase.

### What this project claims

The codebase implements a **multi-stage LangGraph workflow**: Intent Sniffer → optional **Safety Gate** → Compute-Aware Router → Structured Compiler → Red-Team Critic (with optional PRM-style gating) → Artifact Dispatcher.

### Limits and non-claims

- **No universal security guarantee:** Templates, XML fences, and heuristic critics are **not** a substitute for threat modeling, monitoring, and organizational controls.
- **No formal assurance:** Do not use this tool as the *sole* defense in regulated, high-stakes environments (finance, health, legal) where you need formal, auditable correctness guarantees.
- **No constrained decoding in-process:** If you need grammar/logit masking, implement a decoder stack downstream; this repo emits **text artifacts only** and does not embed Outlines-like engines.
- **Model-dependent:** Behavior of tags, tools, and masks inherently depends on the provider, model version, and your downstream API configuration.

---

## 2. Architecture & Persona Discipline

To prevent the most common failure mode in complex prompts—"Identity Loops" (where the LLM confuses the user's intent, the system's instructions, and its own persona)—the system strictly enforces a role taxonomy:

1. **Invoker**: The human or automated agent making the request to the CLI/API.
2. **Author**: The creator of the `raw_prompt` (tracked for trust policies).
3. **Orchestrator (Prompt Polisher)**: The LangGraph compilation pipeline. It acts as an *architectural analyst* and speaks strictly in the neutral third person regarding the prompt. It NEVER role-plays as the final assistant.
4. **Inference Engine**: The compute provider executing our internal nodes via our in-house Provider Adapter Registry (OpenAI-compatible, Anthropic, Gemini adapters).
5. **Target (Executor)**: The downstream model that will eventually receive and execute the `final_prompt`.

### The Persona Discipline

The compiler enforces a strict pronoun register within the generated draft to maintain isolation:

- **Task Context**: Uses **impersonal third-person** analysis (e.g., "This task requires...") to brief the Target without leaking the Orchestrator's internal voice.
- **Direct Instructions**: Uses **second-person imperative** for the Target (e.g., "You are...", "You must...").
- **Orchestrator Invisibility**: The pipeline's private reasoning is strictly forbidden in the final artifact. If the Orchestrator persona leaks (e.g., "As the compiler, I..."), it is treated as a severe fault.

---

## 3. The Compilation Pipeline

The multi-agent workflow executed by the Orchestrator follows a discrete 6-step path:

1. **Intent Sniffer** — Performs intent decomposition, assesses alignment/injection risks, and merges JSON-shaped analysis into the global graph state.
2. **Safety Gate** — Config-driven early abort. If the Sniffer detects severe threats, compilation stops.
3. **Compute-Aware Router** — Recommends multi-node structures, evaluates complexity, and anchors personas/styles.
4. **Structured Compiler** — Assembles the `compiler_draft` utilizing XML sandboxing, positional emphasis (first/last), and the `<task_context>` scaffolding.
5. **Red-Team Critic** — Validates the draft against Persona Discipline and rule constraints. *(Example: The Critic will fail the draft and loop back if it detects the Orchestrator speaking in the first-person).*
6. **Artifact Dispatcher** — Formats final delivery for text output, LangGraph blueprints, and DSPy sketches.

### Inside the Intent Sniffer (JSON Analysis)

The Sniffer generates crucial metadata (provider-dependent) that guides the rest of the compilation:


| Field               | Short meaning                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------ |
| `negations_flipped` | Restatement of user intent with negative constraints translated to positive actions.       |
| `threats`           | List of heuristic threat tags from the model (e.g., injection signals); feeds gate policy. |
| `alignment_risk`    | Coarse label (`low`/`medium`/`high`) to determine structural caution.                      |
| `summary`           | Natural-language intent summary; may be appended to gate `abort_detail`.                   |


---

## 4. Theoretical Scope & Implementation Map

Prompt Polisher maps established empirical LLM research to actionable codebase interventions. 


| Theoretical Concern                                           | Implemented via (In this repo)                                                                         | Out of scope (Mostly elsewhere)                       |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| **Input / Attention** (Negation failures, lost-in-the-middle) | Intent Sniffer positive framing; conditional first/last emphasis hints in compile prompts.             | Full RULER-style long-context reproduction.           |
| **Test-time Compute** (Single-shot under-powering)            | `<task_context>` scaffolding; ICL (In-Context Learning) formatting injected into the `compiler_draft`. | Multi-sample executors; universal ICL conclusions.    |
| **Sampling & Formatting** (Parsing faults)                    | Native `response_format={"type": "json_schema"}` used internally by the router/compiler.               | Outlines-style FSM constrained decoding.              |
| **Closed Loop Search** (Error amplification)                  | Red-Team Critic loop (`MAX_CRITIC_ITERATIONS`); optional scalar gate.                                  | Full verifier-guided tree search stacks.              |
| **Manifold / Style** (Vague, "average" outputs)               | `anchor_persona` injection; vocabulary elevation heuristics.                                           | Measurable geometric "projection".                    |
| **Alignment / Adversarial** (Over-refusal, jailbreaks)        | Sniffer `alignment_risk` labeling; XML sandboxing; Gate policies.                                      | CaMeL-style isolation; adaptive attack benchmarks.    |
| **Automation & Optimization** (Manual tuning cost)            | Blueprint delivery; DSPy text sketches.                                                                | Trainable soft prompts; full DSPy optimization loops. |


---

## 5. Ecosystem & References

### Related Work

- **[DSPy](https://github.com/stanfordnlp/dspy)** — Declarative LM pipelines; Prompt Polisher emits a **text sketch** toward that direction but does not run DSPy training loops.
- **Process Reward Models (PRM)** — The optional `CRITIC_USE_PRM` path is a lightweight, heuristic nod to process-level scoring, not a formally trained PRM.
- **Red-Teaming Loops** — Similar in spirit to reflexion-style patterns, but bounded by discrete text rewrites and strict iteration caps.
- **[LangGraph](https://github.com/langchain-ai/langgraph)** — The orchestration layer powering our state machine.

### Primary References


| Topic                        | Pointer                                                                                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Long-context U-shape         | Liu et al., [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/)                                                                |
| Style mirroring / Mimesis    | Jain et al., [arXiv:2509.12517](https://arxiv.org/abs/2509.12517)                                                                        |
| Next-token prediction (TPG)  | Li et al., [PMLR v238](https://proceedings.mlr.press/v238/li24f/li24f.pdf)                                                               |
| RULER-style length           | Hsieh et al., [arXiv:2404.06654](https://arxiv.org/abs/2404.06654)                                                                       |
| RAG positional bias re-check | Cuconasu et al., [arXiv:2505.15561](https://arxiv.org/abs/2505.15561)                                                                    |
| Chain-of-thought             | Wei et al., [arXiv:2201.11903](https://arxiv.org/abs/2201.11903)                                                                         |
| Self-consistency             | Wang et al., [arXiv:2203.11171](https://arxiv.org/abs/2203.11171)                                                                        |
| Test-time compute            | Snell et al., [arXiv:2408.03314](https://arxiv.org/abs/2408.03314); Agarwal et al., [arXiv:2512.02008](https://arxiv.org/abs/2512.02008) |
| ICL / linear models          | Akyürek et al., [arXiv:2211.15661](https://arxiv.org/abs/2211.15661)                                                                     |
| DSPy                         | Khattab et al., [arXiv:2310.03714](https://arxiv.org/abs/2310.03714)                                                                     |
| Constrained decoding         | [Outlines](https://github.com/dottxt-ai/outlines)                                                                                        |
| Prompt injection (taxonomy)  | [OWASP LLM01:2025](https://genai.owasp.org/llmrisk/llm01/)                                                                               |
| Adaptive attacks on defenses | Nasr et al., [arXiv:2510.09023](https://arxiv.org/abs/2510.09023)                                                                        |


---

**One-line takeaway:** Prompt Polisher is a **staged, auditable compiler-shaped workflow** over black-box LMs, characterized by explicit **scope definitions** and **epistemic humility**. For deeper mechanistic depth, read **[THEORY.zh.md](THEORY.zh.md)**.