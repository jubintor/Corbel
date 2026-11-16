"""Prompt lifecycle management and version governance service.

Enforces immutable prompt versioning, formal lifecycle transitions:
DRAFT -> TEST -> EVALUATE -> APPROVE -> DEPLOY -> MONITOR -> RETIRE,
and instant production rollback. Adheres to ADR-015 and DOMAIN_MODEL.md Section 4.7.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.ai.exceptions import (
    PromptDefinitionNotFoundException,
    PromptLifecycleException,
    PromptVersionNotFoundException,
)
from corbel.ai.models import (
    PromptDefinition,
    PromptLifecycleState,
    PromptVersion,
)
from corbel.ai.schemas import (
    PromptDefinitionCreate,
    PromptDefinitionResponse,
    PromptVersionCreate,
    PromptVersionResponse,
)

logger = logging.getLogger(__name__)

# Legal lifecycle state transitions
VALID_PROMPT_TRANSITIONS: dict[PromptLifecycleState, set[PromptLifecycleState]] = {
    PromptLifecycleState.DRAFT: {
        PromptLifecycleState.TEST,
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.TEST: {
        PromptLifecycleState.EVALUATE,
        PromptLifecycleState.DRAFT,
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.EVALUATE: {
        PromptLifecycleState.APPROVE,
        PromptLifecycleState.DRAFT,
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.APPROVE: {
        PromptLifecycleState.DEPLOY,
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.DEPLOY: {
        PromptLifecycleState.MONITOR,
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.MONITOR: {
        PromptLifecycleState.RETIRE,
    },
    PromptLifecycleState.RETIRE: {
        PromptLifecycleState.DEPLOY,  # Allowed via explicit rollback
    },
}


class PromptService:
    """Service managing prompt definition catalogs, immutable versions, and lifecycle transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_prompt_definition(
        self,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        req: PromptDefinitionCreate,
    ) -> PromptDefinitionResponse:
        """Create a logical prompt definition asset."""
        prompt_def = PromptDefinition(
            organization_id=None if req.is_system else organization_id,
            is_system=req.is_system,
            name=req.name,
            workflow_association=req.workflow_association,
            description=req.description,
            owner_user_id=user_id,
        )
        self.session.add(prompt_def)
        await self.session.flush()

        if req.initial_version:
            v = PromptVersion(
                prompt_definition_id=prompt_def.id,
                version_tag=req.initial_version.version_tag,
                lifecycle_state=PromptLifecycleState.DRAFT.value,
                model_compatibility=req.initial_version.model_compatibility,
                token_budget_input=req.initial_version.token_budget_input,
                token_budget_output=req.initial_version.token_budget_output,
                template_text=req.initial_version.template_text,
                input_schema_json=req.initial_version.input_schema_json,
                output_schema_json=req.initial_version.output_schema_json,
                created_by=user_id,
            )
            self.session.add(v)

        await self.session.commit()
        return await self.get_prompt_definition(prompt_def.id, organization_id)

    async def get_prompt_definition(
        self,
        prompt_definition_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> PromptDefinitionResponse:
        """Retrieve prompt definition by ID with access control."""
        stmt = (
            select(PromptDefinition)
            .options(selectinload(PromptDefinition.versions))
            .where(
                PromptDefinition.id == prompt_definition_id,
                or_(
                    PromptDefinition.is_system.is_(True),
                    PromptDefinition.organization_id == organization_id,
                ),
            )
        )
        result = await self.session.execute(stmt)
        p_def = result.scalar_one_or_none()
        if not p_def:
            raise PromptDefinitionNotFoundException(str(prompt_definition_id))

        versions_res = [PromptVersionResponse.model_validate(v) for v in p_def.versions]
        res = PromptDefinitionResponse.model_validate(p_def)
        res.versions = versions_res
        return res

    async def list_prompt_definitions(
        self,
        organization_id: uuid.UUID,
        workflow_association: str | None = None,
    ) -> list[PromptDefinitionResponse]:
        """List platform-wide system prompts and organization prompts."""
        stmt = (
            select(PromptDefinition)
            .options(selectinload(PromptDefinition.versions))
            .where(
                or_(
                    PromptDefinition.is_system.is_(True),
                    PromptDefinition.organization_id == organization_id,
                )
            )
            .order_by(PromptDefinition.created_at.desc())
        )
        if workflow_association:
            stmt = stmt.where(PromptDefinition.workflow_association == workflow_association)

        p_defs = (await self.session.execute(stmt)).scalars().all()
        results = []
        for p_def in p_defs:
            v_res = [PromptVersionResponse.model_validate(v) for v in p_def.versions]
            item = PromptDefinitionResponse.model_validate(p_def)
            item.versions = v_res
            results.append(item)
        return results

    async def create_prompt_version(
        self,
        prompt_definition_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        req: PromptVersionCreate,
    ) -> PromptVersionResponse:
        """Create a new immutable version iteration of an existing prompt definition."""
        p_def = await self._get_editable_definition(prompt_definition_id, organization_id)

        # Check duplicate version tag
        existing = next((v for v in p_def.versions if v.version_tag == req.version_tag), None)
        if existing:
            raise PromptLifecycleException(
                existing.lifecycle_state,
                PromptLifecycleState.DRAFT.value,
                f"Version tag '{req.version_tag}' already exists on this definition. Prompt versions are immutable.",
            )

        v = PromptVersion(
            prompt_definition_id=p_def.id,
            version_tag=req.version_tag,
            lifecycle_state=PromptLifecycleState.DRAFT.value,
            model_compatibility=req.model_compatibility,
            token_budget_input=req.token_budget_input,
            token_budget_output=req.token_budget_output,
            template_text=req.template_text,
            input_schema_json=req.input_schema_json,
            output_schema_json=req.output_schema_json,
            created_by=user_id,
        )
        self.session.add(v)
        await self.session.commit()
        await self.session.refresh(v)
        return PromptVersionResponse.model_validate(v)

    async def transition_version_state(
        self,
        prompt_version_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        target_state: PromptLifecycleState,
        rationale: str | None = None,
    ) -> PromptVersionResponse:
        """Transition a prompt version through its formal lifecycle states."""
        stmt = (
            select(PromptVersion)
            .join(PromptDefinition)
            .where(
                PromptVersion.id == prompt_version_id,
                or_(
                    PromptDefinition.is_system.is_(True),
                    PromptDefinition.organization_id == organization_id,
                ),
            )
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        version = result.scalar_one_or_none()
        if not version:
            raise PromptVersionNotFoundException(str(prompt_version_id))

        current_st = PromptLifecycleState(version.lifecycle_state)
        valid_targets = VALID_PROMPT_TRANSITIONS.get(current_st, set())

        if target_state not in valid_targets:
            raise PromptLifecycleException(
                current_st.value,
                target_state.value,
                f"Legal next states from '{current_st.value}' are: {[s.value for s in valid_targets]}",
            )

        now = datetime.now(UTC)
        if target_state == PromptLifecycleState.APPROVE:
            version.approved_by = user_id
            version.approved_at = now

        # If deploying this version, demote any currently active DEPLOY version to MONITOR or RETIRE
        if target_state == PromptLifecycleState.DEPLOY:
            def_stmt = (
                select(PromptVersion)
                .where(
                    PromptVersion.prompt_definition_id == version.prompt_definition_id,
                    PromptVersion.lifecycle_state == PromptLifecycleState.DEPLOY.value,
                    PromptVersion.id != version.id,
                )
                .with_for_update()
            )
            active_versions = (await self.session.execute(def_stmt)).scalars().all()
            for av in active_versions:
                av.lifecycle_state = PromptLifecycleState.RETIRE.value
                logger.info(
                    "Demoted previously deployed prompt version %s (%s) to RETIRE",
                    av.id,
                    av.version_tag,
                )

        version.lifecycle_state = target_state.value
        await self.session.commit()
        await self.session.refresh(version)
        logger.info(
            "Transitioned prompt version %s from %s to %s (rationale=%s)",
            version.id,
            current_st.value,
            target_state.value,
            rationale,
        )
        return PromptVersionResponse.model_validate(version)

    async def rollback(
        self,
        prompt_definition_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        target_version_tag: str,
        rationale: str | None = None,
    ) -> PromptVersionResponse:
        """Instant production rollback: promotes target version to DEPLOY and retires current DEPLOY version."""
        p_def = await self._get_editable_definition(prompt_definition_id, organization_id)

        target_ver = next((v for v in p_def.versions if v.version_tag == target_version_tag), None)
        if not target_ver:
            raise PromptVersionNotFoundException(f"{prompt_definition_id} / {target_version_tag}")

        # Target version must have been previously approved or deployed
        if target_ver.approved_at is None and target_ver.lifecycle_state not in (
            PromptLifecycleState.APPROVE.value,
            PromptLifecycleState.DEPLOY.value,
            PromptLifecycleState.MONITOR.value,
            PromptLifecycleState.RETIRE.value,
        ):
            raise PromptLifecycleException(
                target_ver.lifecycle_state,
                PromptLifecycleState.DEPLOY.value,
                "Cannot rollback to a version that was never approved.",
            )

        # Demote current DEPLOY/MONITOR version
        for v in p_def.versions:
            if v.id != target_ver.id and v.lifecycle_state in (
                PromptLifecycleState.DEPLOY.value,
                PromptLifecycleState.MONITOR.value,
            ):
                v.lifecycle_state = PromptLifecycleState.RETIRE.value

        target_ver.lifecycle_state = PromptLifecycleState.DEPLOY.value
        await self.session.commit()
        await self.session.refresh(target_ver)
        logger.warning(
            "Production rollback executed on definition %s: restored version %s to DEPLOY (rationale=%s)",
            prompt_definition_id,
            target_version_tag,
            rationale,
        )
        return PromptVersionResponse.model_validate(target_ver)

    async def get_active_deployed_prompt(
        self,
        name: str,
        organization_id: uuid.UUID | None = None,
    ) -> PromptVersion | None:
        """Retrieve the currently active DEPLOY prompt version for a given prompt name."""
        stmt = (
            select(PromptVersion)
            .join(PromptDefinition)
            .where(
                PromptDefinition.name == name,
                or_(
                    PromptDefinition.organization_id == organization_id,
                    PromptDefinition.is_system.is_(True),
                ),
                PromptVersion.lifecycle_state.in_(
                    [PromptLifecycleState.DEPLOY.value, PromptLifecycleState.MONITOR.value]
                ),
            )
            .order_by(PromptDefinition.is_system.asc(), PromptVersion.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_editable_definition(
        self,
        prompt_definition_id: uuid.UUID,
        organization_id: uuid.UUID | None,
    ) -> PromptDefinition:
        """Lock and fetch prompt definition, enforcing tenant ownership boundaries."""
        stmt = (
            select(PromptDefinition)
            .options(selectinload(PromptDefinition.versions))
            .where(PromptDefinition.id == prompt_definition_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        p_def = result.scalar_one_or_none()
        if not p_def:
            raise PromptDefinitionNotFoundException(str(prompt_definition_id))

        if p_def.is_system and organization_id is not None:
            raise PromptLifecycleException(
                "SYSTEM",
                "EDIT",
                "Platform-wide system prompt definitions are immutable shared baselines and cannot be modified by tenant organizations.",
            )

        if not p_def.is_system and p_def.organization_id != organization_id:
            raise PromptDefinitionNotFoundException(str(prompt_definition_id))

        return p_def
