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
    settings_str = Settings(CORS_ORIGINS="http://localhost:3000, http://localhost:5173") # type: ignore
    assert len(settings_str.CORS_ORIGINS) == 2
    assert "http://localhost:5173" in settings_str.CORS_ORIGINS
