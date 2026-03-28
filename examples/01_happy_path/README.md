# Happy path example (illustration only)

Files here are **synthetic / redacted** for documentation. They are **not** a pinned model output or a strict JSON Schema contract.

- **`sample_report.json`** — Shape resembles `--report-json`; **`radar_analysis` and `routing_decision` keys vary** with the live model and prompts. Do not treat every key in the sample as stable for integration tests without pinning the model and input.
- Use [`../../docs/AUDIT_SELF_EXPLAINING.md`](../../docs/AUDIT_SELF_EXPLAINING.md) §3 for machine-facing contracts (`summary`, envelope, exit codes).
