# Examples (redacted / synthetic)

These files illustrate **CLI inputs and report shapes**. They are **not** produced by pinning a model snapshot in CI; numbers and long prose are **fabricated or trimmed** for privacy and stability. To reproduce with a real model, run:

```bash
uv run prompt-polisher -m "…your raw text…"
uv run prompt-polisher --envelope "…your raw text…"
```

| Folder | Scenario |
| --- | --- |
| [`01_happy_path/`](01_happy_path/) | Normal completion: radar → route → compile → critic pass → deliverables. See [`01_happy_path/README.md`](01_happy_path/README.md) (sample JSON is **not** a fixed schema contract). |
| [`02_aborted_gate/`](02_aborted_gate/) | ThreatGate abort after radar (no route/compile/critic). |
| [`03_multi_node_hint/`](03_multi_node_hint/) | Routing suggests a multi-step workflow; shorter report excerpt. |
| [`04_fast_path/`](04_fast_path/) | Fast mode envelope v2 sample (`--mode fast`) with runtime and quality signals. |
| [`05_compare_json/`](05_compare_json/) | `prompt-polisher compare --json` sample (structural-only), including compiled runtime signals. |

Suggested commands to reproduce with your own environment:

```bash
uv run prompt-polisher --mode fast --envelope "Summarize this text"
uv run prompt-polisher compare --raw "Answer in JSON" --task-input "Alice is 30" --structural-only --json
```

See also [docs/THEORY.zh.md](../docs/THEORY.zh.md) for scope and **when not to use** this tool.
