# Bundled eval set (regression tasks)

Tasks under `manifest.json` + `items.jsonl` for **Tier A** structural checks and optional **Tier B** Raw vs Compiled scoring.

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

# Quick local subset (faster feedback loop)
uv run prompt-polisher-eval --structural-only --id-regex "^smoke|^gate-" --max-items 5 -v
```

### Why does nothing appear on the terminal?

A **default** run (no `--structural-only`) calls the API many times; the **JSON report is printed once at the end**, so **stdout can look empty for minutes**. Watch **stderr**: you should see a one-line `prompt-polisher-eval: starting …` message. Use `**-v`** for per-item progress, or `**--quiet**` to suppress stderr if you only want JSON.

### Exit codes (`prompt-polisher-eval`)


| Code | Meaning                                                                                   |
| ---- | ----------------------------------------------------------------------------------------- |
| `0`  | Success. With `--fail-on-structural`, every `structural_expect` matched.                  |
| `1`  | Error (missing eval set, bad JSONL, LLM config, …).                                       |
| `2`  | Tier A regression: at least one `structural_expect` failed (`--fail-on-structural` only). |


Override location:

```bash
export PROMPT_POLISHER_EVALSET=/path/to/evalsets/bundled
uv run prompt-polisher-eval --structural-only
```

## Items

Each JSONL item supports:

- `id` — stable regression identifier.
- `user_intent` — raw prompt to compile.
- `tags` — free-form labels.
- `category` — scenario group used for aggregate reporting.
- `prompt_type` — expected prompt class, such as `json_extraction_prompt`, `coding_prompt`, or `agent_tool_prompt`.
- `optimization_target` — intended optimization goal, such as `concise`, `strict_format`, `reasoning`, `agentic`, or `small_model`.
- `expected_failure_modes` — known risks this case is meant to catch.
- `structural_expect` — Tier A graph-level expectations.
- `gold` — optional Tier B executor-output scoring spec.
- `executor_system` — optional executor system prompt override.

The bundled set covers smoke, safety, writing, summarization, extraction, coding, reasoning, agent/tool, evaluation, compression, and small-model scenarios. Most items are Tier A only today; `live-contains-01` is a Tier B example that checks executor output contains `BANANA` when not running `--structural-only`.

## Honesty

Numbers apply only to the **pinned model**, temperature, and eval set version. See [docs/THEORY.zh.md](../../docs/THEORY.zh.md) non-claims.