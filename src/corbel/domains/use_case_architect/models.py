"""SQLAlchemy ORM models for Phase 11: Use-Case Architect."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class UseCaseStatus(str, enum.Enum):
    """Lifecycle state of a business use case."""

    DRAFT = "DRAFT"
    DISCOVERY = "DISCOVERY"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"


class MessageSenderRole(str, enum.Enum):
    """Sender role in a discovery dialogue."""

    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"


class UseCase(Base):
    """Business use case managed by the Use-Case Architect."""

    __tablename__ = "use_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=UseCaseStatus.DRAFT.value,
        nullable=False,
        index=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_version: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    messages: Mapped[list["UseCaseMessage"]] = relationship(
        "UseCaseMessage",
        back_populates="use_case",
        cascade="all, delete-orphan",
        order_by="UseCaseMessage.created_at",
    )
    specifications: Mapped[list["UseCaseSpecificationVersion"]] = relationship(
        "UseCaseSpecificationVersion",
        back_populates="use_case",
        cascade="all, delete-orphan",
        order_by="UseCaseSpecificationVersion.version",
    )


class UseCaseMessage(Base):
    """A message in the bounded discovery dialogue for a use case."""

    __tablename__ = "use_case_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("use_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_role: Mapped[str] = mapped_column(String(32), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_requirements_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    clarification_questions_json: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    use_case: Mapped["UseCase"] = relationship(
        "UseCase",
        back_populates="messages",
    )


class UseCaseSpecificationVersion(Base):
    """An immutable, versioned structured solution specification for a use case."""

    __tablename__ = "use_case_specifications"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    use_case_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("use_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    specification_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("use_case_id", "version", name="uq_use_case_spec_version"),
    )

    use_case: Mapped["UseCase"] = relationship(
        "UseCase",
        back_populates="specifications",
    )
