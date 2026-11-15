"""Tests for organization management, membership lifecycle, and tenancy-scoped projects."""

import uuid

import pytest
from httpx import AsyncClient


def unique_email() -> str:
    return f"user_{uuid.uuid4().hex[:8]}@example.com"


def unique_slug(prefix: str = "org") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def create_user_and_token(async_client: AsyncClient, name: str = "Test User") -> tuple[dict, str]:
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
async def test_create_organization_creator_becomes_admin(async_client: AsyncClient) -> None:
    user, token = await create_user_and_token(async_client, "Org Creator")
    headers = {"Authorization": f"Bearer {token}"}

    slug = unique_slug("corp")
    response = await async_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "Corporation A", "slug": slug},
    )
    assert response.status_code == 201
    org = response.json()
    assert org["name"] == "Corporation A"
    assert org["slug"] == slug
    assert org["status"] == "ACTIVE"

    # List organizations for user
    list_res = await async_client.get("/api/v1/organizations", headers=headers)
    assert list_res.status_code == 200
    user_orgs = list_res.json()
    assert len(user_orgs) >= 1
    matched = [o for o in user_orgs if o["id"] == org["id"]]
    assert len(matched) == 1
    assert matched[0]["role"] == "ORG_ADMIN"
    assert matched[0]["membership_status"] == "ACTIVE"


@pytest.mark.anyio
async def test_organization_member_lifecycle(async_client: AsyncClient) -> None:
    admin, admin_token = await create_user_and_token(async_client, "Org Admin")
    member, _ = await create_user_and_token(async_client, "Regular Member")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    org_res = await async_client.post(
        "/api/v1/organizations",
        headers=admin_headers,
        json={"name": "Lifecycle Corp", "slug": unique_slug("lifecycle")},
    )
    org_id = org_res.json()["id"]

    # Admin adds member as AUDITOR
    add_res = await async_client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=admin_headers,
        json={"email": member["email"], "role": "AUDITOR"},
    )
    assert add_res.status_code == 201
    member_data = add_res.json()
    assert member_data["role"] == "AUDITOR"
    assert member_data["status"] == "ACTIVE"

    # List members
    members_res = await async_client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=admin_headers,
    )
    assert members_res.status_code == 200
    members = members_res.json()
    assert len(members) == 2

    # Promote member to ORG_ADMIN
    update_res = await async_client.patch(
        f"/api/v1/organizations/{org_id}/members/{member['id']}/role",
        headers=admin_headers,
        json={"role": "ORG_ADMIN"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["role"] == "ORG_ADMIN"


@pytest.mark.anyio
async def test_sole_admin_protection(async_client: AsyncClient) -> None:
    admin, admin_token = await create_user_and_token(async_client, "Sole Admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    org_res = await async_client.post(
        "/api/v1/organizations",
        headers=admin_headers,
        json={"name": "Sole Admin Org", "slug": unique_slug("sole")},
    )
    org_id = org_res.json()["id"]

    # Attempt to demote sole admin to MEMBER -> 403
    demote_res = await async_client.patch(
        f"/api/v1/organizations/{org_id}/members/{admin['id']}/role",
        headers=admin_headers,
        json={"role": "MEMBER"},
    )
    assert demote_res.status_code == 403
    assert demote_res.json()["error"] == "INSUFFICIENT_PERMISSIONS"
    assert "sole active administrator" in demote_res.json()["message"]

    # Attempt to remove sole admin -> 403
    delete_res = await async_client.delete(
        f"/api/v1/organizations/{org_id}/members/{admin['id']}",
        headers=admin_headers,
    )
    assert delete_res.status_code == 403
    assert delete_res.json()["error"] == "INSUFFICIENT_PERMISSIONS"
    assert "sole active administrator" in delete_res.json()["message"]


@pytest.mark.anyio
async def test_project_crud_within_tenant_context(async_client: AsyncClient) -> None:
    admin, token = await create_user_and_token(async_client, "Project Manager")
    auth_headers = {"Authorization": f"Bearer {token}"}

    org_res = await async_client.post(
        "/api/v1/organizations",
        headers=auth_headers,
        json={"name": "Project Workspace Org", "slug": unique_slug("proj")},
    )
    org_id = org_res.json()["id"]

    tenant_headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": org_id,
    }

    # Create project
    proj_slug = unique_slug("p2p")
    create_res = await async_client.post(
        "/api/v1/projects",
        headers=tenant_headers,
        json={
            "name": "P2P Operational Intelligence",
            "slug": proj_slug,
            "description": "Procure-to-Pay vertical slice",
        },
    )
    assert create_res.status_code == 201
    project = create_res.json()
    assert project["name"] == "P2P Operational Intelligence"
    assert project["slug"] == proj_slug
    assert project["organization_id"] == org_id
    project_id = project["id"]

    # List projects in tenant
    list_res = await async_client.get("/api/v1/projects", headers=tenant_headers)
    assert list_res.status_code == 200
    projects = list_res.json()
    assert any(p["id"] == project_id for p in projects)

    # Get project by ID
    get_res = await async_client.get(f"/api/v1/projects/{project_id}", headers=tenant_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == project_id

    # Update project
    patch_res = await async_client.patch(
        f"/api/v1/projects/{project_id}",
        headers=tenant_headers,
        json={"name": "P2P Intelligence Updated", "description": "Updated description"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "P2P Intelligence Updated"

    # Delete project
    del_res = await async_client.delete(f"/api/v1/projects/{project_id}", headers=tenant_headers)
    assert del_res.status_code == 200

    # Verify deleted
    get_after_del = await async_client.get(f"/api/v1/projects/{project_id}", headers=tenant_headers)
    assert get_after_del.status_code == 404
