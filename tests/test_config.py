"""Automated test suite for centralized application configuration."""

from corbel.core.config import Settings


def test_settings_default_values() -> None:
    """Verify application default configuration settings."""
    settings = Settings(
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_corbel_db",
    )

    assert settings.APP_NAME == "Corbel"
    assert settings.APP_VERSION == "0.1.0"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.POSTGRES_SERVER == "db.example.com"
    assert settings.POSTGRES_PORT == 5432


def test_database_url_generation() -> None:
    """Verify correct generation of synchronous and asynchronous PostgreSQL URLs."""
    settings = Settings(
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="test_user",
        POSTGRES_PASSWORD="test_password",
        POSTGRES_DB="test_corbel_db",
    )

    assert (
        settings.async_database_url
        == "postgresql+asyncpg://test_user:test_password@db.example.com:5432/test_corbel_db"
    )
    assert (
        settings.sync_database_url
        == "postgresql+psycopg://test_user:test_password@db.example.com:5432/test_corbel_db"
    )


def test_cors_origins_parsing() -> None:
    """Verify CORS origins validator handles list and comma-separated string formats."""
    # List format
    settings_list = Settings(CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"])
    assert "http://localhost:3000" in settings_list.CORS_ORIGINS

    # String format
    settings_str = Settings(CORS_ORIGINS="http://localhost:3000, http://localhost:5173")  # type: ignore[arg-type]
    assert len(settings_str.CORS_ORIGINS) == 2
    assert "http://localhost:5173" in settings_str.CORS_ORIGINS


def test_production_security_validation_rejects_insecure_defaults() -> None:
    """Verify that production environment rejects default development secrets (P1-LIM-003)."""
    import pytest

    with pytest.raises(ValueError, match="Production configuration security validation failed"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=True,  # Invalid in production
            JWT_SECRET_KEY="corbel_insecure_development_jwt_secret_key_change_in_production_32bytes",
            POSTGRES_PASSWORD="corbel_secret_password",
            CORS_ORIGINS=["*"],
        )


def test_production_security_validation_rejects_weak_secrets() -> None:
    """Verify production rejects secrets below required length thresholds."""
    import pytest

    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            JWT_SECRET_KEY="too_short_secret",
            POSTGRES_PASSWORD="secure_prod_db_password_123",
            CORS_ORIGINS=["https://app.corbel.internal"],
        )


def test_production_security_validation_accepts_valid_config() -> None:
    """Verify production accepts securely configured settings."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET_KEY="a_very_secure_and_cryptographically_strong_random_jwt_secret_64bytes",
        POSTGRES_PASSWORD="super_secure_production_pg_password_987",
        CORS_ORIGINS=["https://app.corbel.internal", "https://corbel.internal"],
        AI_PROVIDER="mock",
    )
    assert settings.ENVIRONMENT == "production"
    assert settings.DEBUG is False
    assert len(settings.JWT_SECRET_KEY) >= 32


def test_database_pool_configuration_defaults() -> None:
    """Verify bounded database connection pool settings (P1-LIM-008)."""
    settings = Settings()
    assert settings.DB_POOL_SIZE == 5
    assert settings.DB_MAX_OVERFLOW == 10
    assert settings.DB_POOL_TIMEOUT_SECONDS == 30.0
    assert settings.DB_POOL_RECYCLE_SECONDS == 1800
    assert settings.DB_HEALTH_CHECK_TIMEOUT_SECONDS == 3.0
