"""Application settings, loaded from environment variables (12-factor style)."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database for request logging / history. Defaults to a local SQLite file so
    # /history works with zero setup; set DATABASE_URL to a Postgres URL
    # (postgresql+psycopg://...) for Docker/production.
    database_url: str = "sqlite:///./guardrail.db"

    # Hosted LLM (the judge layer, and answers in the RAG demo). Two wire formats:
    #   "anthropic": the Anthropic Messages API (the default)
    #   "openai":    the OpenAI-style chat completions API, which Groq, Google Gemini,
    #                OpenAI and most other providers speak
    # Point base_url / model at any compatible endpoint. With no key, the service runs
    # heuristics-only and says so in every response.
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    llm_api_key: str | None = None
    llm_base_url: str | None = None     # None = the provider's official endpoint
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_timeout_seconds: float = 8.0
    # Optional hint for reasoning models (e.g. "low" for gpt-oss on Groq), so they
    # answer quickly instead of thinking at length about a one-line verdict.
    llm_reasoning_effort: str | None = None

    # CORS origins allowed to call the API (comma-separated in the env var).
    cors_origins: str = "http://localhost:5173"

    @property
    def llm_endpoint(self) -> str:
        """The base URL to call: the configured one, or the provider's official API."""
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_provider == "openai":
            return "https://api.openai.com/v1"
        return "https://api.anthropic.com"

    @property
    def cors_origin_list(self) -> list[str]:
        """Split the comma-separated CORS origins env var into a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
