"""Target-system adapters for Phase 9 Governed Execution.

Adheres strictly to ADR-012 (Procure-to-Pay as Initial Demonstrable Vertical Slice & Simulated Target Adapter).
Live external ERP mutations are strictly prohibited during Phase 9 validation.
"""

import abc
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from corbel.domains.governance.exceptions import TargetAdapterException
from corbel.domains.governance.models import ActionType

logger = logging.getLogger(__name__)


class TargetSystemAdapter(abc.ABC):
    """Abstract interface for enterprise target system adapters."""

    @property
    @abc.abstractmethod
    def adapter_name(self) -> str:
        """Identifier name of the adapter."""
        pass

    @abc.abstractmethod
    async def execute_action(
        self,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Execute a validated and approved action against the target system.

        Returns structured adapter response payload.
        """
        pass


class SimulatedTargetAdapter(TargetSystemAdapter):
    """Controlled simulated enterprise ERP/P2P system adapter.

    Enforces identical schemas, idempotency semantics, and response structures
    as a real ERP integration (e.g. SAP, NetSuite) without mutating external production.
    """

    def __init__(self, simulate_latency_ms: int = 0) -> None:
        self._simulate_latency_ms = simulate_latency_ms

    @property
    def adapter_name(self) -> str:
        return "SimulatedTargetAdapter"

    async def execute_action(
        self,
        action_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Dispatch simulated target operation."""
        # Check for simulated failure trigger in payload
        if payload.get("simulated_failure") is True:
            raise TargetAdapterException(
                self.adapter_name,
                "Simulated target connection timeout or ERP gateway failure."
            )

        now_iso = datetime.now(UTC).isoformat()
        digest = hashlib.sha256(f"{idempotency_key}:{action_type}".encode()).hexdigest()[:8].upper()

        if action_type == ActionType.HOLD_INVOICE.value:
            invoice_id = payload.get("invoice_id", "UNKNOWN-INV")
            hold_reason = payload.get("hold_reason", "PRICE_VARIANCE_DISCREPANCY")
            discrepancy = payload.get("discrepancy_amount_usd", 0.0)

            return {
                "adapter": self.adapter_name,
                "target_system": "SimulatedERP-P2P",
                "operation": "HOLD_INVOICE",
                "external_reference": f"ERP-HOLD-{digest}",
                "invoice_id": invoice_id,
                "hold_status": "PAYMENT_BLOCKED",
                "applied_hold_code": "DISCREPANCY_HOLD_102",
                "reason": hold_reason,
                "held_discrepancy_usd": discrepancy,
                "status": "APPLIED",
                "timestamp": now_iso,
                "acknowledged": True,
            }

        elif action_type == ActionType.REQUEST_CREDIT_MEMO.value:
            supplier_id = payload.get("supplier_id", "SUPP-001")
            invoice_id = payload.get("invoice_id", "INV-UNKNOWN")
            amount = payload.get("claim_amount_usd", 0.0)

            return {
                "adapter": self.adapter_name,
                "target_system": "SimulatedERP-P2P",
                "operation": "REQUEST_CREDIT_MEMO",
                "external_reference": f"ERP-CLM-{digest}",
                "supplier_id": supplier_id,
                "invoice_id": invoice_id,
                "dispatched_claim_usd": amount,
                "vendor_claim_status": "DISPATCHED_TO_VENDOR",
                "dispute_ticket_id": f"TKT-{uuid.uuid4().hex[:6].upper()}",
                "status": "APPLIED",
                "timestamp": now_iso,
                "acknowledged": True,
            }

        elif action_type == ActionType.FLAG_SUPPLIER_REVIEW.value:
            supplier_id = payload.get("supplier_id", "SUPP-001")
            review_reason = payload.get("reason", "RECURRING_DISCREPANCIES")

            return {
                "adapter": self.adapter_name,
                "target_system": "SimulatedERP-P2P",
                "operation": "FLAG_SUPPLIER_REVIEW",
                "external_reference": f"ERP-SRV-{digest}",
                "supplier_id": supplier_id,
                "supplier_hold_flag": "ACTIVE_PROCUREMENT_REVIEW",
                "reason": review_reason,
                "status": "APPLIED",
                "timestamp": now_iso,
                "acknowledged": True,
            }

        else:
            # Generic simulated action execution
            return {
                "adapter": self.adapter_name,
                "target_system": "SimulatedERP-P2P",
                "operation": action_type,
                "external_reference": f"ERP-GEN-{digest}",
                "payload_snapshot": payload,
                "status": "APPLIED",
                "timestamp": now_iso,
                "acknowledged": True,
            }
