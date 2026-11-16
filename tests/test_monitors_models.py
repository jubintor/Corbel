"""Unit tests for Phase 7 Operational Monitoring ORM models and constraints."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from corbel.core.database import get_session_factory
from corbel.domains.monitors.models import (
    BusinessRule,
    EvaluationStatus,
    Finding,
    FindingStatus,
    Monitor,
    MonitorEvaluation,
    MonitorStatus,
    MonitorTargetType,
    RuleOperator,
    RuleSeverity,
)
from corbel.domains.tenancy.models import Organization, Project


@pytest.mark.anyio
async def test_monitor_models_and_composite_foreign_keys() -> None:
    """Verify monitor, business rule, finding, and evaluation model creation and foreign key constraints."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Create test org, user, project
        org = Organization(name="Monitor Test Org", slug=f"mon-org-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()

        project = Project(
            organization_id=org.id,
            name="P2P Monitoring Project",
            slug=f"p2p-mon-{uuid.uuid4().hex[:8]}",
        )
        session.add(project)
        await session.flush()

        # 1. Create Monitor
        monitor = Monitor(
            project_id=project.id,
            name="P2P Value & SLA Monitor",
            description="Operational monitoring for high value POs and cycle times",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="PurchaseOrder",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()
        assert monitor.id is not None
        assert monitor.created_at is not None

        # 2. Add Business Rules
        rule1 = BusinessRule(
            monitor_id=monitor.id,
            rule_code="PO_HIGH_VALUE",
            description="Flag POs exceeding $10,000",
            severity=RuleSeverity.HIGH.value,
            rule_type="THRESHOLD",
            field_name="total_amount",
            operator=RuleOperator.GT.value,
            threshold_value=10000.0,
        )
        rule2 = BusinessRule(
            monitor_id=monitor.id,
            rule_code="PO_PRICE_VARIANCE",
            description="Flag unit price variance > 5%",
            severity=RuleSeverity.CRITICAL.value,
            rule_type="VARIANCE",
            field_name="unit_price",
            operator=RuleOperator.GT.value,
            threshold_value=0.05,
            secondary_field="po_unit_price",
        )
        session.add_all([rule1, rule2])
        await session.flush()

        # 3. Create Finding with same-project composite FK
        finding = Finding(
            project_id=project.id,
            monitor_id=monitor.id,
            rule_id=rule1.id,
            entity_type="PurchaseOrder",
            entity_id="PO-9901",
            finding_type="THRESHOLD",
            severity=RuleSeverity.HIGH.value,
            status=FindingStatus.OPEN.value,
            summary="PO 'PO-9901' exceeds threshold ($12,500 > $10,000)",
            deduplication_hash="dedup-test-hash-1",
            observed_value="12500.00",
            threshold_value="10000.00",
            verified_context_json={"source": "test_record", "amount": 12500.0},
        )
        session.add(finding)
        await session.flush()
        assert finding.id is not None
        assert finding.status == FindingStatus.OPEN.value

        # 4. Create Evaluation Record
        eval_run = MonitorEvaluation(
            project_id=project.id,
            monitor_id=monitor.id,
            status=EvaluationStatus.SUCCESS.value,
            records_evaluated=150,
            findings_detected=1,
            execution_duration_ms=42.5,
            summary_json={"rules_checked": 2},
        )
        session.add(eval_run)
        await session.commit()

        # 5. Query back and verify relationships
        m_stmt = (
            select(Monitor)
            .where(Monitor.id == monitor.id)
        )
        fetched = (await session.execute(m_stmt)).scalar_one()
        assert fetched.name == "P2P Value & SLA Monitor"
        assert len(fetched.rules) == 2
        assert len(fetched.findings) == 1
        assert len(fetched.evaluations) == 1


@pytest.mark.anyio
async def test_duplicate_deduplication_hash_constraint() -> None:
    """Verify that findings enforce project-level deduplication uniqueness."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        org = Organization(name="Dedup Org", slug=f"dedup-{uuid.uuid4().hex[:8]}")
        session.add(org)
        await session.flush()

        project = Project(
            organization_id=org.id,
            name="Dedup Project",
            slug=f"proj-{uuid.uuid4().hex[:8]}",
        )
        session.add(project)
        await session.flush()

        monitor = Monitor(
            project_id=project.id,
            name="Dedup Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
        )
        session.add(monitor)
        await session.flush()

        f1 = Finding(
            project_id=project.id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-001",
            finding_type="TEST",
            severity=RuleSeverity.MEDIUM.value,
            summary="Invoice test finding 1",
            deduplication_hash="unique-hash-12345",
        )
        session.add(f1)
        await session.commit()

        # Second finding with same project_id and deduplication_hash must fail
        f2 = Finding(
            project_id=project.id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-001",
            finding_type="TEST",
            severity=RuleSeverity.MEDIUM.value,
            summary="Duplicate invoice test finding",
            deduplication_hash="unique-hash-12345",
        )
        session.add(f2)
        with pytest.raises(IntegrityError):
            await session.commit()
