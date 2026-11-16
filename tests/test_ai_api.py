"""Tests for Phase 8 FastAPI endpoints."""

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_durable_tasks_api_endpoints(async_client: AsyncClient) -> None:
    """Test task scheduling, status lookup, and cancellation API endpoints."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Create task
    create_res = await async_client.post(
        f"/api/v1/projects/{project_id}/tasks",
        headers=headers,
        json={
            "task_type": "DATASET_IMPORT",
            "input_data": {"filename": "invoices.csv", "batch_size": 500},
            "max_retries": 3,
        },
    )
    assert create_res.status_code == 201
    task = create_res.json()
    task_id = task["id"]
    assert task["status"] == "PENDING"
    assert task["task_type"] == "DATASET_IMPORT"
    assert task["checkpoint_data_json"] == {"input": {"filename": "invoices.csv", "batch_size": 500}}

    # 2. Get task
    get_res = await async_client.get(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id

    # 3. Cancel task
    cancel_res = await async_client.post(
        f"/api/v1/projects/{project_id}/tasks/{task_id}/cancel",
        headers=headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["cancellation_requested"] is True
    # Pending tasks transition directly to CANCELLED
    assert cancel_res.json()["status"] == "CANCELLED"


@pytest.mark.anyio
async def test_workflow_state_machine_api_endpoints(async_client: AsyncClient) -> None:
    """Test bounded state machine execution and workflow inspection endpoints."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # Run Data Discovery State Machine
    run_res = await async_client.post(
        f"/api/v1/projects/{project_id}/workflows/run",
        headers=headers,
        json={
            "workflow_type": "DATA_DISCOVERY",
            "input_parameters": {"dataset_name": "raw_invoices"},
            "max_steps": 8,
        },
    )
    assert run_res.status_code == 200
    wf_result = run_res.json()
    assert wf_result["status"] == "COMPLETED"
    assert wf_result["steps_executed"] == 5
    assert wf_result["workflow_type"] == "DATA_DISCOVERY"
    workflow_id = wf_result["workflow_id"]

    # Retrieve workflow record
    get_wf_res = await async_client.get(
        f"/api/v1/projects/{project_id}/workflows/{workflow_id}",
        headers=headers,
    )
    assert get_wf_res.status_code == 200
    wf_record = get_wf_res.json()
    assert wf_record["id"] == workflow_id
    assert wf_record["status"] == "COMPLETED"
    assert wf_record["current_state"] == "COMPLETED"


@pytest.mark.anyio
async def test_prompt_governance_api_endpoints(async_client: AsyncClient) -> None:
    """Test prompt definition creation, versioning, lifecycle transitions, and rollback."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # 1. Create prompt definition
    create_def_res = await async_client.post(
        "/api/v1/prompts",
        headers=headers,
        json={
            "name": "p2p_price_variance_investigation",
            "workflow_association": "INVESTIGATION",
            "description": "Prompt investigating invoice price variances",
            "initial_version": {
                "version_tag": "1.0.0",
                "template_text": "Investigate case {case_id} for variance.",
                "model_compatibility": "claude-3-5-sonnet",
            },
        },
    )
    assert create_def_res.status_code == 201
    p_def = create_def_res.json()
    prompt_id = p_def["id"]
    assert len(p_def["versions"]) == 1
    v1 = p_def["versions"][0]
    assert v1["lifecycle_state"] == "DRAFT"
    assert v1["version_tag"] == "1.0.0"

    # 2. List prompt definitions
    list_res = await async_client.get(
        "/api/v1/prompts",
        headers=headers,
    )
    assert list_res.status_code == 200
    assert any(p["id"] == prompt_id for p in list_res.json())

    # 3. Transition v1: DRAFT -> TEST -> EVALUATE -> APPROVE -> DEPLOY
    for next_state in ["TEST", "EVALUATE", "APPROVE", "DEPLOY"]:
        trans_res = await async_client.post(
            f"/api/v1/prompts/versions/{v1['id']}/transition",
            headers=headers,
            json={"target_state": next_state, "rationale": f"Moving to {next_state}"},
        )
        assert trans_res.status_code == 200
        assert trans_res.json()["lifecycle_state"] == next_state

    # 4. Create v2
    v2_res = await async_client.post(
        f"/api/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "version_tag": "2.0.0",
            "template_text": "Examine case {case_id} with strict evidence standards.",
            "model_compatibility": "claude-3-5-sonnet",
        },
    )
    assert v2_res.status_code == 201
    v2 = v2_res.json()
    assert v2["lifecycle_state"] == "DRAFT"

    # Transition v2 to DEPLOY
    for next_state in ["TEST", "EVALUATE", "APPROVE", "DEPLOY"]:
        await async_client.post(
            f"/api/v1/prompts/versions/{v2['id']}/transition",
            headers=headers,
            json={"target_state": next_state, "rationale": f"V2 transition {next_state}"},
        )

    # 5. Rollback to v1
    rb_res = await async_client.post(
        f"/api/v1/prompts/{prompt_id}/rollback",
        headers=headers,
        json={"target_version_tag": "1.0.0", "rationale": "Rollback due to v2 regression"},
    )
    assert rb_res.status_code == 200
    assert rb_res.json()["version_tag"] == "1.0.0"
    assert rb_res.json()["lifecycle_state"] == "DEPLOY"


@pytest.mark.anyio
async def test_ai_cost_summary_api(async_client: AsyncClient) -> None:
    """Test cost summary endpoint."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    res = await async_client.get(
        f"/api/v1/projects/{project_id}/ai/costs/summary",
        headers=headers,
    )
    assert res.status_code == 200
    summary = res.json()
    assert "total_cost_usd" in summary
    assert "cost_per_successful_task" in summary
    assert "breakdown_by_workflow" in summary


@pytest.mark.anyio
async def test_evaluation_dataset_and_run_api(async_client: AsyncClient) -> None:
    """Test creating evaluation datasets and running regression benchmarks via API."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}

    # 1. Create dataset
    ds_res = await async_client.post(
        "/api/v1/evaluations/datasets",
        headers=headers,
        json={
            "name": "API P2P Regression Suite",
            "version": "1.0.0",
            "domain": "procure-to-pay",
            "test_cases": [
                {
                    "test_case_id": "API-TC-01",
                    "input_prompt": "Inspect purchase order PO-10023",
                    "expected_keyword": "purchase",
                }
            ],
            "is_system": False,
        },
    )
    assert ds_res.status_code == 201
    dataset = ds_res.json()
    dataset_id = dataset["id"]

    # 2. List datasets
    list_ds_res = await async_client.get(
        "/api/v1/evaluations/datasets",
        headers=headers,
    )
    assert list_ds_res.status_code == 200
    assert any(d["id"] == dataset_id for d in list_ds_res.json())

    # 3. Trigger evaluation run
    run_res = await async_client.post(
        "/api/v1/evaluations/runs",
        headers=headers,
        json={
            "evaluation_dataset_id": dataset_id,
            "target_model_name": "claude-3-5-sonnet",
        },
    )
    assert run_res.status_code == 201
    run = run_res.json()
    run_id = run["id"]
    assert run["status"] == "COMPLETED"
    assert run["summary_metrics_json"]["total_test_cases"] == 1
    assert run["summary_metrics_json"]["passed_test_cases"] == 1

    # 4. Get evaluation run detail
    get_run_res = await async_client.get(
        f"/api/v1/evaluations/runs/{run_id}",
        headers=headers,
    )
    assert get_run_res.status_code == 200
    run_detail = get_run_res.json()
    assert run_detail["id"] == run_id
    assert len(run_detail["results"]) == 1
    assert run_detail["results"][0]["passed"] is True
