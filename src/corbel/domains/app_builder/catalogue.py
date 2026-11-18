"""Controlled Component Catalogue registry for Phase 12: Application Builder."""

from dataclasses import dataclass, field
from typing import Any

from corbel.domains.app_builder.schemas import ComponentType, DataSourceType


@dataclass(frozen=True)
class ComponentSpec:
    """Specification defining the contract, supported data bindings, and properties of a component."""

    component_type: ComponentType
    category: str  # layout, data, form, operational, action, content
    display_name: str
    description: str
    supported_data_sources: list[DataSourceType] = field(default_factory=list)
    required_properties: list[str] = field(default_factory=list)
    default_properties: dict[str, Any] = field(default_factory=dict)
    supports_interactions: bool = False


# Authoritative Catalogue of registered components
COMPONENT_CATALOGUE: dict[ComponentType, ComponentSpec] = {
    # 1. Data Display Components
    ComponentType.DATA_TABLE: ComponentSpec(
        component_type=ComponentType.DATA_TABLE,
        category="data",
        display_name="Data Table",
        description="Tabular grid with sorting, pagination, and field projection.",
        supported_data_sources=[
            DataSourceType.ONTOLOGY_OBJECT,
            DataSourceType.MONITOR_FINDING,
            DataSourceType.APPROVAL,
            DataSourceType.AUDIT_TRAIL,
            DataSourceType.STATIC,
        ],
        required_properties=["columns"],
        default_properties={"columns": [], "page_size": 10, "empty_message": "No records found."},
        supports_interactions=True,
    ),
    ComponentType.RECORD_DETAILS: ComponentSpec(
        component_type=ComponentType.RECORD_DETAILS,
        category="data",
        display_name="Record Details",
        description="Key-value card displaying detailed entity fields.",
        supported_data_sources=[
            DataSourceType.ONTOLOGY_OBJECT,
            DataSourceType.MONITOR_FINDING,
            DataSourceType.APPROVAL,
            DataSourceType.STATIC,
        ],
        required_properties=["fields"],
        default_properties={"fields": [], "title": "Record Overview"},
        supports_interactions=False,
    ),
    ComponentType.METRIC_CARD: ComponentSpec(
        component_type=ComponentType.METRIC_CARD,
        category="data",
        display_name="Metric / KPI Card",
        description="Compact numeric metric indicator with title and trend.",
        supported_data_sources=[
            DataSourceType.ONTOLOGY_OBJECT,
            DataSourceType.MONITOR_FINDING,
            DataSourceType.APPROVAL,
            DataSourceType.STATIC,
        ],
        required_properties=["label"],
        default_properties={"label": "Metric", "format": "number", "unit": ""},
        supports_interactions=True,
    ),
    ComponentType.STATUS_INDICATOR: ComponentSpec(
        component_type=ComponentType.STATUS_INDICATOR,
        category="data",
        display_name="Status Indicator",
        description="Visual badge reflecting lifecycle or health state.",
        supported_data_sources=[
            DataSourceType.ONTOLOGY_OBJECT,
            DataSourceType.MONITOR_FINDING,
            DataSourceType.APPROVAL,
            DataSourceType.STATIC,
        ],
        required_properties=["status_field"],
        default_properties={"status_field": "status"},
        supports_interactions=False,
    ),
    # 2. Operational & Platform Capabilities
    ComponentType.MONITOR_FINDINGS_LIST: ComponentSpec(
        component_type=ComponentType.MONITOR_FINDINGS_LIST,
        category="operational",
        display_name="Monitor Findings List",
        description="Operational queue of detected exceptions, anomalies, and findings.",
        supported_data_sources=[DataSourceType.MONITOR_FINDING],
        required_properties=[],
        default_properties={"severity_filter": "ALL", "max_items": 20},
        supports_interactions=True,
    ),
    ComponentType.APPROVAL_QUEUE: ComponentSpec(
        component_type=ComponentType.APPROVAL_QUEUE,
        category="operational",
        display_name="Approval Queue",
        description="Interactive governance queue for pending human approvals.",
        supported_data_sources=[DataSourceType.APPROVAL],
        required_properties=[],
        default_properties={"assigned_role": "ALL", "show_rationale": True},
        supports_interactions=True,
    ),
    ComponentType.AUDIT_TRAIL_VIEW: ComponentSpec(
        component_type=ComponentType.AUDIT_TRAIL_VIEW,
        category="operational",
        display_name="Audit Trail View",
        description="Immutable chronological activity feed from Phase 10 AuditService.",
        supported_data_sources=[DataSourceType.AUDIT_TRAIL],
        required_properties=[],
        default_properties={"limit": 25},
        supports_interactions=False,
    ),
    ComponentType.DOCUMENT_SEARCH: ComponentSpec(
        component_type=ComponentType.DOCUMENT_SEARCH,
        category="operational",
        display_name="Document RAG Search",
        description="Semantic document clause retrieval powered by pgvector.",
        supported_data_sources=[DataSourceType.DOCUMENT_RAG],
        required_properties=[],
        default_properties={"placeholder": "Search contracts, policies, and guidelines..."},
        supports_interactions=True,
    ),
    # 3. Forms & Inputs
    ComponentType.FORM: ComponentSpec(
        component_type=ComponentType.FORM,
        category="form",
        display_name="Input Form",
        description="Parameterized form collecting user inputs for actions.",
        supported_data_sources=[DataSourceType.STATIC],
        required_properties=["fields", "submit_label"],
        default_properties={"fields": [], "submit_label": "Submit"},
        supports_interactions=True,
    ),
    ComponentType.TEXT_INPUT: ComponentSpec(
        component_type=ComponentType.TEXT_INPUT,
        category="form",
        display_name="Text Input",
        description="Single-line text input field.",
        supported_data_sources=[],
        required_properties=["name", "label"],
        default_properties={"name": "", "label": "Text Field", "placeholder": ""},
        supports_interactions=False,
    ),
    ComponentType.SELECT_INPUT: ComponentSpec(
        component_type=ComponentType.SELECT_INPUT,
        category="form",
        display_name="Select Dropdown",
        description="Option picker dropdown.",
        supported_data_sources=[DataSourceType.ONTOLOGY_OBJECT, DataSourceType.STATIC],
        required_properties=["name", "label", "options"],
        default_properties={"name": "", "label": "Select", "options": []},
        supports_interactions=False,
    ),
    ComponentType.DATE_INPUT: ComponentSpec(
        component_type=ComponentType.DATE_INPUT,
        category="form",
        display_name="Date Input",
        description="Calendar date selector.",
        supported_data_sources=[],
        required_properties=["name", "label"],
        default_properties={"name": "", "label": "Date"},
        supports_interactions=False,
    ),
    # 4. Action & Navigation
    ComponentType.ACTION_BUTTON: ComponentSpec(
        component_type=ComponentType.ACTION_BUTTON,
        category="action",
        display_name="Action Button",
        description="Interactive button triggering a governed platform action or workflow.",
        supported_data_sources=[],
        required_properties=["label"],
        default_properties={"label": "Execute", "variant": "primary"},
        supports_interactions=True,
    ),
    ComponentType.NAV_LINK: ComponentSpec(
        component_type=ComponentType.NAV_LINK,
        category="action",
        display_name="Navigation Link",
        description="Link navigating between application pages.",
        supported_data_sources=[],
        required_properties=["label", "target_page_id"],
        default_properties={"label": "Go to Page", "target_page_id": ""},
        supports_interactions=True,
    ),
    # 5. Content & Layout
    ComponentType.TEXT_BLOCK: ComponentSpec(
        component_type=ComponentType.TEXT_BLOCK,
        category="content",
        display_name="Text Block",
        description="Descriptive markdown or static text block.",
        supported_data_sources=[],
        required_properties=["content"],
        default_properties={"content": "Informational text."},
        supports_interactions=False,
    ),
    ComponentType.CONTAINER: ComponentSpec(
        component_type=ComponentType.CONTAINER,
        category="layout",
        display_name="Container",
        description="Structural grouping box.",
        supported_data_sources=[],
        required_properties=[],
        default_properties={},
        supports_interactions=False,
    ),
    ComponentType.GRID: ComponentSpec(
        component_type=ComponentType.GRID,
        category="layout",
        display_name="Grid Container",
        description="Multi-column grid organizer.",
        supported_data_sources=[],
        required_properties=["columns_count"],
        default_properties={"columns_count": 2},
        supports_interactions=False,
    ),
    ComponentType.TABS: ComponentSpec(
        component_type=ComponentType.TABS,
        category="layout",
        display_name="Tabbed Container",
        description="Tabbed section organizer.",
        supported_data_sources=[],
        required_properties=["tab_labels"],
        default_properties={"tab_labels": []},
        supports_interactions=False,
    ),
    ComponentType.CARD: ComponentSpec(
        component_type=ComponentType.CARD,
        category="layout",
        display_name="Card Container",
        description="Bordered card container.",
        supported_data_sources=[],
        required_properties=[],
        default_properties={"title": ""},
        supports_interactions=False,
    ),
}


def get_component_spec(component_type: ComponentType | str) -> ComponentSpec | None:
    """Resolve component specification from catalogue."""
    if isinstance(component_type, str):
        try:
            component_type = ComponentType(component_type)
        except ValueError:
            return None
    return COMPONENT_CATALOGUE.get(component_type)


def list_catalogue_specs() -> list[dict[str, Any]]:
    """Return serializable catalogue summary for frontend palette."""
    return [
        {
            "component_type": spec.component_type.value,
            "category": spec.category,
            "display_name": spec.display_name,
            "description": spec.description,
            "supported_data_sources": [s.value for s in spec.supported_data_sources],
            "required_properties": spec.required_properties,
            "default_properties": spec.default_properties,
            "supports_interactions": spec.supports_interactions,
        }
        for spec in COMPONENT_CATALOGUE.values()
    ]
