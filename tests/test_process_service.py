"""Unit and integration tests for ProcessService (Phase 6)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.process_intelligence.exceptions import (
    ProcessNotFoundException,
    ProcessValidationException,
)
from corbel.domains.process_intelligence.schemas import (
    ProcessCreate,
    ProcessEventBatchIngestRequest,
    ProcessEventIngestItem,
    ProcessUpdate,
)
from corbel.domains.process_intelligence.service import ProcessService, parse_timestamp
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_parse_timestamp_formats() -> None:
    """Verify parse_timestamp handles ISO, strings, and standard formats correctly."""
    now = datetime(2026, 10, 15, 14, 30, 0, tzinfo=UTC)
    assert parse_timestamp(now) == now

    # ISO string
    ts_iso = parse_timestamp("2026-10-15T14:30:00Z")
    assert ts_iso.year == 2026 and ts_iso.month == 10 and ts_iso.day == 15

    # YYYY-MM-DD
    ts_date = parse_timestamp("2026-10-15")
    assert ts_date.year == 2026 and ts_date.month == 10 and ts_date.day == 15

    # YYYY-MM-DD HH:MM:SS
    ts_datetime = parse_timestamp("2026-10-15 14:30:00")
    assert ts_datetime.hour == 14

    # Invalid timestamp raises ProcessValidationException
    with pytest.raises(ProcessValidationException):
        parse_timestamp("not-a-timestamp-123")


@pytest.mark.anyio
async def test_process_crud_service(async_client: AsyncClient) -> None:
    """Test Process definition lifecycle (create, get, list, update, delete)."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = ProcessService(session, tenancy_service)

        # 1. Create
        create_req = ProcessCreate(
            name="Procure-to-Pay Core",
            description="End-to-end procurement flow",
            target_duration_seconds=86400.0 * 7,
        )
        proc = await service.create_process(org_id, project_id, user_id, create_req)
        assert proc.name == "Procure-to-Pay Core"
        assert proc.target_duration_seconds == 86400.0 * 7

        # 2. Duplicate name error
        with pytest.raises(ProcessValidationException):
            await service.create_process(org_id, project_id, user_id, create_req)

        # 3. Get
        fetched = await service.get_process(org_id, project_id, user_id, proc.id)
        assert fetched.id == proc.id
        assert fetched.name == "Procure-to-Pay Core"

        # 4. List
        procs = await service.list_processes(org_id, project_id, user_id)
        assert len(procs) == 1
        assert procs[0].id == proc.id

        # 5. Update
        updated = await service.update_process(
            org_id,
            project_id,
            user_id,
            proc.id,
            ProcessUpdate(name="P2P Extended", target_duration_seconds=86400.0 * 10),
        )
        assert updated.name == "P2P Extended"
        assert updated.target_duration_seconds == 86400.0 * 10

        # 6. Delete
        await service.delete_process(org_id, project_id, user_id, proc.id)
        with pytest.raises(ProcessNotFoundException):
            await service.get_process(org_id, project_id, user_id, proc.id)


@pytest.mark.anyio
async def test_event_ingestion_and_dfg_calculations(async_client: AsyncClient) -> None:
    """Test event ingestion, chronological assembly, DFG construction, variant ranking, and bottleneck detection."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = ProcessService(session, tenancy_service)

        proc = await service.create_process(
            org_id,
            project_id,
            user_id,
            ProcessCreate(name="P2P Process Mining", target_duration_seconds=86400.0 * 5),
        )

        t0 = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
        # Case 1: Standard Happy Path (PO Created -> Goods Received -> Invoice Received -> Payment Cleared)
        # Duration: PO -> GR (2 days), GR -> Inv (1 day), Inv -> Pay (3 days) = 6 days total (> 5 days SLA)
        c1_events = [
            ProcessEventIngestItem(case_identifier="PO-001", activity_name="PO Created", timestamp=t0),
            ProcessEventIngestItem(case_identifier="PO-001", activity_name="Goods Received", timestamp=t0 + timedelta(days=2)),
            ProcessEventIngestItem(case_identifier="PO-001", activity_name="Invoice Received", timestamp=t0 + timedelta(days=3)),
            ProcessEventIngestItem(case_identifier="PO-001", activity_name="Payment Cleared", timestamp=t0 + timedelta(days=6)),
        ]

        # Case 2: Identical Happy Path, Faster (total 3 days <= 5 days SLA)
        c2_events = [
            ProcessEventIngestItem(case_identifier="PO-002", activity_name="PO Created", timestamp=t0),
            ProcessEventIngestItem(case_identifier="PO-002", activity_name="Goods Received", timestamp=t0 + timedelta(days=1)),
            ProcessEventIngestItem(case_identifier="PO-002", activity_name="Invoice Received", timestamp=t0 + timedelta(days=2)),
            ProcessEventIngestItem(case_identifier="PO-002", activity_name="Payment Cleared", timestamp=t0 + timedelta(days=3)),
        ]

        # Case 3: Variant 2 - Invoicing before Goods Receipt (PO Created -> Invoice Received -> Goods Received)
        c3_events = [
            ProcessEventIngestItem(case_identifier="PO-003", activity_name="PO Created", timestamp=t0),
            ProcessEventIngestItem(case_identifier="PO-003", activity_name="Invoice Received", timestamp=t0 + timedelta(days=1)),
            ProcessEventIngestItem(case_identifier="PO-003", activity_name="Goods Received", timestamp=t0 + timedelta(days=4)),
        ]

        # Case 4: Variant 3 - Rework (Multiple Goods Receipts)
        c4_events = [
            ProcessEventIngestItem(case_identifier="PO-004", activity_name="PO Created", timestamp=t0),
            ProcessEventIngestItem(case_identifier="PO-004", activity_name="Goods Received", timestamp=t0 + timedelta(days=1)),
            ProcessEventIngestItem(case_identifier="PO-004", activity_name="Goods Received", timestamp=t0 + timedelta(days=2)),  # Rework!
            ProcessEventIngestItem(case_identifier="PO-004", activity_name="Invoice Received", timestamp=t0 + timedelta(days=3)),
        ]

        # Ingest all events
        all_events = c1_events + c2_events + c3_events + c4_events
        ingest_res = await service.ingest_events(
            org_id,
            project_id,
            user_id,
            proc.id,
            ProcessEventBatchIngestRequest(events=all_events),
        )
        assert ingest_res.cases_reconstructed == 4
        assert ingest_res.events_reconstructed == 15
        assert ingest_res.variants_count == 3

        # 1. Test Process Overview
        overview = await service.get_process_overview(org_id, project_id, user_id, proc.id)
        assert overview.total_cases == 4
        assert overview.total_events == 15
        assert overview.distinct_activities_count == 4
        assert overview.distinct_variants_count == 3
        assert overview.sla_breach_count == 1  # PO-001 took 6 days > 5 days target
        assert overview.sla_compliance_rate == 75.0  # 3 of 4 compliant
        assert overview.rework_case_count == 1  # PO-004 had repeated Goods Received
        assert overview.rework_rate == 25.0
        assert overview.primary_bottleneck is not None

        # 2. Test Variants Discovery
        variants_res = await service.get_process_variants(org_id, project_id, user_id, proc.id)
        assert variants_res.total_variants == 3

        # Happy path must be Variant 1 (PO Created -> Goods Received -> Invoice Received -> Payment Cleared) with 2 cases (50%)
        happy_var = variants_res.variants[0]
        assert happy_var.is_happy_path is True
        assert happy_var.case_count == 2
        assert happy_var.frequency_percentage == 50.0
        assert happy_var.activities == ["PO Created", "Goods Received", "Invoice Received", "Payment Cleared"]

        # 3. Test Directly-Follows Graph (DFG)
        dfg = await service.get_directly_follows_graph(org_id, project_id, user_id, proc.id)
        node_names = {n.name for n in dfg.nodes}
        assert node_names == {"PO Created", "Goods Received", "Invoice Received", "Payment Cleared"}

        # Edge checks
        edges_map = {(e.source, e.target): e for e in dfg.edges}
        assert ("PO Created", "Goods Received") in edges_map
        assert ("PO Created", "Invoice Received") in edges_map
        assert ("Goods Received", "Goods Received") in edges_map  # Rework loop!
        assert edges_map[("Goods Received", "Goods Received")].is_rework is True

        # Bottleneck edge exists
        assert dfg.bottleneck_edge is not None
        assert dfg.bottleneck_edge.is_bottleneck is True

        # 4. Test Case Listing & Detail
        cases_list = await service.list_cases(org_id, project_id, user_id, proc.id, limit=10)
        assert cases_list.total == 4
        assert len(cases_list.items) == 4

        # Filter by variant
        filtered_cases = await service.list_cases(
            org_id,
            project_id,
            user_id,
            proc.id,
            variant_key=happy_var.variant_key,
        )
        assert filtered_cases.total == 2

        # Case detail
        c1_summary = next(c for c in cases_list.items if c.case_identifier == "PO-001")
        detail = await service.get_case_detail(org_id, project_id, user_id, proc.id, c1_summary.id)
        assert detail.case.case_identifier == "PO-001"
        assert len(detail.events) == 4
        assert detail.events[0].activity_name == "PO Created"
        assert detail.events[-1].activity_name == "Payment Cleared"


@pytest.mark.anyio
async def test_empty_process_analytics(async_client: AsyncClient) -> None:
    """Verify empty process handles statistics without division by zero errors."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = ProcessService(session, tenancy_service)

        proc = await service.create_process(
            org_id,
            project_id,
            user_id,
            ProcessCreate(name="Empty Process"),
        )

        overview = await service.get_process_overview(org_id, project_id, user_id, proc.id)
        assert overview.total_cases == 0
        assert overview.total_events == 0
        assert overview.avg_cycle_time_seconds == 0.0
        assert overview.sla_compliance_rate == 100.0

        variants = await service.get_process_variants(org_id, project_id, user_id, proc.id)
        assert variants.total_variants == 0

        dfg = await service.get_directly_follows_graph(org_id, project_id, user_id, proc.id)
        assert len(dfg.nodes) == 0
        assert len(dfg.edges) == 0
        assert dfg.bottleneck_edge is None
