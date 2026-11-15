"""Process Intelligence & Event Mining service (Phase 6)."""

import logging
import statistics
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.core.config import Settings, get_settings
from corbel.domains.data_intelligence.models import Dataset
from corbel.domains.data_intelligence.parser import DatasetParser
from corbel.domains.process_intelligence.exceptions import (
    ProcessCaseNotFoundException,
    ProcessNotFoundException,
    ProcessReconstructionException,
    ProcessValidationException,
)
from corbel.domains.process_intelligence.models import (
    Process,
    ProcessCase,
    ProcessCaseStatus,
    ProcessEvent,
    ProcessEventDatasetVersion,
    ProcessEventType,
)
from corbel.domains.process_intelligence.schemas import (
    DFGEdge,
    DFGNode,
    DFGResponse,
    ProcessCaseDetailResponse,
    ProcessCasesListResponse,
    ProcessCaseSummary,
    ProcessCreate,
    ProcessEventBatchIngestRequest,
    ProcessEventIngestItem,
    ProcessEventResponse,
    ProcessOverviewResponse,
    ProcessReconstructRequest,
    ProcessReconstructResponse,
    ProcessResponse,
    ProcessUpdate,
    ProcessVariantItem,
    ProcessVariantsResponse,
)
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.tenancy.service import TenancyService

logger = logging.getLogger(__name__)


def parse_timestamp(val: Any) -> datetime:
    """Parse various timestamp representations into a timezone-aware UTC datetime."""
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=UTC)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=UTC)
    if not isinstance(val, str) or not val.strip():
        raise ProcessValidationException(f"Invalid timestamp value: {val}")

    s = val.strip()
    # Try ISO
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    except Exception:
        pass

    # Try common formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%m/%d/%Y",
        "%d-%m-%Y",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=UTC)
        except Exception:
            continue

    raise ProcessValidationException(f"Unable to parse timestamp '{val}'. Expected ISO or YYYY-MM-DD format.")


class ProcessService:
    """Service governing process definitions, event ingestion, and process mining calculations."""

    def __init__(
        self,
        session: AsyncSession,
        tenancy_service: TenancyService,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.tenancy_service = tenancy_service
        self.settings = settings or get_settings()

    # ==========================================================================
    # Process Definition CRUD
    # ==========================================================================

    async def create_process(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: ProcessCreate,
    ) -> ProcessResponse:
        """Create a new operational process definition within the project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        # Check name uniqueness
        existing_stmt = select(Process).where(
            Process.project_id == project_id,
            Process.name == req.name.strip(),
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise ProcessValidationException(f"Process with name '{req.name.strip()}' already exists in this project.")

        process = Process(
            id=uuid.uuid4(),
            project_id=project_id,
            name=req.name.strip(),
            description=req.description.strip() if req.description else None,
            target_duration_seconds=req.target_duration_seconds,
            is_active=req.is_active,
        )
        self.session.add(process)
        await self.session.commit()
        await self.session.refresh(process)

        return ProcessResponse(
            id=process.id,
            project_id=process.project_id,
            name=process.name,
            description=process.description,
            target_duration_seconds=process.target_duration_seconds,
            is_active=process.is_active,
            created_at=process.created_at,
            updated_at=process.updated_at,
            case_count=0,
            event_count=0,
        )

    async def get_process(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
    ) -> ProcessResponse:
        """Retrieve a process definition by ID with case and event counts."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)
        case_count, event_count = await self._get_process_counts(project_id, process_id)

        return ProcessResponse(
            id=process.id,
            project_id=process.project_id,
            name=process.name,
            description=process.description,
            target_duration_seconds=process.target_duration_seconds,
            is_active=process.is_active,
            created_at=process.created_at,
            updated_at=process.updated_at,
            case_count=case_count,
            event_count=event_count,
        )

    async def list_processes(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[ProcessResponse]:
        """List all processes scoped to the project."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        stmt = select(Process).where(Process.project_id == project_id).order_by(Process.created_at.desc())
        processes = (await self.session.execute(stmt)).scalars().all()

        results = []
        for p in processes:
            case_count, event_count = await self._get_process_counts(project_id, p.id)
            results.append(
                ProcessResponse(
                    id=p.id,
                    project_id=p.project_id,
                    name=p.name,
                    description=p.description,
                    target_duration_seconds=p.target_duration_seconds,
                    is_active=p.is_active,
                    created_at=p.created_at,
                    updated_at=p.updated_at,
                    case_count=case_count,
                    event_count=event_count,
                )
            )
        return results

    async def update_process(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
        req: ProcessUpdate,
    ) -> ProcessResponse:
        """Update properties of an existing process."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)

        if req.name is not None and req.name.strip() != process.name:
            dup_stmt = select(Process).where(
                Process.project_id == project_id,
                Process.name == req.name.strip(),
                Process.id != process_id,
            )
            if (await self.session.execute(dup_stmt)).scalar_one_or_none() is not None:
                raise ProcessValidationException(f"Process with name '{req.name.strip()}' already exists.")
            process.name = req.name.strip()

        if req.description is not None:
            process.description = req.description.strip() if req.description else None
        if req.target_duration_seconds is not None:
            process.target_duration_seconds = req.target_duration_seconds
        if req.is_active is not None:
            process.is_active = req.is_active

        await self.session.commit()
        await self.session.refresh(process)

        case_count, event_count = await self._get_process_counts(project_id, process.id)
        return ProcessResponse(
            id=process.id,
            project_id=process.project_id,
            name=process.name,
            description=process.description,
            target_duration_seconds=process.target_duration_seconds,
            is_active=process.is_active,
            created_at=process.created_at,
            updated_at=process.updated_at,
            case_count=case_count,
            event_count=event_count,
        )

    async def delete_process(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
    ) -> None:
        """Delete a process definition and cascade deletion to all its cases and events."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)
        await self.session.delete(process)
        await self.session.commit()

    # ==========================================================================
    # Event Log Ingestion & Assembly
    # ==========================================================================

    async def ingest_events(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
        req: ProcessEventBatchIngestRequest,
    ) -> ProcessReconstructResponse:
        """Ingest a batch of activity events and deterministically assemble cases and variants."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)

        if not req.events:
            raise ProcessValidationException("Event batch cannot be empty.")

        # Group events by case_identifier
        events_by_case: dict[str, list[ProcessEventIngestItem]] = {}
        for item in req.events:
            c_id = item.case_identifier.strip()
            if not c_id:
                raise ProcessValidationException("Case identifier cannot be empty.")
            act = item.activity_name.strip()
            if not act:
                raise ProcessValidationException("Activity name cannot be empty.")

            # Validate timestamp
            parse_timestamp(item.timestamp)
            events_by_case.setdefault(c_id, []).append(item)

        cases_reconstructed = 0
        events_reconstructed = 0

        # Persist each case
        for case_id_str, raw_events in events_by_case.items():
            # Sort events chronologically, breaking ties by activity_name
            sorted_events = sorted(
                raw_events,
                key=lambda e: (parse_timestamp(e.timestamp), e.activity_name),
            )

            started_at = parse_timestamp(sorted_events[0].timestamp)
            ended_at = parse_timestamp(sorted_events[-1].timestamp)
            total_duration_sec = max(0.0, (ended_at - started_at).total_seconds())
            variant_key = " -> ".join([e.activity_name.strip() for e in sorted_events])

            # Check if case exists in process
            case_stmt = select(ProcessCase).where(
                ProcessCase.project_id == project_id,
                ProcessCase.process_id == process_id,
                ProcessCase.case_identifier == case_id_str,
            )
            case_obj = (await self.session.execute(case_stmt)).scalar_one_or_none()

            if case_obj is None:
                case_obj = ProcessCase(
                    id=uuid.uuid4(),
                    process_id=process_id,
                    project_id=project_id,
                    case_identifier=case_id_str,
                    variant_key=variant_key,
                    status=ProcessCaseStatus.COMPLETED.value,
                    started_at=started_at,
                    ended_at=ended_at,
                    total_duration_seconds=total_duration_sec,
                    event_count=len(sorted_events),
                )
                self.session.add(case_obj)
                await self.session.flush()
            else:
                # Clear previous events for overwrite/sync
                await self.session.execute(
                    delete(ProcessEvent).where(ProcessEvent.process_case_id == case_obj.id)
                )
                case_obj.variant_key = variant_key
                case_obj.started_at = started_at
                case_obj.ended_at = ended_at
                case_obj.total_duration_seconds = total_duration_sec
                case_obj.event_count = len(sorted_events)

            # Insert events
            for e in sorted_events:
                ev = ProcessEvent(
                    id=uuid.uuid4(),
                    process_case_id=case_obj.id,
                    project_id=project_id,
                    activity_name=e.activity_name.strip(),
                    timestamp=parse_timestamp(e.timestamp),
                    event_type=e.event_type.strip() if e.event_type else ProcessEventType.COMPLETE.value,
                    resource=e.resource.strip() if e.resource else None,
                    source_system=e.source_system.strip() if e.source_system else None,
                    source_record_id=e.source_record_id.strip() if e.source_record_id else None,
                    attributes_json=e.attributes,
                )
                self.session.add(ev)
                events_reconstructed += 1

            cases_reconstructed += 1

        await self.session.commit()

        # Count distinct variants
        variants_stmt = select(func.count(func.distinct(ProcessCase.variant_key))).where(
            ProcessCase.process_id == process_id,
            ProcessCase.project_id == project_id,
        )
        variants_count = (await self.session.execute(variants_stmt)).scalar() or 0

        return ProcessReconstructResponse(
            process_id=process.id,
            cases_reconstructed=cases_reconstructed,
            events_reconstructed=events_reconstructed,
            variants_count=variants_count,
            message=f"Successfully ingested {events_reconstructed} events across {cases_reconstructed} cases.",
        )

    # ==========================================================================
    # Event Log Reconstruction from Datasets / P2P Tables
    # ==========================================================================

    async def reconstruct_process(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
        req: ProcessReconstructRequest,
    ) -> ProcessReconstructResponse:
        """Reconstruct process cases and events from tabular project datasets or confirmed P2P ontology entities."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)

        if req.mode.upper() == "DATASET_MAPPING":
            return await self._reconstruct_from_dataset_mapping(project_id, process, req)
        elif req.mode.upper() == "P2P_ONTOLOGY":
            return await self._reconstruct_from_p2p_ontology(project_id, process)
        else:
            raise ProcessValidationException(f"Unsupported reconstruction mode '{req.mode}'. Use 'P2P_ONTOLOGY' or 'DATASET_MAPPING'.")

    async def _reconstruct_from_dataset_mapping(
        self,
        project_id: uuid.UUID,
        process: Process,
        req: ProcessReconstructRequest,
    ) -> ProcessReconstructResponse:
        """Reconstruct event log from a specified single event dataset with mapped columns."""
        if not req.dataset_id:
            raise ProcessValidationException("dataset_id is required for DATASET_MAPPING mode.")
        if not req.case_id_column or not req.activity_column or not req.timestamp_column:
            raise ProcessValidationException("case_id_column, activity_column, and timestamp_column are required.")

        # Find dataset and latest version
        ds_stmt = (
            select(Dataset)
            .where(Dataset.id == req.dataset_id, Dataset.project_id == project_id)
            .options(selectinload(Dataset.versions))
        )
        dataset = (await self.session.execute(ds_stmt)).scalar_one_or_none()
        if dataset is None or not dataset.versions:
            raise ProcessReconstructionException(f"Dataset {req.dataset_id} not found or has no uploaded versions.")

        latest_version = sorted(dataset.versions, key=lambda v: v.version_number, reverse=True)[0]
        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()
        file_path = (storage_root / latest_version.storage_path).resolve()

        if not file_path.exists():
            raise ProcessReconstructionException(f"Dataset file for {dataset.name} is missing from disk storage.")

        parser = DatasetParser(file_path, latest_version.file_format)
        headers, row_gen = parser.parse_headers_and_stream()
        header_map = {h.lower().strip(): idx for idx, h in enumerate(headers)}

        c_idx = header_map.get(req.case_id_column.lower().strip())
        a_idx = header_map.get(req.activity_column.lower().strip())
        t_idx = header_map.get(req.timestamp_column.lower().strip())
        r_idx = header_map.get(req.resource_column.lower().strip()) if req.resource_column else None

        if c_idx is None or a_idx is None or t_idx is None:
            raise ProcessValidationException(
                f"Specified columns not found in dataset headers. Available: {headers}"
            )

        events: list[ProcessEventIngestItem] = []
        for row in row_gen:
            if len(row) <= max(c_idx, a_idx, t_idx):
                continue
            case_id = str(row[c_idx]).strip()
            activity = str(row[a_idx]).strip()
            raw_ts = row[t_idx]

            if not case_id or not activity or not raw_ts:
                continue

            try:
                ts = parse_timestamp(raw_ts)
            except Exception:
                continue

            resource = str(row[r_idx]).strip() if r_idx is not None and r_idx < len(row) and row[r_idx] else None
            events.append(
                ProcessEventIngestItem(
                    case_identifier=case_id,
                    activity_name=activity,
                    timestamp=ts,
                    resource=resource,
                )
            )

        if not events:
            raise ProcessReconstructionException("Zero valid events could be extracted from dataset.")

        # Batch ingest using existing assembly logic
        batch_req = ProcessEventBatchIngestRequest(events=events)
        return await self.ingest_events(
            process.project_id, process.project_id, process.project_id, process.id, batch_req
        )

    async def _reconstruct_from_p2p_ontology(
        self,
        project_id: uuid.UUID,
        process: Process,
    ) -> ProcessReconstructResponse:
        """Reconstruct end-to-end P2P event log across purchase_orders, goods_receipts, and invoices."""
        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()

        # Query all datasets for project
        ds_stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .options(selectinload(Dataset.versions))
        )
        datasets = (await self.session.execute(ds_stmt)).scalars().all()
        if not datasets:
            raise ProcessReconstructionException("No datasets found in project to reconstruct P2P process events.")

        # Match datasets by name
        po_ds = next((d for d in datasets if "purchase" in d.name.lower() or "po" in d.name.lower()), None)
        gr_ds = next((d for d in datasets if "receipt" in d.name.lower() or "goods" in d.name.lower() or "delivery" in d.name.lower()), None)
        inv_ds = next((d for d in datasets if "invoice" in d.name.lower()), None)

        if po_ds is None and inv_ds is None:
            raise ProcessReconstructionException(
                "Could not find Purchase Order or Invoice datasets in project. Required datasets: 'purchase_orders', 'goods_receipts', 'invoices'."
            )

        def _col(h_map: dict[str, int], *names: str) -> int | None:
            for n in names:
                k = n.lower().strip()
                if k in h_map:
                    return h_map[k]
            return None

        events_by_case: dict[str, list[dict[str, Any]]] = {}

        # 1. Extract PO Created milestones
        if po_ds and po_ds.versions:
            po_ver = sorted(po_ds.versions, key=lambda v: v.version_number, reverse=True)[0]
            po_file = (storage_root / po_ver.storage_path).resolve()
            if po_file.exists():
                parser = DatasetParser(po_file, po_ver.file_format)
                headers, row_gen = parser.parse_headers_and_stream()
                h_map = {h.lower().strip(): idx for idx, h in enumerate(headers)}
                po_col = _col(h_map, "po_id", "po_number", "order_id")
                date_col = _col(h_map, "order_date", "date", "created_at")
                sup_col = _col(h_map, "supplier_id", "vendor_id")
                amt_col = _col(h_map, "total_amount", "amount")

                if po_col is not None and date_col is not None:
                    for row in row_gen:
                        if len(row) <= max(po_col, date_col):
                            continue
                        po_id = str(row[po_col]).strip()
                        raw_date = row[date_col]
                        if not po_id or not raw_date:
                            continue
                        try:
                            ts = parse_timestamp(raw_date)
                        except Exception:
                            continue

                        supplier = str(row[sup_col]).strip() if sup_col is not None and sup_col < len(row) else None
                        amt = row[amt_col] if amt_col is not None and amt_col < len(row) else None

                        events_by_case.setdefault(po_id, []).append({
                            "activity": "PO Created",
                            "timestamp": ts,
                            "resource": supplier,
                            "source_system": "ERP",
                            "source_record_id": po_id,
                            "attributes": {"total_amount": amt, "supplier_id": supplier},
                            "version_id": po_ver.id,
                            "role": "PURCHASE_ORDER",
                        })

        # 2. Extract Goods Received milestones
        if gr_ds and gr_ds.versions:
            gr_ver = sorted(gr_ds.versions, key=lambda v: v.version_number, reverse=True)[0]
            gr_file = (storage_root / gr_ver.storage_path).resolve()
            if gr_file.exists():
                parser = DatasetParser(gr_file, gr_ver.file_format)
                headers, row_gen = parser.parse_headers_and_stream()
                h_map = {h.lower().strip(): idx for idx, h in enumerate(headers)}
                po_col = _col(h_map, "po_id", "po_number", "order_id")
                date_col = _col(h_map, "delivery_date", "receipt_date", "date")
                status_col = _col(h_map, "status")
                qty_col = _col(h_map, "quantity_received", "quantity")
                rec_col = _col(h_map, "receipt_id")

                if po_col is not None and date_col is not None:
                    for row in row_gen:
                        if len(row) <= max(po_col, date_col):
                            continue
                        po_id = str(row[po_col]).strip()
                        raw_date = row[date_col]
                        if not po_id or not raw_date:
                            continue
                        try:
                            ts = parse_timestamp(raw_date)
                        except Exception:
                            continue

                        status_val = str(row[status_col]).strip() if status_col is not None and status_col < len(row) else None
                        rec_id = str(row[rec_col]).strip() if rec_col is not None and rec_col < len(row) else None
                        qty = row[qty_col] if qty_col is not None and qty_col < len(row) else None

                        events_by_case.setdefault(po_id, []).append({
                            "activity": "Goods Received",
                            "timestamp": ts,
                            "resource": "Warehouse",
                            "source_system": "WMS",
                            "source_record_id": rec_id or po_id,
                            "attributes": {"quantity_received": qty, "receipt_id": rec_id, "status": status_val},
                            "version_id": gr_ver.id,
                            "role": "GOODS_RECEIPT",
                        })

        # 3. Extract Invoice Received milestones
        if inv_ds and inv_ds.versions:
            inv_ver = sorted(inv_ds.versions, key=lambda v: v.version_number, reverse=True)[0]
            inv_file = (storage_root / inv_ver.storage_path).resolve()
            if inv_file.exists():
                parser = DatasetParser(inv_file, inv_ver.file_format)
                headers, row_gen = parser.parse_headers_and_stream()
                h_map = {h.lower().strip(): idx for idx, h in enumerate(headers)}
                po_col = _col(h_map, "po_id", "po_number", "order_id")
                inv_col = _col(h_map, "invoice_id")
                date_col = _col(h_map, "invoice_date", "date", "created_at")
                amt_col = _col(h_map, "invoice_amount", "amount")
                sup_col = _col(h_map, "supplier_id", "vendor_id")
                status_col = _col(h_map, "status")

                if (po_col is not None or inv_col is not None) and date_col is not None:
                    for row in row_gen:
                        if len(row) <= max(filter(None, [po_col, inv_col, date_col])):
                            continue
                        inv_po_id = str(row[po_col]).strip() if po_col is not None and po_col < len(row) else None
                        inv_id = str(row[inv_col]).strip() if inv_col is not None and inv_col < len(row) else None
                        case_key = inv_po_id or inv_id
                        raw_date = row[date_col]
                        if not case_key or not raw_date:
                            continue
                        case_key_str = str(case_key)
                        try:
                            ts = parse_timestamp(raw_date)
                        except Exception:
                            continue

                        amt = row[amt_col] if amt_col is not None and amt_col < len(row) else None
                        sup = str(row[sup_col]).strip() if sup_col is not None and sup_col < len(row) else None
                        status_val = str(row[status_col]).strip() if status_col is not None and status_col < len(row) else None

                        events_by_case.setdefault(case_key_str, []).append({
                            "activity": "Invoice Received",
                            "timestamp": ts,
                            "resource": sup or "Accounts Payable",
                            "source_system": "AP_FINANCE",
                            "source_record_id": inv_id,
                            "attributes": {"invoice_id": inv_id, "invoice_amount": amt, "status": status_val},
                            "version_id": inv_ver.id,
                            "role": "INVOICE",
                        })

                        # If status is PAID, synthesize a Payment Cleared milestone slightly after invoice date
                        if status_val and status_val.upper() == "PAID":
                            pay_ts = datetime.fromtimestamp(ts.timestamp() + 86400 * 5, tz=UTC)
                            events_by_case.setdefault(case_key_str, []).append({
                                "activity": "Payment Cleared",
                                "timestamp": pay_ts,
                                "resource": "Treasury",
                                "source_system": "AP_FINANCE",
                                "source_record_id": inv_id,
                                "attributes": {"invoice_id": inv_id, "amount_paid": amt},
                                "version_id": inv_ver.id,
                                "role": "PAYMENT",
                            })

        if not events_by_case:
            raise ProcessReconstructionException("No valid P2P events could be correlated from the project datasets.")

        # Clear existing cases and events for this process to ensure clean reconstruction
        await self.session.execute(
            delete(ProcessCase).where(ProcessCase.process_id == process.id)
        )

        cases_reconstructed = 0
        events_reconstructed = 0

        for case_id_str, raw_list in events_by_case.items():
            sorted_events = sorted(
                raw_list,
                key=lambda e: (e["timestamp"], e["activity"]),
            )

            started_at = sorted_events[0]["timestamp"]
            ended_at = sorted_events[-1]["timestamp"]
            total_duration_sec = max(0.0, (ended_at - started_at).total_seconds())
            variant_key = " -> ".join([e["activity"] for e in sorted_events])

            case_obj = ProcessCase(
                id=uuid.uuid4(),
                process_id=process.id,
                project_id=project_id,
                case_identifier=case_id_str,
                variant_key=variant_key,
                status=ProcessCaseStatus.COMPLETED.value,
                started_at=started_at,
                ended_at=ended_at,
                total_duration_seconds=total_duration_sec,
                event_count=len(sorted_events),
            )
            self.session.add(case_obj)
            await self.session.flush()

            for e in sorted_events:
                ev = ProcessEvent(
                    id=uuid.uuid4(),
                    process_case_id=case_obj.id,
                    project_id=project_id,
                    dataset_version_id=e.get("version_id"),
                    activity_name=e["activity"],
                    timestamp=e["timestamp"],
                    event_type=ProcessEventType.COMPLETE.value,
                    resource=e.get("resource"),
                    source_system=e.get("source_system"),
                    source_record_id=e.get("source_record_id"),
                    attributes_json=e.get("attributes"),
                )
                self.session.add(ev)
                await self.session.flush()

                if e.get("version_id"):
                    assoc = ProcessEventDatasetVersion(
                        id=uuid.uuid4(),
                        project_id=project_id,
                        process_event_id=ev.id,
                        dataset_version_id=e["version_id"],
                        provenance_role=e.get("role"),
                        transformation_reference="P2P_ONTOLOGY_RECONSTRUCTION",
                    )
                    self.session.add(assoc)

                events_reconstructed += 1

            cases_reconstructed += 1

        await self.session.commit()

        variants_stmt = select(func.count(func.distinct(ProcessCase.variant_key))).where(
            ProcessCase.process_id == process.id,
            ProcessCase.project_id == project_id,
        )
        variants_count = (await self.session.execute(variants_stmt)).scalar() or 0

        return ProcessReconstructResponse(
            process_id=process.id,
            cases_reconstructed=cases_reconstructed,
            events_reconstructed=events_reconstructed,
            variants_count=variants_count,
            message=f"Reconstructed {cases_reconstructed} P2P cases with {events_reconstructed} events across {variants_count} distinct variants.",
        )

    # ==========================================================================
    # Process Performance, DFG & Variant Analytics
    # ==========================================================================

    async def get_process_overview(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
    ) -> ProcessOverviewResponse:
        """Calculate executive metrics, cycle times, SLA breach rates, and identify the primary bottleneck."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        process = await self._get_process_or_404(project_id, process_id)

        # Retrieve all cases for process
        cases_stmt = select(ProcessCase).where(
            ProcessCase.process_id == process_id,
            ProcessCase.project_id == project_id,
        )
        cases = (await self.session.execute(cases_stmt)).scalars().all()

        if not cases:
            return ProcessOverviewResponse(
                process_id=process.id,
                name=process.name,
                target_duration_seconds=process.target_duration_seconds,
                total_cases=0,
                total_events=0,
                distinct_activities_count=0,
                distinct_variants_count=0,
                avg_cycle_time_seconds=0.0,
                median_cycle_time_seconds=0.0,
                min_cycle_time_seconds=0.0,
                max_cycle_time_seconds=0.0,
                sla_breach_count=0,
                sla_compliance_rate=100.0,
                rework_case_count=0,
                rework_rate=0.0,
                primary_bottleneck=None,
            )

        total_cases = len(cases)
        total_events = sum(c.event_count for c in cases)
        durations = [c.total_duration_seconds for c in cases]
        avg_cycle = statistics.mean(durations) if durations else 0.0
        median_cycle = statistics.median(durations) if durations else 0.0
        min_cycle = min(durations) if durations else 0.0
        max_cycle = max(durations) if durations else 0.0

        # SLA compliance
        target = process.target_duration_seconds
        sla_breach_count = sum(1 for c in cases if target is not None and c.total_duration_seconds > target)
        sla_compliance_rate = (
            round(((total_cases - sla_breach_count) / total_cases) * 100.0, 2)
            if total_cases > 0
            else 100.0
        )

        # Unique variants
        unique_variants = {c.variant_key for c in cases}

        # Calculate DFG to identify distinct activities and primary bottleneck
        dfg = await self.get_directly_follows_graph(org_id, project_id, user_id, process_id)
        distinct_activities = len(dfg.nodes)

        # Primary bottleneck is the transition with highest average duration
        primary_bottleneck = None
        if dfg.bottleneck_edge:
            primary_bottleneck = f"{dfg.bottleneck_edge.source} -> {dfg.bottleneck_edge.target} ({round(dfg.bottleneck_edge.avg_duration_seconds / 3600.0, 1)} hrs avg)"

        # Rework detection: check cases where any activity is repeated
        rework_case_count = 0
        for c in cases:
            acts = c.variant_key.split(" -> ")
            if len(acts) > len(set(acts)):
                rework_case_count += 1
        rework_rate = round((rework_case_count / total_cases) * 100.0, 2) if total_cases > 0 else 0.0

        return ProcessOverviewResponse(
            process_id=process.id,
            name=process.name,
            target_duration_seconds=process.target_duration_seconds,
            total_cases=total_cases,
            total_events=total_events,
            distinct_activities_count=distinct_activities,
            distinct_variants_count=len(unique_variants),
            avg_cycle_time_seconds=round(avg_cycle, 2),
            median_cycle_time_seconds=round(median_cycle, 2),
            min_cycle_time_seconds=round(min_cycle, 2),
            max_cycle_time_seconds=round(max_cycle, 2),
            sla_breach_count=sla_breach_count,
            sla_compliance_rate=sla_compliance_rate,
            rework_case_count=rework_case_count,
            rework_rate=rework_rate,
            primary_bottleneck=primary_bottleneck,
        )

    async def get_process_variants(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
    ) -> ProcessVariantsResponse:
        """Discover and rank all unique process execution variants."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        cases_stmt = select(ProcessCase).where(
            ProcessCase.process_id == process_id,
            ProcessCase.project_id == project_id,
        )
        cases = (await self.session.execute(cases_stmt)).scalars().all()
        if not cases:
            return ProcessVariantsResponse(process_id=process_id, variants=[], total_variants=0)

        # Group cases by variant_key
        variant_groups: dict[str, list[ProcessCase]] = {}
        for c in cases:
            variant_groups.setdefault(c.variant_key, []).append(c)

        total_cases = len(cases)
        # Sort variants by case count descending
        sorted_keys = sorted(
            variant_groups.keys(),
            key=lambda k: len(variant_groups[k]),
            reverse=True,
        )

        happy_path_key = sorted_keys[0] if sorted_keys else None
        items: list[ProcessVariantItem] = []

        for key in sorted_keys:
            group = variant_groups[key]
            durations = [c.total_duration_seconds for c in group]
            count = len(group)
            pct = round((count / total_cases) * 100.0, 2)

            items.append(
                ProcessVariantItem(
                    variant_key=key,
                    activities=key.split(" -> "),
                    case_count=count,
                    frequency_percentage=pct,
                    avg_duration_seconds=round(statistics.mean(durations), 2),
                    median_duration_seconds=round(statistics.median(durations), 2),
                    min_duration_seconds=round(min(durations), 2),
                    max_duration_seconds=round(max(durations), 2),
                    is_happy_path=(key == happy_path_key),
                )
            )

        return ProcessVariantsResponse(
            process_id=process_id,
            variants=items,
            total_variants=len(items),
        )

    async def get_directly_follows_graph(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
    ) -> DFGResponse:
        """Construct the Directly-Follows Graph (DFG) with transition frequencies, durations, and bottlenecks."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        cases_stmt = (
            select(ProcessCase)
            .where(
                ProcessCase.process_id == process_id,
                ProcessCase.project_id == project_id,
            )
            .options(selectinload(ProcessCase.events))
        )
        cases = (await self.session.execute(cases_stmt)).scalars().all()
        if not cases:
            return DFGResponse(process_id=process_id, nodes=[], edges=[], bottleneck_edge=None)

        # Track node stats: name -> {count, case_ids, start_offsets, is_start, is_end}
        node_stats: dict[str, dict[str, Any]] = {}
        # Track edge stats: (src, tgt) -> {count, case_ids, durations}
        edge_stats: dict[tuple[str, str], dict[str, Any]] = {}

        for c in cases:
            events = sorted(c.events, key=lambda e: (e.timestamp, e.activity_name))
            if not events:
                continue

            case_start_ts = events[0].timestamp.timestamp()

            for idx, e in enumerate(events):
                act = e.activity_name
                offset = max(0.0, e.timestamp.timestamp() - case_start_ts)

                if act not in node_stats:
                    node_stats[act] = {
                        "frequency": 0,
                        "cases": set(),
                        "offsets": [],
                        "is_start": False,
                        "is_end": False,
                    }
                node_stats[act]["frequency"] += 1
                node_stats[act]["cases"].add(c.id)
                node_stats[act]["offsets"].append(offset)

                if idx == 0:
                    node_stats[act]["is_start"] = True
                if idx == len(events) - 1:
                    node_stats[act]["is_end"] = True

                # Transition to next activity
                if idx < len(events) - 1:
                    next_e = events[idx + 1]
                    next_act = next_e.activity_name
                    trans_dur = max(0.0, (next_e.timestamp - e.timestamp).total_seconds())

                    pair = (act, next_act)
                    if pair not in edge_stats:
                        edge_stats[pair] = {
                            "count": 0,
                            "cases": set(),
                            "durations": [],
                        }
                    edge_stats[pair]["count"] += 1
                    edge_stats[pair]["cases"].add(c.id)
                    edge_stats[pair]["durations"].append(trans_dur)

        # Build DFG Nodes
        nodes: list[DFGNode] = []
        for name, data in node_stats.items():
            avg_offset = statistics.mean(data["offsets"]) if data["offsets"] else 0.0
            nodes.append(
                DFGNode(
                    name=name,
                    frequency=data["frequency"],
                    case_frequency=len(data["cases"]),
                    avg_duration_from_start_seconds=round(avg_offset, 2),
                    is_start_activity=data["is_start"],
                    is_end_activity=data["is_end"],
                )
            )

        # Build DFG Edges
        edges: list[DFGEdge] = []
        bottleneck_edge: DFGEdge | None = None
        max_avg_duration = -1.0

        for (src, tgt), data in edge_stats.items():
            durs = data["durations"]
            avg_dur = statistics.mean(durs) if durs else 0.0
            med_dur = statistics.median(durs) if durs else 0.0
            min_dur = min(durs) if durs else 0.0
            max_dur = max(durs) if durs else 0.0
            is_rework = (src == tgt)

            edge = DFGEdge(
                source=src,
                target=tgt,
                transition_count=data["count"],
                case_count=len(data["cases"]),
                avg_duration_seconds=round(avg_dur, 2),
                median_duration_seconds=round(med_dur, 2),
                min_duration_seconds=round(min_dur, 2),
                max_duration_seconds=round(max_dur, 2),
                is_rework=is_rework,
                is_bottleneck=False,
            )

            # Mark bottleneck candidate (ignoring trivial 0s transitions)
            if avg_dur > max_avg_duration and avg_dur > 0.0:
                max_avg_duration = avg_dur
                bottleneck_edge = edge

            edges.append(edge)

        # Flag the bottleneck edge in list
        if bottleneck_edge is not None:
            for ed in edges:
                if ed.source == bottleneck_edge.source and ed.target == bottleneck_edge.target:
                    ed.is_bottleneck = True
            bottleneck_edge.is_bottleneck = True

        # Sort edges descending by transition count
        edges.sort(key=lambda ed: ed.transition_count, reverse=True)
        nodes.sort(key=lambda nd: nd.frequency, reverse=True)

        return DFGResponse(
            process_id=process_id,
            nodes=nodes,
            edges=edges,
            bottleneck_edge=bottleneck_edge,
        )

    # ==========================================================================
    # Case Drilldown & Timeline
    # ==========================================================================

    async def list_cases(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
        variant_key: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> ProcessCasesListResponse:
        """List cases with optional variant filtering, status filtering, and pagination."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        query = select(ProcessCase).where(
            ProcessCase.process_id == process_id,
            ProcessCase.project_id == project_id,
        )
        if variant_key:
            query = query.where(ProcessCase.variant_key == variant_key.strip())
        if status:
            query = query.where(ProcessCase.status == status.strip().upper())

        # Total count
        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # Pagination
        offset = max(0, (page - 1) * limit)
        query = query.order_by(ProcessCase.started_at.desc()).limit(min(limit, 200)).offset(offset)
        cases = (await self.session.execute(query)).scalars().all()

        items = [
            ProcessCaseSummary(
                id=c.id,
                process_id=c.process_id,
                case_identifier=c.case_identifier,
                variant_key=c.variant_key,
                status=c.status,
                started_at=c.started_at,
                ended_at=c.ended_at,
                total_duration_seconds=c.total_duration_seconds,
                event_count=c.event_count,
            )
            for c in cases
        ]

        return ProcessCasesListResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
        )

    async def get_case_detail(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        process_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> ProcessCaseDetailResponse:
        """Retrieve detailed case summary and its ordered milestone event sequence."""
        await self.tenancy_service.get_project(org_id, project_id, user_id)
        await self.tenancy_service.verify_project_access(
            org_id, project_id, user_id, min_role=[ProjectRole.VIEWER, ProjectRole.ANALYST, ProjectRole.PROJECT_LEAD]
        )

        case_stmt = (
            select(ProcessCase)
            .where(
                ProcessCase.id == case_id,
                ProcessCase.process_id == process_id,
                ProcessCase.project_id == project_id,
            )
            .options(selectinload(ProcessCase.events))
        )
        case_obj = (await self.session.execute(case_stmt)).scalar_one_or_none()
        if case_obj is None:
            raise ProcessCaseNotFoundException(f"Process case {case_id} not found in this process.")

        events = sorted(case_obj.events, key=lambda e: (e.timestamp, e.activity_name))
        event_responses = [
            ProcessEventResponse(
                id=e.id,
                activity_name=e.activity_name,
                timestamp=e.timestamp,
                event_type=e.event_type,
                resource=e.resource,
                source_system=e.source_system,
                source_record_id=e.source_record_id,
                attributes=e.attributes_json,
            )
            for e in events
        ]

        return ProcessCaseDetailResponse(
            case=ProcessCaseSummary(
                id=case_obj.id,
                process_id=case_obj.process_id,
                case_identifier=case_obj.case_identifier,
                variant_key=case_obj.variant_key,
                status=case_obj.status,
                started_at=case_obj.started_at,
                ended_at=case_obj.ended_at,
                total_duration_seconds=case_obj.total_duration_seconds,
                event_count=case_obj.event_count,
            ),
            events=event_responses,
        )

    # ==========================================================================
    # Internal Helpers
    # ==========================================================================

    async def _get_process_or_404(self, project_id: uuid.UUID, process_id: uuid.UUID) -> Process:
        stmt = select(Process).where(
            Process.id == process_id,
            Process.project_id == project_id,
        )
        process = (await self.session.execute(stmt)).scalar_one_or_none()
        if process is None:
            raise ProcessNotFoundException(f"Process {process_id} not found in project {project_id}.")
        return process

    async def _get_process_counts(self, project_id: uuid.UUID, process_id: uuid.UUID) -> tuple[int, int]:
        c_stmt = select(func.count(ProcessCase.id)).where(
            ProcessCase.process_id == process_id,
            ProcessCase.project_id == project_id,
        )
        case_count = (await self.session.execute(c_stmt)).scalar() or 0

        e_stmt = select(func.count(ProcessEvent.id)).where(
            ProcessEvent.process_case_id.in_(
                select(ProcessCase.id).where(
                    ProcessCase.process_id == process_id,
                    ProcessCase.project_id == project_id,
                )
            )
        )
        event_count = (await self.session.execute(e_stmt)).scalar() or 0

        return case_count, event_count
