"""Organization management API endpoints (Multi-Tenancy & Membership)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.tenancy.dependencies import get_current_user
from corbel.domains.tenancy.models import User
from corbel.domains.tenancy.schemas import (
    MemberAddRequest,
    MemberResponse,
    MemberRoleUpdateRequest,
    MemberStatusUpdateRequest,
    OrganizationCreateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
    OrganizationWithRoleResponse,
)
from corbel.domains.tenancy.service import TenancyService

router = APIRouter()


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Organization",
    description="Establish a new enterprise tenant organization. Creator is granted ORG_ADMIN role.",
)
async def create_organization(
    req: OrganizationCreateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    """Create a new tenant organization."""
    service = TenancyService(session)
    org = await service.create_organization(current_user.id, req)
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=list[OrganizationWithRoleResponse],
    status_code=status.HTTP_200_OK,
    summary="List My Organizations",
    description="List all organizations the current authenticated user belongs to with role and status.",
)
async def list_user_organizations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[OrganizationWithRoleResponse]:
    """Retrieve all organizations for the current user."""
    service = TenancyService(session)
    return await service.get_user_organizations(current_user.id)


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Organization Details",
    description="Retrieve details of a specific organization. Requires active membership.",
)
async def get_organization(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    """Fetch organization metadata."""
    service = TenancyService(session)
    org = await service.get_organization(org_id, current_user.id)
    return OrganizationResponse.model_validate(org)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Organization",
    description="Update organization properties. Requires ORG_ADMIN privileges.",
)
async def update_organization(
    org_id: uuid.UUID,
    req: OrganizationUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OrganizationResponse:
    """Update organization details."""
    service = TenancyService(session)
    org = await service.update_organization(org_id, current_user.id, req)
    return OrganizationResponse.model_validate(org)


# ==============================================================================
# Membership Endpoints
# ==============================================================================

@router.get(
    "/{org_id}/members",
    response_model=list[MemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List Organization Members",
    description="List all members of an organization. Requires membership in the organization.",
)
async def list_members(
    org_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MemberResponse]:
    """List members within an organization."""
    service = TenancyService(session)
    rows = await service.list_organization_members(org_id, current_user.id)
    return [
        MemberResponse(
            id=member.id,
            organization_id=member.organization_id,
            user_id=member.user_id,
            email=user.email,
            full_name=user.full_name,
            role=member.role,
            status=member.status,
            created_at=member.created_at,
        )
        for member, user in rows
    ]


@router.post(
    "/{org_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Organization Member",
    description="Add a registered user to the organization by email. Requires ORG_ADMIN privileges.",
)
async def add_member(
    org_id: uuid.UUID,
    req: MemberAddRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Add a member to the organization."""
    service = TenancyService(session)
    member = await service.add_organization_member(org_id, current_user.id, req)
    target_user = await session.get(User, member.user_id)
    assert target_user is not None
    return MemberResponse(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.patch(
    "/{org_id}/members/{user_id}/role",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Member Role",
    description="Modify a user's role in the organization. Requires ORG_ADMIN privileges.",
)
async def update_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    req: MemberRoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Update role of an organization member."""
    service = TenancyService(session)
    member = await service.update_member_role(org_id, current_user.id, user_id, req.role)
    target_user = await session.get(User, member.user_id)
    assert target_user is not None
    return MemberResponse(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.patch(
    "/{org_id}/members/{user_id}/status",
    response_model=MemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Member Status",
    description="Update an organization member's status (ACTIVE, SUSPENDED, REVOKED). Suspended/revoked status terminates active sessions. Requires ORG_ADMIN privileges.",
)
async def update_member_status(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    req: MemberStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MemberResponse:
    """Update status of an organization member."""
    service = TenancyService(session)
    member = await service.update_member_status(org_id, current_user.id, user_id, req.status)
    target_user = await session.get(User, member.user_id)
    assert target_user is not None
    return MemberResponse(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        role=member.role,
        status=member.status,
        created_at=member.created_at,
    )


@router.delete(
    "/{org_id}/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove Organization Member",
    description="Remove a member from the organization. Requires ORG_ADMIN privileges.",
)
async def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Remove member from organization."""
    service = TenancyService(session)
    await service.remove_member(org_id, current_user.id, user_id)
    return {"message": "Member removed successfully"}
