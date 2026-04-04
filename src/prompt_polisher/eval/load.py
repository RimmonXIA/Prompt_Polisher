from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from prompt_polisher.eval.schema import EvalItem


class EvalManifest(BaseModel):
    version: str = "1"
    description: str = ""


class EvalSet(BaseModel):
    manifest: EvalManifest
    items: list[EvalItem]
    source_dir: Path


def resolve_evalset_dir(explicit: Path | None = None) -> Path:
    """Resolve directory containing manifest.json + items.jsonl."""
    if explicit is not None:
        return explicit.resolve()

    env = os.environ.get("PROMPT_POLISHER_EVALSET", "").strip()
    if env:
        return Path(env).expanduser().resolve()

    cwd = Path.cwd().resolve()
    for base in [cwd, *cwd.parents]:
        candidate = base / "evalsets" / "v1"
        if (candidate / "manifest.json").is_file() and (candidate / "items.jsonl").is_file():
            return candidate.resolve()

    msg = (
        "Could not find evalsets/v1 (manifest.json + items.jsonl). "
        "Run from the repository root, set PROMPT_POLISHER_EVALSET, or pass --evalset-dir."
    )
    raise FileNotFoundError(msg)


def load_evalset(evalset_dir: Path | None = None) -> EvalSet:
    """Load manifest and JSONL items from an eval set directory."""
    root = evalset_dir or resolve_evalset_dir()
    manifest_path = root / "manifest.json"
    items_path = root / "items.jsonl"
    if not manifest_path.is_file():
        msg = f"missing manifest: {manifest_path}"
        raise FileNotFoundError(msg)
    if not items_path.is_file():
        msg = f"missing items: {items_path}"
        raise FileNotFoundError(msg)

    manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = EvalManifest.model_validate(manifest_raw)

    items: list[EvalItem] = []
    for line_no, line in enumerate(items_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
            items.append(EvalItem.model_validate(row))
        except (json.JSONDecodeError, ValueError) as exc:
            msg = f"{items_path}:{line_no}: invalid item: {exc}"
            raise ValueError(msg) from exc

    if not items:
        msg = f"no eval items in {items_path}"
        raise ValueError(msg)

    return EvalSet(manifest=manifest, items=items, source_dir=root.resolve())
