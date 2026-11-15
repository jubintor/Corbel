"""Tests for deterministic QueryCompiler in Phase 5."""

import uuid

import pytest

from corbel.domains.ontology.models import BusinessObject, Property, Relationship
from corbel.domains.query.compiler import QueryCompiler
from corbel.domains.query.exceptions import (
    QueryValidationException,
    UnmappedPropertyQueryException,
)
from corbel.domains.query.schemas import (
    QueryFilter,
    QueryJoin,
    QueryOperator,
    QuerySort,
    SortDirection,
    StructuredQueryRequest,
)


@pytest.fixture
def sample_ontology_objects() -> tuple[BusinessObject, BusinessObject, list[Relationship]]:
    """Build mock in-memory BusinessObjects with confirmed mappings and relationships."""
    proj_id = uuid.uuid4()
    po_obj_id = uuid.uuid4()
    sup_obj_id = uuid.uuid4()

    po_props = [
        Property(
            id=uuid.uuid4(),
            business_object_id=po_obj_id,
            name="po_number",
            display_name="PO Number",
            data_type="STRING",
            is_nullable=False,
            is_primary_key=True,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "po_no",
                "status": "CONFIRMED",
            },
        ),
        Property(
            id=uuid.uuid4(),
            business_object_id=po_obj_id,
            name="total_amount",
            display_name="Total Amount",
            data_type="NUMBER",
            is_nullable=False,
            is_primary_key=False,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "amount",
                "status": "CONFIRMED",
            },
        ),
        Property(
            id=uuid.uuid4(),
            business_object_id=po_obj_id,
            name="status",
            display_name="Status",
            data_type="STRING",
            is_nullable=True,
            is_primary_key=False,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "status",
                "status": "CONFIRMED",
            },
        ),
        Property(
            id=uuid.uuid4(),
            business_object_id=po_obj_id,
            name="unmapped_field",
            display_name="Unmapped Field",
            data_type="STRING",
            is_nullable=True,
            is_primary_key=False,
            source_mapping_json=None,
        ),
        Property(
            id=uuid.uuid4(),
            business_object_id=po_obj_id,
            name="supplier_id",
            display_name="Supplier ID",
            data_type="STRING",
            is_nullable=False,
            is_primary_key=False,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "vendor_id",
                "status": "CONFIRMED",
            },
        ),
    ]

    po_obj = BusinessObject(
        id=po_obj_id,
        project_id=proj_id,
        name="PurchaseOrder",
        display_name="Purchase Order",
        properties=po_props,
    )

    sup_props = [
        Property(
            id=uuid.uuid4(),
            business_object_id=sup_obj_id,
            name="supplier_id",
            display_name="Supplier ID",
            data_type="STRING",
            is_nullable=False,
            is_primary_key=True,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "id",
                "status": "CONFIRMED",
            },
        ),
        Property(
            id=uuid.uuid4(),
            business_object_id=sup_obj_id,
            name="supplier_name",
            display_name="Supplier Name",
            data_type="STRING",
            is_nullable=False,
            is_primary_key=False,
            source_mapping_json={
                "dataset_id": str(uuid.uuid4()),
                "dataset_version_id": str(uuid.uuid4()),
                "column_name": "name",
                "status": "CONFIRMED",
            },
        ),
    ]

    sup_obj = BusinessObject(
        id=sup_obj_id,
        project_id=proj_id,
        name="Supplier",
        display_name="Supplier",
        properties=sup_props,
    )

    rel = Relationship(
        id=uuid.uuid4(),
        project_id=proj_id,
        name="supplies",
        source_object_id=sup_obj_id,
        target_object_id=po_obj_id,
        cardinality="ONE_TO_MANY",
        join_expression_json={"foreign_key_property": "supplier_id"},
        source_object=sup_obj,
        target_object=po_obj,
    )

    return po_obj, sup_obj, [rel]


def test_compiler_default_all_mapped_fields(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(entity_name="PurchaseOrder")
    compiled = compiler.compile(ast)

    assert "SELECT " in compiled.sql
    assert "FROM _t_purchaseorder AS _t0" in compiled.sql
    assert "LIMIT ? OFFSET ?" in compiled.sql
    assert compiled.parameters == [50, 0]
    # Verify unmapped_field was excluded, but mapped fields are included
    assert "unmapped_field" not in compiled.projected_columns
    assert "po_number" in compiled.projected_columns
    assert "total_amount" in compiled.projected_columns


def test_compiler_explicit_fields_and_filters(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["po_number", "total_amount"],
        filters=[
            QueryFilter(field="total_amount", operator=QueryOperator.GT, value=10000.5),
            QueryFilter(field="status", operator=QueryOperator.EQ, value="OPEN"),
            QueryFilter(field="po_number", operator=QueryOperator.CONTAINS, value="PO-99"),
        ],
        sorts=[QuerySort(field="total_amount", direction=SortDirection.DESC)],
        limit=25,
        offset=10,
    )
    compiled = compiler.compile(ast)

    assert "_t0.total_amount > ?" in compiled.sql
    assert "_t0.status = ?" in compiled.sql
    assert "_t0.po_number LIKE ?" in compiled.sql
    assert "ORDER BY _t0.total_amount DESC" in compiled.sql
    assert "LIMIT ? OFFSET ?" in compiled.sql
    assert compiled.parameters == [10000.5, "OPEN", "%PO-99%", 25, 10]


def test_compiler_rejects_unmapped_field(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["unmapped_field"],
    )
    with pytest.raises(UnmappedPropertyQueryException) as exc:
        compiler.compile(ast)
    assert "unmapped_field" in str(exc.value)


def test_compiler_rejects_nonexistent_field(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["completely_fake_column"],
    )
    with pytest.raises(QueryValidationException) as exc:
        compiler.compile(ast)
    assert "does not exist" in str(exc.value)


def test_compiler_rejects_sql_injection_attempt(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["po_number; DROP TABLE users;--"],
    )
    with pytest.raises(QueryValidationException):
        compiler.compile(ast)


def test_compiler_in_and_is_null_operators(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, _, rels = sample_ontology_objects
    compiler = QueryCompiler(target_object=po_obj, relationships=rels)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        filters=[
            QueryFilter(field="status", operator=QueryOperator.IN, value=["OPEN", "PENDING", "APPROVED"]),
            QueryFilter(field="po_number", operator=QueryOperator.IS_NOT_NULL),
        ],
    )
    compiled = compiler.compile(ast)

    assert "_t0.status IN (?, ?, ?)" in compiled.sql
    assert "_t0.po_number IS NOT NULL" in compiled.sql
    assert compiled.parameters == ["OPEN", "PENDING", "APPROVED", 50, 0]


def test_compiler_join_with_same_property_names(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, rels = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}
    compiler = QueryCompiler(target_object=po_obj, relationships=rels, all_objects=all_objects)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["po_number", "total_amount"],
        joins=[QueryJoin(relationship_name="supplies", fields=["supplier_name"])],
    )
    compiled = compiler.compile(ast)

    assert "LEFT JOIN _t_supplier AS _t1 ON _t0.supplier_id = _t1.supplier_id" in compiled.sql
    assert "_t1.supplier_name AS Supplier_supplier_name" in compiled.sql
    assert "Supplier_supplier_name" in compiled.projected_columns


def test_compiler_join_with_different_property_names(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, _ = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}

    # Create relationship where source_property != target_property
    rel_diff = Relationship(
        id=uuid.uuid4(),
        project_id=po_obj.project_id,
        name="vendor_connection",
        source_object_id=po_obj.id,
        target_object_id=sup_obj.id,
        cardinality="ONE_TO_MANY",
        join_expression_json={"source_property": "supplier_id", "target_property": "supplier_id"},
        source_object=po_obj,
        target_object=sup_obj,
    )
    compiler = QueryCompiler(target_object=po_obj, relationships=[rel_diff], all_objects=all_objects)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        fields=["po_number"],
        joins=[QueryJoin(relationship_name="vendor_connection", fields=["supplier_name"])],
    )
    compiled = compiler.compile(ast)
    assert "LEFT JOIN _t_supplier AS _t1 ON _t0.supplier_id = _t1.supplier_id" in compiled.sql


def test_compiler_join_rejects_missing_metadata(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, _ = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}

    rel_bad = Relationship(
        id=uuid.uuid4(),
        project_id=po_obj.project_id,
        name="broken_rel",
        source_object_id=po_obj.id,
        target_object_id=sup_obj.id,
        cardinality="ONE_TO_MANY",
        join_expression_json=None,
        source_object=po_obj,
        target_object=sup_obj,
    )
    compiler = QueryCompiler(target_object=po_obj, relationships=[rel_bad], all_objects=all_objects)
    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        joins=[QueryJoin(relationship_name="broken_rel", fields=["supplier_name"])],
    )
    with pytest.raises(QueryValidationException) as exc:
        compiler.compile(ast)
    assert "lacks valid join metadata" in str(exc.value)


def test_compiler_join_rejects_unmapped_target_property(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, _ = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}

    rel_unmapped = Relationship(
        id=uuid.uuid4(),
        project_id=po_obj.project_id,
        name="unmapped_target_rel",
        source_object_id=po_obj.id,
        target_object_id=sup_obj.id,
        cardinality="ONE_TO_MANY",
        join_expression_json={"source_property": "supplier_id", "target_property": "nonexistent_tgt_prop"},
        source_object=po_obj,
        target_object=sup_obj,
    )
    compiler = QueryCompiler(target_object=po_obj, relationships=[rel_unmapped], all_objects=all_objects)
    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        joins=[QueryJoin(relationship_name="unmapped_target_rel", fields=["supplier_name"])],
    )
    with pytest.raises(QueryValidationException) as exc:
        compiler.compile(ast)
    assert "does not exist on" in str(exc.value)


def test_compiler_join_rejects_unmapped_joined_projection_field(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, rels = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}
    compiler = QueryCompiler(target_object=po_obj, relationships=rels, all_objects=all_objects)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        joins=[QueryJoin(relationship_name="supplies", fields=["nonexistent_column_abc"])],
    )
    with pytest.raises(QueryValidationException) as exc:
        compiler.compile(ast)
    assert "does not exist on joined entity" in str(exc.value)


def test_compiler_join_rejects_invalid_relationship(sample_ontology_objects: tuple[BusinessObject, BusinessObject, list[Relationship]]) -> None:
    po_obj, sup_obj, rels = sample_ontology_objects
    all_objects = {"purchaseorder": po_obj, "supplier": sup_obj}
    compiler = QueryCompiler(target_object=po_obj, relationships=rels, all_objects=all_objects)

    ast = StructuredQueryRequest(
        entity_name="PurchaseOrder",
        joins=[QueryJoin(relationship_name="completely_unknown_relationship", fields=["supplier_name"])],
    )
    with pytest.raises(QueryValidationException) as exc:
        compiler.compile(ast)
    assert "does not exist in the project ontology" in str(exc.value)
