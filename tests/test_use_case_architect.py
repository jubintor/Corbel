"""Tests for Phase 11: Use-Case Architect."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from corbel.core.database import get_session_factory
from corbel.domains.governance.models import AuditEvent
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.use_case_architect.models import UseCaseStatus
from corbel.domains.use_case_architect.schemas import UseCaseSpecification
from tests.test_dataset_ingestion import setup_test_org_and_project, unique_slug


@pytest.mark.anyio
async def test_create_and_save_incomplete_use_case(async_client: AsyncClient) -> None:
    """Verify that an authorized user can create and save an incomplete use case draft."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    payload = {
        "title": "Inventory Stockout Early Warning",
        "description": "We need to predict when parts will stock out across our regional hubs before customer orders fail.",
    }
    res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == payload["title"]
    assert data["status"] in (UseCaseStatus.DRAFT.value, UseCaseStatus.DISCOVERY.value)
    assert data["current_version"] == 0
    use_case_id = data["id"]

    # Verify retrieval
    get_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == use_case_id
    assert len(detail["messages"]) >= 1  # User initial description persisted
    assert detail["latest_specification"] is None


@pytest.mark.anyio
async def test_multi_turn_discovery_and_distinguishing_facts_vs_assumptions(
    async_client: AsyncClient,
) -> None:
    """Verify discovery captures requirements, generates open questions, and separates facts vs assumptions."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # 1. Create use case
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "Vendor SLA Compliance Monitor",
            "description": "Monitor delivery time and damaged goods receipts across our top 50 suppliers.",
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    use_case_id = create_res.json()["id"]

    # 2. Post discovery clarification answer
    msg_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/messages",
        json={
            "message_text": (
                "The threshold for delivery delay is strictly 3 business days. "
                "The primary source system is the Warehouse Management DB on PostgreSQL. "
                "Operations leads and Procurement managers need weekly automated digests."
            )
        },
        headers=headers,
    )
    assert msg_res.status_code == 200
    turn_data = msg_res.json()
    assert turn_data["user_message"]["message_text"].startswith("The threshold")
    asst_msg = turn_data["assistant_message"]
    assert asst_msg["extracted_requirements"] is not None

    reqs = asst_msg["extracted_requirements"]
    assert len(reqs["confirmed_requirements"]) >= 1
    assert len(reqs["unverified_assumptions"]) >= 1
    # Distinguish facts from assumptions: confirmed requirements must not match assumptions
    assert reqs["confirmed_requirements"] != reqs["unverified_assumptions"]
    assert asst_msg["clarification_questions"] is not None


@pytest.mark.anyio
async def test_specification_synthesis_schema_validation_and_versioning(
    async_client: AsyncClient,
) -> None:
    """Verify specification generation strictly validates all 22 required fields and tracks version history."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create use case
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "Logistics Route Exception Detection",
            "description": "Identify freight carriers billing unapproved fuel surcharges exceeding 10% of contract rate.",
        },
        headers=headers,
    )
    use_case_id = create_res.json()["id"]

    # Synthesize Version 1
    gen1_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/generate",
        headers=headers,
    )
    assert gen1_res.status_code == 201
    spec1 = gen1_res.json()

    # Validate against Pydantic schema
    validated_spec1 = UseCaseSpecification.model_validate(spec1)
    assert validated_spec1.version_number == 1
    assert validated_spec1.specification_status == "REVIEW"
    assert len(validated_spec1.implementation_plan) >= 1
    assert len(validated_spec1.risks_and_dependencies) >= 1
    assert len(validated_spec1.architecture_rationale_and_alternatives.alternatives_considered) >= 1

    # Check that use case status updated to REVIEW
    uc_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}",
        headers=headers,
    )
    assert uc_res.json()["status"] == UseCaseStatus.REVIEW.value
    assert uc_res.json()["current_version"] == 1

    # Synthesize Version 2
    gen2_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/generate",
        headers=headers,
    )
    assert gen2_res.status_code == 201
    spec2 = gen2_res.json()
    assert spec2["version_number"] == 2

    # Check version history listing
    list_specs_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications",
        headers=headers,
    )
    assert list_specs_res.status_code == 200
    versions = list_specs_res.json()
    assert len(versions) == 2
    assert versions[0]["version"] == 2
    assert versions[1]["version"] == 1

    # Compare revisions
    diff_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/compare?v1=1&v2=2",
        headers=headers,
    )
    assert diff_res.status_code == 200
    diff = diff_res.json()
    assert diff["v1"] == 1
    assert diff["v2"] == 2
    assert "summary" in diff


@pytest.mark.anyio
async def test_technical_architecture_reasoning_and_retrieval_selection(
    async_client: AsyncClient,
) -> None:
    """Verify that architecture recommendation avoids unnecessary agents/RAG and explains rationale."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "Batch Invoice Variance Calculations",
            "description": "Calculate exact mathematical line-item price variances between purchase orders and supplier invoices.",
        },
        headers=headers,
    )
    use_case_id = create_res.json()["id"]

    gen_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/generate",
        headers=headers,
    )
    assert gen_res.status_code == 201
    spec = gen_res.json()

    rationale = spec["architecture_rationale_and_alternatives"]
    # Confirms deterministic components are explicitly recommended
    assert len(rationale["deterministic_components"]) >= 1
    # Confirms reasons why alternatives (such as unconstrained agents) were rejected
    assert len(rationale["alternatives_considered"]) >= 1
    for alt in rationale["alternatives_considered"]:
        assert len(alt["rejection_reason"]) > 5
    # Confirms estimates are labeled as estimates
    estimates = spec["estimates_and_assumptions"]["delivery_estimates"]
    assert any("estimate" in e.lower() for e in estimates)


@pytest.mark.anyio
async def test_specification_approval_authorization_and_audit(
    async_client: AsyncClient,
) -> None:
    """Verify authorization gates on specification approval and native audit trail recording."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create use case & generate spec
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "Procurement Fraud Detection",
            "description": "Detect split purchase orders structured to evade single-signer approval limits.",
        },
        headers=headers,
    )
    use_case_id = create_res.json()["id"]

    await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/generate",
        headers=headers,
    )

    # 1. Register an unauthorized user with role ANALYST
    analyst_email = f"analyst_{unique_slug('usr')}@example.com"
    analyst_pass = "AnalystSecurePassword123!"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": analyst_email,
            "password": analyst_pass,
            "full_name": "Analyst User",
        },
    )
    assert reg_res.status_code == 201
    analyst_id = reg_res.json()["id"]

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": analyst_email,
            "password": analyst_pass,
        },
    )
    assert login_res.status_code == 200
    analyst_token = login_res.json()["access_token"]

    # Add analyst as project member with ANALYST role
    await async_client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=headers,
        json={"user_id": analyst_id, "role": "MEMBER"},
    )
    await async_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=headers,
        json={"user_id": analyst_id, "role": ProjectRole.ANALYST.value},
    )

    # Analyst attempts to approve -> Must be rejected with 403 Forbidden
    analyst_headers = {
        "Authorization": f"Bearer {analyst_token}",
        "X-Organization-ID": org["id"],
    }
    unauth_approve_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/approve",
        headers=analyst_headers,
    )
    assert unauth_approve_res.status_code == 403

    # Authorized user (Lead/Admin) approves
    auth_approve_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/approve",
        headers=headers,
    )
    assert auth_approve_res.status_code == 200
    appr_data = auth_approve_res.json()
    assert appr_data["status"] == UseCaseStatus.APPROVED.value
    assert appr_data["approved_by"] is not None
    assert appr_data["approved_at"] is not None

    # Verify native Phase 10 audit log
    async_session = get_session_factory()
    async with async_session() as session:
        audit_stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == uuid.UUID(org["id"]),
                AuditEvent.project_id == uuid.UUID(project["id"]),
            )
            .order_by(AuditEvent.timestamp.desc())
        )
        audit_events = (await session.execute(audit_stmt)).scalars().all()
        action_types = [e.action_type for e in audit_events]
        assert "USE_CASE_CREATED" in action_types
        assert "SPECIFICATION_GENERATED" in action_types
        assert "SPECIFICATION_APPROVED" in action_types


@pytest.mark.anyio
async def test_tenant_isolation_cross_organization_denial(
    async_client: AsyncClient,
) -> None:
    """Verify that use cases and specifications are strictly isolated by organization and project."""
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)

    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    # Create Use Case in Org A
    res_a = await async_client.post(
        f"/api/v1/projects/{project_a['id']}/use-cases",
        json={"title": "Org A Confidential Project", "description": "Highly confidential use case in Org A."},
        headers=headers_a,
    )
    assert res_a.status_code == 201
    use_case_a_id = res_a.json()["id"]

    # Org B user attempts to retrieve Org A use case in Project A
    cross_res = await async_client.get(
        f"/api/v1/projects/{project_a['id']}/use-cases/{use_case_a_id}",
        headers=headers_b,
    )
    assert cross_res.status_code in (403, 404)

    # Org B user attempts to access Org A use case by passing Project B URL
    cross_res2 = await async_client.get(
        f"/api/v1/projects/{project_b['id']}/use-cases/{use_case_a_id}",
        headers=headers_b,
    )
    assert cross_res2.status_code == 404


@pytest.mark.anyio
async def test_p2p_reference_demonstration_scenario(
    async_client: AsyncClient,
) -> None:
    """End-to-end demonstration of the Procure-to-Pay vertical slice in the Use-Case Architect."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # 1. Business user describes P2P problem statement
    p2p_problem = (
        "We are experiencing recurring price variance discrepancies and delayed approvals in Procure-to-Pay. "
        "Suppliers are invoicing us at higher unit prices than stated on approved Purchase Orders, and our Accounts "
        "Payable team spends hours manually cross-referencing Goods Receipts and PDF vendor contracts."
    )
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "Procurement Exception and Invoice Discrepancy Intelligence",
            "description": p2p_problem,
        },
        headers=headers,
    )
    assert create_res.status_code == 201
    use_case = create_res.json()
    use_case_id = use_case["id"]
    assert use_case["status"] == UseCaseStatus.DISCOVERY.value

    # 2. User answers clarifying question regarding tolerances and approval gates
    ans_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/messages",
        json={
            "message_text": (
                "Price variances exceeding 5% or $500 must trigger an investigation. "
                "The Procurement Lead must approve credit note requests before vendor notification."
            )
        },
        headers=headers,
    )
    assert ans_res.status_code == 200

    # 3. Generate structured specification
    spec_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/generate",
        headers=headers,
    )
    assert spec_res.status_code == 201
    spec = spec_res.json()

    # 4. Verify P2P solution specification elements
    assert "Purchase Orders" in spec["inputs_and_outputs"]["inputs"]
    assert "Supplier Invoices" in spec["inputs_and_outputs"]["inputs"]
    assert any("Price Variance" in out for out in spec["inputs_and_outputs"]["outputs"])
    assert any("Credit Note" in act for act in spec["inputs_and_outputs"]["actions"])
    assert any("approval" in req.lower() for req in spec["human_approval_requirements"])
    assert spec["risk_level"] in ("MEDIUM", "HIGH")

    # 5. Review & Formally Approve
    appr_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{use_case_id}/specifications/approve",
        headers=headers,
    )
    assert appr_res.status_code == 200
    final_uc = appr_res.json()
    assert final_uc["status"] == UseCaseStatus.APPROVED.value
    assert final_uc["approved_by"] is not None
