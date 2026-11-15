"""SQLAlchemy database models for Phase 5 Structured Querying audit records."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class QueryExecution(Base):
    """Authoritative audit record of executed structured and natural language queries."""

    __tablename__ = "query_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_name: Mapped[str] = mapped_column(String(100), nullable=False)
    query_ast_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_sql: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_json: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_nlq: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nlq_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project")  # type: ignore[name-defined] # noqa: F821
    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined] # noqa: F821
    business_object: Mapped["BusinessObject | None"] = relationship("BusinessObject")  # type: ignore[name-defined] # noqa: F821
