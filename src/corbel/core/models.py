"""Foundational core models for Corbel internal platform metadata."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from corbel.core.database import Base


class SystemMetadata(Base):
    """Internal platform metadata ledger storing baseline environment and version information."""

    __tablename__ = "system_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True, nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
