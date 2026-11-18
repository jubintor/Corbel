"""API endpoints for Phase 12: Application Builder & Runtime."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.app_builder.catalogue import list_catalogue_specs
from corbel.domains.app_builder.schemas import (
    ApplicationCreateRequest,
    ApplicationDefinition,
    ApplicationDetailResponse,
    ApplicationPublishRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
    ApplicationValidationResponse,
    ApplicationVersionSummary,
    PublishedApplicationRuntimeResponse,
    RuntimeActionExecuteRequest,
    RuntimeActionExecuteResponse,
    RuntimeDataQueryRequest,
    RuntimeDataQueryResponse,
)
from corbel.domains.app_builder.service import ApplicationBuilderService
from corbel.domains.governance.audit import AuditService
from corbel.domains.governance.service import GovernanceService
from corbel.domains.query.service import QueryService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.service import TenancyService

router = APIRouter(prefix="/projects/{project_id}/applications", tags=["Application Builder"])


def get_app_builder_service(
    session: AsyncSession = Depends(get_db_session),
) -> ApplicationBuilderService:
    """Dependency provider for ApplicationBuilderService."""
    tenancy_service = TenancyService(session)
    audit_service = AuditService(session)
    query_service = QueryService(session)
    governance_service = GovernanceService(session=session, tenancy_service=tenancy_service)
    return ApplicationBuilderService(
        session=session,
        tenancy_service=tenancy_service,
        audit_service=audit_service,
        query_service=query_service,
        governance_service=governance_service,
    )


# ==============================================================================
# Component Catalogue Endpoint
# ==============================================================================


@router.get("/components/catalogue", response_model=list[dict[str, Any]])
async def get_catalogue_components(
    project_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
) -> list[dict[str, Any]]:
    """Return catalogue of available components, specifications, and data-binding rules."""
    return list_catalogue_specs()


# ==============================================================================
# Application CRUD Endpoints
# ==============================================================================


@router.post("", response_model=ApplicationDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    project_id: uuid.UUID,
    payload: ApplicationCreateRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationDetailResponse:
    """Create a new application from an approved use-case specification or blank blueprint."""
    return await service.create_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.get("", response_model=list[ApplicationResponse])
async def list_applications(
    project_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> list[ApplicationResponse]:
    """List all applications in the project."""
    return await service.list_applications(
        organization_id=ctx.organization_id,
        project_id=project_id,
        user_id=ctx.user_id,
    )


@router.get("/{app_id}", response_model=ApplicationDetailResponse)
async def get_application(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationDetailResponse:
    """Get full details of an application including draft and published definitions."""
    return await service.get_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
    )


@router.put("/{app_id}", response_model=ApplicationDetailResponse)
async def update_application(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    payload: ApplicationUpdateRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationDetailResponse:
    """Update application metadata or draft definition."""
    return await service.update_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> None:
    """Delete an application and all its versions. Requires Project Lead or Admin."""
    await service.delete_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
    )


# ==============================================================================
# Validation, Versioning & Publishing Endpoints
# ==============================================================================


@router.post("/{app_id}/validate", response_model=ApplicationValidationResponse)
async def validate_application(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    payload: ApplicationDefinition | None = None,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationValidationResponse:
    """Validate application blueprint structure, components, and data bindings."""
    return await service.validate_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.post("/{app_id}/publish", response_model=ApplicationDetailResponse)
async def publish_application(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    payload: ApplicationPublishRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationDetailResponse:
    """Publish the validated draft as an immutable runtime version. Requires Project Lead."""
    return await service.publish_application(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
        payload=payload,
    )


@router.get("/{app_id}/versions", response_model=list[ApplicationVersionSummary])
async def list_versions(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> list[ApplicationVersionSummary]:
    """List all immutable historical versions of an application."""
    return await service.list_versions(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
    )


@router.get("/{app_id}/versions/{version}", response_model=ApplicationDefinition)
async def get_version(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    version: int,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> ApplicationDefinition:
    """Retrieve an immutable historical version of the application blueprint."""
    return await service.get_version(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        version=version,
        user_id=ctx.user_id,
    )


# ==============================================================================
# Runtime Portal & Component Execution Endpoints
# ==============================================================================


@router.get("/{app_id}/runtime", response_model=PublishedApplicationRuntimeResponse)
async def get_published_runtime(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> PublishedApplicationRuntimeResponse:
    """Serve the published application blueprint for rendering in the portal."""
    return await service.get_published_runtime(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
    )


@router.post("/{app_id}/runtime/data", response_model=RuntimeDataQueryResponse)
async def resolve_runtime_data(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    payload: RuntimeDataQueryRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> RuntimeDataQueryResponse:
    """Execute an authorized query for an application component."""
    return await service.resolve_runtime_data(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
        request=payload,
    )


@router.post("/{app_id}/runtime/action", response_model=RuntimeActionExecuteResponse)
async def execute_runtime_action(
    project_id: uuid.UUID,
    app_id: uuid.UUID,
    payload: RuntimeActionExecuteRequest,
    ctx: TenantContext = Depends(get_active_tenant_context),
    service: ApplicationBuilderService = Depends(get_app_builder_service),
) -> RuntimeActionExecuteResponse:
    """Trigger a governed platform interaction from an application component."""
    return await service.execute_runtime_action(
        organization_id=ctx.organization_id,
        project_id=project_id,
        app_id=app_id,
        user_id=ctx.user_id,
        request=payload,
    )
