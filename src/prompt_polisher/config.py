from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from prompt_polisher.llm.config import ProviderConfig

ProviderName = str
ExecutionMode = Literal["fast", "balanced", "pro"]
OptimizationTarget = Literal[
    "concise",
    "strict_format",
    "reasoning",
    "creative",
    "agentic",
    "small_model",
    "general",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: ProviderName = Field(default="deepseek", alias="LLM_PROVIDER")

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    deepseek_api_key: SecretStr | None = Field(default=None, alias="DEEPSEEK_API_KEY")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    llm_api_key: SecretStr | None = Field(default=None, alias="LLM_API_KEY")

    llm_api_base: str | None = Field(default=None, alias="LLM_API_BASE")
    openai_api_base: str | None = Field(default=None, alias="OPENAI_API_BASE")

    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")

    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE", ge=0.0, le=2.0)
    max_critic_iterations: int = Field(default=3, alias="MAX_CRITIC_ITERATIONS", ge=1, le=20)
    execution_mode: ExecutionMode = Field(default="balanced", alias="EXECUTION_MODE")
    optimization_target: OptimizationTarget = Field(
        default="general", alias="OPTIMIZATION_TARGET"
    )

    critic_use_prm: bool = Field(default=False, alias="CRITIC_USE_PRM")
    prm_model: str | None = Field(default=None, alias="PRM_MODEL")
    external_prm_endpoint: str | None = Field(default=None, alias="EXTERNAL_PRM_ENDPOINT")
    prm_min_score: float = Field(default=0.45, alias="PRM_MIN_SCORE", ge=0.0, le=1.0)
    prm_temperature: float = Field(default=0.0, alias="PRM_TEMPERATURE", ge=0.0, le=2.0)

    author_trust_mode: bool = Field(default=True, alias="AUTHOR_TRUST_MODE")

    prompts_dir: Path | None = Field(default=None, alias="PROMPTS_DIR")

    abort_on_heuristic_injection: bool = Field(default=True, alias="ABORT_ON_HEURISTIC_INJECTION")
    abort_on_sniffer_high: bool = Field(default=False, alias="ABORT_ON_SNIFFER_HIGH")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_json: bool = Field(default=False, alias="LOG_JSON")
    log_prompt_previews: bool = Field(default=False, alias="LOG_PROMPT_PREVIEWS")

    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_api_key: SecretStr | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langchain_project: str | None = Field(default=None, alias="LANGCHAIN_PROJECT")

    langfuse_tracing: bool = Field(default=False, alias="LANGFUSE_TRACING")
    langfuse_public_key: str | None = Field(default=None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: SecretStr | None = Field(default=None, alias="LANGFUSE_SECRET_KEY")
    langfuse_base_url: str | None = Field(default=None, alias="LANGFUSE_BASE_URL")

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _lower_provider(cls, v: object) -> object:
        if isinstance(v, str):
            return v.lower().strip()
        return v

    @field_validator("execution_mode", mode="before")
    @classmethod
    def _normalize_execution_mode(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.lower().strip()
            if s in {"fast", "balanced", "pro"}:
                return s
            msg = f"EXECUTION_MODE must be one of: fast, balanced, pro (got {v!r})"
            raise ValueError(msg)
        return v

    @field_validator("optimization_target", mode="before")
    @classmethod
    def _normalize_optimization_target(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.lower().strip()
            if s in {
                "concise",
                "strict_format",
                "reasoning",
                "creative",
                "agentic",
                "small_model",
                "general",
            }:
                return s
            msg = (
                "OPTIMIZATION_TARGET must be one of: concise, strict_format, reasoning, "
                f"creative, agentic, small_model, general (got {v!r})"
            )
            raise ValueError(msg)
        return v

    @field_validator("prompts_dir", mode="before")
    @classmethod
    def _optional_prompts_dir(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, Path):
            return v if str(v).strip() else None
        if isinstance(v, str):
            s = v.strip()
            return Path(s) if s else None
        return v

    @field_validator(
        "author_trust_mode",
        "abort_on_heuristic_injection",
        "abort_on_sniffer_high",
        "critic_use_prm",
        mode="before",
    )
    @classmethod
    def _coerce_bool_flag(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("0", "false", "no", "off"):
                return False
            if s in ("1", "true", "yes", "on"):
                return True
        return v

    def resolved_api_key(self) -> str:
        cfg = self.resolve_provider_config()
        return cfg.api_key.get_secret_value()

    def resolve_provider_config(self) -> ProviderConfig:
        from prompt_polisher.llm.config import AnthropicConfig, GeminiConfig, OpenAICompatConfig

        provider = self.llm_provider.strip().lower()
        timeout = 180.0

        if provider == "anthropic":
            api_key = self.anthropic_api_key or self.llm_api_key
            if api_key is None:
                msg = "ANTHROPIC_API_KEY or LLM_API_KEY is required when LLM_PROVIDER=anthropic"
                raise ValueError(msg)
            model = self.llm_model or "claude-3-5-sonnet-latest"
            return AnthropicConfig(api_key=api_key, model=model, timeout=timeout)

        if provider in {"gemini", "google"}:
            api_key = self.gemini_api_key or self.llm_api_key
            if api_key is None:
                msg = "GEMINI_API_KEY or LLM_API_KEY is required when LLM_PROVIDER=gemini/google"
                raise ValueError(msg)
            model = self.llm_model or "gemini-2.0-flash"
            return GeminiConfig(api_key=api_key, model=model, timeout=timeout)

        if self.llm_api_key is not None:
            api_key = self.llm_api_key
        elif self.llm_provider == "deepseek" and self.deepseek_api_key:
            api_key = self.deepseek_api_key
        elif self.llm_provider == "openai" and self.openai_api_key:
            api_key = self.openai_api_key
        else:
            # For other OpenAI-compatible providers, we expect LLM_API_KEY to be set.
            if self.llm_provider == "deepseek":
                msg = "DEEPSEEK_API_KEY or LLM_API_KEY is required when LLM_PROVIDER=deepseek"
                raise ValueError(msg)
            if self.llm_provider == "openai":
                msg = "OPENAI_API_KEY or LLM_API_KEY is required when LLM_PROVIDER=openai"
                raise ValueError(msg)
            if self.llm_api_key is None:
                msg = f"LLM_API_KEY is required for provider '{self.llm_provider}'"
                raise ValueError(msg)
            api_key = self.llm_api_key

        return OpenAICompatConfig(
            provider=provider,
            api_key=api_key,
            model=self.resolved_model(),
            base_url=self.resolved_base_url(),
            timeout=timeout,
        )

    def resolved_base_url(self) -> str | None:
        if self.llm_api_base:
            return self.llm_api_base.rstrip("/")
        if self.llm_provider == "deepseek":
            return "https://api.deepseek.com"
        if self.openai_api_base:
            return self.openai_api_base.rstrip("/")
        return None

    def resolved_model(self) -> str:
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == "deepseek":
            return self.deepseek_model
        if self.llm_provider == "openai":
            return self.openai_model
        return self.llm_model or "gpt-4o-mini"  # Fallback

    def resolved_prm_model(self) -> str:
        if self.prm_model and self.prm_model.strip():
            return self.prm_model.strip()
        return self.resolved_model()

    def apply_langchain_env(self) -> None:
        import os

        if self.langchain_tracing_v2:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if self.langchain_api_key is not None:
            os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key.get_secret_value()
        if self.langchain_project:
            os.environ["LANGCHAIN_PROJECT"] = self.langchain_project


@lru_cache
def get_settings() -> Settings:
    return Settings()
