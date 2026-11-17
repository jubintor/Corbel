"""Authoritative native PostgreSQL audit domain service.

Enforces ADR-020:
- Append-only audit store with database-level immutability triggers.
- Automatic canonical payload hash generation (SHA-256) and payload integrity verification.
- Sensitive credential and PII redaction.
- Cross-domain administrative and operational audit trail capture.
- Operational ROI and MTTR progression evaluation.
"""

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from corbel.ai.costs.service import CostService
from corbel.domains.governance.models import (
    Action,
    ActionExecution,
    ActorType,
    AuditEvent,
    ExecutionStatus,
    Investigation,
    Recommendation,
)
from corbel.domains.governance.schemas import (
    AuditTrailExportItem,
    AuditTrailExportResponse,
    OperationalRoiResponse,
)
from corbel.domains.monitors.models import Finding
from corbel.domains.tenancy.models import Project

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "credit_card",
    "card_number",
    "cookie",
    "session",
    "session_id",
    "sessionid",
    "csrf",
    "xsrf",
    "client_secret",
    "private_key",
}

DATABASE_URI_PATTERN = re.compile(
    r"(?i)\b((?:postgres(?:ql)?(?:\+[a-z0-9_]+)?|mysql(?:\+[a-z0-9_]+)?|mssql(?:\+[a-z0-9_]+)?|mongodb(?:\+srv)?|redis[s]?):\/\/[^\s\"'<>]+)"
)


def redact_database_uri_in_text(text: str) -> str:
    """Robustly redact userinfo credentials from database connection URIs in text.

    Correctly handles passwords with special characters (e.g. '@', ':', URL-encoded '%40'),
    while preserving the scheme, username, hostname, port, and database name.
    """

    def _replace_uri(match: re.Match[str]) -> str:
        uri_str = match.group(1)
        trailing = ""
        while uri_str and uri_str[-1] in ".,;:)!?'\"":
            trailing = uri_str[-1] + trailing
            uri_str = uri_str[:-1]

        scheme_match = re.match(r"^([a-zA-Z0-9+_-]+:\/\/)(.*)$", uri_str)
        if not scheme_match:
            return uri_str + trailing

        scheme_prefix = scheme_match.group(1)
        body = scheme_match.group(2)

        # In URI syntax: authority ends at the first '/', '?', or '#'
        path_match = re.search(r"[/?#]", body)
        if path_match:
            authority = body[: path_match.start()]
            rest_path = body[path_match.start() :]
        else:
            authority = body
            rest_path = ""

        # If no '@' in authority, there is no userinfo/credentials in the authority component
        if "@" not in authority:
            return uri_str + trailing

        # When password contains '@' (e.g. admin:p@ssw0rd99@db:5432),
        # the hostname/port is ALWAYS after the LAST '@' in the authority component.
        userinfo, host_port = authority.rsplit("@", 1)

        # If userinfo contains ':', split user and password on the first ':' only
        # so passwords containing ':' are fully redacted.
        if ":" in userinfo:
            user, _ = userinfo.split(":", 1)
            redacted_userinfo = f"{user}:[REDACTED]"
        else:
            redacted_userinfo = "[REDACTED]"

        redacted_authority = f"{redacted_userinfo}@{host_port}"
        return f"{scheme_prefix}{redacted_authority}{rest_path}{trailing}"

    return DATABASE_URI_PATTERN.sub(_replace_uri, text)


CREDENTIAL_STRING_PATTERNS = [
    # Bearer tokens (JWT or opaque)
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE),
    # Common provider API keys (OpenAI sk-..., Anthropic sk-ant-..., etc.)
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    # Key-value secret/password/api_key assignments (e.g. password=..., api_key="...")
    re.compile(
        r"((?:api[_-]?key|password|secret|access_token|refresh_token)\s*[:=]\s*['\"]?)[^'\"\s,;]{6,}(['\"]?)",
        re.IGNORECASE,
    ),
    # Cookie header strings (e.g. Cookie: session=...; token=...)
    re.compile(
        r"((?:session(?:_?id)?|token|csrf|xsrf)\s*=\s*)[A-Za-z0-9_\-\.]{10,}",
        re.IGNORECASE,
    ),
]


def redact_string_credentials(text: str) -> str:
    """Sanitize string values by redacting common credentials, tokens, and connection strings."""
    if not text:
        return text
    # 1. Apply URI-aware database credential redaction
    sanitized = redact_database_uri_in_text(text)
    # 2. Apply other credential patterns
    for pattern in CREDENTIAL_STRING_PATTERNS:
        if pattern.groups == 2:
            sanitized = pattern.sub(r"\g<1>[REDACTED]\g<2>", sanitized)
        elif pattern.groups == 1:
            sanitized = pattern.sub(r"\g<1>[REDACTED]", sanitized)
        else:
            sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def redact_sensitive_data(val: Any) -> Any:
    """Recursively redact sensitive credential keys and embedded string secrets."""
    if isinstance(val, dict):
        cleaned: dict[str, Any] = {}
        for k, v in val.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = redact_sensitive_data(v)
        return cleaned
    elif isinstance(val, list):
        return [redact_sensitive_data(item) for item in val]
    elif isinstance(val, str):
        return redact_string_credentials(val)
    return val


def compute_canonical_payload_hash(payload: Any) -> str:
    """Compute deterministic SHA-256 hash of a JSON-serializable canonical payload."""
    if payload is None:
        return hashlib.sha256(b"").hexdigest()
    try:
        canonical_str = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        canonical_str = str(payload)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


class AuditService:
    """Authoritative service for recording, querying, and exporting append-only audit events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None,
        actor_id: str,
        action_type: str,
        affected_entity_type: str,
        affected_entity_id: str,
        execution_context: dict[str, Any] | None = None,
        actor_type: ActorType = ActorType.USER,
        outcome_status: str = "SUCCESS",
        correlation_id: str | None = None,
        canonical_payload_hash: str | None = None,
        ip_address: str | None = None,
    ) -> AuditEvent:
        """Create an immutable append-only audit record in PostgreSQL.

        Automatically redacts credentials and computes SHA-256 payload integrity hash
        if not explicitly supplied.
        """
        # Redact sensitive attributes before persistence
        sanitized_context = redact_sensitive_data(execution_context) if execution_context is not None else None

        # Authoritatively compute canonical payload hash from sanitized payload
        calculated_hash: str | None = None
        if sanitized_context is not None:
            calculated_hash = compute_canonical_payload_hash(sanitized_context)

        # Integrity check: Never trust caller-supplied hashes.
        # If caller passed a hash, verify it matches the authoritative hash; reject mismatches.
        if canonical_payload_hash is not None and (calculated_hash is None or canonical_payload_hash != calculated_hash):
            raise ValueError(
                f"Integrity violation: caller-supplied canonical_payload_hash '{canonical_payload_hash}' "
                f"does not match authoritative calculated hash '{calculated_hash}' of the sanitized payload."
            )

        audit_event = AuditEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            project_id=project_id,
            actor_type=actor_type.value if hasattr(actor_type, "value") else str(actor_type),
            actor_id=str(actor_id),
            action_type=action_type,
            affected_entity_type=affected_entity_type,
            affected_entity_id=str(affected_entity_id),
            execution_context_json=sanitized_context,
            correlation_id=correlation_id,
            canonical_payload_hash=calculated_hash,
            outcome_status=outcome_status,
            ip_address=ip_address,
        )
        self.session.add(audit_event)
        await self.session.flush()
        return audit_event

    async def list_events(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        action_type: str | None = None,
        affected_entity_type: str | None = None,
        actor_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEvent], int]:
        """List audit events matching filters with bounded pagination."""
        query = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        if project_id is not None:
            query = query.where(AuditEvent.project_id == project_id)
        if action_type:
            query = query.where(AuditEvent.action_type == action_type)
        if affected_entity_type:
            query = query.where(AuditEvent.affected_entity_type == affected_entity_type)
        if actor_id:
            query = query.where(AuditEvent.actor_id == actor_id)
        if correlation_id:
            query = query.where(AuditEvent.correlation_id == correlation_id)

        count_query = select(func.count(AuditEvent.id)).where(AuditEvent.organization_id == organization_id)
        if project_id is not None:
            count_query = count_query.where(AuditEvent.project_id == project_id)
        if action_type:
            count_query = count_query.where(AuditEvent.action_type == action_type)
        if affected_entity_type:
            count_query = count_query.where(AuditEvent.affected_entity_type == affected_entity_type)
        if actor_id:
            count_query = count_query.where(AuditEvent.actor_id == actor_id)
        if correlation_id:
            count_query = count_query.where(AuditEvent.correlation_id == correlation_id)

        total = (await self.session.execute(count_query)).scalar_one()

        query = query.order_by(desc(AuditEvent.timestamp)).limit(limit).offset(offset)
        res = await self.session.execute(query)
        return list(res.scalars().all()), total

    async def export_audit_trail(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
        limit: int = 1000,
    ) -> AuditTrailExportResponse:
        """Export complete audit trail with cryptographic payload verification.

        Note: integrity_verified reflects per-record canonical payload SHA-256 hash matching
        and does not provide cryptographic tamper evidence against privileged database
        administrators or record deletion/insertion/reordering attacks (which requires
        external cryptographic chaining or anchoring, deferred).
        """
        events, total = await self.list_events(
            organization_id=organization_id,
            project_id=project_id,
            limit=limit,
            offset=0,
        )

        export_items: list[AuditTrailExportItem] = []

        for ev in events:
            calc_hash: str | None = None

            if ev.execution_context_json is not None:
                calc_hash = compute_canonical_payload_hash(ev.execution_context_json)
                if ev.canonical_payload_hash is not None:
                    if calc_hash == ev.canonical_payload_hash:
                        verification_status = "VERIFIED"
                    else:
                        verification_status = "HASH_MISMATCH"
                else:
                    verification_status = "UNHASHED_PAYLOAD"
            elif ev.canonical_payload_hash is not None:
                verification_status = "UNAVAILABLE_PAYLOAD"
            else:
                verification_status = "NO_PAYLOAD"

            item = AuditTrailExportItem(
                id=ev.id,
                organization_id=ev.organization_id,
                project_id=ev.project_id,
                actor_type=ActorType(ev.actor_type) if ev.actor_type in [a.value for a in ActorType] else ActorType.USER,
                actor_id=ev.actor_id,
                action_type=ev.action_type,
                affected_entity_type=ev.affected_entity_type,
                affected_entity_id=ev.affected_entity_id,
                execution_context_json=ev.execution_context_json,
                correlation_id=ev.correlation_id,
                canonical_payload_hash=ev.canonical_payload_hash,
                outcome_status=ev.outcome_status,
                ip_address=ev.ip_address,
                timestamp=ev.timestamp,
                payload_verification_status=verification_status,
                calculated_payload_hash=calc_hash,
            )
            export_items.append(item)

        all_verified = True if not events else all(
            item.payload_verification_status == "VERIFIED" for item in export_items
        )

        return AuditTrailExportResponse(
            organization_id=organization_id,
            project_id=project_id,
            exported_at=datetime.now(UTC),
            total_events=total,
            integrity_verified=all_verified,
            events=export_items,
        )

    async def get_operational_roi(
        self,
        organization_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> OperationalRoiResponse:
        """Calculate MTTR progression and financial ROI metrics for governed workflows.

        Strictly tenant-isolated: ensures all investigations, executions, and costs belong
        to the specified organization_id. If project_id is provided, enforces that the project
        belongs to organization_id.
        """
        # 1. Query investigations scoped to organization (and optionally project)
        inv_stmt = (
            select(Investigation)
            .join(Project, Investigation.project_id == Project.id)
            .where(Project.organization_id == organization_id)
        )
        if project_id is not None:
            inv_stmt = inv_stmt.where(Investigation.project_id == project_id)

        inv_rows = (await self.session.execute(inv_stmt)).scalars().all()
        incidents_investigated = len(inv_rows)

        # 2. Query qualifying successful terminal executions joined with their Investigation, Finding, and Project.
        # Enforce Project.organization_id == organization_id for strict tenant isolation.
        # Order deterministically by ActionExecution.completed_at.asc(), ActionExecution.id.asc()
        # so that the earliest qualifying execution per finding is selected.
        exec_stmt = (
            select(ActionExecution, Investigation, Finding)
            .join(Action, ActionExecution.action_id == Action.id)
            .join(Recommendation, Action.recommendation_id == Recommendation.id)
            .join(Investigation, Recommendation.investigation_id == Investigation.id)
            .join(Project, Investigation.project_id == Project.id)
            .outerjoin(Finding, Investigation.finding_id == Finding.id)
            .where(
                Project.organization_id == organization_id,
                ActionExecution.status == ExecutionStatus.SUCCEEDED.value,
                ActionExecution.completed_at.isnot(None),
            )
        )
        if project_id is not None:
            exec_stmt = exec_stmt.where(Investigation.project_id == project_id)

        exec_stmt = exec_stmt.order_by(
            ActionExecution.completed_at.asc(),
            ActionExecution.id.asc(),
        )

        exec_results = (await self.session.execute(exec_stmt)).all()

        durations_minutes: list[float] = []
        total_financial_impact = 0.0
        resolved_finding_ids: set[Any] = set()

        for action_exec, inv, finding in exec_results:
            if finding is not None and finding.id is not None:
                finding_key = finding.id
            elif inv.finding_id is not None:
                finding_key = inv.finding_id
            else:
                # Stable investigation-specific fallback when finding_id is null,
                # ensuring unrelated investigations without findings are not collapsed into one.
                finding_key = f"investigation:{inv.id}"

            # Skip if finding was already counted to prevent duplicate financial impact
            if finding_key in resolved_finding_ids:
                continue

            resolved_finding_ids.add(finding_key)
            total_financial_impact += float(inv.financial_impact_usd)

            detection_time = (
                finding.detected_at
                if finding and finding.detected_at
                else inv.created_at
            )
            if detection_time and action_exec.completed_at:
                duration_seconds = (action_exec.completed_at - detection_time).total_seconds()
                # Handle missing or invalid/negative detection-to-completion durations safely.
                # Never convert a negative duration into an artificial positive MTTR value.
                if duration_seconds >= 0:
                    durations_minutes.append(duration_seconds / 60.0)
                else:
                    logger.warning(
                        "Negative duration detected for finding %s (detected_at: %s, completed_at: %s); excluded from MTTR calculation.",
                        finding_key,
                        detection_time,
                        action_exec.completed_at,
                    )

        resolved_count = len(resolved_finding_ids)

        # Reference baseline MTTR for manual discrepancy resolution (48 hours = 2880 mins), assumed baseline
        baseline_mttr_minutes = 2880.0
        avg_minutes = (
            sum(durations_minutes) / len(durations_minutes)
            if durations_minutes
            else 0.0
        )
        current_mttr_minutes = (
            max(0.01, round(avg_minutes, 2))
            if avg_minutes > 0.0
            else 0.0
        )

        mttr_reduction_percentage = 0.0
        if current_mttr_minutes > 0.0 and baseline_mttr_minutes > 0.0:
            reduction = ((baseline_mttr_minutes - current_mttr_minutes) / baseline_mttr_minutes) * 100.0
            mttr_reduction_percentage = round(max(0.0, reduction), 2)

        # 3. AI cost and cost per successful task
        cost_service = CostService(self.session)
        cost_summary = await cost_service.get_cost_summary(
            organization_id=organization_id,
            project_id=project_id,
        )

        total_ai_cost = cost_summary.total_cost_usd
        cost_per_successful_task = cost_summary.cost_per_successful_task

        benefit_cost_ratio = (
            round(total_financial_impact / total_ai_cost, 2)
            if total_ai_cost > 0.0
            else 0.0
        )

        return OperationalRoiResponse(
            organization_id=organization_id,
            project_id=project_id,
            incidents_investigated=incidents_investigated,
            incidents_resolved=resolved_count,
            baseline_mttr_minutes=baseline_mttr_minutes,
            current_mttr_minutes=current_mttr_minutes,
            mttr_reduction_percentage=mttr_reduction_percentage,
            total_financial_impact_addressed_usd=round(total_financial_impact, 2),
            total_ai_cost_usd=round(total_ai_cost, 6),
            cost_per_successful_task_usd=round(cost_per_successful_task, 6),
            benefit_cost_ratio=benefit_cost_ratio,
            financial_roi_ratio=benefit_cost_ratio,
        )
