"""Comprehensive integration and regression tests for Phase 12: Application Builder & Runtime."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from corbel.core.database import get_session_factory
from corbel.domains.app_builder.models import Application, ApplicationStatus
from corbel.domains.app_builder.schemas import (
    ApplicationDefinition,
    GovernedActionType,
    InteractionActionType,
)
from corbel.domains.app_builder.validator import ApplicationValidator
from corbel.domains.governance.models import (
    Action,
    ActionStatus,
    Approval,
    ApprovalStatus,
    AuditEvent,
)
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.use_case_architect.models import (
    UseCase,
    UseCaseSpecificationVersion,
)
from tests.test_dataset_ingestion import setup_test_org_and_project, unique_slug


@pytest.mark.anyio
async def test_create_blank_application(async_client: AsyncClient) -> None:
    """Verify an authorized user can create a blank application with a valid default blueprint."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    payload = {
        "name": "Custom Operations Portal",
        "description": "Tailored dashboard for monitoring supplier deliveries.",
    }
    res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == payload["name"]
    assert data["status"] == ApplicationStatus.DRAFT.value
    assert data["current_version"] == 0
    assert data["published_version"] is None
    assert data["draft_definition"] is not None
    assert len(data["draft_definition"]["pages"]) >= 1

    app_id = data["id"]

    # Verify retrieval
    get_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == app_id
    assert detail["name"] == payload["name"]


@pytest.mark.anyio
async def test_create_application_from_approved_use_case_spec(async_client: AsyncClient) -> None:
    """Verify transforming an approved Phase 11 Use-Case Specification into an Application blueprint."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # 1. Create and approve a Use Case in Phase 11 Architect via API
    uc_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={
            "title": "P2P Invoice Discrepancy Intelligence",
            "description": "Automate detection of supplier price variances across POs and invoices.",
        },
        headers=headers,
    )
    assert uc_res.status_code == 201
    uc_id = uc_res.json()["id"]

    # Generate specification
    gen_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/generate",
        headers=headers,
    )
    assert gen_res.status_code in (200, 201)

    # Approve specification
    appr_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/approve",
        headers=headers,
    )
    assert appr_res.status_code == 200

    # 2. Create Application from approved Use Case
    app_payload = {
        "name": "P2P Operational Intelligence Portal",
        "description": "Generated from approved solution specification.",
        "source_use_case_id": str(uc_id),
    }
    res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json=app_payload,
        headers=headers,
    )
    assert res.status_code == 201
    app_data = res.json()
    assert app_data["source_use_case_id"] == str(uc_id)
    assert app_data["source_specification_version"] == 1

    # Verify generated blueprint contains structured pages and components
    draft_def = app_data["draft_definition"]
    page_ids = [p["id"] for p in draft_def["pages"]]
    assert "page-dashboard" in page_ids
    assert "page-exceptions" in page_ids
    assert "page-governance" in page_ids

    # Find the hold invoice action button
    all_components = [
        c
        for p in draft_def["pages"]
        for s in p["sections"]
        for c in s["components"]
    ]
    types = [c["component_type"] for c in all_components]
    assert "METRIC_CARD" in types
    assert "DATA_TABLE" in types
    assert "APPROVAL_QUEUE" in types


@pytest.mark.anyio
async def test_update_application_draft_definition(async_client: AsyncClient) -> None:
    """Verify modifying and persisting application draft definition."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Draft App", "description": "Testing updates"},
        headers=headers,
    )
    app = create_res.json()
    app_id = app["id"]

    # Modify draft definition
    current_def = app["draft_definition"]
    current_def["name"] = "Updated Draft App Name"
    current_def["pages"][0]["sections"][0]["components"].append({
        "id": "new_text_comp",
        "component_type": "TEXT_BLOCK",
        "title": "Welcome Notice",
        "properties": {"content": "Welcome to the custom operations portal."},
    })

    update_res = await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": current_def},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_app = update_res.json()
    assert updated_app["name"] == "Updated Draft App Name"
    page_comps = updated_app["draft_definition"]["pages"][0]["sections"][0]["components"]
    assert any(c["id"] == "new_text_comp" for c in page_comps)


@pytest.mark.anyio
async def test_validation_engine_catches_errors_and_injection(async_client: AsyncClient) -> None:
    """Verify validation detects invalid components, orphan navigation targets, and unsafe code injection."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Validation Test App", "description": "Checking rules"},
        headers=headers,
    )
    app_id = create_res.json()["id"]

    # 1. Clean blueprint passes validation
    val_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/validate",
        headers=headers,
    )
    assert val_res.status_code == 200
    assert val_res.json()["is_valid"] is True

    # 2. Defective blueprint with orphan page navigation
    bad_def = create_res.json()["draft_definition"]
    bad_def["navigation"]["default_page_id"] = "non_existent_page_999"

    val_bad_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/validate",
        json=bad_def,
        headers=headers,
    )
    assert val_bad_res.status_code == 200
    bad_report = val_bad_res.json()
    assert bad_report["is_valid"] is False
    assert any("does not exist in pages list" in err["message"] for err in bad_report["errors"])

    # 3. Security check: Script injection attempt in properties
    injected_def = create_res.json()["draft_definition"]
    injected_def["pages"][0]["sections"][0]["components"][0]["properties"]["title"] = (
        "<script>alert('xss');</script>"
    )
    sec_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/validate",
        json=injected_def,
        headers=headers,
    )
    assert sec_res.status_code == 200
    sec_report = sec_res.json()
    assert sec_report["is_valid"] is False
    assert any("Prohibited executable script" in err["message"] or err["code"] == "UNSAFE_CODE_REJECTED" for err in sec_report["errors"])


@pytest.mark.anyio
async def test_publishing_lifecycle_and_immutability(async_client: AsyncClient) -> None:
    """Verify publishing snapshots an immutable version, keeps draft editable, and serves published runtime."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Publishing Test App", "description": "Verify immutability"},
        headers=headers,
    )
    app_id = create_res.json()["id"]

    # Publish Version 1
    pub_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Initial stable release."},
        headers=headers,
    )
    assert pub_res.status_code == 200
    pub_data = pub_res.json()
    assert pub_data["status"] == ApplicationStatus.PUBLISHED.value
    assert pub_data["published_version"] == 1
    assert pub_data["current_version"] == 1

    # Verify Runtime endpoint serves published version
    rt_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime",
        headers=headers,
    )
    assert rt_res.status_code == 200
    rt_data = rt_res.json()
    assert rt_data["version"] == 1
    assert rt_data["name"] == "Publishing Test App"

    # Now mutate the draft definition
    draft_def = pub_data["draft_definition"]
    draft_def["name"] = "Unpublished Work-in-Progress"
    await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": draft_def},
        headers=headers,
    )

    # Runtime MUST still return the published v1 definition, not the uncommitted draft
    rt_res_after = await async_client.get(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime",
        headers=headers,
    )
    assert rt_res_after.status_code == 200
    assert rt_res_after.json()["name"] == "Publishing Test App"  # Preserved immutable v1

    # Publish Version 2
    pub_v2_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Updated with renamed header."},
        headers=headers,
    )
    assert pub_v2_res.status_code == 200
    assert pub_v2_res.json()["published_version"] == 2

    # Check Version History list
    history_res = await async_client.get(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/versions",
        headers=headers,
    )
    assert history_res.status_code == 200
    versions = history_res.json()
    assert len(versions) == 2
    v_nums = [v["version"] for v in versions]
    assert 1 in v_nums and 2 in v_nums


@pytest.mark.anyio
async def test_tenant_isolation(async_client: AsyncClient) -> None:
    """Verify applications are strictly isolated by organization and project."""
    # Org A
    _, token_a, org_a, project_a = await setup_test_org_and_project(async_client)
    headers_a = {"Authorization": f"Bearer {token_a}", "X-Organization-ID": org_a["id"]}

    # Org B
    _, token_b, org_b, project_b = await setup_test_org_and_project(async_client)
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org_b["id"]}

    # Create app in Org A
    create_res = await async_client.post(
        f"/api/v1/projects/{project_a['id']}/applications",
        json={"name": "Org A Confidential App", "description": "Tenant A only"},
        headers=headers_a,
    )
    app_a_id = create_res.json()["id"]

    # Org B attempts to access Org A application -> Must return 404
    cross_res = await async_client.get(
        f"/api/v1/projects/{project_b['id']}/applications/{app_a_id}",
        headers=headers_b,
    )
    assert cross_res.status_code == 404

    # Org B attempts to publish Org A application -> Must return 404
    cross_pub = await async_client.post(
        f"/api/v1/projects/{project_b['id']}/applications/{app_a_id}/publish",
        json={"changelog": "Illegal cross-tenant publish"},
        headers=headers_b,
    )
    assert cross_pub.status_code == 404


@pytest.mark.anyio
async def test_rbac_publishing_authorization(async_client: AsyncClient) -> None:
    """Verify that ANALYST role cannot publish applications; PROJECT_LEAD is required."""
    _, token_admin, org, project = await setup_test_org_and_project(async_client)
    headers_admin = {"Authorization": f"Bearer {token_admin}", "X-Organization-ID": org["id"]}

    # 1. Create app
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "RBAC Test App", "description": "Testing publish role checks"},
        headers=headers_admin,
    )
    app_id = create_res.json()["id"]

    # 2. Register and Login Analyst user
    analyst_email = f"analyst-{unique_slug()}@corbel.internal"
    analyst_pass = "TestPass123!Safe"
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

    # Add analyst as org member and project member with ANALYST role
    add_org_member = await async_client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=headers_admin,
        json={"email": analyst_email, "role": "MEMBER"},
    )
    assert add_org_member.status_code == 201

    add_proj_member = await async_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=headers_admin,
        json={"user_id": analyst_id, "project_role": ProjectRole.ANALYST.value},
    )
    assert add_proj_member.status_code == 201

    headers_analyst = {"Authorization": f"Bearer {analyst_token}", "X-Organization-ID": org["id"]}

    # 3. Analyst can view application
    analyst_view = await async_client.get(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        headers=headers_analyst,
    )
    assert analyst_view.status_code == 200

    # 4. Analyst CANNOT publish application -> 403 Forbidden
    analyst_pub = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Unauthorized publish attempt"},
        headers=headers_analyst,
    )
    assert analyst_pub.status_code == 403


@pytest.mark.anyio
async def test_runtime_data_query_and_action_execution(async_client: AsyncClient) -> None:
    """Verify runtime queries data for components and executes governed actions with approval triggers."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create application with an Action Button and Data Table
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Runtime Engine Test", "description": "Testing queries and actions"},
        headers=headers,
    )
    app = create_res.json()
    app_id = app["id"]

    # Configure a component with STATIC data and an ACTION_BUTTON with approval
    draft_def = app["draft_definition"]
    draft_def["governance"]["approval_required_actions"] = ["HOLD_INVOICE"]
    draft_def["pages"][0]["sections"][0]["components"] = [
        {
            "id": "comp_static_table",
            "component_type": "DATA_TABLE",
            "title": "Configured Rules",
            "properties": {
                "columns": ["rule", "threshold"],
                "static_data": [{"rule": "Price Variance", "threshold": ">5%"}],
            },
            "data_binding": {
                "source_type": "STATIC",
                "limit": 10,
            },
        },
        {
            "id": "comp_hold_btn",
            "component_type": "ACTION_BUTTON",
            "title": "Hold Payment",
            "properties": {"label": "Hold Payment", "variant": "danger"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": "HOLD_INVOICE",
            },
        },
    ]

    put_res = await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": draft_def},
        headers=headers,
    )
    assert put_res.status_code == 200

    # Publish so it's live
    pub_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Ready for runtime actions."},
        headers=headers,
    )
    assert pub_res.status_code == 200

    # 1. Query runtime data for static table component
    data_req = {
        "page_id": draft_def["pages"][0]["id"],
        "component_id": "comp_static_table",
        "limit": 10,
    }
    data_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json=data_req,
        headers=headers,
    )
    assert data_res.status_code == 200
    res_json = data_res.json()
    assert res_json["component_id"] == "comp_static_table"
    assert len(res_json["rows"]) == 1
    assert res_json["rows"][0]["rule"] == "Price Variance"

    # 2. Execute Action requiring approval gate
    action_req = {
        "page_id": draft_def["pages"][0]["id"],
        "component_id": "comp_hold_btn",
        "action_type": InteractionActionType.EXECUTE_ACTION.value,
        "payload": {"invoice_id": "INV-9999", "reason": "Suspected duplicate"},
    }
    action_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/action",
        json=action_req,
        headers=headers,
    )
    assert action_res.status_code == 200
    act_out = action_res.json()
    assert act_out["requires_approval"] is True
    assert act_out["status"] == "PENDING_APPROVAL"
    approval_id = act_out["approval_id"]
    assert approval_id is not None

    # Verify Approval record exists in DB
    session_factory = get_session_factory()
    async with session_factory() as session:
        appr = (await session.execute(select(Approval).where(Approval.id == uuid.UUID(approval_id)))).scalar_one_or_none()
        assert appr is not None
        assert appr.status == ApprovalStatus.PENDING.value

    # 3. Approve Action through published portal
    approve_req = {
        "page_id": draft_def["pages"][0]["id"],
        "component_id": "comp_hold_btn",
        "action_type": "APPROVE_ACTION",
        "payload": {
            "approval_id": approval_id,
            "rationale": "Verified duplicate payment claim.",
        },
    }
    approve_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/action",
        json=approve_req,
        headers=headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "SUCCESS"

    # Verify Approval is now APPROVED
    async with session_factory() as session:
        appr_after = (await session.execute(select(Approval).where(Approval.id == uuid.UUID(approval_id)))).scalar_one_or_none()
        assert appr_after is not None
        assert appr_after.status == ApprovalStatus.APPROVED.value


@pytest.mark.anyio
async def test_audit_trail_logging(async_client: AsyncClient) -> None:
    """Verify all major application builder and runtime events emit authoritative audit records."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Audit Tracked App", "description": "Verify audit log"},
        headers=headers,
    )
    app_id = create_res.json()["id"]

    # Validate app
    await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/validate",
        headers=headers,
    )

    # Publish app
    await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Audited release."},
        headers=headers,
    )

    # Check AuditEvent records in database
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = (
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == uuid.UUID(org["id"]),
                AuditEvent.project_id == uuid.UUID(project["id"]),
            )
        )
        events = (await session.execute(stmt)).scalars().all()
        action_types = [e.action_type for e in events]

        assert "APPLICATION_CREATED" in action_types
        assert "APPLICATION_VALIDATED" in action_types
        assert "APPLICATION_PUBLISHED" in action_types


# =============================================================================
# Targeted Remediation Tests: DEF-012-001 through DEF-012-004
# =============================================================================


@pytest.mark.anyio
async def test_def_012_001_mandatory_consequential_action_approval(async_client: AsyncClient) -> None:
    """DEF-012-001: Mandatory consequential actions ALWAYS require approval regardless of blueprint config."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app
    res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Governance Bypass Prevention", "description": "Testing DEF-012-001"},
        headers=headers,
    )
    app = res.json()
    app_id = app["id"]
    draft_def = app["draft_definition"]

    # Explicitly clear approval_required_actions to simulate an author attempting to bypass approval
    draft_def["governance"]["approval_required_actions"] = []

    # Configure buttons for mandatory consequential actions and custom/unrecognized action
    draft_def["pages"][0]["sections"][0]["components"] = [
        {
            "id": "btn_hold",
            "component_type": "ACTION_BUTTON",
            "title": "Hold Invoice",
            "properties": {"label": "Hold Invoice"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": GovernedActionType.HOLD_INVOICE.value,
            },
        },
        {
            "id": "btn_block",
            "component_type": "ACTION_BUTTON",
            "title": "Block Vendor",
            "properties": {"label": "Block Vendor"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": GovernedActionType.BLOCK_VENDOR.value,
            },
        },
        {
            "id": "btn_dispute",
            "component_type": "ACTION_BUTTON",
            "title": "Dispute Charge",
            "properties": {"label": "Dispute Charge"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": GovernedActionType.DISPUTE_CHARGE.value,
            },
        },
        {
            "id": "btn_custom",
            "component_type": "ACTION_BUTTON",
            "title": "Custom Low Risk Action",
            "properties": {"label": "Custom"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": GovernedActionType.CUSTOM.value,
            },
        },
        {
            "id": "btn_invalid",
            "component_type": "ACTION_BUTTON",
            "title": "Unauthorized Action",
            "properties": {"label": "Exploit"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": "MALICIOUS_UNREGISTERED_ACTION",
            },
        },
    ]

    # 1. Validator checks allowlist
    val_res = ApplicationValidator.validate(ApplicationDefinition.model_validate(draft_def))
    invalid_codes = [e.code for e in val_res.errors]
    assert "INVALID_GOVERNED_ACTION_TYPE" in invalid_codes

    # Fix invalid button for publishing
    draft_def["pages"][0]["sections"][0]["components"].pop()
    put_res = await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": draft_def},
        headers=headers,
    )
    assert put_res.status_code == 200

    pub_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Published for testing DEF-012-001"},
        headers=headers,
    )
    assert pub_res.status_code == 200

    page_id = draft_def["pages"][0]["id"]
    session_factory = get_session_factory()

    # 2. Test mandatory actions: HOLD_INVOICE, BLOCK_VENDOR, DISPUTE_CHARGE
    for btn_id, act_type in [
        ("btn_hold", GovernedActionType.HOLD_INVOICE.value),
        ("btn_block", GovernedActionType.BLOCK_VENDOR.value),
        ("btn_dispute", GovernedActionType.DISPUTE_CHARGE.value),
    ]:
        act_res = await async_client.post(
            f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/action",
            json={
                "page_id": page_id,
                "component_id": btn_id,
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "payload": {"target_id": "TGT-001"},
            },
            headers=headers,
        )
        assert act_res.status_code == 200
        data = act_res.json()
        assert data["requires_approval"] is True
        assert data["status"] == "PENDING_APPROVAL"
        appr_id = data["approval_id"]
        assert appr_id is not None

        # Verify DB Action and Approval
        async with session_factory() as session:
            approval = (
                await session.execute(select(Approval).where(Approval.id == uuid.UUID(appr_id)))
            ).scalar_one_or_none()
            assert approval is not None
            assert approval.status == ApprovalStatus.PENDING.value

            action = (
                await session.execute(select(Action).where(Action.id == approval.action_id))
            ).scalar_one_or_none()
            assert action is not None
            assert action.action_type == act_type
            assert action.is_consequential is True
            assert action.status == ActionStatus.AWAITING_APPROVAL.value

    # 3. Test non-consequential action when NOT in approval_required_actions: succeeds without approval gate
    custom_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/action",
        json={
            "page_id": page_id,
            "component_id": "btn_custom",
            "action_type": InteractionActionType.EXECUTE_ACTION.value,
            "payload": {"param": "value"},
        },
        headers=headers,
    )
    assert custom_res.status_code == 200
    custom_data = custom_res.json()
    assert custom_data["requires_approval"] is False
    assert custom_data["status"] == "SUCCESS"


@pytest.mark.anyio
async def test_def_012_002_reject_unapproved_use_case_specification(async_client: AsyncClient) -> None:
    """DEF-012-002: Comprehensive specification approval integrity test covering all 7 checks."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    session_factory = get_session_factory()

    # Create Use Case in project
    uc_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases",
        json={"title": "Approval Integrity Test", "description": "Verifying strict version-level approval"},
        headers=headers,
    )
    assert uc_res.status_code == 201
    uc_id = uc_res.json()["id"]

    # 1. Generate Specification Version 1 (starts in REVIEW state)
    gen1_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/generate",
        headers=headers,
    )
    assert gen1_res.status_code in (200, 201)

    # Check 4: Review-state specification version 1 is rejected
    rev_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={
            "name": "Review Spec App",
            "description": "Must be rejected because spec v1 is in review",
            "source_use_case_id": uc_id,
            "source_specification_version": 1,
        },
        headers=headers,
    )
    assert rev_res.status_code == 400
    assert "has not been approved" in rev_res.json()["detail"]

    # Check 6: Rejection creates neither an application nor a misleading audit event
    async with session_factory() as session:
        app_stmt = select(Application).where(Application.name == "Review Spec App")
        assert (await session.execute(app_stmt)).scalar_one_or_none() is None

        audit_stmt = select(AuditEvent).where(
            AuditEvent.project_id == uuid.UUID(project["id"]),
            AuditEvent.action_type == "APPLICATION_CREATED",
            AuditEvent.affected_entity_id == "Review Spec App",
        )
        assert (await session.execute(audit_stmt)).scalar_one_or_none() is None

    # Approve Specification Version 1
    appr1_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/approve",
        headers=headers,
    )
    assert appr1_res.status_code == 200

    # Check 2: Current approved specification version (v1) can create an application
    app_v1_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={
            "name": "V1 Approved Application",
            "description": "Created from approved v1",
            "source_use_case_id": uc_id,
            "source_specification_version": 1,
        },
        headers=headers,
    )
    assert app_v1_res.status_code == 201
    assert app_v1_res.json()["source_specification_version"] == 1

    # Generate and approve Specification Version 2
    gen2_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/generate",
        headers=headers,
    )
    assert gen2_res.status_code in (200, 201)

    appr2_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/approve",
        headers=headers,
    )
    assert appr2_res.status_code == 200

    # Check 1: Approved historical specification version (v1) can still create an application
    hist_app_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={
            "name": "Historical V1 Application",
            "description": "Created from historical approved v1 after v2 exists",
            "source_use_case_id": uc_id,
            "source_specification_version": 1,
        },
        headers=headers,
    )
    assert hist_app_res.status_code == 201
    assert hist_app_res.json()["source_specification_version"] == 1

    # Generate Specification Version 3 (unapproved draft/review)
    gen3_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/use-cases/{uc_id}/specifications/generate",
        headers=headers,
    )
    assert gen3_res.status_code in (200, 201)

    # Force parent UseCase status to APPROVED in database to test the exact scenario
    async with session_factory() as session:
        uc_row = (await session.execute(select(UseCase).where(UseCase.id == uuid.UUID(uc_id)))).scalar_one()
        uc_row.status = "APPROVED"
        # Also ensure version 3 specification_json has status "DRAFT"
        spec3_row = (
            await session.execute(
                select(UseCaseSpecificationVersion).where(
                    UseCaseSpecificationVersion.use_case_id == uuid.UUID(uc_id),
                    UseCaseSpecificationVersion.version == 3,
                )
            )
        ).scalar_one()
        s3_json = dict(spec3_row.specification_json)
        s3_json["specification_status"] = "DRAFT"
        spec3_row.specification_json = s3_json
        await session.commit()

    # Check 3: Draft specification version 3 is rejected EVEN IF parent UseCase status is APPROVED
    draft_app_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={
            "name": "Draft Spec Application",
            "description": "Must be rejected despite parent status being APPROVED",
            "source_use_case_id": uc_id,
            "source_specification_version": 3,
        },
        headers=headers,
    )
    assert draft_app_res.status_code == 400
    assert "has not been approved" in draft_app_res.json()["detail"]

    # Check 5: Missing or invalid specification status is rejected
    async with session_factory() as session:
        spec3_row = (
            await session.execute(
                select(UseCaseSpecificationVersion).where(
                    UseCaseSpecificationVersion.use_case_id == uuid.UUID(uc_id),
                    UseCaseSpecificationVersion.version == 3,
                )
            )
        ).scalar_one()
        s3_json = dict(spec3_row.specification_json)
        # Remove specification_status entirely
        s3_json.pop("specification_status", None)
        spec3_row.specification_json = s3_json
        await session.commit()

    missing_status_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={
            "name": "Missing Status App",
            "description": "Must be rejected when specification_status is missing",
            "source_use_case_id": uc_id,
            "source_specification_version": 3,
        },
        headers=headers,
    )
    assert missing_status_res.status_code == 400
    assert "has not been approved" in missing_status_res.json()["detail"]

    # Check 7: Tenant and project isolation remains intact
    # Cross-project request using a different project ID must return 404
    other_proj_id = uuid.uuid4()
    cross_proj_res = await async_client.post(
        f"/api/v1/projects/{other_proj_id}/applications",
        json={
            "name": "Cross Project App",
            "description": "Unauthorized project reference",
            "source_use_case_id": uc_id,
        },
        headers=headers,
    )
    assert cross_proj_res.status_code == 404


@pytest.mark.anyio
async def test_def_012_003_component_visibility_roles_enforcement(async_client: AsyncClient) -> None:
    """DEF-012-003: Components configured with visibility_roles enforce role boundaries on backend and frontend."""
    _, lead_token, org, project = await setup_test_org_and_project(async_client)
    headers_lead = {"Authorization": f"Bearer {lead_token}", "X-Organization-ID": org["id"]}

    # Register and setup Analyst user in project
    analyst_email = f"analyst-{unique_slug()}@corbel.internal"
    analyst_pass = "TestPass123!Safe"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": analyst_email, "password": analyst_pass, "full_name": "Analyst User"},
    )
    analyst_id = reg_res.json()["id"]

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": analyst_email, "password": analyst_pass},
    )
    analyst_token = login_res.json()["access_token"]
    headers_analyst = {"Authorization": f"Bearer {analyst_token}", "X-Organization-ID": org["id"]}

    # Add to org and project as ANALYST
    await async_client.post(
        f"/api/v1/organizations/{org['id']}/members",
        headers=headers_lead,
        json={"email": analyst_email, "role": "MEMBER"},
    )
    await async_client.post(
        f"/api/v1/projects/{project['id']}/members",
        headers=headers_lead,
        json={"user_id": analyst_id, "project_role": ProjectRole.ANALYST.value},
    )

    # Create application with two components:
    # 1. comp_public: no visibility_roles restriction
    # 2. comp_restricted: visibility_roles = ["PROJECT_LEAD"]
    create_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Role Gated App", "description": "Testing component visibility roles"},
        headers=headers_lead,
    )
    app = create_res.json()
    app_id = app["id"]
    draft_def = app["draft_definition"]
    page_id = draft_def["pages"][0]["id"]

    draft_def["pages"][0]["sections"][0]["components"] = [
        {
            "id": "comp_public",
            "component_type": "DATA_TABLE",
            "title": "Public Data",
            "properties": {"columns": ["k", "v"], "static_data": [{"k": "status", "v": "normal"}]},
            "data_binding": {"source_type": "STATIC"},
            "visibility_roles": [],
        },
        {
            "id": "comp_restricted",
            "component_type": "DATA_TABLE",
            "title": "Confidential Governance Data",
            "properties": {"columns": ["secret", "value"], "static_data": [{"secret": "token", "value": "xyz"}]},
            "data_binding": {"source_type": "STATIC"},
            "interaction": {
                "action_type": InteractionActionType.EXECUTE_ACTION.value,
                "governed_action_type": GovernedActionType.CUSTOM.value,
            },
            "visibility_roles": [ProjectRole.PROJECT_LEAD.value],
        },
    ]

    await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": draft_def},
        headers=headers_lead,
    )
    await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "Role restricted version."},
        headers=headers_lead,
    )

    # 1. Analyst can query public component
    res_pub = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_public"},
        headers=headers_analyst,
    )
    assert res_pub.status_code == 200

    # 2. Analyst CANNOT query restricted component -> HTTP 403 Forbidden
    res_restr = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_restricted"},
        headers=headers_analyst,
    )
    assert res_restr.status_code == 403
    assert "not authorized to view component" in res_restr.json()["detail"]

    # 3. Analyst CANNOT trigger interaction on restricted component -> HTTP 403 Forbidden
    res_act = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/action",
        json={
            "page_id": page_id,
            "component_id": "comp_restricted",
            "action_type": InteractionActionType.EXECUTE_ACTION.value,
        },
        headers=headers_analyst,
    )
    assert res_act.status_code == 403
    assert "not authorized to interact with component" in res_act.json()["detail"]

    # 4. Project Lead CAN query restricted component -> HTTP 200 OK
    res_lead = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_restricted"},
        headers=headers_lead,
    )
    assert res_lead.status_code == 200
    assert len(res_lead.json()["rows"]) == 1


@pytest.mark.anyio
async def test_def_012_004_audit_trail_offset_pagination(async_client: AsyncClient) -> None:
    """DEF-012-004: AUDIT_TRAIL component query correctly respects offset and limit."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # Create app and perform operations that generate audit trail records
    app_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications",
        json={"name": "Audit Pagination App", "description": "Testing pagination offsets"},
        headers=headers,
    )
    app = app_res.json()
    app_id = app["id"]
    draft_def = app["draft_definition"]
    page_id = draft_def["pages"][0]["id"]

    # Configure AUDIT_TRAIL component
    draft_def["pages"][0]["sections"][0]["components"] = [
        {
            "id": "comp_audit_log",
            "component_type": "AUDIT_TRAIL_VIEW",
            "title": "Operational Audit Log",
            "data_binding": {
                "source_type": "AUDIT_TRAIL",
                "limit": 2,
                "offset": 0,
            },
        }
    ]

    await async_client.put(
        f"/api/v1/projects/{project['id']}/applications/{app_id}",
        json={"draft_definition": draft_def},
        headers=headers,
    )

    # Perform multiple actions to generate at least 4 audit events
    await async_client.post(f"/api/v1/projects/{project['id']}/applications/{app_id}/validate", headers=headers)
    await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/publish",
        json={"changelog": "V1"},
        headers=headers,
    )

    # Query page 1 (limit 2, offset 0)
    page1_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_audit_log", "limit": 2, "offset": 0},
        headers=headers,
    )
    assert page1_res.status_code == 200
    p1_data = page1_res.json()
    assert len(p1_data["rows"]) == 2
    assert p1_data["total_rows"] >= 3

    # Query page 2 (limit 2, offset 2)
    page2_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_audit_log", "limit": 2, "offset": 2},
        headers=headers,
    )
    assert page2_res.status_code == 200
    p2_data = page2_res.json()
    assert len(p2_data["rows"]) >= 1
    assert p2_data["total_rows"] == p1_data["total_rows"]

    # Verify rows on page 1 and page 2 are distinct
    assert p1_data["rows"][0] != p2_data["rows"][0]

    # Query out-of-bounds offset
    empty_page_res = await async_client.post(
        f"/api/v1/projects/{project['id']}/applications/{app_id}/runtime/data",
        json={"page_id": page_id, "component_id": "comp_audit_log", "limit": 2, "offset": 1000},
        headers=headers,
    )
    assert empty_page_res.status_code == 200
    assert len(empty_page_res.json()["rows"]) == 0
    assert empty_page_res.json()["total_rows"] == p1_data["total_rows"]
