"""Pydantic schemas for Phase 7: Adaptive Monitors & Exception Detection."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from corbel.domains.monitors.models import (
    EvaluationStatus,
    FindingStatus,
    MonitorStatus,
    MonitorTargetType,
    RuleOperator,
    RuleSeverity,
)


class BusinessRuleBase(BaseModel):
    """Base business rule specification attributes."""

    rule_code: str = Field(min_length=2, max_length=64, description="Unique rule code identifier")
    description: str | None = Field(default=None, max_length=1024, description="Human readable description")
    severity: RuleSeverity = Field(default=RuleSeverity.MEDIUM, description="Exception severity")
    rule_type: str = Field(default="THRESHOLD", max_length=64, description="Rule evaluation type")
    field_name: str = Field(min_length=1, max_length=128, description="Target entity property or process metric")
    operator: RuleOperator = Field(default=RuleOperator.GT, description="Comparison operator")
    threshold_value: float | None = Field(default=None, description="Numeric threshold value")
    threshold_string: str | None = Field(default=None, max_length=255, description="String threshold value")
    secondary_field: str | None = Field(default=None, max_length=128, description="Optional secondary property for comparison")
    parameters_json: dict[str, Any] | None = Field(default=None, description="Additional rule parameters")


class BusinessRuleCreate(BusinessRuleBase):
    """Payload to create a business rule on a monitor."""

    pass


class BusinessRuleResponse(BusinessRuleBase):
    """API response model for a configured business rule."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    monitor_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class MonitorCreate(BaseModel):
    """Payload to configure a new operational monitor."""

    name: str = Field(min_length=2, max_length=255, description="Monitor display name")
    description: str | None = Field(default=None, max_length=1024, description="Operational scope and purpose")
    target_type: MonitorTargetType = Field(default=MonitorTargetType.ENTITY, description="Target scope: ENTITY or PROCESS")
    target_id: str = Field(min_length=1, max_length=255, description="Entity name (e.g. PurchaseOrder) or Process UUID")
    schedule_cron: str | None = Field(default=None, max_length=128, description="Cron expression for periodic evaluation")
    status: MonitorStatus = Field(default=MonitorStatus.ACTIVE, description="Initial monitor state")
    rules: list[BusinessRuleCreate] = Field(default_factory=list, description="Associated business rules")


class MonitorUpdate(BaseModel):
    """Payload to modify monitor metadata and state."""

    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1024)
    schedule_cron: str | None = Field(default=None, max_length=128)
    status: MonitorStatus | None = Field(default=None)


class MonitorResponse(BaseModel):
    """API response model representing an operational monitor with rule configurations."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    target_type: MonitorTargetType
    target_id: str
    schedule_cron: str | None
    status: MonitorStatus
    last_run_at: datetime | None
    last_status: str | None
    created_at: datetime
    updated_at: datetime
    rules: list[BusinessRuleResponse] = Field(default_factory=list)
    open_findings_count: int = 0
    total_findings_count: int = 0


class FindingResponse(BaseModel):
    """API response model representing a detected operational exception finding."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    monitor_id: uuid.UUID
    rule_id: uuid.UUID | None
    process_case_id: uuid.UUID | None
    entity_type: str | None
    entity_id: str | None
    finding_type: str
    severity: RuleSeverity
    status: FindingStatus
    summary: str
    deduplication_hash: str
    observed_value: str | None
    threshold_value: str | None
    verified_context_json: dict[str, Any] | None
    detected_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: uuid.UUID | None
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    resolution_notes: str | None


class FindingStatusUpdate(BaseModel):
    """Payload to update the lifecycle state of a finding (e.g. acknowledge or resolve)."""

    status: FindingStatus = Field(description="Target lifecycle state")
    resolution_notes: str | None = Field(default=None, max_length=1024, description="Resolution or dismissal rationale")


class MonitorEvaluationResponse(BaseModel):
    """API response model for a monitor evaluation run execution."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    monitor_id: uuid.UUID
    status: EvaluationStatus
    records_evaluated: int
    findings_detected: int
    execution_duration_ms: float
    summary_json: dict[str, Any] | None
    error_message: str | None
    evaluated_at: datetime


class MonitorEvaluationRunRequest(BaseModel):
    """Request payload to trigger on-demand monitor evaluation."""

    limit: int = Field(default=500, ge=1, le=5000, description="Bounded batch evaluation record limit")
