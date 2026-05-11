from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypedDict


class ChatMessage(TypedDict):
    role: str
    content: str


class ProviderAdapter(Protocol):
    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str: ...

    async def acomplete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str,
        temperature: float,
        timeout: float,
    ) -> str: ...
