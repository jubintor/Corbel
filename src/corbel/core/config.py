"""Centralized configuration management for Corbel using Pydantic Settings."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Authoritative application settings loaded from environment variables."""

    # Application Information
    ENVIRONMENT: str = Field(default="development", description="Runtime environment: development, test, production")
    DEBUG: bool = Field(default=False, description="Enable debug mode and detailed trace outputs")
    APP_NAME: str = Field(default="Corbel", description="Application service name")
    APP_VERSION: str = Field(default="0.1.0", description="Application semantic version")
    API_V1_PREFIX: str = Field(default="/api/v1", description="Prefix for v1 REST API routes")

    # Host & Port
    HOST: str = Field(default="0.0.0.0", description="Host interface to bind to")
    PORT: int = Field(default=8000, description="Port to listen on")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Standard logging level")
    LOG_FORMAT: str = Field(default="console", description="Logging format: json or console")

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origin URLs",
    )

    # PostgreSQL Database Settings
    POSTGRES_SERVER: str = Field(default="localhost", description="PostgreSQL host name")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_USER: str = Field(default="corbel", description="PostgreSQL database user")
    POSTGRES_PASSWORD: str = Field(default="corbel_secret_password", description="PostgreSQL user password")
    POSTGRES_DB: str = Field(default="corbel_db", description="PostgreSQL database name")

    # Optional explicit connection string overrides
    DATABASE_URL: str | None = Field(default=None, description="Explicit sync database connection URL override")
    DATABASE_ASYNC_URL: str | None = Field(default=None, description="Explicit async database connection URL override")

    # Security & Authentication Settings (Phase 2)
    JWT_SECRET_KEY: str = Field(
        default="corbel_insecure_development_jwt_secret_key_change_in_production_32bytes",
        description="Cryptographic secret key for signing JWT tokens",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, description="Access token expiration window in minutes")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiration window in days")

    # Data Intelligence & Profiling Settings (Phase 3)
    DATASET_STORAGE_DIR: str = Field(
        default="./data/datasets",
        description="Local directory path for securely isolated dataset storage",
    )
    MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=52428800,  # 50 MB
        description="Maximum permitted dataset upload file size in bytes",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        import json
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def async_database_url(self) -> str:
        """Construct the asyncpg connection URL for SQLAlchemy async engine."""
        if self.DATABASE_ASYNC_URL:
            return self.DATABASE_ASYNC_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Construct the psycopg connection URL for Alembic migrations and sync scripts."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton instance of application settings."""
    return Settings()
