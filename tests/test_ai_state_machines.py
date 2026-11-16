"""Tests for task-specific bounded state machines, tool registry, and execution guardrails."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.ai.exceptions import (
    ToolPermissionException,
    ToolValidationException,
    WorkflowBudgetExceededException,
)
from corbel.ai.models import WorkflowStatus
from corbel.ai.state_machines.data_discovery import DataDiscoveryStateMachine
from corbel.ai.state_machines.process_investigation import ProcessInvestigationStateMachine
from corbel.ai.state_machines.rule_generation import RuleGenerationStateMachine
from corbel.ai.tools.registry import get_default_tool_registry
from corbel.core.database import get_session_factory
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_process_investigation_state_machine_fact_vs_hypothesis_separation(
    async_client: AsyncClient,
) -> None:
    """Test ProcessInvestigationStateMachine:

    1. Executes full sequence: Detect Finding -> Retrieve Events -> Correlate Objects -> Investigate -> Verify Facts -> Explain Hypothesis.
    2. Strictly separates verified transactional facts from causal hypotheses.
    3. Records ModelInvocation and CostRecord.
    """
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        machine = ProcessInvestigationStateMachine(
            session=session,
            organization_id=org_id,
            project_id=project_id,
            max_steps=8,
        )

        input_params = {
            "case_identifier": "CASE-P2P-9041",
            "finding_type": "PRICE_VARIANCE",
        }
        result = await machine.run(input_params)

        assert result.status == WorkflowStatus.COMPLETED.value
        assert result.steps_executed == 6
        assert result.final_state == "COMPLETED"

        # Verify strict separation of facts and hypotheses
        assert len(result.verified_facts) > 0
        assert len(result.hypotheses) > 0

        # Facts must contain verified transaction details
        fact_types = [f["fact_type"] for f in result.verified_facts]
        assert "PROCESS_TIMELINE" in fact_types
        assert "TRANSACTION_VARIANCE" in fact_types

        # Hypotheses must clearly represent probabilistic causal reasoning
        assert any("Candidate causal hypothesis" in h for h in result.hypotheses)

        # Budget tracking
        assert result.tokens_consumed > 0
        assert result.cost_usd >= 0.0


@pytest.mark.anyio
async def test_data_discovery_state_machine_execution(async_client: AsyncClient) -> None:
    """Test DataDiscoveryStateMachine execution through schema inspection, profiling, entity inference, invariant validation, and model saving."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        machine = DataDiscoveryStateMachine(
            session=session,
            organization_id=org_id,
            project_id=project_id,
            max_steps=8,
        )

        result = await machine.run({"dataset_name": "raw_invoices"})
        assert result.status == WorkflowStatus.COMPLETED.value
        assert result.steps_executed == 5
        assert result.result_data["saved_model"]["status"] == "VALIDATED"


@pytest.mark.anyio
async def test_rule_generation_state_machine_execution(async_client: AsyncClient) -> None:
    """Test RuleGenerationStateMachine: Observe -> Identify Pattern -> Propose Rule -> Test -> Validate -> Activate."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        machine = RuleGenerationStateMachine(
            session=session,
            organization_id=org_id,
            project_id=project_id,
            max_steps=8,
        )

        result = await machine.run({"target_entity": "PurchaseOrder"})
        assert result.status == WorkflowStatus.COMPLETED.value
        assert result.result_data["activated_rule"]["status"] == "ACTIVE"
        assert result.result_data["activated_rule"]["rule_code"] == "PO_DELIVERY_SLA_5_DAYS"


@pytest.mark.anyio
async def test_step_limit_budget_guardrail(async_client: AsyncClient) -> None:
    """Test that exceeding max_steps raises WorkflowBudgetExceededException and halts execution."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Set max_steps to 2, less than the 5 steps required to complete
        machine = ProcessInvestigationStateMachine(
            session=session,
            organization_id=org_id,
            project_id=project_id,
            max_steps=2,
        )

        with pytest.raises(WorkflowBudgetExceededException) as exc_info:
            await machine.run({"case_identifier": "CASE-P2P-FAIL"})
        assert "exceeded maximum allowable steps limit" in str(exc_info.value)


@pytest.mark.anyio
async def test_tool_registry_permissions_and_validation() -> None:
    """Test ToolRegistry parameter validation and permission allowlists."""
    registry = get_default_tool_registry()

    # 1. Valid tool execution
    res = await registry.execute(
        name="calculate_variance",
        arguments={"invoice_amount": 1050.0, "po_amount": 1000.0, "tolerance_pct": 0.5},
        allowed_tools=["calculate_variance"],
    )
    assert res["variance_pct"] == 5.0
    assert res["is_breach"] is True

    # 2. Invalid parameter schema -> ToolValidationException
    with pytest.raises(ToolValidationException):
        await registry.execute(
            name="calculate_variance",
            arguments={"invoice_amount": "NOT_A_NUMBER", "po_amount": 1000.0},
            allowed_tools=["calculate_variance"],
        )

    # 3. Disallowed tool -> ToolPermissionException
    with pytest.raises(ToolPermissionException):
        await registry.execute(
            name="calculate_variance",
            arguments={"invoice_amount": 1000.0, "po_amount": 1000.0},
            allowed_tools=["inspect_schema"],  # calculate_variance not permitted
        )
