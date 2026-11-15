"""Tests for multi-tenant isolation, cross-tenant attack prevention, and scope boundaries."""

import uuid

import pytest
from httpx import AsyncClient


def unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


def unique_slug(prefix: str = "iso") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def create_user_and_token(async_client: AsyncClient, name: str) -> tuple[dict, str]:
    email = unique_email()
    password = "SecurePassword123!"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": name},
    )
    user_data = reg_res.json()
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login_res.json()["access_token"]
    return user_data, token


@pytest.mark.anyio
async def test_cross_tenant_project_read_isolation(async_client: AsyncClient) -> None:
    """Verify that projects belonging to Org B cannot be accessed by Org A."""
    # Tenant A
    user_a, token_a = await create_user_and_token(async_client, "User A")
    auth_a = {"Authorization": f"Bearer {token_a}"}
    org_a_res = await async_client.post(
        "/api/v1/organizations",
        headers=auth_a,
        json={"name": "Tenant Alpha", "slug": unique_slug("alpha")},
    )
    org_a_id = org_a_res.json()["id"]

    # Tenant B
    user_b, token_b = await create_user_and_token(async_client, "User B")
    auth_b = {"Authorization": f"Bearer {token_b}"}
    org_b_res = await async_client.post(
        "/api/v1/organizations",
        headers=auth_b,
        json={"name": "Tenant Beta", "slug": unique_slug("beta")},
    )
    org_b_id = org_b_res.json()["id"]

    # Create project in Org B
    proj_b_res = await async_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b_id},
        json={"name": "Beta Private Project", "slug": unique_slug("beta-proj")},
    )
    proj_b_id = proj_b_res.json()["id"]

    # User A tries to read Project B using Org A header -> 404 (not in Org A)
    read_attempt = await async_client.get(
        f"/api/v1/projects/{proj_b_id}",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a_id},
    )
    assert read_attempt.status_code == 404
    assert read_attempt.json()["error"] == "PROJECT_NOT_FOUND"


@pytest.mark.anyio
async def test_header_tampering_attack_rejected(async_client: AsyncClient) -> None:
    """Verify that User A cannot forge X-Organization-ID header for Org B."""
    user_a, token_a = await create_user_and_token(async_client, "Attacker User A")
    _user_b, token_b = await create_user_and_token(async_client, "Victim User B")

    # Create Victim Org B
    org_b_res = await async_client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Target Org B", "slug": unique_slug("target-b")},
    )
    org_b_id = org_b_res.json()["id"]

    # User A sends request presenting Org B's ID in header
    tamper_res = await async_client.get(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_b_id},
    )
    assert tamper_res.status_code == 403
    assert tamper_res.json()["error"] == "NOT_ORGANIZATION_MEMBER"

    # User A tries to create a project in Org B
    create_tamper = await async_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_b_id},
        json={"name": "Malicious Project", "slug": unique_slug("malicious")},
    )
    assert create_tamper.status_code == 403
    assert create_tamper.json()["error"] == "NOT_ORGANIZATION_MEMBER"


@pytest.mark.anyio
async def test_cross_tenant_update_and_delete_rejected(async_client: AsyncClient) -> None:
    """Verify that User A cannot mutate or delete Org B's projects."""
    user_a, token_a = await create_user_and_token(async_client, "User A")
    _user_b, token_b = await create_user_and_token(async_client, "User B")

    org_a_res = await async_client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Org A", "slug": unique_slug("orga")},
    )
    org_a_id = org_a_res.json()["id"]

    org_b_res = await async_client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Org B", "slug": unique_slug("orgb")},
    )
    org_b_id = org_b_res.json()["id"]

    # Create project in Org B
    proj_b_res = await async_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b_id},
        json={"name": "Beta Core Project", "slug": unique_slug("bcore")},
    )
    proj_b_id = proj_b_res.json()["id"]

    # User A attempts PATCH with Org A header -> 404
    patch_attempt = await async_client.patch(
        f"/api/v1/projects/{proj_b_id}",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a_id},
        json={"name": "Compromised Project"},
    )
    assert patch_attempt.status_code == 404

    # User A attempts DELETE with Org A header -> 404
    delete_attempt = await async_client.delete(
        f"/api/v1/projects/{proj_b_id}",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a_id},
    )
    assert delete_attempt.status_code == 404


@pytest.mark.anyio
async def test_cross_tenant_project_member_assignment_rejected(async_client: AsyncClient) -> None:
    """Verify that adding a user from another organization to a project is rejected."""
    user_a, token_a = await create_user_and_token(async_client, "Admin Org A")
    user_b, _ = await create_user_and_token(async_client, "Stranger User B")

    org_a_res = await async_client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Strict Org A", "slug": unique_slug("strict")},
    )
    org_a_id = org_a_res.json()["id"]

    # Create project in Org A
    proj_a_res = await async_client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a_id},
        json={"name": "Strict Project", "slug": unique_slug("strict-proj")},
    )
    proj_a_id = proj_a_res.json()["id"]

    # Attempt to add User B (who is NOT in Org A) to Project A
    add_member_res = await async_client.post(
        f"/api/v1/projects/{proj_a_id}/members",
        headers={"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a_id},
        json={"user_id": user_b["id"], "project_role": "ANALYST"},
    )
    assert add_member_res.status_code == 403
    assert add_member_res.json()["error"] == "CROSS_TENANT_VIOLATION"


@pytest.mark.anyio
async def test_multi_tenant_user_isolated_views(async_client: AsyncClient) -> None:
    """Verify that a user who belongs to multiple organizations sees strictly isolated data per active tenant."""
    common_user, common_token = await create_user_and_token(async_client, "Multi Org User")
    headers = {"Authorization": f"Bearer {common_token}"}

    # Common user creates Org 1
    org1_res = await async_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "First Tenant", "slug": unique_slug("first")},
    )
    org1_id = org1_res.json()["id"]

    # Common user creates Org 2
    org2_res = await async_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Second Tenant", "slug": unique_slug("second")},
    )
    org2_id = org2_res.json()["id"]

    # Create project in Org 1
    p1_res = await async_client.post(
        "/api/v1/projects",
        headers={**headers, "X-Organization-ID": org1_id},
        json={"name": "Org 1 Project", "slug": unique_slug("p1")},
    )
    p1_id = p1_res.json()["id"]

    # Create project in Org 2
    p2_res = await async_client.post(
        "/api/v1/projects",
        headers={**headers, "X-Organization-ID": org2_id},
        json={"name": "Org 2 Project", "slug": unique_slug("p2")},
    )
    p2_id = p2_res.json()["id"]

    # Query with Org 1 context
    org1_list = await async_client.get(
        "/api/v1/projects",
        headers={**headers, "X-Organization-ID": org1_id},
    )
    assert org1_list.status_code == 200
    org1_project_ids = [p["id"] for p in org1_list.json()]
    assert p1_id in org1_project_ids
    assert p2_id not in org1_project_ids

    # Query with Org 2 context
    org2_list = await async_client.get(
        "/api/v1/projects",
        headers={**headers, "X-Organization-ID": org2_id},
    )
    assert org2_list.status_code == 200
    org2_project_ids = [p["id"] for p in org2_list.json()]
    assert p2_id in org2_project_ids
    assert p1_id not in org2_project_ids
