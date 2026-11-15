"""Integration tests for QueryService and Query API endpoints (Phase 5)."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from corbel.core.config import get_settings
from corbel.core.database import get_session_factory
from corbel.domains.ontology.models import Property
from tests.test_dataset_ingestion import setup_test_org_and_project
from tests.test_tenancy import create_user_and_token


@pytest.mark.anyio
async def test_get_query_schema_endpoint(async_client: AsyncClient) -> None:
    """Verify query schema endpoint returns entities with properties and mapping statuses."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Initially without ontology
    res = await async_client.get(f"/api/v1/projects/{project_id}/query/schema", headers=headers)
    assert res.status_code == 200
    schema = res.json()
    assert schema["project_id"] == project_id
    assert schema["entities"] == []

    # 2. Seed P2P ontology
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # 3. Retrieve schema again
    res2 = await async_client.get(f"/api/v1/projects/{project_id}/query/schema", headers=headers)
    assert res2.status_code == 200
    schema2 = res2.json()
    assert len(schema2["entities"]) == 4

    names = {e["name"] for e in schema2["entities"]}
    assert names == {"Supplier", "PurchaseOrder", "GoodsReceipt", "Invoice"}

    # Properties are currently unmapped
    invoice_ent = next(e for e in schema2["entities"] if e["name"] == "Invoice")
    assert any(p["name"] == "invoice_amount" and not p["is_mapped"] for p in invoice_ent["properties"])


@pytest.mark.anyio
async def test_execute_structured_query_end_to_end(async_client: AsyncClient) -> None:
    """End-to-end integration test: seed ontology -> upload data -> map properties -> execute structured query."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Seed P2P ontology
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # 2. Upload synthetic Invoice CSV
    csv_content = (
        b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\n"
        b"INV-001,SUP-1,PO-100,2026-10-01,1500.00,USD,PAID\n"
        b"INV-002,SUP-2,PO-101,2026-10-02,3200.50,USD,PENDING\n"
        b"INV-003,SUP-1,PO-102,2026-10-03,450.00,USD,PAID\n"
        b"INV-004,SUP-3,PO-103,2026-10-04,12000.00,USD,PENDING\n"
        b"INV-005,SUP-2,PO-104,2026-10-05,7500.00,USD,DISCREPANT\n"
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

    # 3. Discover and accept mappings for Invoice
    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")
    invoice_obj_id = invoice_obj["id"]

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
    suggestions = disc_res.json()["suggestions"]
    assert len(suggestions) > 0

    # Accept all suggested mappings
    for s in suggestions:
        accept_res = await async_client.post(
            f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept",
            headers=headers,
        )
        assert accept_res.status_code == 200

    # 4. Execute structured query with filtering and sorting
    query_payload = {
        "entity_name": "Invoice",
        "fields": ["invoice_id", "invoice_amount", "status"],
        "filters": [
            {
                "field": "invoice_amount",
                "operator": "gt",
                "value": 1000,
            }
        ],
        "sorts": [
            {
                "field": "invoice_amount",
                "direction": "desc",
            }
        ],
        "limit": 10,
        "offset": 0,
    }

    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=query_payload,
        headers=headers,
    )
    assert exec_res.status_code == 200
    data = exec_res.json()

    assert data["entity_name"] == "Invoice"
    assert data["columns"] == ["invoice_id", "invoice_amount", "status"]
    assert data["total_count"] == 4
    assert len(data["rows"]) == 4
    # Sorted descending by amount: 12000.0, 7500.0, 3200.5, 1500.0
    amounts = [float(r["invoice_amount"]) for r in data["rows"]]
    assert amounts == [12000.0, 7500.0, 3200.5, 1500.0]
    assert data["rows"][0]["invoice_id"] == "INV-004"
    assert len(data["query_plan"]) > 0

    # 5. Verify query history recorded audit
    hist_res = await async_client.get(
        f"/api/v1/projects/{project_id}/query/history",
        headers=headers,
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 1
    latest_audit = history[0]
    assert latest_audit["entity_name"] == "Invoice"
    assert latest_audit["row_count"] == 4
    assert latest_audit["is_nlq"] is False


@pytest.mark.anyio
async def test_natural_language_query_compilation_and_execution(async_client: AsyncClient) -> None:
    """Test translating a natural language query into a structured AST and executing it."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Seed and map
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    csv_content = (
        b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\n"
        b"INV-101,SUP-1,PO-100,2026-10-01,1500.00,USD,PAID\n"
        b"INV-102,SUP-2,PO-101,2026-10-02,3200.50,USD,PENDING\n"
    )
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", csv_content, "text/csv")},
        headers=headers,
    )
    dataset = upload_res.json()
    dataset_id = dataset["id"]
    version_id = dataset["latest_version"]["id"]

    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")

    disc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "business_object_id": invoice_obj["id"],
        },
        headers=headers,
    )
    for s in disc_res.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # 2. Call NLQ endpoint (Mock provider is active in tests)
    nlq_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/nlq",
        json={
            "prompt": "Show all invoices where status is PAID",
            "target_entity": "Invoice",
        },
        headers=headers,
    )
    assert nlq_res.status_code == 200
    nlq_data = nlq_res.json()

    assert nlq_data["prompt"] == "Show all invoices where status is PAID"
    assert nlq_data["parsed_query"]["entity_name"] == "Invoice"
    assert len(nlq_data["parsed_query"]["filters"]) >= 1

    # 3. Execute the resulting AST directly
    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=nlq_data["parsed_query"],
        headers=headers,
    )
    assert exec_res.status_code == 200
    rows = exec_res.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["invoice_id"] == "INV-101"
    assert rows[0]["status"] == "PAID"


@pytest.mark.anyio
async def test_invoice_query_preserves_nulls_and_duplicates(async_client: AsyncClient) -> None:
    """Case A: Invoice query returns 8 rows, 7 mapped columns, preserving null invoice amount and duplicate INV-1005."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Seed P2P ontology
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # 2. Upload exact 8-row Synthetic Invoice dataset with null amount and duplicate INV-1005
    csv_content = (
        b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\n"
        b"INV-1001,SUP-001,PO-5001,2026-10-01,1250.00,USD,PAID\n"
        b"INV-1002,SUP-002,PO-5002,2026-10-02,2400.50,USD,PENDING\n"
        b"INV-1003,SUP-001,PO-5003,2026-10-03,875.00,USD,APPROVED\n"
        b"INV-1004,SUP-003,PO-5004,2026-10-04,,USD,PENDING\n"
        b"INV-1005,SUP-002,PO-5005,2026-10-05,3100.00,USD,PAID\n"
        b"INV-1005,SUP-002,PO-5005,2026-10-05,3100.00,USD,PAID\n"
        b"INV-1007,SUP-004,PO-5007,2026-10-07,450.75,USD,REJECTED\n"
        b"INV-1008,SUP-003,PO-5008,2026-10-08,980.00,USD,APPROVED\n"
    )
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("corbel_phase3_test.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert upload_res.status_code == 201
    dataset = upload_res.json()
    dataset_id = dataset["id"]
    version_id = dataset["latest_version"]["id"]

    # 3. Discover and accept mappings for Invoice
    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")

    disc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "business_object_id": invoice_obj["id"],
        },
        headers=headers,
    )
    assert disc_res.status_code == 200
    for s in disc_res.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # 4. Execute zero-filter Invoice query
    query_payload = {
        "entity_name": "Invoice",
        "fields": [],
        "filters": [],
        "limit": 50,
        "offset": 0,
    }
    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=query_payload,
        headers=headers,
    )
    assert exec_res.status_code == 200
    data = exec_res.json()
    assert data["entity_name"] == "Invoice"
    assert data["total_count"] == 8
    assert len(data["rows"]) == 8
    assert len(data["columns"]) == 7  # 7 of 8 properties mapped (due_date unmapped)

    # Null amount preserved for INV-1004
    inv_1004 = next(r for r in data["rows"] if r["invoice_id"] == "INV-1004")
    assert inv_1004["invoice_amount"] is None

    # Duplicate INV-1005 rows preserved
    inv_1005_rows = [r for r in data["rows"] if r["invoice_id"] == "INV-1005"]
    assert len(inv_1005_rows) == 2
    for r in inv_1005_rows:
        assert float(r["invoice_amount"]) == 3100.0
        assert r["status"] == "PAID"


@pytest.mark.anyio
async def test_query_execution_missing_dataset_file_raises_error(async_client: AsyncClient) -> None:
    """Case B: Missing dataset file on disk raises QueryExecutionException rather than empty results."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    csv_content = (
        b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\n"
        b"INV-001,SUP-1,PO-1,2026-10-01,100,USD,PAID\n"
    )
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", csv_content, "text/csv")},
        headers=headers,
    )
    dataset = upload_res.json()
    dataset_id = dataset["id"]
    version = dataset["latest_version"]

    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")

    disc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={"dataset_id": dataset_id, "dataset_version_id": version["id"], "business_object_id": invoice_obj["id"]},
        headers=headers,
    )
    for s in disc_res.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # Remove the physical backing file
    from corbel.domains.data_intelligence.models import DatasetVersion

    settings = get_settings()
    storage_root = Path(settings.DATASET_STORAGE_DIR).resolve()
    async with get_session_factory()() as session:
        v_db = (
            await session.execute(
                select(DatasetVersion).where(DatasetVersion.id == uuid.UUID(version["id"]))
            )
        ).scalar_one()
        storage_path = v_db.storage_path

    file_path = (storage_root / storage_path).resolve()
    assert file_path.exists()
    file_path.unlink()

    # Query execution must fail with descriptive error
    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json={"entity_name": "Invoice", "limit": 10},
        headers=headers,
    )
    assert exec_res.status_code == 500
    err = exec_res.json()
    assert "unavailable on storage" in err.get("message", "")
    assert str(file_path) not in err.get("message", "")  # Do not leak internal server paths


@pytest.mark.anyio
async def test_query_execution_missing_dataset_version_raises_error(async_client: AsyncClient) -> None:
    """Case C: Non-existent or deleted dataset version raises QueryExecutionException."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # Directly map an invoice property to a non-existent dataset version
    fake_version_id = uuid.uuid4()
    fake_dataset_id = uuid.uuid4()

    async with get_session_factory()() as session:
        props = (
            await session.execute(
                select(Property)
                .join(Property.business_object)
                .where(
                    Property.business_object.has(project_id=uuid.UUID(project_id), name="Invoice")
                )
            )
        ).scalars().all()
        assert len(props) > 0
        prop = props[0]
        prop.source_mapping_json = {
            "dataset_id": str(fake_dataset_id),
            "dataset_version_id": str(fake_version_id),
            "column_name": "dummy_col",
            "status": "CONFIRMED",
        }
        await session.commit()

    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json={"entity_name": "Invoice", "limit": 10},
        headers=headers,
    )
    assert exec_res.status_code == 500
    err = exec_res.json()
    assert "could not be resolved" in err.get("message", "")


@pytest.mark.anyio
async def test_query_execution_foreign_project_dataset_isolation(async_client: AsyncClient) -> None:
    """Case D: Cross-project isolation prevents loading datasets belonging to other projects."""
    # Create Project 1
    _, token1, org1, project1 = await setup_test_org_and_project(async_client)
    headers1 = {"Authorization": f"Bearer {token1}", "X-Organization-ID": org1["id"]}
    await async_client.post(f"/api/v1/projects/{project1['id']}/ontology/seed-p2p", headers=headers1)

    # Create Project 2 and upload a dataset there
    _, token2, org2, project2 = await setup_test_org_and_project(async_client)
    headers2 = {"Authorization": f"Bearer {token2}", "X-Organization-ID": org2["id"]}
    csv_content = b"invoice_id,status\nINV-P2,PAID\n"
    upload_res2 = await async_client.post(
        f"/api/v1/projects/{project2['id']}/datasets/upload",
        files={"file": ("p2.csv", csv_content, "text/csv")},
        headers=headers2,
    )
    p2_version_id = upload_res2.json()["latest_version"]["id"]
    p2_dataset_id = upload_res2.json()["id"]

    # In Project 1, try to map Invoice to Project 2's dataset version
    async with get_session_factory()() as session:
        props = (
            await session.execute(
                select(Property)
                .join(Property.business_object)
                .where(
                    Property.business_object.has(project_id=uuid.UUID(project1["id"]), name="Invoice")
                )
            )
        ).scalars().all()
        prop = props[0]
        prop.source_mapping_json = {
            "dataset_id": p2_dataset_id,
            "dataset_version_id": p2_version_id,
            "column_name": "invoice_id",
            "status": "CONFIRMED",
        }
        await session.commit()

    # Query in Project 1 must not load Project 2's dataset version
    exec_res = await async_client.post(
        f"/api/v1/projects/{project1['id']}/query/execute",
        json={"entity_name": "Invoice", "limit": 10},
        headers=headers1,
    )
    assert exec_res.status_code == 500
    err = exec_res.json()
    assert "could not be resolved" in err.get("message", "")


@pytest.mark.anyio
async def test_query_execution_with_relationship_join_end_to_end(async_client: AsyncClient) -> None:
    """Verify executing a joined query across two populated sandbox tables (PurchaseOrder LEFT JOIN Supplier)."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    # 1. Seed P2P ontology
    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    # 2. Upload Suppliers CSV
    sup_csv = (
        b"supplier_id,supplier_name,country,payment_terms,status\n"
        b"SUP-001,Acme Industrial,USA,NET30,ACTIVE\n"
        b"SUP-002,Global Logistics,DEU,NET60,ACTIVE\n"
    )
    sup_upload = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("suppliers.csv", sup_csv, "text/csv")},
        headers=headers,
    )
    assert sup_upload.status_code == 201
    sup_dataset = sup_upload.json()

    # 3. Upload Purchase Orders CSV
    po_csv = (
        b"po_id,supplier_id,total_amount,currency,order_date,status\n"
        b"PO-5001,SUP-001,15000.0,USD,2026-10-01,OPEN\n"
        b"PO-5002,SUP-002,28500.0,USD,2026-10-02,APPROVED\n"
    )
    po_upload = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("purchase_orders.csv", po_csv, "text/csv")},
        headers=headers,
    )
    assert po_upload.status_code == 201
    po_dataset = po_upload.json()

    # 4. Map Supplier properties
    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    objects = objects_res.json()
    sup_obj = next(o for o in objects if o["name"] == "Supplier")
    po_obj = next(o for o in objects if o["name"] == "PurchaseOrder")

    sup_disc = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={
            "dataset_id": sup_dataset["id"],
            "dataset_version_id": sup_dataset["latest_version"]["id"],
            "business_object_id": sup_obj["id"],
        },
        headers=headers,
    )
    for s in sup_disc.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # 5. Map PurchaseOrder properties
    po_disc = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={
            "dataset_id": po_dataset["id"],
            "dataset_version_id": po_dataset["latest_version"]["id"],
            "business_object_id": po_obj["id"],
        },
        headers=headers,
    )
    for s in po_disc.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # 6. Execute joined query: PurchaseOrder joining supplies relationship to get Supplier_supplier_name
    query_payload = {
        "entity_name": "PurchaseOrder",
        "fields": ["po_id", "total_amount"],
        "joins": [
            {
                "relationship_name": "supplies",
                "fields": ["supplier_name"],
            }
        ],
        "sorts": [{"field": "total_amount", "direction": "asc"}],
    }
    exec_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=query_payload,
        headers=headers,
    )
    assert exec_res.status_code == 200
    res_data = exec_res.json()

    assert res_data["entity_name"] == "PurchaseOrder"
    assert "Supplier_supplier_name" in res_data["columns"]
    assert res_data["total_count"] == 2
    assert len(res_data["rows"]) == 2

    # Verify actual row values joined from both SQLite sandbox tables
    assert res_data["rows"][0]["po_id"] == "PO-5001"
    assert float(res_data["rows"][0]["total_amount"]) == 15000.0
    assert res_data["rows"][0]["Supplier_supplier_name"] == "Acme Industrial"

    assert res_data["rows"][1]["po_id"] == "PO-5002"
    assert float(res_data["rows"][1]["total_amount"]) == 28500.0
    assert res_data["rows"][1]["Supplier_supplier_name"] == "Global Logistics"


@pytest.mark.anyio
async def test_nlq_audit_attribution_end_to_end_api_flow(async_client: AsyncClient) -> None:
    """Verify end-to-end NLQ compilation audit flow, token attribution, single-use, and isolation."""
    _, token, org, project = await setup_test_org_and_project(async_client)
    headers = {"Authorization": f"Bearer {token}", "X-Organization-ID": org["id"]}
    project_id = project["id"]

    await async_client.post(f"/api/v1/projects/{project_id}/ontology/seed-p2p", headers=headers)

    csv_content = b"invoice_id,supplier_id,po_number,invoice_date,invoice_amount,currency,status\nINV-001,SUP-1,PO-1,2026-10-01,100,USD,PAID\n"
    upload_res = await async_client.post(
        f"/api/v1/projects/{project_id}/datasets/upload",
        files={"file": ("invoices.csv", csv_content, "text/csv")},
        headers=headers,
    )
    dataset = upload_res.json()
    objects_res = await async_client.get(f"/api/v1/projects/{project_id}/ontology/objects", headers=headers)
    invoice_obj = next(o for o in objects_res.json() if o["name"] == "Invoice")

    disc_res = await async_client.post(
        f"/api/v1/projects/{project_id}/ontology/discover-mappings",
        json={"dataset_id": dataset["id"], "dataset_version_id": dataset["latest_version"]["id"], "business_object_id": invoice_obj["id"]},
        headers=headers,
    )
    for s in disc_res.json()["suggestions"]:
        await async_client.post(f"/api/v1/projects/{project_id}/ontology/mappings/{s['id']}/accept", headers=headers)

    # 1. Manual query execution -> MUST record is_nlq=False, nlq_prompt=None, token_count=None
    manual_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json={"entity_name": "Invoice", "limit": 10},
        headers=headers,
    )
    assert manual_res.status_code == 200

    hist_res1 = await async_client.get(f"/api/v1/projects/{project_id}/query/history", headers=headers)
    assert hist_res1.status_code == 200
    history1 = hist_res1.json()
    assert len(history1) >= 1
    assert history1[0]["is_nlq"] is False
    assert history1[0]["nlq_prompt"] is None
    assert history1[0]["token_count"] is None

    # 2. Compile an NLQ query
    nlq_prompt = "Show all invoices where status is PAID"
    nlq_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/nlq",
        json={"prompt": nlq_prompt, "target_entity": "Invoice"},
        headers=headers,
    )
    assert nlq_res.status_code == 200
    nlq_data = nlq_res.json()
    nlq_ref = nlq_data["nlq_reference"]
    assert nlq_ref is not None
    assert nlq_data["token_usage"]["total_tokens"] > 0
    expected_tokens = nlq_data["token_usage"]["total_tokens"]

    # Compilation alone MUST NOT create an execution record
    hist_before_exec = (await async_client.get(f"/api/v1/projects/{project_id}/query/history", headers=headers)).json()
    assert len(hist_before_exec) == len(history1)

    # 3. Execute query with the server-issued nlq_reference
    exec_nlq_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=nlq_data["parsed_query"],
        headers=headers,
    )
    assert exec_nlq_res.status_code == 200

    # 4. Check query history in PostgreSQL -> MUST record is_nlq=True, nlq_prompt, token_count
    hist_res2 = await async_client.get(f"/api/v1/projects/{project_id}/query/history", headers=headers)
    assert hist_res2.status_code == 200
    history2 = hist_res2.json()
    latest_nlq_exec = history2[0]

    assert latest_nlq_exec["is_nlq"] is True
    assert latest_nlq_exec["nlq_prompt"] == nlq_prompt
    assert latest_nlq_exec["token_count"] == expected_tokens
    assert latest_nlq_exec["entity_name"] == "Invoice"

    # 5. Single-use enforcement: re-using the exact same nlq_reference must fail
    replay_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=nlq_data["parsed_query"],
        headers=headers,
    )
    assert replay_res.status_code == 422
    assert "Invalid or expired NLQ compilation reference" in replay_res.json().get("message", "")

    # 6. Forged nlq_reference must fail
    forged_query = dict(nlq_data["parsed_query"])
    forged_query["nlq_reference"] = str(uuid.uuid4())
    forged_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json=forged_query,
        headers=headers,
    )
    assert forged_res.status_code == 422
    assert "Invalid or expired NLQ compilation reference" in forged_res.json().get("message", "")

    # 7. Cross-user isolation: user B cannot use user A's nlq_reference
    # Create User B in same org/project
    _, token_b = await create_user_and_token(async_client, "User B")
    # First compile a fresh NLQ as User A
    fresh_nlq = await async_client.post(
        f"/api/v1/projects/{project_id}/query/nlq",
        json={"prompt": "Find all invoices", "target_entity": "Invoice"},
        headers=headers,
    )
    fresh_ref = fresh_nlq.json()["nlq_reference"]

    # Attempt execution as User B with headers for User B (User B not member -> 403 or if member -> 422)
    # Even if User B is added or not, execute with User B token
    headers_b = {"Authorization": f"Bearer {token_b}", "X-Organization-ID": org["id"]}
    user_b_res = await async_client.post(
        f"/api/v1/projects/{project_id}/query/execute",
        json={**fresh_nlq.json()["parsed_query"], "nlq_reference": fresh_ref},
        headers=headers_b,
    )
    # User B is not authorized or reference doesn't match User B -> rejected
    assert user_b_res.status_code in (403, 404, 422)
