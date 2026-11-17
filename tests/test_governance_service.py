"""Unit and integration tests for GovernanceService, Approvals & Action Dispatcher."""

import uuid

import pytest
from httpx import AsyncClient

from corbel.core.database import get_session_factory
from corbel.domains.governance.exceptions import (
    InvalidActionStateException,
    InvalidApprovalStateException,
    PayloadIntegrityException,
)
from corbel.domains.governance.models import (
    ActionStatus,
    ApprovalStatus,
    InvestigationStatus,
)
from corbel.domains.governance.schemas import (
    ActionExecuteRequest,
    ApprovalDecisionRequest,
    DocumentCreateRequest,
    DocumentType,
    InvestigationCreateRequest,
)
from corbel.domains.governance.service import GovernanceService, compute_payload_hash
from corbel.domains.monitors.models import (
    Finding,
    FindingStatus,
    Monitor,
    MonitorStatus,
    MonitorTargetType,
)
from corbel.domains.tenancy.service import TenancyService
from tests.test_dataset_ingestion import setup_test_org_and_project


@pytest.mark.anyio
async def test_investigation_lifecycle_and_evidence_capture(async_client: AsyncClient) -> None:
    """Test creating an investigation from a finding, capturing facts, hypotheses, and recommendations."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = GovernanceService(session, tenancy_service)

        # 1. Ingest Contract for RAG
        doc = await service.create_document(
            org_id,
            project_id,
            user_id,
            DocumentCreateRequest(
                title="Apex Supply Terms",
                document_type=DocumentType.CONTRACT,
                file_name="Apex_Terms.txt",
                raw_text=(
                    "Clause 4. Pricing and Freight Terms\n"
                    "All shipping surcharges must receive prior written approval from buyer. "
                    "Invoices with unauthorized freight will be held for review."
                ),
            ),
        )
        assert doc.id is not None

        # 2. Create Monitor and Finding
        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="P2P Value Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        dedup = uuid.uuid4().hex
        finding = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-7844",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.OPEN.value,
            summary="Invoice INV-7844 billed $16,250.00 exceeding PO-10023 ($15,000.00) by $1,250.00",
            deduplication_hash=dedup,
            observed_value="16250.00",
            threshold_value="15000.00",
            verified_context_json={"po_number": "PO-10023", "supplier_name": "Apex Industrial"},
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        # 3. Create Investigation
        inv = await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(
                finding_id=finding.id,
                title="Investigation of INV-7844 Variance",
                include_rag_documents=True,
            ),
        )

        assert inv.id is not None
        assert inv.status == InvestigationStatus.COMPLETED.value
        assert inv.financial_impact_usd == 1250.00
        assert len(inv.verified_facts_json) >= 1
        assert "Candidate causal hypothesis" in (inv.causal_hypothesis or "")
        assert len(inv.missing_evidence_json) >= 1

        # Check evidence items
        evidence = await service.list_evidence(org_id, project_id, user_id, inv.id)
        assert len(evidence) >= 1

        # Verify finding transitioned to INVESTIGATING
        await session.refresh(finding)
        assert finding.status == FindingStatus.INVESTIGATING.value

        # Verify recommendations and action created
        actions = await service.list_actions(org_id, project_id, user_id)
        assert len(actions) == 1
        action = actions[0]
        assert action.status == ActionStatus.AWAITING_APPROVAL.value
        assert action.is_consequential is True

        # Verify pending approval gate created
        approvals = await service.list_approvals(org_id, project_id, user_id)
        assert len(approvals) == 1
        assert approvals[0].status == ApprovalStatus.PENDING.value
        assert approvals[0].action_id == action.id


@pytest.mark.anyio
async def test_human_approval_gate_and_canonical_hash_generation(async_client: AsyncClient) -> None:
    """Test approval gate computing SHA-256 canonical payload hash on authorization."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = GovernanceService(session, tenancy_service)

        # Set up finding and investigation
        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Invoice Test Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-9901",
            finding_type="PRICE_VARIANCE",
            severity="MEDIUM",
            status=FindingStatus.OPEN.value,
            summary="Price variance on INV-9901",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="5500.00",
            threshold_value="5000.00",
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(finding_id=finding.id, include_rag_documents=False),
        )

        approvals = await service.list_approvals(org_id, project_id, user_id)
        approval = approvals[0]
        approval_id = approval.id
        actions = await service.list_actions(org_id, project_id, user_id)
        action = actions[0]

        # 1. Authorize approval
        decided_approval = await service.decide_approval(
            org_id,
            project_id,
            user_id,
            approval_id,
            ApprovalDecisionRequest(
                decision=ApprovalStatus.APPROVED,
                rationale="Approved by Procurement Manager after verifying variance.",
            ),
        )

        assert decided_approval.status == ApprovalStatus.APPROVED.value
        assert decided_approval.decided_by_user_id == user_id
        assert decided_approval.approved_payload_hash is not None

        # Verify hash matches canonical serialization of proposed payload
        expected_hash = compute_payload_hash(action.proposed_payload_json)
        assert decided_approval.approved_payload_hash == expected_hash

        await session.refresh(action)
        assert action.status == ActionStatus.APPROVED.value

        # Attempting to decide again raises InvalidApprovalStateException
        with pytest.raises(InvalidApprovalStateException):
            await service.decide_approval(
                org_id,
                project_id,
                user_id,
                approval_id,
                ApprovalDecisionRequest(decision=ApprovalStatus.REJECTED),
            )


@pytest.mark.anyio
async def test_rejection_path_halts_execution(async_client: AsyncClient) -> None:
    """Test that human operator rejection transitions action to REJECTED and halts execution."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = GovernanceService(session, tenancy_service)

        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Reject Test Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-REJECT",
            finding_type="PRICE_VARIANCE",
            severity="LOW",
            status=FindingStatus.OPEN.value,
            summary="Variance within allowable tolerance",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="1050.00",
            threshold_value="1000.00",
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(finding_id=finding.id, include_rag_documents=False),
        )

        approvals = await service.list_approvals(org_id, project_id, user_id)
        approval = approvals[0]
        actions = await service.list_actions(org_id, project_id, user_id)
        action = actions[0]

        # Operator Rejects
        decided_approval = await service.decide_approval(
            org_id,
            project_id,
            user_id,
            approval.id,
            ApprovalDecisionRequest(
                decision=ApprovalStatus.REJECTED,
                rationale="Variance justified under approved promotional discount program.",
            ),
        )

        assert decided_approval.status == ApprovalStatus.REJECTED.value
        await session.refresh(action)
        assert action.status == ActionStatus.REJECTED.value

        # Attempting execution on rejected action must be blocked
        with pytest.raises(InvalidActionStateException):
            await service.execute_action(
                org_id,
                project_id,
                user_id,
                action.id,
                ActionExecuteRequest(idempotency_key=f"EXEC-{uuid.uuid4().hex}"),
            )


@pytest.mark.anyio
async def test_deterministic_action_execution_and_payload_integrity(async_client: AsyncClient) -> None:
    """Test action execution against SimulatedTargetAdapter, idempotency, and payload integrity protection."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = GovernanceService(session, tenancy_service)

        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Exec Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-DISPATCH-1",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.OPEN.value,
            summary="Price breach on INV-DISPATCH-1",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="25000.00",
            threshold_value="20000.00",
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(finding_id=finding.id, include_rag_documents=False),
        )

        approvals = await service.list_approvals(org_id, project_id, user_id)
        approval = approvals[0]
        actions = await service.list_actions(org_id, project_id, user_id)
        action = actions[0]

        # Approve
        await service.decide_approval(
            org_id,
            project_id,
            user_id,
            approval.id,
            ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED),
        )

        # 1. Execute action successfully
        idempotency_key = f"IDEM-KEY-{uuid.uuid4().hex}"
        execution = await service.execute_action(
            org_id,
            project_id,
            user_id,
            action.id,
            ActionExecuteRequest(idempotency_key=idempotency_key),
        )

        assert execution.status == "SUCCEEDED"
        assert execution.adapter_response_json is not None
        assert execution.adapter_response_json["operation"] == "HOLD_INVOICE"
        assert execution.adapter_response_json["applied_hold_code"] == "DISCREPANCY_HOLD_102"
        assert execution.dispatched_payload_hash == approval.approved_payload_hash

        await session.refresh(action)
        assert action.status == ActionStatus.EXECUTED.value

        # 2. Idempotency test: Replaying the exact same request returns existing execution
        replayed_exec = await service.execute_action(
            org_id,
            project_id,
            user_id,
            action.id,
            ActionExecuteRequest(idempotency_key=idempotency_key),
        )
        assert replayed_exec.id == execution.id

        # 3. Payload Integrity Tampering Test:
        # Create second action & approval, then tamper with action payload prior to dispatch
        finding2 = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-TAMPER",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.OPEN.value,
            summary="Tamper test",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="3000.00",
            threshold_value="2000.00",
        )
        session.add(finding2)
        await session.flush()
        await session.commit()

        await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(finding_id=finding2.id, include_rag_documents=False),
        )

        appr2 = (await service.list_approvals(org_id, project_id, user_id))[0]
        act2 = (await service.list_actions(org_id, project_id, user_id))[0]

        await service.decide_approval(
            org_id,
            project_id,
            user_id,
            appr2.id,
            ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED),
        )

        # Deliberately mutate action payload after approval
        act2.proposed_payload_json = {"invoice_id": "TAMPERED_INVOICE_ID", "amount": 999999.0}
        session.add(act2)
        await session.commit()

        # Dispatch must detect hash mismatch and raise PayloadIntegrityException
        with pytest.raises(PayloadIntegrityException):
            await service.execute_action(
                org_id,
                project_id,
                user_id,
                act2.id,
                ActionExecuteRequest(idempotency_key=f"IDEM-TAMPER-{uuid.uuid4().hex}"),
            )


@pytest.mark.anyio
async def test_append_only_audit_log_traceability(async_client: AsyncClient) -> None:
    """Test that all investigation, approval, and execution events produce immutable audit records."""
    user, _, org, project = await setup_test_org_and_project(async_client)
    org_id = uuid.UUID(org["id"])
    project_id = uuid.UUID(project["id"])
    user_id = uuid.UUID(user["id"])

    session_factory = get_session_factory()
    async with session_factory() as session:
        tenancy_service = TenancyService(session)
        service = GovernanceService(session, tenancy_service)

        monitor = Monitor(
            id=uuid.uuid4(),
            project_id=project_id,
            name="Audit Trace Monitor",
            target_type=MonitorTargetType.ENTITY.value,
            target_id="Invoice",
            status=MonitorStatus.ACTIVE.value,
        )
        session.add(monitor)
        await session.flush()

        finding = Finding(
            id=uuid.uuid4(),
            project_id=project_id,
            monitor_id=monitor.id,
            entity_type="Invoice",
            entity_id="INV-AUDIT",
            finding_type="PRICE_VARIANCE",
            severity="HIGH",
            status=FindingStatus.OPEN.value,
            summary="Audit trail test",
            deduplication_hash=uuid.uuid4().hex,
            observed_value="12000.00",
            threshold_value="10000.00",
        )
        session.add(finding)
        await session.flush()
        await session.commit()

        # Run investigation
        await service.create_investigation(
            org_id,
            project_id,
            user_id,
            InvestigationCreateRequest(finding_id=finding.id, include_rag_documents=False),
        )

        approvals = await service.list_approvals(org_id, project_id, user_id)
        actions = await service.list_actions(org_id, project_id, user_id)

        # Approve and execute
        await service.decide_approval(
            org_id,
            project_id,
            user_id,
            approvals[0].id,
            ApprovalDecisionRequest(decision=ApprovalStatus.APPROVED),
        )
        await service.execute_action(
            org_id,
            project_id,
            user_id,
            actions[0].id,
            ActionExecuteRequest(idempotency_key=f"AUDIT-KEY-{uuid.uuid4().hex}"),
        )

        # Query audit events
        audit_events, total = await service.list_audit_events(org_id, project_id, user_id)
        assert total >= 4
        action_types = [e.action_type for e in audit_events]
        assert "INVESTIGATION_COMPLETED" in action_types
        assert "ACTION_PROPOSED" in action_types
        assert "APPROVAL_GRANTED" in action_types
        assert "ACTION_EXECUTED" in action_types

        # Verify actor attribution
        for e in audit_events:
            assert e.actor_id == str(user_id)
            assert e.organization_id == org_id
            assert e.project_id == project_id
