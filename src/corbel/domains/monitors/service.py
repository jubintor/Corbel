"""Domain application service orchestrating Adaptive Monitors & Exception Detection (Phase 7)."""

import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from corbel.core.config import get_settings
from corbel.domains.data_intelligence.models import Dataset
from corbel.domains.data_intelligence.parser import DatasetParser
from corbel.domains.governance.audit import AuditService
from corbel.domains.monitors.exceptions import (
    FindingNotFoundException,
    FindingTransitionException,
    MonitorEvaluationException,
    MonitorNotFoundException,
    MonitorValidationException,
)
from corbel.domains.monitors.models import (
    BusinessRule,
    EvaluationStatus,
    Finding,
    FindingStatus,
    Monitor,
    MonitorEvaluation,
    MonitorStatus,
    MonitorTargetType,
    RuleOperator,
    RuleSeverity,
)
from corbel.domains.monitors.schemas import (
    BusinessRuleCreate,
    BusinessRuleResponse,
    FindingResponse,
    FindingStatusUpdate,
    MonitorCreate,
    MonitorEvaluationResponse,
    MonitorResponse,
    MonitorUpdate,
)
from corbel.domains.ontology.models import BusinessObject
from corbel.domains.process_intelligence.models import Process, ProcessCase
from corbel.domains.tenancy.models import ProjectRole
from corbel.domains.tenancy.service import TenancyService

logger = logging.getLogger(__name__)

# Valid finding state transition map
VALID_FINDING_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.OPEN: {
        FindingStatus.ACKNOWLEDGED,
        FindingStatus.INVESTIGATING,
        FindingStatus.RECOMMENDED,
        FindingStatus.RESOLVED,
        FindingStatus.DISMISSED,
    },
    FindingStatus.ACKNOWLEDGED: {
        FindingStatus.INVESTIGATING,
        FindingStatus.RECOMMENDED,
        FindingStatus.RESOLVED,
        FindingStatus.DISMISSED,
    },
    FindingStatus.INVESTIGATING: {
        FindingStatus.RECOMMENDED,
        FindingStatus.RESOLVED,
        FindingStatus.DISMISSED,
        FindingStatus.OPEN,
    },
    FindingStatus.RECOMMENDED: {
        FindingStatus.RESOLVED,
        FindingStatus.DISMISSED,
        FindingStatus.OPEN,
    },
    FindingStatus.RESOLVED: {
        FindingStatus.OPEN,  # Reopening resolved finding
    },
    FindingStatus.DISMISSED: {
        FindingStatus.OPEN,  # Reopening dismissed finding
    },
}


class MonitorService:
    """Service providing monitor configuration, lifecycle management, and deterministic exception detection."""

    def __init__(self, session: AsyncSession, tenancy_service: TenancyService) -> None:
        self.session = session
        self.tenancy = tenancy_service
        self.settings = get_settings()
        self.audit = AuditService(session)

    # -------------------------------------------------------------------------
    # Helper Accessors
    # -------------------------------------------------------------------------

    async def _get_monitor_or_404(
        self, project_id: uuid.UUID, monitor_id: uuid.UUID
    ) -> Monitor:
        stmt = (
            select(Monitor)
            .where(Monitor.project_id == project_id, Monitor.id == monitor_id)
            .options(
                selectinload(Monitor.rules),
                selectinload(Monitor.findings),
                selectinload(Monitor.evaluations),
            )
        )
        res = await self.session.execute(stmt)
        monitor = res.scalar_one_or_none()
        if not monitor:
            raise MonitorNotFoundException(str(monitor_id))
        return monitor

    async def _get_finding_or_404(
        self, project_id: uuid.UUID, finding_id: uuid.UUID
    ) -> Finding:
        stmt = (
            select(Finding)
            .where(Finding.project_id == project_id, Finding.id == finding_id)
            .options(selectinload(Finding.rule))
        )
        res = await self.session.execute(stmt)
        finding = res.scalar_one_or_none()
        if not finding:
            raise FindingNotFoundException(str(finding_id))
        return finding

    async def _get_findings_counts(
        self, project_id: uuid.UUID, monitor_id: uuid.UUID
    ) -> tuple[int, int]:
        total_stmt = select(func.count(Finding.id)).where(
            Finding.project_id == project_id, Finding.monitor_id == monitor_id
        )
        total_count = (await self.session.execute(total_stmt)).scalar() or 0

        open_stmt = select(func.count(Finding.id)).where(
            Finding.project_id == project_id,
            Finding.monitor_id == monitor_id,
            Finding.status.in_([FindingStatus.OPEN.value, FindingStatus.ACKNOWLEDGED.value]),
        )
        open_count = (await self.session.execute(open_stmt)).scalar() or 0

        return open_count, total_count

    # -------------------------------------------------------------------------
    # Monitor Management (CRUD & Lifecycle)
    # -------------------------------------------------------------------------

    async def create_monitor(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        req: MonitorCreate,
    ) -> MonitorResponse:
        """Create a new operational monitor with validated target and rule configurations."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )

        # Validate unique monitor name within project
        dup_stmt = select(Monitor).where(
            Monitor.project_id == project_id, Monitor.name == req.name
        )
        if (await self.session.execute(dup_stmt)).scalar_one_or_none():
            raise MonitorValidationException(
                f"A monitor named '{req.name}' already exists in this project."
            )

        # Validate target scope
        if req.target_type == MonitorTargetType.PROCESS:
            # Check if referenced process exists in project
            try:
                proc_uuid = uuid.UUID(req.target_id)
                p_stmt = select(Process).where(
                    Process.project_id == project_id, Process.id == proc_uuid
                )
            except ValueError:
                p_stmt = select(Process).where(
                    Process.project_id == project_id, Process.name == req.target_id
                )
            proc = (await self.session.execute(p_stmt)).scalar_one_or_none()
            if not proc:
                raise MonitorValidationException(
                    f"Referenced target process '{req.target_id}' was not found in project."
                )

        # Validate business rule conditions
        for rule_req in req.rules:
            self._validate_rule_definition(req.target_type, rule_req)

        # Create monitor
        monitor = Monitor(
            project_id=project_id,
            name=req.name,
            description=req.description,
            target_type=req.target_type.value,
            target_id=req.target_id,
            schedule_cron=req.schedule_cron,
            status=req.status.value,
        )
        self.session.add(monitor)
        await self.session.flush()

        # Add rules
        for rule_req in req.rules:
            rule = BusinessRule(
                monitor_id=monitor.id,
                rule_code=rule_req.rule_code,
                description=rule_req.description,
                severity=rule_req.severity.value,
                rule_type=rule_req.rule_type,
                field_name=rule_req.field_name,
                operator=rule_req.operator.value,
                threshold_value=rule_req.threshold_value,
                threshold_string=rule_req.threshold_string,
                secondary_field=rule_req.secondary_field,
                parameters_json=rule_req.parameters_json,
            )
            self.session.add(rule)

        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="MONITOR_CREATED",
            affected_entity_type="Monitor",
            affected_entity_id=str(monitor.id),
            execution_context={"name": monitor.name, "target_type": monitor.target_type},
        )
        await self.session.commit()
        monitor = await self._get_monitor_or_404(project_id, monitor.id)

        return MonitorResponse(
            id=monitor.id,
            project_id=monitor.project_id,
            name=monitor.name,
            description=monitor.description,
            target_type=MonitorTargetType(monitor.target_type),
            target_id=monitor.target_id,
            schedule_cron=monitor.schedule_cron,
            status=MonitorStatus(monitor.status),
            last_run_at=monitor.last_run_at,
            last_status=monitor.last_status,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            rules=[BusinessRuleResponse.model_validate(r) for r in monitor.rules],
            open_findings_count=0,
            total_findings_count=0,
        )

    async def get_monitor(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
    ) -> MonitorResponse:
        """Retrieve monitor configuration, rules, and findings overview."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR, ProjectRole.APPROVER, ProjectRole.VIEWER],
        )
        monitor = await self._get_monitor_or_404(project_id, monitor_id)
        open_c, total_c = await self._get_findings_counts(project_id, monitor_id)

        return MonitorResponse(
            id=monitor.id,
            project_id=monitor.project_id,
            name=monitor.name,
            description=monitor.description,
            target_type=MonitorTargetType(monitor.target_type),
            target_id=monitor.target_id,
            schedule_cron=monitor.schedule_cron,
            status=MonitorStatus(monitor.status),
            last_run_at=monitor.last_run_at,
            last_status=monitor.last_status,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            rules=[BusinessRuleResponse.model_validate(r) for r in monitor.rules],
            open_findings_count=open_c,
            total_findings_count=total_c,
        )

    async def list_monitors(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[MonitorResponse]:
        """List all operational monitors configured for the active project."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR, ProjectRole.APPROVER, ProjectRole.VIEWER],
        )

        stmt = (
            select(Monitor)
            .where(Monitor.project_id == project_id)
            .options(selectinload(Monitor.rules))
            .order_by(Monitor.created_at.desc())
        )
        monitors = (await self.session.execute(stmt)).scalars().all()

        results: list[MonitorResponse] = []
        for m in monitors:
            open_c, total_c = await self._get_findings_counts(project_id, m.id)
            results.append(
                MonitorResponse(
                    id=m.id,
                    project_id=m.project_id,
                    name=m.name,
                    description=m.description,
                    target_type=MonitorTargetType(m.target_type),
                    target_id=m.target_id,
                    schedule_cron=m.schedule_cron,
                    status=MonitorStatus(m.status),
                    last_run_at=m.last_run_at,
                    last_status=m.last_status,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                    rules=[BusinessRuleResponse.model_validate(r) for r in m.rules],
                    open_findings_count=open_c,
                    total_findings_count=total_c,
                )
            )
        return results

    async def update_monitor(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
        req: MonitorUpdate,
    ) -> MonitorResponse:
        """Update monitor metadata, schedule, or activation status."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )

        monitor = await self._get_monitor_or_404(project_id, monitor_id)

        if req.name is not None and req.name != monitor.name:
            dup_stmt = select(Monitor).where(
                Monitor.project_id == project_id,
                Monitor.name == req.name,
                Monitor.id != monitor_id,
            )
            if (await self.session.execute(dup_stmt)).scalar_one_or_none():
                raise MonitorValidationException(
                    f"A monitor named '{req.name}' already exists in this project."
                )
            monitor.name = req.name

        if req.description is not None:
            monitor.description = req.description
        if req.schedule_cron is not None:
            monitor.schedule_cron = req.schedule_cron
        if req.status is not None:
            monitor.status = req.status.value

        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="MONITOR_UPDATED",
            affected_entity_type="Monitor",
            affected_entity_id=str(monitor.id),
            execution_context={"name": monitor.name, "status": monitor.status},
        )
        await self.session.commit()
        monitor = await self._get_monitor_or_404(project_id, monitor.id)

        open_c, total_c = await self._get_findings_counts(project_id, monitor_id)
        return MonitorResponse(
            id=monitor.id,
            project_id=monitor.project_id,
            name=monitor.name,
            description=monitor.description,
            target_type=MonitorTargetType(monitor.target_type),
            target_id=monitor.target_id,
            schedule_cron=monitor.schedule_cron,
            status=MonitorStatus(monitor.status),
            last_run_at=monitor.last_run_at,
            last_status=monitor.last_status,
            created_at=monitor.created_at,
            updated_at=monitor.updated_at,
            rules=[BusinessRuleResponse.model_validate(r) for r in monitor.rules],
            open_findings_count=open_c,
            total_findings_count=total_c,
        )

    async def delete_monitor(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
    ) -> None:
        """Delete monitor and cascade remove rules, findings, and evaluation logs."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )
        monitor = await self._get_monitor_or_404(project_id, monitor_id)
        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="MONITOR_DELETED",
            affected_entity_type="Monitor",
            affected_entity_id=str(monitor.id),
        )
        await self.session.delete(monitor)
        await self.session.commit()

    async def add_rule(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
        req: BusinessRuleCreate,
    ) -> BusinessRuleResponse:
        """Add a business rule to an existing operational monitor."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )
        monitor = await self._get_monitor_or_404(project_id, monitor_id)
        self._validate_rule_definition(MonitorTargetType(monitor.target_type), req)

        # Check unique rule_code within monitor
        dup = next((r for r in monitor.rules if r.rule_code == req.rule_code), None)
        if dup:
            raise MonitorValidationException(
                f"Rule code '{req.rule_code}' is already configured on this monitor."
            )

        rule = BusinessRule(
            monitor_id=monitor.id,
            rule_code=req.rule_code,
            description=req.description,
            severity=req.severity.value,
            rule_type=req.rule_type,
            field_name=req.field_name,
            operator=req.operator.value,
            threshold_value=req.threshold_value,
            threshold_string=req.threshold_string,
            secondary_field=req.secondary_field,
            parameters_json=req.parameters_json,
        )
        self.session.add(rule)
        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="MONITOR_RULE_ADDED",
            affected_entity_type="BusinessRule",
            affected_entity_id=str(rule.id),
            execution_context={"monitor_id": str(monitor.id), "rule_code": rule.rule_code},
        )
        await self.session.commit()
        refreshed_rule = (
            await self.session.execute(select(BusinessRule).where(BusinessRule.id == rule.id))
        ).scalar_one()
        return BusinessRuleResponse.model_validate(refreshed_rule)

    async def delete_rule(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
        rule_id: uuid.UUID,
    ) -> None:
        """Remove a business rule from a monitor."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )
        monitor = await self._get_monitor_or_404(project_id, monitor_id)
        rule = next((r for r in monitor.rules if r.id == rule_id), None)
        if not rule:
            raise MonitorValidationException(f"Rule '{rule_id}' not found on monitor.")
        if rule in monitor.rules:
            monitor.rules.remove(rule)
        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="MONITOR_RULE_DELETED",
            affected_entity_type="BusinessRule",
            affected_entity_id=str(rule_id),
            execution_context={"monitor_id": str(monitor.id)},
        )
        await self.session.delete(rule)
        await self.session.commit()

    # -------------------------------------------------------------------------
    # Exception / Finding Management
    # -------------------------------------------------------------------------

    async def list_findings(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID | None = None,
        finding_status: FindingStatus | None = None,
        severity: RuleSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[FindingResponse]:
        """List operational exception findings with optional status and severity filtering."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR, ProjectRole.APPROVER, ProjectRole.VIEWER],
        )

        stmt = select(Finding).where(Finding.project_id == project_id)

        if monitor_id is not None:
            stmt = stmt.where(Finding.monitor_id == monitor_id)
        if finding_status is not None:
            stmt = stmt.where(Finding.status == finding_status.value)
        if severity is not None:
            stmt = stmt.where(Finding.severity == severity.value)

        stmt = stmt.order_by(Finding.detected_at.desc()).limit(min(limit, 500)).offset(offset)
        findings = (await self.session.execute(stmt)).scalars().all()

        return [FindingResponse.model_validate(f) for f in findings]

    async def get_finding(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        finding_id: uuid.UUID,
    ) -> FindingResponse:
        """Retrieve single finding with complete factual context and evidence provenance."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR, ProjectRole.APPROVER, ProjectRole.VIEWER],
        )
        finding = await self._get_finding_or_404(project_id, finding_id)
        return FindingResponse.model_validate(finding)

    async def update_finding_status(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        finding_id: uuid.UUID,
        req: FindingStatusUpdate,
    ) -> FindingResponse:
        """Transition finding lifecycle state with audit attribution and resolution notes."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )

        finding = await self._get_finding_or_404(project_id, finding_id)
        current_st = FindingStatus(finding.status)
        target_st = req.status

        # Validate transition legality
        if target_st != current_st:
            valid_targets = VALID_FINDING_TRANSITIONS.get(current_st, set())
            if target_st not in valid_targets:
                raise FindingTransitionException(current_st.value, target_st.value)

        finding.status = target_st.value
        now = datetime.now(UTC)

        if target_st == FindingStatus.ACKNOWLEDGED and finding.acknowledged_at is None:
            finding.acknowledged_at = now
            finding.acknowledged_by = user_id

        if target_st in (FindingStatus.RESOLVED, FindingStatus.DISMISSED):
            finding.resolved_at = now
            finding.resolved_by = user_id
            if req.resolution_notes:
                finding.resolution_notes = req.resolution_notes

        await self.audit.log_event(
            organization_id=org_id,
            project_id=project_id,
            actor_id=str(user_id),
            action_type="FINDING_STATUS_UPDATED",
            affected_entity_type="Finding",
            affected_entity_id=str(finding.id),
            execution_context={
                "old_status": current_st.value,
                "new_status": target_st.value,
                "resolution_notes": req.resolution_notes,
            },
        )
        await self.session.commit()
        refreshed_finding = await self._get_finding_or_404(project_id, finding_id)
        return FindingResponse.model_validate(refreshed_finding)

    # -------------------------------------------------------------------------
    # Deterministic Monitor Evaluation Engine
    # -------------------------------------------------------------------------

    async def evaluate_monitor(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID,
        limit: int = 500,
    ) -> MonitorEvaluationResponse:
        """Execute deterministic evaluation of configured business rules against project operational data."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[ProjectRole.PROJECT_LEAD, ProjectRole.ANALYST, ProjectRole.OPERATOR],
        )

        monitor = await self._get_monitor_or_404(project_id, monitor_id)

        if monitor.status != MonitorStatus.ACTIVE.value:
            raise MonitorValidationException(
                f"Cannot evaluate monitor '{monitor.name}' because its status is {monitor.status}."
            )

        if not monitor.rules:
            raise MonitorValidationException(
                f"Monitor '{monitor.name}' has no active business rules configured."
            )

        start_time = time.perf_counter()
        bounded_limit = max(1, min(limit, 5000))

        records_scanned = 0
        findings_created = 0
        summary_info: dict[str, Any] = {
            "target_type": monitor.target_type,
            "target_id": monitor.target_id,
            "rules_evaluated": len(monitor.rules),
            "skipped_null_or_invalid": 0,
            "deduplicated_existing": 0,
        }

        try:
            if monitor.target_type == MonitorTargetType.PROCESS.value:
                records_scanned, findings_created = await self._evaluate_process_target(
                    project_id=project_id,
                    monitor=monitor,
                    limit=bounded_limit,
                    summary_info=summary_info,
                )
            else:
                records_scanned, findings_created = await self._evaluate_entity_target(
                    project_id=project_id,
                    monitor=monitor,
                    limit=bounded_limit,
                    summary_info=summary_info,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Record evaluation run ledger
            eval_record = MonitorEvaluation(
                project_id=project_id,
                monitor_id=monitor.id,
                status=EvaluationStatus.SUCCESS.value,
                records_evaluated=records_scanned,
                findings_detected=findings_created,
                execution_duration_ms=duration_ms,
                summary_json=summary_info,
            )
            self.session.add(eval_record)

            monitor.last_run_at = datetime.now(UTC)
            monitor.last_status = EvaluationStatus.SUCCESS.value

            await self.session.commit()
            refreshed_eval = (
                await self.session.execute(
                    select(MonitorEvaluation).where(MonitorEvaluation.id == eval_record.id)
                )
            ).scalar_one()

            return MonitorEvaluationResponse.model_validate(refreshed_eval)

        except Exception as exc:
            await self.session.rollback()
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Record failed evaluation
            err_msg = str(exc)[:1024]
            fail_eval = MonitorEvaluation(
                project_id=project_id,
                monitor_id=monitor.id,
                status=EvaluationStatus.ERROR.value,
                records_evaluated=records_scanned,
                findings_detected=0,
                execution_duration_ms=duration_ms,
                summary_json={"error": err_msg},
                error_message=err_msg,
            )
            self.session.add(fail_eval)
            monitor.last_run_at = datetime.now(UTC)
            monitor.last_status = EvaluationStatus.ERROR.value
            await self.session.commit()

            logger.error("Monitor evaluation failed: %s", exc, exc_info=True)
            raise MonitorEvaluationException(f"Evaluation failed: {err_msg}") from exc

    async def list_evaluations(
        self,
        org_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        monitor_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MonitorEvaluationResponse]:
        """List execution evaluation history for an operational project."""
        await self.tenancy.get_project(org_id, project_id, user_id)
        await self.tenancy.verify_project_access(
            org_id=org_id,
            project_id=project_id,
            user_id=user_id,
            min_role=[
                ProjectRole.PROJECT_LEAD,
                ProjectRole.ANALYST,
                ProjectRole.OPERATOR,
                ProjectRole.APPROVER,
                ProjectRole.VIEWER,
            ],
        )

        stmt = select(MonitorEvaluation).where(MonitorEvaluation.project_id == project_id)

        if monitor_id is not None:
            stmt = stmt.where(MonitorEvaluation.monitor_id == monitor_id)

        stmt = (
            stmt.order_by(MonitorEvaluation.evaluated_at.desc())
            .limit(min(max(1, limit), 500))
            .offset(max(0, offset))
        )
        evaluations = (await self.session.execute(stmt)).scalars().all()

        return [MonitorEvaluationResponse.model_validate(e) for e in evaluations]

    # -------------------------------------------------------------------------
    # Internal Evaluation Strategies
    # -------------------------------------------------------------------------

    async def _evaluate_process_target(
        self,
        project_id: uuid.UUID,
        monitor: Monitor,
        limit: int,
        summary_info: dict[str, Any],
    ) -> tuple[int, int]:
        """Evaluate process cases against cycle time SLA and process metrics."""
        # Find process
        try:
            p_uuid = uuid.UUID(monitor.target_id)
            stmt = select(Process).where(Process.project_id == project_id, Process.id == p_uuid)
        except ValueError:
            stmt = select(Process).where(Process.project_id == project_id, Process.name == monitor.target_id)
        process = (await self.session.execute(stmt)).scalar_one_or_none()

        if not process:
            raise MonitorValidationException(f"Process '{monitor.target_id}' not found in project.")

        cases_stmt = (
            select(ProcessCase)
            .where(ProcessCase.project_id == project_id, ProcessCase.process_id == process.id)
            .order_by(ProcessCase.started_at.desc())
            .limit(limit)
        )
        cases = (await self.session.execute(cases_stmt)).scalars().all()

        scanned = 0
        created = 0

        for case in cases:
            scanned += 1
            for rule in monitor.rules:
                # Resolve observed field value
                obs_val: float | None = None
                if rule.field_name in ("total_duration_seconds", "duration", "duration_seconds"):
                    obs_val = float(case.total_duration_seconds)
                elif rule.field_name in ("event_count", "events"):
                    obs_val = float(case.event_count)
                else:
                    summary_info["skipped_null_or_invalid"] += 1
                    continue

                if rule.threshold_value is None:
                    continue

                violates = self._check_numeric_condition(
                    obs_val, rule.operator, rule.threshold_value
                )
                if violates:
                    dedup_key = f"{project_id}:{monitor.id}:{rule.rule_code}:ProcessCase:{case.case_identifier}"
                    dedup_hash = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()

                    # Check if already emitted
                    exists_stmt = select(Finding.id).where(
                        Finding.project_id == project_id,
                        Finding.deduplication_hash == dedup_hash,
                    )
                    if (await self.session.execute(exists_stmt)).scalar_one_or_none():
                        summary_info["deduplicated_existing"] += 1
                        continue

                    summary_text = (
                        f"Process case '{case.case_identifier}' observed {rule.field_name}="
                        f"{obs_val:.1f} which violates rule '{rule.rule_code}' "
                        f"({rule.operator} {rule.threshold_value})."
                    )

                    context_payload = {
                        "case_identifier": case.case_identifier,
                        "process_id": str(case.process_id),
                        "process_name": process.name,
                        "variant_key": case.variant_key,
                        "field_name": rule.field_name,
                        "observed_value": obs_val,
                        "threshold_value": rule.threshold_value,
                        "operator": rule.operator,
                        "total_duration_seconds": case.total_duration_seconds,
                        "started_at": case.started_at.isoformat(),
                        "ended_at": case.ended_at.isoformat(),
                    }

                    finding = Finding(
                        project_id=project_id,
                        monitor_id=monitor.id,
                        rule_id=rule.id,
                        process_case_id=case.id,
                        entity_type="ProcessCase",
                        entity_id=case.case_identifier,
                        finding_type=rule.rule_type,
                        severity=rule.severity,
                        status=FindingStatus.OPEN.value,
                        summary=summary_text,
                        deduplication_hash=dedup_hash,
                        observed_value=f"{obs_val:.2f}",
                        threshold_value=str(rule.threshold_value),
                        verified_context_json=context_payload,
                    )
                    self.session.add(finding)
                    created += 1

        return scanned, created

    async def _evaluate_entity_target(
        self,
        project_id: uuid.UUID,
        monitor: Monitor,
        limit: int,
        summary_info: dict[str, Any],
    ) -> tuple[int, int]:
        """Evaluate business entity dataset records against configured deterministic threshold rules."""
        storage_root = Path(self.settings.DATASET_STORAGE_DIR).resolve()

        # Look up datasets matching entity name or associated with project
        ds_stmt = (
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .options(selectinload(Dataset.versions))
        )
        datasets = (await self.session.execute(ds_stmt)).scalars().all()

        target_name_lower = monitor.target_id.lower().replace(" ", "").replace("_", "")

        matched_ds: Dataset | None = None
        for ds in datasets:
            ds_name_clean = ds.name.lower().replace(" ", "").replace("_", "")
            if target_name_lower in ds_name_clean or ds_name_clean in target_name_lower:
                matched_ds = ds
                break

        # Fallback for common P2P terms
        if not matched_ds:
            if "order" in target_name_lower or "po" in target_name_lower:
                matched_ds = next((d for d in datasets if "purchase" in d.name.lower() or "po" in d.name.lower() or "order" in d.name.lower()), None)
            elif "invoice" in target_name_lower or "inv" in target_name_lower:
                matched_ds = next((d for d in datasets if "invoice" in d.name.lower()), None)

        if not matched_ds or not matched_ds.versions:
            # Check if business object exists with mapped property
            bo_stmt = (
                select(BusinessObject)
                .where(BusinessObject.project_id == project_id, BusinessObject.name == monitor.target_id)
                .options(selectinload(BusinessObject.properties))
            )
            bo = (await self.session.execute(bo_stmt)).scalar_one_or_none()
            if not bo:
                raise MonitorValidationException(
                    f"Target entity '{monitor.target_id}' has no matching dataset or confirmed business object in project."
                )
            summary_info["notice"] = "Business object verified but no associated dataset version available."
            return 0, 0

        # Stream rows from latest version
        latest_ver = sorted(matched_ds.versions, key=lambda v: v.version_number, reverse=True)[0]
        data_path = (storage_root / latest_ver.storage_path).resolve()
        if not data_path.exists():
            raise MonitorValidationException(f"Dataset file '{latest_ver.storage_path}' not found on storage disk.")

        parser = DatasetParser(data_path, latest_ver.file_format)
        headers, row_gen = parser.parse_headers_and_stream()
        h_map = {h.lower().strip(): idx for idx, h in enumerate(headers)}

        # Helper to find column index
        def _col_idx(name: str) -> int | None:
            clean = name.lower().strip()
            if clean in h_map:
                return h_map[clean]
            # fuzzy matching
            for k, idx in h_map.items():
                if clean in k or k in clean:
                    return idx
            return None

        # Identify primary key column
        id_idx = None
        for cand in ("id", "po_id", "po_number", "order_id", "invoice_id", "invoice_number", "inv_id", "record_id"):
            id_idx = _col_idx(cand)
            if id_idx is not None:
                break

        scanned = 0
        created = 0

        for row in row_gen:
            if scanned >= limit:
                break
            scanned += 1

            record_id = str(row[id_idx]) if id_idx is not None and id_idx < len(row) and row[id_idx] else f"REC-{scanned}"
            row_dict = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}

            for rule in monitor.rules:
                field_idx = _col_idx(rule.field_name)
                if field_idx is None or field_idx >= len(row) or row[field_idx] is None or row[field_idx] == "":
                    summary_info["skipped_null_or_invalid"] += 1
                    continue

                raw_val = row[field_idx]

                # Special P2P Variance check (e.g. invoice unit_price vs po unit_price)
                if rule.rule_type == "VARIANCE" and rule.secondary_field:
                    sec_idx = _col_idx(rule.secondary_field)
                    if sec_idx is None or sec_idx >= len(row) or row[sec_idx] is None or row[sec_idx] == "":
                        summary_info["skipped_null_or_invalid"] += 1
                        continue
                    try:
                        p_val = float(raw_val)
                        s_val = float(row[sec_idx])
                    except (ValueError, TypeError):
                        summary_info["skipped_null_or_invalid"] += 1
                        continue

                    if s_val == 0.0:
                        continue

                    # Relative variance: (p_val - s_val) / s_val
                    variance = (p_val - s_val) / s_val
                    threshold = rule.threshold_value if rule.threshold_value is not None else 0.0
                    violates = self._check_numeric_condition(variance, rule.operator, threshold)

                    if violates:
                        created += await self._emit_entity_finding(
                            project_id=project_id,
                            monitor=monitor,
                            rule=rule,
                            entity_id=record_id,
                            observed_val=f"{variance * 100.0:.2f}% (val={p_val}, baseline={s_val})",
                            threshold_val=f"{threshold * 100.0:.2f}%",
                            row_dict=row_dict,
                            summary_info=summary_info,
                        )
                    continue

                # Standard numeric condition
                if rule.threshold_value is not None:
                    try:
                        num_val = float(raw_val)
                    except (ValueError, TypeError):
                        summary_info["skipped_null_or_invalid"] += 1
                        continue

                    violates = self._check_numeric_condition(num_val, rule.operator, rule.threshold_value)
                    if violates:
                        created += await self._emit_entity_finding(
                            project_id=project_id,
                            monitor=monitor,
                            rule=rule,
                            entity_id=record_id,
                            observed_val=f"{num_val:.2f}",
                            threshold_val=f"{rule.threshold_value:.2f}",
                            row_dict=row_dict,
                            summary_info=summary_info,
                        )
                elif rule.threshold_string is not None:
                    str_val = str(raw_val).strip()
                    violates = False
                    if rule.operator in (RuleOperator.EQ.value, RuleOperator.EQ):
                        violates = (str_val == rule.threshold_string.strip())
                    elif rule.operator in (RuleOperator.NEQ.value, RuleOperator.NEQ):
                        violates = (str_val != rule.threshold_string.strip())

                    if violates:
                        created += await self._emit_entity_finding(
                            project_id=project_id,
                            monitor=monitor,
                            rule=rule,
                            entity_id=record_id,
                            observed_val=str_val,
                            threshold_val=rule.threshold_string,
                            row_dict=row_dict,
                            summary_info=summary_info,
                        )

        return scanned, created

    async def _emit_entity_finding(
        self,
        project_id: uuid.UUID,
        monitor: Monitor,
        rule: BusinessRule,
        entity_id: str,
        observed_val: str,
        threshold_val: str,
        row_dict: dict[str, Any],
        summary_info: dict[str, Any],
    ) -> int:
        """Create finding with deterministic deduplication hash."""
        dedup_key = f"{project_id}:{monitor.id}:{rule.rule_code}:{monitor.target_id}:{entity_id}"
        dedup_hash = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()

        # Check existing finding
        exists_stmt = select(Finding.id).where(
            Finding.project_id == project_id,
            Finding.deduplication_hash == dedup_hash,
        )
        if (await self.session.execute(exists_stmt)).scalar_one_or_none():
            summary_info["deduplicated_existing"] += 1
            return 0

        summary_text = (
            f"{monitor.target_id} '{entity_id}' observed {rule.field_name}="
            f"{observed_val} which violates operational rule '{rule.rule_code}' "
            f"({rule.operator} {threshold_val})."
        )

        context_payload = {
            "entity_type": monitor.target_id,
            "entity_id": entity_id,
            "field_name": rule.field_name,
            "observed_value": observed_val,
            "threshold_value": threshold_val,
            "operator": rule.operator,
            "source_record": row_dict,
        }

        finding = Finding(
            project_id=project_id,
            monitor_id=monitor.id,
            rule_id=rule.id,
            entity_type=monitor.target_id,
            entity_id=entity_id,
            finding_type=rule.rule_type,
            severity=rule.severity,
            status=FindingStatus.OPEN.value,
            summary=summary_text,
            deduplication_hash=dedup_hash,
            observed_value=observed_val,
            threshold_value=threshold_val,
            verified_context_json=context_payload,
        )
        self.session.add(finding)
        return 1

    def _check_numeric_condition(
        self, observed: float, operator: str, threshold: float
    ) -> bool:
        """Evaluate deterministic arithmetic comparison."""
        op = operator.lower() if isinstance(operator, str) else operator.value.lower()
        if op == "gt":
            return observed > threshold
        if op == "gte":
            return observed >= threshold
        if op == "lt":
            return observed < threshold
        if op == "lte":
            return observed <= threshold
        if op == "eq":
            return abs(observed - threshold) < 1e-9
        if op == "neq":
            return abs(observed - threshold) >= 1e-9
        return False

    def _validate_rule_definition(
        self, target_type: MonitorTargetType, rule: BusinessRuleCreate
    ) -> None:
        """Validate rule syntax, operator compatibility, and threshold values."""
        if not rule.rule_code or len(rule.rule_code.strip()) < 2:
            raise MonitorValidationException("Rule code must be at least 2 characters.")

        if not rule.field_name or len(rule.field_name.strip()) < 1:
            raise MonitorValidationException("Rule target field_name must be specified.")

        if (
            rule.operator in (RuleOperator.GT, RuleOperator.GTE, RuleOperator.LT, RuleOperator.LTE)
            and rule.threshold_value is None
        ):
            raise MonitorValidationException(
                f"Numeric operator '{rule.operator.value}' requires a numeric threshold_value."
            )

        if (
            rule.operator in (RuleOperator.EQ, RuleOperator.NEQ)
            and rule.threshold_value is None
            and rule.threshold_string is None
        ):
            raise MonitorValidationException(
                f"Equality operator '{rule.operator.value}' requires either threshold_value or threshold_string."
            )
