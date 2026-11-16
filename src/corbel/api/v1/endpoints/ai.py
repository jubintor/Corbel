"""FastAPI router for Phase 8: Complete AI Infrastructure & Bounded State Machines."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.costs.service import CostService
from corbel.ai.evaluation.service import EvaluationService
from corbel.ai.models import WorkflowExecution, WorkflowType
from corbel.ai.prompts.service import PromptService
from corbel.ai.schemas import (
    CostSummaryResponse,
    EvaluationDatasetCreate,
    EvaluationDatasetResponse,
    EvaluationRunRequest,
    EvaluationRunResponse,
    PromptDefinitionCreate,
    PromptDefinitionResponse,
    PromptLifecycleTransitionRequest,
    PromptRollbackRequest,
    PromptVersionCreate,
    PromptVersionResponse,
    TaskCreate,
    TaskResponse,
    WorkflowExecutionResponse,
    WorkflowRunRequest,
)
from corbel.ai.state_machines.base import BoundedStateMachine, StateMachineResult
from corbel.ai.state_machines.data_discovery import DataDiscoveryStateMachine
from corbel.ai.state_machines.process_investigation import ProcessInvestigationStateMachine
from corbel.ai.state_machines.rule_generation import RuleGenerationStateMachine
from corbel.ai.tasks.manager import TaskManager
from corbel.core.database import get_db_session
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.tenancy.service import TenancyService

router = APIRouter(tags=["AI Infrastructure & Bounded State Machines"])


# -----------------------------------------------------------------------------
# Dependency Helpers
# -----------------------------------------------------------------------------


def get_task_manager(session: AsyncSession = Depends(get_db_session)) -> TaskManager:
    return TaskManager(session)


def get_cost_service(session: AsyncSession = Depends(get_db_session)) -> CostService:
    return CostService(session)


def get_prompt_service(session: AsyncSession = Depends(get_db_session)) -> PromptService:
    return PromptService(session)


def get_evaluation_service(session: AsyncSession = Depends(get_db_session)) -> EvaluationService:
    return EvaluationService(session)


# -----------------------------------------------------------------------------
# 1. Durable Background Task Execution Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule Durable Task",
    description="Enqueue a durable background task with safe claiming and checkpointing.",
)
async def create_task(
    project_id: uuid.UUID,
    req: TaskCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    manager: TaskManager = Depends(get_task_manager),
) -> TaskResponse:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
    )
    task = await manager.create_task(
        project_id=project_id,
        task_type=req.task_type,
        input_data=req.input_data,
        max_retries=req.max_retries,
    )
    return TaskResponse.model_validate(task)


@router.get(
    "/projects/{project_id}/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Task Status",
    description="Retrieve execution state, checkpoint, and lease status for a durable task.",
)
async def get_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    manager: TaskManager = Depends(get_task_manager),
) -> TaskResponse:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[
            ProjectRole.PROJECT_LEAD,
            ProjectRole.ANALYST,
            ProjectRole.OPERATOR,
            ProjectRole.APPROVER,
            ProjectRole.VIEWER,
        ],
    )
    task = await manager.get_task(task_id)
    return TaskResponse.model_validate(task)


@router.post(
    "/projects/{project_id}/tasks/{task_id}/cancel",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Task",
    description="Submit a cancellation request for a running durable task at its next safe boundary.",
)
async def cancel_task(
    project_id: uuid.UUID,
    task_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    manager: TaskManager = Depends(get_task_manager),
) -> TaskResponse:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
    )
    task = await manager.request_cancellation(task_id)
    return TaskResponse.model_validate(task)


# -----------------------------------------------------------------------------
# 2. Bounded State Machine Workflow Execution Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/workflows/run",
    response_model=StateMachineResult,
    status_code=status.HTTP_200_OK,
    summary="Execute Bounded State Machine",
    description="Run a task-specific bounded state machine with step limits, scoped tools, and budget guardrails.",
)
async def run_workflow(
    project_id: uuid.UUID,
    req: WorkflowRunRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> StateMachineResult:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
    )

    sm_kwargs = {
        "session": session,
        "organization_id": context.organization_id,
        "project_id": project_id,
        "max_steps": req.max_steps,
        "token_budget": req.token_budget,
        "cost_budget_usd": req.cost_budget_usd,
    }

    machine: BoundedStateMachine
    if req.workflow_type == WorkflowType.DATA_DISCOVERY:
        machine = DataDiscoveryStateMachine(**sm_kwargs)
    elif req.workflow_type in (WorkflowType.PROCESS_MINING, WorkflowType.INVESTIGATION):
        machine = ProcessInvestigationStateMachine(**sm_kwargs)
    elif req.workflow_type == WorkflowType.RULE_GENERATION:
        machine = RuleGenerationStateMachine(**sm_kwargs)
    else:
        machine = DataDiscoveryStateMachine(**sm_kwargs)

    res: StateMachineResult = await machine.run(req.input_parameters)
    return res


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Workflow Execution",
    description="Retrieve execution state, step count, and output data for an analytical workflow.",
)
async def get_workflow(
    project_id: uuid.UUID,
    workflow_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowExecutionResponse:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[
            ProjectRole.PROJECT_LEAD,
            ProjectRole.ANALYST,
            ProjectRole.OPERATOR,
            ProjectRole.APPROVER,
            ProjectRole.VIEWER,
        ],
    )
    stmt = WorkflowExecution.__table__.select().where(
        WorkflowExecution.id == workflow_id,
        WorkflowExecution.project_id == project_id,
    )
    row = (await session.execute(stmt)).mappings().one_or_none()
    if not row:
        from corbel.ai.exceptions import WorkflowNotFoundException
        raise WorkflowNotFoundException(str(workflow_id))
    return WorkflowExecutionResponse.model_validate(row)


# -----------------------------------------------------------------------------
# 3. Prompt Management & Lifecycle Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/prompts",
    response_model=PromptDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Prompt Definition",
    description="Create a logical prompt definition asset under the active organization or system baseline.",
)
async def create_prompt_definition(
    req: PromptDefinitionCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> PromptDefinitionResponse:
    return await service.create_prompt_definition(
        organization_id=context.organization_id,
        user_id=context.user_id,
        req=req,
    )


@router.get(
    "/prompts",
    response_model=list[PromptDefinitionResponse],
    status_code=status.HTTP_200_OK,
    summary="List Prompt Definitions",
    description="List all platform-wide system prompts and organization-owned prompt definitions.",
)
async def list_prompt_definitions(
    workflow_association: str | None = Query(default=None),
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> list[PromptDefinitionResponse]:
    return await service.list_prompt_definitions(
        organization_id=context.organization_id,
        workflow_association=workflow_association,
    )


@router.get(
    "/prompts/{prompt_id}",
    response_model=PromptDefinitionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Prompt Definition",
    description="Retrieve prompt definition with its full version history.",
)
async def get_prompt_definition(
    prompt_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> PromptDefinitionResponse:
    return await service.get_prompt_definition(
        prompt_definition_id=prompt_id,
        organization_id=context.organization_id,
    )


@router.post(
    "/prompts/{prompt_id}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Prompt Version",
    description="Append an immutable prompt version to a definition in DRAFT state.",
)
async def create_prompt_version(
    prompt_id: uuid.UUID,
    req: PromptVersionCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> PromptVersionResponse:
    return await service.create_prompt_version(
        prompt_definition_id=prompt_id,
        organization_id=context.organization_id,
        user_id=context.user_id,
        req=req,
    )


@router.post(
    "/prompts/versions/{version_id}/transition",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Transition Prompt Lifecycle State",
    description="Formally transition a prompt version: DRAFT -> TEST -> EVALUATE -> APPROVE -> DEPLOY -> MONITOR -> RETIRE.",
)
async def transition_prompt_version(
    version_id: uuid.UUID,
    req: PromptLifecycleTransitionRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> PromptVersionResponse:
    return await service.transition_version_state(
        prompt_version_id=version_id,
        organization_id=context.organization_id,
        user_id=context.user_id,
        target_state=req.target_state,
        rationale=req.rationale,
    )


@router.post(
    "/prompts/{prompt_id}/rollback",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Rollback Prompt Version",
    description="Restore production deployment reference to a previously approved immutable prompt version.",
)
async def rollback_prompt_version(
    prompt_id: uuid.UUID,
    req: PromptRollbackRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: PromptService = Depends(get_prompt_service),
) -> PromptVersionResponse:
    return await service.rollback(
        prompt_definition_id=prompt_id,
        organization_id=context.organization_id,
        user_id=context.user_id,
        target_version_tag=req.target_version_tag,
        rationale=req.rationale,
    )


# -----------------------------------------------------------------------------
# 4. AI Economics & Cost Attribution Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/ai/costs/summary",
    response_model=CostSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Project AI Cost Summary",
    description="Calculate multi-dimensional cost breakdown and Cost per Successful Task for a project.",
)
async def get_project_cost_summary(
    project_id: uuid.UUID,
    use_case: str | None = Query(default=None),
    workflow_name: str | None = Query(default=None),
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
    cost_service: CostService = Depends(get_cost_service),
) -> CostSummaryResponse:
    tenancy = TenancyService(session)
    await tenancy.get_project(context.organization_id, project_id, context.user_id)
    await tenancy.verify_project_access(
        context.organization_id,
        project_id,
        context.user_id,
        min_role=[
            ProjectRole.PROJECT_LEAD,
            ProjectRole.ANALYST,
            ProjectRole.OPERATOR,
            ProjectRole.APPROVER,
            ProjectRole.VIEWER,
        ],
    )
    return await cost_service.get_cost_summary(
        organization_id=context.organization_id,
        project_id=project_id,
        use_case=use_case,
        workflow_name=workflow_name,
    )


# -----------------------------------------------------------------------------
# 5. AI Evaluation & Regression Framework Endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/evaluations/datasets",
    response_model=EvaluationDatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Evaluation Dataset",
    description="Create a versioned regression benchmark dataset with test cases and expected outcomes.",
)
async def create_evaluation_dataset(
    req: EvaluationDatasetCreate,
    context: TenantContext = Depends(get_active_tenant_context),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationDatasetResponse:
    return await service.create_dataset(
        organization_id=context.organization_id,
        req=req,
    )


@router.get(
    "/evaluations/datasets",
    response_model=list[EvaluationDatasetResponse],
    status_code=status.HTTP_200_OK,
    summary="List Evaluation Datasets",
    description="List system baseline and organization-owned evaluation benchmark datasets.",
)
async def list_evaluation_datasets(
    domain: str | None = Query(default=None),
    context: TenantContext = Depends(get_active_tenant_context),
    service: EvaluationService = Depends(get_evaluation_service),
) -> list[EvaluationDatasetResponse]:
    return await service.list_datasets(
        organization_id=context.organization_id,
        domain=domain,
    )


@router.post(
    "/evaluations/runs",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run Evaluation Benchmark",
    description="Execute an automated regression benchmark suite against a target prompt or model.",
)
async def trigger_evaluation_run(
    req: EvaluationRunRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationRunResponse:
    return await service.trigger_run(
        organization_id=context.organization_id,
        req=req,
    )


@router.get(
    "/evaluations/runs/{run_id}",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Evaluation Run Detail",
    description="Retrieve evaluation benchmark run with detailed scoring metrics and test case diagnostics.",
)
async def get_evaluation_run(
    run_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    service: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationRunResponse:
    return await service.get_run(
        run_id=run_id,
        organization_id=context.organization_id,
    )
