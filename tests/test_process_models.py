"""Unit tests for Process Intelligence domain models and constraints (Phase 6)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from corbel.core.database import get_session_factory
from corbel.domains.process_intelligence.models import (
    Process,
    ProcessCase,
    ProcessCaseStatus,
    ProcessEvent,
    ProcessEventType,
)
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_process_model_crud_and_cascade(async_client: AsyncClient) -> None:
    """Test Process model creation, case linking, event linking, and cascade deletion."""
    _, _, _, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        # 1. Create Process
        proc = Process(
            id=uuid.uuid4(),
            project_id=project_id,
            name="P2P Core Process",
            description="Procure-to-Pay Lifecycle",
            target_duration_seconds=86400.0 * 5,  # 5 days
        )
        session.add(proc)
        await session.commit()

        # 2. Create Process Case
        now = datetime.now(UTC)
        case = ProcessCase(
            id=uuid.uuid4(),
            process_id=proc.id,
            project_id=project_id,
            case_identifier="PO-1001",
            variant_key="PO Created -> Goods Received -> Invoice Received",
            status=ProcessCaseStatus.COMPLETED.value,
            started_at=now,
            ended_at=now + timedelta(days=3),
            total_duration_seconds=86400.0 * 3,
            event_count=3,
        )
        session.add(case)
        await session.commit()

        # 3. Create Process Event
        ev = ProcessEvent(
            id=uuid.uuid4(),
            process_case_id=case.id,
            project_id=project_id,
            activity_name="PO Created",
            timestamp=now,
            event_type=ProcessEventType.COMPLETE.value,
            resource="SUP-001",
            attributes_json={"total_amount": 15000.0},
        )
        session.add(ev)
        await session.commit()

        # 4. Verify associations
        res = (await session.execute(select(Process).where(Process.id == proc.id))).scalar_one()
        assert res.name == "P2P Core Process"

        cases = (await session.execute(select(ProcessCase).where(ProcessCase.process_id == proc.id))).scalars().all()
        assert len(cases) == 1
        assert cases[0].case_identifier == "PO-1001"

        events = (await session.execute(select(ProcessEvent).where(ProcessEvent.process_case_id == case.id))).scalars().all()
        assert len(events) == 1
        assert events[0].activity_name == "PO Created"

        # 5. Cascade Delete
        await session.delete(proc)
        await session.commit()

        # Verify cases and events are cascaded
        c_after = (await session.execute(select(ProcessCase).where(ProcessCase.process_id == proc.id))).scalars().all()
        assert len(c_after) == 0

        e_after = (await session.execute(select(ProcessEvent).where(ProcessEvent.id == ev.id))).scalars().all()
        assert len(e_after) == 0


@pytest.mark.anyio
async def test_process_name_unique_per_project(async_client: AsyncClient) -> None:
    """Verify process name must be unique within the same project."""
    _, _, _, project = await setup_test_org_and_project(async_client)
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        proc1 = Process(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Unique Process Name",
        )
        session.add(proc1)
        await session.commit()

        proc2 = Process(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Unique Process Name",
        )
        session.add(proc2)
        with pytest.raises(IntegrityError):
            await session.commit()
