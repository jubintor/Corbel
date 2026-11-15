"""API endpoints for Phase 6: Process Intelligence & Event Mining."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.process_intelligence.schemas import (
    DFGResponse,
    ProcessCaseDetailResponse,
    ProcessCasesListResponse,
    ProcessCreate,
    ProcessEventBatchIngestRequest,
    ProcessOverviewResponse,
    ProcessReconstructRequest,
    ProcessReconstructResponse,
    ProcessResponse,
    ProcessUpdate,
    ProcessVariantsResponse,
)
from corbel.domains.process_intelligence.service import ProcessService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.service import TenancyService

router = APIRouter(tags=["Process Intelligence & Event Mining"])


def get_process_service(session: AsyncSession = Depends(get_db_session)) -> ProcessService:
    tenancy_service = TenancyService(session)
    return ProcessService(session=session, tenancy_service=tenancy_service)


@router.post(
    "/projects/{project_id}/process",
    response_model=ProcessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Process Definition",
    description="Define a new operational process workflow (e.g. Procure-to-Pay) with target cycle time.",
)
async def create_process(
    project_id: uuid.UUID,
    req: ProcessCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessResponse:
    return await service.create_process(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )


@router.get(
    "/projects/{project_id}/process",
    response_model=list[ProcessResponse],
    status_code=status.HTTP_200_OK,
    summary="List Project Processes",
    description="Retrieve all operational process definitions configured for the project.",
)
async def list_processes(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> list[ProcessResponse]:
    return await service.list_processes(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}",
    response_model=ProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Process Definition",
    description="Retrieve details and metrics counts for a specific process definition.",
)
async def get_process(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessResponse:
    return await service.get_process(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
    )


@router.put(
    "/projects/{project_id}/process/{process_id}",
    response_model=ProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Process Definition",
    description="Update a process definition's name, description, target duration SLA, or active state.",
)
async def update_process(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    req: ProcessUpdate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessResponse:
    return await service.update_process(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
        req=req,
    )


@router.delete(
    "/projects/{project_id}/process/{process_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Process Definition",
    description="Delete a process definition and cascade deletion to all its cases and events.",
)
async def delete_process(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> None:
    await service.delete_process(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
    )


@router.post(
    "/projects/{project_id}/process/{process_id}/events/batch",
    response_model=ProcessReconstructResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch Ingest Process Events",
    description="Ingest a list of atomic activity events, deterministically assembling cases and variant sequences.",
)
async def batch_ingest_events(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    req: ProcessEventBatchIngestRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessReconstructResponse:
    return await service.ingest_events(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
        req=req,
    )


@router.post(
    "/projects/{project_id}/process/{process_id}/reconstruct",
    response_model=ProcessReconstructResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconstruct Process from Datasets",
    description="Reconstruct event logs, cases, and variants from tabular datasets or confirmed P2P ontology entities.",
)
async def reconstruct_process(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    req: ProcessReconstructRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessReconstructResponse:
    return await service.reconstruct_process(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
        req=req,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}/overview",
    response_model=ProcessOverviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Process Overview & Performance KPIs",
    description="Retrieve high-level cycle time statistics, SLA compliance rates, rework percentages, and bottleneck identification.",
)
async def get_process_overview(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessOverviewResponse:
    return await service.get_process_overview(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}/variants",
    response_model=ProcessVariantsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Process Variants",
    description="Discover and rank all unique process execution paths sorted by execution frequency.",
)
async def get_process_variants(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessVariantsResponse:
    return await service.get_process_variants(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}/dfg",
    response_model=DFGResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Directly-Follows Graph (DFG)",
    description="Compute the full Directly-Follows Graph with activity frequencies, transition counts, average durations, and bottleneck highlights.",
)
async def get_directly_follows_graph(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> DFGResponse:
    return await service.get_directly_follows_graph(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}/cases",
    response_model=ProcessCasesListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Process Cases",
    description="Explore individual process case instances with optional variant filtering, status filtering, and pagination.",
)
async def list_cases(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    variant_key: str | None = Query(default=None, description="Filter by variant sequence key"),
    status_val: str | None = Query(default=None, alias="status", description="Filter by status (e.g. COMPLETED, ACTIVE)"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessCasesListResponse:
    return await service.list_cases(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
        variant_key=variant_key,
        status=status_val,
        page=page,
        limit=limit,
    )


@router.get(
    "/projects/{project_id}/process/{process_id}/cases/{case_id}",
    response_model=ProcessCaseDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Case Detail & Event Timeline",
    description="Retrieve a case's chronological milestone event sequence and operational attributes.",
)
async def get_case_detail(
    project_id: uuid.UUID,
    process_id: uuid.UUID,
    case_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: ProcessService = Depends(get_process_service),
) -> ProcessCaseDetailResponse:
    return await service.get_case_detail(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        process_id=process_id,
        case_id=case_id,
    )
