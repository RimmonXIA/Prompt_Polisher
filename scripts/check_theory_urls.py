#!/usr/bin/env python3
"""Check HTTP(S) URLs embedded in docs/THEORY.zh.md (maintainer tool; optional network)."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_URL_RE = re.compile(r"https?://[^\s\)\]\"'<>]+", re.IGNORECASE)


def theory_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "THEORY.zh.md"


def extract_urls(text: str) -> list[str]:
    found = _URL_RE.findall(text)
    seen: set[str] = set()
    out: list[str] = []
    for u in found:
        u = u.rstrip(".,;:")
        if u.endswith(")"):
            u = u[:-1]
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Prompt-Polisher-link-check/1.0"
)


def _request_status(url: str, timeout: float, method: str) -> tuple[int | None, str | None]:
    req = urllib.request.Request(
        url,
        method=method,
        headers={"User-Agent": _BROWSER_UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if method == "GET":
                resp.read(8192)
            return resp.getcode(), None
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return None, str(exc)


def head_status(url: str, timeout: float) -> tuple[int | None, str | None]:
    """HEAD first; on 403/405 or failure, retry GET (some hosts block bare HEAD)."""
    code, err = _request_status(url, timeout, "HEAD")
    if code is not None and 200 <= code < 400:
        return code, err
    if code in (403, 405) or code is None:
        return _request_status(url, timeout, "GET")
    return code, err


def main() -> int:
    parser = argparse.ArgumentParser(description="Check HTTP(S) URLs in docs/THEORY.zh.md")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repository root",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-request timeout seconds",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Print URLs only, no network",
    )
    args = parser.parse_args()
    path = theory_path(args.root)
    if not path.is_file():
        print(f"missing {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    urls = extract_urls(text)
    if args.list_only:
        for u in urls:
            print(u)
        return 0

    failures: list[tuple[str, str]] = []
    for url in urls:
        code, err = head_status(url, args.timeout)
        if code is None or code >= 400:
            failures.append((url, err or f"HTTP {code}"))
            print(f"FAIL {url} -> {err or code}", file=sys.stderr)
        else:
            print(f"OK   {url} -> {code}")

    if failures:
        print(f"\n{len(failures)} URL(s) failed", file=sys.stderr)
        return 1
    print(f"\nAll {len(urls)} URL(s) OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
