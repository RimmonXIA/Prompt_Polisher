from __future__ import annotations

import base64
import json
import sys

import httpx

from prompt_polisher.config import get_settings


def main(argv: list[str] | None = None) -> int:
    _ = argv
    settings = get_settings()
    base = (settings.langfuse_base_url or "https://cloud.langfuse.com").rstrip("/")

    health = httpx.get(f"{base}/api/public/health", timeout=20.0)
    if health.status_code != 200:
        print(f"Health check failed: HTTP {health.status_code}", file=sys.stderr)
        return 1
    print("Langfuse health: OK")

    public = settings.langfuse_public_key
    secret = settings.langfuse_secret_key
    if not public or secret is None:
        print(
            "Set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to verify credentials.",
            file=sys.stderr,
        )
        return 0

    token = base64.b64encode(f"{public}:{secret.get_secret_value()}".encode()).decode()
    projects = httpx.get(
        f"{base}/api/public/projects",
        headers={"Authorization": f"Basic {token}"},
        timeout=20.0,
    )
    if projects.status_code != 200:
        print(f"Auth check failed: HTTP {projects.status_code} {projects.text}", file=sys.stderr)
        return 1

    try:
        data = projects.json()
    except json.JSONDecodeError:
        print("Auth check: unexpected response", file=sys.stderr)
        return 1

    print("Langfuse credentials: OK")
    if isinstance(data, dict) and "data" in data:
        names = [p.get("name") for p in data.get("data", []) if isinstance(p, dict)]
        if names:
            print("Projects:", ", ".join(str(n) for n in names if n))
    return 0
