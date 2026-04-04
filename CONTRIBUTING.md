# Contributing

Thanks for helping improve Prompt Polisher.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Local setup

```bash
git clone https://github.com/RimmonXIA/Prompt_Polisher.git
cd Prompt_Polisher
uv sync --all-groups
cp .env.example .env
# Edit .env with your API keys when exercising the CLI against a real model.
```

Optional Langfuse tracing:

```bash
uv sync --extra langfuse
```

## Checks to run before a PR

```bash
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
# Optional: end-to-end eval harness (needs working LLM credentials; compile still calls the API)
uv run prompt-polisher-eval --structural-only --fail-on-structural
```

Optional (needs network): verify reference URLs in [docs/THEORY.zh.md](docs/THEORY.zh.md) with `uv run python scripts/check_theory_urls.py` (use `--list-only` to skip HTTP).

CI runs the same steps with `uv sync --frozen` on **Python 3.11 and 3.12**; `pytest` is configured with **`--cov-fail-under=70`** (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Pull requests

- Keep changes focused on a single concern when possible.
- Update the README, [docs/THEORY.zh.md](docs/THEORY.zh.md), and (if scope or non-claims change) [docs/THEORY.en.md](docs/THEORY.en.md) or [examples/](examples/) when user-facing behavior or theory claims change.
- Do not commit secrets (`.env`, API keys, tokens).

## Repository metadata (maintainers)

GitHub’s **About** box affects discovery (search and the repo header). After substantive releases, consider:

- **Description** (suggested, under ~350 characters): `Python CLI: LangGraph prompt compiler (radar → gate → route → compile → critic); JSON envelope for agents.`
- **Topics** (pick a subset that fits the project): `langgraph`, `langchain`, `prompt-engineering`, `llm`, `python`, `cli`, `openai`, `deepseek`, `agent`, `dspy`
- **Website** (optional): [English theory bridge](https://github.com/RimmonXIA/Prompt_Polisher/blob/main/docs/THEORY.en.md) or the [README](https://github.com/RimmonXIA/Prompt_Polisher#readme) anchor.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
