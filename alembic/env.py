"""Alembic migration environment configured for Corbel."""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from corbel.core.config import get_settings
from corbel.core.database import Base
from corbel.core.models import SystemMetadata  # noqa: F401 - Register models with Base.metadata
from corbel.domains.data_intelligence.models import (  # noqa: F401 - Register Phase 3 models
    Dataset,
    DatasetVersion,
    DataSource,
)
from corbel.domains.ontology.models import (  # noqa: F401 - Register Phase 4 models
    BusinessObject,
    Property,
    PropertyMapping,
    Relationship,
)
from corbel.domains.query.models import (  # noqa: F401 - Register Phase 5 models
    QueryExecution,
)
from corbel.domains.tenancy.models import (  # noqa: F401 - Register Phase 2 tenancy models
    Organization,
    OrganizationMember,
    Project,
    ProjectMember,
    User,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def get_sync_url() -> str:
    """Retrieve synchronized database URL from centralized settings."""
    settings = get_settings()
    return settings.sync_database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using engine created from settings."""
    sync_url = get_sync_url()
    connectable = create_engine(
        sync_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
