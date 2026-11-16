"""Tests for Corbel AI Granular Cost Attribution and Evaluation Framework."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.ai.costs.service import CostService
from corbel.ai.evaluation.service import EvaluationService
from corbel.ai.models import (
    ModelCallOutcome,
    ModelInvocation,
    TaskExecution,
    TaskStatus,
    TaskType,
    WorkflowExecution,
    WorkflowOutcome,
    WorkflowStatus,
    WorkflowType,
)
from corbel.ai.schemas import EvaluationDatasetCreate, EvaluationRunRequest
from corbel.core.database import get_session_factory
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_cost_service_attribution_and_successful_task_metrics(
    async_client: AsyncClient,
) -> None:
    """Test CostService:

    1. Cost calculation using pricing tiers with cached token discount.
    2. Strict separation of outcome tiers (model call vs workflow vs task).
    3. Computation of Cost per Successful Task.
    """
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        cost_service = CostService(session)

        # 1. Verify pricing calculations
        # Claude 3.5 Sonnet: input $3/M, output $15/M, cached input $0.30/M
        cost_usd, pricing = cost_service.calculate_cost(
            model_name="claude-3-5-sonnet",
            input_tokens=1_000_000,
            output_tokens=100_000,
            cached_input_tokens=500_000,
        )
        # Expected: (uncached 500k * 3) + (cached 500k * 0.3) + (output 100k * 15)
        # = 1.5 + 0.15 + 1.5 = 3.15
        assert abs(cost_usd - 3.15) < 1e-4
        assert pricing["input_per_m"] == 3.0

        # 2. Create tasks with different outcomes
        # Task 1: Completed successfully with 2 model invocations
        task1 = TaskExecution(
            id=uuid.uuid4(),
            project_id=project_id,
            task_type=TaskType.DATASET_IMPORT.value,
            status=TaskStatus.COMPLETED.value,
        )
        session.add(task1)

        wf1 = WorkflowExecution(
            id=uuid.uuid4(),
            task_execution_id=task1.id,
            project_id=project_id,
            workflow_type=WorkflowType.DATA_DISCOVERY.value,
            current_state="COMPLETED",
            status=WorkflowStatus.COMPLETED.value,
        )
        session.add(wf1)
        await session.commit()

        # Invocations for Task 1
        inv1 = ModelInvocation(
            id=uuid.uuid4(),
            workflow_execution_id=wf1.id,
            provider_name="anthropic",
            model_name="claude-3-5-sonnet",
            input_tokens=1000,
            output_tokens=200,
            cached_input_tokens=500,
            latency_ms=250.0,
            model_call_outcome=ModelCallOutcome.SUCCESS.value,
        )
        session.add(inv1)
        await session.commit()

        await cost_service.record_cost(
            organization_id=org_id,
            project_id=project_id,
            model_invocation=inv1,
            task_execution_id=task1.id,
            workflow_name="DATA_DISCOVERY",
            agent_name="DataDiscoveryAgent",
            workflow_outcome=WorkflowOutcome.SUCCESS,
            task_outcome=TaskStatus.COMPLETED,
        )

        inv2 = ModelInvocation(
            id=uuid.uuid4(),
            workflow_execution_id=wf1.id,
            provider_name="openai",
            model_name="gpt-4o",
            input_tokens=2000,
            output_tokens=500,
            cached_input_tokens=0,
            latency_ms=400.0,
            model_call_outcome=ModelCallOutcome.SUCCESS.value,
        )
        session.add(inv2)
        await session.commit()

        await cost_service.record_cost(
            organization_id=org_id,
            project_id=project_id,
            model_invocation=inv2,
            task_execution_id=task1.id,
            workflow_name="DATA_DISCOVERY",
            agent_name="DataDiscoveryAgent",
            workflow_outcome=WorkflowOutcome.SUCCESS,
            task_outcome=TaskStatus.COMPLETED,
        )

        # Task 2: FAILED task (outcome = FAILED)
        task2 = TaskExecution(
            id=uuid.uuid4(),
            project_id=project_id,
            task_type=TaskType.WORKFLOW_RUN.value,
            status=TaskStatus.FAILED.value,
        )
        session.add(task2)
        wf2 = WorkflowExecution(
            id=uuid.uuid4(),
            task_execution_id=task2.id,
            project_id=project_id,
            workflow_type=WorkflowType.INVESTIGATION.value,
            current_state="FAILED",
            status=WorkflowStatus.FAILED.value,
        )
        session.add(wf2)
        await session.commit()

        inv3 = ModelInvocation(
            id=uuid.uuid4(),
            workflow_execution_id=wf2.id,
            provider_name="anthropic",
            model_name="claude-3-5-sonnet",
            input_tokens=5000,
            output_tokens=100,
            cached_input_tokens=0,
            latency_ms=1200.0,
            model_call_outcome=ModelCallOutcome.PROVIDER_ERROR.value,
        )
        session.add(inv3)
        await session.commit()

        await cost_service.record_cost(
            organization_id=org_id,
            project_id=project_id,
            model_invocation=inv3,
            task_execution_id=task2.id,
            workflow_name="INVESTIGATION",
            agent_name="InvestigationAgent",
            workflow_outcome=WorkflowOutcome.FAILED,
            task_outcome=TaskStatus.FAILED,
        )

        # 3. Retrieve Cost Summary
        summary = await cost_service.get_cost_summary(
            organization_id=org_id,
            project_id=project_id,
        )
        assert summary.invocations_count == 3
        assert summary.total_tokens == (1200 + 2500 + 5100)
        assert summary.total_cached_tokens == 500
        assert summary.successful_tasks_count == 1
        assert summary.cost_per_successful_task > 0.0
        assert "DATA_DISCOVERY" in summary.breakdown_by_workflow


@pytest.mark.anyio
async def test_evaluation_framework_benchmarking_and_regression(
    async_client: AsyncClient,
) -> None:
    """Test EvaluationService:

    1. Golden dataset creation and schema validation.
    2. Regression run execution.
    3. Metrics computation (schema compliance, grounding, tool precision, correctness).
    """
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        eval_service = EvaluationService(session)

        # 1. Create Golden Dataset
        dataset_create = EvaluationDatasetCreate(
            name="P2P Invoice Exception Golden Set",
            version="1.0.0",
            domain="procure-to-pay",
            test_cases=[
                {
                    "test_case_id": "TC-01",
                    "input_prompt": "Detect price variance between PO-1001 and INV-5001",
                    "expected_keyword": "variance",
                },
                {
                    "test_case_id": "TC-02",
                    "input_prompt": "Verify delivery receipt GR-9021 for PO-1002",
                    "expected_keyword": "receipt",
                },
            ],
            is_system=False,
        )

        dataset = await eval_service.create_dataset(
            organization_id=org_id,
            req=dataset_create,
        )
        assert dataset.name == "P2P Invoice Exception Golden Set"
        assert len(dataset.test_cases_json) == 2

        # 2. Execute Benchmark Run
        run_request = EvaluationRunRequest(
            evaluation_dataset_id=dataset.id,
            target_model_name="claude-3-5-sonnet",
        )
        run = await eval_service.trigger_run(
            organization_id=org_id,
            req=run_request,
        )
        assert run.status == "COMPLETED"
        assert run.summary_metrics_json is not None
        assert run.summary_metrics_json["total_test_cases"] == 2
        assert run.summary_metrics_json["passed_test_cases"] == 2
        assert run.summary_metrics_json["pass_rate"] == 1.0

        # 3. Retrieve Run and Results
        fetched_run = await eval_service.get_run(run.id, organization_id=org_id)
        assert fetched_run.id == run.id
        assert len(fetched_run.results) == 2
        assert all(r.passed is True for r in fetched_run.results)
