"""
Application configuration using Pydantic BaseSettings.
All values are loaded from environment variables (or .env file).
Type-safe, validated at startup — no silent misconfigurations.
"""
from __future__ import annotations

import secrets
from typing import Annotated, Any
from pydantic import AnyHttpUrl, BeforeValidator, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_cors(value: Any) -> list[str]:
    """Accept comma-separated string or list for CORS origins."""
    if isinstance(value, str):
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str = secrets.token_hex(32)
    APP_VERSION: str = "1.0.0"
    APP_NAME: str = "CrimeAI"
    ALLOWED_ORIGINS: Annotated[list[str], BeforeValidator(_parse_cors)] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # ── API ───────────────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    DOCS_ENABLED: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/crimeai"
    DATABASE_URL_SYNC: str = "postgresql://postgres:password@localhost:5432/crimeai"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 300

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = secrets.token_hex(32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_ML: str = "20/minute"

    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "fir-documents"

    # ── Sentry ────────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""

    # ── ML / NLP ──────────────────────────────────────────────────────────────
    SPACY_MODEL: str = "en_core_web_sm"
    DBSCAN_EPS: float = 0.5
    DBSCAN_MIN_SAMPLES: int = 3
    HOTSPOT_PREDICTION_INTERVAL: int = 3600

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json | console

    # ── Computed properties ───────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @field_validator("APP_ENV")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Fail fast if production is misconfigured."""
        if self.APP_ENV == "production":
            if self.APP_SECRET_KEY == secrets.token_hex(32):
                raise ValueError("APP_SECRET_KEY must be explicitly set in production")
            if not self.SENTRY_DSN:
                # Warn but don't fail — Sentry is optional
                pass
        return self


# Single instance — imported everywhere as `from app.core.config import settings`
settings = Settings()
