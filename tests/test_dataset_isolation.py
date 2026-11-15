"""Security & Tenant Isolation tests for Data Intelligence & Profiling."""

import io
import uuid

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_unauthenticated_upload_rejected(async_client: AsyncClient) -> None:
    fake_proj_id = uuid.uuid4()
    files = {"file": ("data.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")}
    response = await async_client.post(
        f"/api/v1/projects/{fake_proj_id}/datasets/upload",
        files=files,
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_unauthenticated_dataset_list_rejected(async_client: AsyncClient) -> None:
    fake_proj_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/projects/{fake_proj_id}/datasets")
    assert response.status_code == 401


@pytest.mark.anyio
async def test_cross_tenant_dataset_isolation(async_client: AsyncClient) -> None:
    """Verifies Tenant A cannot see, read, preview, or mutate Tenant B's datasets."""
    # Tenant A
    user_a, token_a, org_a, proj_a = await setup_test_org_and_project(async_client)
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}

    # Tenant B
    user_b, token_b, org_b, proj_b = await setup_test_org_and_project(async_client)
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    # Tenant A uploads a sensitive dataset
    csv_a = "secret_id,amount\nSEC-1,99999\n"
    files_a = {"file": ("secrets.csv", io.BytesIO(csv_a.encode("utf-8")), "text/csv")}
    upload_res = await async_client.post(
        f"/api/v1/projects/{proj_a['id']}/datasets/upload",
        headers=headers_a,
        files=files_a,
    )
    assert upload_res.status_code == 201
    dataset_a = upload_res.json()
    dataset_a_id = dataset_a["id"]

    # 1. Tenant B attempts to list datasets in Tenant A's project
    b_list_res = await async_client.get(
        f"/api/v1/projects/{proj_a['id']}/datasets",
        headers=headers_b,
    )
    assert b_list_res.status_code in (403, 404)

    # 2. Tenant B attempts to fetch Tenant A's dataset details directly
    b_get_res = await async_client.get(
        f"/api/v1/projects/{proj_a['id']}/datasets/{dataset_a_id}",
        headers=headers_b,
    )
    assert b_get_res.status_code in (403, 404)

    # 3. Tenant B attempts to fetch Tenant A's dataset using their own project ID in URL
    b_spoof_res = await async_client.get(
        f"/api/v1/projects/{proj_b['id']}/datasets/{dataset_a_id}",
        headers=headers_b,
    )
    assert b_spoof_res.status_code == 404

    # 4. Tenant B attempts to preview Tenant A's dataset
    b_prev_res = await async_client.get(
        f"/api/v1/projects/{proj_a['id']}/datasets/{dataset_a_id}/preview",
        headers=headers_b,
    )
    assert b_prev_res.status_code in (403, 404)

    # 5. Tenant B attempts to upload a dataset into Tenant A's project
    files_b = {"file": ("infiltrate.csv", io.BytesIO(b"x,y\n1,2\n"), "text/csv")}
    b_upload_res = await async_client.post(
        f"/api/v1/projects/{proj_a['id']}/datasets/upload",
        headers=headers_b,
        files=files_b,
    )
    assert b_upload_res.status_code in (403, 404)

    # 6. Tenant B lists all organization datasets: Tenant A's dataset must not appear
    b_all_res = await async_client.get(
        "/api/v1/datasets",
        headers=headers_b,
    )
    assert b_all_res.status_code == 200
    b_datasets = b_all_res.json()
    assert all(d["id"] != dataset_a_id for d in b_datasets)


@pytest.mark.anyio
async def test_header_tampering_rejected(async_client: AsyncClient) -> None:
    """Verifies that spoofing X-Organization-ID to an org where user is not a member is rejected."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    random_org_id = str(uuid.uuid4())

    tampered_headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": random_org_id,
    }
    response = await async_client.get(
        f"/api/v1/projects/{project['id']}/datasets",
        headers=tampered_headers,
    )
    assert response.status_code == 403
