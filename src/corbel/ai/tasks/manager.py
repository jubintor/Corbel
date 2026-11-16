"""PostgreSQL-backed durable background execution engine.

Implements safe concurrent task claiming via SELECT ... FOR UPDATE SKIP LOCKED,
time-bounded worker leases, periodic heartbeats, safe checkpoints, and cancellation boundaries.
Adheres strictly to ADR-014, ADR-017, and DOMAIN_MODEL.md Section 4.7.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.exceptions import TaskLeaseExpiredException, TaskNotFoundException
from corbel.ai.models import TaskExecution, TaskStatus, TaskType

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages durable asynchronous background jobs in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_task(
        self,
        project_id: uuid.UUID,
        task_type: TaskType | str,
        input_data: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> TaskExecution:
        """Create a new durable background task in PENDING state."""
        type_str = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        task = TaskExecution(
            project_id=project_id,
            task_type=type_str,
            status=TaskStatus.PENDING.value,
            max_retries=max_retries,
            checkpoint_data_json={"input": input_data} if input_data else None,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        logger.info("Created durable task %s of type %s for project %s", task.id, type_str, project_id)
        return task

    async def claim_next_task(
        self,
        worker_id: str,
        lease_duration_seconds: int = 300,
        task_types: list[str | TaskType] | None = None,
        project_id: uuid.UUID | None = None,
    ) -> TaskExecution | None:
        """Claim the next available task using SELECT ... FOR UPDATE SKIP LOCKED.

        Claims tasks that are:
        1. PENDING, OR
        2. RUNNING but with an expired worker lease (lease_expires_at < now) and retry_count < max_retries.
        """
        now = datetime.now(UTC)

        stmt = (
            select(TaskExecution)
            .where(
                or_(
                    TaskExecution.status == TaskStatus.PENDING.value,
                    (
                        (TaskExecution.status == TaskStatus.RUNNING.value)
                        & (TaskExecution.lease_expires_at < now)
                        & (TaskExecution.retry_count < TaskExecution.max_retries)
                    ),
                )
            )
            .with_for_update(skip_locked=True)
            .order_by(TaskExecution.created_at.asc())
            .limit(1)
        )

        if project_id is not None:
            stmt = stmt.where(TaskExecution.project_id == project_id)

        if task_types:
            type_vals = [t.value if isinstance(t, TaskType) else str(t) for t in task_types]
            stmt = stmt.where(TaskExecution.task_type.in_(type_vals))

        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            return None

        # Check if this is a lease recovery (retry)
        if task.status == TaskStatus.RUNNING.value and task.lease_expires_at and task.lease_expires_at < now:
            task.retry_count += 1
            logger.warning(
                "Worker lease expired for task %s (previous worker %s). Claiming as retry #%d by worker %s",
                task.id,
                task.worker_id,
                task.retry_count,
                worker_id,
            )

        task.status = TaskStatus.RUNNING.value
        task.worker_id = worker_id
        task.lease_generation = (task.lease_generation or 0) + 1
        task.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
        task.last_heartbeat_at = now
        if not task.started_at:
            task.started_at = now

        await self.session.commit()
        await self.session.refresh(task)
        logger.info(
            "Worker %s successfully claimed task %s (generation=%d, lease expires %s)",
            worker_id,
            task.id,
            task.lease_generation,
            task.lease_expires_at,
        )
        return task

    async def heartbeat(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        extend_seconds: int = 300,
        lease_generation: int | None = None,
    ) -> bool:
        """Extend the worker lease on a running task to signal active execution.

        Enforces strict worker ownership, active lease validity, and fencing token checks.
        Raises TaskLeaseExpiredException if the worker no longer holds the active lease.
        """
        task = await self._get_task_for_worker(task_id, worker_id, lease_generation=lease_generation)
        now = datetime.now(UTC)
        task.last_heartbeat_at = now
        task.lease_expires_at = now + timedelta(seconds=extend_seconds)
        await self.session.commit()
        return True

    async def save_checkpoint(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        checkpoint_data: dict[str, Any],
        lease_generation: int | None = None,
    ) -> None:
        """Persist intermediate state checkpoint to enable resume-on-failure.

        Atomically verifies worker ownership, active lease, and fencing token under row lock.
        """
        task = await self._get_task_for_worker(task_id, worker_id, lease_generation=lease_generation)
        current = dict(task.checkpoint_data_json or {})
        current.update(checkpoint_data)
        task.checkpoint_data_json = current
        await self.session.commit()
        logger.debug(
            "Checkpoint saved for task %s by worker %s (generation=%d)",
            task_id,
            worker_id,
            task.lease_generation,
        )

    async def request_cancellation(self, task_id: uuid.UUID) -> TaskExecution:
        """Mark a task for cancellation at its next safe checkpoint boundary."""
        stmt = select(TaskExecution).where(TaskExecution.id == task_id).with_for_update()
        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise TaskNotFoundException(str(task_id))

        task.cancellation_requested = True
        # If task is still PENDING, we can transition it to CANCELLED immediately
        if task.status == TaskStatus.PENDING.value:
            task.status = TaskStatus.CANCELLED.value
            task.ended_at = datetime.now(UTC)

        await self.session.commit()
        await self.session.refresh(task)
        logger.info("Cancellation requested for task %s (current status=%s)", task_id, task.status)
        return task

    async def is_cancellation_requested(self, task_id: uuid.UUID) -> bool:
        """Check whether a cancellation request has been submitted for a task."""
        stmt = select(TaskExecution.cancellation_requested).where(TaskExecution.id == task_id)
        result = await self.session.execute(stmt)
        flag = result.scalar_one_or_none()
        return bool(flag)

    async def complete_task(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        result_data: dict[str, Any] | None = None,
        lease_generation: int | None = None,
    ) -> TaskExecution:
        """Transition task to terminal COMPLETED state under strict lease ownership."""
        task = await self._get_task_for_worker(task_id, worker_id, lease_generation=lease_generation)
        task.status = TaskStatus.COMPLETED.value
        task.ended_at = datetime.now(UTC)
        task.lease_expires_at = None
        if result_data:
            current = dict(task.checkpoint_data_json or {})
            current["result"] = result_data
            task.checkpoint_data_json = current

        await self.session.commit()
        await self.session.refresh(task)
        logger.info(
            "Task %s completed by worker %s (generation=%d)",
            task_id,
            worker_id,
            task.lease_generation,
        )
        return task

    async def fail_task(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        error_message: str,
        is_retryable: bool = False,
        lease_generation: int | None = None,
    ) -> TaskExecution:
        """Handle task failure under strict lease ownership."""
        task = await self._get_task_for_worker(task_id, worker_id, lease_generation=lease_generation)
        now = datetime.now(UTC)

        if is_retryable and task.retry_count < task.max_retries:
            task.retry_count += 1
            task.status = TaskStatus.PENDING.value
            task.worker_id = None
            task.lease_expires_at = None
            task.error_diagnostics_json = {
                "last_error": error_message,
                "retry_count": task.retry_count,
                "retryable": True,
            }
            logger.warning("Requeuing task %s for retry #%d: %s", task_id, task.retry_count, error_message)
        else:
            task.status = TaskStatus.FAILED.value
            task.ended_at = now
            task.lease_expires_at = None
            task.error_diagnostics_json = {
                "error": error_message,
                "retryable": is_retryable,
                "final_retry_count": task.retry_count,
            }
            logger.error("Task %s permanently failed: %s", task_id, error_message)

        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def cancel_task(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        reason: str | None = None,
        lease_generation: int | None = None,
    ) -> TaskExecution:
        """Transition task cleanly to terminal CANCELLED state under strict lease ownership."""
        task = await self._get_task_for_worker(task_id, worker_id, lease_generation=lease_generation)
        task.status = TaskStatus.CANCELLED.value
        task.ended_at = datetime.now(UTC)
        task.lease_expires_at = None
        if reason:
            diag = dict(task.error_diagnostics_json or {})
            diag["cancellation_reason"] = reason
            task.error_diagnostics_json = diag

        await self.session.commit()
        await self.session.refresh(task)
        logger.info(
            "Task %s cancelled cleanly by worker %s (generation=%d)",
            task_id,
            worker_id,
            task.lease_generation,
        )
        return task

    async def get_task(self, task_id: uuid.UUID) -> TaskExecution:
        """Retrieve task by ID or raise TaskNotFoundException."""
        stmt = select(TaskExecution).where(TaskExecution.id == task_id)
        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise TaskNotFoundException(str(task_id))
        return task

    async def _get_task_for_worker(
        self,
        task_id: uuid.UUID,
        worker_id: str,
        lease_generation: int | None = None,
    ) -> TaskExecution:
        """Helper to lock and strictly verify worker ownership and lease validity for a task.

        Acquires a row-level lock (SELECT ... FOR UPDATE) and validates:
        1. Task exists.
        2. Task is in RUNNING status.
        3. Task worker_id matches requesting worker_id.
        4. If lease_generation is provided, matches task.lease_generation (fencing token).
        5. Worker lease has not expired (lease_expires_at >= now).

        Raises:
            TaskNotFoundException: If task does not exist.
            TaskLeaseExpiredException: If worker is not the active owner or lease has expired.
        """
        now = datetime.now(UTC)
        stmt = select(TaskExecution).where(TaskExecution.id == task_id).with_for_update()
        result = await self.session.execute(stmt)
        task = result.scalar_one_or_none()
        if not task:
            raise TaskNotFoundException(str(task_id))

        if task.status != TaskStatus.RUNNING.value:
            raise TaskLeaseExpiredException(
                task_id=str(task_id),
                worker_id=worker_id,
                reason=f"Task is in status '{task.status}', not 'RUNNING'.",
                details={"current_status": task.status},
            )

        if task.worker_id != worker_id:
            logger.warning(
                "Worker lease conflict on task %s: current worker=%s, requested by=%s",
                task_id,
                task.worker_id,
                worker_id,
            )
            raise TaskLeaseExpiredException(
                task_id=str(task_id),
                worker_id=worker_id,
                reason=f"Task is currently owned by worker '{task.worker_id}', not '{worker_id}'.",
                details={"current_worker_id": task.worker_id},
            )

        if lease_generation is not None and task.lease_generation != lease_generation:
            logger.warning(
                "Stale lease generation on task %s: current generation=%d, requested=%d",
                task_id,
                task.lease_generation,
                lease_generation,
            )
            raise TaskLeaseExpiredException(
                task_id=str(task_id),
                worker_id=worker_id,
                reason=f"Stale lease generation {lease_generation}; current generation is {task.lease_generation}.",
                details={"expected_generation": lease_generation, "current_generation": task.lease_generation},
            )

        if task.lease_expires_at is not None and task.lease_expires_at < now:
            logger.warning(
                "Worker lease expired on task %s for worker %s: expired at %s, current %s",
                task_id,
                worker_id,
                task.lease_expires_at,
                now,
            )
            raise TaskLeaseExpiredException(
                task_id=str(task_id),
                worker_id=worker_id,
                reason=f"Worker lease expired at {task.lease_expires_at.isoformat()} (current time: {now.isoformat()}).",
                details={"lease_expires_at": task.lease_expires_at.isoformat()},
            )

        return task
