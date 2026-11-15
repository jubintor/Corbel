"""API endpoints for Phase 4: Ontology Engine & Semantic Discovery."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.ontology.models import BusinessObject, Relationship
from corbel.domains.ontology.schemas import (
    BusinessObjectCreateRequest,
    BusinessObjectDetailResponse,
    BusinessObjectResponse,
    BusinessObjectUpdateRequest,
    OntologyGraphResponse,
    OntologyTraversalResponse,
    PropertyCreateRequest,
    PropertyMappingCreateRequest,
    PropertyMappingResponse,
    PropertyResponse,
    PropertyUpdateRequest,
    RelationshipCreateRequest,
    RelationshipResponse,
    SemanticDiscoveryRequest,
    SemanticDiscoveryResponse,
)
from corbel.domains.ontology.service import OntologyService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context

router = APIRouter(tags=["Ontology Engine & Semantic Discovery"])


def _map_object_to_detail(obj: BusinessObject) -> BusinessObjectDetailResponse:
    props = [
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
        for p in obj.properties
    ]
    return BusinessObjectDetailResponse(
        id=obj.id,
        project_id=obj.project_id,
        name=obj.name,
        display_name=obj.display_name,
        description=obj.description,
        primary_key_property=obj.primary_key_property,
        version=obj.version,
        property_count=len(obj.properties),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
        properties=props,
    )


def _map_object_to_summary(obj: BusinessObject) -> BusinessObjectResponse:
    return BusinessObjectResponse(
        id=obj.id,
        project_id=obj.project_id,
        name=obj.name,
        display_name=obj.display_name,
        description=obj.description,
        primary_key_property=obj.primary_key_property,
        version=obj.version,
        property_count=len(obj.properties),
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


def _map_relationship(rel: Relationship) -> RelationshipResponse:
    return RelationshipResponse(
        id=rel.id,
        project_id=rel.project_id,
        name=rel.name,
        source_object_id=rel.source_object_id,
        source_object_name=rel.source_object.name if rel.source_object else None,
        target_object_id=rel.target_object_id,
        target_object_name=rel.target_object.name if rel.target_object else None,
        cardinality=rel.cardinality,
        description=rel.description,
        join_expression=rel.join_expression_json,
        created_at=rel.created_at,
    )


# ==============================================================================
# P2P Seed & Graph
# ==============================================================================


@router.post(
    "/projects/{project_id}/ontology/seed-p2p",
    response_model=list[BusinessObjectDetailResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Seed P2P Baseline Ontology",
    description="Idempotently initialize baseline Procure-to-Pay Business Objects (Supplier, PO, GR, Invoice) and Relationships.",
)
async def seed_p2p_ontology(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[BusinessObjectDetailResponse]:
    service = OntologyService(session)
    objects = await service.seed_p2p_ontology(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )
    return [_map_object_to_detail(o) for o in objects]


@router.get(
    "/projects/{project_id}/ontology/graph",
    response_model=OntologyGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Full Ontology Graph",
    description="Retrieve all Business Objects, Properties, mapping counts, and directed Relationships.",
)
async def get_ontology_graph(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> OntologyGraphResponse:
    service = OntologyService(session)
    return await service.get_ontology_graph(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )


@router.get(
    "/projects/{project_id}/ontology/objects/{object_id}/traverse",
    response_model=OntologyTraversalResponse,
    status_code=status.HTTP_200_OK,
    summary="Traverse Connected Business Objects",
    description="Traverse outgoing and incoming semantic relationships connected to a Business Object.",
)
async def traverse_ontology(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> OntologyTraversalResponse:
    service = OntologyService(session)
    return await service.traverse_ontology(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        user_id=context.user_id,
    )


# ==============================================================================
# Business Objects CRUD
# ==============================================================================


@router.get(
    "/projects/{project_id}/ontology/objects",
    response_model=list[BusinessObjectDetailResponse],
    status_code=status.HTTP_200_OK,
    summary="List Business Objects",
    description="List all Business Objects configured in a project workspace.",
)
async def list_business_objects(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[BusinessObjectDetailResponse]:
    service = OntologyService(session)
    objects = await service.list_business_objects(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )
    return [_map_object_to_detail(o) for o in objects]


@router.post(
    "/projects/{project_id}/ontology/objects",
    response_model=BusinessObjectDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Business Object",
    description="Define a new Business Object with optional initial properties.",
)
async def create_business_object(
    project_id: uuid.UUID,
    req: BusinessObjectCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessObjectDetailResponse:
    service = OntologyService(session)
    obj = await service.create_business_object(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )
    return _map_object_to_detail(obj)


@router.get(
    "/projects/{project_id}/ontology/objects/{object_id}",
    response_model=BusinessObjectDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Business Object Details",
    description="Retrieve a Business Object with all properties and mapping status.",
)
async def get_business_object(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessObjectDetailResponse:
    service = OntologyService(session)
    obj = await service.get_business_object(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        user_id=context.user_id,
    )
    return _map_object_to_detail(obj)


@router.put(
    "/projects/{project_id}/ontology/objects/{object_id}",
    response_model=BusinessObjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Business Object",
    description="Update metadata for an existing Business Object.",
)
async def update_business_object(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    req: BusinessObjectUpdateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> BusinessObjectResponse:
    service = OntologyService(session)
    obj = await service.update_business_object(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        user_id=context.user_id,
        req=req,
    )
    return _map_object_to_summary(obj)


@router.delete(
    "/projects/{project_id}/ontology/objects/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Business Object",
    description="Delete a Business Object, cascading to properties and connected relationships.",
)
async def delete_business_object(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = OntologyService(session)
    await service.delete_business_object(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        user_id=context.user_id,
    )


# ==============================================================================
# Properties Management
# ==============================================================================


@router.post(
    "/projects/{project_id}/ontology/objects/{object_id}/properties",
    response_model=PropertyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Property",
    description="Add a new Property to an existing Business Object.",
)
async def add_property(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    req: PropertyCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    service = OntologyService(session)
    p = await service.add_property(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        user_id=context.user_id,
        req=req,
    )
    return PropertyResponse(
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


@router.put(
    "/projects/{project_id}/ontology/objects/{object_id}/properties/{property_id}",
    response_model=PropertyResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Property",
    description="Update an existing Property's attributes.",
)
async def update_property(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    property_id: uuid.UUID,
    req: PropertyUpdateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> PropertyResponse:
    service = OntologyService(session)
    p = await service.update_property(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        property_id=property_id,
        user_id=context.user_id,
        req=req,
    )
    return PropertyResponse(
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


@router.delete(
    "/projects/{project_id}/ontology/objects/{object_id}/properties/{property_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Property",
    description="Remove a Property from a Business Object.",
)
async def delete_property(
    project_id: uuid.UUID,
    object_id: uuid.UUID,
    property_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = OntologyService(session)
    await service.delete_property(
        org_id=context.organization_id,
        project_id=project_id,
        object_id=object_id,
        property_id=property_id,
        user_id=context.user_id,
    )


# ==============================================================================
# Relationships Management
# ==============================================================================


@router.get(
    "/projects/{project_id}/ontology/relationships",
    response_model=list[RelationshipResponse],
    status_code=status.HTTP_200_OK,
    summary="List Relationships",
    description="List all directed relationships between Business Objects in this project.",
)
async def list_relationships(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[RelationshipResponse]:
    service = OntologyService(session)
    rels = await service.list_relationships(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )
    return [_map_relationship(r) for r in rels]


@router.post(
    "/projects/{project_id}/ontology/relationships",
    response_model=RelationshipResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Relationship",
    description="Create a directed semantic relationship between two Business Objects.",
)
async def create_relationship(
    project_id: uuid.UUID,
    req: RelationshipCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> RelationshipResponse:
    service = OntologyService(session)
    rel = await service.create_relationship(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )
    return _map_relationship(rel)


@router.delete(
    "/projects/{project_id}/ontology/relationships/{relationship_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Relationship",
    description="Delete a relationship.",
)
async def delete_relationship(
    project_id: uuid.UUID,
    relationship_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = OntologyService(session)
    await service.delete_relationship(
        org_id=context.organization_id,
        project_id=project_id,
        relationship_id=relationship_id,
        user_id=context.user_id,
    )


# ==============================================================================
# Semantic Discovery & Mappings
# ==============================================================================


@router.post(
    "/projects/{project_id}/ontology/discover-mappings",
    response_model=SemanticDiscoveryResponse,
    status_code=status.HTTP_200_OK,
    summary="Run Deterministic Semantic Discovery",
    description="Analyze a dataset version against a Business Object and produce explainable, confidence-scored candidate suggestions.",
)
async def discover_semantic_mappings(
    project_id: uuid.UUID,
    req: SemanticDiscoveryRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> SemanticDiscoveryResponse:
    service = OntologyService(session)
    return await service.discover_semantic_mappings(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )


@router.get(
    "/projects/{project_id}/ontology/mappings",
    response_model=list[PropertyMappingResponse],
    status_code=status.HTTP_200_OK,
    summary="List Semantic Mappings",
    description="List column-to-property mappings (suggested, confirmed, or rejected).",
)
async def list_property_mappings(
    project_id: uuid.UUID,
    status: str | None = Query(default=None, description="Filter by status (SUGGESTED, CONFIRMED, REJECTED)"),
    business_object_id: uuid.UUID | None = Query(default=None, description="Filter by Business Object ID"),
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[PropertyMappingResponse]:
    service = OntologyService(session)
    return await service.list_mappings(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        status=status,
        business_object_id=business_object_id,
    )


@router.post(
    "/projects/{project_id}/ontology/mappings",
    response_model=PropertyMappingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Explicit Property Mapping",
    description="Manually create or override a column-to-property mapping with strict compatibility validation.",
)
async def create_property_mapping(
    project_id: uuid.UUID,
    req: PropertyMappingCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> PropertyMappingResponse:
    service = OntologyService(session)
    m = await service.create_property_mapping(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )
    return PropertyMappingResponse(
        id=m.id,
        project_id=m.project_id,
        property_id=m.property_id,
        dataset_id=m.dataset_id,
        dataset_version_id=m.dataset_version_id,
        column_name=m.column_name,
        confidence=m.confidence,
        status=m.status,
        explanation=m.explanation,
        created_at=m.created_at,
    )


@router.post(
    "/projects/{project_id}/ontology/mappings/{mapping_id}/accept",
    response_model=PropertyMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept Suggested Mapping",
    description="Explicitly accept a candidate suggestion, updating status to CONFIRMED and activating on the Property.",
)
async def accept_mapping(
    project_id: uuid.UUID,
    mapping_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> PropertyMappingResponse:
    service = OntologyService(session)
    m = await service.accept_mapping(
        org_id=context.organization_id,
        project_id=project_id,
        mapping_id=mapping_id,
        user_id=context.user_id,
    )
    return PropertyMappingResponse(
        id=m.id,
        project_id=m.project_id,
        property_id=m.property_id,
        dataset_id=m.dataset_id,
        dataset_version_id=m.dataset_version_id,
        column_name=m.column_name,
        confidence=m.confidence,
        status=m.status,
        explanation=m.explanation,
        created_at=m.created_at,
    )


@router.post(
    "/projects/{project_id}/ontology/mappings/{mapping_id}/reject",
    response_model=PropertyMappingResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject Suggested Mapping",
    description="Explicitly reject a candidate suggestion.",
)
async def reject_mapping(
    project_id: uuid.UUID,
    mapping_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> PropertyMappingResponse:
    service = OntologyService(session)
    m = await service.reject_mapping(
        org_id=context.organization_id,
        project_id=project_id,
        mapping_id=mapping_id,
        user_id=context.user_id,
    )
    return PropertyMappingResponse(
        id=m.id,
        project_id=m.project_id,
        property_id=m.property_id,
        dataset_id=m.dataset_id,
        dataset_version_id=m.dataset_version_id,
        column_name=m.column_name,
        confidence=m.confidence,
        status=m.status,
        explanation=m.explanation,
        created_at=m.created_at,
    )


@router.delete(
    "/projects/{project_id}/ontology/mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Property Mapping",
    description="Remove a column-to-property mapping.",
)
async def delete_property_mapping(
    project_id: uuid.UUID,
    mapping_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = OntologyService(session)
    await service.delete_mapping(
        org_id=context.organization_id,
        project_id=project_id,
        mapping_id=mapping_id,
        user_id=context.user_id,
    )
