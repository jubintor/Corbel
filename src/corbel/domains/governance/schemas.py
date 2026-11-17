"""Pydantic v2 schemas for Phase 9: Governed Investigation, Approvals & RAG."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from corbel.domains.governance.models import (
    ActionStatus,
    ActionType,
    ActorType,
    ApprovalStatus,
    DocumentType,
    EvidenceSourceType,
    ExecutionStatus,
    InvestigationStatus,
    RiskLevel,
)

# ==============================================================================
# 1. RAG & Documents
# ==============================================================================


class DocumentCreateRequest(BaseModel):
    """Request to upload an unstructured document for RAG indexing."""

    title: str = Field(..., min_length=1, max_length=255)
    document_type: DocumentType = DocumentType.CONTRACT
    file_name: str = Field(..., min_length=1, max_length=255)
    file_format: str = Field(default="TXT", max_length=32)
    version_tag: str = Field(default="v1.0", max_length=32)
    raw_text: str = Field(..., min_length=10)
    metadata_json: dict[str, Any] | None = None


class DocumentChunkResponse(BaseModel):
    """Serialized document chunk retrieved or indexed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    section_heading: str | None = None
    chunk_text: str
    token_count: int
    created_at: datetime


class DocumentResponse(BaseModel):
    """Document summary with metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    document_type: str
    file_name: str
    file_format: str
    version_tag: str
    metadata_json: dict[str, Any] | None = None
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentQueryRequest(BaseModel):
    """Query parameters for RAG retrieval."""

    query_text: str = Field(..., min_length=2)
    document_type: DocumentType | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class DocumentQueryResult(BaseModel):
    """Single matching chunk with relevance and provenance."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    file_name: str
    version_tag: str
    section_heading: str | None = None
    chunk_text: str
    relevance_score: float
    is_untrusted: bool = True
    retrieval_method: str = "HYBRID_RRF"


class DocumentQueryResponse(BaseModel):
    """List of retrieved document chunks with retrieval metadata."""

    query_text: str
    results: list[DocumentQueryResult]
    total_retrieved: int


# ==============================================================================
# 2. Evidence
# ==============================================================================


class EvidenceResponse(BaseModel):
    """Captured investigative evidence item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    investigation_id: uuid.UUID
    evidence_type: EvidenceSourceType
    source_identifier: str
    document_name: str | None = None
    dataset_version_id: uuid.UUID | None = None
    section_or_chunk: str | None = None
    content_snippet: str
    structured_data_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    is_verified_fact: bool
    evidence_classification: str = "TRANSACTION_FACT"
    retrieved_at: datetime


# ==============================================================================
# 3. Recommendations & Actions
# ==============================================================================


class RecommendationResponse(BaseModel):
    """Structured proposal produced by an investigation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    investigation_id: uuid.UUID
    title: str
    description: str
    confidence_score: float
    risk_level: RiskLevel
    recommended_action_type: ActionType
    suggested_payload_json: dict[str, Any]
    created_at: datetime


class ActionResponse(BaseModel):
    """Proposed or executed action."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    recommendation_id: uuid.UUID
    action_type: ActionType
    target_system: str
    proposed_payload_json: dict[str, Any]
    is_consequential: bool
    status: ActionStatus
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(BaseModel):
    """Human decision payload for an approval gate."""

    decision: ApprovalStatus = Field(..., description="Must be APPROVED or REJECTED")
    rationale: str | None = Field(default=None, max_length=1024)


class ApprovalResponse(BaseModel):
    """Human authorization gate record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_id: uuid.UUID
    assigned_role: str
    decided_by_user_id: uuid.UUID | None = None
    status: ApprovalStatus
    approved_payload_hash: str | None = None
    approved_payload_json: dict[str, Any] | None = None
    decision_rationale: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ActionExecuteRequest(BaseModel):
    """Request to dispatch an approved action to target adapter."""

    idempotency_key: str = Field(..., min_length=8, max_length=128)
    simulated_failure: bool = Field(default=False, description="Simulate adapter failure for resilience testing")


class ActionExecutionResponse(BaseModel):
    """Target-system execution outcome record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action_id: uuid.UUID
    approval_id: uuid.UUID
    idempotency_key: str
    target_adapter_type: str
    status: ExecutionStatus
    attempt_count: int
    dispatched_payload_json: dict[str, Any]
    dispatched_payload_hash: str
    adapter_response_json: dict[str, Any] | None = None
    error_message: str | None = None
    dispatched_at: datetime
    completed_at: datetime | None = None


# ==============================================================================
# 4. Investigation
# ==============================================================================


class InvestigationCreateRequest(BaseModel):
    """Request to initiate an investigation on an operational finding."""

    finding_id: uuid.UUID
    title: str | None = Field(default=None, max_length=255)
    include_rag_documents: bool = Field(default=True)


class InvestigationResponse(BaseModel):
    """Complete investigation record with verified facts, hypothesis, and impact."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    finding_id: uuid.UUID
    status: InvestigationStatus
    title: str
    summary: str | None = None
    verified_facts_json: list[dict[str, Any]] | None = None
    document_extracts_json: list[dict[str, Any]] | None = None
    causal_hypothesis: str | None = None
    missing_evidence_json: list[dict[str, Any]] | None = None
    financial_impact_usd: float
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None

    # Nested items
    evidence_count: int = 0
    recommendations: list[RecommendationResponse] = []
    actions: list[ActionResponse] = []


class InvestigationListResponse(BaseModel):
    """Paginated list of investigations."""

    items: list[InvestigationResponse]
    total: int


# ==============================================================================
# 5. Authoritative Audit Events
# ==============================================================================


class AuditEventResponse(BaseModel):
    """Append-only authoritative audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    actor_type: ActorType
    actor_id: str
    action_type: str
    affected_entity_type: str
    affected_entity_id: str
    execution_context_json: dict[str, Any] | None = None
    correlation_id: str | None = None
    canonical_payload_hash: str | None = None
    outcome_status: str
    ip_address: str | None = None
    timestamp: datetime


class AuditEventListResponse(BaseModel):
    """Paginated list of audit events."""

    items: list[AuditEventResponse]
    total: int


class AuditTrailExportItem(AuditEventResponse):
    """Export item with cryptographic payload verification result."""

    payload_verification_status: str
    calculated_payload_hash: str | None = None


class AuditTrailExportResponse(BaseModel):
    """Complete exported audit trail with canonical payload verification.

    Note: integrity_verified reflects per-record canonical payload SHA-256 hash matching
    and does not provide cryptographic tamper evidence against privileged database
    administrators or record deletion/insertion/reordering attacks (which requires
    external cryptographic chaining or anchoring, deferred).
    """

    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    exported_at: datetime
    total_events: int
    integrity_verified: bool
    events: list[AuditTrailExportItem]


class OperationalRoiResponse(BaseModel):
    """Operational ROI and MTTR progression metrics for governed workflows."""

    organization_id: uuid.UUID
    project_id: uuid.UUID | None = None
    incidents_investigated: int
    incidents_resolved: int
    baseline_mttr_minutes: float = Field(
        ...,
        description="Assumed reference baseline MTTR for manual discrepancy resolution (48.0 hours = 2880.0 minutes), not an empirically measured value.",
    )
    current_mttr_minutes: float = Field(
        ...,
        description="Realized average MTTR in minutes from detection to terminal successful execution.",
    )
    mttr_reduction_percentage: float = Field(
        ...,
        description="Percentage reduction in MTTR compared to the reference manual baseline.",
    )
    total_financial_impact_addressed_usd: float = Field(
        ...,
        description="Total financial value protected or recovered across all successfully resolved findings.",
    )
    total_ai_cost_usd: float = Field(
        ...,
        description="Cumulative AI inference expenditure across model invocations.",
    )
    cost_per_successful_task_usd: float = Field(
        ...,
        description="Average AI cost attributed per successfully completed business task.",
    )
    benefit_cost_ratio: float = Field(
        ...,
        description="Benefit-Cost Ratio (BCR) representing financial value protected divided by total AI cost (value multiple).",
    )
    financial_roi_ratio: float = Field(
        ...,
        description="Legacy field alias for benefit_cost_ratio (Benefit-Cost Multiple, not conventional net ROI).",
    )


# ==============================================================================
# 6. P2P Vertical Slice E2E Demo Helper
# ==============================================================================


class P2PVerticalSliceDemoRequest(BaseModel):
    """Trigger parameters for demonstrating the full P2P vertical slice."""

    supplier_name: str = "Apex Industrial Supplies"
    po_number: str = "PO-10023"
    po_amount: float = 15000.00
    invoice_number: str = "INV-7844"
    invoice_amount: float = 16250.00
    expected_variance: float = 1250.00
    auto_approve: bool = False


class P2PVerticalSliceDemoResponse(BaseModel):
    """End-to-end outcome of the P2P vertical slice demonstration."""

    finding_id: uuid.UUID
    investigation_id: uuid.UUID
    financial_impact_usd: float
    verified_facts: list[dict[str, Any]]
    causal_hypothesis: str
    retrieved_document_snippets: list[str]
    recommendation: RecommendationResponse
    action: ActionResponse
    approval: ApprovalResponse | None = None
    execution: ActionExecutionResponse | None = None
    audit_events_count: int
