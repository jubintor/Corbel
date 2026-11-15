"""Project workspace API endpoints strictly enforcing multi-tenant isolation."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.models import User
from corbel.domains.tenancy.schemas import (
    ProjectCreateRequest,
    ProjectMemberAddRequest,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from corbel.domains.tenancy.service import TenancyService

router = APIRouter()


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project Workspace",
    description="Create a project workspace scoped strictly to the authorized active tenant organization.",
)
async def create_project(
    req: ProjectCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Create a project within the active organization."""
    service = TenancyService(session)
    project = await service.create_project(context.organization_id, context.user_id, req)
    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List Projects",
    description="List all project workspaces belonging strictly to the active tenant organization.",
)
async def list_projects(
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectResponse]:
    """List projects in active tenant context."""
    service = TenancyService(session)
    projects = await service.list_projects(context.organization_id, context.user_id)
    return [ProjectResponse.model_validate(p) for p in projects]


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Project Details",
    description="Retrieve project workspace metadata within the authorized tenant context.",
)
async def get_project(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Fetch project details enforcing organization ownership."""
    service = TenancyService(session)
    project = await service.get_project(context.organization_id, project_id, context.user_id)
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Project Workspace",
    description="Update project workspace metadata within the active tenant context.",
)
async def update_project(
    project_id: uuid.UUID,
    req: ProjectUpdateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    """Update project details."""
    service = TenancyService(session)
    project = await service.update_project(context.organization_id, project_id, context.user_id, req)
    return ProjectResponse.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Project Workspace",
    description="Delete project workspace within authorized tenant.",
)
async def delete_project(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Delete project workspace."""
    service = TenancyService(session)
    await service.delete_project(context.organization_id, project_id, context.user_id)
    return {"message": "Project workspace deleted successfully"}


# ==============================================================================
# Project Membership Endpoints (Same-Organization Invariant Enforced)
# ==============================================================================

@router.get(
    "/{project_id}/members",
    response_model=list[ProjectMemberResponse],
    status_code=status.HTTP_200_OK,
    summary="List Project Members",
    description="List all members assigned to this project workspace.",
)
async def list_project_members(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectMemberResponse]:
    """List members assigned to the project."""
    service = TenancyService(session)
    rows = await service.list_project_members(context.organization_id, project_id, context.user_id)
    return [
        ProjectMemberResponse(
            id=pm.id,
            organization_id=pm.organization_id,
            project_id=pm.project_id,
            user_id=pm.user_id,
            email=u.email,
            full_name=u.full_name,
            project_role=pm.project_role,
            granted_at=pm.granted_at,
        )
        for pm, u in rows
    ]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Project Member",
    description="Assign an organization user to the project. Target user MUST belong to the same Organization.",
)
async def add_project_member(
    project_id: uuid.UUID,
    req: ProjectMemberAddRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> ProjectMemberResponse:
    """Assign user to project with cross-tenant validation."""
    service = TenancyService(session)
    pm = await service.add_project_member(
        context.organization_id,
        project_id,
        context.user_id,
        req.user_id,
        req.project_role,
    )
    target_user = await session.get(User, pm.user_id)
    assert target_user is not None
    return ProjectMemberResponse(
        id=pm.id,
        organization_id=pm.organization_id,
        project_id=pm.project_id,
        user_id=pm.user_id,
        email=target_user.email,
        full_name=target_user.full_name,
        project_role=pm.project_role,
        granted_at=pm.granted_at,
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove Project Member",
    description="Remove a user assignment from the project workspace.",
)
async def remove_project_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Remove user from project."""
    service = TenancyService(session)
    await service.remove_project_member(context.organization_id, project_id, context.user_id, user_id)
    return {"message": "Project member assignment removed successfully"}
