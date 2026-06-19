"""Application settings, loaded from environment variables (12-factor)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder secret shipped in source. Refusing to boot with it in production
# is a fail-fast guard against accidentally deploying an insecure default.
DEFAULT_JWT_SECRET = "change-me-in-production-please-use-a-long-random-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://app:app@db:5432/procurement"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Comma-separated list of allowed CORS origins (empty = none / same-origin only).
    cors_origins: str = ""

    # Login rate limiting (brute-force / credential-stuffing protection).
    login_rate_limit: int = 10        # attempts...
    login_rate_window_seconds: int = 60  # ...per window, per client IP.

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_secure_secret_in_production(self) -> Settings:
        if self.app_env == "production" and (
            self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32
        ):
            raise ValueError(
                "Insecure JWT_SECRET in production: set a strong secret "
                "(>= 32 chars, not the default). Generate one with `openssl rand -hex 32`."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so settings are parsed once per process."""
    return Settings()
