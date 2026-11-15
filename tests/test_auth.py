"""Tests for authentication endpoints and token mechanics."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient


def unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


@pytest.mark.anyio
async def test_register_user_success(async_client: AsyncClient) -> None:
    email = unique_email()
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == email
    assert data["full_name"] == "Test User"
    assert data["is_active"] is True
    assert "id" in data
    assert "hashed_password" not in data
    assert "password" not in data


@pytest.mark.anyio
async def test_register_duplicate_email_fails(async_client: AsyncClient) -> None:
    email = unique_email()
    payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "Initial User",
    }
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    error_data = res2.json()
    assert error_data["error"] == "USER_ALREADY_EXISTS"


@pytest.mark.anyio
async def test_register_short_password_fails(async_client: AsyncClient) -> None:
    email = unique_email()
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "short",
            "full_name": "Short Password User",
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_login_valid_credentials(async_client: AsyncClient) -> None:
    email = unique_email()
    password = "CorrectPassword123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Login User"},
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0


@pytest.mark.anyio
async def test_login_invalid_password_fails(async_client: AsyncClient) -> None:
    email = unique_email()
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "User"},
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.anyio
async def test_login_nonexistent_email_fails(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent_user@example.com", "password": "Password123!"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "INVALID_CREDENTIALS"


@pytest.mark.anyio
async def test_refresh_token_lifecycle(async_client: AsyncClient) -> None:
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Refresh User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    tokens = login_res.json()
    refresh_token = tokens["refresh_token"]

    # Refresh tokens
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["token_type"] == "bearer"


@pytest.mark.anyio
async def test_refresh_token_reuse_detection_fails(async_client: AsyncClient) -> None:
    """Verify that reusing an old refresh token returns 401 and revokes descendant tokens."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Reuse Test User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    tokens = login_res.json()
    old_refresh_token = tokens["refresh_token"]

    # First refresh: succeeds and rotates token
    first_refresh = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert first_refresh.status_code == 200
    rotated_tokens = first_refresh.json()
    new_refresh_token = rotated_tokens["refresh_token"]

    # Second refresh using OLD token: MUST FAIL WITH 401 (token reuse detected)
    reuse_attempt = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )
    assert reuse_attempt.status_code == 401
    assert reuse_attempt.json()["error"] == "INVALID_CREDENTIALS"
    assert "reuse detected" in reuse_attempt.json()["message"]

    # Replay attack invalidation: descendant tokens in the family are also revoked
    descendant_attempt = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert descendant_attempt.status_code == 401


@pytest.mark.anyio
async def test_refresh_token_with_invalid_token_fails(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.jwt.token"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_me(async_client: AsyncClient) -> None:
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Me User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    access_token = login_res.json()["access_token"]

    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == email
    assert me_data["full_name"] == "Me User"
    assert "hashed_password" not in me_data


@pytest.mark.anyio
async def test_get_current_user_unauthorized(async_client: AsyncClient) -> None:
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_logout_endpoint(async_client: AsyncClient) -> None:
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Logout User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    access_token = login_res.json()["access_token"]

    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_res.status_code == 200
    assert "successfully" in logout_res.json()["message"]


@pytest.mark.anyio
async def test_replacement_refresh_token_succeeds(async_client: AsyncClient) -> None:
    """Verify that successive refresh rotations proceed seamlessly."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Successive User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token1 = login_res.json()["refresh_token"]

    # Rotation 1 -> 2
    res1 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert res1.status_code == 200
    token2 = res1.json()["refresh_token"]

    # Rotation 2 -> 3
    res2 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert res2.status_code == 200
    token3 = res2.json()["refresh_token"]

    # Rotation 3 -> 4
    res3 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token3})
    assert res3.status_code == 200
    assert "access_token" in res3.json()


@pytest.mark.anyio
async def test_refresh_after_logout_is_rejected(async_client: AsyncClient) -> None:
    """Verify that logging out invalidates all refresh tokens for that session."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Logout Refresh User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    tokens = login_res.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Terminate session via logout
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_res.status_code == 200

    # Attempt to refresh using token from logged-out session -> MUST FAIL WITH 401
    refresh_attempt = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_attempt.status_code == 401


@pytest.mark.anyio
async def test_access_token_after_logout_is_rejected(async_client: AsyncClient) -> None:
    """Verify that logging out immediately invalidates existing access tokens."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Logout Access User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    access_token = login_res.json()["access_token"]

    # Access token is valid before logout
    me_before = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_before.status_code == 200

    # Terminate session
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout_res.status_code == 200

    # Access token must be rejected immediately after logout -> MUST FAIL WITH 401
    me_after = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_after.status_code == 401


@pytest.mark.anyio
async def test_expired_refresh_token_rejected(async_client: AsyncClient) -> None:
    """Verify that expired refresh tokens are rejected with 401."""
    from corbel.core.database import get_session_factory
    from corbel.domains.tenancy.models import RefreshToken, SessionStatus, UserSession
    from corbel.domains.tenancy.security import create_refresh_token, hash_token

    email = unique_email()
    password = "Password123!"
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Expired Token User"},
    )
    user_id = uuid.UUID(reg.json()["id"])

    # Create an expired session and token directly in database
    session_factory = get_session_factory()
    now_utc = datetime.now(UTC)
    expired_time = now_utc - timedelta(days=1)
    session_id = uuid.uuid4()
    token_id = uuid.uuid4()

    token_str, _, _, _, _ = create_refresh_token(
        user_id=user_id,
        email=email,
        session_id=session_id,
        family_id=session_id,
        token_id=token_id,
        expires_delta=timedelta(seconds=-60),
    )

    async with session_factory() as session:
        user_session = UserSession(
            id=session_id,
            user_id=user_id,
            status=SessionStatus.ACTIVE.value,
            created_at=expired_time,
            expires_at=expired_time,
        )
        db_token = RefreshToken(
            id=token_id,
            session_id=session_id,
            user_id=user_id,
            token_hash=hash_token(token_str),
            family_id=session_id,
            is_revoked=False,
            expires_at=expired_time,
        )
        session.add(user_session)
        session.add(db_token)
        await session.commit()

    # Attempt to refresh with expired token -> 401
    res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token_str})
    assert res.status_code == 401


@pytest.mark.anyio
async def test_concurrent_refresh_requests_cannot_both_succeed(async_client: AsyncClient) -> None:
    """Verify that concurrent requests with the same refresh token cannot both succeed."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Concurrent User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    refresh_token = login_res.json()["refresh_token"]

    # Issue two simultaneous refresh requests with the identical refresh token
    req1 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    req2 = async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})

    responses = await asyncio.gather(req1, req2)
    status_codes = [r.status_code for r in responses]

    # Exactly one request must succeed (200), and the other must be rejected (401)
    assert 200 in status_codes
    assert 401 in status_codes
    assert status_codes.count(200) == 1


@pytest.mark.anyio
async def test_incorrect_token_types_rejected(async_client: AsyncClient) -> None:
    """Verify that cross-token type usage is strictly rejected."""
    email = unique_email()
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Type Test User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    tokens = login_res.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Try to use access_token at /refresh endpoint -> MUST FAIL
    res1 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert res1.status_code == 401

    # Try to use refresh_token at /me endpoint -> MUST FAIL
    res2 = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert res2.status_code == 401
