"""Declarative application blueprint generator from Phase 11 Use-Case Specifications."""

from corbel.domains.app_builder.schemas import (
    AppGovernanceConfig,
    ApplicationDefinition,
    AppPage,
    AppSection,
    ComponentInstance,
    ComponentType,
    DataBindingConfig,
    DataSourceType,
    InteractionActionType,
    InteractionConfig,
    LayoutType,
    NavigationConfig,
    NavItem,
)
from corbel.domains.use_case_architect.schemas import UseCaseSpecification


class ApplicationGenerator:
    """Transforms approved solution specifications or creates default blank blueprints."""

    @classmethod
    def create_blank_blueprint(cls, name: str, description: str) -> ApplicationDefinition:
        """Create a default minimal functional application blueprint."""
        page_id = "page-overview"
        nav = NavigationConfig(
            title=name,
            default_page_id=page_id,
            items=[NavItem(page_id=page_id, label="Overview", icon="home")],
        )

        section = AppSection(
            id="sec-welcome",
            title="Welcome",
            description="Default application workspace.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-welcome-text",
                    component_type=ComponentType.TEXT_BLOCK,
                    title="Application Overview",
                    properties={
                        "content": f"### {name}\n\n{description}\n\nUse the Application Builder to configure pages, data tables, and actions."
                    },
                )
            ],
        )

        return ApplicationDefinition(
            name=name,
            description=description,
            navigation=nav,
            pages=[AppPage(id=page_id, title="Overview", icon="home", sections=[section])],
            governance=AppGovernanceConfig(
                required_roles=["MEMBER", "ANALYST", "OPERATOR", "PROJECT_LEAD"],
                data_classification="INTERNAL",
            ),
        )

    @classmethod
    def generate_from_use_case_specification(
        cls,
        spec: UseCaseSpecification,
    ) -> ApplicationDefinition:
        """Translate a validated Phase 11 UseCaseSpecification into an operational blueprint."""
        title = spec.title
        desc = spec.description

        is_p2p = any(
            k in f"{spec.title} {spec.description} {spec.business_objective}".lower()
            for k in ["purchase order", "po", "invoice", "receipt", "variance", "supplier", "procure", "p2p"]
        )

        # Build each functional page with its corresponding navigation item
        dash_nav, dash_page = cls._build_dashboard_page(spec)
        data_nav, data_page = cls._build_data_explorer_page(is_p2p)
        exc_nav, exc_page = cls._build_exceptions_page()
        gov_nav, gov_page = cls._build_governance_page()
        aud_nav, aud_page = cls._build_audit_page()

        nav_items = [dash_nav, data_nav, exc_nav, gov_nav, aud_nav]
        pages = [dash_page, data_page, exc_page, gov_page, aud_page]

        navigation = NavigationConfig(
            title=title,
            default_page_id=dash_page.id,
            items=nav_items,
        )

        governance = AppGovernanceConfig(
            required_roles=spec.stakeholders_and_roles or ["MEMBER", "ANALYST", "OPERATOR", "PROJECT_LEAD"],
            data_classification=spec.data_classification,
            approval_required_actions=spec.human_approval_requirements or ["HOLD_INVOICE", "REQUEST_CREDIT"],
        )

        return ApplicationDefinition(
            name=title,
            description=desc,
            navigation=navigation,
            pages=pages,
            governance=governance,
        )

    # =========================================================================
    # Page Builders (Decomposed for maintainability & modularity)
    # =========================================================================

    @classmethod
    def _build_dashboard_page(cls, spec: UseCaseSpecification) -> tuple[NavItem, AppPage]:
        """Page 1: Overview & Metrics Dashboard."""
        page_id = "page-dashboard"
        nav_item = NavItem(page_id=page_id, label="Dashboard", icon="chart-bar")

        kpis_section = AppSection(
            id="sec-kpis",
            title="Operational Metrics & Status",
            description="Key performance indicators and system monitoring status.",
            layout=LayoutType.THREE_COLUMNS,
            components=[
                ComponentInstance(
                    id="kpi-exceptions",
                    component_type=ComponentType.METRIC_CARD,
                    title="Active Exceptions",
                    properties={"label": "Active Exceptions", "format": "number", "unit": ""},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.MONITOR_FINDING,
                        filters=[{"field": "status", "operator": "eq", "value": "OPEN"}],
                    ),
                ),
                ComponentInstance(
                    id="kpi-approvals",
                    component_type=ComponentType.METRIC_CARD,
                    title="Pending Approvals",
                    properties={"label": "Pending Approvals", "format": "number", "unit": ""},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.APPROVAL,
                        filters=[{"field": "status", "operator": "eq", "value": "PENDING"}],
                    ),
                ),
                ComponentInstance(
                    id="kpi-risk",
                    component_type=ComponentType.STATUS_INDICATOR,
                    title="Solution Risk Level",
                    properties={"status_field": spec.risk_level},
                ),
            ],
        )

        overview_section = AppSection(
            id="sec-overview-details",
            title="Business Objectives & Solution Workflow",
            layout=LayoutType.TWO_COLUMNS,
            components=[
                ComponentInstance(
                    id="text-objective",
                    component_type=ComponentType.TEXT_BLOCK,
                    title="Operational Objectives",
                    properties={
                        "content": (
                            f"**Objective:** {spec.business_objective}\n\n"
                            f"**Architecture:** {spec.proposed_architecture}\n\n"
                            f"**Data Freshness:** {spec.freshness_and_latency}"
                        )
                    },
                ),
                ComponentInstance(
                    id="text-workflow",
                    component_type=ComponentType.TEXT_BLOCK,
                    title="Process Flow",
                    properties={
                        "content": (
                            f"**Workflow:** {spec.workflow_description}\n\n"
                            f"**Stakeholders:** {', '.join(spec.stakeholders_and_roles)}"
                        )
                    },
                ),
            ],
        )

        page = AppPage(
            id=page_id,
            title="Operational Dashboard",
            icon="chart-bar",
            sections=[kpis_section, overview_section],
        )
        return nav_item, page

    @classmethod
    def _build_data_explorer_page(cls, is_p2p: bool) -> tuple[NavItem, AppPage]:
        """Page 2: Operational Data Explorer."""
        page_id = "page-data"
        nav_item = NavItem(page_id=page_id, label="Data Explorer", icon="table")

        table_entity = "PurchaseOrder" if is_p2p else "OperationalLog"
        table_cols = (
            ["po_number", "vendor_id", "total_amount", "status", "created_date"]
            if is_p2p
            else ["id", "event_type", "status", "timestamp"]
        )

        data_section = AppSection(
            id="sec-primary-table",
            title=f"{table_entity} Records",
            description=f"Direct access to profiled {table_entity} records.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-data-table",
                    component_type=ComponentType.DATA_TABLE,
                    title=f"{table_entity} Register",
                    properties={
                        "columns": table_cols,
                        "page_size": 15,
                        "empty_message": f"No {table_entity} records available.",
                    },
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.ONTOLOGY_OBJECT,
                        entity_name=table_entity,
                        limit=50,
                    ),
                    interaction=InteractionConfig(
                        action_type=InteractionActionType.REFRESH_DATA,
                    ),
                )
            ],
        )

        page = AppPage(
            id=page_id,
            title="Operational Data Explorer",
            icon="table",
            sections=[data_section],
        )
        return nav_item, page

    @classmethod
    def _build_exceptions_page(cls) -> tuple[NavItem, AppPage]:
        """Page 3: Exceptions & RAG Document Intelligence."""
        page_id = "page-exceptions"
        nav_item = NavItem(page_id=page_id, label="Exceptions & RAG", icon="exclamation-circle")

        exceptions_section = AppSection(
            id="sec-findings",
            title="Detected Exceptions & Anomalies",
            description="Deterministic monitor findings and deviation alerts.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-findings-list",
                    component_type=ComponentType.MONITOR_FINDINGS_LIST,
                    title="Active Monitor Findings",
                    properties={"severity_filter": "ALL", "max_items": 20},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.MONITOR_FINDING,
                    ),
                    interaction=InteractionConfig(
                        action_type=InteractionActionType.OPEN_INVESTIGATION,
                    ),
                )
            ],
        )

        rag_section = AppSection(
            id="sec-rag-search",
            title="Semantic Clause Retrieval (RAG)",
            description="Retrieve governing contracts, terms, and guidelines with source citations.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-rag-search",
                    component_type=ComponentType.DOCUMENT_SEARCH,
                    title="Contract & Policy Search",
                    properties={"placeholder": "Search supplier master agreements, freight rules, or discount terms..."},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.DOCUMENT_RAG,
                    ),
                )
            ],
        )

        page = AppPage(
            id=page_id,
            title="Exceptions & Document Intelligence",
            icon="exclamation-circle",
            sections=[exceptions_section, rag_section],
        )
        return nav_item, page

    @classmethod
    def _build_governance_page(cls) -> tuple[NavItem, AppPage]:
        """Page 4: Governance, Approvals & Corrective Actions."""
        page_id = "page-governance"
        nav_item = NavItem(page_id=page_id, label="Approvals & Actions", icon="shield-check")

        approvals_section = AppSection(
            id="sec-approvals",
            title="Human-in-the-Loop Approval Queue",
            description="Governed authorization for consequential business actions.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-approval-queue",
                    component_type=ComponentType.APPROVAL_QUEUE,
                    title="Pending Consequential Actions",
                    properties={"show_rationale": True},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.APPROVAL,
                    ),
                    interaction=InteractionConfig(
                        action_type=InteractionActionType.APPROVE_ACTION,
                        requires_confirmation=True,
                        confirmation_message="Confirm approval of this operational action?",
                    ),
                )
            ],
        )

        action_section = AppSection(
            id="sec-action-dispatch",
            title="Corrective Action Dispatcher",
            layout=LayoutType.TWO_COLUMNS,
            components=[
                ComponentInstance(
                    id="btn-hold-invoice",
                    component_type=ComponentType.ACTION_BUTTON,
                    title="Hold Discrepant Invoice",
                    properties={"label": "Hold Discrepant Invoice", "variant": "danger"},
                    interaction=InteractionConfig(
                        action_type=InteractionActionType.EXECUTE_ACTION,
                        governed_action_type="HOLD_INVOICE",
                        target_adapter_type="SimulatedTargetAdapter",
                        requires_confirmation=True,
                        confirmation_message="Hold invoice from payment processing in ERP?",
                    ),
                ),
                ComponentInstance(
                    id="btn-request-credit",
                    component_type=ComponentType.ACTION_BUTTON,
                    title="Request Supplier Credit Note",
                    properties={"label": "Request Supplier Credit Note", "variant": "primary"},
                    interaction=InteractionConfig(
                        action_type=InteractionActionType.EXECUTE_ACTION,
                        governed_action_type="REQUEST_CREDIT",
                        target_adapter_type="SimulatedTargetAdapter",
                        requires_confirmation=True,
                        confirmation_message="Request credit memo from supplier for price discrepancy?",
                    ),
                ),
            ],
        )

        page = AppPage(
            id=page_id,
            title="Governance & Corrective Actions",
            icon="shield-check",
            sections=[approvals_section, action_section],
        )
        return nav_item, page

    @classmethod
    def _build_audit_page(cls) -> tuple[NavItem, AppPage]:
        """Page 5: Append-Only Audit Trail."""
        page_id = "page-audit"
        nav_item = NavItem(page_id=page_id, label="Audit Trail", icon="clock")

        audit_section = AppSection(
            id="sec-audit-history",
            title="Operational & Administrative Audit Trail",
            description="Immutable chronological record of decisions and actions.",
            layout=LayoutType.SINGLE,
            components=[
                ComponentInstance(
                    id="comp-audit-trail",
                    component_type=ComponentType.AUDIT_TRAIL_VIEW,
                    title="Append-Only Audit Log",
                    properties={"limit": 25},
                    data_binding=DataBindingConfig(
                        source_type=DataSourceType.AUDIT_TRAIL,
                        limit=25,
                    ),
                )
            ],
        )

        page = AppPage(
            id=page_id,
            title="Audit & Compliance",
            icon="clock",
            sections=[audit_section],
        )
        return nav_item, page
