"""Multi-tenant isolation and security tests for Ontology Engine (Phase 4)."""

import uuid

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_unauthenticated_ontology_requests_rejected(async_client: AsyncClient) -> None:
    """Verify all ontology endpoints reject unauthenticated access with 401 Unauthorized."""
    fake_project_id = uuid.uuid4()
    fake_object_id = uuid.uuid4()

    res = await async_client.get(f"/api/v1/projects/{fake_project_id}/ontology/objects")
    assert res.status_code == 401

    res = await async_client.post(f"/api/v1/projects/{fake_project_id}/ontology/seed-p2p")
    assert res.status_code == 401

    res = await async_client.get(f"/api/v1/projects/{fake_project_id}/ontology/graph")
    assert res.status_code == 401

    res = await async_client.get(f"/api/v1/projects/{fake_project_id}/ontology/objects/{fake_object_id}")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_cross_tenant_ontology_isolation(async_client: AsyncClient) -> None:
    """Verify Organization A cannot read or mutate Organization B's ontology objects."""
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    project_a_id = project_a["id"]
    project_b_id = project_b["id"]

    # 1. Org A seeds P2P ontology
    seed_a = await async_client.post(
        f"/api/v1/projects/{project_a_id}/ontology/seed-p2p",
        headers=headers_a,
    )
    assert seed_a.status_code == 201
    obj_a_id = seed_a.json()[0]["id"]

    # 2. Org B attempts to read Org A's objects list using Org B's credentials -> Rejected (403 or 404)
    res = await async_client.get(
        f"/api/v1/projects/{project_a_id}/ontology/objects",
        headers=headers_b,
    )
    assert res.status_code in (403, 404)

    # 3. Org B attempts to read Org A's specific Business Object -> Rejected (403 or 404)
    res = await async_client.get(
        f"/api/v1/projects/{project_a_id}/ontology/objects/{obj_a_id}",
        headers=headers_b,
    )
    assert res.status_code in (403, 404)

    # 4. Org B attempts to add a property to Org A's Business Object -> Rejected
    res = await async_client.post(
        f"/api/v1/projects/{project_a_id}/ontology/objects/{obj_a_id}/properties",
        json={"name": "malicious_prop", "data_type": "STRING"},
        headers=headers_b,
    )
    assert res.status_code in (403, 404)

    # 5. Header tampering: Org A user sends Org B project ID in path while keeping X-Organization-ID of Org A
    res = await async_client.get(
        f"/api/v1/projects/{project_b_id}/ontology/objects",
        headers=headers_a,
    )
    assert res.status_code in (403, 404)
