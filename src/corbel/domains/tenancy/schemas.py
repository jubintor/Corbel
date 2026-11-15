"""Pydantic v2 schemas for Tenancy & Access Control subdomain."""

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from corbel.domains.tenancy.models import (
    MembershipStatus,
    OrgRole,
    OrgStatus,
    ProjectRole,
    ProjectStatus,
)


def slugify(text: str) -> str:
    """Generate clean URL slug from input text."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


# ==============================================================================
# Authentication Schemas
# ==============================================================================

class UserRegisterRequest(BaseModel):
    """Payload for registering a new user."""

    email: str = Field(..., description="User corporate or standard email address")
    password: str = Field(..., min_length=8, description="Plaintext password (minimum 8 characters)")
    full_name: str = Field(..., min_length=1, max_length=255, description="Full human name")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", clean):
            raise ValueError("Invalid email address format")
        return clean


class UserLoginRequest(BaseModel):
    """Payload for user authentication."""

    email: str = Field(..., description="Registered email address")
    password: str = Field(..., description="User password")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshTokenRequest(BaseModel):
    """Payload for refreshing an expired access token."""

    refresh_token: str = Field(..., description="Valid cryptographically signed refresh token")


class TokenResponse(BaseModel):
    """OAuth2 / JWT compatible token response."""

    access_token: str = Field(..., description="Signed JWT access token")
    refresh_token: str = Field(..., description="Signed JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration window in seconds")


class UserResponse(BaseModel):
    """Public user profile model (never leaks password hashes)."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserUpdateRequest(BaseModel):
    """Payload for updating user profile."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)


# ==============================================================================
# Organization Schemas
# ==============================================================================

class OrganizationCreateRequest(BaseModel):
    """Payload for creating a new enterprise tenant organization."""

    name: str = Field(..., min_length=2, max_length=255, description="Organization legal or business name")
    slug: str | None = Field(default=None, max_length=128, description="URL-safe unique identifier")

    @field_validator("slug", mode="before")
    @classmethod
    def auto_slug(cls, v: str | None) -> str | None:
        if v:
            return slugify(v)
        return None


class OrganizationUpdateRequest(BaseModel):
    """Payload for modifying an organization."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    status: OrgStatus | None = None


class OrganizationResponse(BaseModel):
    """Organization metadata schema."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationWithRoleResponse(BaseModel):
    """Organization metadata with contextual membership role and status for active user."""

    id: uuid.UUID
    name: str
    slug: str
    status: str
    role: str
    membership_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Membership Schemas
# ==============================================================================

class MemberAddRequest(BaseModel):
    """Payload for adding or inviting a user to an organization."""

    email: str = Field(..., description="Email address of the user to add")
    role: OrgRole = Field(default=OrgRole.MEMBER, description="Organization role")

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class MemberRoleUpdateRequest(BaseModel):
    """Payload for updating an organization member's role."""

    role: OrgRole = Field(..., description="New organization role")


class MemberStatusUpdateRequest(BaseModel):
    """Payload for activating, suspending or revoking an organization membership."""

    status: MembershipStatus = Field(..., description="New membership status")


class MemberResponse(BaseModel):
    """Organization member response model."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==============================================================================
# Project Schemas
# ==============================================================================

class ProjectCreateRequest(BaseModel):
    """Payload for creating a project workspace within an organization."""

    name: str = Field(..., min_length=2, max_length=255, description="Project workspace name")
    slug: str | None = Field(default=None, max_length=128, description="URL-safe unique project slug")
    description: str | None = Field(default=None, max_length=1024, description="Optional workspace description")


class ProjectUpdateRequest(BaseModel):
    """Payload for updating project workspace metadata."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    status: ProjectStatus | None = None


class ProjectResponse(BaseModel):
    """Project workspace response schema."""

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectMemberAddRequest(BaseModel):
    """Payload for assigning an organization user to a project."""

    user_id: uuid.UUID = Field(..., description="User ID belonging to the same Organization")
    project_role: ProjectRole = Field(default=ProjectRole.VIEWER, description="Project-scoped role")


class ProjectMemberResponse(BaseModel):
    """Project member response schema."""

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    project_role: str
    granted_at: datetime

    model_config = ConfigDict(from_attributes=True)
