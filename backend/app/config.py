"""Application settings, loaded from environment variables (12-factor style)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres connection string. When unset, request logging is disabled and
    # the service still classifies prompts (handy for tests and demos).
    database_url: str | None = None

    # Hosted-LLM judge. The defaults target the Anthropic Messages API, but any
    # compatible endpoint works by overriding base_url / model.
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.anthropic.com"
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_timeout_seconds: float = 8.0

    # CORS origins allowed to call the API (comma-separated in the env var).
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
