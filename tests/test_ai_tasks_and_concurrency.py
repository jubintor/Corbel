"""Tests for PostgreSQL-backed durable background tasks, concurrency, leases, and cancellation."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from corbel.ai.exceptions import TaskLeaseExpiredException
from corbel.ai.models import TaskStatus, TaskType
from corbel.ai.tasks.manager import TaskManager
from corbel.core.database import get_session_factory
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_durable_task_lifecycle_and_checkpointing(async_client: AsyncClient) -> None:
    """Test full task execution lifecycle: create -> claim -> checkpoint -> complete."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        manager = TaskManager(session)

        # 1. Create task
        task = await manager.create_task(
            project_id=project_id,
            task_type=TaskType.DATASET_IMPORT,
            input_data={"filename": "orders.csv", "rows": 1000},
        )
        assert task.status == TaskStatus.PENDING.value
        assert task.retry_count == 0
        assert task.checkpoint_data_json == {"input": {"filename": "orders.csv", "rows": 1000}}

        # 2. Claim task
        worker_id = "worker-alpha-01"
        claimed = await manager.claim_next_task(
            worker_id=worker_id,
            lease_duration_seconds=120,
            project_id=project_id,
        )
        assert claimed is not None
        assert claimed.id == task.id
        assert claimed.status == TaskStatus.RUNNING.value
        assert claimed.worker_id == worker_id
        assert claimed.lease_expires_at is not None

        # 3. Heartbeat extension
        heartbeat_ok = await manager.heartbeat(task.id, worker_id=worker_id, extend_seconds=300)
        assert heartbeat_ok is True

        # 4. Save checkpoint
        await manager.save_checkpoint(
            task.id,
            worker_id=worker_id,
            checkpoint_data={"processed_rows": 500, "stage": "VALIDATING"},
        )
        updated = await manager.get_task(task.id)
        assert updated.checkpoint_data_json["processed_rows"] == 500
        assert updated.checkpoint_data_json["stage"] == "VALIDATING"

        # 5. Complete task
        completed = await manager.complete_task(
            task.id, worker_id=worker_id, result_data={"status": "IMPORT_SUCCESS"}
        )
        assert completed.status == TaskStatus.COMPLETED.value
        assert completed.ended_at is not None
        assert completed.checkpoint_data_json["result"] == {"status": "IMPORT_SUCCESS"}


@pytest.mark.anyio
async def test_concurrent_task_claiming_skip_locked(async_client: AsyncClient) -> None:
    """Test safe concurrent claiming with SELECT ... FOR UPDATE SKIP LOCKED.

    When two workers claim concurrently, each worker must receive a distinct task,
    and no task may ever be double-claimed.
    """
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    # Create 2 tasks
    async with session_factory() as session:
        manager = TaskManager(session)
        t1 = await manager.create_task(project_id, TaskType.WORKFLOW_RUN)
        t2 = await manager.create_task(project_id, TaskType.WORKFLOW_RUN)

    # Claim concurrently using two separate database sessions
    async def _claim_worker(worker_id: str) -> uuid.UUID | None:
        async with session_factory() as s:
            mgr = TaskManager(s)
            claimed = await mgr.claim_next_task(worker_id=worker_id, project_id=project_id)
            return claimed.id if claimed else None

    results = await asyncio.gather(
        _claim_worker("worker-1"),
        _claim_worker("worker-2"),
    )

    claimed_ids = [r for r in results if r is not None]
    assert len(claimed_ids) == 2
    # Verify both distinct tasks were claimed without collisions
    assert set(claimed_ids) == {t1.id, t2.id}


@pytest.mark.anyio
async def test_lease_expiration_and_recovery(async_client: AsyncClient) -> None:
    """Test that a task with an expired worker lease is safely reclaimed as a retry."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        manager = TaskManager(session)
        task = await manager.create_task(project_id, TaskType.SCHEMA_PROFILING, max_retries=3)

        # Worker 1 claims task but lease expires in the past
        claimed = await manager.claim_next_task(
            worker_id="crashed-worker",
            lease_duration_seconds=1,
            project_id=project_id,
        )
        assert claimed is not None

        # Artificially expire the lease in database
        claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
        await session.commit()

        # Worker 2 claims next task -> should recover task and increment retry_count
        recovered = await manager.claim_next_task(
            worker_id="recovery-worker",
            lease_duration_seconds=300,
            project_id=project_id,
        )
        assert recovered is not None
        assert recovered.id == task.id
        assert recovered.worker_id == "recovery-worker"
        assert recovered.retry_count == 1
        assert recovered.status == TaskStatus.RUNNING.value


@pytest.mark.anyio
async def test_cancellation_and_graceful_shutdown(async_client: AsyncClient) -> None:
    """Test task cancellation request and clean boundary termination."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        manager = TaskManager(session)
        task = await manager.create_task(project_id, TaskType.MONITOR_SWEEP)

        # Request cancellation while PENDING -> immediately transitions to CANCELLED
        cancelled_pending = await manager.request_cancellation(task.id)
        assert cancelled_pending.status == TaskStatus.CANCELLED.value
        assert cancelled_pending.cancellation_requested is True

        # Create another task, claim it as RUNNING, then request cancellation
        task2 = await manager.create_task(project_id, TaskType.WORKFLOW_RUN)
        claimed2 = await manager.claim_next_task(worker_id="worker-beta", project_id=project_id)
        assert claimed2 is not None

        await manager.request_cancellation(task2.id)
        # Check boundary flag
        is_cancelled = await manager.is_cancellation_requested(task2.id)
        assert is_cancelled is True

        # Worker detects cancellation at safe boundary and cleans up
        clean_cancelled = await manager.cancel_task(
            task2.id, worker_id="worker-beta", reason="Operator stopped workflow"
        )
        assert clean_cancelled.status == TaskStatus.CANCELLED.value
        assert clean_cancelled.lease_expires_at is None
        assert clean_cancelled.error_diagnostics_json["cancellation_reason"] == "Operator stopped workflow"


@pytest.mark.anyio
async def test_stale_worker_ownership_rejection_and_fencing(async_client: AsyncClient) -> None:
    """Test that a stale or expired worker cannot mutate, complete, fail, or heartbeat a task."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        manager = TaskManager(session)

        # 1. Create task (generation 0)
        task = await manager.create_task(project_id, TaskType.DATASET_IMPORT)
        assert task.lease_generation == 0

        # 2. Worker A claims task (generation 1)
        worker_a = "worker-alpha"
        claimed_a = await manager.claim_next_task(
            worker_id=worker_a,
            lease_duration_seconds=10,
            project_id=project_id,
        )
        assert claimed_a is not None
        assert claimed_a.worker_id == worker_a
        assert claimed_a.lease_generation == 1

        # Worker A can save checkpoint while lease is active
        await manager.save_checkpoint(
            task.id,
            worker_id=worker_a,
            checkpoint_data={"progress": 25},
            lease_generation=1,
        )
        updated_a = await manager.get_task(task.id)
        assert updated_a.checkpoint_data_json["progress"] == 25

        # 3. Simulate Worker A lease expiration
        claimed_a.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
        await session.commit()

        # 4. Worker B reclaims task (generation 2)
        worker_b = "worker-beta"
        claimed_b = await manager.claim_next_task(
            worker_id=worker_b,
            lease_duration_seconds=300,
            project_id=project_id,
        )
        assert claimed_b is not None
        assert claimed_b.id == task.id
        assert claimed_b.worker_id == worker_b
        assert claimed_b.lease_generation == 2
        assert claimed_b.retry_count == 1

        # 5. Stale Worker A attempts mutations - every stale attempt must raise TaskLeaseExpiredException
        with pytest.raises(TaskLeaseExpiredException) as exc_cp:
            await manager.save_checkpoint(
                task.id,
                worker_id=worker_a,
                checkpoint_data={"progress": 99},
                lease_generation=1,
            )
        assert exc_cp.value.status_code == 409

        with pytest.raises(TaskLeaseExpiredException) as exc_comp:
            await manager.complete_task(
                task.id,
                worker_id=worker_a,
                result_data={"fake": True},
                lease_generation=1,
            )
        assert exc_comp.value.status_code == 409

        with pytest.raises(TaskLeaseExpiredException) as exc_fail:
            await manager.fail_task(
                task.id,
                worker_id=worker_a,
                error_message="stale error",
                lease_generation=1,
            )
        assert exc_fail.value.status_code == 409

        with pytest.raises(TaskLeaseExpiredException) as exc_hb:
            await manager.heartbeat(task.id, worker_id=worker_a, lease_generation=1)
        assert exc_hb.value.status_code == 409

        with pytest.raises(TaskLeaseExpiredException) as exc_can:
            await manager.cancel_task(task.id, worker_id=worker_a, lease_generation=1)
        assert exc_can.value.status_code == 409

        # Also verify without lease_generation parameter: worker_id mismatch alone is rejected
        with pytest.raises(TaskLeaseExpiredException):
            await manager.save_checkpoint(task.id, worker_id=worker_a, checkpoint_data={"progress": 99})

        # Also verify fencing token mismatch if worker_id was somehow identical but generation is stale
        with pytest.raises(TaskLeaseExpiredException):
            await manager.save_checkpoint(
                task.id,
                worker_id=worker_b,
                checkpoint_data={"progress": 99},
                lease_generation=1,  # Old generation
            )

        # 6. Legitimate Worker B can checkpoint and complete successfully
        await manager.save_checkpoint(
            task.id,
            worker_id=worker_b,
            checkpoint_data={"progress": 100},
            lease_generation=2,
        )
        completed = await manager.complete_task(
            task.id,
            worker_id=worker_b,
            result_data={"success": True},
            lease_generation=2,
        )
        assert completed.status == TaskStatus.COMPLETED.value
        assert completed.worker_id == worker_b
        assert completed.checkpoint_data_json["progress"] == 100
        assert completed.checkpoint_data_json["result"] == {"success": True}


@pytest.mark.anyio
async def test_stale_worker_racing_requests_cannot_overwrite(async_client: AsyncClient) -> None:
    """Test that concurrent racing requests between stale worker and valid worker are safely serialized."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    # 1. Setup task reclaimed by Worker B
    async with session_factory() as session:
        manager = TaskManager(session)
        task = await manager.create_task(project_id, TaskType.SCHEMA_PROFILING)
        claimed_a = await manager.claim_next_task(worker_id="worker-a", lease_duration_seconds=1, project_id=project_id)
        assert claimed_a is not None
        claimed_a.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
        await session.commit()

        claimed_b = await manager.claim_next_task(worker_id="worker-b", lease_duration_seconds=120, project_id=project_id)
        assert claimed_b is not None
        assert claimed_b.lease_generation == 2
        task_id = task.id

    # 2. Race: Worker A (stale) and Worker B (active) concurrently attempt completion
    async def _worker_a_comp() -> str:
        async with session_factory() as s_a:
            mgr_a = TaskManager(s_a)
            try:
                await mgr_a.complete_task(task_id, worker_id="worker-a", result_data={"winner": "a"}, lease_generation=1)
                return "A_SUCCESS"
            except TaskLeaseExpiredException:
                return "A_REJECTED"

    async def _worker_b_comp() -> str:
        async with session_factory() as s_b:
            mgr_b = TaskManager(s_b)
            try:
                await mgr_b.complete_task(task_id, worker_id="worker-b", result_data={"winner": "b"}, lease_generation=2)
                return "B_SUCCESS"
            except TaskLeaseExpiredException:
                return "B_REJECTED"

    results = await asyncio.gather(_worker_a_comp(), _worker_b_comp())
    assert "A_REJECTED" in results
    assert "B_SUCCESS" in results

    # 3. Verify final state in database belongs exclusively to Worker B
    async with session_factory() as s_check:
        mgr_check = TaskManager(s_check)
        final_task = await mgr_check.get_task(task_id)
        assert final_task.status == TaskStatus.COMPLETED.value
        assert final_task.worker_id == "worker-b"
        assert final_task.checkpoint_data_json["result"] == {"winner": "b"}
