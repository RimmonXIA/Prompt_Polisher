from __future__ import annotations

from prompt_polisher.llm.adapters import AnthropicAdapter, GeminiAdapter, OpenAICompatibleAdapter
from prompt_polisher.llm.config import (
    AnthropicConfig,
    GeminiConfig,
    OpenAICompatConfig,
    ProviderConfig,
)
from prompt_polisher.llm.protocol import ProviderAdapter


def build_adapter(cfg: ProviderConfig) -> ProviderAdapter:
    if isinstance(cfg, OpenAICompatConfig):
        return OpenAICompatibleAdapter(
            api_key=cfg.api_key.get_secret_value(),
            base_url=cfg.base_url,
            default_model=cfg.model,
        )
    if isinstance(cfg, AnthropicConfig):
        return AnthropicAdapter(
            api_key=cfg.api_key.get_secret_value(),
            default_model=cfg.model,
        )
    if isinstance(cfg, GeminiConfig):
        return GeminiAdapter(
            api_key=cfg.api_key.get_secret_value(),
            default_model=cfg.model,
        )
    msg = f"Unsupported provider config: {type(cfg).__name__}"
    raise TypeError(msg)
