from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from prompt_polisher.langfuse_check import main


def test_langfuse_check_health_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    mock_get = MagicMock()
    mock_get.return_value.status_code = 200

    with patch("prompt_polisher.langfuse_check.httpx.get", mock_get):
        code = main([])

    assert code == 0
    assert mock_get.call_count >= 1
