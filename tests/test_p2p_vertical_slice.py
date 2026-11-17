"""Integration tests for the Phase 9 Procure-to-Pay (P2P) vertical slice."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.governance.models import (
    ActionStatus,
    ActionType,
    ApprovalStatus,
)
from corbel.domains.governance.schemas import (
    ActionExecuteRequest,
    ApprovalDecisionRequest,
    P2PVerticalSliceDemoRequest,
)
from corbel.domains.governance.service import GovernanceService
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_p2p_end_to_end_governance_flow(async_client: AsyncClient) -> None:
    """Test the complete P2P vertical slice:
    1. Operational anomaly detected as Finding (Invoice price/freight variance).
    2. Master Service Agreement ingested into RAG knowledge base.
    3. Governed investigation launched: verified facts separated from hypotheses.
    4. Deterministic financial impact calculation.
    5. Action recommended (HOLD_INVOICE).
    6. Human approval gate: signed with canonical payload hash.
    7. Consequential execution through TargetSystemAdapter verifying hash integrity.
    8. Complete, append-only PostgreSQL audit trail recorded.
    """
    user, _, org, project = await setup_test_org_and_project(async_client)
    user_id = uuid.UUID(user["id"])
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])

    session_factory = get_session_factory()

    # Step 1: Run full automated P2P Demo Slice via GovernanceService
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        gov_service = GovernanceService(session=session, tenancy_service=tenancy_service)

        demo_req = P2PVerticalSliceDemoRequest(
            supplier_name="Global Logistics Ltd",
            po_number="PO-4410",
            po_amount=10000.00,
            invoice_number="INV-99201",
            invoice_amount=14850.00,
            expected_variance=4850.00,
            auto_approve=False,
        )
        demo_resp = await gov_service.run_p2p_vertical_slice_demo(
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
            req=demo_req,
        )

        assert demo_resp.financial_impact_usd == 4850.00
        assert len(demo_resp.verified_facts) >= 2
        assert "unauthorized" in demo_resp.causal_hypothesis.lower()
        assert len(demo_resp.retrieved_document_snippets) >= 1
        assert demo_resp.recommendation.recommended_action_type == ActionType.HOLD_INVOICE.value
        assert demo_resp.action.status == ActionStatus.AWAITING_APPROVAL
        assert demo_resp.approval is not None
        assert demo_resp.approval.status == ApprovalStatus.PENDING

        approval_id = demo_resp.approval.id
        action_id = demo_resp.action.id

    # Step 2: Human Approver reviews and decides
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        gov_service = GovernanceService(session=session, tenancy_service=tenancy_service)

        dec_req = ApprovalDecisionRequest(
            decision=ApprovalStatus.APPROVED,
            rationale="Approved after verifying MSA lack of pre-approval for expedited air freight.",
        )
        appr_result = await gov_service.decide_approval(
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
            approval_id=approval_id,
            req=dec_req,
        )
        assert appr_result.status == ApprovalStatus.APPROVED.value
        assert appr_result.approved_payload_hash is not None

    # Step 3: Execute Consequential Governed Action
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        gov_service = GovernanceService(session=session, tenancy_service=tenancy_service)

        exec_req = ActionExecuteRequest(
            idempotency_key=f"idem-p2p-{uuid.uuid4().hex[:12]}",
        )
        exec_result = await gov_service.execute_action(
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
            action_id=action_id,
            req=exec_req,
        )
        assert exec_result.status == "SUCCEEDED"
        assert exec_result.adapter_response_json is not None
        assert exec_result.target_adapter_type == "SimulatedTargetAdapter"

    # Step 4: Verify Authoritative Audit Trail
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        gov_service = GovernanceService(session=session, tenancy_service=tenancy_service)

        events, total = await gov_service.list_audit_events(
            organization_id=org_id,
            project_id=project_id,
            user_id=user_id,
        )
        assert total >= 4
        action_types = [e.action_type for e in events]
        assert "INVESTIGATION_COMPLETED" in action_types
        assert "APPROVAL_GRANTED" in action_types
        assert "ACTION_EXECUTED" in action_types


@pytest.mark.anyio
async def test_p2p_demo_slice_api_endpoint(
    async_client: AsyncClient,
) -> None:
    """Test POST /api/v1/projects/{project_id}/demo/p2p-slice HTTP endpoint."""
    user, token, org, project = await setup_test_org_and_project(async_client)
    org_id = str(org["id"])
    project_id = str(project["id"])

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Organization-ID": org_id,
    }

    payload = {
        "supplier_name": "Apex Industrial Supplies",
        "po_number": "PO-10023",
        "po_amount": 15000.00,
        "invoice_number": "INV-7844",
        "invoice_amount": 16250.00,
        "expected_variance": 1250.00,
        "auto_approve": True,
    }

    res = await async_client.post(
        f"/api/v1/projects/{project_id}/demo/p2p-slice",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["financial_impact_usd"] == 1250.00
    assert len(data["verified_facts"]) >= 2
    assert len(data["retrieved_document_snippets"]) >= 1
    assert data["action"]["status"] == "EXECUTED"
    assert data["approval"]["status"] == "APPROVED"
    assert data["execution"] is not None
    assert data["execution"]["status"] == "SUCCEEDED"
    assert data["audit_events_count"] >= 4
