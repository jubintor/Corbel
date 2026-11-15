"""Multi-tenant isolation and security tests for Process Intelligence (Phase 6)."""

import uuid

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_unauthenticated_process_requests_rejected(async_client: AsyncClient) -> None:
    """Verify all process endpoints reject unauthenticated requests with 401 Unauthorized."""
    fake_project_id = uuid.uuid4()
    fake_process_id = uuid.uuid4()

    # List processes
    res1 = await async_client.get(f"/api/v1/projects/{fake_project_id}/process")
    assert res1.status_code == 401

    # Create process
    res2 = await async_client.post(
        f"/api/v1/projects/{fake_project_id}/process",
        json={"name": "Proc"},
    )
    assert res2.status_code == 401

    # Get overview
    res3 = await async_client.get(f"/api/v1/projects/{fake_project_id}/process/{fake_process_id}/overview")
    assert res3.status_code == 401

    # Get DFG
    res4 = await async_client.get(f"/api/v1/projects/{fake_project_id}/process/{fake_process_id}/dfg")
    assert res4.status_code == 401

    # Get variants
    res5 = await async_client.get(f"/api/v1/projects/{fake_project_id}/process/{fake_process_id}/variants")
    assert res5.status_code == 401

    # List cases
    res6 = await async_client.get(f"/api/v1/projects/{fake_project_id}/process/{fake_process_id}/cases")
    assert res6.status_code == 401


@pytest.mark.anyio
async def test_cross_tenant_process_isolation(async_client: AsyncClient) -> None:
    """Verify Organization A cannot view, access, ingest into, or mutate Organization B's processes."""
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    project_a_id = project_a["id"]

    # 1. Org A creates a process
    res_a = await async_client.post(
        f"/api/v1/projects/{project_a_id}/process",
        json={"name": "Org A Private Process"},
        headers=headers_a,
    )
    assert res_a.status_code == 201
    proc_a_id = res_a.json()["id"]

    # 2. Org B attempts to list processes in Org A's project -> MUST fail (403 or 404)
    res_b_list = await async_client.get(
        f"/api/v1/projects/{project_a_id}/process",
        headers=headers_b,
    )
    assert res_b_list.status_code in (403, 404)

    # 3. Org B attempts to get Org A's process detail -> MUST fail
    res_b_get = await async_client.get(
        f"/api/v1/projects/{project_a_id}/process/{proc_a_id}",
        headers=headers_b,
    )
    assert res_b_get.status_code in (403, 404)

    # 4. Org B attempts to get Org A's DFG -> MUST fail
    res_b_dfg = await async_client.get(
        f"/api/v1/projects/{project_a_id}/process/{proc_a_id}/dfg",
        headers=headers_b,
    )
    assert res_b_dfg.status_code in (403, 404)

    # 5. Org B attempts to delete Org A's process -> MUST fail
    res_b_del = await async_client.delete(
        f"/api/v1/projects/{project_a_id}/process/{proc_a_id}",
        headers=headers_b,
    )
    assert res_b_del.status_code in (403, 404)
