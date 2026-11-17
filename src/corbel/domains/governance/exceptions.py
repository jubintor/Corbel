"""Domain-specific exceptions for Phase 9: Governed Investigation, Approvals & RAG."""

import uuid


class GovernanceException(Exception):
    """Base exception for all governance and investigation errors."""

    def __init__(self, message: str, status_code: int = 400, error_code: str = "GOVERNANCE_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class InvestigationNotFoundException(GovernanceException):
    """Raised when an investigation is not found or does not belong to the requested project."""

    def __init__(self, investigation_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Investigation '{investigation_id}' not found in active project workspace.",
            status_code=404,
            error_code="INVESTIGATION_NOT_FOUND",
        )


class FindingNotFoundException(GovernanceException):
    """Raised when a finding is not found for investigation initialization."""

    def __init__(self, finding_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Finding '{finding_id}' not found in active project workspace.",
            status_code=404,
            error_code="FINDING_NOT_FOUND",
        )


class DocumentNotFoundException(GovernanceException):
    """Raised when a RAG document is not found."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Document '{document_id}' not found in active project workspace.",
            status_code=404,
            error_code="DOCUMENT_NOT_FOUND",
        )


class RecommendationNotFoundException(GovernanceException):
    """Raised when a recommendation is not found."""

    def __init__(self, recommendation_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Recommendation '{recommendation_id}' not found.",
            status_code=404,
            error_code="RECOMMENDATION_NOT_FOUND",
        )


class ActionNotFoundException(GovernanceException):
    """Raised when an action is not found."""

    def __init__(self, action_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Action '{action_id}' not found in active project workspace.",
            status_code=404,
            error_code="ACTION_NOT_FOUND",
        )


class ApprovalNotFoundException(GovernanceException):
    """Raised when an approval gate is not found."""

    def __init__(self, approval_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Approval '{approval_id}' not found.",
            status_code=404,
            error_code="APPROVAL_NOT_FOUND",
        )


class UnauthorizedApprovalException(GovernanceException):
    """Raised when an unauthenticated actor or unauthorized role attempts to decide an approval."""

    def __init__(self, message: str = "User lacks required authorization role to decide this approval.") -> None:
        super().__init__(
            message,
            status_code=403,
            error_code="UNAUTHORIZED_APPROVAL",
        )


class InvalidApprovalStateException(GovernanceException):
    """Raised when attempting to decide an approval that is not in PENDING state."""

    def __init__(self, current_status: str) -> None:
        super().__init__(
            f"Cannot decide approval: Current status is '{current_status}', must be 'PENDING'.",
            status_code=409,
            error_code="INVALID_APPROVAL_STATE",
        )


class InvalidActionStateException(GovernanceException):
    """Raised when attempting to execute an action that is not in APPROVED state."""

    def __init__(self, current_status: str) -> None:
        super().__init__(
            f"Cannot execute action: Current status is '{current_status}', must be 'APPROVED'.",
            status_code=409,
            error_code="INVALID_ACTION_STATE",
        )


class PayloadIntegrityException(GovernanceException):
    """Raised when dispatched payload hash does not match the approved canonical payload hash."""

    def __init__(
        self,
        approved_hash: str,
        dispatched_hash: str,
    ) -> None:
        super().__init__(
            f"Payload integrity violation: Dispatched payload hash '{dispatched_hash}' "
            f"does not match approved payload hash '{approved_hash}'. Execution aborted.",
            status_code=400,
            error_code="PAYLOAD_INTEGRITY_MISMATCH",
        )


class DuplicateExecutionException(GovernanceException):
    """Raised when an action has already been executed under an idempotency key."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"Action execution with idempotency key '{idempotency_key}' already completed.",
            status_code=409,
            error_code="DUPLICATE_EXECUTION",
        )


class TargetAdapterException(GovernanceException):
    """Raised when target adapter fails during simulated or real external execution."""

    def __init__(self, adapter_name: str, details: str) -> None:
        super().__init__(
            f"Target adapter '{adapter_name}' execution failed: {details}",
            status_code=502,
            error_code="TARGET_ADAPTER_ERROR",
        )
