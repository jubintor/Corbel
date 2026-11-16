"""Granular financial cost and token attribution service.

Tracks expenditure across Tenant, Project, Use Case, Workflow, Agent, Model,
and records Cost per Successful Task. Adheres to ADR-015 and DOMAIN_MODEL.md Section 4.7.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.models import (
    CostRecord,
    ModelInvocation,
    TaskStatus,
    WorkflowOutcome,
)
from corbel.ai.schemas import CostSummaryResponse

logger = logging.getLogger(__name__)

# Standard model pricing tiers in USD per 1,000,000 tokens
MODEL_PRICING_TIERS: dict[str, dict[str, float]] = {
    "claude-3-5-sonnet": {
        "input_per_m": 3.00,
        "output_per_m": 15.00,
        "cached_input_per_m": 0.30,  # 90% discount on cached tokens
    },
    "claude-3-haiku": {
        "input_per_m": 0.25,
        "output_per_m": 1.25,
        "cached_input_per_m": 0.03,
    },
    "gpt-4o": {
        "input_per_m": 5.00,
        "output_per_m": 15.00,
        "cached_input_per_m": 2.50,
    },
    "gpt-4o-mini": {
        "input_per_m": 0.15,
        "output_per_m": 0.60,
        "cached_input_per_m": 0.075,
    },
    "mock": {
        "input_per_m": 0.00,
        "output_per_m": 0.00,
        "cached_input_per_m": 0.00,
    },
}


class CostService:
    """Service calculating and recording granular multi-dimensional AI costs."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def calculate_cost(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
    ) -> tuple[float, dict[str, Any]]:
        """Calculate dollar cost in USD using model pricing tiers."""
        clean_model = model_name.lower().strip()
        pricing = None
        for key, tier in MODEL_PRICING_TIERS.items():
            if key in clean_model:
                pricing = tier
                break

        if pricing is None:
            # Default to standard sonnet tier if unknown
            pricing = MODEL_PRICING_TIERS["claude-3-5-sonnet"]

        # Effective uncached input tokens
        uncached_input = max(0, input_tokens - cached_input_tokens)

        cost = (
            (uncached_input * pricing["input_per_m"] / 1_000_000.0)
            + (cached_input_tokens * pricing["cached_input_per_m"] / 1_000_000.0)
            + (output_tokens * pricing["output_per_m"] / 1_000_000.0)
        )
        return round(cost, 6), pricing

    async def record_cost(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        model_invocation: ModelInvocation,
        task_execution_id: uuid.UUID | None,
        use_case: str = "procure-to-pay",
        workflow_name: str = "general",
        agent_name: str | None = None,
        workflow_outcome: WorkflowOutcome | str = WorkflowOutcome.SUCCESS,
        task_outcome: TaskStatus | str = TaskStatus.COMPLETED,
    ) -> CostRecord:
        """Create and persist a granular CostRecord for a model invocation."""
        cost_usd, pricing_tier = self.calculate_cost(
            model_name=model_invocation.model_name,
            input_tokens=model_invocation.input_tokens,
            output_tokens=model_invocation.output_tokens,
            cached_input_tokens=model_invocation.cached_input_tokens,
        )

        wf_out_str = (
            workflow_outcome.value
            if isinstance(workflow_outcome, WorkflowOutcome)
            else str(workflow_outcome)
        )
        task_out_str = (
            task_outcome.value
            if isinstance(task_outcome, TaskStatus)
            else str(task_outcome)
        )

        record = CostRecord(
            model_invocation_id=model_invocation.id,
            task_execution_id=task_execution_id,
            organization_id=organization_id,
            project_id=project_id,
            use_case=use_case,
            workflow_name=workflow_name,
            agent_name=agent_name,
            cost_usd=cost_usd,
            model_call_outcome=model_invocation.model_call_outcome,
            workflow_outcome=wf_out_str,
            task_outcome=task_out_str,
            pricing_tier_snapshot_json=pricing_tier,
            is_estimated=True,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        logger.info(
            "Recorded cost $%.6f for invocation %s (workflow=%s, outcome=%s)",
            cost_usd,
            model_invocation.id,
            workflow_name,
            wf_out_str,
        )
        return record

    async def get_cost_summary(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        use_case: str | None = None,
        workflow_name: str | None = None,
    ) -> CostSummaryResponse:
        """Compute aggregated cost report and Cost per Successful Task."""
        stmt = (
            select(CostRecord, ModelInvocation)
            .join(ModelInvocation, CostRecord.model_invocation_id == ModelInvocation.id)
            .where(CostRecord.organization_id == organization_id)
        )
        if project_id is not None:
            stmt = stmt.where(CostRecord.project_id == project_id)
        if use_case is not None:
            stmt = stmt.where(CostRecord.use_case == use_case)
        if workflow_name is not None:
            stmt = stmt.where(CostRecord.workflow_name == workflow_name)

        rows = (await self.session.execute(stmt)).all()

        total_cost = 0.0
        total_tokens = 0
        total_cached_tokens = 0
        successful_task_ids: set[Any] = set()
        successful_tasks_cost = 0.0
        wf_breakdown: dict[str, float] = {}
        model_breakdown: dict[str, float] = {}

        for cost_rec, invoc in rows:
            total_cost += cost_rec.cost_usd
            total_tokens += invoc.input_tokens + invoc.output_tokens
            total_cached_tokens += invoc.cached_input_tokens

            wf = cost_rec.workflow_name or "unknown"
            wf_breakdown[wf] = round(wf_breakdown.get(wf, 0.0) + cost_rec.cost_usd, 6)

            model = invoc.model_name or "unknown"
            model_breakdown[model] = round(model_breakdown.get(model, 0.0) + cost_rec.cost_usd, 6)

            # Check if this invocation contributed to a genuinely successful business task
            if (
                cost_rec.task_outcome == TaskStatus.COMPLETED.value
                and cost_rec.workflow_outcome == WorkflowOutcome.SUCCESS.value
            ):
                task_key = cost_rec.task_execution_id or cost_rec.id
                successful_task_ids.add(task_key)
                successful_tasks_cost += cost_rec.cost_usd

        successful_tasks_count = len(successful_task_ids)
        cost_per_successful_task = (
            round(successful_tasks_cost / successful_tasks_count, 6)
            if successful_tasks_count > 0
            else 0.0
        )

        return CostSummaryResponse(
            total_cost_usd=round(total_cost, 6),
            total_tokens=total_tokens,
            total_cached_tokens=total_cached_tokens,
            invocations_count=len(rows),
            successful_tasks_count=successful_tasks_count,
            cost_per_successful_task=cost_per_successful_task,
            breakdown_by_workflow=wf_breakdown,
            breakdown_by_model=model_breakdown,
        )
