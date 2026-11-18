"""Pydantic v2 schemas for Phase 12: Application Builder."""

import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComponentType(str, enum.Enum):
    """Controlled catalogue of reusable UI component types."""

    # Layout
    CONTAINER = "CONTAINER"
    GRID = "GRID"
    TABS = "TABS"
    CARD = "CARD"

    # Data
    DATA_TABLE = "DATA_TABLE"
    RECORD_DETAILS = "RECORD_DETAILS"
    METRIC_CARD = "METRIC_CARD"
    STATUS_INDICATOR = "STATUS_INDICATOR"

    # Forms & Input
    FORM = "FORM"
    TEXT_INPUT = "TEXT_INPUT"
    SELECT_INPUT = "SELECT_INPUT"
    DATE_INPUT = "DATE_INPUT"

    # Operational & Platform Capabilities
    MONITOR_FINDINGS_LIST = "MONITOR_FINDINGS_LIST"
    APPROVAL_QUEUE = "APPROVAL_QUEUE"
    AUDIT_TRAIL_VIEW = "AUDIT_TRAIL_VIEW"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"

    # Interaction & Content
    ACTION_BUTTON = "ACTION_BUTTON"
    NAV_LINK = "NAV_LINK"
    TEXT_BLOCK = "TEXT_BLOCK"


class LayoutType(str, enum.Enum):
    """Page section layout organization."""

    SINGLE = "SINGLE"
    TWO_COLUMNS = "TWO_COLUMNS"
    THREE_COLUMNS = "THREE_COLUMNS"
    GRID = "GRID"
    TABS = "TABS"
    CARD = "CARD"


class DataSourceType(str, enum.Enum):
    """Approved platform data-binding source types."""

    ONTOLOGY_OBJECT = "ONTOLOGY_OBJECT"
    MONITOR_FINDING = "MONITOR_FINDING"
    APPROVAL = "APPROVAL"
    DOCUMENT_RAG = "DOCUMENT_RAG"
    AUDIT_TRAIL = "AUDIT_TRAIL"
    STATIC = "STATIC"


class InteractionActionType(str, enum.Enum):
    """Controlled interactive action types for components."""

    NAVIGATE = "NAVIGATE"
    SUBMIT_FORM = "SUBMIT_FORM"
    EXECUTE_ACTION = "EXECUTE_ACTION"
    APPROVE_ACTION = "APPROVE_ACTION"
    REJECT_ACTION = "REJECT_ACTION"
    OPEN_INVESTIGATION = "OPEN_INVESTIGATION"
    REFRESH_DATA = "REFRESH_DATA"


class GovernedActionType(str, enum.Enum):
    """Controlled catalogue of permitted backend governed action types."""

    HOLD_INVOICE = "HOLD_INVOICE"
    BLOCK_VENDOR = "BLOCK_VENDOR"
    DISPUTE_CHARGE = "DISPUTE_CHARGE"
    REQUEST_CREDIT = "REQUEST_CREDIT"
    REQUEST_CREDIT_MEMO = "REQUEST_CREDIT_MEMO"
    FLAG_SUPPLIER_REVIEW = "FLAG_SUPPLIER_REVIEW"
    CUSTOM = "CUSTOM"


MANDATORY_CONSEQUENTIAL_ACTIONS: set[str] = {
    GovernedActionType.HOLD_INVOICE.value,
    GovernedActionType.BLOCK_VENDOR.value,
    GovernedActionType.DISPUTE_CHARGE.value,
}


class DataBindingConfig(BaseModel):
    """Configuration binding a component to an authorized platform query."""

    model_config = ConfigDict(extra="ignore")

    source_type: DataSourceType
    entity_name: str | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    sort: dict[str, str] | None = None
    limit: int = 50
    offset: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)


class InteractionConfig(BaseModel):
    """Configuration specifying user interaction or action execution."""

    model_config = ConfigDict(extra="ignore")

    action_type: InteractionActionType
    target_page_id: str | None = None
    governed_action_type: GovernedActionType | str | None = None
    target_adapter_type: str | None = None
    requires_confirmation: bool = False
    confirmation_message: str | None = None
    payload_template: dict[str, Any] = Field(default_factory=dict)


class ComponentInstance(BaseModel):
    """A configured component instance within a section."""

    model_config = ConfigDict(extra="ignore")

    id: str
    component_type: ComponentType
    title: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    data_binding: DataBindingConfig | None = None
    interaction: InteractionConfig | None = None
    visibility_roles: list[str] = Field(default_factory=list)


class AppSection(BaseModel):
    """A structural section of an application page."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str | None = None
    description: str | None = None
    layout: LayoutType = LayoutType.SINGLE
    components: list[ComponentInstance] = Field(default_factory=list)


class AppPage(BaseModel):
    """An application page containing configured sections."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    icon: str | None = None
    sections: list[AppSection] = Field(default_factory=list)


class NavItem(BaseModel):
    """A navigation menu item."""

    model_config = ConfigDict(extra="ignore")

    page_id: str
    label: str
    icon: str | None = None
    roles: list[str] = Field(default_factory=list)


class NavigationConfig(BaseModel):
    """Application-wide navigation menu structure."""

    model_config = ConfigDict(extra="ignore")

    title: str
    default_page_id: str
    items: list[NavItem] = Field(default_factory=list)


class AppGovernanceConfig(BaseModel):
    """Governance, data classification, and authorization requirements."""

    model_config = ConfigDict(extra="ignore")

    required_roles: list[str] = Field(default_factory=list)
    data_classification: str = "INTERNAL"
    approval_required_actions: list[str] = Field(default_factory=list)


class ApplicationDefinition(BaseModel):
    """Complete, validated declarative application blueprint."""

    model_config = ConfigDict(extra="ignore")

    app_id: uuid.UUID | None = None
    name: str
    description: str
    navigation: NavigationConfig
    pages: list[AppPage] = Field(default_factory=list)
    governance: AppGovernanceConfig = Field(default_factory=AppGovernanceConfig)


class ValidationErrorItem(BaseModel):
    """A single validation error in the application definition."""

    path: str
    message: str
    code: str


class ValidationWarningItem(BaseModel):
    """A non-blocking validation warning or recommendation."""

    path: str
    message: str
    code: str


class ApplicationValidationResponse(BaseModel):
    """Validation report for an application definition."""

    is_valid: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)
    warnings: list[ValidationWarningItem] = Field(default_factory=list)


class ApplicationCreateRequest(BaseModel):
    """Request payload to create a new application."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=3, max_length=255)
    description: str = Field(..., min_length=5)
    source_use_case_id: uuid.UUID | None = None
    source_specification_version: int | None = None


class ApplicationUpdateRequest(BaseModel):
    """Request payload to update application metadata or draft definition."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=3, max_length=255)
    description: str | None = Field(None, min_length=5)
    draft_definition: ApplicationDefinition | None = None


class ApplicationPublishRequest(BaseModel):
    """Request payload to publish the validated application draft."""

    model_config = ConfigDict(extra="forbid")

    changelog: str | None = Field(None, max_length=1000)


class ApplicationResponse(BaseModel):
    """Summary representation of an application."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    source_use_case_id: uuid.UUID | None = None
    source_specification_version: int | None = None
    status: str
    current_version: int
    published_version: int | None = None
    created_by: uuid.UUID
    updated_by: uuid.UUID
    published_by: uuid.UUID | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationDetailResponse(ApplicationResponse):
    """Detailed application view including current draft and published definition."""

    draft_definition: ApplicationDefinition
    published_definition: ApplicationDefinition | None = None


class ApplicationVersionSummary(BaseModel):
    """Summary of an immutable application version."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    is_published: bool
    changelog: str | None = None
    created_by: uuid.UUID
    created_at: datetime


class PublishedApplicationRuntimeResponse(BaseModel):
    """Payload served to the published application portal."""

    application_id: uuid.UUID
    version: int
    name: str
    description: str
    definition: ApplicationDefinition
    user_roles: list[str] = Field(default_factory=list)
    published_at: datetime | None = None


class RuntimeDataQueryRequest(BaseModel):
    """Request payload to query data for an application component."""

    model_config = ConfigDict(extra="forbid")

    component_id: str
    page_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class RuntimeDataQueryResponse(BaseModel):
    """Resolved dataset for an application component."""

    component_id: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    execution_time_ms: float = 0.0


class RuntimeActionExecuteRequest(BaseModel):
    """Request to invoke an interaction or action from an application component."""

    model_config = ConfigDict(extra="forbid")

    component_id: str
    page_id: str
    action_type: InteractionActionType
    payload: dict[str, Any] = Field(default_factory=dict)
    confirmation_acknowledged: bool = False


class RuntimeActionExecuteResponse(BaseModel):
    """Outcome of an application component interaction."""

    status: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    approval_id: uuid.UUID | None = None
