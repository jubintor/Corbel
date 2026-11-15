"""Multi-tenant isolation and security tests for Structured Querying & Early AI Gateway (Phase 5)."""

import uuid

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_unauthenticated_query_requests_rejected(async_client: AsyncClient) -> None:
    """Verify all query endpoints reject unauthenticated requests with 401 Unauthorized."""
    fake_project_id = uuid.uuid4()

    # Schema endpoint
    res = await async_client.get(f"/api/v1/projects/{fake_project_id}/query/schema")
    assert res.status_code == 401

    # Execute endpoint
    res = await async_client.post(
        f"/api/v1/projects/{fake_project_id}/query/execute",
        json={"entity_name": "Invoice", "fields": ["invoice_id"]},
    )
    assert res.status_code == 401

    # NLQ endpoint
    res = await async_client.post(
        f"/api/v1/projects/{fake_project_id}/query/nlq",
        json={"prompt": "Find all invoices"},
    )
    assert res.status_code == 401

    # History endpoint
    res = await async_client.get(f"/api/v1/projects/{fake_project_id}/query/history")
    assert res.status_code == 401


@pytest.mark.anyio
async def test_cross_tenant_query_isolation(async_client: AsyncClient) -> None:
    """Verify Organization A cannot query or view query history for Organization B's project."""
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    project_a_id = project_a["id"]

    # Org A seeds P2P
    await async_client.post(f"/api/v1/projects/{project_a_id}/ontology/seed-p2p", headers=headers_a)

    # 1. Org B attempts to get query schema of Org A's project -> Rejected (403 or 404)
    res_schema = await async_client.get(
        f"/api/v1/projects/{project_a_id}/query/schema",
        headers=headers_b,
    )
    assert res_schema.status_code in (403, 404)

    # 2. Org B attempts to execute query against Org A's project -> Rejected (403 or 404)
    res_exec = await async_client.post(
        f"/api/v1/projects/{project_a_id}/query/execute",
        json={"entity_name": "Invoice", "fields": ["invoice_id"]},
        headers=headers_b,
    )
    assert res_exec.status_code in (403, 404)

    # 3. Org B attempts to compile NLQ against Org A's project -> Rejected (403 or 404)
    res_nlq = await async_client.post(
        f"/api/v1/projects/{project_a_id}/query/nlq",
        json={"prompt": "Show invoices"},
        headers=headers_b,
    )
    assert res_nlq.status_code in (403, 404)

    # 4. Org B attempts to view query history of Org A's project -> Rejected (403 or 404)
    res_hist = await async_client.get(
        f"/api/v1/projects/{project_a_id}/query/history",
        headers=headers_b,
    )
    assert res_hist.status_code in (403, 404)
