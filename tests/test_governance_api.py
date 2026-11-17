"""API integration tests for Phase 9: Governed Investigation, Approvals & RAG."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.monitors.models import (
    Finding,
    FindingStatus,
    Monitor,
    MonitorStatus,
    MonitorTargetType,
)
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_governance_investigation_and_approval_api_flow(async_client: AsyncClient) -> None:
    """Test full HTTP API flow for document ingestion, investigation, approval, and execution."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    project_id = project["id"]
    org_id = org["id"]

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": org_id,
    }

    # 1. Ingest Document for RAG
    doc_payload = {
        "title": "Vendor Terms",
        "document_type": "CONTRACT",
        "file_name": "vendor_terms.txt",
        "raw_text": (
            "Clause 4. Freight and Surcharges\n"
            "All expedited shipping surcharges must be pre-approved in writing. "
            "Unapproved freight charges exceeding $100.00 will result in an invoice payment hold."
        ),
    }
    doc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/documents",
        json=doc_payload,
        headers=headers,
    )
    assert doc_res.status_code == 201
    doc_data = doc_res.json()
    assert doc_data["title"] == "Vendor Terms"
    assert doc_data["chunk_count"] >= 1

    # 2. Query RAG Document
    query_res = await async_client.post(
        f"/api/v1/projects/{project_id}/documents/query",
        json={"query_text": "freight surcharge shipping payment hold", "top_k": 3},
        headers=headers,
    )
    assert query_res.status_code == 200
    q_data = query_res.json()
    assert q_data["total_retrieved"] >= 1
    assert "freight" in q_data["results"][0]["chunk_text"].lower()

    # 3. Create Monitor and Finding in DB
    session_factory = get_session_factory()
    async with session_factory() as session:
        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id),
            name="API Test Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=uuid.UUID(project_id),
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-API-001",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.OPEN.value,
            summary="Invoice INV-API-001 exceeds PO amount by $1,250.00",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="16250.00",
            threshold_value="15000.00",
        )
        session.add(finding)
        await session.commit()
        finding_id = str(finding.id)

    # 4. Initiate Investigation
    inv_res = await async_client.post(
        f"/api/v1/projects/{project_id}/investigations",
        json={"finding_id": finding_id, "title": "API Investigation INV-API-001"},
        headers=headers,
    )
    assert inv_res.status_code == 201
    inv_data = inv_res.json()
    inv_id = inv_data["id"]
    assert inv_data["status"] == "COMPLETED"
    assert inv_data["financial_impact_usd"] == 1250.00
    assert len(inv_data["recommendations"]) == 1
    assert len(inv_data["actions"]) == 1
    action_id = inv_data["actions"][0]["id"]

    # 5. Fetch Evidence
    ev_res = await async_client.get(
        f"/api/v1/projects/{project_id}/investigations/{inv_id}/evidence",
        headers=headers,
    )
    assert ev_res.status_code == 200
    evidence = ev_res.json()
    assert len(evidence) >= 1

    # 6. List Approvals
    appr_res = await async_client.get(
        f"/api/v1/projects/{project_id}/approvals",
        headers=headers,
    )
    assert appr_res.status_code == 200
    approvals = appr_res.json()
    assert len(approvals) >= 1
    approval_id = approvals[0]["id"]
    assert approvals[0]["status"] == "PENDING"

    # 7. Decide Approval (Approve)
    decide_res = await async_client.post(
        f"/api/v1/projects/{project_id}/approvals/{approval_id}/decide",
        json={"decision": "APPROVED", "rationale": "Verified variance against contract terms."},
        headers=headers,
    )
    assert decide_res.status_code == 200
    decide_data = decide_res.json()
    assert decide_data["status"] == "APPROVED"
    assert decide_data["approved_payload_hash"] is not None

    # 8. Execute Action
    idempotency_key = f"API-EXEC-{uuid.uuid4().hex}"
    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/actions/{action_id}/execute",
        json={"idempotency_key": idempotency_key},
        headers=headers,
    )
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "SUCCEEDED"
    assert exec_data["adapter_response_json"]["operation"] == "HOLD_INVOICE"
    assert exec_data["dispatched_payload_hash"] == decide_data["approved_payload_hash"]

    # 9. List Audit Events
    audit_res = await async_client.get(
        f"/api/v1/projects/{project_id}/audit-events",
        headers=headers,
    )
    assert audit_res.status_code == 200
    audit_data = audit_res.json()
    assert audit_data["total"] >= 4


@pytest.mark.anyio
async def test_cross_tenant_isolation_enforcement(async_client: AsyncClient) -> None:
    """Test that users from Org A cannot access or manipulate Org B's investigations or approvals."""
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)

    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "X-Organization-ID": org_b["id"],
    }

    # User B attempts to access Org A's project investigations
    res = await async_client.get(
        f"/api/v1/projects/{project_a['id']}/investigations",
        headers=headers_b,
    )
    assert res.status_code in [403, 404]

    # User B attempts to query Org A's RAG documents
    res_doc = await async_client.get(
        f"/api/v1/projects/{project_a['id']}/documents",
        headers=headers_b,
    )
    assert res_doc.status_code in [403, 404]
