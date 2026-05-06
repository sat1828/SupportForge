"""
SupportForge Backend — Pydantic v2 Settings
All config sourced from environment variables.
Validated at startup — missing required vars raise immediately.
"""
from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py is at: backend/app/config.py
# .env is at:      backend/.env  (CWD when running uvicorn from backend/)
# Also look in:    supportforge/.env  (project root, for Docker/CI)
_APP_DIR = Path(__file__).parent          # backend/app/
_BACKEND_DIR = _APP_DIR.parent            # backend/
_PROJECT_DIR = _BACKEND_DIR.parent        # supportforge/

# Build the list of env files to search (first found wins)
_ENV_FILES = [
    str(_BACKEND_DIR / ".env"),           # backend/.env  ← primary
    str(_PROJECT_DIR / ".env"),           # supportforge/.env ← fallback
    ".env",                               # CWD fallback
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ───────────────────────────────────────────
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    # ── Database ──────────────────────────────────────────────
    database_url: str = Field(..., description="PostgreSQL async connection URL")

    # ── Redis ─────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")

    # ── Security ──────────────────────────────────────────────
    secret_key: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── LLM Providers ─────────────────────────────────────────
    groq_api_key: str = Field(default="")
    groq_model: str = "llama-3.1-8b-instant"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # ── LangSmith (optional — graceful degradation) ────────────
    langsmith_api_key: str = Field(default="")
    langsmith_project: str = "supportforge"
    langchain_tracing_v2: bool = False

    # ── Translation ───────────────────────────────────────────
    libretranslate_url: str = "http://localhost:5000"

    # ── RAG ───────────────────────────────────────────────────
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    embedding_cache_ttl_seconds: int = 86400

    # ── Execution Budget (Invariants) ──────────────────────────
    max_steps_per_ticket: int = Field(default=10, ge=1, le=50)
    max_latency_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    max_kb_retries: int = Field(default=3, ge=1, le=10)
    max_llm_calls_per_ticket: int = Field(default=5, ge=1, le=20)
    max_tokens_per_ticket: int = Field(default=5000, ge=500, le=32000)

    # ── Concurrency ───────────────────────────────────────────
    max_concurrent_agent_executions: int = Field(default=20, ge=1, le=100)
    max_tickets_per_user_per_minute: int = Field(default=5, ge=1, le=60)

    # ── Context Manager ───────────────────────────────────────
    max_context_messages: int = 6
    max_context_tokens: int = 4000
    max_kb_results_per_cycle: int = 3

    # ── Replay Retention ──────────────────────────────────────
    replay_full_retention_days: int = 7
    replay_summary_retention_days: int = 90

    # ── CORS ──────────────────────────────────────────────────
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def langsmith_enabled(self) -> bool:
        return bool(self.langsmith_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Called once at startup."""
    return Settings()


# Module-level convenience — import `settings` directly
settings = get_settings()
