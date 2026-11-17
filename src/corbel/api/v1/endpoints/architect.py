"""API endpoints for Phase 11: Use-Case Architect."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.costs.service import CostService
from corbel.core.database import get_db_session
from corbel.domains.governance.audit import AuditService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.service import TenancyService
from corbel.domains.use_case_architect.schemas import (
    DiscoveryTurnResponse,
    SpecificationDiffResponse,
    SpecificationVersionSummary,
    UseCaseCreateRequest,
    UseCaseDetailResponse,
    UseCaseMessageCreateRequest,
    UseCaseResponse,
    UseCaseSpecification,
    UseCaseUpdateRequest,
)
from corbel.domains.use_case_architect.service import UseCaseArchitectService

router = APIRouter(prefix="/projects/{project_id}/use-cases", tags=["Use-Case Architect"])


def get_architect_service(
    session: AsyncSession = Depends(get_db_session),
) -> UseCaseArchitectService:
    """Dependency provider for UseCaseArchitectService."""
    tenancy_service = TenancyService(session)
    audit_service = AuditService(session)
    cost_service = CostService(session)
    return UseCaseArchitectService(
        session=session,
        tenancy_service=tenancy_service,
        audit_service=audit_service,
        cost_service=cost_service,
    )


# ==============================================================================
# Use Case CRUD & Discovery Endpoints
# ==============================================================================


@router.post("", response_model=UseCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_use_case(
    project_id: uuid.UUID,
    payload: UseCaseCreateRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseResponse:
    """Create a new business use case and initiate discovery."""
    return await service.create_use_case(
        organization_id=ctx.organization_id,
        project_id=project_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.get("", response_model=list[UseCaseResponse])
async def list_use_cases(
    project_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> list[UseCaseResponse]:
    """List all use cases in the project."""
    return await service.list_use_cases(
        organization_id=ctx.organization_id,
        project_id=project_id,
        user_id=ctx.user_id,
    )


@router.get("/{use_case_id}", response_model=UseCaseDetailResponse)
async def get_use_case(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseDetailResponse:
    """Get complete details, messages, and latest specification for a use case."""
    return await service.get_use_case(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
    )


@router.put("/{use_case_id}", response_model=UseCaseResponse)
async def update_use_case(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    payload: UseCaseUpdateRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseResponse:
    """Update title or description of an unapproved use case."""
    return await service.update_use_case(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.delete("/{use_case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_use_case(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> None:
    """Delete a use case. Requires Lead or Org Admin."""
    await service.delete_use_case(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
    )


@router.post("/{use_case_id}/messages", response_model=DiscoveryTurnResponse)
async def add_discovery_message(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    payload: UseCaseMessageCreateRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> DiscoveryTurnResponse:
    """Post a user response in the discovery dialogue and execute bounded turn."""
    return await service.add_discovery_message(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
        message_text=payload.message_text,
    )


# ==============================================================================
# Specification Synthesis, Versioning & Approval Endpoints
# ==============================================================================


@router.post(
    "/{use_case_id}/specifications/generate",
    response_model=UseCaseSpecification,
    status_code=status.HTTP_201_CREATED,
)
async def generate_specification(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseSpecification:
    """Generate a structured, versioned specification based on discovery requirements."""
    return await service.generate_specification(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
    )


@router.get(
    "/{use_case_id}/specifications",
    response_model=list[SpecificationVersionSummary],
)
async def list_specifications(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> list[SpecificationVersionSummary]:
    """List all specification revisions for a use case."""
    return await service.list_specifications(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
    )


@router.get(
    "/{use_case_id}/specifications/compare",
    response_model=SpecificationDiffResponse,
)
async def compare_specifications(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    v1: int = Query(..., ge=1),
    v2: int = Query(..., ge=1),
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> SpecificationDiffResponse:
    """Compare two specification revisions and return field diffs."""
    return await service.compare_specifications(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        v1=v1,
        v2=v2,
        user_id=ctx.user_id,
    )


@router.get(
    "/{use_case_id}/specifications/{version}",
    response_model=UseCaseSpecification,
)
async def get_specification_version(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    version: int,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseSpecification:
    """Retrieve a specific version of a specification."""
    return await service.get_specification_version(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        version=version,
        user_id=ctx.user_id,
    )


@router.post(
    "/{use_case_id}/specifications/approve",
    response_model=UseCaseResponse,
)
async def approve_specification(
    project_id: uuid.UUID,
    use_case_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: UseCaseArchitectService = Depends(get_architect_service),
) -> UseCaseResponse:
    """Approve the current specification design. Requires Project Lead or Org Admin."""
    return await service.approve_specification(
        organization_id=ctx.organization_id,
        project_id=project_id,
        use_case_id=use_case_id,
        user_id=ctx.user_id,
    )
