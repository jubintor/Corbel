"""SQLAlchemy ORM models for Tenancy & Access Control (Phase 2)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class OrgRole(str, enum.Enum):
    """Organization-level roles defining administrative and governance permissions."""
    ORG_ADMIN = "ORG_ADMIN"
    MEMBER = "MEMBER"
    AUDITOR = "AUDITOR"


class MembershipStatus(str, enum.Enum):
    """Lifecycle status of a user's membership within an organization."""
    ACTIVE = "ACTIVE"
    INVITED = "INVITED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class SessionStatus(str, enum.Enum):
    """Lifecycle status of a server-side authenticated user session."""
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class OrgStatus(str, enum.Enum):
    """Lifecycle status of an organization tenant."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class ProjectStatus(str, enum.Enum):
    """Operational status of a project workspace."""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ProjectRole(str, enum.Enum):
    """Project-scoped roles defining analytical and execution permissions."""
    PROJECT_LEAD = "PROJECT_LEAD"
    ANALYST = "ANALYST"
    OPERATOR = "OPERATOR"
    APPROVER = "APPROVER"
    VIEWER = "VIEWER"


class Organization(Base):
    """Root multi-tenant boundary representing an enterprise organization."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=OrgStatus.ACTIVE.value, nullable=False)
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
    members: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list["Project"]] = relationship(
        "Project",
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class User(Base):
    """Authenticated human actor capable of belonging to one or more organizations."""

    __tablename__ = "users"
    __allow_unmapped__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    memberships: Mapped[list["OrganizationMember"]] = relationship(
        "OrganizationMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Transient runtime attribute for the active session authorizing the current request
    active_session_id: uuid.UUID | None = None


class OrganizationMember(Base):
    """Membership association connecting a User to an Organization with scoped role and status."""

    __tablename__ = "organization_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), default=OrgRole.MEMBER.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=MembershipStatus.ACTIVE.value, nullable=False)
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
    organization: Mapped["Organization"] = relationship("Organization", back_populates="members")
    user: Mapped["User"] = relationship("User", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_members_org_user"),
    )


class Project(Base):
    """Scoped operational workspace within an Organization (e.g. Procure-to-Pay Optimization)."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.ACTIVE.value, nullable=False)
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
    organization: Mapped["Organization"] = relationship("Organization", back_populates="projects")
    members: Mapped[list["ProjectMember"]] = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
        # Candidate key required by DOMAIN_MODEL.md for same-project composite foreign keys
        UniqueConstraint("organization_id", "id", name="uq_projects_org_id"),
    )


class ProjectMember(Base):
    """Explicit assignment of an active Organization User to a specific Project with contextual role."""

    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_role: Mapped[str] = mapped_column(String(32), default=ProjectRole.VIEWER.value, nullable=False)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="members")
    user: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        # Composite FK enforcing project belongs to the stated organization
        ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_project_members_org_project",
        ),
    )


class UserSession(Base):
    """Server-side authenticated user session.

    Ties together access tokens and refresh tokens. Revoking a session
    immediately invalidates both the session's active refresh tokens and
    any access tokens issued under that session identifier.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=SessionStatus.ACTIVE.value,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class RefreshToken(Base):
    """Persisted refresh token with cryptographic hash, family tracking, and rotation status.

    Guarantees strict single-use semantics: reusing a revoked/rotated token triggers
    immediate family-wide invalidation (replay attack detection).
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")
    session: Mapped["UserSession | None"] = relationship("UserSession", back_populates="refresh_tokens")
