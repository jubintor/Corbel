"""Domain service managing Business Objects, Properties, Relationships, and Semantic Mappings."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.domains.data_intelligence.exceptions import (
    DatasetNotFoundException,
    DatasetVersionNotFoundException,
)
from corbel.domains.data_intelligence.models import Dataset, DatasetVersion
from corbel.domains.ontology.exceptions import (
    BusinessObjectAlreadyExistsException,
    BusinessObjectNotFoundException,
    IncompatibleMappingTypeException,
    InvalidPropertyMappingException,
    InvalidRelationshipEndpointsException,
    PropertyAlreadyExistsException,
    PropertyMappingNotFoundException,
    PropertyNotFoundException,
    RelationshipAlreadyExistsException,
    RelationshipNotFoundException,
)
from corbel.domains.ontology.matcher import SemanticMatcher
from corbel.domains.ontology.models import (
    BusinessObject,
    MappingStatus,
    Property,
    PropertyMapping,
    PropertyType,
    Relationship,
    RelationshipCardinality,
)
from corbel.domains.ontology.schemas import (
    BusinessObjectCreateRequest,
    BusinessObjectUpdateRequest,
    OntologyGraphEdge,
    OntologyGraphNode,
    OntologyGraphResponse,
    OntologyTraversalResponse,
    PropertyCreateRequest,
    PropertyMappingCreateRequest,
    PropertyMappingResponse,
    PropertyResponse,
    PropertyUpdateRequest,
    RelationshipCreateRequest,
    SemanticDiscoveryRequest,
    SemanticDiscoveryResponse,
    TraversalStep,
)
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.tenancy.service import TenancyService


class OntologyService:
    """Service orchestrating semantic business concepts, relationships, and deterministic mappings."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenancy_service = TenancyService(session)

    # ==========================================================================
    # Business Objects
    # ==========================================================================

    async def create_business_object(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: BusinessObjectCreateRequest,
    ) -> BusinessObject:
        """Create a new Business Object in the project workspace."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Check name uniqueness within project
        existing = await self.session.execute(
            select(BusinessObject).where(
                BusinessObject.project_id == project_id,
                func.lower(BusinessObject.name) == req.name.strip().lower(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise BusinessObjectAlreadyExistsException(
                f"Business Object '{req.name.strip()}' already exists in this project"
            )

        obj = BusinessObject(
            id=uuid.uuid4(),
            project_id=project_id,
            name=req.name.strip(),
            display_name=req.display_name.strip(),
            description=req.description.strip() if req.description else None,
            primary_key_property=req.primary_key_property.strip() if req.primary_key_property else None,
            version=1,
        )
        self.session.add(obj)

        # Add initial properties if supplied
        for p in req.properties:
            prop = Property(
                id=uuid.uuid4(),
                business_object_id=obj.id,
                name=p.name.strip(),
                display_name=p.display_name.strip() if p.display_name else None,
                data_type=p.data_type.value,
                is_nullable=p.is_nullable,
                is_primary_key=p.is_primary_key,
                description=p.description.strip() if p.description else None,
            )
            self.session.add(prop)

        await self.session.commit()
        return await self.get_business_object(org_id, project_id, obj.id, user_id)

    async def get_business_object(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> BusinessObject:
        """Retrieve a Business Object with all properties loaded."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)

        stmt = (
            select(BusinessObject)
            .options(selectinload(BusinessObject.properties))
            .where(
                BusinessObject.id == object_id,
                BusinessObject.project_id == project_id,
            )
        )
        obj = (await self.session.execute(stmt)).scalar_one_or_none()
        if obj is None:
            raise BusinessObjectNotFoundException(
                f"Business Object with ID '{object_id}' not found in project"
            )
        return obj

    async def list_business_objects(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[BusinessObject]:
        """List all Business Objects cataloged in a project workspace."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)

        stmt = (
            select(BusinessObject)
            .options(selectinload(BusinessObject.properties))
            .where(BusinessObject.project_id == project_id)
            .order_by(BusinessObject.name.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_business_object(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        user_id: uuid.UUID,
        req: BusinessObjectUpdateRequest,
    ) -> BusinessObject:
        """Update an existing Business Object's metadata."""
        obj = await self.get_business_object(org_id, project_id, object_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        if req.display_name is not None:
            obj.display_name = req.display_name.strip()
        if req.description is not None:
            obj.description = req.description.strip() or None
        if req.primary_key_property is not None:
            obj.primary_key_property = req.primary_key_property.strip() or None

        obj.version += 1
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def delete_business_object(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a Business Object and cascade deletion to its properties and relationships."""
        obj = await self.get_business_object(org_id, project_id, object_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.PROJECT_LEAD]
        )
        await self.session.delete(obj)
        await self.session.commit()

    # ==========================================================================
    # Properties
    # ==========================================================================

    async def add_property(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        user_id: uuid.UUID,
        req: PropertyCreateRequest,
    ) -> Property:
        """Add a new Property to an existing Business Object."""
        obj = await self.get_business_object(org_id, project_id, object_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Check duplicate property name
        existing = await self.session.execute(
            select(Property).where(
                Property.business_object_id == obj.id,
                func.lower(Property.name) == req.name.strip().lower(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise PropertyAlreadyExistsException(
                f"Property '{req.name.strip()}' already exists on Business Object '{obj.name}'"
            )

        prop = Property(
            id=uuid.uuid4(),
            business_object_id=obj.id,
            name=req.name.strip(),
            display_name=req.display_name.strip() if req.display_name else None,
            data_type=req.data_type.value,
            is_nullable=req.is_nullable,
            is_primary_key=req.is_primary_key,
            description=req.description.strip() if req.description else None,
        )
        self.session.add(prop)
        if req.is_primary_key:
            obj.primary_key_property = prop.name
        obj.version += 1

        await self.session.commit()
        await self.session.refresh(prop)
        return prop

    async def update_property(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        property_id: uuid.UUID,
        user_id: uuid.UUID,
        req: PropertyUpdateRequest,
    ) -> Property:
        """Update property attributes and constraints."""
        await self.get_business_object(org_id, project_id, object_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        stmt = select(Property).where(
            Property.id == property_id,
            Property.business_object_id == object_id,
        )
        prop = (await self.session.execute(stmt)).scalar_one_or_none()
        if prop is None:
            raise PropertyNotFoundException("Property not found on the specified Business Object")

        if req.display_name is not None:
            prop.display_name = req.display_name.strip() or None
        if req.data_type is not None:
            prop.data_type = req.data_type.value
        if req.is_nullable is not None:
            prop.is_nullable = req.is_nullable
        if req.is_primary_key is not None:
            prop.is_primary_key = req.is_primary_key
        if req.description is not None:
            prop.description = req.description.strip() or None

        await self.session.commit()
        await self.session.refresh(prop)
        return prop

    async def delete_property(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        property_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Remove a Property from a Business Object."""
        await self.get_business_object(org_id, project_id, object_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        stmt = select(Property).where(
            Property.id == property_id,
            Property.business_object_id == object_id,
        )
        prop = (await self.session.execute(stmt)).scalar_one_or_none()
        if prop is None:
            raise PropertyNotFoundException("Property not found on the specified Business Object")

        await self.session.delete(prop)
        await self.session.commit()

    # ==========================================================================
    # Relationships
    # ==========================================================================

    async def create_relationship(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: RelationshipCreateRequest,
    ) -> Relationship:
        """Establish a directed relationship connecting two Business Objects in the same project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Validate that both source and target objects exist in the exact same project
        src_obj = await self.session.execute(
            select(BusinessObject).where(
                BusinessObject.id == req.source_object_id,
                BusinessObject.project_id == project_id,
            )
        )
        if src_obj.scalar_one_or_none() is None:
            raise InvalidRelationshipEndpointsException("Source Business Object not found in this project")

        tgt_obj = await self.session.execute(
            select(BusinessObject).where(
                BusinessObject.id == req.target_object_id,
                BusinessObject.project_id == project_id,
            )
        )
        if tgt_obj.scalar_one_or_none() is None:
            raise InvalidRelationshipEndpointsException("Target Business Object not found in this project")

        # Check duplicate relationship
        dup = await self.session.execute(
            select(Relationship).where(
                Relationship.project_id == project_id,
                func.lower(Relationship.name) == req.name.strip().lower(),
                Relationship.source_object_id == req.source_object_id,
                Relationship.target_object_id == req.target_object_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise RelationshipAlreadyExistsException(
                f"Relationship '{req.name.strip()}' already connects these endpoints"
            )

        rel = Relationship(
            id=uuid.uuid4(),
            project_id=project_id,
            name=req.name.strip(),
            source_object_id=req.source_object_id,
            target_object_id=req.target_object_id,
            cardinality=req.cardinality.value,
            description=req.description.strip() if req.description else None,
            join_expression_json=req.join_expression,
        )
        self.session.add(rel)
        await self.session.commit()
        await self.session.refresh(rel)
        return rel

    async def list_relationships(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Relationship]:
        """List all directed relationships configured within a project workspace."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)

        stmt = (
            select(Relationship)
            .options(
                selectinload(Relationship.source_object),
                selectinload(Relationship.target_object),
            )
            .where(Relationship.project_id == project_id)
            .order_by(Relationship.name.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete_relationship(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        relationship_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Remove a Relationship."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        stmt = select(Relationship).where(
            Relationship.id == relationship_id,
            Relationship.project_id == project_id,
        )
        rel = (await self.session.execute(stmt)).scalar_one_or_none()
        if rel is None:
            raise RelationshipNotFoundException("Relationship not found")

        await self.session.delete(rel)
        await self.session.commit()

    # ==========================================================================
    # P2P Foundation Seed
    # ==========================================================================

    async def seed_p2p_ontology(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[BusinessObject]:
        """Initialize the baseline Procure-to-Pay (P2P) ontology concepts and relationships.

        Creates Supplier, PurchaseOrder, GoodsReceipt, and Invoice if not present.
        """
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        p2p_definitions: list[dict[str, Any]] = [
            {
                "name": "Supplier",
                "display_name": "Supplier / Vendor",
                "description": "Enterprise supplier entity providing goods and services.",
                "primary_key_property": "supplier_id",
                "properties": [
                    {"name": "supplier_id", "data_type": PropertyType.STRING, "is_primary_key": True, "is_nullable": False, "description": "Unique supplier identifier"},
                    {"name": "supplier_name", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Legal entity name of the supplier"},
                    {"name": "country", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": True, "description": "Country of incorporation or operation"},
                    {"name": "status", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Vendor master status (ACTIVE, BLOCKED)"},
                ],
            },
            {
                "name": "PurchaseOrder",
                "display_name": "Purchase Order (PO)",
                "description": "Legally binding procurement commitment issued to a supplier.",
                "primary_key_property": "po_id",
                "properties": [
                    {"name": "po_id", "data_type": PropertyType.STRING, "is_primary_key": True, "is_nullable": False, "description": "Unique Purchase Order identifier"},
                    {"name": "supplier_id", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Foreign key to Supplier"},
                    {"name": "order_date", "data_type": PropertyType.DATETIME, "is_primary_key": False, "is_nullable": False, "description": "Date and time the PO was authorized"},
                    {"name": "total_amount", "data_type": PropertyType.NUMBER, "is_primary_key": False, "is_nullable": False, "description": "Authorized committed spend amount"},
                    {"name": "currency", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "ISO transaction currency code"},
                    {"name": "status", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "PO approval lifecycle status"},
                ],
            },
            {
                "name": "GoodsReceipt",
                "display_name": "Goods Receipt (GR)",
                "description": "Warehouse intake record acknowledging delivery of purchased items.",
                "primary_key_property": "receipt_id",
                "properties": [
                    {"name": "receipt_id", "data_type": PropertyType.STRING, "is_primary_key": True, "is_nullable": False, "description": "Unique delivery receipt identifier"},
                    {"name": "po_id", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Foreign key to Purchase Order"},
                    {"name": "delivery_date", "data_type": PropertyType.DATETIME, "is_primary_key": False, "is_nullable": False, "description": "Timestamp of physical delivery"},
                    {"name": "quantity_received", "data_type": PropertyType.NUMBER, "is_primary_key": False, "is_nullable": False, "description": "Accepted physical item count"},
                    {"name": "status", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Inspection status (ACCEPTED, DEFECTIVE)"},
                ],
            },
            {
                "name": "Invoice",
                "display_name": "Vendor Invoice",
                "description": "Financial billing request submitted by a supplier against a PO.",
                "primary_key_property": "invoice_id",
                "properties": [
                    {"name": "invoice_id", "data_type": PropertyType.STRING, "is_primary_key": True, "is_nullable": False, "description": "Unique invoice reference number"},
                    {"name": "po_id", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": True, "description": "Foreign key to Purchase Order"},
                    {"name": "supplier_id", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Foreign key to Supplier"},
                    {"name": "invoice_date", "data_type": PropertyType.DATETIME, "is_primary_key": False, "is_nullable": False, "description": "Date invoice was billed"},
                    {"name": "invoice_amount", "data_type": PropertyType.NUMBER, "is_primary_key": False, "is_nullable": False, "description": "Billed gross monetary amount"},
                    {"name": "due_date", "data_type": PropertyType.DATETIME, "is_primary_key": False, "is_nullable": True, "description": "Payment term due date"},
                    {"name": "currency", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Billed currency code"},
                    {"name": "status", "data_type": PropertyType.STRING, "is_primary_key": False, "is_nullable": False, "description": "Invoice status (PENDING, PAID, DISCREPANT)"},
                ],
            },
        ]

        created_objects: dict[str, BusinessObject] = {}

        for defn in p2p_definitions:
            existing = await self.session.execute(
                select(BusinessObject)
                .options(selectinload(BusinessObject.properties))
                .where(
                    BusinessObject.project_id == project_id,
                    BusinessObject.name == defn["name"],
                )
            )
            obj = existing.scalar_one_or_none()
            if obj is None:
                obj = BusinessObject(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    name=defn["name"],
                    display_name=defn["display_name"],
                    description=defn["description"],
                    primary_key_property=defn["primary_key_property"],
                    version=1,
                )
                self.session.add(obj)

                for p in defn["properties"]:
                    prop = Property(
                        id=uuid.uuid4(),
                        business_object_id=obj.id,
                        name=p["name"],
                        display_name=p["name"].replace("_", " ").title(),
                        data_type=p["data_type"].value,
                        is_nullable=p["is_nullable"],
                        is_primary_key=p["is_primary_key"],
                        description=p["description"],
                    )
                    self.session.add(prop)
            created_objects[defn["name"]] = obj

        await self.session.commit()

        # Refresh objects to ensure IDs are assigned
        for name in list(created_objects.keys()):
            refreshed = await self.get_business_object(
                org_id, project_id, created_objects[name].id, user_id
            )
            created_objects[name] = refreshed

        # Define default P2P relationships
        relationships = [
            ("supplies", "Supplier", "PurchaseOrder", RelationshipCardinality.ONE_TO_MANY, {"source_property": "supplier_id", "target_property": "supplier_id"}),
            ("received_as", "PurchaseOrder", "GoodsReceipt", RelationshipCardinality.ONE_TO_MANY, {"source_property": "po_id", "target_property": "po_id"}),
            ("billed_in", "PurchaseOrder", "Invoice", RelationshipCardinality.ONE_TO_MANY, {"source_property": "po_id", "target_property": "po_id"}),
            ("invoices", "Supplier", "Invoice", RelationshipCardinality.ONE_TO_MANY, {"source_property": "supplier_id", "target_property": "supplier_id"}),
        ]

        for rel_name, src_name, tgt_name, card, join_exp in relationships:
            src_obj = created_objects.get(src_name)
            tgt_obj = created_objects.get(tgt_name)
            if src_obj and tgt_obj:
                rel_check = await self.session.execute(
                    select(Relationship).where(
                        Relationship.project_id == project_id,
                        Relationship.name == rel_name,
                        Relationship.source_object_id == src_obj.id,
                        Relationship.target_object_id == tgt_obj.id,
                    )
                )
                if rel_check.scalar_one_or_none() is None:
                    rel = Relationship(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        name=rel_name,
                        source_object_id=src_obj.id,
                        target_object_id=tgt_obj.id,
                        cardinality=card.value,
                        join_expression_json=join_exp,
                    )
                    self.session.add(rel)

        await self.session.commit()
        return list(created_objects.values())

    # ==========================================================================
    # Semantic Discovery & Mapping Engine
    # ==========================================================================

    async def discover_semantic_mappings(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: SemanticDiscoveryRequest,
    ) -> SemanticDiscoveryResponse:
        """Run deterministic matching against a dataset version, generating confidence-scored

        suggestions with explainability notes. Suggestions are persisted with status SUGGESTED
        and are never activated automatically.
        """
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # 1. Fetch Business Object and its properties
        obj = await self.get_business_object(org_id, project_id, req.business_object_id, user_id)

        # 2. Fetch Dataset and Dataset Version (validating same-project integrity)
        ds_stmt = select(Dataset).where(
            Dataset.id == req.dataset_id,
            Dataset.project_id == project_id,
        )
        dataset = (await self.session.execute(ds_stmt)).scalar_one_or_none()
        if dataset is None:
            raise DatasetNotFoundException(req.dataset_id)

        ver_stmt = select(DatasetVersion).where(
            DatasetVersion.id == req.dataset_version_id,
            DatasetVersion.dataset_id == req.dataset_id,
            DatasetVersion.project_id == project_id,
        )
        version = (await self.session.execute(ver_stmt)).scalar_one_or_none()
        if version is None:
            raise DatasetVersionNotFoundException(req.dataset_id, req.dataset_version_id)

        raw_schema = version.schema_metadata_json
        schema_metadata: list[dict[str, Any]] = list(raw_schema) if isinstance(raw_schema, list) else []
        profiling_summary: dict[str, Any] = version.profiling_summary_json if isinstance(version.profiling_summary_json, dict) else {}
        profiling_columns: list[dict[str, Any]] = profiling_summary.get("columns", [])

        # 3. Execute Deterministic Semantic Matcher
        candidates = SemanticMatcher.discover_mappings_for_object(
            business_object_properties=obj.properties,
            dataset_schema=schema_metadata,
            profiling_columns=profiling_columns,
        )

        persisted_suggestions: list[PropertyMapping] = []

        for cand in candidates:
            prop_id = uuid.UUID(cand.property_id)

            # Check if mapping record already exists for this property, version, and column
            existing_stmt = select(PropertyMapping).where(
                PropertyMapping.property_id == prop_id,
                PropertyMapping.dataset_version_id == version.id,
                PropertyMapping.column_name == cand.column_name,
            )
            mapping = (await self.session.execute(existing_stmt)).scalar_one_or_none()

            if mapping is None:
                mapping = PropertyMapping(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    property_id=prop_id,
                    dataset_id=dataset.id,
                    dataset_version_id=version.id,
                    column_name=cand.column_name,
                    confidence=cand.confidence,
                    status=MappingStatus.SUGGESTED.value,
                    explanation=cand.explanation,
                )
                self.session.add(mapping)
            else:
                # Update confidence and explanation if previously suggested
                if mapping.status == MappingStatus.SUGGESTED.value:
                    mapping.confidence = cand.confidence
                    mapping.explanation = cand.explanation

            persisted_suggestions.append(mapping)

        await self.session.commit()

        # Build response items
        prop_map = {p.id: p for p in obj.properties}
        resp_items: list[PropertyMappingResponse] = []
        for s in persisted_suggestions:
            p = prop_map.get(s.property_id)
            resp_items.append(
                PropertyMappingResponse(
                    id=s.id,
                    project_id=s.project_id,
                    property_id=s.property_id,
                    property_name=p.name if p else None,
                    business_object_id=obj.id,
                    business_object_name=obj.name,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    dataset_version_id=version.id,
                    column_name=s.column_name,
                    confidence=s.confidence,
                    status=s.status,
                    explanation=s.explanation,
                    created_at=s.created_at,
                )
            )

        return SemanticDiscoveryResponse(
            dataset_id=dataset.id,
            dataset_version_id=version.id,
            business_object_id=obj.id,
            business_object_name=obj.name,
            suggestions=resp_items,
            total_suggested=len(resp_items),
        )

    async def create_property_mapping(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: PropertyMappingCreateRequest,
    ) -> PropertyMapping:
        """Create or update an explicit column-to-property mapping, performing strict compatibility checks."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Validate property exists and belongs to a Business Object in this project
        prop_stmt = (
            select(Property)
            .join(BusinessObject, Property.business_object_id == BusinessObject.id)
            .where(
                Property.id == req.property_id,
                BusinessObject.project_id == project_id,
            )
        )
        prop = (await self.session.execute(prop_stmt)).scalar_one_or_none()
        if prop is None:
            raise PropertyNotFoundException("Target property not found in this project workspace")

        # Validate dataset and version exist in this project
        ver_stmt = (
            select(DatasetVersion)
            .where(
                DatasetVersion.id == req.dataset_version_id,
                DatasetVersion.dataset_id == req.dataset_id,
                DatasetVersion.project_id == project_id,
            )
        )
        version = (await self.session.execute(ver_stmt)).scalar_one_or_none()
        if version is None:
            raise DatasetVersionNotFoundException(req.dataset_id, req.dataset_version_id)

        # Validate column exists in discovered schema metadata
        raw_schema = version.schema_metadata_json
        schema_metadata: list[dict[str, Any]] = list(raw_schema) if isinstance(raw_schema, list) else []
        col_meta = next((c for c in schema_metadata if c.get("name") == req.column_name), None)
        if col_meta is None:
            raise InvalidPropertyMappingException(
                f"Column '{req.column_name}' not found in dataset version schema"
            )

        # Validate type compatibility
        col_type = col_meta.get("data_type", "STRING")
        if prop.data_type == PropertyType.NUMBER.value and col_type in ("DATETIME", "BOOLEAN"):
            raise IncompatibleMappingTypeException(
                f"Cannot map temporal/boolean column '{req.column_name}' to numeric property '{prop.name}'"
            )

        # Upsert mapping
        existing = await self.session.execute(
            select(PropertyMapping).where(
                PropertyMapping.property_id == prop.id,
                PropertyMapping.dataset_version_id == version.id,
                PropertyMapping.column_name == req.column_name,
            )
        )
        mapping = existing.scalar_one_or_none()
        if mapping is None:
            mapping = PropertyMapping(
                id=uuid.uuid4(),
                project_id=project_id,
                property_id=prop.id,
                dataset_id=req.dataset_id,
                dataset_version_id=version.id,
                column_name=req.column_name,
                confidence=req.confidence,
                status=req.status.value,
                explanation=req.explanation,
            )
            self.session.add(mapping)
        else:
            mapping.confidence = req.confidence
            mapping.status = req.status.value
            mapping.explanation = req.explanation

        # If confirmed, activate in Property.source_mapping_json
        if req.status == MappingStatus.CONFIRMED:
            prop.source_mapping_json = {
                "dataset_id": str(req.dataset_id),
                "dataset_version_id": str(version.id),
                "column_name": req.column_name,
                "confidence": req.confidence,
                "status": MappingStatus.CONFIRMED.value,
                "explanation": req.explanation,
            }

        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def accept_mapping(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        mapping_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PropertyMapping:
        """Explicitly accept a suggested mapping, activating it on the Property."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        mapping = await self._get_mapping(project_id, mapping_id)
        mapping.status = MappingStatus.CONFIRMED.value

        # Update parent property's active source mapping
        prop = await self.session.get(Property, mapping.property_id)
        if prop:
            prop.source_mapping_json = {
                "dataset_id": str(mapping.dataset_id),
                "dataset_version_id": str(mapping.dataset_version_id),
                "column_name": mapping.column_name,
                "confidence": mapping.confidence,
                "status": MappingStatus.CONFIRMED.value,
                "explanation": mapping.explanation,
            }

        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def reject_mapping(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        mapping_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PropertyMapping:
        """Explicitly reject a suggested mapping."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        mapping = await self._get_mapping(project_id, mapping_id)
        mapping.status = MappingStatus.REJECTED.value

        # If property was pointing to this mapping, clear it
        prop = await self.session.get(Property, mapping.property_id)
        if (
            prop
            and prop.source_mapping_json
            and prop.source_mapping_json.get("dataset_version_id") == str(mapping.dataset_version_id)
            and prop.source_mapping_json.get("column_name") == mapping.column_name
        ):
            prop.source_mapping_json = None

        await self.session.commit()
        await self.session.refresh(mapping)
        return mapping

    async def list_mappings(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        status: str | None = None,
        business_object_id: uuid.UUID | None = None,
    ) -> list[PropertyMappingResponse]:
        """List mappings within a project workspace with related entity names resolved."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)

        stmt = (
            select(
                PropertyMapping,
                Property.name.label("property_name"),
                BusinessObject.id.label("business_object_id"),
                BusinessObject.name.label("business_object_name"),
                Dataset.name.label("dataset_name"),
            )
            .join(Property, PropertyMapping.property_id == Property.id)
            .join(BusinessObject, Property.business_object_id == BusinessObject.id)
            .join(Dataset, PropertyMapping.dataset_id == Dataset.id)
            .where(PropertyMapping.project_id == project_id)
        )

        if status:
            stmt = stmt.where(PropertyMapping.status == status.upper())
        if business_object_id:
            stmt = stmt.where(BusinessObject.id == business_object_id)

        stmt = stmt.order_by(PropertyMapping.created_at.desc())
        results = (await self.session.execute(stmt)).all()

        items: list[PropertyMappingResponse] = []
        for row in results:
            m = row[0]
            items.append(
                PropertyMappingResponse(
                    id=m.id,
                    project_id=m.project_id,
                    property_id=m.property_id,
                    property_name=row.property_name,
                    business_object_id=row.business_object_id,
                    business_object_name=row.business_object_name,
                    dataset_id=m.dataset_id,
                    dataset_name=row.dataset_name,
                    dataset_version_id=m.dataset_version_id,
                    column_name=m.column_name,
                    confidence=m.confidence,
                    status=m.status,
                    explanation=m.explanation,
                    created_at=m.created_at,
                )
            )
        return items

    async def delete_mapping(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        mapping_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete a property mapping."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        mapping = await self._get_mapping(project_id, mapping_id)
        prop = await self.session.get(Property, mapping.property_id)
        if (
            prop
            and prop.source_mapping_json
            and prop.source_mapping_json.get("dataset_version_id") == str(mapping.dataset_version_id)
            and prop.source_mapping_json.get("column_name") == mapping.column_name
        ):
            prop.source_mapping_json = None

        await self.session.delete(mapping)
        await self.session.commit()

    async def _get_mapping(self, project_id: uuid.UUID, mapping_id: uuid.UUID) -> PropertyMapping:
        stmt = select(PropertyMapping).where(
            PropertyMapping.id == mapping_id,
            PropertyMapping.project_id == project_id,
        )
        mapping = (await self.session.execute(stmt)).scalar_one_or_none()
        if mapping is None:
            raise PropertyMappingNotFoundException("Property mapping not found")
        return mapping

    # ==========================================================================
    # Graph & Traversal
    # ==========================================================================

    async def get_ontology_graph(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OntologyGraphResponse:
        """Construct the complete graph representation (nodes, properties, edges) of the project ontology."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)

        objects = await self.list_business_objects(org_id, project_id, user_id)
        relationships = await self.list_relationships(org_id, project_id, user_id)

        nodes: list[OntologyGraphNode] = []
        total_mapped = 0

        for obj in objects:
            prop_resps: list[PropertyResponse] = []
            mapped_count = 0
            for p in obj.properties:
                is_mapped = p.source_mapping_json is not None
                if is_mapped:
                    mapped_count += 1
                    total_mapped += 1
                prop_resps.append(
                    PropertyResponse(
                        id=p.id,
                        business_object_id=p.business_object_id,
                        name=p.name,
                        display_name=p.display_name,
                        data_type=p.data_type,
                        is_nullable=p.is_nullable,
                        is_primary_key=p.is_primary_key,
                        description=p.description,
                        source_mapping=p.source_mapping_json,
                        created_at=p.created_at,
                    )
                )

            nodes.append(
                OntologyGraphNode(
                    id=str(obj.id),
                    name=obj.name,
                    display_name=obj.display_name,
                    description=obj.description,
                    properties=prop_resps,
                    mapped_properties_count=mapped_count,
                    total_properties_count=len(obj.properties),
                )
            )

        edges: list[OntologyGraphEdge] = [
            OntologyGraphEdge(
                id=str(r.id),
                name=r.name,
                source=str(r.source_object_id),
                target=str(r.target_object_id),
                cardinality=r.cardinality,
                join_expression=r.join_expression_json,
            )
            for r in relationships
        ]

        return OntologyGraphResponse(
            project_id=project_id,
            nodes=nodes,
            edges=edges,
            total_objects=len(nodes),
            total_relationships=len(edges),
            total_mapped_properties=total_mapped,
        )

    async def traverse_ontology(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        object_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OntologyTraversalResponse:
        """Inspect deterministic traversal paths connected to a specific Business Object."""
        obj = await self.get_business_object(org_id, project_id, object_id, user_id)
        relationships = await self.list_relationships(org_id, project_id, user_id)

        outgoing: list[TraversalStep] = []
        incoming: list[TraversalStep] = []

        for r in relationships:
            if r.source_object_id == object_id and r.target_object:
                outgoing.append(
                    TraversalStep(
                        relationship_id=r.id,
                        relationship_name=r.name,
                        cardinality=r.cardinality,
                        target_object_id=r.target_object_id,
                        target_object_name=r.target_object.name,
                        join_expression=r.join_expression_json,
                    )
                )
            elif r.target_object_id == object_id and r.source_object:
                incoming.append(
                    TraversalStep(
                        relationship_id=r.id,
                        relationship_name=r.name,
                        cardinality=r.cardinality,
                        target_object_id=r.source_object_id,
                        target_object_name=r.source_object.name,
                        join_expression=r.join_expression_json,
                    )
                )

        return OntologyTraversalResponse(
            start_object_id=obj.id,
            start_object_name=obj.name,
            outgoing_paths=outgoing,
            incoming_paths=incoming,
        )
