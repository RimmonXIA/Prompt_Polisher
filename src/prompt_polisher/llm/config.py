from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr


class OpenAICompatConfig(BaseModel):
    kind: Literal["openai_compat"] = "openai_compat"
    provider: str
    api_key: SecretStr
    model: str
    base_url: str | None = None
    timeout: float = 180.0


class AnthropicConfig(BaseModel):
    kind: Literal["anthropic"] = "anthropic"
    api_key: SecretStr
    model: str
    timeout: float = 180.0


class GeminiConfig(BaseModel):
    kind: Literal["gemini"] = "gemini"
    api_key: SecretStr
    model: str
    timeout: float = 180.0


ProviderConfig = Annotated[
    OpenAICompatConfig | AnthropicConfig | GeminiConfig,
    Field(discriminator="kind"),
]
