"""Integration tests for dataset file upload, profiling, and metadata endpoints."""

import io
import json

import pytest
from httpx import AsyncClient

from tests.test_tenancy import create_user_and_token, unique_slug


async def setup_test_org_and_project(async_client: AsyncClient) -> tuple[dict, str, dict, dict]:
    """Helper creating user, active organization, and project workspace."""
    user, token = await create_user_and_token(async_client, "Data Analyst")
    headers = {"Authorization": f"Bearer {token}"}

    org_res = await async_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={"name": "P2P Enterprise", "slug": unique_slug("p2p-org")},
    )
    assert org_res.status_code == 201
    org = org_res.json()

    proj_res = await async_client.post(
        "/api/v1/projects",
        headers={**headers, "X-Organization-ID": org["id"]},
        json={
            "name": "Procure-to-Pay Intelligence",
            "slug": unique_slug("p2p-proj"),
            "description": "P2P dataset profiling and monitoring",
        },
    )
    assert proj_res.status_code == 201
    project = proj_res.json()

    return user, token, org, project


@pytest.mark.anyio
async def test_upload_valid_csv_dataset(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    csv_content = (
        "supplier_id,supplier_name,country,payment_terms,credit_limit\n"
        "SUP-001,Acme Supply,USA,NET30,50000\n"
        "SUP-002,Global Logistics,DEU,NET60,100000\n"
        "SUP-003,Apex Components,GBR,NET30,25000\n"
    )

    files = {"file": ("suppliers.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    data = {"name": "Suppliers Master", "description": "Vendor master records"}

    response = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        data=data,
        files=files,
    )
    assert response.status_code == 201
    dataset = response.json()

    assert dataset["name"] == "Suppliers Master"
    assert dataset["status"] == "PROFILED"
    assert dataset["version_count"] == 1

    v = dataset["latest_version"]
    assert v is not None
    assert v["version_number"] == 1
    assert v["file_format"] == "CSV"
    assert v["record_count"] == 3
    assert v["column_count"] == 5
    assert v["status"] == "READY"

    # Verify profiling summary contents
    summary = v["profiling_summary"]
    assert summary is not None
    assert summary["total_rows"] == 3
    assert summary["total_columns"] == 5
    assert summary["duplicate_rows_count"] == 0

    col_names = [c["column_name"] for c in summary["columns"]]
    assert "supplier_id" in col_names
    assert "credit_limit" in col_names

    credit_col = next(c for c in summary["columns"] if c["column_name"] == "credit_limit")
    assert credit_col["detected_type"] == "INTEGER"
    assert credit_col["numeric_stats"]["min"] == 25000.0
    assert credit_col["numeric_stats"]["max"] == 100000.0
    assert credit_col["numeric_stats"]["mean"] == 58333.3333


@pytest.mark.anyio
async def test_upload_valid_json_dataset(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    json_records = [
        {"po_number": "PO-101", "amount": 1500.50, "status": "APPROVED"},
        {"po_number": "PO-102", "amount": 2750.00, "status": "APPROVED"},
    ]
    file_bytes = json.dumps(json_records).encode("utf-8")
    files = {"file": ("purchase_orders.json", io.BytesIO(file_bytes), "application/json")}

    response = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        files=files,
    )
    assert response.status_code == 201
    dataset = response.json()
    assert dataset["status"] == "PROFILED"
    assert dataset["latest_version"]["record_count"] == 2


@pytest.mark.anyio
async def test_upload_unsupported_format_fails(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    files = {"file": ("malicious_script.sh", io.BytesIO(b"echo hello"), "application/x-sh")}
    response = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        files=files,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "UNSUPPORTED_FILE_FORMAT"


@pytest.mark.anyio
async def test_upload_empty_dataset_fails(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        files=files,
    )
    assert response.status_code == 400
    assert response.json()["error"] == "EMPTY_DATASET"


@pytest.mark.anyio
async def test_dataset_versioning_and_preview(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Upload v1
    v1_csv = "sku,qty\nITEM-A,10\nITEM-B,20\n"
    files1 = {"file": ("inventory.csv", io.BytesIO(v1_csv.encode("utf-8")), "text/csv")}
    res1 = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        data={"name": "Inventory Levels"},
        files=files1,
    )
    assert res1.status_code == 201
    dataset = res1.json()
    dataset_id = dataset["id"]

    # Upload v2 with same dataset name
    v2_csv = "sku,qty\nITEM-A,15\nITEM-B,25\nITEM-C,35\n"
    files2 = {"file": ("inventory.csv", io.BytesIO(v2_csv.encode("utf-8")), "text/csv")}
    res2 = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        data={"name": "Inventory Levels"},
        files=files2,
    )
    assert res2.status_code == 201
    d2 = res2.json()
    assert d2["version_count"] == 2
    assert d2["latest_version"]["version_number"] == 2
    assert d2["latest_version"]["record_count"] == 3

    # Preview dataset
    prev_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset_id}/preview?limit=2",
        headers=headers,
    )
    assert prev_res.status_code == 200
    prev = prev_res.json()
    assert prev["columns"] == ["sku", "qty"]
    assert prev["total_preview_rows"] == 2


@pytest.mark.anyio
async def test_dataset_deletion(async_client: AsyncClient) -> None:
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    csv_content = "id,value\n1,Alpha\n"
    files = {"file": ("temp.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = await async_client.post(
        f"/api/v1/projects/{project['id']}/datasets/upload",
        headers=headers,
        files=files,
    )
    dataset_id = res.json()["id"]

    # Delete
    del_res = await async_client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{dataset_id}",
        headers=headers,
    )
    assert del_res.status_code == 204

    # Verify 404
    get_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/datasets/{dataset_id}",
        headers=headers,
    )
    assert get_res.status_code == 404
