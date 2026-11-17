"""Comprehensive tests for Phase 2 Security and Maintenance Remediations:
- P2-LIM-001: Refresh-token replacement theft & idempotency protocol
- P2-LIM-004: Account-lockout denial of service prevention
- P2-LIM-007: Cross-organization session revocation scoping
- P2-LIM-006: Bounded cleanup and zero Mypy errors
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.tenancy.exceptions import (
    InvalidCredentialsException,
    MembershipInactiveException,
)
from corbel.domains.tenancy.models import (
    MembershipStatus,
    OrgRole,
    RateLimitBucket,
    RefreshToken,
    SessionStatus,
    UserSession,
)
from corbel.domains.tenancy.schemas import (
    MemberAddRequest,
    OrganizationCreateRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from corbel.domains.tenancy.security import get_client_ip
from corbel.domains.tenancy.service import TenancyService


def unique_email(prefix: str = "sec") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


# ==============================================================================
# P2-LIM-001: Refresh-Token Replacement Theft & Idempotency Protocol
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_001_idempotent_refresh_success_and_retry(async_client: AsyncClient) -> None:
    """Verify legitimate refresh succeeds and retry with SAME idempotency key returns replacement."""
    email = unique_email("idem_ok")
    password = "Password123!"

    reg = await async_client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Idem User"})
    assert reg.status_code == 201

    login = await async_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    orig_refresh = login.json()["refresh_token"]

    idemp_key = f"idemp-client-key-{uuid.uuid4().hex}"

    # 1. Initial refresh with client idempotency key
    res1 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh, "idempotency_key": idemp_key},
    )
    assert res1.status_code == 200
    first_replacement = res1.json()["refresh_token"]
    assert first_replacement != orig_refresh

    # 2. Lost-response retry with SAME idempotency key within grace window
    res2 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh, "idempotency_key": idemp_key},
    )
    assert res2.status_code == 200
    assert res2.json()["refresh_token"] == first_replacement

    # 3. Access token from retry is fully valid
    me = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {res2.json()['access_token']}"},
    )
    assert me.status_code == 200


@pytest.mark.anyio
async def test_p2_lim_001_retry_with_different_or_missing_key_rejected(async_client: AsyncClient) -> None:
    """Verify attacker presenting old refresh token with different or missing key is rejected and revoked."""
    email = unique_email("idem_theft")
    password = "Password123!"

    await async_client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Theft Victim"})
    login = await async_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    orig_refresh = login.json()["refresh_token"]

    legit_key = f"legit-key-{uuid.uuid4().hex}"

    # Legitimate client rotates token
    res1 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh, "idempotency_key": legit_key},
    )
    assert res1.status_code == 200
    new_refresh = res1.json()["refresh_token"]

    # 1. Attacker tries to replay old token with NO idempotency key -> MUST FAIL 401
    steal_no_key = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh},
    )
    assert steal_no_key.status_code == 401

    # Because replay was detected, entire family must be revoked!
    # Even newly issued token must now be invalid
    victim_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh, "idempotency_key": f"key-{uuid.uuid4().hex}"},
    )
    assert victim_refresh.status_code == 401


@pytest.mark.anyio
async def test_p2_lim_001_attacker_different_key_revokes_family(async_client: AsyncClient) -> None:
    """Verify attacker trying a different idempotency key cannot obtain replacement and revokes family."""
    email = unique_email("diff_key")
    password = "Password123!"

    await async_client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "User Diff"})
    login = await async_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    orig_refresh = login.json()["refresh_token"]

    legit_key = f"legit-key-{uuid.uuid4().hex}"
    attacker_key = f"attacker-diff-{uuid.uuid4().hex}"

    res1 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh, "idempotency_key": legit_key},
    )
    assert res1.status_code == 200

    # Attacker tries with different idempotency key
    steal_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": orig_refresh, "idempotency_key": attacker_key},
    )
    assert steal_res.status_code == 401
    assert "mismatched idempotency key" in steal_res.json()["message"]


@pytest.mark.anyio
async def test_p2_lim_001_concurrent_refresh_different_keys_conflict(async_client: AsyncClient) -> None:
    """Verify concurrent requests with different idempotency keys cannot both obtain valid replacements."""
    email = unique_email("concurrent_diff")
    password = "Password123!"

    await async_client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "User Conc"})
    login = await async_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    orig_refresh = login.json()["refresh_token"]

    key1 = f"key-1-{uuid.uuid4().hex}"
    key2 = f"key-2-{uuid.uuid4().hex}"

    # Run two concurrent requests with DIFFERENT keys
    req1 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": orig_refresh, "idempotency_key": key1})
    req2 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": orig_refresh, "idempotency_key": key2})

    r1, r2 = await asyncio.gather(req1, req2)
    statuses = [r1.status_code, r2.status_code]
    # Exactly one may succeed and the other must be rejected (401)
    assert 200 in statuses
    assert 401 in statuses


# ==============================================================================
# P2-LIM-004: Account-Lockout Denial of Service Prevention
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_004_attacker_cannot_lock_victim_from_different_ip() -> None:
    """Verify attacker failing 5 times against victim's email from IP A does not lock victim from IP B."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)
        from corbel.core.config import get_settings
        settings = get_settings()
        orig_threshold = settings.RATE_LIMIT_LOGIN_FAILURES_LOCKOUT
        settings.RATE_LIMIT_LOGIN_FAILURES_LOCKOUT = 5

        try:
            email = unique_email("victim_dos")
            password = "CorrectPassword123!"

            await service.register_user(UserRegisterRequest(email=email, password=password, full_name="Victim User"))

            attacker_ip = "198.51.100.55"
            victim_ip = "203.0.113.10"

            # Attacker fails 5 times from attacker_ip
            for _ in range(5):
                with pytest.raises(InvalidCredentialsException):
                    await service.authenticate_user(
                        UserLoginRequest(email=email, password="WrongPassword!"),
                        ip_address=attacker_ip,
                    )

            # Attacker IP is now locked out for this account
            from corbel.domains.tenancy.rate_limiter import RateLimitExceededException
            with pytest.raises(RateLimitExceededException):
                await service.authenticate_user(
                    UserLoginRequest(email=email, password="WrongPassword!"),
                    ip_address=attacker_ip,
                )

            # Legitimate victim from victim_ip can still log in successfully!
            victim_tokens = await service.authenticate_user(
                UserLoginRequest(email=email, password=password),
                ip_address=victim_ip,
            )
            assert victim_tokens.access_token is not None
        finally:
            settings.RATE_LIMIT_LOGIN_FAILURES_LOCKOUT = orig_threshold


@pytest.mark.anyio
async def test_p2_lim_004_trusted_proxy_forwarded_for_resolution() -> None:
    """Verify spoofed X-Forwarded-For headers from untrusted clients are not trusted."""
    class MockClient:
        host = "203.0.113.50"  # Untrusted external IP

    class MockRequest:
        client = MockClient()
        headers = {"x-forwarded-for": "10.0.0.1, 1.2.3.4"}

    # Untrusted proxy connection: ignores header and returns actual direct client host
    resolved_ip = get_client_ip(MockRequest(), trusted_proxies=["127.0.0.1", "::1"])
    assert resolved_ip == "203.0.113.50"

    # Trusted proxy connection (e.g. localhost reverse proxy): returns rightmost untrusted IP
    class TrustedMockClient:
        host = "127.0.0.1"

    class TrustedMockRequest:
        client = TrustedMockClient()
        headers = {"x-forwarded-for": "203.0.113.99, 127.0.0.1"}

    resolved_trusted = get_client_ip(TrustedMockRequest(), trusted_proxies=["127.0.0.1", "::1"])
    assert resolved_trusted == "203.0.113.99"


@pytest.mark.anyio
async def test_p2_lim_004_successful_login_resets_failure_counter() -> None:
    """Verify successful authentication resets failure counter for the (account, IP) dimension."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        email = unique_email("reset_cnt")
        password = "GoodPassword123!"
        ip = "192.0.2.77"

        await service.register_user(UserRegisterRequest(email=email, password=password, full_name="Reset User"))

        # 3 failures (below lockout threshold of 5)
        for _ in range(3):
            with pytest.raises(InvalidCredentialsException):
                await service.authenticate_user(UserLoginRequest(email=email, password="BadPassword!"), ip_address=ip)

        # Successful login resets the counter
        tokens = await service.authenticate_user(UserLoginRequest(email=email, password=password), ip_address=ip)
        assert tokens.access_token is not None

        # Another 3 failures do NOT trigger lockout because counter was reset
        for _ in range(3):
            with pytest.raises(InvalidCredentialsException):
                await service.authenticate_user(UserLoginRequest(email=email, password="BadPassword!"), ip_address=ip)


# ==============================================================================
# P2-LIM-007: Cross-Organization Session Revocation Scoping
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_007_cross_org_suspension_isolation() -> None:
    """Verify suspending user in Org A denies Org A access immediately while preserving Org B access and session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        admin_a = await service.register_user(UserRegisterRequest(email=unique_email("admin_a"), password="Password123!", full_name="Admin A"))
        admin_b = await service.register_user(UserRegisterRequest(email=unique_email("admin_b"), password="Password123!", full_name="Admin B"))
        shared_user = await service.register_user(UserRegisterRequest(email=unique_email("shared"), password="Password123!", full_name="Shared User"))

        org_a = await service.create_organization(admin_a.id, OrganizationCreateRequest(name="Organization A"))
        org_b = await service.create_organization(admin_b.id, OrganizationCreateRequest(name="Organization B"))

        # Add shared_user to both organizations
        await service.add_organization_member(org_a.id, admin_a.id, MemberAddRequest(email=shared_user.email, role=OrgRole.MEMBER))
        await service.add_organization_member(org_b.id, admin_b.id, MemberAddRequest(email=shared_user.email, role=OrgRole.MEMBER))

        # Shared user logs in and obtains active session
        login_tokens = await service.authenticate_user(
            UserLoginRequest(email=shared_user.email, password="Password123!"),
            ip_address="127.0.0.1",
        )
        assert login_tokens.access_token is not None

        # Shared user can access both orgs initially
        m_a = await service.verify_membership(org_a.id, shared_user.id)
        assert m_a.status == MembershipStatus.ACTIVE.value
        m_b = await service.verify_membership(org_b.id, shared_user.id)
        assert m_b.status == MembershipStatus.ACTIVE.value

        # Admin of Org A suspends shared_user in Org A
        updated_member = await service.update_member_status(
            org_a.id,
            admin_a.id,
            shared_user.id,
            MembershipStatus.SUSPENDED,
        )
        assert updated_member.status == MembershipStatus.SUSPENDED.value

        # 1. Access to Org A is immediately rejected
        with pytest.raises(MembershipInactiveException):
            await service.verify_membership(org_a.id, shared_user.id)

        # 2. Access to Org B continues to work!
        m_b_still_active = await service.verify_membership(org_b.id, shared_user.id)
        assert m_b_still_active.status == MembershipStatus.ACTIVE.value

        # 3. Refreshing tokens succeeds and preserves Org B access
        refreshed = await service.refresh_access_token(
            login_tokens.refresh_token,
            idempotency_key=f"refresh-{uuid.uuid4().hex}",
        )
        assert refreshed.access_token is not None

        # Still blocked from Org A after refresh
        with pytest.raises(MembershipInactiveException):
            await service.verify_membership(org_a.id, shared_user.id)

        # Still active in Org B
        assert (await service.verify_membership(org_b.id, shared_user.id)).status == MembershipStatus.ACTIVE.value


# ==============================================================================
# P2-LIM-006: Bounded Cleanup and Retention
# ==============================================================================

@pytest.mark.anyio
async def test_p2_lim_006_bounded_batch_cleanup() -> None:
    """Verify purge_expired_records operates in bounded batches and prunes expired tokens, sessions, and buckets."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        service = TenancyService(session)

        user = await service.register_user(UserRegisterRequest(email=unique_email("batch_purge"), password="Password123!", full_name="Batch Purge User"))

        past_60_days = datetime.now(UTC) - timedelta(days=60)

        # Create 5 expired sessions and 5 expired refresh tokens
        for _ in range(5):
            sess = UserSession(
                id=uuid.uuid4(),
                user_id=user.id,
                status=SessionStatus.EXPIRED.value,
                created_at=past_60_days,
                expires_at=past_60_days,
            )
            session.add(sess)

            tok = RefreshToken(
                id=uuid.uuid4(),
                session_id=sess.id,
                user_id=user.id,
                token_hash=uuid.uuid4().hex,
                family_id=sess.id,
                is_revoked=True,
                revoked_at=past_60_days,
                expires_at=past_60_days,
            )
            session.add(tok)

        # Create expired rate limit bucket
        bucket = RateLimitBucket(
            key=f"expired_bucket_{uuid.uuid4().hex}",
            tokens=5,
            last_updated=past_60_days,
            blocked_until=past_60_days,
        )
        session.add(bucket)
        await session.commit()

        # Run bounded cleanup with batch_size=2
        stats = await service.purge_expired_records(retention_days=30, batch_size=2, max_batches=10)
        assert stats["purged_refresh_tokens"] >= 5
        assert stats["purged_user_sessions"] >= 5
        assert stats["purged_rate_limit_buckets"] >= 1

        # Re-running cleanup should be safe and idempotent
        stats2 = await service.purge_expired_records(retention_days=30, batch_size=2)
        assert stats2["purged_refresh_tokens"] == 0
        assert stats2["purged_user_sessions"] == 0
