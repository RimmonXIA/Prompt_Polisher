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
uv run ruff check src tests
uv run mypy src
```

CI runs the same steps with `uv sync --frozen` (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Pull requests

- Keep changes focused on a single concern when possible.
- Update the README or [docs/THEORY.zh.md](docs/THEORY.zh.md) if user-facing behavior or theory claims change.
- Do not commit secrets (`.env`, API keys, tokens).

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
