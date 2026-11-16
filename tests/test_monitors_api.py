"""HTTP integration tests for Phase 7: Adaptive Monitors & Exception Detection API endpoints."""

import io

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_monitors_and_findings_api_end_to_end(async_client: AsyncClient) -> None:
    """Full HTTP API test: create monitor -> add rule -> evaluate -> list findings -> acknowledge & resolve."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Upload a dataset so there's data to monitor
    csv_bytes = (
        b"po_number,supplier,total_amount\n"
        b"PO-8001,Alpha Vendor,4500.00\n"
        b"PO-8002,Beta Logistics,16000.00\n"
    )
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("purchase_orders.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"name": "purchase_orders_test"},
        headers=headers,
    )
    assert upload_res.status_code == 201

    # 2. Create Monitor
    create_res = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors",
        json={
            "name": "High Value PO Observer",
            "description": "Monitors procurement spending over 10k",
            "target_type": "ENTITY",
            "target_id": "PurchaseOrder",
            "rules": [
                {
                    "rule_code": "PO_THRESHOLD_10K",
                    "description": "Total amount > 10,000",
                    "severity": "HIGH",
                    "rule_type": "THRESHOLD",
                    "field_name": "total_amount",
                    "operator": "gt",
                    "threshold_value": 10000.0,
                }
            ],
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    mon = create_res.json()
    monitor_id = mon["id"]
    assert mon["name"] == "High Value PO Observer"
    assert len(mon["rules"]) == 1

    # 3. List Monitors
    list_res = await async_client.get(
        f"/api/v1/projects/{project_id}/monitors",
        headers=headers,
    )
    assert list_res.status_code == 200
    mon_list = list_res.json()
    assert len(mon_list) >= 1
    assert any(m["id"] == monitor_id for m in mon_list)

    # 4. Get Monitor Detail
    get_res = await async_client.get(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == monitor_id

    # 5. Add a secondary rule
    add_rule_res = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}/rules",
        json={
            "rule_code": "PO_WARN_5K",
            "description": "Total amount > 5,000",
            "severity": "MEDIUM",
            "rule_type": "THRESHOLD",
            "field_name": "total_amount",
            "operator": "gt",
            "threshold_value": 5000.0,
        },
        headers=headers,
    )
    assert add_rule_res.status_code == 201
    rule2_id = add_rule_res.json()["id"]

    # 6. Trigger Monitor Evaluation
    eval_res = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}/evaluate",
        json={"limit": 100},
        headers=headers,
    )
    assert eval_res.status_code == 200
    eval_data = eval_res.json()
    assert eval_data["status"] == "SUCCESS"
    assert eval_data["records_evaluated"] == 2
    # PO-8002 ($16,000) violates both rules -> 2 findings
    assert eval_data["findings_detected"] == 2

    # 7. List Findings (filtered by monitor)
    findings_res = await async_client.get(
        f"/api/v1/projects/{project_id}/findings?monitor_id={monitor_id}",
        headers=headers,
    )
    assert findings_res.status_code == 200
    findings = findings_res.json()
    assert len(findings) == 2
    finding_1 = findings[0]
    finding_id = finding_1["id"]

    # 8. Get Finding Detail
    f_detail_res = await async_client.get(
        f"/api/v1/projects/{project_id}/findings/{finding_id}",
        headers=headers,
    )
    assert f_detail_res.status_code == 200
    f_detail = f_detail_res.json()
    assert f_detail["id"] == finding_id
    assert f_detail["status"] == "OPEN"
    assert f_detail["verified_context_json"] is not None

    # 9. Patch Finding Status to ACKNOWLEDGED
    patch_res1 = await async_client.patch(
        f"/api/v1/projects/{project_id}/findings/{finding_id}/status",
        json={"status": "ACKNOWLEDGED"},
        headers=headers,
    )
    assert patch_res1.status_code == 200
    assert patch_res1.json()["status"] == "ACKNOWLEDGED"

    # 10. Patch Finding Status to RESOLVED with notes
    patch_res2 = await async_client.patch(
        f"/api/v1/projects/{project_id}/findings/{finding_id}/status",
        json={"status": "RESOLVED", "resolution_notes": "PO-8002 verified and accepted"},
        headers=headers,
    )
    assert patch_res2.status_code == 200
    assert patch_res2.json()["status"] == "RESOLVED"
    assert patch_res2.json()["resolution_notes"] == "PO-8002 verified and accepted"

    # 11. Delete Rule 2
    del_rule_res = await async_client.delete(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}/rules/{rule2_id}",
        headers=headers,
    )
    assert del_rule_res.status_code == 204

    # 12. Delete Monitor
    del_mon_res = await async_client.delete(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}",
        headers=headers,
    )
    assert del_mon_res.status_code == 204


@pytest.mark.anyio
async def test_list_evaluations_api_complete(async_client: AsyncClient) -> None:
    """Test GET /api/v1/projects/{project_id}/evaluations:

    - Empty history
    - Unauthorized access (no token)
    - Successful evaluation listing with full schema fields
    - Monitor ID filtering
    - Pagination boundaries (limit, offset)
    - Project isolation
    """
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Empty evaluation history
    empty_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations",
        headers=headers,
    )
    assert empty_res.status_code == 200
    assert empty_res.json() == []

    # 2. Unauthorized access (no token)
    unauth_res = await async_client.get(f"/api/v1/projects/{project_id}/evaluations")
    assert unauth_res.status_code == 401

    # 3. Setup dataset & monitor
    csv_bytes = b"inv_id,amount\nINV-001,500.0\nINV-002,1500.0\n"
    await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", io.BytesIO(csv_bytes), "text/csv")},
        data={"name": "invoices_dataset"},
        headers=headers,
    )

    mon_res = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors",
        json={
            "name": "Invoice High Amount Monitor",
            "target_type": "ENTITY",
            "target_id": "Invoice",
            "rules": [
                {
                    "rule_code": "INV_OVER_1000",
                    "severity": "HIGH",
                    "rule_type": "THRESHOLD",
                    "field_name": "amount",
                    "operator": "gt",
                    "threshold_value": 1000.0,
                }
            ],
        },
        headers=headers,
    )
    assert mon_res.status_code == 201
    monitor_id = mon_res.json()["id"]

    # 4. Trigger 2 evaluation runs
    eval1 = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}/evaluate",
        headers=headers,
    )
    assert eval1.status_code == 200

    eval2 = await async_client.post(
        f"/api/v1/projects/{project_id}/monitors/{monitor_id}/evaluate",
        headers=headers,
    )
    assert eval2.status_code == 200

    # 5. List evaluations
    list_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations",
        headers=headers,
    )
    assert list_res.status_code == 200
    evals = list_res.json()
    assert len(evals) == 2

    # Check schema fields match MonitorEvaluationResponse
    # evals[0] is the 2nd evaluation run (most recent, deduplicated findings)
    latest_eval = evals[0]
    assert latest_eval["project_id"] == project_id
    assert latest_eval["monitor_id"] == monitor_id
    assert latest_eval["status"] == "SUCCESS"
    assert latest_eval["records_evaluated"] == 2
    assert latest_eval["findings_detected"] == 0
    assert latest_eval["summary_json"]["deduplicated_existing"] == 1
    assert "execution_duration_ms" in latest_eval
    assert "evaluated_at" in latest_eval

    # evals[1] is the 1st evaluation run (new finding detected)
    first_eval = evals[1]
    assert first_eval["project_id"] == project_id
    assert first_eval["monitor_id"] == monitor_id
    assert first_eval["status"] == "SUCCESS"
    assert first_eval["records_evaluated"] == 2
    assert first_eval["findings_detected"] == 1

    # 6. Pagination boundaries
    page_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations?limit=1&offset=0",
        headers=headers,
    )
    assert page_res.status_code == 200
    page_items = page_res.json()
    assert len(page_items) == 1
    assert page_items[0]["id"] == evals[0]["id"]

    page2_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations?limit=1&offset=1",
        headers=headers,
    )
    assert page2_res.status_code == 200
    page2_items = page2_res.json()
    assert len(page2_items) == 1
    assert page2_items[0]["id"] == evals[1]["id"]

    offset_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations?limit=10&offset=50",
        headers=headers,
    )
    assert offset_res.status_code == 200
    assert offset_res.json() == []

    # 7. Monitor ID filtering
    mon_filter_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations?monitor_id={monitor_id}",
        headers=headers,
    )
    assert mon_filter_res.status_code == 200
    assert len(mon_filter_res.json()) == 2

    # Filter with non-existent monitor ID
    empty_mon_res = await async_client.get(
        f"/api/v1/projects/{project_id}/evaluations?monitor_id=00000000-0000-0000-0000-000000000000",
        headers=headers,
    )
    assert empty_mon_res.status_code == 200
    assert empty_mon_res.json() == []

    # 8. Project isolation: create a second project in the same organization
    proj2_res = await async_client.post(
        "/api/v1/projects",
        json={"name": "Isolated Project Beta", "description": "Separate scope"},
        headers=headers,
    )
    assert proj2_res.status_code == 201
    proj2_id = proj2_res.json()["id"]

    # Verify project 2 has 0 evaluations
    proj2_evals_res = await async_client.get(
        f"/api/v1/projects/{proj2_id}/evaluations",
        headers=headers,
    )
    assert proj2_evals_res.status_code == 200
    assert proj2_evals_res.json() == []
