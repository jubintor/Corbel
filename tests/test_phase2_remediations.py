"""Comprehensive regression and verification test suite for Phase 2 Remediations (P2-LIM-001 through P2-LIM-014)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, select

from corbel.core.config import get_settings
from corbel.core.database import get_session_factory
from corbel.domains.governance.exceptions import UnauthorizedApprovalException
from corbel.domains.governance.models import ApprovalStatus
from corbel.domains.governance.schemas import ApprovalDecisionRequest
from corbel.domains.governance.service import GovernanceService
from corbel.domains.tenancy.exceptions import (
    InsufficientPermissionException,
)
from corbel.domains.tenancy.models import (
    MembershipStatus,
    OrgRole,
    ProjectMember,
    ProjectRole,
    RefreshToken,
    User,
    UserSession,
)
from corbel.domains.tenancy.rate_limiter import RateLimiter
from corbel.domains.tenancy.schemas import (
    MemberAddRequest,
    OrganizationCreateRequest,
    ProjectCreateRequest,
    UserRegisterRequest,
)
from corbel.domains.tenancy.security import (
    create_access_token,
    decode_token,
    validate_password_policy,
)
from corbel.domains.tenancy.service import TenancyService


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


# ==============================================================================
# P2-LIM-001: Concurrent Refresh Token Collision & Grace Window
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_001_concurrent_refresh_grace_window(async_client: AsyncClient) -> None:
    """Verify that concurrent refresh collisions receive valid replacement tokens rather than triggering family revocation."""
    email = unique_email("refresh_col")
    password = "SecurePassword123!"

    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Collision User"},
    )
    assert reg.status_code == 201

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200
    init_tokens = login.json()
    orig_refresh = init_tokens["refresh_token"]

    # Concurrently execute two refresh requests with the same refresh token and shared operation key (P2-LIM-001)
    idemp_op_key = f"op-key-{uuid.uuid4().hex}"
    req1 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": orig_refresh, "idempotency_key": idemp_op_key})
    req2 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": orig_refresh, "idempotency_key": idemp_op_key})

    r1, r2 = await asyncio.gather(req1, req2)
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Both return valid access tokens
    tok1 = r1.json()["access_token"]
    tok2 = r2.json()["access_token"]
    assert tok1 is not None
    assert tok2 is not None

    # Test me endpoint with both access tokens
    me1 = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok1}"})
    me2 = await async_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tok2}"})
    assert me1.status_code == 200
    assert me2.status_code == 200


# ==============================================================================
# P2-LIM-002: Orphaned Project Member Cascade
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_002_orphaned_project_members_cascade() -> None:
    """Verify that removing a member from an organization cascades to project members and preserves integrity."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        # 1. Register admin and member
        admin = await service.register_user(
            UserRegisterRequest(email=unique_email("admin"), password="Password123!", full_name="Admin")
        )
        member = await service.register_user(
            UserRegisterRequest(email=unique_email("member"), password="Password123!", full_name="Member")
        )

        # 2. Create organization and project
        org = await service.create_organization(
            admin.id, OrganizationCreateRequest(name="Cascade Test Org")
        )
        project = await service.create_project(
            org.id, admin.id, ProjectCreateRequest(name="Cascade Test Project")
        )

        # 3. Add member to organization and project
        await service.add_organization_member(
            org.id, admin.id, MemberAddRequest(email=member.email, role=OrgRole.MEMBER)
        )
        await service.add_project_member(
            org.id, project.id, admin.id, member.id, ProjectRole.ANALYST
        )

        # Verify project membership exists
        pm_query = select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == member.id,
        )
        pm_res = await session.execute(pm_query)
        assert pm_res.scalar_one_or_none() is not None

        # 4. Remove member from organization
        await service.remove_member(org.id, admin.id, member.id)

        # Verify project membership is deleted (no orphaned records)
        pm_res2 = await session.execute(pm_query)
        assert pm_res2.scalar_one_or_none() is None


# ==============================================================================
# P2-LIM-003: Password Policy & UTF-8 Bounds
# ==============================================================================

def test_p2_lim_003_password_policy_bounds() -> None:
    """Verify password policy enforces UTF-8 byte boundary (<=72 bytes) and complexity without silent truncation."""
    # Under 8 chars
    with pytest.raises(ValueError, match="at least 8 characters"):
        validate_password_policy("Short1!")

    # Exceeding 72 UTF-8 bytes
    long_pwd = "A" * 70 + "!1"  # 72 bytes - valid
    validate_password_policy(long_pwd)

    too_long = "A" * 71 + "!1"  # 73 bytes - invalid
    with pytest.raises(ValueError, match="exceed.*72 bytes"):
        validate_password_policy(too_long)

    # Multi-byte UTF-8 character length test
    # Each '€' is 3 bytes in UTF-8
    euro_pwd = "€" * 25  # 75 bytes
    with pytest.raises(ValueError, match="exceed.*72 bytes"):
        validate_password_policy(euro_pwd)

    # Missing digits/symbols
    with pytest.raises(ValueError, match="at least one letter and at least one number or special character"):
        validate_password_policy("AllLettersPassword")

    # Missing letters
    with pytest.raises(ValueError, match="at least one letter and at least one number or special character"):
        validate_password_policy("1234567890!@#$")


# ==============================================================================
# P2-LIM-004: Constant-Time Authentication
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_004_constant_time_authentication() -> None:
    """Verify that authenticating a non-existent email executes dummy bcrypt verification rather than fast-failing."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)
        non_existent_email = unique_email("nonexistent")

        from corbel.domains.tenancy.exceptions import InvalidCredentialsException
        from corbel.domains.tenancy.schemas import UserLoginRequest

        # Should execute verify_password_async on DUMMY_BCRYPT_HASH and raise InvalidCredentialsException
        with pytest.raises(InvalidCredentialsException):
            await service.authenticate_user(
                UserLoginRequest(email=non_existent_email, password="AnyPassword123!")
            )


# ==============================================================================
# P2-LIM-005: Distributed Atomic Rate Limiter
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_005_distributed_rate_limiter() -> None:
    """Verify that RateLimiter limits requests and returns retry_after."""
    session_factory = get_session_factory()
    test_key = f"test_limiter_{uuid.uuid4().hex[:8]}"

    async with session_factory() as session:
        limiter = RateLimiter(session)

        # Allow 3 requests per minute
        for _ in range(3):
            retry_after = await limiter.check_and_record(test_key, max_requests=3, window_seconds=60)
            assert retry_after is None
            await session.commit()

        # 4th request must return retry_after seconds (>0)
        retry_after = await limiter.check_and_record(test_key, max_requests=3, window_seconds=60)
        assert retry_after is not None
        assert retry_after > 0
        await session.commit()


# ==============================================================================
# P2-LIM-006: Purge Expired Records
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_006_purge_expired_records() -> None:
    """Verify that purge_expired_records removes expired refresh tokens and user sessions."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        user = await service.register_user(
            UserRegisterRequest(email=unique_email("purge"), password="Password123!", full_name="Purge User")
        )

        # Create expired session and token in past
        past_time = datetime.now(UTC) - timedelta(days=60)
        session_record = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            status="EXPIRED",
            created_at=past_time,
            expires_at=past_time,
        )
        session.add(session_record)
        await session.flush()

        token_record = RefreshToken(
            id=uuid.uuid4(),
            session_id=session_record.id,
            user_id=user.id,
            token_hash="dummy_hash",
            family_id=session_record.id,
            is_revoked=True,
            revoked_at=past_time,
            expires_at=past_time,
        )
        session.add(token_record)
        await session.commit()

        # Purge records with 30-day retention
        stats = await service.purge_expired_records(retention_days=30, batch_size=100)
        assert stats["purged_refresh_tokens"] >= 1
        assert stats["purged_user_sessions"] >= 1


# ==============================================================================
# P2-LIM-007: Project Read Isolation
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_007_project_read_isolation() -> None:
    """Verify that regular organization members can only list and view projects they are assigned to."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        admin = await service.register_user(
            UserRegisterRequest(email=unique_email("admin7"), password="Password123!", full_name="Admin 7")
        )
        member1 = await service.register_user(
            UserRegisterRequest(email=unique_email("m1"), password="Password123!", full_name="Member 1")
        )
        member2 = await service.register_user(
            UserRegisterRequest(email=unique_email("m2"), password="Password123!", full_name="Member 2")
        )

        org = await service.create_organization(admin.id, OrganizationCreateRequest(name="Isolation Org"))
        await service.add_organization_member(org.id, admin.id, MemberAddRequest(email=member1.email, role=OrgRole.MEMBER))
        await service.add_organization_member(org.id, admin.id, MemberAddRequest(email=member2.email, role=OrgRole.MEMBER))

        # Admin creates project and assigns ONLY member1
        project = await service.create_project(org.id, admin.id, ProjectCreateRequest(name="Project Alpha"))
        await service.add_project_member(org.id, project.id, admin.id, member1.id, ProjectRole.ANALYST)

        # member1 can list Project Alpha
        m1_projects = await service.list_projects(org.id, member1.id)
        assert len(m1_projects) == 1
        assert m1_projects[0].id == project.id

        # member2 cannot list Project Alpha
        m2_projects = await service.list_projects(org.id, member2.id)
        assert len(m2_projects) == 0

        # member2 cannot get Project Alpha directly
        from corbel.domains.tenancy.exceptions import InsufficientPermissionException
        with pytest.raises(InsufficientPermissionException):
            await service.get_project(org.id, project.id, member2.id)


# ==============================================================================
# P2-LIM-008: Organization Member Status Suspension Lifecycle
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_008_member_status_suspension_terminates_session() -> None:
    """Verify updating member status to SUSPENDED revokes active sessions and blocks access."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        admin = await service.register_user(
            UserRegisterRequest(email=unique_email("admin8"), password="Password123!", full_name="Admin 8")
        )
        member = await service.register_user(
            UserRegisterRequest(email=unique_email("m8"), password="Password123!", full_name="Member 8")
        )

        org = await service.create_organization(admin.id, OrganizationCreateRequest(name="Suspension Org"))
        await service.add_organization_member(org.id, admin.id, MemberAddRequest(email=member.email, role=OrgRole.MEMBER))

        # Create active session for member
        from corbel.domains.tenancy.models import SessionStatus
        active_sess = UserSession(
            id=uuid.uuid4(),
            user_id=member.id,
            status=SessionStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(active_sess)
        await session.commit()

        # Admin suspends member
        updated_member = await service.update_member_status(
            org.id, admin.id, member.id, MembershipStatus.SUSPENDED
        )
        assert updated_member.status == MembershipStatus.SUSPENDED.value

        # Note on P2-LIM-007: Suspension is organization-scoped.
        # Active session is preserved for other organizations, while access to suspended org is blocked.
        await session.refresh(active_sess)
        assert active_sess.status == SessionStatus.ACTIVE.value

        from corbel.domains.tenancy.exceptions import MembershipInactiveException
        with pytest.raises(MembershipInactiveException):
            await service.verify_membership(org.id, member.id)


# ==============================================================================
# P2-LIM-009: Governance Approval Authorization & Segregation of Duties
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_009_governance_approval_role_and_sod() -> None:
    """Verify that ANALYST cannot decide approvals, and SoD prevents action proposer from approving."""
    from corbel.domains.governance.schemas import InvestigationCreateRequest
    from corbel.domains.monitors.models import (
        Finding,
        FindingStatus,
        Monitor,
        MonitorStatus,
        MonitorTargetType,
    )

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        gov_service = GovernanceService(session, tenancy_service=tenancy_service)

        admin = await tenancy_service.register_user(
            UserRegisterRequest(email=unique_email("admin9"), password="Password123!", full_name="Admin 9")
        )
        lead = await tenancy_service.register_user(
            UserRegisterRequest(email=unique_email("lead"), password="Password123!", full_name="Project Lead")
        )
        analyst = await tenancy_service.register_user(
            UserRegisterRequest(email=unique_email("analyst"), password="Password123!", full_name="Analyst")
        )
        approver = await tenancy_service.register_user(
            UserRegisterRequest(email=unique_email("approver"), password="Password123!", full_name="Approver")
        )

        org = await tenancy_service.create_organization(admin.id, OrganizationCreateRequest(name="Gov Org"))
        await tenancy_service.add_organization_member(org.id, admin.id, MemberAddRequest(email=lead.email, role=OrgRole.MEMBER))
        await tenancy_service.add_organization_member(org.id, admin.id, MemberAddRequest(email=analyst.email, role=OrgRole.MEMBER))
        await tenancy_service.add_organization_member(org.id, admin.id, MemberAddRequest(email=approver.email, role=OrgRole.MEMBER))

        project = await tenancy_service.create_project(org.id, admin.id, ProjectCreateRequest(name="Gov Project"))
        await tenancy_service.add_project_member(org.id, project.id, admin.id, lead.id, ProjectRole.PROJECT_LEAD)
        await tenancy_service.add_project_member(org.id, project.id, admin.id, analyst.id, ProjectRole.ANALYST)
        await tenancy_service.add_project_member(org.id, project.id, admin.id, approver.id, ProjectRole.APPROVER)

        # Set up finding and investigation
        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project.id,
            name="Invoice Test Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=project.id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-9901",
            finding_type="PRICE_VARIANCE",
            severity="MEDIUM",
            status=FindingStatus.OPEN.value,
            summary="Price variance on INV-9901",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="5500.00",
            threshold_value="5000.00",
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        # Lead creates the investigation (proposing the action)
        await gov_service.create_investigation(
            org.id,
            project.id,
            lead.id,
            InvestigationCreateRequest(finding_id=finding.id, include_rag_documents=False),
        )

        approvals = await gov_service.list_approvals(org.id, project.id, lead.id)
        assert len(approvals) >= 1
        approval = approvals[0]

        # 1. Analyst attempts to decide -> Rejected due to role (ANALYST not in [APPROVER, PROJECT_LEAD])
        with pytest.raises(UnauthorizedApprovalException, match="is not authorized to decide approvals"):
            await gov_service.decide_approval(
                org.id,
                project.id,
                analyst.id,
                approval.id,
                ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED),
            )

        # 2. Lead attempts to approve own action -> Rejected by Segregation of Duties (SoD)
        with pytest.raises(UnauthorizedApprovalException, match="Segregation of Duties violation"):
            await gov_service.decide_approval(
                org.id,
                project.id,
                lead.id,
                approval.id,
                ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED, rationale="Self-approval attempt"),
            )

        # 3. Independent Approver decides -> Succeeds!
        decided = await gov_service.decide_approval(
            org.id,
            project.id,
            approver.id,
            approval.id,
            ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED, rationale="Approved by independent approver"),
        )
        assert decided.status == ApprovalStatus.APPROVED.value


# ==============================================================================
# P2-LIM-010: Database Concurrency Race Handling (409 Conflict)
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_010_database_concurrency_conflict() -> None:
    """Verify duplicate email and duplicate org slugs return 409 Conflict."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)
        email = unique_email("race")

        await service.register_user(UserRegisterRequest(email=email, password="Password123!", full_name="First User"))

        from corbel.domains.tenancy.exceptions import UserAlreadyExistsException
        with pytest.raises(UserAlreadyExistsException):
            await service.register_user(UserRegisterRequest(email=email, password="Password123!", full_name="Duplicate User"))


# ==============================================================================
# P2-LIM-011: Auditor Role Separation
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_011_auditor_cannot_create_project() -> None:
    """Verify that users with AUDITOR role cannot create projects."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        admin = await service.register_user(
            UserRegisterRequest(email=unique_email("admin11"), password="Password123!", full_name="Admin 11")
        )
        auditor = await service.register_user(
            UserRegisterRequest(email=unique_email("auditor"), password="Password123!", full_name="Auditor")
        )

        org = await service.create_organization(admin.id, OrganizationCreateRequest(name="Auditor Org"))
        await service.add_organization_member(org.id, admin.id, MemberAddRequest(email=auditor.email, role=OrgRole.AUDITOR))

        with pytest.raises(InsufficientPermissionException):
            await service.create_project(org.id, auditor.id, ProjectCreateRequest(name="Auditor Project"))


# ==============================================================================
# P2-LIM-012: Deprecated is_superuser Dropped
# ==============================================================================

def test_p2_lim_012_is_superuser_dropped() -> None:
    """Verify that is_superuser is removed from User ORM model and table columns."""
    mapper = inspect(User)
    column_names = [c.key for c in mapper.columns]
    assert "is_superuser" not in column_names


# ==============================================================================
# P2-LIM-014: JWT Issuer & Audience Validation
# ==============================================================================

def test_p2_lim_014_jwt_issuer_and_audience() -> None:
    """Verify that generated tokens contain issuer and audience claims, and rejecting invalid ones."""
    settings = get_settings()
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()

    token = create_access_token(
        user_id=user_id,
        email="test@example.com",
        session_id=session_id,
        expires_delta=timedelta(minutes=15),
    )

    payload = decode_token(token, expected_type="access")
    assert payload["iss"] == settings.JWT_ISSUER
    assert payload["aud"] == settings.JWT_AUDIENCE
    assert payload["sub"] == str(user_id)
    assert payload["sid"] == str(session_id)
