"""Data Intelligence domain service managing data sources, dataset ingestion, and profiling."""

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.core.config import get_settings
from corbel.domains.data_intelligence.exceptions import (
    DatasetNotFoundException,
    DatasetVersionNotFoundException,
    DataSourceNotFoundException,
    EmptyDatasetException,
    FileSizeLimitExceededException,
)
from corbel.domains.data_intelligence.models import (
    Dataset,
    DatasetStatus,
    DatasetVersion,
    DatasetVersionStatus,
    DataSource,
    DataSourceStatus,
    SourceType,
)
from corbel.domains.data_intelligence.parser import (
    DatasetParser,
    detect_file_format,
    sanitize_filename,
)
from corbel.domains.data_intelligence.profiler import DatasetProfiler
from corbel.domains.data_intelligence.schemas import (
    DatasetPreviewResponse,
    DatasetResponse,
    DatasetVersionResponse,
    DataSourceCreateRequest,
)
from corbel.domains.tenancy.models import Project, ProjectRole
from corbel.domains.tenancy.service import TenancyService


class DataIntelligenceService:
    """Service orchestrating dataset persistence, storage isolation, and deterministic profiling."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tenancy_service = TenancyService(session)
        self.settings = get_settings()

    # ==========================================================================
    # Data Sources
    # ==========================================================================

    async def get_or_create_default_file_source(self, project_id: uuid.UUID) -> DataSource:
        """Retrieve or initialize the default FILE_INGEST data source for a project."""
        stmt = select(DataSource).where(
            DataSource.project_id == project_id,
            DataSource.source_type == SourceType.FILE_INGEST.value,
            DataSource.name == "File Uploads",
        )
        source = (await self.session.execute(stmt)).scalar_one_or_none()
        if source is not None:
            return source

        new_source = DataSource(
            id=uuid.uuid4(),
            project_id=project_id,
            name="File Uploads",
            source_type=SourceType.FILE_INGEST.value,
            status=DataSourceStatus.ACTIVE.value,
        )
        self.session.add(new_source)
        await self.session.commit()
        await self.session.refresh(new_source)
        return new_source

    async def create_data_source(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: DataSourceCreateRequest,
    ) -> DataSource:
        """Register a new Data Source within the project workspace."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        source = DataSource(
            id=uuid.uuid4(),
            project_id=project_id,
            name=req.name.strip(),
            source_type=req.source_type.value,
            connection_config_encrypted=req.connection_config_encrypted,
            status=DataSourceStatus.ACTIVE.value,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def list_data_sources(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[DataSource]:
        """List all data sources in the given project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(org_id, project_id, user_id)
        stmt = (
            select(DataSource)
            .where(DataSource.project_id == project_id)
            .order_by(DataSource.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_data_source(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        source_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> DataSource:
        """Retrieve a specific data source in the given project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(org_id, project_id, user_id)
        stmt = select(DataSource).where(
            DataSource.project_id == project_id,
            DataSource.id == source_id,
        )
        source = (await self.session.execute(stmt)).scalar_one_or_none()
        if source is None:
            raise DataSourceNotFoundException(source_id)
        return source

    # ==========================================================================
    # Dataset Ingestion & Profiling
    # ==========================================================================

    async def ingest_dataset_upload(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        file: UploadFile,
        name: str | None = None,
        description: str | None = None,
        data_source_id: uuid.UUID | None = None,
    ) -> Dataset:
        """Process file upload: sanitize, stream to isolated storage, parse, and profile deterministically."""
        # 1. Enforce project access and organization ownership
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # 2. Validate and sanitize filename
        raw_filename = file.filename or "uploaded_dataset.csv"
        safe_filename = sanitize_filename(raw_filename)
        detected_format = detect_file_format(safe_filename)

        # 3. Resolve data source
        if data_source_id is not None:
            source = await self.get_data_source(org_id, project_id, data_source_id, user_id)
        else:
            source = await self.get_or_create_default_file_source(project_id)

        # 4. Resolve or create Dataset container
        clean_name = name.strip() if name and name.strip() else Path(safe_filename).stem
        stmt = select(Dataset).where(
            Dataset.project_id == project_id,
            Dataset.name == clean_name,
        )
        dataset = (await self.session.execute(stmt)).scalar_one_or_none()

        if dataset is None:
            dataset = Dataset(
                id=uuid.uuid4(),
                project_id=project_id,
                data_source_id=source.id,
                name=clean_name,
                description=description.strip() if description else None,
                status=DatasetStatus.PENDING.value,
            )
            self.session.add(dataset)
            await self.session.commit()
            await self.session.refresh(dataset)

        # 5. Determine next version number
        v_stmt = select(func.coalesce(func.max(DatasetVersion.version_number), 0)).where(
            DatasetVersion.dataset_id == dataset.id
        )
        max_ver = (await self.session.execute(v_stmt)).scalar() or 0
        version_number = max_ver + 1

        # 6. Prepare isolated target storage directory
        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()
        target_dir = storage_root / str(org_id) / str(project_id) / str(dataset.id) / f"v{version_number}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file_path = target_dir / safe_filename

        # 7. Stream file to disk while calculating SHA-256 and enforcing byte limits
        sha256 = hashlib.sha256()
        total_bytes = 0
        max_bytes = self.settings.MAX_UPLOAD_SIZE_BYTES

        try:
            with open(target_file_path, "wb") as out_f:
                while True:
                    chunk = await file.read(65536)  # 64 KB chunks
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        out_f.close()
                        if target_file_path.exists():
                            target_file_path.unlink()
                        raise FileSizeLimitExceededException(total_bytes, max_bytes)
                    sha256.update(chunk)
                    out_f.write(chunk)
        except Exception:
            if target_file_path.exists():
                target_file_path.unlink()
            raise

        if total_bytes == 0:
            if target_file_path.exists():
                target_file_path.unlink()
            raise EmptyDatasetException("Uploaded dataset file is empty (0 bytes).")

        checksum = sha256.hexdigest()
        relative_storage_path = str(target_file_path.relative_to(storage_root)).replace("\\", "/")

        # 8. Create immutable DatasetVersion record
        version = DatasetVersion(
            id=uuid.uuid4(),
            project_id=project_id,
            dataset_id=dataset.id,
            version_number=version_number,
            file_format=detected_format,
            file_size_bytes=total_bytes,
            checksum_hash=checksum,
            storage_path=relative_storage_path,
            status=DatasetVersionStatus.PROFILING.value,
        )
        self.session.add(version)
        await self.session.commit()
        await self.session.refresh(version)

        # 9. Execute deterministic parsing and profiling
        try:
            parser = DatasetParser(target_file_path, detected_format)
            headers, stream = parser.parse_headers_and_stream()
            schemas, summary = DatasetProfiler.profile_stream(headers, stream)

            version.record_count = summary.total_rows
            version.column_count = summary.total_columns
            version.schema_metadata_json = [s.model_dump() for s in schemas]
            version.profiling_summary_json = summary.model_dump(mode="json")
            version.status = DatasetVersionStatus.READY.value

            dataset.status = DatasetStatus.PROFILED.value
            await self.session.commit()
        except Exception as e:
            version.status = DatasetVersionStatus.FAILED.value
            version.error_message = str(e)[:2000]
            dataset.status = DatasetStatus.ERROR.value
            await self.session.commit()
            raise

        # Return full dataset with eagerly loaded versions
        return await self.get_dataset(org_id, project_id, dataset.id, user_id)

    async def list_datasets(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Dataset]:
        """List all datasets in a project with their version snapshots."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(org_id, project_id, user_id)
        stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .options(selectinload(Dataset.versions))
            .order_by(Dataset.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_organization_datasets(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[Dataset]:
        """List all datasets across all accessible projects in the active organization."""
        await self.tenancy_service.verify_membership(org_id, user_id)
        # Fetch projects belonging strictly to this organization
        p_stmt = select(Project.id).where(Project.organization_id == org_id)
        project_ids = list((await self.session.execute(p_stmt)).scalars().all())

        if not project_ids:
            return []

        stmt = (
            select(Dataset)
            .where(Dataset.project_id.in_(project_ids))
            .options(selectinload(Dataset.versions))
            .order_by(Dataset.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_dataset(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Dataset:
        """Fetch dataset details and verify same-project isolation."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(org_id, project_id, user_id)
        stmt = (
            select(Dataset)
            .where(
                Dataset.project_id == project_id,
                Dataset.id == dataset_id,
            )
            .options(selectinload(Dataset.versions))
        )
        dataset = (await self.session.execute(stmt)).scalar_one_or_none()
        if dataset is None:
            raise DatasetNotFoundException(dataset_id)
        return dataset

    async def get_dataset_version(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id_or_number: Any,
        user_id: uuid.UUID,
    ) -> DatasetVersion:
        """Retrieve a specific dataset version snapshot."""
        await self.get_dataset(org_id, project_id, dataset_id, user_id)

        try:
            ver_uuid = uuid.UUID(str(version_id_or_number))
            stmt = select(DatasetVersion).where(
                DatasetVersion.project_id == project_id,
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.id == ver_uuid,
            )
        except ValueError:
            ver_num = int(version_id_or_number)
            stmt = select(DatasetVersion).where(
                DatasetVersion.project_id == project_id,
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.version_number == ver_num,
            )

        version = (await self.session.execute(stmt)).scalar_one_or_none()
        if version is None:
            raise DatasetVersionNotFoundException(dataset_id, version_id_or_number)
        return version

    async def get_dataset_preview(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID | None,
        user_id: uuid.UUID,
        limit: int = 20,
    ) -> DatasetPreviewResponse:
        """Retrieve preview rows without reading the whole file into memory."""
        dataset = await self.get_dataset(org_id, project_id, dataset_id, user_id)
        if not dataset.versions:
            raise DatasetVersionNotFoundException(dataset_id, "latest")

        target_version = dataset.versions[0]
        if version_id is not None:
            target_version = await self.get_dataset_version(org_id, project_id, dataset_id, version_id, user_id)

        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()
        file_path = (storage_root / target_version.storage_path).resolve()

        # Path traversal guard
        if not str(file_path).startswith(str(storage_root)):
            raise DatasetNotFoundException(dataset_id)

        parser = DatasetParser(file_path, target_version.file_format)
        columns, rows = parser.get_preview(limit=min(limit, 100))

        return DatasetPreviewResponse(
            dataset_id=dataset.id,
            version_number=target_version.version_number,
            columns=columns,
            rows=rows,
            total_preview_rows=len(rows),
        )

    async def delete_dataset(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Delete dataset, cascading version records, and physical storage files."""
        dataset = await self.get_dataset(org_id, project_id, dataset_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.PROJECT_LEAD]
        )

        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()
        dataset_storage_dir = storage_root / str(org_id) / str(project_id) / str(dataset.id)

        if dataset_storage_dir.exists() and str(dataset_storage_dir).startswith(str(storage_root)):
            shutil.rmtree(dataset_storage_dir, ignore_errors=True)

        await self.session.delete(dataset)
        await self.session.commit()

    @staticmethod
    def map_to_response(dataset: Dataset) -> DatasetResponse:
        """Map ORM Dataset and latest version to public Pydantic response."""
        latest_v = dataset.versions[0] if dataset.versions else None
        v_resp = DatasetVersionResponse.from_orm_model(latest_v) if latest_v is not None else None

        return DatasetResponse(
            id=dataset.id,
            project_id=dataset.project_id,
            data_source_id=dataset.data_source_id,
            name=dataset.name,
            description=dataset.description,
            status=dataset.status,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
            latest_version=v_resp,
            version_count=len(dataset.versions),
        )
