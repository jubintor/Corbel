"""Integration and unit tests for Phase 10: Native PostgreSQL Audit Store.

Covers:
1. Database-level append-only immutability triggers (ADR-020).
2. Cross-domain administrative and operational audit trail capture (Tenancy, Monitors, Governance).
3. Sensitive credential and PII redaction.
4. Canonical SHA-256 payload integrity hashing and compliance export verification.
5. Operational ROI and MTTR progression evaluation.
6. Governance audit export and ROI REST API endpoints.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from corbel.core.database import get_session_factory
from corbel.domains.governance.audit import (
    AuditService,
    compute_canonical_payload_hash,
    redact_sensitive_data,
)
from corbel.domains.monitors.models import MonitorTargetType, RuleSeverity
from corbel.domains.monitors.schemas import BusinessRuleCreate, MonitorCreate
from corbel.domains.monitors.service import MonitorService
from corbel.domains.tenancy.models import MembershipStatus, OrgRole, ProjectStatus
from corbel.domains.tenancy.schemas import (
    MemberAddRequest,
    ProjectCreateRequest,
    ProjectUpdateRequest,
)
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_audit_event_immutability_triggers(async_client: AsyncClient) -> None:
    """Verify ADR-020 database triggers strictly reject UPDATE, DELETE, and TRUNCATE."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    # 1. Insert an audit event via AuditService
    event_id: uuid.UUID
    async with session_factory() as session:
        audit_service = AuditService(session)
        ev = await audit_service.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="TEST_IMMUTABILITY_EVENT",
            affected_entity_type="TestEntity",
            affected_entity_id=str(uuid.uuid4()),
            execution_context={"key": "initial_value"},
        )
        await session.commit()
        event_id = ev.id

    # 2. Attempt UPDATE - must be rejected by PostgreSQL trigger
    async with session_factory() as session:
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(
                text("UPDATE audit_events SET action_type = 'TAMPERED' WHERE id = :event_id"),
                {"event_id": event_id},
            )
            await session.commit()
        assert "audit_events table is append-only" in str(exc_info.value)
        await session.rollback()

    # 3. Attempt DELETE - must be rejected by PostgreSQL trigger
    async with session_factory() as session:
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(
                text("DELETE FROM audit_events WHERE id = :event_id"),
                {"event_id": event_id},
            )
            await session.commit()
        assert "audit_events table is append-only" in str(exc_info.value)
        await session.rollback()

    # 4. Attempt TRUNCATE - must be rejected by PostgreSQL trigger
    async with session_factory() as session:
        with pytest.raises(DBAPIError) as exc_info:
            await session.execute(text("TRUNCATE TABLE audit_events"))
            await session.commit()
        assert "audit_events table is append-only" in str(exc_info.value)
        await session.rollback()


@pytest.mark.anyio
async def test_audit_sensitive_data_redaction_and_canonical_hash() -> None:
    """Verify recursive secret redaction and deterministic canonical hashing."""
    raw_payload = {
        "user_email": "auditor@corbel.internal",
        "api_key": "sk-proj-supersecretkey1234567890",
        "password": "my_plaintext_password",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy",
        "nested": {
            "token": "secret_access_token",
            "safe_counter": 42,
        },
    }

    redacted = redact_sensitive_data(raw_payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["password"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"
    assert redacted["nested"]["safe_counter"] == 42
    assert redacted["user_email"] == "auditor@corbel.internal"

    # Deterministic SHA-256 hash
    hash1 = compute_canonical_payload_hash(redacted)
    hash2 = compute_canonical_payload_hash(redacted)
    assert hash1 == hash2
    assert len(hash1) == 64


@pytest.mark.anyio
async def test_cross_domain_administrative_audit_trail(async_client: AsyncClient) -> None:
    """Verify administrative actions in Tenancy and Monitors domains produce immutable audit records."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    # 1. Tenancy Actions: Create a secondary user and add as member
    secondary_email = f"member_{uuid.uuid4().hex[:8]}@example.com"
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": secondary_email, "password": "Password123!", "full_name": "Test Member"},
    )
    assert reg_resp.status_code == 201
    secondary_user_id = uuid.UUID(reg_resp.json()["id"])

    async with session_factory() as session:
        tenancy_service = TenancyService(session)

        # Add member
        await tenancy_service.add_organization_member(
            org_id=org_id,
            actor_id=user_id,
            req=MemberAddRequest(email=secondary_email, role=OrgRole.MEMBER),
        )

        # Update member role
        await tenancy_service.update_member_role(
            org_id=org_id,
            actor_id=user_id,
            target_user_id=secondary_user_id,
            new_role=OrgRole.AUDITOR,
        )

        # Update member status
        await tenancy_service.update_member_status(
            org_id=org_id,
            actor_id=user_id,
            target_user_id=secondary_user_id,
            new_status=MembershipStatus.SUSPENDED,
        )

        # Create secondary project
        proj2 = await tenancy_service.create_project(
            org_id=org_id,
            actor_id=user_id,
            req=ProjectCreateRequest(name="Secondary Audit Project", description="Phase 10 test"),
        )

        # Update project
        await tenancy_service.update_project(
            org_id=org_id,
            project_id=proj2.id,
            actor_id=user_id,
            req=ProjectUpdateRequest(status=ProjectStatus.ARCHIVED),
        )

    # 2. Monitors Actions: Create monitor, add rule, and update finding status
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        monitor_service = MonitorService(session=session, tenancy_service=tenancy_service)

        monitor_resp = await monitor_service.create_monitor(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            req=MonitorCreate(
                name=f"Audit Test Monitor {uuid.uuid4().hex[:6]}",
                target_type=MonitorTargetType.ENTITY,
                target_id="PurchaseOrder",
            ),
        )
        monitor_id = monitor_resp.id

        await monitor_service.add_rule(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            monitor_id=monitor_id,
            req=BusinessRuleCreate(
                rule_code="AUDIT-RULE-001",
                description="Test rule emission",
                severity=RuleSeverity.HIGH,
                rule_type="NUMERIC_COMPARISON",
                field_name="total_amount",
                operator="gt",
                threshold_value=1000.0,
            ),
        )

    # 3. Query audit trail and verify administrative event coverage
    async with session_factory() as session:
        audit_service = AuditService(session)
        events, total = await audit_service.list_events(
            organization_id=org_id,
            limit=100,
        )
        action_types = {e.action_type for e in events}

        assert "MEMBER_ADDED" in action_types
        assert "MEMBER_ROLE_UPDATED" in action_types
        assert "MEMBER_STATUS_UPDATED" in action_types
        assert "PROJECT_CREATED" in action_types
        assert "PROJECT_UPDATED" in action_types
        assert "MONITOR_CREATED" in action_types
        assert "MONITOR_RULE_ADDED" in action_types


@pytest.mark.anyio
async def test_audit_trail_export_and_roi_endpoints(async_client: AsyncClient) -> None:
    """Verify /audit-events/export and /governance/roi API endpoints."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}"}
    project_id = project["id"]

    # 1. Run P2P Vertical Slice Demo to generate governance events and findings
    demo_resp = await async_client.post(
        f"/api/v1/projects/{project_id}/demo/p2p-slice",
        json={
            "supplier_name": "Apex Industrial Supplies",
            "po_number": "PO-9910",
            "po_amount": 5000.0,
            "invoice_number": "INV-9910",
            "invoice_amount": 6250.0,
            "expected_variance": 1250.0,
            "auto_approve": True,
        },
        headers=headers,
    )
    assert demo_resp.status_code == 200

    # 2. Test Audit Trail Export Endpoint
    export_resp = await async_client.get(
        f"/api/v1/projects/{project_id}/audit-events/export",
        headers=headers,
    )
    assert export_resp.status_code == 200
    export_data = export_resp.json()

    assert export_data["total_events"] > 0
    assert export_data["integrity_verified"] is True
    assert len(export_data["events"]) > 0

    # Verify each event has valid payload verification status
    for ev in export_data["events"]:
        assert ev["payload_verification_status"] in ("VERIFIED", "NO_PAYLOAD", "VERIFIED_DIGEST_ONLY")
        assert ev["canonical_payload_hash"] is not None

    # 3. Test Operational ROI & MTTR Progression Endpoint
    roi_resp = await async_client.get(
        f"/api/v1/projects/{project_id}/governance/roi",
        headers=headers,
    )
    assert roi_resp.status_code == 200
    roi_data = roi_resp.json()

    assert roi_data["incidents_investigated"] >= 1
    assert roi_data["incidents_resolved"] >= 1
    assert roi_data["baseline_mttr_minutes"] == 2880.0
    assert roi_data["current_mttr_minutes"] > 0.0
    assert roi_data["mttr_reduction_percentage"] > 90.0  # Automated demo resolves in seconds vs 48 hrs
    assert roi_data["total_financial_impact_addressed_usd"] >= 1250.0
