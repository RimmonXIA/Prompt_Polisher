"""F8: URL extraction used by scripts/check_theory_urls.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _script_module():
    path = Path(__file__).resolve().parent.parent / "scripts" / "check_theory_urls.py"
    spec = importlib.util.spec_from_file_location("_check_theory_urls", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_urls_dedupes_and_strips_trailing_paren() -> None:
    m = _script_module()
    text = "[x](https://example.com/paper) also https://example.com/paper"
    urls = m.extract_urls(text)
    assert urls == ["https://example.com/paper"]


def test_extract_urls_finds_arxiv() -> None:
    m = _script_module()
    text = "See https://arxiv.org/abs/2404.06654 for details."
    assert "https://arxiv.org/abs/2404.06654" in m.extract_urls(text)
