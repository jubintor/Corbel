"""HTTP integration tests for Process Intelligence API endpoints (Phase 6)."""


import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_process_api_endpoints_end_to_end(async_client: AsyncClient) -> None:
    """Full HTTP API test: create process -> batch ingest -> query DFG, variants, cases, and overview."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Create Process
    create_res = await async_client.post(
        f"/api/v1/projects/{project_id}/process",
        json={
            "name": "P2P Operational Intelligence",
            "description": "Procure-to-Pay Event Log",
            "target_duration_seconds": 86400 * 4,  # 4 days
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    proc = create_res.json()
    process_id = proc["id"]
    assert proc["name"] == "P2P Operational Intelligence"

    # 2. List Processes
    list_res = await async_client.get(f"/api/v1/projects/{project_id}/process", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 3. Batch Ingest Events
    t0 = "2026-10-01T08:00:00Z"
    t1 = "2026-10-02T12:00:00Z"
    t2 = "2026-10-03T16:00:00Z"

    events_payload = {
        "events": [
            {"case_identifier": "PO-9001", "activity_name": "PO Created", "timestamp": t0, "resource": "SUP-1"},
            {"case_identifier": "PO-9001", "activity_name": "Goods Received", "timestamp": t1, "resource": "WH-1"},
            {"case_identifier": "PO-9001", "activity_name": "Invoice Received", "timestamp": t2, "resource": "AP-1"},
            {"case_identifier": "PO-9002", "activity_name": "PO Created", "timestamp": t0, "resource": "SUP-2"},
            {"case_identifier": "PO-9002", "activity_name": "Invoice Received", "timestamp": t1, "resource": "AP-2"},
        ]
    }
    ingest_res = await async_client.post(
        f"/api/v1/projects/{project_id}/process/{process_id}/events/batch",
        json=events_payload,
        headers=headers,
    )
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.json()
    assert ingest_data["cases_reconstructed"] == 2
    assert ingest_data["events_reconstructed"] == 5
    assert ingest_data["variants_count"] == 2

    # 4. Get Process Overview
    overview_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/overview",
        headers=headers,
    )
    assert overview_res.status_code == 200
    overview = overview_res.json()
    assert overview["total_cases"] == 2
    assert overview["total_events"] == 5
    assert overview["distinct_variants_count"] == 2
    assert overview["distinct_activities_count"] == 3

    # 5. Get Process Variants
    variants_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/variants",
        headers=headers,
    )
    assert variants_res.status_code == 200
    variants_data = variants_res.json()
    assert variants_data["total_variants"] == 2
    assert len(variants_data["variants"]) == 2

    # 6. Get Directly-Follows Graph (DFG)
    dfg_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/dfg",
        headers=headers,
    )
    assert dfg_res.status_code == 200
    dfg = dfg_res.json()
    assert len(dfg["nodes"]) == 3
    assert len(dfg["edges"]) >= 2
    assert dfg["bottleneck_edge"] is not None

    # 7. List Cases
    cases_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/cases",
        headers=headers,
    )
    assert cases_res.status_code == 200
    cases_data = cases_res.json()
    assert cases_data["total"] == 2
    case_9001 = next(c for c in cases_data["items"] if c["case_identifier"] == "PO-9001")

    # 8. Get Case Detail
    detail_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/cases/{case_9001['id']}",
        headers=headers,
    )
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["case"]["case_identifier"] == "PO-9001"
    assert len(detail["events"]) == 3
    assert detail["events"][0]["activity_name"] == "PO Created"
    assert detail["events"][1]["activity_name"] == "Goods Received"
    assert detail["events"][2]["activity_name"] == "Invoice Received"

    # 9. Update Process
    update_res = await async_client.put(
        f"/api/v1/projects/{project_id}/process/{process_id}",
        json={"name": "P2P Renamed", "target_duration_seconds": 86400 * 10},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "P2P Renamed"

    # 10. Delete Process
    del_res = await async_client.delete(
        f"/api/v1/projects/{project_id}/process/{process_id}",
        headers=headers,
    )
    assert del_res.status_code == 204

    # Verify 404 after deletion
    get_after = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}",
        headers=headers,
    )
    assert get_after.status_code == 404


@pytest.mark.anyio
async def test_reconstruct_process_from_p2p_datasets(async_client: AsyncClient) -> None:
    """Test full multi-table P2P reconstruction: upload POs and Invoices, trigger reconstruct."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Upload purchase_orders.csv
    po_csv = (
        b"po_id,supplier_id,total_amount,currency,order_date,status\n"
        b"PO-7001,SUP-1,10000,USD,2026-10-01,OPEN\n"
        b"PO-7002,SUP-2,25000,USD,2026-10-02,APPROVED\n"
    )
    po_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("purchase_orders.csv", po_csv, "text/csv")},
        headers=headers,
    )
    assert po_res.status_code == 201, f"PO upload failed: {po_res.text}"

    # 2. Upload invoices.csv
    inv_csv = (
        b"invoice_id,supplier_id,po_id,invoice_date,invoice_amount,currency,status\n"
        b"INV-8001,SUP-1,PO-7001,2026-10-04,10000,USD,PAID\n"
        b"INV-8002,SUP-2,PO-7002,2026-10-06,25000,USD,PENDING\n"
    )
    inv_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", inv_csv, "text/csv")},
        headers=headers,
    )
    assert inv_res.status_code == 201, f"Invoice upload failed: {inv_res.text}"

    # 3. Create Process
    proc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/process",
        json={"name": "Auto P2P Mining"},
        headers=headers,
    )
    process_id = proc_res.json()["id"]

    # 4. Trigger P2P Ontology Reconstruction
    recon_res = await async_client.post(
        f"/api/v1/projects/{project_id}/process/{process_id}/reconstruct",
        json={"mode": "P2P_ONTOLOGY"},
        headers=headers,
    )
    assert recon_res.status_code == 200
    recon_data = recon_res.json()
    assert recon_data["cases_reconstructed"] == 2
    assert recon_data["events_reconstructed"] >= 4

    # 5. Check DFG and Variants
    dfg_res = await async_client.get(
        f"/api/v1/projects/{project_id}/process/{process_id}/dfg",
        headers=headers,
    )
    assert dfg_res.status_code == 200
    dfg = dfg_res.json()
    node_names = {n["name"] for n in dfg["nodes"]}
    assert "PO Created" in node_names
    assert "Invoice Received" in node_names
