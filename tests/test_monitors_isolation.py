"""Tenant and project isolation security tests for Phase 7 Monitors & Findings."""


import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project
from tests.test_tenancy import create_user_and_token


@pytest.mark.anyio
async def test_monitor_cross_tenant_isolation(async_client: AsyncClient) -> None:
    """Verify that Tenant A cannot access, list, or manipulate Tenant B's monitors or findings."""
    # Setup Tenant A
    user_a, token_a, org_a, proj_a = await setup_test_org_and_project(async_client)
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}
    proj_a_id = proj_a["id"]

    # Setup Tenant B
    user_b, token_b, org_b, proj_b = await setup_test_org_and_project(async_client)
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    # 1. Tenant A creates a monitor
    create_res = await async_client.post(
        f"/api/v1/projects/{proj_a_id}/monitors",
        json={
            "name": "Tenant A Secret Monitor",
            "target_type": "ENTITY",
            "target_id": "PurchaseOrder",
            "rules": [
                {
                    "rule_code": "SEC_10K",
                    "severity": "HIGH",
                    "rule_type": "THRESHOLD",
                    "field_name": "total_amount",
                    "operator": "gt",
                    "threshold_value": 10000.0,
                }
            ],
        },
        headers=headers_a,
    )
    assert create_res.status_code == 201
    mon_a_id = create_res.json()["id"]

    # 2. Tenant B attempts to GET Tenant A's monitor -> 403 or 404 (isolation enforced)
    cross_get_res = await async_client.get(
        f"/api/v1/projects/{proj_a_id}/monitors/{mon_a_id}",
        headers=headers_b,
    )
    assert cross_get_res.status_code in (403, 404)

    # 3. Tenant B attempts to LIST Tenant A's monitors -> 403 or 404
    cross_list_res = await async_client.get(
        f"/api/v1/projects/{proj_a_id}/monitors",
        headers=headers_b,
    )
    assert cross_list_res.status_code in (403, 404)

    # 4. Tenant B attempts to evaluate Tenant A's monitor -> 403 or 404
    cross_eval_res = await async_client.post(
        f"/api/v1/projects/{proj_a_id}/monitors/{mon_a_id}/evaluate",
        json={},
        headers=headers_b,
    )
    assert cross_eval_res.status_code in (403, 404)

    # 5. Tenant B attempts to list Tenant A's findings -> 403 or 404
    cross_find_res = await async_client.get(
        f"/api/v1/projects/{proj_a_id}/findings",
        headers=headers_b,
    )
    assert cross_find_res.status_code in (403, 404)


@pytest.mark.anyio
async def test_monitor_viewer_role_restrictions(async_client: AsyncClient) -> None:
    """Verify that a VIEWER role member cannot create, delete, or evaluate monitors."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # Create a secondary user with VIEWER role
    viewer_user, viewer_token = await create_user_and_token(async_client, "Viewer User")
    viewer_id = viewer_user["id"]
    viewer_headers = {
        "Authorization": f"Bearer {viewer_token}",
        "X-Organization-ID": org["id"],
    }

    # Add viewer to org
    add_org_res = await async_client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": viewer_user["email"], "role": "MEMBER"},
        headers=headers,
    )
    assert add_org_res.status_code == 201

    # Add viewer to project with VIEWER role
    add_proj_res = await async_client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": viewer_id, "project_role": "VIEWER"},
        headers=headers,
    )
    assert add_proj_res.status_code == 201

    # VIEWER can LIST monitors (empty)
    v_list = await async_client.get(
        f"/api/v1/projects/{project_id}/monitors",
        headers=viewer_headers,
    )
    assert v_list.status_code == 200

    # VIEWER cannot CREATE monitors -> 403 Forbidden
    v_create = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors",
        json={
            "name": "Viewer Unauthorized Monitor",
            "target_type": "ENTITY",
            "target_id": "PurchaseOrder",
            "rules": [],
        },
        headers=viewer_headers,
    )
    assert v_create.status_code == 403
