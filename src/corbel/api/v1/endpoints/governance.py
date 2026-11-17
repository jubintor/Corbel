"""API endpoints for Phase 9: Governed Investigation, Approvals & RAG."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.governance.models import (
    ActionStatus,
    ApprovalStatus,
    InvestigationStatus,
)
from corbel.domains.governance.schemas import (
    ActionExecuteRequest,
    ActionExecutionResponse,
    ActionResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    AuditEventListResponse,
    AuditEventResponse,
    DocumentCreateRequest,
    DocumentQueryRequest,
    DocumentQueryResponse,
    DocumentResponse,
    EvidenceResponse,
    InvestigationCreateRequest,
    InvestigationListResponse,
    InvestigationResponse,
    P2PVerticalSliceDemoRequest,
    P2PVerticalSliceDemoResponse,
    RecommendationResponse,
)
from corbel.domains.governance.service import GovernanceService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.service import TenancyService

router = APIRouter(tags=["Governed Investigation, Approvals & RAG"])


def get_governance_service(session: AsyncSession = Depends(get_db_session)) -> GovernanceService:
    tenancy_service = TenancyService(session)
    return GovernanceService(session=session, tenancy_service=tenancy_service)


# ==============================================================================
# 1. Investigation Endpoints
# ==============================================================================


@router.post(
    "/projects/{project_id}/investigations",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Governed Investigation",
    description="Launch an evidence-backed investigation from an operational finding.",
)
async def create_investigation(
    project_id: uuid.UUID,
    req: InvestigationCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> InvestigationResponse:
    inv = await service.create_investigation(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        req=req,
    )
    # Reload with relationships
    inv_detailed = await service.get_investigation(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        investigation_id=inv.id,
    )
    recs = [RecommendationResponse.model_validate(r) for r in inv_detailed.recommendations]
    acts = [
        ActionResponse.model_validate(a)
        for r in inv_detailed.recommendations
        for a in r.actions
    ]
    res = InvestigationResponse.model_validate(inv_detailed)
    res.evidence_count = len(inv_detailed.evidence_items)
    res.recommendations = recs
    res.actions = acts
    return res


@router.get(
    "/projects/{project_id}/investigations",
    response_model=InvestigationListResponse,
    summary="List Investigations",
    description="Retrieve paginated investigations belonging to the active project.",
)
async def list_investigations(
    project_id: uuid.UUID,
    status_filter: InvestigationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> InvestigationListResponse:
    items, total = await service.list_investigations(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    res_items = []
    for inv in items:
        resp = InvestigationResponse.model_validate(inv)
        resp.evidence_count = len(inv.evidence_items)
        resp.recommendations = [RecommendationResponse.model_validate(r) for r in inv.recommendations]
        resp.actions = [ActionResponse.model_validate(a) for r in inv.recommendations for a in r.actions]
        res_items.append(resp)
    return InvestigationListResponse(items=res_items, total=total)


@router.get(
    "/projects/{project_id}/investigations/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Get Investigation Details",
    description="Retrieve complete investigation details with verified facts, hypothesis, evidence, and recommendations.",
)
async def get_investigation(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> InvestigationResponse:
    inv = await service.get_investigation(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        investigation_id=investigation_id,
    )
    resp = InvestigationResponse.model_validate(inv)
    resp.evidence_count = len(inv.evidence_items)
    resp.recommendations = [RecommendationResponse.model_validate(r) for r in inv.recommendations]
    resp.actions = [ActionResponse.model_validate(a) for r in inv.recommendations for a in r.actions]
    return resp


@router.get(
    "/projects/{project_id}/investigations/{investigation_id}/evidence",
    response_model=list[EvidenceResponse],
    summary="List Investigation Evidence",
    description="Retrieve all supporting evidence items captured with strict provenance.",
)
async def list_investigation_evidence(
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> list[EvidenceResponse]:
    evidence = await service.list_evidence(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        investigation_id=investigation_id,
    )
    return [EvidenceResponse.model_validate(e) for e in evidence]


# ==============================================================================
# 2. Documents & RAG Endpoints
# ==============================================================================


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Document for RAG",
    description="Upload and chunk an unstructured business document (e.g. Contract, Terms, Delivery Note) for RAG retrieval.",
)
async def create_document(
    project_id: uuid.UUID,
    req: DocumentCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> DocumentResponse:
    doc = await service.create_document(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        req=req,
    )
    resp = DocumentResponse.model_validate(doc)
    resp.chunk_count = getattr(doc, "_chunk_count", 0)
    return resp


@router.get(
    "/projects/{project_id}/documents",
    response_model=list[DocumentResponse],
    summary="List RAG Documents",
    description="Retrieve all indexed documents for the active project.",
)
async def list_documents(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> list[DocumentResponse]:
    docs = await service.list_documents(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
    )
    res = []
    for d in docs:
        resp = DocumentResponse.model_validate(d)
        resp.chunk_count = len(d.chunks)
        res.append(resp)
    return res


@router.post(
    "/projects/{project_id}/documents/query",
    response_model=DocumentQueryResponse,
    summary="Query RAG Document Chunks",
    description="Retrieve relevant chunks with lexical & semantic relevance scoring and provenance metadata.",
)
async def query_documents(
    project_id: uuid.UUID,
    req: DocumentQueryRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> DocumentQueryResponse:
    return await service.query_documents(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        req=req,
    )


# ==============================================================================
# 3. Actions & Approvals Endpoints
# ==============================================================================


@router.get(
    "/projects/{project_id}/actions",
    response_model=list[ActionResponse],
    summary="List Actions",
    description="Retrieve proposed, approved, and executed actions.",
)
async def list_actions(
    project_id: uuid.UUID,
    status_filter: ActionStatus | None = Query(default=None, alias="status"),
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> list[ActionResponse]:
    actions = await service.list_actions(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        status=status_filter,
    )
    return [ActionResponse.model_validate(a) for a in actions]


@router.get(
    "/projects/{project_id}/approvals",
    response_model=list[ApprovalResponse],
    summary="List Approvals",
    description="Retrieve human approval gates for the project.",
)
async def list_approvals(
    project_id: uuid.UUID,
    status_filter: ApprovalStatus | None = Query(default=None, alias="status"),
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> list[ApprovalResponse]:
    approvals = await service.list_approvals(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        status=status_filter,
    )
    return [ApprovalResponse.model_validate(a) for a in approvals]


@router.post(
    "/projects/{project_id}/approvals/{approval_id}/decide",
    response_model=ApprovalResponse,
    summary="Decide Human Approval Gate",
    description="Authorize or reject a proposed action. Computes canonicalized payload hash upon authorization.",
)
async def decide_approval(
    project_id: uuid.UUID,
    approval_id: uuid.UUID,
    req: ApprovalDecisionRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> ApprovalResponse:
    appr = await service.decide_approval(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        approval_id=approval_id,
        req=req,
    )
    return ApprovalResponse.model_validate(appr)


@router.post(
    "/projects/{project_id}/actions/{action_id}/execute",
    response_model=ActionExecutionResponse,
    summary="Dispatch Approved Action",
    description="Execute an approved action against the target adapter with canonical payload hash verification and idempotency.",
)
async def execute_action(
    project_id: uuid.UUID,
    action_id: uuid.UUID,
    req: ActionExecuteRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> ActionExecutionResponse:
    execution = await service.execute_action(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        action_id=action_id,
        req=req,
    )
    return ActionExecutionResponse.model_validate(execution)


# ==============================================================================
# 4. Authoritative Audit Trail Endpoints
# ==============================================================================


@router.get(
    "/projects/{project_id}/audit-events",
    response_model=AuditEventListResponse,
    summary="List Authoritative Audit Events",
    description="Retrieve append-only historical audit records with provenance and verification hashes.",
)
async def list_audit_events(
    project_id: uuid.UUID,
    action_type: str | None = Query(default=None),
    affected_entity_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> AuditEventListResponse:
    events, total = await service.list_audit_events(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        action_type=action_type,
        affected_entity_type=affected_entity_type,
        limit=limit,
        offset=offset,
    )
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
    )


# ==============================================================================
# 5. P2P Vertical Slice E2E Demonstration Endpoint
# ==============================================================================


@router.post(
    "/projects/{project_id}/demo/p2p-slice",
    response_model=P2PVerticalSliceDemoResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute P2P Vertical Slice Demonstration",
    description="Demonstrate the complete Procure-to-Pay vertical slice: exception -> investigation -> RAG -> recommendation -> approval -> simulated execution -> audit.",
)
async def run_p2p_demo(
    project_id: uuid.UUID,
    req: P2PVerticalSliceDemoRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: GovernanceService = Depends(get_governance_service),
) -> P2PVerticalSliceDemoResponse:
    return await service.run_p2p_vertical_slice_demo(
        organization_id=context.organization_id,
        project_id=project_id,
        user_id=context.user.id,
        req=req,
    )
