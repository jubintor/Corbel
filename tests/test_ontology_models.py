"""Unit and model integrity tests for Ontology Engine (Phase 4)."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from corbel.core.database import get_session_factory
from corbel.domains.ontology.models import (
    BusinessObject,
    Property,
    PropertyType,
    Relationship,
    RelationshipCardinality,
)
from corbel.domains.tenancy.models import Organization, Project


@pytest.mark.anyio
async def test_business_object_and_properties_persistence() -> None:
    """Verify BusinessObject and Property creation, relationships, and cascades."""
    session_factory = get_session_factory()
    async with session_factory() as db_session:
        org = Organization(id=uuid.uuid4(), name="Ontology Test Org", slug=f"ont-org-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        await db_session.flush()

        proj = Project(id=uuid.uuid4(), organization_id=org.id, name="Ontology Project", slug=f"ont-proj-{uuid.uuid4().hex[:6]}")
        db_session.add(proj)
        await db_session.flush()

        obj = BusinessObject(
            id=uuid.uuid4(),
            project_id=proj.id,
            name="Invoice",
            display_name="Vendor Invoice",
            description="Vendor billing document",
            primary_key_property="invoice_id",
        )
        db_session.add(obj)
        await db_session.flush()

        prop1 = Property(
            id=uuid.uuid4(),
            business_object_id=obj.id,
            name="invoice_id",
            data_type=PropertyType.STRING.value,
            is_primary_key=True,
            is_nullable=False,
        )
        prop2 = Property(
            id=uuid.uuid4(),
            business_object_id=obj.id,
            name="invoice_amount",
            data_type=PropertyType.NUMBER.value,
            is_primary_key=False,
            is_nullable=False,
        )
        db_session.add_all([prop1, prop2])
        await db_session.commit()

        # Query back
        stmt = (
            select(BusinessObject)
            .options(selectinload(BusinessObject.properties))
            .where(BusinessObject.id == obj.id)
        )
        retrieved = (await db_session.execute(stmt)).scalar_one()
        assert retrieved.name == "Invoice"
        assert retrieved.display_name == "Vendor Invoice"
        assert len(retrieved.properties) == 2
        assert {p.name for p in retrieved.properties} == {"invoice_id", "invoice_amount"}


@pytest.mark.anyio
async def test_relationship_composite_fk_same_project() -> None:
    """Verify Relationship model links two Business Objects in the same project."""
    session_factory = get_session_factory()
    async with session_factory() as db_session:
        org = Organization(id=uuid.uuid4(), name="Rel Test Org", slug=f"rel-org-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        await db_session.flush()

        proj = Project(id=uuid.uuid4(), organization_id=org.id, name="Rel Project", slug=f"rel-proj-{uuid.uuid4().hex[:6]}")
        db_session.add(proj)
        await db_session.flush()

        src_obj = BusinessObject(id=uuid.uuid4(), project_id=proj.id, name="Supplier", display_name="Supplier")
        tgt_obj = BusinessObject(id=uuid.uuid4(), project_id=proj.id, name="PurchaseOrder", display_name="Purchase Order")
        db_session.add_all([src_obj, tgt_obj])
        await db_session.flush()

        rel = Relationship(
            id=uuid.uuid4(),
            project_id=proj.id,
            name="supplies",
            source_object_id=src_obj.id,
            target_object_id=tgt_obj.id,
            cardinality=RelationshipCardinality.ONE_TO_MANY.value,
            join_expression_json={"source_property": "supplier_id", "target_property": "supplier_id"},
        )
        db_session.add(rel)
        await db_session.commit()

        stmt = select(Relationship).where(Relationship.id == rel.id)
        saved_rel = (await db_session.execute(stmt)).scalar_one()
        assert saved_rel.name == "supplies"
        assert saved_rel.source_object_id == src_obj.id
        assert saved_rel.target_object_id == tgt_obj.id
