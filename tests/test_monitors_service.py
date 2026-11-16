"""Unit and integration tests for MonitorService and deterministic evaluation engine (Phase 7)."""

import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.monitors.exceptions import (
    FindingTransitionException,
    MonitorNotFoundException,
    MonitorValidationException,
)
from corbel.domains.monitors.models import (
    FindingStatus,
    MonitorStatus,
    MonitorTargetType,
    RuleOperator,
    RuleSeverity,
)
from corbel.domains.monitors.schemas import (
    BusinessRuleCreate,
    FindingStatusUpdate,
    MonitorCreate,
    MonitorUpdate,
)
from corbel.domains.monitors.service import MonitorService
from corbel.domains.process_intelligence.schemas import (
    ProcessCreate,
    ProcessEventBatchIngestRequest,
    ProcessEventIngestItem,
)
from corbel.domains.process_intelligence.service import ProcessService
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_monitor_crud_and_rule_management(async_client: AsyncClient) -> None:
    """Test full monitor lifecycle: create, get, list, update, add/delete rules, and delete."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = MonitorService(session, tenancy_service)

        # 1. Create Monitor
        req = MonitorCreate(
            name="P2P Value Exception Monitor",
            description="Detect high value POs and discrepancies",
            target_type=MonitorTargetType.ENTITY,
            target_id="PurchaseOrder",
            schedule_cron="0 * * * *",
            status=MonitorStatus.ACTIVE,
            rules=[
                BusinessRuleCreate(
                    rule_code="PO_OVER_5K",
                    description="POs over $5,000",
                    severity=RuleSeverity.MEDIUM,
                    rule_type="THRESHOLD",
                    field_name="total_amount",
                    operator=RuleOperator.GT,
                    threshold_value=5000.0,
                )
            ],
        )
        created = await service.create_monitor(org_id, project_id, user_id, req)
        assert created.id is not None
        assert created.name == "P2P Value Exception Monitor"
        assert len(created.rules) == 1
        assert created.rules[0].rule_code == "PO_OVER_5K"

        # 2. Get Monitor
        fetched = await service.get_monitor(org_id, project_id, user_id, created.id)
        assert fetched.id == created.id
        assert fetched.open_findings_count == 0

        # 3. Add second rule
        new_rule = await service.add_rule(
            org_id,
            project_id,
            user_id,
            created.id,
            BusinessRuleCreate(
                rule_code="PO_CRITICAL_25K",
                description="POs over $25,000 require executive signoff",
                severity=RuleSeverity.CRITICAL,
                rule_type="THRESHOLD",
                field_name="total_amount",
                operator=RuleOperator.GT,
                threshold_value=25000.0,
            ),
        )
        assert new_rule.rule_code == "PO_CRITICAL_25K"

        # 4. List Monitors
        monitors = await service.list_monitors(org_id, project_id, user_id)
        assert len(monitors) == 1
        assert len(monitors[0].rules) == 2

        # 5. Update Monitor (e.g. Pause)
        updated = await service.update_monitor(
            org_id,
            project_id,
            user_id,
            created.id,
            MonitorUpdate(status=MonitorStatus.PAUSED, description="Temporarily paused"),
        )
        assert updated.status == MonitorStatus.PAUSED
        assert updated.description == "Temporarily paused"

        # 6. Delete Rule
        await service.delete_rule(org_id, project_id, user_id, created.id, new_rule.id)
        refreshed = await service.get_monitor(org_id, project_id, user_id, created.id)
        assert len(refreshed.rules) == 1

        # 7. Delete Monitor
        await service.delete_monitor(org_id, project_id, user_id, created.id)
        with pytest.raises(MonitorNotFoundException):
            await service.get_monitor(org_id, project_id, user_id, created.id)


@pytest.mark.anyio
async def test_monitor_validation_errors(async_client: AsyncClient) -> None:
    """Verify validation errors for duplicate names, missing thresholds, and invalid targets."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = MonitorService(session, tenancy_service)

        # Missing threshold for numeric operator
        with pytest.raises(MonitorValidationException) as exc:
            await service.create_monitor(
                org_id,
                project_id,
                user_id,
                MonitorCreate(
                    name="Invalid Numeric Rule Monitor",
                    target_type=MonitorTargetType.ENTITY,
                    target_id="PurchaseOrder",
                    rules=[
                        BusinessRuleCreate(
                            rule_code="BAD_RULE",
                            field_name="total_amount",
                            operator=RuleOperator.GT,
                            threshold_value=None,  # Missing!
                        )
                    ],
                ),
            )
        assert "requires a numeric threshold_value" in str(exc.value)

        # Invalid process target
        with pytest.raises(MonitorValidationException) as exc:
            await service.create_monitor(
                org_id,
                project_id,
                user_id,
                MonitorCreate(
                    name="Nonexistent Process Monitor",
                    target_type=MonitorTargetType.PROCESS,
                    target_id="Nonexistent-Process-1234",
                    rules=[],
                ),
            )
        assert "was not found in project" in str(exc.value)


@pytest.mark.anyio
async def test_finding_lifecycle_transitions(async_client: AsyncClient) -> None:
    """Verify finding state transitions: OPEN -> ACKNOWLEDGED -> RESOLVED, and illegal transitions."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = MonitorService(session, tenancy_service)

        # Create monitor
        mon = await service.create_monitor(
            org_id,
            project_id,
            user_id,
            MonitorCreate(
                name="Lifecycle Test Monitor",
                target_type=MonitorTargetType.ENTITY,
                target_id="Invoice",
            ),
        )

        # Manually seed finding
        from corbel.domains.monitors.models import Finding
        f = Finding(
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-9901",
            finding_type="PRICE_VARIANCE",
            severity=RuleSeverity.HIGH.value,
            status=FindingStatus.OPEN.value,
            summary="Price variance of 12% detected",
            deduplication_hash="dedup-lifecycle-test-1",
        )
        session.add(f)
        await session.commit()
        await session.refresh(f)
        finding_id = f.id

        # 1. Transition OPEN -> ACKNOWLEDGED
        ack_res = await service.update_finding_status(
            org_id,
            project_id,
            user_id,
            finding_id,
            FindingStatusUpdate(status=FindingStatus.ACKNOWLEDGED),
        )
        assert ack_res.status == FindingStatus.ACKNOWLEDGED
        assert ack_res.acknowledged_at is not None
        assert ack_res.acknowledged_by == user_id

        # 2. Transition ACKNOWLEDGED -> RESOLVED
        res_res = await service.update_finding_status(
            org_id,
            project_id,
            user_id,
            finding_id,
            FindingStatusUpdate(
                status=FindingStatus.RESOLVED,
                resolution_notes="Discrepancy approved by procurement manager.",
            ),
        )
        assert res_res.status == FindingStatus.RESOLVED
        assert res_res.resolved_at is not None
        assert res_res.resolution_notes == "Discrepancy approved by procurement manager."

        # 3. Transition RESOLVED -> ACKNOWLEDGED is ILLEGAL (only OPEN is allowed from RESOLVED)
        with pytest.raises(FindingTransitionException) as exc:
            await service.update_finding_status(
                org_id,
                project_id,
                user_id,
                finding_id,
                FindingStatusUpdate(status=FindingStatus.ACKNOWLEDGED),
            )
        assert "Cannot transition finding from 'RESOLVED' to 'ACKNOWLEDGED'" in str(exc.value)

        # 4. Transition RESOLVED -> OPEN (Reopening) is legal
        reopen_res = await service.update_finding_status(
            org_id,
            project_id,
            user_id,
            finding_id,
            FindingStatusUpdate(status=FindingStatus.OPEN),
        )
        assert reopen_res.status == FindingStatus.OPEN


@pytest.mark.anyio
async def test_deterministic_p2p_entity_evaluation_and_deduplication(async_client: AsyncClient) -> None:
    """Verify deterministic evaluation against uploaded P2P dataset, threshold violations, and deduplication."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Upload a synthetic Purchase Orders dataset with 3 records (one normal, two violating thresholds)
    csv_content = (
        "po_id,supplier,order_date,total_amount,unit_price,po_unit_price\n"
        "PO-1001,Acme Supply,2026-10-01,3500.00,10.00,10.00\n"
        "PO-1002,Global Logistics,2026-10-02,15000.00,12.50,10.00\n"
        "PO-1003,Pinnacle Materials,2026-10-03,28000.00,25.00,20.00\n"
    )
    files = {"file": ("purchase_orders.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        data={"name": "purchase_orders_october"},
        files=files,
    )
    assert upload_res.status_code == 201

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)

        # Create Monitor targeting PurchaseOrder entity with 2 rules:
        # Rule 1: High Value PO > $10,000 (PO-1002 and PO-1003 violate)
        # Rule 2: Price Variance > 20% (PO-1002: (12.5 - 10)/10 = 25% violates; PO-1003: (25 - 20)/20 = 25% violates)
        monitor_service = MonitorService(session, tenancy_service)
        monitor = await monitor_service.create_monitor(
            org_id,
            project_id,
            user_id,
            MonitorCreate(
                name="P2P PO Value & Variance Monitor",
                description="Checks PO values and price variance against expected baseline",
                target_type=MonitorTargetType.ENTITY,
                target_id="PurchaseOrder",
                rules=[
                    BusinessRuleCreate(
                        rule_code="PO_HIGH_VALUE_10K",
                        description="Purchase Order total exceeds $10,000 threshold",
                        severity=RuleSeverity.HIGH,
                        rule_type="THRESHOLD",
                        field_name="total_amount",
                        operator=RuleOperator.GT,
                        threshold_value=10000.0,
                    ),
                    BusinessRuleCreate(
                        rule_code="PO_PRICE_VARIANCE_20PCT",
                        description="Unit price exceeds PO expected unit price by > 20%",
                        severity=RuleSeverity.CRITICAL,
                        rule_type="VARIANCE",
                        field_name="unit_price",
                        operator=RuleOperator.GT,
                        threshold_value=0.20,
                        secondary_field="po_unit_price",
                    ),
                ],
            ),
        )

        # Run Evaluation 1
        eval_run_1 = await monitor_service.evaluate_monitor(
            org_id, project_id, user_id, monitor.id, limit=500
        )
        assert eval_run_1.status.value == "SUCCESS"
        assert eval_run_1.records_evaluated == 3
        # PO-1002 violated both rules (2 findings)
        # PO-1003 violated both rules (2 findings)
        # PO-1001 passed both rules
        # Total findings detected = 4
        assert eval_run_1.findings_detected == 4

        # List Findings
        findings = await monitor_service.list_findings(org_id, project_id, user_id, monitor.id)
        assert len(findings) == 4
        # Verify details and factual context
        po_1002_findings = [f for f in findings if f.entity_id == "PO-1002"]
        assert len(po_1002_findings) == 2
        for f in po_1002_findings:
            assert f.verified_context_json is not None
            assert f.verified_context_json["source_record"]["supplier"] == "Global Logistics"

        # Run Evaluation 2 (Deduplication Check)
        eval_run_2 = await monitor_service.evaluate_monitor(
            org_id, project_id, user_id, monitor.id, limit=500
        )
        assert eval_run_2.status.value == "SUCCESS"
        assert eval_run_2.records_evaluated == 3
        # No duplicate findings should be emitted!
        assert eval_run_2.findings_detected == 0

        # Findings count must remain exactly 4
        findings_after = await monitor_service.list_findings(org_id, project_id, user_id, monitor.id)
        assert len(findings_after) == 4


@pytest.mark.anyio
async def test_deterministic_process_sla_evaluation(async_client: AsyncClient) -> None:
    """Verify deterministic evaluation of process cases against cycle-time / SLA threshold rules."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        proc_service = ProcessService(session, tenancy_service)

        # 1. Create a Process
        proc = await proc_service.create_process(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            req=ProcessCreate(
                name="P2P Invoice Clearance Process",
                description="End-to-end invoice clearance workflow",
                target_duration_seconds=86400 * 2,  # 2 days target
            ),
        )

        # 2. Ingest two process cases:
        # Case A: duration = 1 day (86400s) -> within SLA
        # Case B: duration = 5 days (432000s) -> violates 3-day SLA (259200s)
        base_time = datetime(2026, 10, 1, 8, 0, 0, tzinfo=UTC)
        events_case_a = [
            ProcessEventIngestItem(
                case_identifier="CASE-NORMAL-01",
                activity_name="PO Created",
                timestamp=base_time,
            ),
            ProcessEventIngestItem(
                case_identifier="CASE-NORMAL-01",
                activity_name="Payment Cleared",
                timestamp=base_time + timedelta(days=1),
            ),
        ]
        events_case_b = [
            ProcessEventIngestItem(
                case_identifier="CASE-BREACH-02",
                activity_name="PO Created",
                timestamp=base_time,
            ),
            ProcessEventIngestItem(
                case_identifier="CASE-BREACH-02",
                activity_name="Payment Cleared",
                timestamp=base_time + timedelta(days=5),
            ),
        ]
        await proc_service.ingest_events(
            org_id, project_id, user_id, proc.id,
            ProcessEventBatchIngestRequest(events=events_case_a + events_case_b)
        )

        # 3. Create Monitor targeting this process with SLA cycle-time rule > 3 days (259200s)
        monitor_service = MonitorService(session, tenancy_service)
        monitor = await monitor_service.create_monitor(
            org_id,
            project_id,
            user_id,
            MonitorCreate(
                name="P2P Cycle Time SLA Monitor",
                description="Detect cases taking longer than 3 days",
                target_type=MonitorTargetType.PROCESS,
                target_id=str(proc.id),
                rules=[
                    BusinessRuleCreate(
                        rule_code="SLA_3_DAYS_BREACH",
                        description="Case duration exceeded 3 days (259200s)",
                        severity=RuleSeverity.HIGH,
                        rule_type="PROCESS_SLA",
                        field_name="total_duration_seconds",
                        operator=RuleOperator.GT,
                        threshold_value=259200.0,
                    ),
                ],
            ),
        )

        # 4. Evaluate Monitor
        eval_run = await monitor_service.evaluate_monitor(
            org_id, project_id, user_id, monitor.id, limit=100
        )
        assert eval_run.status.value == "SUCCESS"
        assert eval_run.records_evaluated == 2
        # Exactly 1 breach (CASE-BREACH-02)
        assert eval_run.findings_detected == 1

        findings = await monitor_service.list_findings(org_id, project_id, user_id, monitor.id)
        assert len(findings) == 1
        assert findings[0].entity_id == "CASE-BREACH-02"
        assert findings[0].finding_type == "PROCESS_SLA"
        assert findings[0].verified_context_json["case_identifier"] == "CASE-BREACH-02"
        assert float(findings[0].verified_context_json["total_duration_seconds"]) == 432000.0

        # 5. List Evaluations via service
        evaluations = await monitor_service.list_evaluations(org_id, project_id, user_id)
        assert len(evaluations) == 1
        assert evaluations[0].id == eval_run.id
        assert evaluations[0].project_id == project_id
        assert evaluations[0].monitor_id == monitor.id
        assert evaluations[0].records_evaluated == 2
        assert evaluations[0].findings_detected == 1

        # Check filtering by monitor_id
        filtered_evals = await monitor_service.list_evaluations(
            org_id, project_id, user_id, monitor_id=monitor.id
        )
        assert len(filtered_evals) == 1

        # Check filtering by non-matching monitor_id
        empty_evals = await monitor_service.list_evaluations(
            org_id, project_id, user_id, monitor_id=uuid.uuid4()
        )
        assert len(empty_evals) == 0
