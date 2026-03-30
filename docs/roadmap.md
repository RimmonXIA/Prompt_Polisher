# Prompt Polisher: Roadmap

Following the core implementation and architectural audit, the next phase of evolution focuses on moving from a **static heuristic compiler** to a **data-driven adaptive system**.

## 1. Automated Evaluation Pipeline (Benchmark-Driven)
- **Goal**: Move beyond "expert intuition" (THEORY.zh.md) to objective performance metrics.
- **Action**: Integrate a `Metric` system (inspired by DSPy) to run A/B tests: `Compiled Prompt` vs `Raw Prompt` across diverse datasets (e.g., RULER for long context, or custom adversarial sets).
- **Impact**: Provides quantitative proof of compilation value (e.g., "15% improvement in instruction following") rather than relying on theoretical alignment.

## 2. Model-Aware Dynamic Routing (Heterogeneous Awareness)
- **Goal**: Adaptation to Reasoning Models (OpenAI o1, DeepSeek-R1) vs. standard models.
- **Action**: Evolve the `Routing` node to detect the downstream LLM architecture. If a reasoning model is detected, switch to "Intent Distillation" (stripping CoT prompts); for standard models, remain in "Structural Compilation".
- **Impact**: Avoids the "performance degradation" caused by feeding human-written CoT prompts into models that possess native RL-based reasoning chains.

## 3. Dynamic Threat Intelligence (Red-Teaming CI)
- **Goal**: Keep the `Threat Gate` resilient against evolving jailbreak techniques (e.g., GCG attacks).
- **Action**: Implement an automated Red-Teaming loop that periodically scrapes and tests the system against the latest jailbreak datasets (e.g., from `llm-attacks.org`).
- **Impact**: Transforms the "Static Defense" (Regex/Radar) into a "Continuous Immunity System" that evolves with the threat landscape.

---
> **Philosophy**: The goal is not to preserve static rules, but to build a middleware that can effectively **test, falsify, and reconstruct** those rules as models evolve.
