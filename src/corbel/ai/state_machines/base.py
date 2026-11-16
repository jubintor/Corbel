"""Base class for bounded, task-specific state machines in Corbel.

Replaces unconstrained ReAct loops with deterministic state transitions, step caps,
scoped tool allowlists, token/cost budgets, cancellation boundaries, and durable checkpointing.
Adheres strictly to ADR-014, ADR-019, and ARCHITECTURE.md Section 5.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.costs.service import CostService
from corbel.ai.exceptions import (
    WorkflowBudgetExceededException,
    WorkflowExecutionException,
)
from corbel.ai.gateway import AIGateway
from corbel.ai.models import (
    ModelCallOutcome,
    ModelInvocation,
    TaskExecution,
    TaskStatus,
    WorkflowExecution,
    WorkflowOutcome,
    WorkflowStatus,
    WorkflowType,
)
from corbel.ai.schemas import ModelRequest
from corbel.ai.tasks.manager import TaskManager
from corbel.ai.tools.registry import ToolRegistry, get_default_tool_registry

logger = logging.getLogger(__name__)


class StateMachineResult(BaseModel):
    """Execution summary returned by a bounded state machine."""

    workflow_id: uuid.UUID
    workflow_type: str
    status: str
    steps_executed: int
    tokens_consumed: int
    cost_usd: float
    final_state: str
    result_data: dict[str, Any]
    verified_facts: list[dict[str, Any]] = []
    hypotheses: list[str] = []


class BoundedStateMachine(ABC):
    """Abstract base for task-specific finite state machines governing AI workflows."""

    def __init__(
        self,
        session: AsyncSession,
        organization_id: uuid.UUID,
        project_id: uuid.UUID,
        workflow_type: WorkflowType,
        ai_gateway: AIGateway | None = None,
        tool_registry: ToolRegistry | None = None,
        cost_service: CostService | None = None,
        task_manager: TaskManager | None = None,
        max_steps: int = 8,
        token_budget: int = 50000,
        cost_budget_usd: float = 5.0,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.project_id = project_id
        self.workflow_type = workflow_type
        self.ai_gateway = ai_gateway or AIGateway()
        self.tool_registry = tool_registry or get_default_tool_registry()
        self.cost_service = cost_service or CostService(session)
        self.task_manager = task_manager or TaskManager(session)
        self.max_steps = max_steps
        self.token_budget = token_budget
        self.cost_budget_usd = cost_budget_usd

        # Runtime trackers
        self.step_count = 0
        self.tokens_consumed = 0
        self.total_cost_usd = 0.0
        self.current_state = self.initial_state

    @property
    @abstractmethod
    def initial_state(self) -> str:
        """Name of the initial analytical state."""
        ...

    @property
    @abstractmethod
    def legal_transitions(self) -> dict[str, list[str]]:
        """Map of permitted deterministic state transitions."""
        ...

    @property
    @abstractmethod
    def allowed_tools(self) -> list[str]:
        """Explicit allowlist of permitted read-only tools for this workflow."""
        ...

    @abstractmethod
    async def execute_step(
        self,
        state: str,
        context: dict[str, Any],
        execution: WorkflowExecution,
    ) -> tuple[str, dict[str, Any]]:
        """Execute one bounded analytical step and return (next_state, updated_context)."""
        ...

    async def run(
        self,
        input_parameters: dict[str, Any],
        task_execution: TaskExecution | None = None,
    ) -> StateMachineResult:
        """Run the bounded state machine until terminal state, step cap, or cancellation."""
        now = datetime.now(UTC)

        # 1. Initialize WorkflowExecution record in DB
        wf_exec = WorkflowExecution(
            project_id=self.project_id,
            task_execution_id=task_execution.id if task_execution else None,
            workflow_type=self.workflow_type.value,
            workflow_version="1.0.0",
            status=WorkflowStatus.INITIALIZED.value,
            current_state=self.initial_state,
            step_count=0,
            max_steps=self.max_steps,
            token_budget=self.token_budget,
            cost_budget_usd=self.cost_budget_usd,
            input_parameters_json=input_parameters,
            state_data_json={},
            started_at=now,
        )
        self.session.add(wf_exec)
        await self.session.commit()
        await self.session.refresh(wf_exec)

        context: dict[str, Any] = dict(input_parameters)
        wf_exec.status = WorkflowStatus.STEPPING.value

        terminal_states = {"COMPLETED", "FAILED", "CANCELLED", "TERMINAL"}
        final_status = WorkflowStatus.COMPLETED

        try:
            while self.current_state not in terminal_states:
                # 2. Check for cancellation request at safe execution boundary
                if task_execution:
                    is_cancelled = await self.task_manager.is_cancellation_requested(task_execution.id)
                    if is_cancelled:
                        logger.info("Cancellation detected at boundary for workflow %s", wf_exec.id)
                        self.current_state = "CANCELLED"
                        final_status = WorkflowStatus.CANCELLED
                        break

                # 3. Guardrail: Step Cap
                if self.step_count >= self.max_steps:
                    raise WorkflowBudgetExceededException(
                        f"Workflow exceeded maximum allowable steps limit ({self.max_steps}).",
                        details={"step_count": self.step_count, "max_steps": self.max_steps},
                    )

                # 4. Guardrail: Token Budget
                if self.tokens_consumed >= self.token_budget:
                    raise WorkflowBudgetExceededException(
                        f"Workflow exceeded maximum allowable token budget ({self.token_budget}).",
                        details={"tokens_consumed": self.tokens_consumed, "token_budget": self.token_budget},
                    )

                # 5. Guardrail: Cost Budget
                if self.total_cost_usd >= self.cost_budget_usd:
                    raise WorkflowBudgetExceededException(
                        f"Workflow exceeded dollar cost budget (${self.cost_budget_usd:.2f}).",
                        details={"total_cost_usd": self.total_cost_usd, "cost_budget_usd": self.cost_budget_usd},
                    )

                # 6. Execute one state step
                prev_state = self.current_state
                next_state, context = await self.execute_step(self.current_state, context, wf_exec)
                self.step_count += 1

                # 7. Validate deterministic state transition legality
                valid_next = self.legal_transitions.get(prev_state, [])
                if next_state not in valid_next and next_state not in terminal_states:
                    raise WorkflowExecutionException(
                        f"Illegal state transition from '{prev_state}' to '{next_state}'. Permitted: {valid_next}"
                    )

                self.current_state = next_state
                wf_exec.current_state = next_state
                wf_exec.step_count = self.step_count
                wf_exec.state_data_json = context

                # 8. Checkpoint in PostgreSQL
                if task_execution:
                    await self.task_manager.save_checkpoint(
                        task_execution.id,
                        task_execution.worker_id or "in-process",
                        {
                            "workflow_id": str(wf_exec.id),
                            "step_count": self.step_count,
                            "current_state": self.current_state,
                            "context": context,
                        },
                        lease_generation=task_execution.lease_generation,
                    )
                await self.session.commit()

            # Terminal reached
            if self.current_state == "FAILED":
                final_status = WorkflowStatus.FAILED
            elif self.current_state == "CANCELLED":
                final_status = WorkflowStatus.CANCELLED
            else:
                final_status = WorkflowStatus.COMPLETED

        except Exception as exc:
            final_status = WorkflowStatus.FAILED
            wf_exec.status = WorkflowStatus.FAILED.value
            wf_exec.ended_at = datetime.now(UTC)
            await self.session.commit()
            logger.error("State machine execution failed on step %d: %s", self.step_count, exc, exc_info=True)
            raise

        wf_exec.status = final_status.value
        wf_exec.ended_at = datetime.now(UTC)
        wf_exec.result_data_json = context
        await self.session.commit()

        return StateMachineResult(
            workflow_id=wf_exec.id,
            workflow_type=self.workflow_type.value,
            status=final_status.value,
            steps_executed=self.step_count,
            tokens_consumed=self.tokens_consumed,
            cost_usd=self.total_cost_usd,
            final_state=self.current_state,
            result_data=context,
            verified_facts=context.get("verified_facts", []),
            hypotheses=context.get("hypotheses", []),
        )

    async def invoke_model_with_attribution(
        self,
        workflow_execution: WorkflowExecution,
        prompt_text: str,
        system_prompt: str,
        task_execution_id: uuid.UUID | None = None,
        agent_name: str | None = None,
    ) -> str:
        """Call AI Gateway, update token/cost budgets, and record ModelInvocation & CostRecord."""
        req = ModelRequest(system_prompt=system_prompt, user_prompt=prompt_text)
        resp = await self.ai_gateway.generate_text(req)

        # Update budget consumption
        total_call_tokens = resp.token_usage.total_tokens
        cached_call_tokens = resp.token_usage.cached_tokens
        self.tokens_consumed += total_call_tokens

        # Record ModelInvocation
        invoc = ModelInvocation(
            workflow_execution_id=workflow_execution.id,
            provider_name=resp.provider,
            model_name=resp.model,
            input_tokens=resp.token_usage.prompt_tokens,
            output_tokens=resp.token_usage.completion_tokens,
            cached_input_tokens=cached_call_tokens,
            latency_ms=resp.latency_ms,
            model_call_outcome=ModelCallOutcome.SUCCESS.value,
        )
        self.session.add(invoc)
        await self.session.flush()

        # Record CostRecord
        cost_rec = await self.cost_service.record_cost(
            organization_id=self.organization_id,
            project_id=self.project_id,
            model_invocation=invoc,
            task_execution_id=task_execution_id,
            workflow_name=self.workflow_type.value,
            agent_name=agent_name,
            workflow_outcome=WorkflowOutcome.SUCCESS,
            task_outcome=TaskStatus.RUNNING,
        )
        self.total_cost_usd += cost_rec.cost_usd
        return resp.content
