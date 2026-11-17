"""FastAPI dependencies for authentication, deterministic RBAC, and tenant context resolution."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.tenancy.exceptions import (
    InsufficientPermissionException,
    InvalidCredentialsException,
    MembershipInactiveException,
    NotOrganizationMemberException,
    OrganizationSuspendedException,
)
from corbel.domains.tenancy.models import (
    MembershipStatus,
    Organization,
    OrganizationMember,
    OrgRole,
    OrgStatus,
    SessionStatus,
    User,
    UserSession,
)
from corbel.domains.tenancy.security import AuthenticationException, decode_token

# Bearer token extractor (auto_error=False to allow clean custom exception handling)
oauth2_scheme = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    """Validated operational context for multi-tenant requests."""

    user: User
    organization: Organization
    membership: OrganizationMember

    @property
    def organization_id(self) -> uuid.UUID:
        return self.organization.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.user.id

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_admin(self) -> bool:
        return self.membership.role == OrgRole.ORG_ADMIN.value


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Extract, decode, and validate JWT access token against server-side session state."""
    if credentials is None or not credentials.credentials:
        raise AuthenticationException("Authentication required. Please provide a Bearer token.")

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")
    user_id_str = payload.get("sub")
    session_id_str = payload.get("sid")
    if not user_id_str:
        raise AuthenticationException("Malformed token: missing subject claim")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError as exc:
        raise AuthenticationException("Invalid user ID format in token") from exc

    # Enforce server-side session validation
    if not session_id_str:
        raise AuthenticationException("Malformed token: missing session identifier claim")

    try:
        session_id = uuid.UUID(session_id_str)
    except ValueError as exc:
        raise AuthenticationException("Invalid session ID format in token") from exc

    # Enforce server-side session validation using a single joined query for performance
    stmt = (
        select(UserSession, User)
        .join(User, UserSession.user_id == User.id)
        .where(UserSession.id == session_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise AuthenticationException("Session has been terminated or revoked. Please sign in again.")

    user_session: UserSession = row[0]
    user: User = row[1]
    if (
        user_session.status != SessionStatus.ACTIVE.value
        or user_session.user_id != user_id
    ):
        raise AuthenticationException("Session has been terminated or revoked. Please sign in again.")

    now_utc = datetime.now(UTC)
    if user_session.expires_at < now_utc:
        user_session.status = SessionStatus.EXPIRED.value
        await session.commit()
        raise AuthenticationException("Session has expired. Please sign in again.")

    if not user.is_active:
        raise InvalidCredentialsException("User account is inactive. Access denied.")

    # Attach active session id for downstream handlers (e.g. logout)
    user.active_session_id = session_id
    return user


async def get_active_tenant_context(
    request: Request,
    x_organization_id: str | None = Header(default=None, alias="X-Organization-ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TenantContext:
    """Resolve and deterministically validate the active organization tenant context."""
    from corbel.domains.tenancy.service import TenancyService

    service = TenancyService(session)

    # 1. Determine target organization_id from header or route path parameter
    target_org_id_str = x_organization_id
    if not target_org_id_str and "org_id" in request.path_params:
        target_org_id_str = request.path_params["org_id"]

    target_org_id: uuid.UUID | None = None
    if target_org_id_str:
        try:
            target_org_id = uuid.UUID(target_org_id_str)
        except ValueError as exc:
            raise AuthenticationException("Invalid organization ID format") from exc
    else:
        # Fallback: if user has exactly one active organization, select it automatically
        user_orgs = await service.get_user_organizations(current_user.id)
        active_orgs = [o for o in user_orgs if o.membership_status == MembershipStatus.ACTIVE.value and o.status == OrgStatus.ACTIVE.value]
        if len(active_orgs) == 1:
            target_org_id = active_orgs[0].id
        elif len(active_orgs) == 0:
            raise NotOrganizationMemberException("User has no active organization memberships")
        else:
            raise AuthenticationException(
                "Multiple active organizations available. Please provide an X-Organization-ID header."
            )

    # 2. Strict membership and status verification with single joined query
    stmt = (
        select(OrganizationMember, Organization)
        .join(Organization, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.organization_id == target_org_id,
            OrganizationMember.user_id == current_user.id,
        )
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise NotOrganizationMemberException(target_org_id)

    membership, org = row
    if membership.status != MembershipStatus.ACTIVE.value:
        raise MembershipInactiveException(status=membership.status)

    if org.status != OrgStatus.ACTIVE.value:
        raise OrganizationSuspendedException(org_id=target_org_id)

    return TenantContext(
        user=current_user,
        organization=org,
        membership=membership,
    )


def require_org_roles(allowed_roles: list[OrgRole]) -> Callable[..., Awaitable[TenantContext]]:
    """Dependency factory enforcing that the authenticated user holds one of the required organization roles."""

    async def role_checker(context: TenantContext = Depends(get_active_tenant_context)) -> TenantContext:
        if context.membership.role not in [r.value for r in allowed_roles]:
            raise InsufficientPermissionException(
                required_role=", ".join(r.value for r in allowed_roles)
            )
        return context

    return role_checker


# Convenience dependency for admin-only operations
require_org_admin = require_org_roles([OrgRole.ORG_ADMIN])
