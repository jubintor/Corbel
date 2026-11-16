"""Tests for prompt definition management, immutable versions, lifecycle governance, and rollback."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.ai.exceptions import (
    PromptDefinitionNotFoundException,
    PromptLifecycleException,
)
from corbel.ai.models import PromptLifecycleState
from corbel.ai.prompts.service import PromptService
from corbel.ai.schemas import (
    PromptDefinitionCreate,
    PromptVersionCreate,
)
from corbel.core.database import get_session_factory
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_prompt_definition_lifecycle_and_rollback(async_client: AsyncClient) -> None:
    """Test full prompt lifecycle: create -> DRAFT -> TEST -> EVALUATE -> APPROVE -> DEPLOY -> rollback."""
    user, _, org, _ = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = PromptService(session)

        # 1. Create prompt definition with initial v1.0.0 in DRAFT
        p_def = await service.create_prompt_definition(
            organization_id=org_id,
            user_id=user_id,
            req=PromptDefinitionCreate(
                name="P2P Investigation Assistant",
                workflow_association="INVESTIGATION",
                description="Investigates price variances and invoice discrepancies",
                initial_version=PromptVersionCreate(
                    version_tag="1.0.0",
                    template_text="Analyze finding for PO {po_number} with invoice {inv_number}.",
                ),
            ),
        )
        assert p_def.name == "P2P Investigation Assistant"
        assert len(p_def.versions) == 1
        v1 = p_def.versions[0]
        assert v1.version_tag == "1.0.0"
        assert v1.lifecycle_state == PromptLifecycleState.DRAFT.value

        # 2. Transition through formal lifecycle: DRAFT -> TEST
        v1_test = await service.transition_version_state(
            prompt_version_id=v1.id,
            organization_id=org_id,
            user_id=user_id,
            target_state=PromptLifecycleState.TEST,
        )
        assert v1_test.lifecycle_state == PromptLifecycleState.TEST.value

        # 3. Invalid transition attempt (TEST directly to DEPLOY) must raise PromptLifecycleException
        with pytest.raises(PromptLifecycleException):
            await service.transition_version_state(
                prompt_version_id=v1.id,
                organization_id=org_id,
                user_id=user_id,
                target_state=PromptLifecycleState.DEPLOY,
            )

        # 4. Valid progression: TEST -> EVALUATE -> APPROVE -> DEPLOY
        await service.transition_version_state(
            v1.id, org_id, user_id, PromptLifecycleState.EVALUATE
        )
        v1_approved = await service.transition_version_state(
            v1.id, org_id, user_id, PromptLifecycleState.APPROVE
        )
        assert v1_approved.approved_at is not None
        assert v1_approved.approved_by == user_id

        v1_deployed = await service.transition_version_state(
            v1.id, org_id, user_id, PromptLifecycleState.DEPLOY
        )
        assert v1_deployed.lifecycle_state == PromptLifecycleState.DEPLOY.value

        # 5. Create v2.0.0 (immutable append)
        v2 = await service.create_prompt_version(
            prompt_definition_id=p_def.id,
            organization_id=org_id,
            user_id=user_id,
            req=PromptVersionCreate(
                version_tag="2.0.0",
                template_text="Enhanced template: examine {po_number} line items vs invoice {inv_number}.",
            ),
        )
        assert v2.version_tag == "2.0.0"
        assert v2.lifecycle_state == PromptLifecycleState.DRAFT.value

        # Approve and deploy v2.0.0
        await service.transition_version_state(v2.id, org_id, user_id, PromptLifecycleState.TEST)
        await service.transition_version_state(v2.id, org_id, user_id, PromptLifecycleState.EVALUATE)
        await service.transition_version_state(v2.id, org_id, user_id, PromptLifecycleState.APPROVE)
        v2_deployed = await service.transition_version_state(v2.id, org_id, user_id, PromptLifecycleState.DEPLOY)
        assert v2_deployed.lifecycle_state == PromptLifecycleState.DEPLOY.value

        # v1.0.0 should now be retired
        active_prompt = await service.get_active_deployed_prompt(p_def.name, org_id)
        assert active_prompt is not None
        assert active_prompt.version_tag == "2.0.0"

        # 6. Execute Instant Rollback: restore v1.0.0 to DEPLOY
        rolled_back = await service.rollback(
            prompt_definition_id=p_def.id,
            organization_id=org_id,
            user_id=user_id,
            target_version_tag="1.0.0",
            rationale="Performance regression in v2.0.0",
        )
        assert rolled_back.version_tag == "1.0.0"
        assert rolled_back.lifecycle_state == PromptLifecycleState.DEPLOY.value

        active_now = await service.get_active_deployed_prompt(p_def.name, org_id)
        assert active_now is not None
        assert active_now.version_tag == "1.0.0"


@pytest.mark.anyio
async def test_prompt_tenant_isolation_and_system_protection(async_client: AsyncClient) -> None:
    """Test multi-tenant prompt security:

    1. Org B cannot see or edit Org A's prompt definitions.
    2. Tenant users cannot modify platform-wide system prompt definitions.
    """
    user_a, _, org_a, _ = await setup_test_org_and_project(async_client)
    user_b, _, org_b, _ = await setup_test_org_and_project(async_client)
    org_a_id = uuid.UUID(org_a["id"])
    org_b_id = uuid.UUID(org_b["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        service = PromptService(session)

        # 1. Org A creates a prompt
        prompt_a = await service.create_prompt_definition(
            organization_id=org_a_id,
            user_id=uuid.UUID(user_a["id"]),
            req=PromptDefinitionCreate(
                name="Org A Secret Prompt",
                workflow_association="PROCESS_MINING",
            ),
        )

        # 2. Org B attempts to retrieve Org A's prompt -> PromptDefinitionNotFoundException
        with pytest.raises(PromptDefinitionNotFoundException):
            await service.get_prompt_definition(prompt_a.id, organization_id=org_b_id)

        # 3. Create a platform system prompt
        system_prompt = await service.create_prompt_definition(
            organization_id=None,
            user_id=None,
            req=PromptDefinitionCreate(
                name="Platform Standard Query Compiler",
                workflow_association="DATA_DISCOVERY",
                is_system=True,
            ),
        )
        assert system_prompt.is_system is True

        # 4. Both Org A and Org B can read the system prompt
        sys_read_a = await service.get_prompt_definition(system_prompt.id, organization_id=org_a_id)
        sys_read_b = await service.get_prompt_definition(system_prompt.id, organization_id=org_b_id)
        assert sys_read_a.id == system_prompt.id
        assert sys_read_b.id == system_prompt.id

        # 5. Tenant user attempting to append version to system prompt is blocked
        with pytest.raises(PromptLifecycleException) as exc_info:
            await service.create_prompt_version(
                prompt_definition_id=system_prompt.id,
                organization_id=org_a_id,
                user_id=uuid.UUID(user_a["id"]),
                req=PromptVersionCreate(version_tag="1.0.0", template_text="Hacked prompt template"),
            )
        assert "Platform-wide system prompt definitions are immutable" in str(exc_info.value)
