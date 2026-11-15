"""API endpoints for Phase 5: Structured Querying & Early AI Gateway."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.query.schemas import (
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    QueryExecutionAuditResponse,
    QuerySchemaResponse,
    StructuredQueryRequest,
    StructuredQueryResponse,
)
from corbel.domains.query.service import QueryService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context

router = APIRouter(tags=["Structured Querying & Early AI Gateway"])


@router.get(
    "/projects/{project_id}/query/schema",
    response_model=QuerySchemaResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Project Query Schema",
    description="Retrieve all queryable business entities, mapped properties, and traversable relationships.",
)
async def get_query_schema(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> QuerySchemaResponse:
    service = QueryService(session)
    return await service.get_query_schema(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )


@router.post(
    "/projects/{project_id}/query/execute",
    response_model=StructuredQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Structured Query",
    description="Validate and execute a structured query AST against confirmed ontology datasets in a read-only SQL sandbox.",
)
async def execute_structured_query(
    project_id: uuid.UUID,
    req: StructuredQueryRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> StructuredQueryResponse:
    service = QueryService(session)
    return await service.execute_query(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )


@router.post(
    "/projects/{project_id}/query/nlq",
    response_model=NaturalLanguageQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Natural Language Query Compilation",
    description="Translate a natural language question into a validated StructuredQueryRequest AST via the Early AI Gateway.",
)
async def natural_language_query(
    project_id: uuid.UUID,
    req: NaturalLanguageQueryRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> NaturalLanguageQueryResponse:
    service = QueryService(session)
    return await service.natural_language_query(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )


@router.get(
    "/projects/{project_id}/query/history",
    response_model=list[QueryExecutionAuditResponse],
    status_code=status.HTTP_200_OK,
    summary="List Query Execution Audit History",
    description="Retrieve the audit history of queries executed within the project workspace.",
)
async def get_query_history(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of historical records to return"),
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[QueryExecutionAuditResponse]:
    service = QueryService(session)
    return await service.get_query_history(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        limit=limit,
    )
