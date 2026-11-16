"""API endpoints for Phase 7: Adaptive Monitors & Exception Detection."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.monitors.models import FindingStatus, RuleSeverity
from corbel.domains.monitors.schemas import (
    BusinessRuleCreate,
    BusinessRuleResponse,
    FindingResponse,
    FindingStatusUpdate,
    MonitorCreate,
    MonitorEvaluationResponse,
    MonitorEvaluationRunRequest,
    MonitorResponse,
    MonitorUpdate,
)
from corbel.domains.monitors.service import MonitorService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.service import TenancyService

router = APIRouter(tags=["Adaptive Monitors & Exception Detection"])


def get_monitor_service(session: AsyncSession = Depends(get_db_session)) -> MonitorService:
    tenancy_service = TenancyService(session)
    return MonitorService(session=session, tenancy_service=tenancy_service)


# -----------------------------------------------------------------------------
# Monitor Configuration & Lifecycle Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/monitors",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Operational Monitor",
    description="Configure a new operational monitor for a business entity or process with deterministic rules.",
)
async def create_monitor(
    project_id: uuid.UUID,
    req: MonitorCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    return await service.create_monitor(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )


@router.get(
    "/projects/{project_id}/monitors",
    response_model=list[MonitorResponse],
    status_code=status.HTTP_200_OK,
    summary="List Project Monitors",
    description="Retrieve all operational monitors configured in the active project with findings counts.",
)
async def list_monitors(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> list[MonitorResponse]:
    return await service.list_monitors(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )


@router.get(
    "/projects/{project_id}/monitors/{monitor_id}",
    response_model=MonitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Monitor Details",
    description="Retrieve detailed configuration, rules, and findings overview for a specific monitor.",
)
async def get_monitor(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    return await service.get_monitor(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
    )


@router.put(
    "/projects/{project_id}/monitors/{monitor_id}",
    response_model=MonitorResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Monitor",
    description="Update monitor metadata, schedule, or activation status (ACTIVE/PAUSED).",
)
async def update_monitor(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    req: MonitorUpdate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorResponse:
    return await service.update_monitor(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        req=req,
    )


@router.delete(
    "/projects/{project_id}/monitors/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Monitor",
    description="Remove an operational monitor and cascade delete its configured rules and evaluation logs.",
)
async def delete_monitor(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> None:
    await service.delete_monitor(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
    )


@router.post(
    "/projects/{project_id}/monitors/{monitor_id}/rules",
    response_model=BusinessRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Rule to Monitor",
    description="Attach an additional deterministic business rule or threshold constraint to an existing monitor.",
)
async def add_rule(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    req: BusinessRuleCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> BusinessRuleResponse:
    return await service.add_rule(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        req=req,
    )


@router.delete(
    "/projects/{project_id}/monitors/{monitor_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Rule from Monitor",
    description="Remove a business rule constraint from an operational monitor.",
)
async def delete_rule(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    rule_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> None:
    await service.delete_rule(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        rule_id=rule_id,
    )


# -----------------------------------------------------------------------------
# Monitor Evaluation Engine Execution
# -----------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/monitors/{monitor_id}/evaluate",
    response_model=MonitorEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger Monitor Evaluation",
    description="Execute deterministic rule evaluation against project data and emit deduplicated exception findings.",
)
async def evaluate_monitor(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID,
    req: MonitorEvaluationRunRequest = MonitorEvaluationRunRequest(),
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> MonitorEvaluationResponse:
    return await service.evaluate_monitor(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        limit=req.limit,
    )


@router.get(
    "/projects/{project_id}/evaluations",
    response_model=list[MonitorEvaluationResponse],
    status_code=status.HTTP_200_OK,
    summary="List Monitor Evaluation History",
    description="Retrieve execution audit history for monitor evaluation runs within a project.",
)
async def list_evaluations(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID | None = Query(default=None, description="Filter by monitor ID"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> list[MonitorEvaluationResponse]:
    return await service.list_evaluations(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        limit=limit,
        offset=offset,
    )


# -----------------------------------------------------------------------------
# Finding / Exception Management Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/findings",
    response_model=list[FindingResponse],
    status_code=status.HTTP_200_OK,
    summary="List Operational Findings",
    description="Retrieve operational exception findings with optional filtering by monitor, status, and severity.",
)
async def list_findings(
    project_id: uuid.UUID,
    monitor_id: uuid.UUID | None = Query(default=None, description="Filter by monitor ID"),
    finding_status: FindingStatus | None = Query(default=None, alias="status", description="Filter by finding status"),
    severity: RuleSeverity | None = Query(default=None, description="Filter by severity level"),
    limit: int = Query(default=50, ge=1, le=500, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> list[FindingResponse]:
    return await service.list_findings(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        monitor_id=monitor_id,
        finding_status=finding_status,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/findings/{finding_id}",
    response_model=FindingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Finding Detail",
    description="Retrieve complete factual details and verified context for an operational exception finding.",
)
async def get_finding(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> FindingResponse:
    return await service.get_finding(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        finding_id=finding_id,
    )


@router.patch(
    "/projects/{project_id}/findings/{finding_id}/status",
    response_model=FindingResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Finding Status",
    description="Transition finding lifecycle state (e.g. ACKNOWLEDGED, RESOLVED, DISMISSED) with resolution audit.",
)
async def update_finding_status(
    project_id: uuid.UUID,
    finding_id: uuid.UUID,
    req: FindingStatusUpdate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: MonitorService = Depends(get_monitor_service),
) -> FindingResponse:
    return await service.update_finding_status(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        finding_id=finding_id,
        req=req,
    )
