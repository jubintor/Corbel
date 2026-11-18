"""Business service for Phase 12: Application Builder."""

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.domains.app_builder.generator import ApplicationGenerator
from corbel.domains.app_builder.models import (
    Application,
    ApplicationStatus,
    ApplicationVersion,
)
from corbel.domains.app_builder.schemas import (
    MANDATORY_CONSEQUENTIAL_ACTIONS,
    ApplicationCreateRequest,
    ApplicationDefinition,
    ApplicationDetailResponse,
    ApplicationPublishRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
    ApplicationValidationResponse,
    ApplicationVersionSummary,
    ComponentInstance,
    DataSourceType,
    GovernedActionType,
    InteractionActionType,
    PublishedApplicationRuntimeResponse,
    RuntimeActionExecuteRequest,
    RuntimeActionExecuteResponse,
    RuntimeDataQueryRequest,
    RuntimeDataQueryResponse,
)
from corbel.domains.app_builder.validator import ApplicationValidator
from corbel.domains.governance.audit import AuditService
from corbel.domains.governance.models import (
    Action,
    ActionStatus,
    ActorType,
    Approval,
    ApprovalStatus,
    AuditEvent,
)
from corbel.domains.governance.schemas import ApprovalDecisionRequest
from corbel.domains.governance.service import GovernanceService
from corbel.domains.monitors.models import Finding
from corbel.domains.query.schemas import QueryFilter, StructuredQueryRequest
from corbel.domains.query.service import QueryService
from corbel.domains.tenancy.models import OrgRole, ProjectRole
from corbel.domains.tenancy.service import TenancyService
from corbel.domains.use_case_architect.models import (
    UseCase,
    UseCaseSpecificationVersion,
)
from corbel.domains.use_case_architect.schemas import UseCaseSpecification

logger = logging.getLogger(__name__)


class ApplicationBuilderService:
    """Orchestrates declarative application building, validation, publishing, and secure runtime."""

    def __init__(
        self,
        session: AsyncSession,
        tenancy_service: TenancyService,
        audit_service: AuditService,
        query_service: QueryService | None = None,
        governance_service: GovernanceService | None = None,
    ) -> None:
        self.session = session
        self.tenancy_service = tenancy_service
        self.audit_service = audit_service
        self.query_service = query_service or QueryService(session)
        self.governance_service = governance_service or GovernanceService(
            session=session, tenancy_service=tenancy_service
        )

    # =========================================================================
    # Tenancy & Access Verification
    # =========================================================================

    async def _verify_project_access(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        min_role: list[ProjectRole] | None = None,
    ) -> Any:
        """Verify organization ownership of project and user membership."""
        await self.tenancy_service.get_project(organization_id, project_id, user_id)
        return await self.tenancy_service.verify_project_access(
            org_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            min_role=min_role,
        )

    async def _get_app_entity(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        for_update: bool = False,
    ) -> Application:
        """Retrieve an Application ensuring strict tenant and project isolation."""
        stmt = select(Application).where(
            Application.id == app_id,
            Application.organization_id == organization_id,
            Application.project_id == project_id,
        )
        if for_update:
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        app = result.scalar_one_or_none()
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application {app_id} not found in project {project_id}.",
            )
        return app

    @staticmethod
    def _find_component(
        definition: ApplicationDefinition,
        page_id: str,
        component_id: str,
    ) -> ComponentInstance | None:
        """Locate a component instance within an application blueprint page."""
        for page in definition.pages:
            if page.id == page_id:
                for section in page.sections:
                    for comp in section.components:
                        if comp.id == component_id:
                            return comp
        return None

    # =========================================================================
    # Application CRUD & Lifecycle
    # =========================================================================

    async def create_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ApplicationCreateRequest,
    ) -> ApplicationDetailResponse:
        """Create a new application from an approved Phase 11 use case or blank blueprint."""
        await self._verify_project_access(organization_id, project_id, user_id)

        now = datetime.now(UTC)
        app_id = uuid.uuid4()
        initial_definition: ApplicationDefinition
        target_ver: int | None = None

        if payload.source_use_case_id:
            # Query use case
            uc_stmt = select(UseCase).where(
                UseCase.id == payload.source_use_case_id,
                UseCase.organization_id == organization_id,
                UseCase.project_id == project_id,
            )
            uc_res = await self.session.execute(uc_stmt)
            use_case = uc_res.scalar_one_or_none()
            if not use_case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Source use case {payload.source_use_case_id} not found in project.",
                )

            # Resolve specification version
            target_ver = payload.source_specification_version or use_case.current_version
            if target_ver < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Source use case {use_case.id} has no generated specifications to build from.",
                )

            spec_stmt = select(UseCaseSpecificationVersion).where(
                UseCaseSpecificationVersion.use_case_id == use_case.id,
                UseCaseSpecificationVersion.version == target_ver,
            )
            spec_res = await self.session.execute(spec_stmt)
            spec_row = spec_res.scalar_one_or_none()
            if not spec_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Specification version {target_ver} not found for use case {use_case.id}.",
                )

            # Enforce approved specification at backend (DEF-012-002)
            spec_status = (
                spec_row.specification_json.get("specification_status")
                if isinstance(spec_row.specification_json, dict)
                else None
            )
            is_approved = spec_status == "APPROVED"
            if not is_approved:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Specification version {target_ver} of use case {use_case.id} has not been approved.",
                )

            spec = UseCaseSpecification.model_validate(spec_row.specification_json)
            initial_definition = ApplicationGenerator.generate_from_use_case_specification(spec)
        else:
            initial_definition = ApplicationGenerator.create_blank_blueprint(
                name=payload.name,
                description=payload.description,
            )

        initial_definition.app_id = app_id

        app = Application(
            id=app_id,
            organization_id=organization_id,
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            source_use_case_id=payload.source_use_case_id,
            source_specification_version=target_ver if payload.source_use_case_id else None,
            status=ApplicationStatus.DRAFT.value,
            current_version=0,
            published_version=None,
            draft_definition_json=initial_definition.model_dump(mode="json"),
            created_by=user_id,
            updated_by=user_id,
            created_at=now,
            updated_at=now,
        )
        self.session.add(app)
        await self.session.flush()

        # Audit event logged and committed in the same transaction
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="APPLICATION_CREATED",
            affected_entity_type="Application",
            affected_entity_id=str(app.id),
            execution_context={
                "name": app.name,
                "source_use_case_id": str(app.source_use_case_id) if app.source_use_case_id else None,
            },
        )
        await self.session.commit()
        await self.session.refresh(app)

        return await self.get_application(organization_id, project_id, app.id, user_id)

    async def get_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ApplicationDetailResponse:
        """Get application details with draft definition and published definition."""
        await self._verify_project_access(organization_id, project_id, user_id)
        app = await self._get_app_entity(organization_id, project_id, app_id)

        draft_def = ApplicationDefinition.model_validate(app.draft_definition_json)
        pub_def: ApplicationDefinition | None = None

        if app.published_version is not None:
            ver_stmt = select(ApplicationVersion).where(
                ApplicationVersion.application_id == app.id,
                ApplicationVersion.version == app.published_version,
            )
            ver_res = await self.session.execute(ver_stmt)
            ver_row = ver_res.scalar_one_or_none()
            if ver_row:
                pub_def = ApplicationDefinition.model_validate(ver_row.definition_json)

        return ApplicationDetailResponse(
            id=app.id,
            organization_id=app.organization_id,
            project_id=app.project_id,
            name=app.name,
            description=app.description,
            source_use_case_id=app.source_use_case_id,
            source_specification_version=app.source_specification_version,
            status=app.status,
            current_version=app.current_version,
            published_version=app.published_version,
            created_by=app.created_by,
            updated_by=app.updated_by,
            published_by=app.published_by,
            published_at=app.published_at,
            created_at=app.created_at,
            updated_at=app.updated_at,
            draft_definition=draft_def,
            published_definition=pub_def,
        )

    async def list_applications(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ApplicationResponse]:
        """List all applications in a project."""
        await self._verify_project_access(organization_id, project_id, user_id)
        stmt = (
            select(Application)
            .where(
                Application.organization_id == organization_id,
                Application.project_id == project_id,
            )
            .order_by(desc(Application.created_at))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [ApplicationResponse.model_validate(r) for r in rows]

    async def update_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ApplicationUpdateRequest | dict[str, Any],
    ) -> ApplicationDetailResponse:
        """Update draft definition or application metadata."""
        await self._verify_project_access(
            organization_id,
            project_id,
            user_id,
            min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD],
        )
        app = await self._get_app_entity(organization_id, project_id, app_id)

        now = datetime.now(UTC)
        p_name = payload.name if isinstance(payload, ApplicationUpdateRequest) else payload.get("name")
        p_desc = payload.description if isinstance(payload, ApplicationUpdateRequest) else payload.get("description")
        p_def = (
            payload.draft_definition
            if isinstance(payload, ApplicationUpdateRequest)
            else payload.get("draft_definition")
        )

        if p_name is not None:
            app.name = p_name
        if p_desc is not None:
            app.description = p_desc
        if p_def is not None:
            parsed_def = (
                p_def
                if isinstance(p_def, ApplicationDefinition)
                else ApplicationDefinition.model_validate(p_def)
            )
            parsed_def.app_id = app.id
            if p_name is None and parsed_def.name:
                app.name = parsed_def.name
            if p_desc is None and parsed_def.description:
                app.description = parsed_def.description
            app.draft_definition_json = parsed_def.model_dump(mode="json")
            # If application was VALIDATED, editing draft reverts status to DRAFT
            if app.status == ApplicationStatus.VALIDATED.value:
                app.status = ApplicationStatus.DRAFT.value

        app.updated_by = user_id
        app.updated_at = now

        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="APPLICATION_UPDATED",
            affected_entity_type="Application",
            affected_entity_id=str(app.id),
            execution_context={"name": app.name},
        )
        await self.session.commit()
        await self.session.refresh(app)

        return await self.get_application(organization_id, project_id, app.id, user_id)

    async def delete_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete an application and all its versions atomically. Requires Lead or Admin."""
        await self._verify_project_access(
            organization_id,
            project_id,
            user_id,
            min_role=[ProjectRole.PROJECT_LEAD],
        )
        app = await self._get_app_entity(organization_id, project_id, app_id)

        # Atomic commit: log audit event and delete in the exact same transaction
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="APPLICATION_DELETED",
            affected_entity_type="Application",
            affected_entity_id=str(app_id),
            execution_context={"name": app.name},
        )
        await self.session.delete(app)
        await self.session.commit()

    # =========================================================================
    # Validation & Publication
    # =========================================================================

    async def validate_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ApplicationDefinition | None = None,
    ) -> ApplicationValidationResponse:
        """Validate the application draft against component specifications and safety boundaries."""
        await self._verify_project_access(organization_id, project_id, user_id)
        app = await self._get_app_entity(organization_id, project_id, app_id)

        definition = (
            payload
            if payload is not None
            else ApplicationDefinition.model_validate(app.draft_definition_json)
        )
        report = ApplicationValidator.validate(definition)

        if payload is None and report.is_valid and app.status == ApplicationStatus.DRAFT.value:
            app.status = ApplicationStatus.VALIDATED.value
            app.updated_at = datetime.now(UTC)
            await self.session.commit()

        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="APPLICATION_VALIDATED",
            affected_entity_type="Application",
            affected_entity_id=str(app.id),
            execution_context={
                "is_valid": report.is_valid,
                "errors_count": len(report.errors),
                "warnings_count": len(report.warnings),
            },
        )
        await self.session.commit()

        return report

    async def publish_application(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: ApplicationPublishRequest,
    ) -> ApplicationDetailResponse:
        """Publish the validated draft. Enforces row locking and atomic version creation."""
        await self._verify_project_access(
            organization_id,
            project_id,
            user_id,
            min_role=[ProjectRole.PROJECT_LEAD],
        )

        # Acquire row lock to serialize concurrent publishing attempts
        app = await self._get_app_entity(organization_id, project_id, app_id, for_update=True)

        definition = ApplicationDefinition.model_validate(app.draft_definition_json)
        validation = ApplicationValidator.validate(definition)
        if not validation.is_valid:
            error_msgs = "; ".join(f"{e.path}: {e.message}" for e in validation.errors[:3])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot publish invalid application blueprint: {error_msgs}",
            )

        now = datetime.now(UTC)
        new_version = app.current_version + 1

        version_record = ApplicationVersion(
            id=uuid.uuid4(),
            application_id=app.id,
            version=new_version,
            is_published=True,
            definition_json=definition.model_dump(mode="json"),
            changelog=payload.changelog,
            created_by=user_id,
            created_at=now,
        )
        self.session.add(version_record)

        app.current_version = new_version
        app.published_version = new_version
        app.status = ApplicationStatus.PUBLISHED.value
        app.published_by = user_id
        app.published_at = now
        app.updated_at = now

        # Atomic audit event in the same transaction
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="APPLICATION_PUBLISHED",
            affected_entity_type="Application",
            affected_entity_id=str(app.id),
            execution_context={
                "version": new_version,
                "changelog": payload.changelog,
            },
        )

        await self.session.commit()
        await self.session.refresh(app)

        return await self.get_application(organization_id, project_id, app.id, user_id)

    async def list_versions(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ApplicationVersionSummary]:
        """List all published and historical versions of an application."""
        await self._verify_project_access(organization_id, project_id, user_id)
        await self._get_app_entity(organization_id, project_id, app_id)

        stmt = (
            select(ApplicationVersion)
            .where(ApplicationVersion.application_id == app_id)
            .order_by(desc(ApplicationVersion.version))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [ApplicationVersionSummary.model_validate(r) for r in rows]

    async def get_version(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        version: int,
        user_id: uuid.UUID,
    ) -> ApplicationDefinition:
        """Retrieve a specific historical application version definition."""
        await self._verify_project_access(organization_id, project_id, user_id)
        await self._get_app_entity(organization_id, project_id, app_id)

        stmt = select(ApplicationVersion).where(
            ApplicationVersion.application_id == app_id,
            ApplicationVersion.version == version,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version} not found for application {app_id}.",
            )
        return ApplicationDefinition.model_validate(row.definition_json)

    # =========================================================================
    # Runtime Engine & Data Resolution
    # =========================================================================

    async def get_published_runtime(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PublishedApplicationRuntimeResponse:
        """Serve the immutable published application definition for execution in the portal."""
        pm = await self._verify_project_access(organization_id, project_id, user_id)
        app = await self._get_app_entity(organization_id, project_id, app_id)

        if app.published_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application '{app.name}' has not been published yet.",
            )

        stmt = select(ApplicationVersion).where(
            ApplicationVersion.application_id == app.id,
            ApplicationVersion.version == app.published_version,
        )
        result = await self.session.execute(stmt)
        version_row = result.scalar_one_or_none()
        if not version_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Published version {app.published_version} not found.",
            )

        definition = ApplicationDefinition.model_validate(version_row.definition_json)

        # Resolve caller roles
        roles = [pm.project_role] if pm else [OrgRole.ORG_ADMIN.value]

        return PublishedApplicationRuntimeResponse(
            application_id=app.id,
            version=version_row.version,
            name=definition.name,
            description=definition.description,
            definition=definition,
            user_roles=roles,
            published_at=app.published_at,
        )

    async def resolve_runtime_data(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        request: RuntimeDataQueryRequest,
    ) -> RuntimeDataQueryResponse:
        """Resolve authorized data for an application component using existing platform services."""
        pm = await self._verify_project_access(organization_id, project_id, user_id)
        app = await self._get_app_entity(organization_id, project_id, app_id)

        # Determine definition (published version preferred, draft fallback if previewing)
        definition_json = app.draft_definition_json
        if app.published_version is not None:
            ver_stmt = select(ApplicationVersion).where(
                ApplicationVersion.application_id == app.id,
                ApplicationVersion.version == app.published_version,
            )
            ver_row = (await self.session.execute(ver_stmt)).scalar_one_or_none()
            if ver_row:
                definition_json = ver_row.definition_json

        definition = ApplicationDefinition.model_validate(definition_json)

        # Find target component
        target_component = self._find_component(definition, request.page_id, request.component_id)
        if not target_component or not target_component.data_binding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Component '{request.component_id}' or its data binding not found.",
            )

        # Enforce component visibility roles (DEF-012-003)
        user_role = pm.project_role if pm else OrgRole.ORG_ADMIN.value
        if (
            target_component.visibility_roles
            and user_role not in target_component.visibility_roles
            and user_role != OrgRole.ORG_ADMIN.value
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user_role}' is not authorized to view component '{request.component_id}'.",
            )

        start_time = time.perf_counter()
        binding = target_component.data_binding

        # Route to focused data source resolver
        if binding.source_type == DataSourceType.ONTOLOGY_OBJECT:
            columns, rows, total_rows = await self._resolve_ontology_data(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                target_component=target_component,
                request=request,
            )
        elif binding.source_type == DataSourceType.MONITOR_FINDING:
            columns, rows, total_rows = await self._resolve_findings_data(
                project_id=project_id,
                request=request,
            )
        elif binding.source_type == DataSourceType.APPROVAL:
            columns, rows, total_rows = await self._resolve_approvals_data(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
            )
        elif binding.source_type == DataSourceType.AUDIT_TRAIL:
            columns, rows, total_rows = await self._resolve_audit_data(
                organization_id=organization_id,
                project_id=project_id,
                request=request,
            )
        elif binding.source_type == DataSourceType.STATIC:
            columns, rows, total_rows = self._resolve_static_data(target_component)
        else:
            columns, rows, total_rows = [], [], 0

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return RuntimeDataQueryResponse(
            component_id=request.component_id,
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            execution_time_ms=round(latency_ms, 2),
        )

    # -------------------------------------------------------------------------
    # Private Runtime Data Resolvers
    # -------------------------------------------------------------------------

    async def _resolve_ontology_data(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        target_component: ComponentInstance,
        request: RuntimeDataQueryRequest,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Resolve structured records from the Corbel ontology service."""
        binding = target_component.data_binding
        if not binding:
            return [], [], 0
        entity_name = binding.entity_name or "PurchaseOrder"
        parsed_filters = [
            QueryFilter.model_validate(f) if isinstance(f, dict) else f
            for f in binding.filters
        ]
        query_req = StructuredQueryRequest(
            entity_name=entity_name,
            fields=target_component.properties.get("columns", []),
            filters=parsed_filters,
            limit=request.limit or binding.limit,
            offset=request.offset or binding.offset,
        )
        try:
            res = await self.query_service.execute_query(
                org_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                req=query_req,
            )
            return res.columns, res.rows, res.total_count
        except Exception as e:
            logger.warning("Ontology query error: %s. Returning empty set.", e)
            return query_req.fields or ["id", "status"], [], 0

    async def _resolve_findings_data(
        self,
        project_id: uuid.UUID,
        request: RuntimeDataQueryRequest,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Resolve active monitor findings scoped to the project."""
        f_stmt = (
            select(Finding)
            .where(Finding.project_id == project_id)
            .order_by(desc(Finding.detected_at))
            .limit(request.limit)
            .offset(request.offset)
        )
        f_result = await self.session.execute(f_stmt)
        findings = f_result.scalars().all()
        columns = ["id", "summary", "severity", "status", "detected_at"]
        rows = [
            {
                "id": str(f.id),
                "summary": f.summary,
                "severity": f.severity,
                "status": f.status,
                "detected_at": f.detected_at.isoformat() if f.detected_at else None,
            }
            for f in findings
        ]
        return columns, rows, len(rows)

    async def _resolve_approvals_data(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Resolve pending consequential action approvals."""
        approvals = await self.governance_service.list_approvals(
            organization_id=organization_id,
            project_id=project_id,
            user_id=user_id,
            status=ApprovalStatus.PENDING,
        )
        columns = ["id", "action_id", "assigned_role", "status", "created_at"]
        rows = [
            {
                "id": str(a.id),
                "action_id": str(a.action_id),
                "assigned_role": a.assigned_role,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in approvals
        ]
        return columns, rows, len(rows)

    async def _resolve_audit_data(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        request: RuntimeDataQueryRequest,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Resolve append-only audit trail events with deterministic limit and offset pagination."""
        count_stmt = (
            select(func.count(AuditEvent.id))
            .where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.project_id == project_id,
            )
        )
        total_rows = (await self.session.execute(count_stmt)).scalar_one() or 0

        aud_stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.project_id == project_id,
            )
            .order_by(desc(AuditEvent.timestamp), desc(AuditEvent.id))
            .limit(request.limit)
            .offset(request.offset)
        )
        aud_res = await self.session.execute(aud_stmt)
        audits = aud_res.scalars().all()
        columns = ["timestamp", "action_type", "affected_entity_type", "outcome_status"]
        rows = [
            {
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "action_type": a.action_type,
                "affected_entity_type": a.affected_entity_type,
                "outcome_status": a.outcome_status,
            }
            for a in audits
        ]
        return columns, rows, total_rows

    @staticmethod
    def _resolve_static_data(
        target_component: ComponentInstance,
    ) -> tuple[list[str], list[dict[str, Any]], int]:
        """Resolve statically configured designer dataset."""
        columns = target_component.properties.get("columns", ["key", "value"])
        rows = target_component.properties.get("static_data", [])
        return columns, rows, len(rows)

    async def execute_runtime_action(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        app_id: uuid.UUID,
        user_id: uuid.UUID,
        request: RuntimeActionExecuteRequest,
    ) -> RuntimeActionExecuteResponse:
        """Execute a governed platform interaction triggered from an application component."""
        pm = await self._verify_project_access(organization_id, project_id, user_id)
        app = await self._get_app_entity(organization_id, project_id, app_id)

        # Determine definition (published version preferred, draft fallback if previewing)
        definition_json = app.draft_definition_json
        if app.published_version is not None:
            ver_stmt = select(ApplicationVersion).where(
                ApplicationVersion.application_id == app.id,
                ApplicationVersion.version == app.published_version,
            )
            ver_row = (await self.session.execute(ver_stmt)).scalar_one_or_none()
            if ver_row:
                definition_json = ver_row.definition_json

        definition = ApplicationDefinition.model_validate(definition_json)
        target_component = self._find_component(definition, request.page_id, request.component_id)

        if not target_component or not target_component.interaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Component '{request.component_id}' or its interaction is not configured.",
            )

        # Enforce component visibility roles (DEF-012-003)
        user_role = pm.project_role if pm else OrgRole.ORG_ADMIN.value
        if (
            target_component.visibility_roles
            and user_role not in target_component.visibility_roles
            and user_role != OrgRole.ORG_ADMIN.value
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{user_role}' is not authorized to interact with component '{request.component_id}'.",
            )

        inter = target_component.interaction
        if inter.requires_confirmation and not request.confirmation_acknowledged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=inter.confirmation_message or "Explicit confirmation is required to proceed.",
            )

        # 1. Action Execution
        if request.action_type == InteractionActionType.EXECUTE_ACTION:
            raw_action = inter.governed_action_type or GovernedActionType.HOLD_INVOICE.value
            governed_action_type = (
                raw_action.value if hasattr(raw_action, "value") else str(raw_action)
            )

            # Validate against server-side allowlist (DEF-012-001)
            valid_action_values = {a.value for a in GovernedActionType}
            if governed_action_type not in valid_action_values:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Action type '{governed_action_type}' is not recognized or permitted.",
                )

            # Mandatory consequential actions always require human approval (DEF-012-001)
            is_mandatory = governed_action_type in MANDATORY_CONSEQUENTIAL_ACTIONS
            is_configured = governed_action_type in definition.governance.approval_required_actions

            if is_mandatory or is_configured:
                # Create a governed Action and Approval record
                now = datetime.now(UTC)
                action = Action(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    action_type=governed_action_type,
                    target_system=inter.target_adapter_type or "SimulatedTargetAdapter",
                    proposed_payload_json=request.payload,
                    is_consequential=True,
                    status=ActionStatus.AWAITING_APPROVAL.value,
                    created_at=now,
                    updated_at=now,
                )
                self.session.add(action)
                await self.session.flush()

                approval = Approval(
                    id=uuid.uuid4(),
                    action_id=action.id,
                    assigned_role=ProjectRole.PROJECT_LEAD.value,
                    status=ApprovalStatus.PENDING.value,
                    created_at=now,
                )
                self.session.add(approval)
                await self.session.commit()

                await self.audit_service.log_event(
                    organization_id=organization_id,
                    project_id=project_id,
                    actor_id=str(user_id),
                    actor_type=ActorType.USER,
                    action_type="APPLICATION_ACTION_EXECUTED",
                    affected_entity_type="Action",
                    affected_entity_id=str(action.id),
                    execution_context={
                        "app_id": str(app.id),
                        "component_id": request.component_id,
                        "status": "APPROVAL_REQUIRED",
                    },
                )
                await self.session.commit()

                return RuntimeActionExecuteResponse(
                    status="PENDING_APPROVAL",
                    message="Action submitted and requires human authorization before execution.",
                    data={"action_id": str(action.id), "approval_id": str(approval.id)},
                    requires_approval=True,
                    approval_id=approval.id,
                )
            else:
                return RuntimeActionExecuteResponse(
                    status="SUCCESS",
                    message=f"Action '{governed_action_type}' executed successfully.",
                    data={"payload": request.payload},
                )

        elif request.action_type == InteractionActionType.APPROVE_ACTION:
            approval_id_str = request.payload.get("approval_id")
            if not approval_id_str:
                raise HTTPException(status_code=400, detail="Missing approval_id in action payload.")

            decision_req = ApprovalDecisionRequest(
                decision=ApprovalStatus.APPROVED,
                rationale=request.payload.get("rationale", "Approved via published application."),
            )
            appr = await self.governance_service.decide_approval(
                organization_id=organization_id,
                project_id=project_id,
                user_id=user_id,
                approval_id=uuid.UUID(approval_id_str),
                req=decision_req,
            )
            return RuntimeActionExecuteResponse(
                status="SUCCESS",
                message="Approval granted successfully.",
                data={"approval_id": str(appr.id), "status": appr.status},
            )

        return RuntimeActionExecuteResponse(
            status="SUCCESS",
            message=f"Interaction '{request.action_type.value}' acknowledged.",
            data={},
        )
