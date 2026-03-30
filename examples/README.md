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

See also [docs/THEORY.en.md](../docs/THEORY.en.md) for scope and **when not to use** this tool.
