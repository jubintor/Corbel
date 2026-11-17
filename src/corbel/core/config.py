"""Centralized configuration management for Corbel using Pydantic Settings."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator, model_validator
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

    # Database Connection Pool Settings (P1-LIM-008, P1-LIM-009)
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50, description="SQLAlchemy connection pool size per worker")
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=50, description="SQLAlchemy maximum overflow connections per worker")
    DB_POOL_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1.0, description="Timeout in seconds waiting for connection from pool")
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=60, description="Connection recycle interval in seconds")
    DB_HEALTH_CHECK_TIMEOUT_SECONDS: float = Field(default=3.0, ge=0.5, le=30.0, description="Timeout in seconds for database health ping")

    # Optional explicit connection string overrides
    DATABASE_URL: str | None = Field(default=None, description="Explicit sync database connection URL override")
    DATABASE_ASYNC_URL: str | None = Field(default=None, description="Explicit async database connection URL override")

    # Security & Authentication Settings (Phase 2 & Remediations)
    JWT_SECRET_KEY: str = Field(
        default="corbel_insecure_development_jwt_secret_key_change_in_production_32bytes",
        description="Cryptographic secret key for signing JWT tokens",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    JWT_ISSUER: str = Field(default="corbel-identity", description="JWT issuer claim (iss)")
    JWT_AUDIENCE: str = Field(default="corbel-api", description="JWT audience claim (aud)")
    JWT_PUBLIC_KEY: str | None = Field(default=None, description="Public key for asymmetric JWT validation (RS256/ES256)")
    JWT_PRIVATE_KEY: str | None = Field(default=None, description="Private key for asymmetric JWT signing (RS256/ES256)")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, description="Access token expiration window in minutes")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Refresh token expiration window in days")
    AUTH_SESSION_RETENTION_DAYS: int = Field(default=30, description="Days to retain expired/revoked auth records before purging")
    AUTH_TOKEN_PURGE_BATCH_SIZE: int = Field(default=500, description="Batch size for purging expired auth records")
    RATE_LIMIT_LOGIN_PER_MINUTE: int = Field(default=10, description="Permitted login attempts per IP per minute")
    RATE_LIMIT_REGISTER_PER_MINUTE: int = Field(default=5, description="Permitted registration attempts per IP per minute")
    RATE_LIMIT_LOGIN_FAILURES_LOCKOUT: int = Field(default=5, description="Consecutive failed logins before temporary lockout")
    RATE_LIMIT_LOCKOUT_MINUTES: int = Field(default=15, description="Temporary lockout duration in minutes")
    TRUSTED_PROXIES: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "::1"],
        description="Explicitly trusted reverse proxy IP addresses for client IP extraction",
    )

    # Data Intelligence & Profiling Settings (Phase 3)
    DATASET_STORAGE_DIR: str = Field(
        default="./data/datasets",
        description="Local directory path for securely isolated dataset storage",
    )
    MAX_UPLOAD_SIZE_BYTES: int = Field(
        default=52428800,  # 50 MB
        description="Maximum permitted dataset upload file size in bytes",
    )

    # Structured Querying & Early AI Gateway Settings (Phase 5)
    AI_PROVIDER: str = Field(
        default="mock",
        description="AI Model Gateway provider: 'mock', 'anthropic', or 'openai'",
    )
    ANTHROPIC_API_KEY: str | None = Field(
        default=None,
        description="API key for Anthropic Claude hosted model gateway",
    )
    ANTHROPIC_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Anthropic model identifier",
    )
    OPENAI_API_KEY: str | None = Field(
        default=None,
        description="API key for OpenAI GPT hosted model gateway",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o",
        description="OpenAI model identifier",
    )
    XAI_API_KEY: str | None = Field(
        default=None,
        description="API key for xAI Grok hosted model gateway",
    )
    XAI_MODEL: str = Field(
        default="grok-beta",
        description="xAI model identifier",
    )
    LLAMA_API_KEY: str | None = Field(
        default=None,
        description="API key for hosted LLaMA model gateway",
    )
    LLAMA_MODEL: str = Field(
        default="meta-llama/llama-3.3-70b-instruct",
        description="LLaMA model identifier",
    )
    LLAMA_BASE_URL: str | None = Field(
        default=None,
        description="Base URL for hosted LLaMA API endpoint",
    )

    # Embedding & Vector RAG Settings (Phase 9 Upgrade)
    EMBEDDING_PROVIDER: str = Field(
        default="fake",
        description="Embedding provider: 'fake' (deterministic mock for test/dev) or 'openai'",
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-3-small",
        description="Embedding model identifier",
    )
    EMBEDDING_DIMENSIONS: int = Field(
        default=1536,
        description="Embedding vector dimensions",
    )
    EMBEDDING_API_KEY: str | None = Field(
        default=None,
        description="API key for hosted embedding provider",
    )
    RAG_TOP_K: int = Field(
        default=5,
        description="Default top-K retrieval count for RAG",
    )
    RAG_RRF_K: int = Field(
        default=60,
        description="Reciprocal Rank Fusion smoothing constant k",
    )
    AI_REQUEST_TIMEOUT_SECONDS: float = Field(
        default=30.0,
        description="Timeout in seconds for external AI gateway requests",
    )
    AI_MAX_RETRIES: int = Field(
        default=2,
        description="Maximum retry attempts for transient AI gateway errors",
    )
    MAX_QUERY_ROW_LIMIT: int = Field(
        default=500,
        description="Maximum row limit permitted for structured query executions",
    )

    # Optional Arize Phoenix Observability Settings (Phase 10, ADR-016)
    PHOENIX_ENABLED: bool = Field(
        default=False,
        description="Enable optional Arize Phoenix AI telemetry and trace export",
    )
    PHOENIX_COLLECTOR_ENDPOINT: str = Field(
        default="http://localhost:6006/v1/traces",
        description="Arize Phoenix OpenTelemetry OTLP/HTTP collector endpoint",
    )
    PHOENIX_PROJECT_NAME: str = Field(
        default="corbel-ai",
        description="Arize Phoenix project namespace for spans and traces",
    )
    PHOENIX_CAPTURE_PAYLOADS: bool = Field(
        default=False,
        description="Capture full prompt payloads in Phoenix traces (default False for sensitive data protection)",
    )
    PHOENIX_TIMEOUT_SECONDS: float = Field(
        default=2.0,
        description="Timeout in seconds for outbound Phoenix trace spans export",
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

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforce strict security requirements when running in production environment (P1-LIM-003)."""
        if self.ENVIRONMENT.lower() == "production":
            errors: list[str] = []

            # 1. Debug mode must strictly be disabled in production
            if self.DEBUG:
                errors.append("DEBUG mode must be False in production environment")

            # 2. Reject default or weak JWT secrets
            insecure_jwt_defaults = {
                "corbel_insecure_development_jwt_secret_key_change_in_production_32bytes",
                "change_me_to_a_secure_random_string_in_production_min32chars",
                "secret",
                "changeme",
                "default",
            }
            if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY in insecure_jwt_defaults:
                errors.append("JWT_SECRET_KEY must not use default or placeholder development secrets")
            elif len(self.JWT_SECRET_KEY) < 32:
                errors.append("JWT_SECRET_KEY must be at least 32 characters long for cryptographic security")

            # 3. Reject default or weak database credentials
            insecure_pg_passwords = {
                "corbel_secret_password",
                "replace_with_local_database_password",
                "postgres",
                "password",
                "admin",
                "",
            }
            if self.POSTGRES_PASSWORD in insecure_pg_passwords:
                errors.append("POSTGRES_PASSWORD must not use default or placeholder database passwords")
            elif len(self.POSTGRES_PASSWORD) < 8:
                errors.append("POSTGRES_PASSWORD must be at least 8 characters long")

            # 4. Reject wildcard CORS origins with credentials
            if "*" in self.CORS_ORIGINS:
                errors.append("CORS_ORIGINS must not contain wildcard '*' in production when credentials are enabled")

            # 5. Validate AI provider requirements
            if self.AI_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
                errors.append("ANTHROPIC_API_KEY is required in production when AI_PROVIDER is 'anthropic'")
            elif self.AI_PROVIDER == "openai" and not self.OPENAI_API_KEY:
                errors.append("OPENAI_API_KEY is required in production when AI_PROVIDER is 'openai'")

            if errors:
                # Never include the actual secret values in the exception message
                raise ValueError(
                    f"Production configuration security validation failed with {len(errors)} error(s): "
                    + "; ".join(errors)
                )

        return self

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
