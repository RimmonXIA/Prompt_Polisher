# Prompt Polisher — English theory bridge

**Canonical source.** All normative theory, evidence grades, limits, and the full reference map remain in **[THEORY.zh.md](THEORY.zh.md)** (Chinese). This document is a **short English bridge** (~10–15 minute read) for recruiters and international readers. If anything disagrees with the Chinese doc, **THEORY.zh.md wins**.

## What this project claims

Prompt engineering is treated as **structured intervention** on (at least) **attention**, **test-time compute** (tokens, CoT-style scaffolding), **output distributions / decoding**, and **safety boundaries** — not as a one-shot paraphrase. The codebase implements a **multi-stage LangGraph workflow**: Radar → optional **ThreatGate** → Routing → Compile → Critic (with optional **PRM-style** scalar gating) → Router.

**Non-claims:** The tool does **not** guarantee task success, formal safety, global optimality, or portability across every model and API. See [Limits and non-claims](#limits-and-non-claims) and [When not to use this tool](#when-not-to-use-this-tool).

## Architecture Taxonomy

To prevent role confusion and "Identity Loops", the system strictly enforces the following entities and data objects:
1. **Invoker**: The user or automated agent making the request to the CLI/API.
2. **Author**: The creator of the `raw_prompt` (often the same as the Invoker, but conceptually distinct for trust/source tracking).
3. **Orchestrator (Prompt Polisher)**: The LangGraph compilation pipeline. It acts as an analyst/architect and speaks in the *third person* regarding the prompt. It NEVER role-plays as the final assistant.
4. **Inference Engine (LLM)**: The raw compute provider executing our internal nodes (Radar, Compile, Critic). It is constrained by the Orchestrator's taxonomy.
5. **Target (Executor)**: The downstream model that will eventually receive and execute the `final_prompt`.

## Pipeline (aligned with code)

1. **Radar** — Intent decomposition, heuristic alignment/injection signals, JSON-shaped analysis merged into graph state.
2. **ThreatGate** — Config-driven early abort after Radar; skips Route, Compile, Critic, and Router when triggered.
3. **Routing** — Complexity and multi-node recommendations; persona / style anchoring (metaphorically “manifold addressing”; **analogy**, not proven geometry).
4. **Compile** — Structured assembly into a `draft`: XML-ish sandboxing, first/last emphasis, optional `<thinking>`-style scaffolding, **§2.5-style ICL/few-shot guidance embedded in the draft text** (not a separate JSON field for ICL).
5. **Critic** — Rule checks first; optional scalar **PRM-like** score before the text critic; FAIL loops back to Compile up to `MAX_CRITIC_ITERATIONS`.
6. **Router** — Text deliverables: final prompt, workflow blueprint, DSPy-style sketch.

**Radar JSON field hints** (keys are **model-dependent**; common examples—see [README.md](../README.md) implementation table):

| Field (often present) | Short meaning |
| --- | --- |
| `negations_flipped` | Restatement of user intent with negations / scope clarified for the model (internal phrasing aid). |
| `threats` | List of heuristic threat tags from the model (e.g. injection signals); gate may use these. |
| `alignment_risk` | Coarse label such as `low` / `medium` / `high`; feeds gate policy. |
| `summary` | Natural-language radar summary; may be appended to gate `abort_detail`. |

The CLI emits **text artifacts only**. **Temperature, top-p, logits masks, constrained decoding** belong to **your downstream decoder** (see implementation scope).

## “Layer” labels in diagrams

Subgraphs labeled **Layer 1–8** in [THEORY.zh.md](THEORY.zh.md) tie the product nodes to a **theory map** (input → compute → sampling → closed loop → anchoring → alignment → automation → adversarial). They are **reading aids**, not separate runtime modules.

## Implementation scope (summary)

| Concern | In this repo | Mostly elsewhere |
| --- | --- | --- |
| §1 Input, U-shape, negation, persona | Radar “positive” framing; conditional first/last / long-context hints in compile prompts | Full RULER-style reproduction; end-to-end RAG re-evaluation |
| §2 CoT, ICL, test-time compute | `<thinking>`-style scaffolding; ICL guidance in `draft`; routing suggests complexity | Multi-sample executors; universal ICL conclusions |
| §3 Logits / sampling | **Not implemented** — CLI outputs text only | Outlines-style constrained decoding |
| §4 Closed loop, PRM | Critic↔Compile loop; optional scalar gate | Full verifier-guided search stacks |
| §5 Anchor / manifold | `anchor_persona` and wording | Measurable geometric “projection” |
| §6 Alignment, over-refusal | Radar `alignment_risk`; gate policies | Deployment-specific RM details |
| §7 Soft prompts, DSPy | `dspy_sketch` text | Trainable soft prompts; runnable DSPy |
| Bundled eval baseline | `evalsets/bundled`, `prompt-polisher-eval` (Tier A structure; optional Tier B paired Raw vs compiled + gold) | Full domain benchmarks; universal claims |
| §8 Injection, jailbreak | Heuristics + Radar JSON; shallow XML rules | CaMeL-style isolation; adaptive attack benchmarks |

## Theory map (compact)

| Full theory (§) | Workflow focus | Typical pain (empirical / analogy) |
| --- | --- | --- |
| §1 Input | Radar, compile context | Negation failures, lost-in-the-middle, persona dilution |
| §2 Compute | Routing, compile | Single-shot under-powering; ICL format alignment |
| §3 Sampling | Router (text only in-repo) | Format reliability; sampling tails |
| §4 Closed loop | Critic | Error amplification along autoregressive chain |
| §5 Manifold (§5.9–§5.10) | Routing anchors, Vocab elevation | Vague, “average” outputs; Style mirroring |
| §6 Alignment | Radar | Over-refusal, alignment tax (term is overloaded) |
| §7 Automation | Blueprint / DSPy sketch | Manual prompt tuning cost |
| §8 Adversarial | Radar + Critic | Injection / jailbreak; **defense needs system design** |

## Limits and non-claims

1. **No weight updates** unless you add fine-tuning yourself; interventions are inference-time context and decoding config.
2. **No universal security guarantee** — templates, XML fences, and critics are **not** a substitute for threat modeling, monitoring, and organizational controls. Strong claims need **adaptive attack**-style evaluation (see §8.13 references in [THEORY.zh.md](THEORY.zh.md)).
3. **Model- and stack-dependent** — Behavior of tags, tools, and masks depends on provider, model version, and decoder.
4. **Evidence grades** in the Chinese doc (**Empirical / Mechanistic / Analogy / Speculation**) apply; sentences not marked Empirical are **not** theorems for all LLMs.
5. **Optional PRM-style score** — Heuristic scalar gating only; **not** formal verification.

## When not to use this tool

- **Regulated or high-stakes assurance** where you need **auditable, formal** safety or correctness guarantees (e.g., some finance, health, or legal workflows) without additional controls.
- **Sole defense** against prompt injection or jailbreaks in agentic / RAG systems — you still need **architecture** (trust boundaries, tool policy, monitoring), not only compiled prompts.
- **Replacing evaluation** — Use explicit benchmarks and human/LLM-judge rubrics for *your* tasks; this CLI does not ship a claim of SOTA on downstream metrics.
- **Constrained decoding in-process** — If you need grammar / logit masking **inside** this package, implement or call a decoder stack downstream; this repo does not embed Outlines-like engines.

## Bundled evaluation harness

The repo includes a **small, versioned** eval set (`evalsets/bundled/`) and the `prompt-polisher-eval` CLI entry point. **Tier A** scores structural expectations on the compile graph (no second LLM). **Tier B** optionally runs a paired **Raw vs Compiled** pass against simple gold checks. Results are **Empirical only** for the pinned model, temperature, and eval version—they do **not** imply universal performance (see *Replacing evaluation* under [When not to use this tool](#when-not-to-use-this-tool)).

## Related work (positioning)

- **[DSPy](https://github.com/stanfordnlp/dspy)** — Declarative LM pipelines and metric-driven optimization; Prompt Polisher emits a **text sketch** toward that direction but does not run DSPy training loops.
- **Process reward models (PRM) / verifiers** — Literature on **process-level** scoring and search at decode time; the optional `CRITIC_USE_PRM` path is a **lightweight, heuristic** nod in that family, not a trained PRM.
- **Red-teaming / critic loops** — Similar in spirit to reflexion-style and critic–generator patterns; here bounded by **discrete text** rewrites and iteration caps.
- **[LangGraph](https://github.com/langchain-ai/langgraph)** — Orchestration layer for the state machine above.

## Primary references (same as Chinese doc, curated)

For the full table and additional rows, see the **参考文献** section at the end of [THEORY.zh.md](THEORY.zh.md).

| Topic | Pointer |
| --- | --- |
| Long-context U-shape | Liu et al., [Lost in the Middle](https://aclanthology.org/2024.tacl-1.9/) |
| Style mirroring / Mimesis | Jain et al., [arXiv:2509.12517](https://arxiv.org/abs/2509.12517) |
| Next-token prediction (TPG) | Li et al., [PMLR v238](https://proceedings.mlr.press/v238/li24f/li24f.pdf) |
| RULER-style length | Hsieh et al., [arXiv:2404.06654](https://arxiv.org/abs/2404.06654) |
| RAG positional bias re-check | Cuconasu et al., [arXiv:2505.15561](https://arxiv.org/abs/2505.15561) |
| Chain-of-thought | Wei et al., [arXiv:2201.11903](https://arxiv.org/abs/2201.11903) |
| Self-consistency | Wang et al., [arXiv:2203.11171](https://arxiv.org/abs/2203.11171) |
| Test-time compute | Snell et al., [arXiv:2408.03314](https://arxiv.org/abs/2408.03314); Agarwal et al., [arXiv:2512.02008](https://arxiv.org/abs/2512.02008) |
| ICL / linear models | Akyürek et al., [arXiv:2211.15661](https://arxiv.org/abs/2211.15661) |
| DSPy | Khattab et al., [arXiv:2310.03714](https://arxiv.org/abs/2310.03714) |
| Constrained decoding | [Outlines](https://github.com/dottxt-ai/outlines) |
| Prompt injection (taxonomy) | [OWASP LLM01:2025](https://genai.owasp.org/llmrisk/llm01/) |
| Adaptive attacks on defenses | Nasr et al., [arXiv:2510.09023](https://arxiv.org/abs/2510.09023) |

---

**One-line takeaway:** Prompt Polisher is a **staged, auditable compiler-shaped workflow** over black-box LMs, with explicit **scope** and **epistemic humility** (evidence grades, non-claims). For depth, read **[THEORY.zh.md](THEORY.zh.md)**.
