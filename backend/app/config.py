"""Application settings, loaded from environment variables (12-factor style)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # backend/.env, found from this file rather than the working directory, so it also
    # loads when an agent (e.g. Claude Desktop) starts the MCP server from elsewhere.
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # Database for request logging (/stats, /history). Defaults to a local SQLite file
    # so it works with zero setup; set DATABASE_URL to a Postgres URL
    # (postgresql+psycopg://...) for Docker/production.
    database_url: str = "sqlite:///./guardrail.db"

    # Bearer token for the admin-only /history endpoint, which returns raw prompts.
    # Unset (the default) switches /history off, so a public demo never exposes what
    # other visitors typed. Aggregate numbers are always available from /stats.
    admin_token: str | None = None

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

    # RAG demo: the local embedding model (downloaded once, then cached) and how
    # many chunks to retrieve per question.
    rag_embedding_model: str = "BAAI/bge-small-en-v1.5"
    rag_model_cache_dir: str | None = None   # None = fastembed's default cache folder
    rag_top_k: int = 4
    # Where chunk embeddings live: "memory" (NumPy), "pgvector" (Postgres), or "auto",
    # which uses pgvector whenever DATABASE_URL points at Postgres.
    rag_vector_store: Literal["auto", "memory", "pgvector"] = "auto"

    # Host headers the MCP endpoint (/mcp) accepts, comma-separated; ":*" means any
    # port. Add the public host name when deploying (DNS-rebinding protection).
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*"

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
    def mcp_allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        """Split the comma-separated CORS origins env var into a clean list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
