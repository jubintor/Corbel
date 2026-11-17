"""Business service for Phase 11: Use-Case Architect."""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.costs.service import CostService
from corbel.ai.gateway import AIGateway
from corbel.ai.schemas import ModelRequest
from corbel.domains.governance.audit import AuditService
from corbel.domains.governance.models import ActorType
from corbel.domains.tenancy.models import OrgRole, ProjectRole
from corbel.domains.tenancy.service import TenancyService
from corbel.domains.use_case_architect.models import (
    MessageSenderRole,
    UseCase,
    UseCaseMessage,
    UseCaseSpecificationVersion,
    UseCaseStatus,
)
from corbel.domains.use_case_architect.prompts import (
    DISCOVERY_SYSTEM_PROMPT,
    SPECIFICATION_SYSTEM_PROMPT,
)
from corbel.domains.use_case_architect.schemas import (
    ArchitectureAlternative,
    ArchitectureRationale,
    DiscoveryMessageItem,
    DiscoveryTurnResponse,
    EstimatesAndAssumptions,
    ExtractedRequirements,
    ImplementationMilestone,
    InputsAndOutputs,
    SpecificationDiffResponse,
    SpecificationVersionSummary,
    TechnicalRisk,
    UseCaseCreateRequest,
    UseCaseDetailResponse,
    UseCaseResponse,
    UseCaseSpecification,
    UseCaseUpdateRequest,
)

logger = logging.getLogger(__name__)


class UseCaseArchitectService:
    """Orchestrates use-case discovery, technical architecture synthesis, and governance."""

    def __init__(
        self,
        session: AsyncSession,
        tenancy_service: TenancyService,
        audit_service: AuditService,
        cost_service: CostService,
        ai_gateway: AIGateway | None = None,
    ) -> None:
        self.session = session
        self.tenancy_service = tenancy_service
        self.audit_service = audit_service
        self.cost_service = cost_service
        self.ai_gateway = ai_gateway or AIGateway()

    # =========================================================================
    # Tenancy & Authorization Verification
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
            org_id=organization_id, project_id=project_id, user_id=user_id, min_role=min_role
        )

    async def _get_use_case_entity(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
    ) -> UseCase:
        """Retrieve a UseCase ensuring strict tenant and project isolation."""
        stmt = select(UseCase).where(
            UseCase.id == use_case_id,
            UseCase.organization_id == organization_id,
            UseCase.project_id == project_id,
        )
        result = await self.session.execute(stmt)
        use_case = result.scalar_one_or_none()
        if not use_case:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Use case {use_case_id} not found in project {project_id}.",
            )
        return use_case

    # =========================================================================
    # Use Case Lifecycle & CRUD
    # =========================================================================

    async def create_use_case(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: UseCaseCreateRequest,
    ) -> UseCaseResponse:
        """Create a new use case, initiate discovery dialogue, and log audit event."""
        await self._verify_project_access(organization_id, project_id, user_id)

        now = datetime.now(UTC)
        use_case = UseCase(
            id=uuid.uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            status=UseCaseStatus.DRAFT.value,
            created_by=user_id,
            current_version=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(use_case)
        await self.session.flush()

        # Add initial user problem statement
        user_msg = UseCaseMessage(
            id=uuid.uuid4(),
            use_case_id=use_case.id,
            sender_role=MessageSenderRole.USER.value,
            message_text=payload.description,
            created_at=now,
        )
        self.session.add(user_msg)

        # Execute initial discovery turn
        try:
            discovery_result = await self._run_discovery_turn(
                use_case=use_case,
                new_input=payload.description,
                history=[user_msg],
            )
            asst_msg = UseCaseMessage(
                id=uuid.uuid4(),
                use_case_id=use_case.id,
                sender_role=MessageSenderRole.ASSISTANT.value,
                message_text=discovery_result["summary"],
                extracted_requirements_json=discovery_result["extracted_requirements"],
                clarification_questions_json=discovery_result["clarification_questions"],
                created_at=datetime.now(UTC),
            )
            self.session.add(asst_msg)
            use_case.status = UseCaseStatus.DISCOVERY.value
        except Exception as e:
            logger.warning("Initial AI discovery turn failed; saving draft use case without blocking: %s", e)
            # Retain DRAFT status so provider failure does not destroy saved work

        await self.session.commit()
        await self.session.refresh(use_case)

        # Native Phase 10 Audit Event
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="USE_CASE_CREATED",
            affected_entity_type="UseCase",
            affected_entity_id=str(use_case.id),
            execution_context={
                "title": use_case.title,
                "status": use_case.status,
            },
        )
        await self.session.commit()

        return UseCaseResponse.model_validate(use_case)

    async def get_use_case(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UseCaseDetailResponse:
        """Get complete details for a use case including messages and latest specification."""
        await self._verify_project_access(organization_id, project_id, user_id)
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)

        # Load messages
        msg_stmt = (
            select(UseCaseMessage)
            .where(UseCaseMessage.use_case_id == use_case_id)
            .order_by(UseCaseMessage.created_at.asc())
        )
        messages_result = await self.session.execute(msg_stmt)
        messages = messages_result.scalars().all()

        # Load latest specification if exists
        spec_stmt = (
            select(UseCaseSpecificationVersion)
            .where(UseCaseSpecificationVersion.use_case_id == use_case_id)
            .order_by(desc(UseCaseSpecificationVersion.version))
            .limit(1)
        )
        spec_result = await self.session.execute(spec_stmt)
        latest_spec_row = spec_result.scalar_one_or_none()

        latest_spec: UseCaseSpecification | None = None
        if latest_spec_row:
            latest_spec = UseCaseSpecification.model_validate(latest_spec_row.specification_json)

        detail = UseCaseDetailResponse(
            id=use_case.id,
            organization_id=use_case.organization_id,
            project_id=use_case.project_id,
            title=use_case.title,
            description=use_case.description,
            status=use_case.status,
            current_version=use_case.current_version,
            created_by=use_case.created_by,
            approved_by=use_case.approved_by,
            approved_at=use_case.approved_at,
            created_at=use_case.created_at,
            updated_at=use_case.updated_at,
            messages=[
                DiscoveryMessageItem(
                    id=m.id,
                    sender_role=m.sender_role,
                    message_text=m.message_text,
                    extracted_requirements=ExtractedRequirements.model_validate(m.extracted_requirements_json)
                    if m.extracted_requirements_json
                    else None,
                    clarification_questions=m.clarification_questions_json,
                    created_at=m.created_at,
                )
                for m in messages
            ],
            latest_specification=latest_spec,
        )
        return detail

    async def list_use_cases(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[UseCaseResponse]:
        """List all use cases in a project."""
        await self._verify_project_access(organization_id, project_id, user_id)
        stmt = (
            select(UseCase)
            .where(
                UseCase.organization_id == organization_id,
                UseCase.project_id == project_id,
            )
            .order_by(desc(UseCase.created_at))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [UseCaseResponse.model_validate(r) for r in rows]

    async def update_use_case(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: UseCaseUpdateRequest,
    ) -> UseCaseResponse:
        """Update use case title or description."""
        await self._verify_project_access(organization_id, project_id, user_id)
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)

        if use_case.status == UseCaseStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot modify an approved use case. Create a new revision or use case.",
            )

        if payload.title is not None:
            use_case.title = payload.title
        if payload.description is not None:
            use_case.description = payload.description
        use_case.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(use_case)

        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="USE_CASE_UPDATED",
            affected_entity_type="UseCase",
            affected_entity_id=str(use_case.id),
            execution_context={"title": use_case.title},
        )
        await self.session.commit()

        return UseCaseResponse.model_validate(use_case)

    async def delete_use_case(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a use case and audit the deletion."""
        await self._verify_project_access(
            organization_id,
            project_id,
            user_id,
            min_role=[ProjectRole.PROJECT_LEAD],
        )
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)
        await self.session.delete(use_case)
        await self.session.commit()

        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="USE_CASE_DELETED",
            affected_entity_type="UseCase",
            affected_entity_id=str(use_case_id),
        )
        await self.session.commit()

    # =========================================================================
    # Discovery Dialogue
    # =========================================================================

    async def add_discovery_message(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
        message_text: str,
    ) -> DiscoveryTurnResponse:
        """Post a user response, run an AI discovery turn, and return updated state."""
        await self._verify_project_access(organization_id, project_id, user_id)
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)

        # 1. Persist user message
        user_msg = UseCaseMessage(
            id=uuid.uuid4(),
            use_case_id=use_case.id,
            sender_role=MessageSenderRole.USER.value,
            message_text=message_text,
            created_at=datetime.now(UTC),
        )
        self.session.add(user_msg)
        await self.session.flush()

        # 2. Fetch history
        stmt = (
            select(UseCaseMessage)
            .where(UseCaseMessage.use_case_id == use_case_id)
            .order_by(UseCaseMessage.created_at.asc())
        )
        hist_result = await self.session.execute(stmt)
        history = list(hist_result.scalars().all())

        # 3. Run bounded discovery turn
        discovery_result = await self._run_discovery_turn(
            use_case=use_case,
            new_input=message_text,
            history=history,
        )

        asst_msg = UseCaseMessage(
            id=uuid.uuid4(),
            use_case_id=use_case.id,
            sender_role=MessageSenderRole.ASSISTANT.value,
            message_text=discovery_result["summary"],
            extracted_requirements_json=discovery_result["extracted_requirements"],
            clarification_questions_json=discovery_result["clarification_questions"],
            created_at=datetime.now(UTC),
        )
        self.session.add(asst_msg)

        if use_case.status == UseCaseStatus.DRAFT.value:
            use_case.status = UseCaseStatus.DISCOVERY.value
        use_case.updated_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(user_msg)
        await self.session.refresh(asst_msg)

        # Audit discovery turn
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="USE_CASE_DISCOVERY_TURN",
            affected_entity_type="UseCase",
            affected_entity_id=str(use_case.id),
            execution_context={
                "message_length": len(message_text),
                "questions_count": len(discovery_result.get("clarification_questions", [])),
                "can_generate": discovery_result.get("can_generate_specification", False),
            },
        )
        await self.session.commit()

        user_item = DiscoveryMessageItem(
            id=user_msg.id,
            sender_role=user_msg.sender_role,
            message_text=user_msg.message_text,
            created_at=user_msg.created_at,
        )
        asst_item = DiscoveryMessageItem(
            id=asst_msg.id,
            sender_role=asst_msg.sender_role,
            message_text=asst_msg.message_text,
            extracted_requirements=ExtractedRequirements.model_validate(asst_msg.extracted_requirements_json)
            if asst_msg.extracted_requirements_json
            else None,
            clarification_questions=asst_msg.clarification_questions_json,
            created_at=asst_msg.created_at,
        )

        return DiscoveryTurnResponse(
            user_message=user_item,
            assistant_message=asst_item,
            can_generate_specification=discovery_result.get("can_generate_specification", False),
        )

    # =========================================================================
    # Specification Synthesis & Versioning
    # =========================================================================

    async def generate_specification(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UseCaseSpecification:
        """Synthesize a complete, versioned structured UseCaseSpecification."""
        await self._verify_project_access(organization_id, project_id, user_id)
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)

        # Fetch messages
        stmt = (
            select(UseCaseMessage)
            .where(UseCaseMessage.use_case_id == use_case_id)
            .order_by(UseCaseMessage.created_at.asc())
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())

        new_version = use_case.current_version + 1
        spec = await self._synthesize_specification_with_ai(
            use_case=use_case,
            messages=messages,
            target_version=new_version,
        )

        # Persist version
        spec_version_row = UseCaseSpecificationVersion(
            id=uuid.uuid4(),
            use_case_id=use_case.id,
            version=new_version,
            specification_json=spec.model_dump(mode="json"),
            created_by=user_id,
            created_at=datetime.now(UTC),
        )
        self.session.add(spec_version_row)

        use_case.current_version = new_version
        use_case.status = UseCaseStatus.REVIEW.value
        use_case.updated_at = datetime.now(UTC)

        await self.session.commit()

        # Audit event
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="SPECIFICATION_GENERATED",
            affected_entity_type="UseCaseSpecification",
            affected_entity_id=str(spec_version_row.id),
            execution_context={
                "version": new_version,
                "proposed_architecture": spec.proposed_architecture,
                "risk_level": spec.risk_level,
            },
        )
        await self.session.commit()

        return spec

    async def list_specifications(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[SpecificationVersionSummary]:
        """List all specification revisions for a use case."""
        await self._verify_project_access(organization_id, project_id, user_id)
        await self._get_use_case_entity(organization_id, project_id, use_case_id)

        stmt = (
            select(UseCaseSpecificationVersion)
            .where(UseCaseSpecificationVersion.use_case_id == use_case_id)
            .order_by(desc(UseCaseSpecificationVersion.version))
        )
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        summaries: list[SpecificationVersionSummary] = []
        for r in rows:
            json_data = r.specification_json
            summaries.append(
                SpecificationVersionSummary(
                    version=r.version,
                    created_by=r.created_by,
                    created_at=r.created_at,
                    title=json_data.get("title", ""),
                    proposed_architecture=json_data.get("proposed_architecture", ""),
                    risk_level=json_data.get("risk_level", "MEDIUM"),
                )
            )
        return summaries

    async def get_specification_version(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        version: int,
        user_id: uuid.UUID,
    ) -> UseCaseSpecification:
        """Retrieve a specific version of a UseCaseSpecification."""
        await self._verify_project_access(organization_id, project_id, user_id)
        await self._get_use_case_entity(organization_id, project_id, use_case_id)

        stmt = select(UseCaseSpecificationVersion).where(
            UseCaseSpecificationVersion.use_case_id == use_case_id,
            UseCaseSpecificationVersion.version == version,
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Specification version {version} not found for use case {use_case_id}.",
            )
        return UseCaseSpecification.model_validate(row.specification_json)

    async def compare_specifications(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        v1: int,
        v2: int,
        user_id: uuid.UUID,
    ) -> SpecificationDiffResponse:
        """Compare two specification revisions and produce a structured diff."""
        await self._verify_project_access(organization_id, project_id, user_id)
        spec1 = await self.get_specification_version(organization_id, project_id, use_case_id, v1, user_id)
        spec2 = await self.get_specification_version(organization_id, project_id, use_case_id, v2, user_id)

        d1 = spec1.model_dump(mode="json")
        d2 = spec2.model_dump(mode="json")

        differences: dict[str, dict[str, Any]] = {}
        ignored_keys = {"version_number", "created_at", "updated_at"}

        all_keys = set(d1.keys()).union(d2.keys())
        for k in all_keys:
            if k in ignored_keys:
                continue
            val1 = d1.get(k)
            val2 = d2.get(k)
            if val1 != val2:
                differences[k] = {"v1": val1, "v2": val2}

        summary = (
            f"Compared version {v1} to {v2}. Found {len(differences)} modified field(s): "
            f"{', '.join(differences.keys()) if differences else 'No substantive differences'}."
        )

        return SpecificationDiffResponse(
            use_case_id=use_case_id,
            v1=v1,
            v2=v2,
            differences=differences,
            summary=summary,
        )

    async def approve_specification(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        use_case_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> UseCaseResponse:
        """Approve the current specification design. Requires PROJECT_LEAD or ORG_ADMIN."""
        pm = await self._verify_project_access(
            organization_id,
            project_id,
            user_id,
            min_role=[ProjectRole.PROJECT_LEAD],
        )
        user_role = pm.role if pm else OrgRole.ORG_ADMIN.value
        use_case = await self._get_use_case_entity(organization_id, project_id, use_case_id)

        if use_case.current_version < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot approve a use case without at least one generated specification.",
            )

        now = datetime.now(UTC)
        use_case.status = UseCaseStatus.APPROVED.value
        use_case.approved_by = user_id
        use_case.approved_at = now
        use_case.updated_at = now

        # Update specification status in the latest record
        spec_stmt = (
            select(UseCaseSpecificationVersion)
            .where(
                UseCaseSpecificationVersion.use_case_id == use_case_id,
                UseCaseSpecificationVersion.version == use_case.current_version,
            )
        )
        spec_res = await self.session.execute(spec_stmt)
        latest_spec_row = spec_res.scalar_one_or_none()
        if latest_spec_row:
            spec_dict = dict(latest_spec_row.specification_json)
            spec_dict["specification_status"] = "APPROVED"
            spec_dict["updated_at"] = now.isoformat()
            latest_spec_row.specification_json = spec_dict

        await self.session.commit()
        await self.session.refresh(use_case)

        # Audit event
        await self.audit_service.log_event(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=str(user_id),
            actor_type=ActorType.USER,
            action_type="SPECIFICATION_APPROVED",
            affected_entity_type="UseCase",
            affected_entity_id=str(use_case.id),
            execution_context={
                "version": use_case.current_version,
                "approved_by_role": user_role,
            },
        )
        await self.session.commit()

        return UseCaseResponse.model_validate(use_case)

    # =========================================================================
    # Internal AI Orchestration & Bounded Reasoning
    # =========================================================================

    async def _run_discovery_turn(
        self,
        use_case: UseCase,
        new_input: str,
        history: list[UseCaseMessage],
    ) -> dict[str, Any]:
        """Run a single bounded discovery turn via AI Gateway, with reliable deterministic heuristic fallback."""
        provider = self.ai_gateway.get_provider()

        # Build prompt context
        conversation_transcript = "\n".join(
            f"{m.sender_role}: {m.message_text}" for m in history if m.message_text
        )

        user_prompt = f"""Use Case Title: {use_case.title}
Problem Statement: {use_case.description}

Conversation Transcript:
{conversation_transcript}

Latest User Input:
{new_input}

Extract requirements and formulate 1-3 targeted clarifying questions in JSON.
"""
        request = ModelRequest(
            system_prompt=DISCOVERY_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=1500,
        )

        try:
            # If provider is mock and hasn't registered a response, use heuristic discovery
            if provider.provider_name == "mock" and not getattr(provider, "_registered_responses", {}):
                return self._heuristic_discovery_analysis(use_case.title, use_case.description, history)

            response = await self.ai_gateway.generate_text(request)
            parsed = self._extract_json(response.content)
            if (
                isinstance(parsed, dict)
                and "summary" in parsed
                and "extracted_requirements" in parsed
            ):
                return parsed
            return self._heuristic_discovery_analysis(use_case.title, use_case.description, history)
        except Exception as e:
            logger.warning("AI discovery generation exception: %s. Falling back to heuristic extraction.", e)
            return self._heuristic_discovery_analysis(use_case.title, use_case.description, history)

    async def _synthesize_specification_with_ai(
        self,
        use_case: UseCase,
        messages: list[UseCaseMessage],
        target_version: int,
    ) -> UseCaseSpecification:
        """Synthesize structured specification via AI Gateway with strict Pydantic validation."""
        provider = self.ai_gateway.get_provider()
        now = datetime.now(UTC)

        # Gather transcript and requirements
        conversation_transcript = "\n".join(
            f"{m.sender_role}: {m.message_text}" for m in messages if m.message_text
        )

        user_prompt = f"""Title: {use_case.title}
Problem Statement: {use_case.description}
Version: {target_version}

Dialogue History:
{conversation_transcript}

Synthesize a production-grade UseCaseSpecification conforming to the schema.
"""
        request = ModelRequest(
            system_prompt=SPECIFICATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=3000,
        )

        # Check if provider is mock without custom registered response
        if provider.provider_name == "mock" and not getattr(provider, "_registered_responses", {}):
            return self._heuristic_specification_synthesis(use_case, messages, target_version, now)

        try:
            validated, _ = await self.ai_gateway.generate_structured(request, UseCaseSpecification)
            # Ensure identifiers and version match authoritatively
            validated.use_case_id = use_case.id
            validated.version_number = target_version
            validated.created_at = now
            validated.updated_at = now
            return validated
        except Exception as e:
            logger.warning(
                "AI Gateway structured specification generation failed: %s. Using heuristic synthesis.",
                e,
            )
            return self._heuristic_specification_synthesis(use_case, messages, target_version, now)

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from markdown code fences or raw text."""
        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return None

    # =========================================================================
    # Deterministic Heuristic Generators (P2P-Aware, Platform-Consistent)
    # =========================================================================

    def _heuristic_discovery_analysis(
        self,
        title: str,
        description: str,
        history: list[UseCaseMessage],
    ) -> dict[str, Any]:
        """Perform deterministic analysis of discovery dialogue extracting requirements and questions."""
        full_text = f"{title} {description} " + " ".join(m.message_text for m in history)
        t_lower = full_text.lower()

        is_p2p = any(k in t_lower for k in ["purchase order", "po", "invoice", "receipt", "variance", "supplier", "procure", "p2p"])

        # Stakeholders
        stakeholders = ["Operations Lead"]
        if "procurement" in t_lower or "buyer" in t_lower or is_p2p:
            stakeholders.extend(["Procurement Manager", "Accounts Payable Specialist"])
        if "finance" in t_lower or "cfo" in t_lower or "audit" in t_lower:
            stakeholders.append("Finance Controller")

        # Source systems
        sources = ["PostgreSQL Operational DB"]
        if "sap" in t_lower or "erp" in t_lower or is_p2p:
            sources.append("ERP (SAP/Oracle)")
        if "warehouse" in t_lower or "wms" in t_lower:
            sources.append("Warehouse Management System (WMS)")
        if "email" in t_lower or "pdf" in t_lower or "contract" in t_lower:
            sources.append("Supplier Contract & Invoice Repository")

        # Inputs & outputs
        inputs = ["Transactional Event Logs"]
        outputs = ["Exception Finding Alerts", "Root-Cause Investigation Report"]
        if is_p2p:
            inputs.extend(["Purchase Orders", "Goods Receipts", "Supplier Invoices"])
            outputs.extend(["Price Variance Calculation", "Recommended Credit Note Action"])

        # Confirmed vs Assumptions
        confirmed = [f"Business Objective: Address '{title}'"]
        if is_p2p:
            confirmed.append("Identified P2P process events (PO -> Goods Receipt -> Invoice -> Match)")
        assumptions = [
            "Assumed standard daily ingestion latency is acceptable",
            "Assumed financial variance calculations must be deterministic with zero model approximation",
        ]

        # Clarification questions
        questions = []
        if "threshold" not in t_lower and "tolerance" not in t_lower:
            questions.append("What is the exact financial variance threshold (e.g., >5% or >$500) that should trigger an exception?")
        if "approval" not in t_lower and "gate" not in t_lower:
            questions.append("Which user roles have authority to approve corrective supplier actions or price adjustments?")
        if len(questions) == 0:
            questions.append("Are there specific supplier contract documents that should be ingested for semantic clause retrieval?")

        summary = (
            f"Understood operational objective for '{title}'. Identified {len(stakeholders)} relevant roles, "
            f"{len(sources)} source systems, and confirmed core transactional inputs. "
            f"Formulated {len(questions)} high-priority clarification question(s) to finalize the specification."
        )

        can_generate = len(history) >= 2 or len(description.split()) > 20

        return {
            "summary": summary,
            "extracted_requirements": {
                "business_objective": f"Resolve operational challenges in: {title}",
                "expected_outcomes": [
                    "Automated detection of transactional anomalies",
                    "Elimination of manual investigation overhead",
                    "Quantifiable operational and financial impact tracking",
                ],
                "stakeholders": stakeholders,
                "workflows": ["Order-to-Delivery Review", "Invoice Exception Approval Workflow"],
                "inputs": inputs,
                "outputs": outputs,
                "source_systems": sources,
                "data_sensitivity": "INTERNAL",
                "freshness_latency": "Near Real-Time (< 5 min) or Hourly Ingestion",
                "confirmed_requirements": confirmed,
                "unverified_assumptions": assumptions,
            },
            "clarification_questions": questions[:3],
            "can_generate_specification": can_generate,
        }

    def _heuristic_specification_synthesis(
        self,
        use_case: UseCase,
        messages: list[UseCaseMessage],
        target_version: int,
        now: datetime,
    ) -> UseCaseSpecification:
        """Heuristically generate a rich, valid, production-grade UseCaseSpecification."""
        full_text = f"{use_case.title} {use_case.description} " + " ".join(m.message_text for m in messages)
        t_lower = full_text.lower()
        is_p2p = any(k in t_lower for k in ["purchase order", "po", "invoice", "receipt", "variance", "supplier", "procure", "p2p"])

        title = use_case.title
        desc = use_case.description

        if is_p2p:
            proposed_arch = (
                "Deterministic Event Monitor Pipeline + Governed Investigation & Document RAG"
            )
            justification = (
                "Procure-to-Pay exception monitoring demands 100% deterministic arithmetic for price "
                "and quantity variance detection. High-risk payment or credit note actions must never be "
                "executed autonomously by LLMs; they require human approval gates under RBAC. Document RAG "
                "is selectively utilized solely for extracting clauses from vendor contracts and delivery receipts."
            )
            deterministic_comps = [
                "Process Event Mining (PO -> Goods Receipt -> Invoice -> 3-Way Match)",
                "Price Variance Arithmetic Engine (absolute & percentage tolerance checks)",
                "Tenancy & RBAC Deterministic Authorization Service",
                "Immutable Append-Only PostgreSQL Audit Logger",
            ]
            retrieval_comps = [
                "PostgreSQL pgvector / Full-Text Document Ingestion for Vendor Master Contracts",
                "Structured SQL Lookups for Transactional PO and Invoice Line Items",
            ]
            agentic_comps = [
                "Bounded Root-Cause Investigation State Machine (Detect -> Retrieve -> Correlate -> Explain)",
            ]
            alternatives = [
                ArchitectureAlternative(
                    approach="Pure Autonomous Agent ReAct Loop",
                    pros=["Flexible natural language goal execution"],
                    cons=[
                        "Non-deterministic math risks financial inaccuracy",
                        "Unbounded token consumption and hallucination risk",
                        "Incompatible with zero-trust enterprise financial controls",
                    ],
                    rejection_reason="Enterprise financial operations require strict deterministic guarantees and human approval gates.",
                ),
                ArchitectureAlternative(
                    approach="Standalone Document RAG Chatbot",
                    pros=["Easy to deploy over unstructured PDFs"],
                    cons=[
                        "Cannot perform deterministic relational variance calculations",
                        "Lacks process event timeline awareness and state tracking",
                    ],
                    rejection_reason="Cannot compute transactional 3-way matches or enforce operational action workflows.",
                ),
            ]
            inputs_outputs = InputsAndOutputs(
                inputs=["Purchase Orders", "Goods Receipts", "Supplier Invoices", "Vendor Invoices", "Supplier Master Data"],
                outputs=["Price Variance Finding Alerts", "Root-Cause Investigation Dossier", "Corrective Action Proposals"],
                decisions=["Variance Tolerance Breach Evaluation", "Credit Note Approval Decision"],
                actions=["Issue Supplier Inquiry", "Request Credit Note", "Hold Invoice Payment"],
            )
            sources = ["ERP (SAP/Oracle)", "Warehouse Management DB", "Vendor Portal"]
            approval_reqs = [
                "Credit note requests exceeding $1,000 require Finance Controller approval",
                "Vendor payment holds require Procurement Lead sign-off",
            ]
            milestones = [
                ImplementationMilestone(
                    milestone_id="M1",
                    title="Data Schema Mapping & Ingestion",
                    description="Configure datasets and map PO, Invoice, and Goods Receipt schemas into Corbel Business Objects.",
                    target_components=["Data Intelligence", "Ontology Engine"],
                    dependencies=["Source ERP access"],
                    estimated_effort="1-2 sprints (estimate)",
                    acceptance_criteria=["Profiled schemas with >99% type accuracy", "All foreign keys validated"],
                ),
                ImplementationMilestone(
                    milestone_id="M2",
                    title="Deterministic Variance Monitors",
                    description="Deploy monitor rules detecting price variances >5% and goods receipt delays >7 days.",
                    target_components=["Process Intelligence", "Adaptive Monitors"],
                    dependencies=["M1"],
                    estimated_effort="1 sprint (estimate)",
                    acceptance_criteria=["Deterministic findings created upon ingestion", "Zero arithmetic hallucination"],
                ),
                ImplementationMilestone(
                    milestone_id="M3",
                    title="Governed Root-Cause Investigation & Human Approval",
                    description="Wire bounded investigation workflow and human approval gates for proposed corrective actions.",
                    target_components=["Governed Investigation", "Native Audit Service"],
                    dependencies=["M2"],
                    estimated_effort="2 sprints (estimate)",
                    acceptance_criteria=["Verified fact vs hypothesis separation", "Immutable audit trail on all approvals"],
                ),
            ]
            risks = [
                TechnicalRisk(
                    risk="Inconsistent PO number formatting across legacy ERP tables",
                    severity="MEDIUM",
                    mitigation="Implement canonical regex cleaning and schema validation during initial profiling.",
                ),
                TechnicalRisk(
                    risk="LLM hallucination during invoice text extraction",
                    severity="HIGH",
                    mitigation="Validate extracted numbers against deterministic database records before raising findings.",
                ),
            ]
        else:
            proposed_arch = "Deterministic Event Pipeline + Governed Operational Intelligence"
            justification = (
                "The operational requirements are best met with deterministic schema validation and event tracking, "
                "paired with governed AI recommendations that strictly require human authorization."
            )
            deterministic_comps = ["PostgreSQL Relational Storage", "Deterministic Business Rule Engine", "RBAC Service"]
            retrieval_comps = ["Structured SQL Querying"]
            agentic_comps = ["Bounded Analysis State Machine"]
            alternatives = [
                ArchitectureAlternative(
                    approach="Unconstrained Autonomous Agents",
                    pros=["High conversational flexibility"],
                    cons=["High cost", "Lack of deterministic auditability"],
                    rejection_reason="Does not meet enterprise predictability standards.",
                )
            ]
            inputs_outputs = InputsAndOutputs(
                inputs=["Operational Log Events", "User Metadata"],
                outputs=["Status Reports", "Exception Alerts"],
                decisions=["Threshold Breach Detection"],
                actions=["Notify Operators", "Update Status"],
            )
            sources = ["Operational Database"]
            approval_reqs = ["Consequential state changes require Operator Lead approval"]
            milestones = [
                ImplementationMilestone(
                    milestone_id="M1",
                    title="Foundation Architecture & Integration",
                    description="Set up data ingestion and baseline monitoring.",
                    target_components=["Data Intelligence"],
                    dependencies=[],
                    estimated_effort="1 sprint (estimate)",
                    acceptance_criteria=["Data ingestion verified"],
                )
            ]
            risks = [
                TechnicalRisk(
                    risk="Source data latency spikes",
                    severity="LOW",
                    mitigation="Configure ingestion timeout alerts and dead-letter queues.",
                )
            ]

        return UseCaseSpecification(
            use_case_id=use_case.id,
            version_number=target_version,
            title=title,
            description=desc,
            business_objective=f"Deliver governed operational automation for: {title}",
            expected_outcomes=[
                "Deterministic detection of operational anomalies",
                "Reduced mean time to resolution (MTTR) with automated root-cause analysis",
                "Complete auditability of every decision and action",
            ],
            stakeholders_and_roles=["Process Owner", "Operations Lead", "Finance Controller"],
            workflow_description="Event Ingestion -> Deterministic Monitoring -> Bounded Investigation -> Human Approval -> Action Execution",
            inputs_and_outputs=inputs_outputs,
            source_systems=sources,
            data_classification="CONFIDENTIAL" if is_p2p else "INTERNAL",
            freshness_and_latency="Near Real-Time (< 5 min latency)",
            retrieval_requirements="Hybrid Structured SQL & Document RAG with verified citation links",
            required_tools_and_actions=inputs_outputs.actions,
            risk_level="HIGH" if is_p2p else "MEDIUM",
            human_approval_requirements=approval_reqs,
            proposed_architecture=proposed_arch,
            architecture_rationale_and_alternatives=ArchitectureRationale(
                recommended_pattern=proposed_arch,
                justification=justification,
                deterministic_components=deterministic_comps,
                retrieval_components=retrieval_comps,
                agentic_components=agentic_comps,
                alternatives_considered=alternatives,
            ),
            implementation_plan=milestones,
            estimates_and_assumptions=EstimatesAndAssumptions(
                delivery_estimates=[
                    "Total estimated implementation: 3-5 sprints (estimate only, not a contractual commitment)",
                ],
                verified_capabilities=[
                    "PostgreSQL relational schema and immutable audit storage",
                    "Deterministic monitor evaluation and threshold checks",
                    "Bounded investigation state machines with fact/hypothesis separation",
                    "Human-in-the-loop approval gates with JWT RBAC enforcement",
                ],
                unverified_assumptions=[
                    "Assumes source system API credentials will be provisioned by customer IT",
                    "Assumes standard volume does not exceed 100,000 events/day without partitioning",
                ],
            ),
            risks_and_dependencies=risks,
            open_questions=[
                "What is the exact escalation path if an approval SLA is breached?",
                "Are there additional external legacy archives requiring batch synchronization?",
            ],
            success_metrics=[
                "Over 80% reduction in manual investigation time",
                "100% of price variance discrepancies detected within 5 minutes of invoice ingestion",
                "Zero unauthorized financial transactions executed",
            ],
            evaluation_plan="Benchmark against historical transaction logs; measure precision, recall, and MTTR reduction.",
            specification_status="REVIEW",
            created_at=now,
            updated_at=now,
        )
