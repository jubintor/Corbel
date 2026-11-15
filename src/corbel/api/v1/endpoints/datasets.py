"""Data Intelligence REST API endpoints for data sources, dataset ingestion, and profiling."""

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.core.database import get_db_session
from corbel.domains.data_intelligence.schemas import (
    DatasetPreviewResponse,
    DatasetResponse,
    DatasetVersionResponse,
    DataSourceCreateRequest,
    DataSourceResponse,
)
from corbel.domains.data_intelligence.service import DataIntelligenceService
from corbel.domains.tenancy.dependencies import TenantContext, get_active_tenant_context

router = APIRouter()


# ==============================================================================
# Data Sources
# ==============================================================================


@router.post(
    "/projects/{project_id}/data-sources",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Data Source",
    description="Register a data source connection within a project workspace.",
)
async def create_data_source(
    project_id: uuid.UUID,
    req: DataSourceCreateRequest,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> DataSourceResponse:
    service = DataIntelligenceService(session)
    source = await service.create_data_source(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        req=req,
    )
    return DataSourceResponse.model_validate(source)


@router.get(
    "/projects/{project_id}/data-sources",
    response_model=list[DataSourceResponse],
    status_code=status.HTTP_200_OK,
    summary="List Data Sources",
    description="List all data sources configured within a project workspace.",
)
async def list_data_sources(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[DataSourceResponse]:
    service = DataIntelligenceService(session)
    sources = await service.list_data_sources(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )
    return [DataSourceResponse.model_validate(s) for s in sources]


# ==============================================================================
# Dataset Ingestion & Profiling
# ==============================================================================


@router.post(
    "/projects/{project_id}/datasets/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload & Profile Dataset",
    description="Securely upload, parse, and deterministically profile a tabular dataset (CSV, JSON, XLSX).",
)
async def upload_dataset(
    project_id: uuid.UUID,
    file: UploadFile = File(..., description="Tabular dataset file (CSV, JSON, XLSX)"),
    name: str | None = Form(default=None, description="Optional custom dataset name"),
    description: str | None = Form(default=None, description="Optional dataset description"),
    data_source_id: uuid.UUID | None = Form(default=None, description="Optional data source ID"),
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetResponse:
    service = DataIntelligenceService(session)
    dataset = await service.ingest_dataset_upload(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
        file=file,
        name=name,
        description=description,
        data_source_id=data_source_id,
    )
    return DataIntelligenceService.map_to_response(dataset)


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[DatasetResponse],
    status_code=status.HTTP_200_OK,
    summary="List Project Datasets",
    description="List all datasets cataloged within a project workspace.",
)
async def list_project_datasets(
    project_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[DatasetResponse]:
    service = DataIntelligenceService(session)
    datasets = await service.list_datasets(
        org_id=context.organization_id,
        project_id=project_id,
        user_id=context.user_id,
    )
    return [DataIntelligenceService.map_to_response(d) for d in datasets]


@router.get(
    "/datasets",
    response_model=list[DatasetResponse],
    status_code=status.HTTP_200_OK,
    summary="List Organization Datasets",
    description="List all datasets cataloged across all accessible projects in the active tenant organization.",
)
async def list_organization_datasets(
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> list[DatasetResponse]:
    service = DataIntelligenceService(session)
    datasets = await service.list_organization_datasets(
        org_id=context.organization_id,
        user_id=context.user_id,
    )
    return [DataIntelligenceService.map_to_response(d) for d in datasets]


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}",
    response_model=DatasetResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dataset Details",
    description="Retrieve dataset metadata, versions, and profiling summary.",
)
async def get_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetResponse:
    service = DataIntelligenceService(session)
    dataset = await service.get_dataset(
        org_id=context.organization_id,
        project_id=project_id,
        dataset_id=dataset_id,
        user_id=context.user_id,
    )
    return DataIntelligenceService.map_to_response(dataset)


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/versions/{version_id}",
    response_model=DatasetVersionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Dataset Version Snapshot",
    description="Retrieve complete schema metadata and statistical profile for a specific dataset version.",
)
async def get_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: str,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetVersionResponse:
    service = DataIntelligenceService(session)
    v = await service.get_dataset_version(
        org_id=context.organization_id,
        project_id=project_id,
        dataset_id=dataset_id,
        version_id_or_number=version_id,
        user_id=context.user_id,
    )
    return DatasetVersionResponse.from_orm_model(v)


@router.get(
    "/projects/{project_id}/datasets/{dataset_id}/preview",
    response_model=DatasetPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview Dataset Rows",
    description="Retrieve first N sample rows from the stored dataset without loading entire file into memory.",
)
async def get_dataset_preview(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100, description="Max rows to preview"),
    version_id: uuid.UUID | None = Query(default=None, description="Optional specific version ID"),
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> DatasetPreviewResponse:
    service = DataIntelligenceService(session)
    return await service.get_dataset_preview(
        org_id=context.organization_id,
        project_id=project_id,
        dataset_id=dataset_id,
        version_id=version_id,
        user_id=context.user_id,
        limit=limit,
    )


@router.delete(
    "/projects/{project_id}/datasets/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Dataset",
    description="Delete a dataset, all its versions, and its stored files.",
)
async def delete_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    context: TenantContext = Depends(get_active_tenant_context),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    service = DataIntelligenceService(session)
    await service.delete_dataset(
        org_id=context.organization_id,
        project_id=project_id,
        dataset_id=dataset_id,
        user_id=context.user_id,
    )
