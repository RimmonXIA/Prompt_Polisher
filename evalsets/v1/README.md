# Eval set v1 (Phase 1)

Versioned tasks under `manifest.json` + `items.jsonl` for **Tier A** structural checks and optional **Tier B** Raw vs Compiled scoring.

## Run

From the repository root (with API key in `.env`):

```bash
# Full option reference (Rich-formatted: tiers, discovery, exit codes)
uv run prompt-polisher-eval --help

uv run prompt-polisher-eval -V   # package version only

# Tier A only — no executor LLM calls (recommended for CI-style checks)
uv run prompt-polisher-eval --structural-only --fail-on-structural

# Full suite — Tier B runs for items with non-`none` gold (extra API cost)
uv run prompt-polisher-eval
```

### Exit codes (`prompt-polisher-eval`)

| Code | Meaning |
| --- | --- |
| `0` | Success. With `--fail-on-structural`, every `structural_expect` matched. |
| `1` | Error (missing eval set, bad JSONL, LLM config, …). |
| `2` | Tier A regression: at least one `structural_expect` failed (`--fail-on-structural` only). |

Override location:

```bash
export PROMPT_POLISHER_EVALSET=/path/to/evalsets/v1
uv run prompt-polisher-eval --structural-only
```

## Items

- `smoke-structural-01` — benign compile; expects successful pipeline.
- `gate-heuristic-01` — heuristic injection line; expects threat-gate abort (requires `ABORT_ON_HEURISTIC_INJECTION` default **on**).
- `live-contains-01` — **Tier B**: checks executor output contains `BANANA`; uses paired Raw vs Compiled arms when not `--structural-only`. Results are **model-dependent**.

## Honesty

Numbers apply only to the **pinned model**, temperature, and eval set version. See [docs/THEORY.en.md](../../docs/THEORY.en.md) non-claims.
