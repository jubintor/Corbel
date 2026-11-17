"""Targeted regression tests for Phase 10 Remediation.

Covers:
1. SEC-P10-001: Audit export and ROI authorization (AUDITOR, PROJECT_LEAD, ORG_ADMIN allowed; ANALYST, OPERATOR, non-member, cross-tenant denied).
2. SEC-P10-003: Sensitive data redaction (cookie headers, session credentials, Bearer tokens, DB connection strings, API keys, error strings, mixed-case keys, plain business text preserved).
3. COV-P10-001: Project membership audit coverage (PROJECT_MEMBER_ADDED, PROJECT_MEMBER_UPDATED, PROJECT_MEMBER_REMOVED, transaction atomicity).
4. DATA-P10-001: MTTR correctness (unresolved, proposed, rejected, failed, cancelled excluded; deduplicated findings/executions; timestamp safety).
5. DOC-P10-001: Correct financial metric terminology (benefit_cost_ratio and financial_roi_ratio).
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from corbel.ai.telemetry.phoenix import redact_secrets_from_text
from corbel.core.database import get_session_factory
from corbel.domains.governance.audit import (
    AuditService,
    compute_canonical_payload_hash,
    redact_sensitive_data,
    redact_string_credentials,
)
from corbel.domains.governance.models import (
    Action,
    ActionExecution,
    ActionStatus,
    ActionType,
    Approval,
    ApprovalStatus,
    AuditEvent,
    ExecutionStatus,
    Investigation,
    InvestigationStatus,
    Recommendation,
    RiskLevel,
)
from corbel.domains.monitors.models import (
    Finding,
    FindingStatus,
    Monitor,
    MonitorStatus,
    MonitorTargetType,
)
from corbel.domains.tenancy.models import OrgRole, ProjectMember, ProjectRole
from corbel.domains.tenancy.schemas import MemberAddRequest
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project
from tests.test_tenancy import create_user_and_token

# ==============================================================================
# 1. SEC-P10-001: Audit Export & ROI Authorization Tests
# ==============================================================================


@pytest.mark.anyio
async def test_audit_export_and_roi_rbac_enforcement(async_client: AsyncClient) -> None:
    """Verify SEC-P10-001: Only AUDITOR, PROJECT_LEAD, and ORG_ADMIN can export audit trail and query ROI."""
    # Setup base org and project (owner is ORG_ADMIN + PROJECT_LEAD)
    owner, owner_token, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    owner_id = uuid.UUID(owner["id"])
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    session_factory = get_session_factory()

    # Helper to create a user and assign to project with a specific role
    async def create_user_with_project_role(role: ProjectRole) -> tuple[dict, str]:
        u, tok = await create_user_and_token(async_client, f"User {role.value}")
        u_id = uuid.UUID(u["id"])
        async with session_factory() as session:
            tenancy = TenancyService(session)
            # Add to org as MEMBER
            from corbel.domains.tenancy.schemas import MemberAddRequest
            await tenancy.add_organization_member(
                org_id=org_id,
                actor_id=owner_id,
                req=MemberAddRequest(email=u["email"], role=OrgRole.MEMBER),
            )
            # Add to project
            await tenancy.add_project_member(
                org_id=org_id,
                project_id=project_id,
                actor_id=owner_id,
                target_user_id=u_id,
                role=role,
            )
        return u, tok

    # 1. Project AUDITOR -> Allowed (200)
    _, auditor_token = await create_user_with_project_role(ProjectRole.AUDITOR)
    auditor_headers = {"Authorization": f"Bearer {auditor_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=auditor_headers)
    assert r.status_code == 200, f"Expected 200 for ProjectRole.AUDITOR, got {r.status_code}: {r.text}"
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=auditor_headers)
    assert r_roi.status_code == 200

    # 2. Project PROJECT_LEAD -> Allowed (200)
    _, lead_token = await create_user_with_project_role(ProjectRole.PROJECT_LEAD)
    lead_headers = {"Authorization": f"Bearer {lead_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=lead_headers)
    assert r.status_code == 200
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=lead_headers)
    assert r_roi.status_code == 200

    # 3. Organization ORG_ADMIN -> Allowed (200)
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=owner_headers)
    assert r.status_code == 200
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=owner_headers)
    assert r_roi.status_code == 200

    # 4. Project ANALYST -> Denied (403)
    _, analyst_token = await create_user_with_project_role(ProjectRole.ANALYST)
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=analyst_headers)
    assert r.status_code == 403, f"Expected 403 for ProjectRole.ANALYST, got {r.status_code}"
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=analyst_headers)
    assert r_roi.status_code == 403

    # 5. Project OPERATOR -> Denied (403)
    _, operator_token = await create_user_with_project_role(ProjectRole.OPERATOR)
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=operator_headers)
    assert r.status_code == 403, f"Expected 403 for ProjectRole.OPERATOR, got {r.status_code}"
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=operator_headers)
    assert r_roi.status_code == 403

    # 6. Non-member user in same org -> Denied (403)
    non_member_user, non_member_token = await create_user_and_token(async_client, "Org Member Only")
    async with session_factory() as session:
        tenancy = TenancyService(session)
        from corbel.domains.tenancy.schemas import MemberAddRequest
        await tenancy.add_organization_member(
            org_id=org_id,
            actor_id=owner_id,
            req=MemberAddRequest(email=non_member_user["email"], role=OrgRole.MEMBER),
        )
    non_member_headers = {"Authorization": f"Bearer {non_member_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=non_member_headers)
    assert r.status_code == 403, f"Expected 403 for non-project member, got {r.status_code}"
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=non_member_headers)
    assert r_roi.status_code == 403

    # 7. Cross-tenant user -> Denied (403 / 404)
    _, foreign_token, _, _ = await setup_test_org_and_project(async_client)
    foreign_headers = {"Authorization": f"Bearer {foreign_token}"}
    r = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=foreign_headers)
    assert r.status_code in (403, 404), f"Expected 403/404 for cross-tenant access, got {r.status_code}"
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=foreign_headers)
    assert r_roi.status_code in (403, 404)


# ==============================================================================
# 2. SEC-P10-003: Sensitive Data Redaction Tests
# ==============================================================================


def test_sensitive_data_redaction_comprehensive() -> None:
    """Verify SEC-P10-003: Redaction of nested cookies, session credentials, DB strings, and exception text."""
    payload = {
        # Dictionary sensitive keys
        "headers": {
            "Cookie": "session_id=s3ss10n_t0k3n_12345; csrf=c5rf_t0k3n_98765",
            "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummytoken123",
            "User-Agent": "CorbelAuditAgent/1.0",
        },
        "session_id": "sess_abcdef1234567890",
        "client_secret": "sec_9876543210fedcba",
        "apiKey": "sk-proj-1234567890abcdef1234567890",
        "DATABASE_URL": "postgresql://dbuser:supersecretpass123@db.internal:5432/corbel_prod",
        "error_context": {
            "error": "Connection to postgresql://admin:p@ssw0rd99@db:5432 failed: Bearer secret_bearer_token_xyz12345",
            "retry_count": 3,
        },
        "business_record": {
            "po_number": "PO-9910",
            "supplier_name": "Apex Industrial Supplies",
            "total_amount": 5000.0,
            "variance_notes": "Invoice exceeds PO by $1,250.00 due to expedited shipping surcharge.",
        },
    }

    redacted = redact_sensitive_data(payload)

    # 1. Key-level dictionary redactions
    assert redacted["headers"]["Cookie"] == "[REDACTED]"
    assert redacted["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["headers"]["User-Agent"] == "CorbelAuditAgent/1.0"
    assert redacted["session_id"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["apiKey"] == "[REDACTED]"

    # 2. String credential redactions (DB URL in non-sensitive key name)
    assert "supersecretpass123" not in redacted["DATABASE_URL"]
    assert "[REDACTED]" in redacted["DATABASE_URL"]
    assert redacted["DATABASE_URL"] == "postgresql://dbuser:[REDACTED]@db.internal:5432/corbel_prod"

    # 3. String credentials in exception message
    err_str = redacted["error_context"]["error"]
    assert "p@ssw0rd99" not in err_str
    assert "secret_bearer_token_xyz12345" not in err_str
    assert "[REDACTED]" in err_str
    assert redacted["error_context"]["retry_count"] == 3

    # 4. Ordinary business content preserved intact
    assert redacted["business_record"]["po_number"] == "PO-9910"
    assert redacted["business_record"]["supplier_name"] == "Apex Industrial Supplies"
    assert redacted["business_record"]["total_amount"] == 5000.0
    assert redacted["business_record"]["variance_notes"] == "Invoice exceeds PO by $1,250.00 due to expedited shipping surcharge."

    # 5. Deterministic hashing consistency
    h1 = compute_canonical_payload_hash(redacted)
    h2 = compute_canonical_payload_hash(redacted)
    assert h1 == h2


def test_redact_string_credentials_patterns() -> None:
    """Verify specific credential string patterns, including database URIs with special characters."""
    # Bearer
    b_text = "Call authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummytoken"
    assert redact_string_credentials(b_text) == "Call authorization: Bearer [REDACTED]"
    assert redact_secrets_from_text(b_text) == "Call authorization: Bearer [REDACTED]"

    # OpenAI API Key
    sk_text = "Failed with key sk-proj-1234567890abcdef1234567890"
    assert redact_string_credentials(sk_text) == "Failed with key [REDACTED]"
    assert redact_secrets_from_text(sk_text) == "Failed with key [REDACTED]"

    # Anthropic API Key
    ant_text = "Anthropic key sk-ant-api03-1234567890abcdef1234567890"
    assert redact_string_credentials(ant_text) == "Anthropic key [REDACTED]"
    assert redact_secrets_from_text(ant_text) == "Anthropic key [REDACTED]"

    # MySQL connection string
    mysql_text = "mysql://root:toor1234@localhost:3306/app"
    assert redact_string_credentials(mysql_text) == "mysql://root:[REDACTED]@localhost:3306/app"
    assert redact_secrets_from_text(mysql_text) == "mysql://root:[REDACTED]@localhost:3306/app"

    # Database URI with '@' in password (SEC-P10-001 / Requirement 1)
    pg_special = "postgresql://admin:p@ssw0rd99@db:5432/corbel"
    redacted_pg = redact_string_credentials(pg_special)
    assert redacted_pg == "postgresql://admin:[REDACTED]@db:5432/corbel"
    assert "p@ssw0rd99" not in redacted_pg
    assert redact_secrets_from_text(pg_special) == "postgresql://admin:[REDACTED]@db:5432/corbel"

    # Database URI with URL-encoded characters and colons in password
    mysql_special = "mysql://app_user:p%40ss%3Aw%2Frd@127.0.0.1:3306/production"
    redacted_mysql = redact_string_credentials(mysql_special)
    assert redacted_mysql == "mysql://app_user:[REDACTED]@127.0.0.1:3306/production"
    assert "p%40ss%3Aw%2Frd" not in redacted_mysql
    assert redact_secrets_from_text(mysql_special) == "mysql://app_user:[REDACTED]@127.0.0.1:3306/production"

    # MongoDB SRV with special character in password
    mongo_special = "mongodb+srv://admin:Secr3t!@cluster0.mongodb.net/test?retryWrites=true"
    redacted_mongo = redact_string_credentials(mongo_special)
    assert redacted_mongo == "mongodb+srv://admin:[REDACTED]@cluster0.mongodb.net/test?retryWrites=true"
    assert "Secr3t!" not in redacted_mongo
    assert redact_secrets_from_text(mongo_special) == "mongodb+srv://admin:[REDACTED]@cluster0.mongodb.net/test?retryWrites=true"

    # Redis connection string with password only
    redis_text = "redis://:mypassword123@cache:6379/0"
    redacted_redis = redact_string_credentials(redis_text)
    assert redacted_redis == "redis://:[REDACTED]@cache:6379/0"
    assert "mypassword123" not in redacted_redis
    assert redact_secrets_from_text(redis_text) == "redis://:[REDACTED]@cache:6379/0"

    # URI in sentence with trailing punctuation
    sentence_text = "Error connecting to postgresql://admin:p@ssw0rd99@db:5432/corbel."
    redacted_sentence = redact_string_credentials(sentence_text)
    assert redacted_sentence == "Error connecting to postgresql://admin:[REDACTED]@db:5432/corbel."
    assert "p@ssw0rd99" not in redacted_sentence


# ==============================================================================
# 3. COV-P10-001: Project Membership Audit Coverage Tests
# ==============================================================================


@pytest.mark.anyio
async def test_project_membership_audit_events_and_atomicity(async_client: AsyncClient) -> None:
    """Verify COV-P10-001: Project member add, update, and remove produce audit events in the same transaction."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    actor_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    # Create target user in same organization
    target_user, _ = await create_user_and_token(async_client, "Audited Member")
    target_user_id = uuid.UUID(target_user["id"])

    async with session_factory() as session:
        tenancy = TenancyService(session)
        from corbel.domains.tenancy.schemas import MemberAddRequest
        await tenancy.add_organization_member(
            org_id=org_id,
            actor_id=actor_id,
            req=MemberAddRequest(email=target_user["email"], role=OrgRole.MEMBER),
        )

    # 1. Add project member -> PROJECT_MEMBER_ADDED
    async with session_factory() as session:
        tenancy = TenancyService(session)
        pm = await tenancy.add_project_member(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            target_user_id=target_user_id,
            role=ProjectRole.ANALYST,
        )
        assert pm is not None

    # Verify audit event recorded
    async with session_factory() as session:
        audit = AuditService(session)
        events, _ = await audit.list_events(
            organization_id=org_id,
            project_id=project_id,
            action_type="PROJECT_MEMBER_ADDED",
        )
        assert len(events) >= 1
        ev = events[0]
        assert ev.affected_entity_type == "ProjectMember"
        assert ev.actor_id == str(actor_id)
        assert ev.execution_context_json["target_user_id"] == str(target_user_id)
        assert ev.execution_context_json["new_role"] == ProjectRole.ANALYST.value

    # 2. Update project member -> PROJECT_MEMBER_UPDATED
    async with session_factory() as session:
        tenancy = TenancyService(session)
        pm_up = await tenancy.add_project_member(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            target_user_id=target_user_id,
            role=ProjectRole.AUDITOR,
        )
        assert pm_up.project_role == ProjectRole.AUDITOR.value

    async with session_factory() as session:
        audit = AuditService(session)
        events, _ = await audit.list_events(
            organization_id=org_id,
            project_id=project_id,
            action_type="PROJECT_MEMBER_UPDATED",
        )
        assert len(events) >= 1
        ev = events[0]
        assert ev.execution_context_json["previous_role"] == ProjectRole.ANALYST.value
        assert ev.execution_context_json["new_role"] == ProjectRole.AUDITOR.value

    # 3. Remove project member -> PROJECT_MEMBER_REMOVED
    async with session_factory() as session:
        tenancy = TenancyService(session)
        await tenancy.remove_project_member(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            target_user_id=target_user_id,
        )

    async with session_factory() as session:
        audit = AuditService(session)
        events, _ = await audit.list_events(
            organization_id=org_id,
            project_id=project_id,
            action_type="PROJECT_MEMBER_REMOVED",
        )
        assert len(events) >= 1
        ev = events[0]
        assert ev.execution_context_json["target_user_id"] == str(target_user_id)


# ==============================================================================
# 4. DATA-P10-001 & DOC-P10-001: MTTR Correctness & Benefit-Cost Ratio Tests
# ==============================================================================


@pytest.mark.anyio
async def test_mttr_and_benefit_cost_ratio_correctness(async_client: AsyncClient) -> None:
    """Verify DATA-P10-001 & DOC-P10-001: Only successful terminal executions qualify for MTTR; deduplication and ratio."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()

    async with session_factory() as session:
        audit_service = AuditService(session)

        # Create monitor
        mon = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Remediation Value Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(mon)
        await session.flush()

        # 1. Setup Finding 1: Successfully resolved
        f1 = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-001",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.RESOLVED.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=60),
            summary="PO vs Invoice price discrepancy",
        )

        # 2. Setup Finding 2: Unresolved investigation (must NOT be counted in MTTR)
        f2 = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-002",
            finding_type="DELIVERY_DELAY",
            severity="MEDIUM",
            status=FindingStatus.OPEN.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=120),
            summary="Delayed shipment",
        )

        # 3. Setup Finding 3: Failed action execution (must NOT be counted in MTTR)
        f3 = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-003",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.INVESTIGATING.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=90),
            summary="Failed action execution",
        )

        session.add_all([f1, f2, f3])
        await session.flush()

        inv1 = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f1.id,
            title="Investigation for F1",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1200.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=45),
        )

        inv2 = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f2.id,
            title="Investigation for F2",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=5000.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=110),
        )

        inv3 = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f3.id,
            title="Investigation for F3",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=3000.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=80),
        )

        # 4. Setup Duplicate Investigation on Finding 1 (must NOT duplicate financial impact)
        inv1_dup = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f1.id,  # Points to Finding 1
            title="Duplicate investigation on F1",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1200.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=30),
        )

        session.add_all([inv1, inv2, inv3, inv1_dup])
        await session.flush()

        rec1 = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv1.id,
            title="Credit memo adjustment",
            description="Adjust price discrepancy",
            confidence_score=0.95,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 1200.0},
            risk_level=RiskLevel.LOW.value,
        )

        rec3 = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv3.id,
            title="Failed recommendation",
            description="Failed attempt",
            confidence_score=0.85,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 3000.0},
            risk_level=RiskLevel.MEDIUM.value,
        )

        session.add_all([rec1, rec3])
        await session.flush()

        act1 = Action(
            id=uuid.uuid4(),
            project_id=project_id,
            recommendation_id=rec1.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 1200.0},
            status=ActionStatus.EXECUTED.value,
        )

        act3 = Action(
            id=uuid.uuid4(),
            project_id=project_id,
            recommendation_id=rec3.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 3000.0},
            status=ActionStatus.FAILED.value,
        )

        session.add_all([act1, act3])
        await session.flush()

        appr1 = Approval(
            id=uuid.uuid4(),
            action_id=act1.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 1200.0},
        )

        appr3 = Approval(
            id=uuid.uuid4(),
            action_id=act3.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 3000.0},
        )

        session.add_all([appr1, appr3])
        await session.flush()

        # Terminal SUCCEEDED execution completed 15 mins after detection (duration = 45 mins)
        exec1 = ActionExecution(
            id=uuid.uuid4(),
            action_id=act1.id,
            approval_id=appr1.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"amount": 1200.0},
            dispatched_payload_hash="dummyhash",
            completed_at=f1.detected_at + timedelta(minutes=45),
        )

        exec3 = ActionExecution(
            id=uuid.uuid4(),
            action_id=act3.id,
            approval_id=appr3.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.FAILED.value,
            dispatched_payload_json={"amount": 3000.0},
            dispatched_payload_hash="dummyhash3",
            completed_at=datetime.now(UTC) - timedelta(minutes=70),
        )

        session.add_all([exec1, exec3])
        await session.commit()

        # Calculate Operational ROI
        roi = await audit_service.get_operational_roi(organization_id=org_id, project_id=project_id)

        # Assertions
        # Total investigated incidents = 4 investigations
        assert roi.incidents_investigated == 4
        # Only Finding 1 successfully resolved
        assert roi.incidents_resolved == 1
        # Financial impact only counted once ($1200.0, not $1200 + $1200 from duplicate)
        assert roi.total_financial_impact_addressed_usd == 1200.0
        # MTTR must be exactly 45.0 minutes (from F1 detection to exec1 completion)
        assert roi.current_mttr_minutes == 45.0
        # Baseline is 2880.0
        assert roi.baseline_mttr_minutes == 2880.0
        # Reduction percentage: (2880 - 45) / 2880 * 100 = 98.44%
        assert roi.mttr_reduction_percentage == 98.44

        # Benefit-Cost Ratio & Legacy Financial ROI Ratio fields
        assert hasattr(roi, "benefit_cost_ratio")
        assert hasattr(roi, "financial_roi_ratio")
        assert roi.benefit_cost_ratio == roi.financial_roi_ratio


# ==============================================================================
# 5. Audit Hash Integrity & Caller Hash Rejection Tests (Requirement 2)
# ==============================================================================


@pytest.mark.anyio
async def test_audit_hash_integrity_and_caller_supplied_rejection(async_client: AsyncClient) -> None:
    """Verify Requirement 2: Internal SHA-256 calculation, redaction before hash, and caller hash rejection."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    actor_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    # 1. Normal payload receives deterministic canonical hash
    raw_payload = {"po_number": "PO-1001", "amount": 2500.0, "status": "APPROVED"}
    expected_hash = compute_canonical_payload_hash(raw_payload)

    async with session_factory() as session:
        audit = AuditService(session)
        ev1 = await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="TEST_HASH_NORMAL",
            affected_entity_type="PurchaseOrder",
            affected_entity_id="PO-1001",
            execution_context=raw_payload,
        )
        await session.commit()
        assert ev1.canonical_payload_hash == expected_hash

    # 2. Sensitive values are redacted BEFORE hashing
    payload_with_secrets = {
        "po_number": "PO-1002",
        "api_key": "sk-proj-secrettoken1234567890",
        "DATABASE_URL": "postgresql://admin:p@ssw0rd99@db:5432/corbel",
    }
    sanitized_payload = redact_sensitive_data(payload_with_secrets)
    expected_sanitized_hash = compute_canonical_payload_hash(sanitized_payload)

    async with session_factory() as session:
        audit = AuditService(session)
        ev2 = await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="TEST_HASH_REDACTED",
            affected_entity_type="PurchaseOrder",
            affected_entity_id="PO-1002",
            execution_context=payload_with_secrets,
        )
        await session.commit()
        assert ev2.canonical_payload_hash == expected_sanitized_hash
        assert ev2.execution_context_json["api_key"] == "[REDACTED]"
        assert "p@ssw0rd99" not in ev2.execution_context_json["DATABASE_URL"]

    # 3. Caller-supplied mismatched hash is REJECTED
    async with session_factory() as session:
        audit = AuditService(session)
        with pytest.raises(ValueError) as exc_info:
            await audit.log_event(
                organization_id=org_id,
                project_id=project_id,
                actor_id=str(actor_id),
                action_type="TEST_HASH_TAMPERED",
                affected_entity_type="PurchaseOrder",
                affected_entity_id="PO-1003",
                execution_context={"po_number": "PO-1003"},
                canonical_payload_hash="tampered_fake_hash_1234567890",
            )
        assert "Integrity violation" in str(exc_info.value)
        assert "tampered_fake_hash_1234567890" in str(exc_info.value)

    # 4. Caller-supplied matching hash is accepted
    matching_hash = compute_canonical_payload_hash({"po_number": "PO-1004"})
    async with session_factory() as session:
        audit = AuditService(session)
        ev4 = await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="TEST_HASH_MATCHING",
            affected_entity_type="PurchaseOrder",
            affected_entity_id="PO-1004",
            execution_context={"po_number": "PO-1004"},
            canonical_payload_hash=matching_hash,
        )
        await session.commit()
        assert ev4.canonical_payload_hash == matching_hash

    # 5. Repeated identical payloads produce identical hashes
    async with session_factory() as session:
        audit = AuditService(session)
        ev5a = await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="TEST_HASH_REPEATED_A",
            affected_entity_type="Entity",
            affected_entity_id="E-1",
            execution_context={"b": 2, "a": 1},
        )
        ev5b = await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="TEST_HASH_REPEATED_B",
            affected_entity_type="Entity",
            affected_entity_id="E-2",
            execution_context={"a": 1, "b": 2},  # Same keys in different dict order
        )
        await session.commit()
        assert ev5a.canonical_payload_hash == ev5b.canonical_payload_hash


# ==============================================================================
# 6. Audit Export Integrity Reporting Tests (Requirement 3)
# ==============================================================================


@pytest.mark.anyio
async def test_audit_export_integrity_reporting_statuses(async_client: AsyncClient) -> None:
    """Verify Requirement 3: Per-record payload verification statuses and aggregate integrity_verified boolean."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    actor_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    # Create isolated project for testing all statuses together
    async with session_factory() as session:
        audit = AuditService(session)

        # 1. Record with matching payload & hash -> VERIFIED
        await audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(actor_id),
            action_type="EVENT_VERIFIED",
            affected_entity_type="Entity",
            affected_entity_id="1",
            execution_context={"valid": True},
        )

        # 2. Record with tampered hash (inserted directly to simulate DB corruption / tampering)
        ev_mismatch = AuditEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            actor_type="USER",
            actor_id=str(actor_id),
            action_type="EVENT_TAMPERED",
            affected_entity_type="Entity",
            affected_entity_id="2",
            execution_context_json={"valid": True},
            canonical_payload_hash="invalid_corrupted_hash",
            outcome_status="SUCCESS",
        )
        session.add(ev_mismatch)

        # 3. Record with unhashed payload (payload present, but hash is None)
        ev_unhashed = AuditEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            actor_type="USER",
            actor_id=str(actor_id),
            action_type="EVENT_UNHASHED",
            affected_entity_type="Entity",
            affected_entity_id="3",
            execution_context_json={"unhashed": True},
            canonical_payload_hash=None,
            outcome_status="SUCCESS",
        )
        session.add(ev_unhashed)

        # 4. Record with unavailable payload (hash present, but execution_context_json is None)
        ev_unavailable = AuditEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            actor_type="USER",
            actor_id=str(actor_id),
            action_type="EVENT_UNAVAILABLE_PAYLOAD",
            affected_entity_type="Entity",
            affected_entity_id="4",
            execution_context_json=None,
            canonical_payload_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            outcome_status="SUCCESS",
        )
        session.add(ev_unavailable)

        # 5. Record with no payload and no hash
        ev_nopayload = AuditEvent(
            id=uuid.uuid4(),
            organization_id=org_id,
            project_id=project_id,
            actor_type="USER",
            actor_id=str(actor_id),
            action_type="EVENT_NO_PAYLOAD",
            affected_entity_type="Entity",
            affected_entity_id="5",
            execution_context_json=None,
            canonical_payload_hash=None,
            outcome_status="SUCCESS",
        )
        session.add(ev_nopayload)
        await session.commit()

        # Export audit trail
        export_resp = await audit.export_audit_trail(organization_id=org_id, project_id=project_id)

    # Verify per-record verification statuses
    status_by_action = {item.action_type: item.payload_verification_status for item in export_resp.events}
    assert status_by_action["EVENT_VERIFIED"] == "VERIFIED"
    assert status_by_action["EVENT_TAMPERED"] == "HASH_MISMATCH"
    assert status_by_action["EVENT_UNHASHED"] == "UNHASHED_PAYLOAD"
    assert status_by_action["EVENT_UNAVAILABLE_PAYLOAD"] == "UNAVAILABLE_PAYLOAD"
    assert status_by_action["EVENT_NO_PAYLOAD"] == "NO_PAYLOAD"

    # Because there are unverified records, aggregate integrity_verified MUST be False
    assert export_resp.integrity_verified is False

    # Now verify that when a project has ONLY valid verified records, integrity_verified is True
    _, _, _, clean_project = await setup_test_org_and_project(async_client)
    clean_project_id = uuid.UUID(clean_project["id"])
    async with session_factory() as session:
        clean_audit = AuditService(session)
        await clean_audit.log_event(
            organization_id=org_id,
            project_id=clean_project_id,
            actor_id=str(actor_id),
            action_type="CLEAN_EVENT_1",
            affected_entity_type="Entity",
            affected_entity_id="c1",
            execution_context={"key": "val1"},
        )
        await clean_audit.log_event(
            organization_id=org_id,
            project_id=clean_project_id,
            actor_id=str(actor_id),
            action_type="CLEAN_EVENT_2",
            affected_entity_type="Entity",
            affected_entity_id="c2",
            execution_context={"key": "val2"},
        )
        await session.commit()

        clean_export = await clean_audit.export_audit_trail(organization_id=org_id, project_id=clean_project_id)
        assert len(clean_export.events) == 2
        assert all(item.payload_verification_status == "VERIFIED" for item in clean_export.events)
        assert clean_export.integrity_verified is True


# ==============================================================================
# 7. Operational ROI Deterministic Earliest Execution & Negative Duration Tests (Requirement 4)
# ==============================================================================


@pytest.mark.anyio
async def test_operational_roi_deterministic_earliest_execution_and_negative_duration(async_client: AsyncClient) -> None:
    """Verify Requirement 4: Deterministic earliest execution selection, duplicate impact deduplication, and negative duration exclusion."""
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()

    async with session_factory() as session:
        audit_service = AuditService(session)

        mon = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Deterministic ROI Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(mon)
        await session.flush()

        # Finding 1 with two investigations and executions:
        # Inv 1: earlier execution (completed 20 mins after detection) with impact 1500.0
        # Inv 2: later execution (completed 50 mins after detection) with impact 2500.0
        f1 = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-DETERM-1",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.RESOLVED.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=60),
            summary="Price variance on INV-DETERM-1",
        )

        # Finding 2 with invalid negative duration (detected_at is AFTER completed_at, e.g. clock skew)
        f2_negative = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=mon.id,
            entity_type="Invoice",
            entity_id="INV-NEGATIVE",
            finding_type="PRICE_VARIANCE",
            severity="MEDIUM",
            status=FindingStatus.RESOLVED.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) + timedelta(minutes=60),  # Future detected_at
            summary="Invalid timestamp finding",
        )

        session.add_all([f1, f2_negative])
        await session.flush()

        inv1_earlier = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f1.id,
            title="Earlier Investigation for F1",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1500.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=40),
        )

        inv1_later = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f1.id,
            title="Later Investigation for F1",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=2500.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=10),
        )

        inv2_neg = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=f2_negative.id,
            title="Investigation for F2 negative",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=800.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=10),
        )

        session.add_all([inv1_earlier, inv1_later, inv2_neg])
        await session.flush()

        # Recommendations
        rec1_earlier = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv1_earlier.id,
            title="Rec 1 Earlier",
            description="Rec earlier",
            confidence_score=0.9,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 1500.0},
            risk_level=RiskLevel.LOW.value,
        )
        rec1_later = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv1_later.id,
            title="Rec 1 Later",
            description="Rec later",
            confidence_score=0.8,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 2500.0},
            risk_level=RiskLevel.LOW.value,
        )
        rec2_neg = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv2_neg.id,
            title="Rec 2 Neg",
            description="Rec neg",
            confidence_score=0.9,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 800.0},
            risk_level=RiskLevel.LOW.value,
        )
        session.add_all([rec1_earlier, rec1_later, rec2_neg])
        await session.flush()

        # Actions
        act1_earlier = Action(
            id=uuid.uuid4(),
            project_id=project_id,
            recommendation_id=rec1_earlier.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 1500.0},
            status=ActionStatus.EXECUTED.value,
        )
        act1_later = Action(
            id=uuid.uuid4(),
            project_id=project_id,
            recommendation_id=rec1_later.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 2500.0},
            status=ActionStatus.EXECUTED.value,
        )
        act2_neg = Action(
            id=uuid.uuid4(),
            project_id=project_id,
            recommendation_id=rec2_neg.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 800.0},
            status=ActionStatus.EXECUTED.value,
        )
        session.add_all([act1_earlier, act1_later, act2_neg])
        await session.flush()

        # Approvals
        appr1_earlier = Approval(
            id=uuid.uuid4(),
            action_id=act1_earlier.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 1500.0},
        )
        appr1_later = Approval(
            id=uuid.uuid4(),
            action_id=act1_later.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 2500.0},
        )
        appr2_neg = Approval(
            id=uuid.uuid4(),
            action_id=act2_neg.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 800.0},
        )
        session.add_all([appr1_earlier, appr1_later, appr2_neg])
        await session.flush()

        # Executions:
        # exec1_earlier completed 20 mins after f1.detected_at
        exec1_earlier = ActionExecution(
            id=uuid.uuid4(),
            action_id=act1_earlier.id,
            approval_id=appr1_earlier.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"amount": 1500.0},
            dispatched_payload_hash="hash_early",
            completed_at=f1.detected_at + timedelta(minutes=20),
        )
        # exec1_later completed 50 mins after f1.detected_at
        exec1_later = ActionExecution(
            id=uuid.uuid4(),
            action_id=act1_later.id,
            approval_id=appr1_later.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"amount": 2500.0},
            dispatched_payload_hash="hash_late",
            completed_at=f1.detected_at + timedelta(minutes=50),
        )
        # exec2_neg has completed_at BEFORE f2_negative.detected_at (negative duration!)
        exec2_neg = ActionExecution(
            id=uuid.uuid4(),
            action_id=act2_neg.id,
            approval_id=appr2_neg.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"amount": 800.0},
            dispatched_payload_hash="hash_neg",
            completed_at=datetime.now(UTC),  # Detected is 60m in future, so duration < 0
        )
        session.add_all([exec1_earlier, exec1_later, exec2_neg])
        await session.commit()

        # Compute ROI
        roi = await audit_service.get_operational_roi(organization_id=org_id, project_id=project_id)

        # 1. Total incidents resolved = 2 findings (F1 and F2_negative)
        assert roi.incidents_resolved == 2
        # 2. Financial impact: F1 impact is 1500.0 (from earlier execution, NOT 1500 + 2500), F2 impact is 800.0 -> total 2300.0
        assert roi.total_financial_impact_addressed_usd == 2300.0
        # 3. MTTR duration: ONLY F1 (20.0 minutes) qualifies! F2_negative had negative duration and was excluded, NOT converted to 0.1
        assert roi.current_mttr_minutes == 20.0
        assert roi.baseline_mttr_minutes == 2880.0
        # 4. Reduction: (2880 - 20) / 2880 * 100 = 99.31%
        assert roi.mttr_reduction_percentage == 99.31


# ==============================================================================
# 8. Distinct ORG_ADMIN Supervisory Access Without Project Membership (Requirement 5)
# ==============================================================================


@pytest.mark.anyio
async def test_org_admin_supervisory_access_without_project_membership(async_client: AsyncClient) -> None:
    """Verify Requirement 5: ORG_ADMIN who is not a project member has supervisory access to export and ROI."""
    creator_user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    creator_id = uuid.UUID(creator_user["id"])

    session_factory = get_session_factory()

    # Create a separate pure ORG_ADMIN user who is NOT assigned as a project member
    admin_user, admin_token = await create_user_and_token(async_client, "Pure Org Admin")
    admin_user_id = uuid.UUID(admin_user["id"])

    # Create a regular organization MEMBER who is also NOT a project member
    regular_member, regular_token = await create_user_and_token(async_client, "Regular Org Member")

    async with session_factory() as session:
        tenancy = TenancyService(session)
        # Add pure admin to organization as ORG_ADMIN
        await tenancy.add_organization_member(
            org_id=org_id,
            actor_id=creator_id,
            req=MemberAddRequest(email=admin_user["email"], role=OrgRole.ORG_ADMIN),
        )
        # Add regular user to organization as MEMBER
        await tenancy.add_organization_member(
            org_id=org_id,
            actor_id=creator_id,
            req=MemberAddRequest(email=regular_member["email"], role=OrgRole.MEMBER),
        )

    # Verify that pure_admin_user is NOT a member of the project
    async with session_factory() as session:
        pm_check = (
            await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == admin_user_id,
                )
            )
        ).scalar_one_or_none()
        assert pm_check is None, "Test invariant: pure_admin_user must not be a project member"

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    member_headers = {"Authorization": f"Bearer {regular_token}"}

    # 1. Pure ORG_ADMIN can export audit records without project membership -> 200
    r_export = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=admin_headers)
    assert r_export.status_code == 200, f"Expected 200 for ORG_ADMIN, got {r_export.status_code}: {r_export.text}"

    # 2. Pure ORG_ADMIN can access ROI without project membership -> 200
    r_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=admin_headers)
    assert r_roi.status_code == 200, f"Expected 200 for ORG_ADMIN, got {r_roi.status_code}: {r_roi.text}"

    # 3. Regular organization MEMBER without project membership -> 403
    r_mem_export = await async_client.get(f"/api/v1/projects/{project_id}/audit-events/export", headers=member_headers)
    assert r_mem_export.status_code == 403
    r_mem_roi = await async_client.get(f"/api/v1/projects/{project_id}/governance/roi", headers=member_headers)
    assert r_mem_roi.status_code == 403


# ==============================================================================
# 9. Membership Audit Transaction Integrity & Rollback Tests (Requirement 6)
# ==============================================================================


@pytest.mark.anyio
async def test_project_membership_transaction_rollback(async_client: AsyncClient) -> None:
    """Verify Requirement 6: If transaction fails, neither membership mutation nor its audit event is committed."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    actor_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()

    target_user, _ = await create_user_and_token(async_client, "Rollback Target")
    target_user_id = uuid.UUID(target_user["id"])

    # Add target user to organization
    async with session_factory() as session:
        tenancy = TenancyService(session)
        await tenancy.add_organization_member(
            org_id=org_id,
            actor_id=actor_id,
            req=MemberAddRequest(email=target_user["email"], role=OrgRole.MEMBER),
        )

    # 1. Test Rollback on add_project_member
    async with session_factory() as session:
        tenancy = TenancyService(session)
        with patch.object(session, "commit", side_effect=RuntimeError("Simulated database failure during member addition")):
            with pytest.raises(RuntimeError) as exc_info:
                await tenancy.add_project_member(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=actor_id,
                    target_user_id=target_user_id,
                    role=ProjectRole.ANALYST,
                )
            assert "Simulated database failure" in str(exc_info.value)
            await session.rollback()

    # Verify that in a fresh session: neither ProjectMember NOR AuditEvent exists
    async with session_factory() as session:
        # Check ProjectMember
        pm = (
            await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == target_user_id,
                )
            )
        ).scalar_one_or_none()
        assert pm is None, "Rollback invariant: ProjectMember must not exist after rollback"

        # Check AuditEvent
        ev = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.project_id == project_id,
                    AuditEvent.action_type == "PROJECT_MEMBER_ADDED",
                )
            )
        ).scalars().all()
        # Ensure no audit event for target_user_id was persisted
        target_events = [e for e in ev if e.execution_context_json and e.execution_context_json.get("target_user_id") == str(target_user_id)]
        assert len(target_events) == 0, "Rollback invariant: AuditEvent must not be committed after rollback"

    # Now successfully add the member so we can test rollback on removal
    async with session_factory() as session:
        tenancy = TenancyService(session)
        await tenancy.add_project_member(
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            target_user_id=target_user_id,
            role=ProjectRole.ANALYST,
        )

    # Verify member is added
    async with session_factory() as session:
        pm_added = (
            await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == target_user_id,
                )
            )
        ).scalar_one_or_none()
        assert pm_added is not None

    # 2. Test Rollback on remove_project_member
    async with session_factory() as session:
        tenancy = TenancyService(session)
        with patch.object(session, "commit", side_effect=RuntimeError("Simulated database failure during member removal")):
            with pytest.raises(RuntimeError) as exc_info:
                await tenancy.remove_project_member(
                    org_id=org_id,
                    project_id=project_id,
                    actor_id=actor_id,
                    target_user_id=target_user_id,
                )
            assert "Simulated database failure" in str(exc_info.value)
            await session.rollback()

    # Verify that in a fresh session: ProjectMember STILL exists, and PROJECT_MEMBER_REMOVED was NOT committed
    async with session_factory() as session:
        pm_still_there = (
            await session.execute(
                select(ProjectMember).where(
                    ProjectMember.project_id == project_id,
                    ProjectMember.user_id == target_user_id,
                )
            )
        ).scalar_one_or_none()
        assert pm_still_there is not None, "Rollback invariant: ProjectMember must still exist when removal fails"

        ev_removed = (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.project_id == project_id,
                    AuditEvent.action_type == "PROJECT_MEMBER_REMOVED",
                )
            )
        ).scalars().all()
        target_remove_events = [e for e in ev_removed if e.execution_context_json and e.execution_context_json.get("target_user_id") == str(target_user_id)]
        assert len(target_remove_events) == 0, "Rollback invariant: Removal audit event must not be committed when removal fails"


# ==============================================================================
# 10. Multi-Organization ROI Tenant Isolation Tests
# ==============================================================================


@pytest.mark.anyio
async def test_operational_roi_multi_organization_tenant_isolation(async_client: AsyncClient) -> None:
    """Verify that AuditService.get_operational_roi strictly isolates organization data.

    - Org A org-level ROI contains only Org A investigations and executions.
    - Org B org-level ROI contains only Org B investigations and executions.
    - Project-scoped ROI cannot calculate data for a project belonging to a different organization.
    """
    # 1. Setup Org A with Project A
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    org_a_id = uuid.UUID(org_a["id"])
    project_a_id = uuid.UUID(project_a["id"])

    # 2. Setup Org B with Project B
    _, _, org_b, project_b = await setup_test_org_and_project(async_client)
    org_b_id = uuid.UUID(org_b["id"])
    project_b_id = uuid.UUID(project_b["id"])

    session_factory = get_session_factory()

    # Populate Org A
    async with session_factory() as session:
        mon_a = Monitor(
            id=uuid.uuid4(),
            project_id=project_a_id,
            name="Org A Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(mon_a)
        await session.flush()

        finding_a = Finding(
            id=uuid.uuid4(),
            project_id=project_a_id,
            monitor_id=mon_a.id,
            entity_type="Invoice",
            entity_id="INV-ORG-A-1",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.RESOLVED.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=40),
            summary="Price variance in Org A",
        )
        session.add(finding_a)
        await session.flush()

        inv_a = Investigation(
            id=uuid.uuid4(),
            project_id=project_a_id,
            finding_id=finding_a.id,
            title="Investigation in Org A",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1000.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        session.add(inv_a)
        await session.flush()

        rec_a = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv_a.id,
            title="Rec in Org A",
            description="Rec Org A",
            confidence_score=0.9,
            recommended_action_type=ActionType.HOLD_INVOICE.value,
            suggested_payload_json={"hold": True},
            risk_level=RiskLevel.LOW.value,
        )
        session.add(rec_a)
        await session.flush()

        act_a = Action(
            id=uuid.uuid4(),
            project_id=project_a_id,
            recommendation_id=rec_a.id,
            action_type=ActionType.HOLD_INVOICE.value,
            proposed_payload_json={"hold": True},
            status=ActionStatus.EXECUTED.value,
        )
        session.add(act_a)
        await session.flush()

        appr_a = Approval(
            id=uuid.uuid4(),
            action_id=act_a.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"hold": True},
        )
        session.add(appr_a)
        await session.flush()

        exec_a = ActionExecution(
            id=uuid.uuid4(),
            action_id=act_a.id,
            approval_id=appr_a.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"hold": True},
            dispatched_payload_hash="hash_a",
            completed_at=finding_a.detected_at + timedelta(minutes=30),  # Duration 30 mins
        )
        session.add(exec_a)
        await session.commit()

    # Populate Org B
    async with session_factory() as session:
        mon_b = Monitor(
            id=uuid.uuid4(),
            project_id=project_b_id,
            name="Org B Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(mon_b)
        await session.flush()

        finding_b = Finding(
            id=uuid.uuid4(),
            project_id=project_b_id,
            monitor_id=mon_b.id,
            entity_type="Invoice",
            entity_id="INV-ORG-B-1",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.RESOLVED.value,
            deduplication_hash=f"dedup-{uuid.uuid4().hex[:12]}",
            detected_at=datetime.now(UTC) - timedelta(minutes=120),
            summary="Price variance in Org B",
        )
        session.add(finding_b)
        await session.flush()

        inv_b = Investigation(
            id=uuid.uuid4(),
            project_id=project_b_id,
            finding_id=finding_b.id,
            title="Investigation in Org B",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=5000.0,
            completed_at=datetime.now(UTC) - timedelta(minutes=30),
        )
        session.add(inv_b)
        await session.flush()

        rec_b = Recommendation(
            id=uuid.uuid4(),
            investigation_id=inv_b.id,
            title="Rec in Org B",
            description="Rec Org B",
            confidence_score=0.9,
            recommended_action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            suggested_payload_json={"amount": 5000.0},
            risk_level=RiskLevel.LOW.value,
        )
        session.add(rec_b)
        await session.flush()

        act_b = Action(
            id=uuid.uuid4(),
            project_id=project_b_id,
            recommendation_id=rec_b.id,
            action_type=ActionType.REQUEST_CREDIT_MEMO.value,
            proposed_payload_json={"amount": 5000.0},
            status=ActionStatus.EXECUTED.value,
        )
        session.add(act_b)
        await session.flush()

        appr_b = Approval(
            id=uuid.uuid4(),
            action_id=act_b.id,
            assigned_role="MANAGER",
            status=ApprovalStatus.APPROVED.value,
            approved_payload_json={"amount": 5000.0},
        )
        session.add(appr_b)
        await session.flush()

        exec_b = ActionExecution(
            id=uuid.uuid4(),
            action_id=act_b.id,
            approval_id=appr_b.id,
            idempotency_key=f"idemp-{uuid.uuid4().hex[:8]}",
            status=ExecutionStatus.SUCCEEDED.value,
            dispatched_payload_json={"amount": 5000.0},
            dispatched_payload_hash="hash_b",
            completed_at=finding_b.detected_at + timedelta(minutes=90),  # Duration 90 mins
        )
        session.add(exec_b)
        await session.commit()

    # 3. Test Org A organization-level ROI (project_id=None)
    async with session_factory() as session:
        audit_service = AuditService(session)
        roi_a = await audit_service.get_operational_roi(organization_id=org_a_id, project_id=None)
        assert roi_a.incidents_investigated == 1
        assert roi_a.incidents_resolved == 1
        assert roi_a.total_financial_impact_addressed_usd == 1000.0
        assert roi_a.current_mttr_minutes == 30.0

    # 4. Test Org B organization-level ROI (project_id=None)
    async with session_factory() as session:
        audit_service = AuditService(session)
        roi_b = await audit_service.get_operational_roi(organization_id=org_b_id, project_id=None)
        assert roi_b.incidents_investigated == 1
        assert roi_b.incidents_resolved == 1
        assert roi_b.total_financial_impact_addressed_usd == 5000.0
        assert roi_b.current_mttr_minutes == 90.0

    # 5. Test Cross-Tenant Project Lookup (Org A requesting Project B)
    # Project B belongs to Org B, so querying with organization_id=org_a_id and project_id=project_b_id MUST yield 0 records
    async with session_factory() as session:
        audit_service = AuditService(session)
        cross_roi = await audit_service.get_operational_roi(organization_id=org_a_id, project_id=project_b_id)
        assert cross_roi.incidents_investigated == 0
        assert cross_roi.incidents_resolved == 0
        assert cross_roi.total_financial_impact_addressed_usd == 0.0
        assert cross_roi.current_mttr_minutes == 0.0

    # 6. Test HTTP Endpoint Cross-Tenant Rejection
    headers_a = {"Authorization": f"Bearer {token_a}"}
    resp = await async_client.get(f"/api/v1/projects/{project_b_id}/governance/roi", headers=headers_a)
    assert resp.status_code in (403, 404), f"Expected 403 or 404 on cross-tenant ROI API, got {resp.status_code}"


# ==============================================================================
# 11. Missing-Finding Deduplication Fallback Tests
# ==============================================================================


@pytest.mark.anyio
async def test_operational_roi_missing_finding_deduplication(async_client: AsyncClient) -> None:
    """Verify deduplication when Investigation.finding_id is null / finding is None.

    Ensures that unrelated investigations without findings are not collapsed into one,
    while duplicate executions for the SAME investigation are properly deduplicated.
    """
    _, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()

    async with session_factory() as session:
        audit_service = AuditService(session)

        # Create two distinct investigations where finding is None and finding_id is None
        # We simulate the exact join result tuple: (ActionExecution, Investigation, Finding)
        inv1 = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=None,  # type: ignore[arg-type]
            title="Investigation 1 without finding",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1200.0,
            created_at=datetime.now(UTC) - timedelta(minutes=45),
            completed_at=datetime.now(UTC) - timedelta(minutes=15),
        )

        inv2 = Investigation(
            id=uuid.uuid4(),
            project_id=project_id,
            finding_id=None,  # type: ignore[arg-type]
            title="Investigation 2 without finding",
            status=InvestigationStatus.COMPLETED.value,
            financial_impact_usd=1800.0,
            created_at=datetime.now(UTC) - timedelta(minutes=30),
            completed_at=datetime.now(UTC) - timedelta(minutes=5),
        )

        # Executions:
        # exec1_earlier for inv1 (completed 30m after inv1.created_at -> duration 30m)
        exec1_earlier = ActionExecution(
            id=uuid.uuid4(),
            action_id=uuid.uuid4(),
            approval_id=uuid.uuid4(),
            idempotency_key="idemp-1a",
            status=ExecutionStatus.SUCCEEDED.value,
            completed_at=inv1.created_at + timedelta(minutes=30),
        )
        # exec1_later for inv1 (completed 40m after inv1.created_at -> duplicate for same inv1!)
        exec1_later = ActionExecution(
            id=uuid.uuid4(),
            action_id=uuid.uuid4(),
            approval_id=uuid.uuid4(),
            idempotency_key="idemp-1b",
            status=ExecutionStatus.SUCCEEDED.value,
            completed_at=inv1.created_at + timedelta(minutes=40),
        )
        # exec2 for inv2 (completed 20m after inv2.created_at -> duration 20m)
        exec2 = ActionExecution(
            id=uuid.uuid4(),
            action_id=uuid.uuid4(),
            approval_id=uuid.uuid4(),
            idempotency_key="idemp-2",
            status=ExecutionStatus.SUCCEEDED.value,
            completed_at=inv2.created_at + timedelta(minutes=20),
        )

        mock_inv_rows = [inv1, inv2]
        mock_exec_results = [
            (exec1_earlier, inv1, None),
            (exec1_later, inv1, None),
            (exec2, inv2, None),
        ]

        mock_inv_res = MagicMock()
        mock_inv_res.scalars.return_value.all.return_value = mock_inv_rows

        mock_exec_res = MagicMock()
        mock_exec_res.all.return_value = mock_exec_results

        mock_cost_res = MagicMock()
        mock_cost_res.all.return_value = []

        with patch.object(session, "execute", side_effect=[mock_inv_res, mock_exec_res, mock_cost_res]):
            roi = await audit_service.get_operational_roi(organization_id=org_id, project_id=project_id)

            # Both distinct investigations without finding MUST be counted
            assert roi.incidents_resolved == 2, f"Expected 2 incidents resolved, got {roi.incidents_resolved}"
            # Duplicate execution for inv1 is deduplicated: 1200 + 1800 = 3000.0 (NOT 1200 + 1200 + 1800)
            assert roi.total_financial_impact_addressed_usd == 3000.0
            # Durations: 30m for inv1 (from earlier execution) and 20m for inv2 -> average 25.0m
            assert roi.current_mttr_minutes == 25.0
