"""Integration tests for OntologyService and API workflows (Phase 4)."""

import pytest
from httpx import AsyncClient

from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_seed_p2p_ontology_endpoint(async_client: AsyncClient) -> None:
    """Verify seeding P2P ontology creates the 4 core business objects and relationships."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/seed-p2p",
        headers=headers,
    )
    assert res.status_code == 201
    objects = res.json()
    assert len(objects) == 4
    names = {o["name"] for o in objects}
    assert names == {"Supplier", "PurchaseOrder", "GoodsReceipt", "Invoice"}

    # Check graph endpoint
    graph_res = await async_client.get(
        f"/api/v1/projects/{project_id}/ontology/graph",
        headers=headers,
    )
    assert graph_res.status_code == 200
    graph = graph_res.json()
    assert graph["total_objects"] == 4
    assert graph["total_relationships"] == 4
    assert len(graph["nodes"]) == 4
    assert len(graph["edges"]) == 4


@pytest.mark.anyio
async def test_semantic_discovery_and_accept_lifecycle(async_client: AsyncClient) -> None:
    """Verify end-to-end workflow: upload dataset -> discover mappings -> inspect suggestions -> accept mapping."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Seed P2P ontology
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # 2. Upload synthetic P2P Invoice dataset
    csv_content = (
        b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\n"
        b"INV-101,SUP-1,PO-991,2026-10-01,1500.00,USD,PAID\n"
        b"INV-102,SUP-2,PO-992,2026-10-02,3200.50,USD,PENDING\n"
    )
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert upload_res.status_code == 201
    dataset = upload_res.json()
    dataset_id = dataset["id"]
    version_id = dataset["latest_version"]["id"]

    # 3. Find the Invoice Business Object
    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")
    invoice_obj_id = invoice_obj["id"]

    # 4. Run Semantic Discovery
    disc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "business_object_id": invoice_obj_id,
        },
        headers=headers,
    )
    assert disc_res.status_code == 200
    disc_data = disc_res.json()
    suggestions = disc_data["suggestions"]
    assert len(suggestions) > 0

    # Verify suggestions are unconfirmed (status == SUGGESTED)
    assert all(s["status"] == "SUGGESTED" for s in suggestions)

    # Check that known alias po_number -> po_id was proposed
    po_suggestion = next(s for s in suggestions if s["column_name"] == "po_number")
    assert po_suggestion["property_name"] == "po_id"
    assert po_suggestion["confidence"] >= 0.85

    # 5. Accept a suggestion
    accept_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/mappings/{po_suggestion['id']}/accept",
        headers=headers,
    )
    assert accept_res.status_code == 200
    accepted = accept_res.json()
    assert accepted["status"] == "CONFIRMED"

    # 6. Verify property now reflects confirmed source mapping
    inv_details = (await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects/{invoice_obj_id}", headers=headers)).json()
    po_prop = next(p for p in inv_details["properties"] if p["name"] == "po_id")
    assert po_prop["source_mapping"] is not None
    assert po_prop["source_mapping"]["column_name"] == "po_number"
    assert po_prop["source_mapping"]["status"] == "CONFIRMED"


@pytest.mark.anyio
async def test_reject_suggestion_lifecycle(async_client: AsyncClient) -> None:
    """Verify explicitly rejecting a candidate suggestion marks status as REJECTED."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # Seed
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # Upload
    csv_content = b"invoice_id,supplier_id\nINV-1,SUP-1\n"
    ds = (await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("test.csv", csv_content, "text/csv")},
        headers=headers,
    )).json()

    objects = (await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)).json()
    inv_obj = next(o for o in objects if o["name"] == "Invoice")

    disc = (await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={"dataset_id": ds["id"], "dataset_version_id": ds["latest_version"]["id"], "business_object_id": inv_obj["id"]},
        headers=headers,
    )).json()

    suggestion = disc["suggestions"][0]
    reject_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/mappings/{suggestion['id']}/reject",
        headers=headers,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "REJECTED"


@pytest.mark.anyio
async def test_traversal_paths(async_client: AsyncClient) -> None:
    """Verify traversal query returns connected semantic relationships."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)
    objects = (await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)).json()
    po_obj = next(o for o in objects if o["name"] == "PurchaseOrder")

    trav_res = await async_client.get(
        f"/api/v1/projects/{project_id}/ontology/objects/{po_obj['id']}/traverse",
        headers=headers,
    )
    assert trav_res.status_code == 200
    trav = trav_res.json()
    assert trav["start_object_name"] == "PurchaseOrder"
    # PO has outgoing paths (received_as -> GoodsReceipt, billed_in -> Invoice) and incoming (supplies <- Supplier)
    outgoing_targets = {p["target_object_name"] for p in trav["outgoing_paths"]}
    assert "GoodsReceipt" in outgoing_targets
    assert "Invoice" in outgoing_targets
    incoming_sources = {p["target_object_name"] for p in trav["incoming_paths"]}
    assert "Supplier" in incoming_sources
