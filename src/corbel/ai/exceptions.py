"""Exceptions for the Corbel AI Gateway."""

from typing import Any

from corbel.core.exceptions import CorbelException


class AIGatewayException(CorbelException):
    """Base exception for AI Gateway operations."""

    def __init__(
        self,
        message: str,
        error_code: str = "AI_GATEWAY_ERROR",
        status_code: int = 502,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status_code,
            details=details,
        )


class ModelProviderAuthException(AIGatewayException):
    """Raised when authentication with the AI provider fails."""

    def __init__(self, provider: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Authentication failed for AI provider '{provider}'. Please check API key configuration.",
            error_code="AI_PROVIDER_AUTH_ERROR",
            status_code=502,
            details=details,
        )


class ModelProviderTimeoutException(AIGatewayException):
    """Raised when an AI provider call times out."""

    def __init__(self, provider: str, timeout_seconds: float) -> None:
        super().__init__(
            message=f"AI provider '{provider}' request timed out after {timeout_seconds}s.",
            error_code="AI_PROVIDER_TIMEOUT",
            status_code=504,
            details={"provider": provider, "timeout_seconds": timeout_seconds},
        )


class ModelProviderRateLimitException(AIGatewayException):
    """Raised when an AI provider returns rate limit errors."""

    def __init__(self, provider: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Rate limit exceeded for AI provider '{provider}'.",
            error_code="AI_PROVIDER_RATE_LIMIT",
            status_code=429,
            details=details,
        )


class InvalidModelResponseException(AIGatewayException):
    """Raised when an AI provider returns invalid, malformed, or unparseable output."""

    def __init__(self, message: str, raw_response: str | None = None) -> None:
        details: dict[str, Any] = {}
        if raw_response:
            # Truncate raw response to prevent log bloat
            details["raw_sample"] = raw_response[:500]
        super().__init__(
            message=message,
            error_code="AI_INVALID_MODEL_RESPONSE",
            status_code=502,
            details=details,
        )


class UnsupportedModelProviderException(AIGatewayException):
    """Raised when an unsupported AI provider is requested."""

    def __init__(self, provider: str, supported: list[str]) -> None:
        super().__init__(
            message=f"AI provider '{provider}' is not supported. Supported providers: {', '.join(supported)}.",
            error_code="AI_UNSUPPORTED_PROVIDER",
            status_code=400,
            details={"provider": provider, "supported_providers": supported},
        )


# -----------------------------------------------------------------------------
# Phase 8: Tool & State Machine Exceptions
# -----------------------------------------------------------------------------


class ToolException(CorbelException):
    """Base exception for tool execution errors."""

    def __init__(
        self,
        message: str,
        error_code: str = "TOOL_ERROR",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=status_code, details=details)


class ToolNotFoundException(ToolException):
    """Raised when a requested tool is not found in the registry."""

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            message=f"Tool '{tool_name}' is not registered in the tool registry.",
            error_code="TOOL_NOT_FOUND",
            status_code=404,
            details={"tool_name": tool_name},
        )


class ToolValidationException(ToolException):
    """Raised when tool arguments fail Pydantic validation."""

    def __init__(self, tool_name: str, errors: str) -> None:
        super().__init__(
            message=f"Invalid arguments for tool '{tool_name}': {errors}",
            error_code="TOOL_VALIDATION_ERROR",
            status_code=422,
            details={"tool_name": tool_name, "errors": errors},
        )


class ToolPermissionException(ToolException):
    """Raised when a state machine attempts to invoke a tool outside its allowed scope."""

    def __init__(self, tool_name: str, reason: str = "Tool is not in the active state machine allowlist.") -> None:
        super().__init__(
            message=f"Permission denied for tool '{tool_name}': {reason}",
            error_code="TOOL_PERMISSION_DENIED",
            status_code=403,
            details={"tool_name": tool_name, "reason": reason},
        )


class TaskExecutionException(CorbelException):
    """Base exception for durable task execution failures."""

    def __init__(
        self,
        message: str,
        error_code: str = "TASK_EXECUTION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=status_code, details=details)


class TaskNotFoundException(TaskExecutionException):
    """Raised when a durable background task cannot be found."""

    def __init__(self, task_id: str) -> None:
        super().__init__(
            message=f"Task '{task_id}' not found.",
            error_code="TASK_NOT_FOUND",
            status_code=404,
            details={"task_id": task_id},
        )


class TaskLeaseExpiredException(TaskExecutionException):
    """Raised when a worker attempts to mutate or heartbeat a task without a valid active lease."""

    def __init__(
        self,
        task_id: str,
        worker_id: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        msg = f"Task lease error on '{task_id}' for worker '{worker_id}'."
        if reason:
            msg += f" {reason}"
        det: dict[str, Any] = {"task_id": task_id, "worker_id": worker_id}
        if details:
            det.update(details)
        super().__init__(
            message=msg,
            error_code="TASK_LEASE_EXPIRED",
            status_code=409,
            details=det,
        )


class WorkflowExecutionException(CorbelException):
    """Base exception for bounded state machine workflow failures."""

    def __init__(
        self,
        message: str,
        error_code: str = "WORKFLOW_EXECUTION_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message=message, error_code=error_code, status_code=status_code, details=details)


class WorkflowNotFoundException(WorkflowExecutionException):
    """Raised when a workflow execution record is not found."""

    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            message=f"Workflow execution '{workflow_id}' not found.",
            error_code="WORKFLOW_NOT_FOUND",
            status_code=404,
            details={"workflow_id": workflow_id},
        )


class WorkflowBudgetExceededException(WorkflowExecutionException):
    """Raised when an analytical workflow exceeds its max steps, token budget, or cost limit."""

    def __init__(self, reason: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message=f"Workflow execution halted: {reason}",
            error_code="WORKFLOW_BUDGET_EXCEEDED",
            status_code=400,
            details=details,
        )


class PromptDefinitionNotFoundException(CorbelException):
    """Raised when a prompt definition cannot be found."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            message=f"Prompt definition '{identifier}' not found.",
            error_code="PROMPT_DEFINITION_NOT_FOUND",
            status_code=404,
            details={"identifier": identifier},
        )


class PromptVersionNotFoundException(CorbelException):
    """Raised when a prompt version cannot be found."""

    def __init__(self, identifier: str) -> None:
        super().__init__(
            message=f"Prompt version '{identifier}' not found.",
            error_code="PROMPT_VERSION_NOT_FOUND",
            status_code=404,
            details={"identifier": identifier},
        )


class PromptLifecycleException(CorbelException):
    """Raised when an invalid prompt lifecycle state transition is attempted."""

    def __init__(self, current_state: str, target_state: str, reason: str | None = None) -> None:
        msg = f"Cannot transition prompt from '{current_state}' to '{target_state}'."
        if reason:
            msg += f" {reason}"
        super().__init__(
            message=msg,
            error_code="PROMPT_LIFECYCLE_INVALID_TRANSITION",
            status_code=400,
            details={"current_state": current_state, "target_state": target_state, "reason": reason},
        )


class EvaluationDatasetNotFoundException(CorbelException):
    """Raised when an evaluation dataset cannot be found."""

    def __init__(self, dataset_id: str) -> None:
        super().__init__(
            message=f"Evaluation dataset '{dataset_id}' not found.",
            error_code="EVALUATION_DATASET_NOT_FOUND",
            status_code=404,
            details={"dataset_id": dataset_id},
        )


class EvaluationRunNotFoundException(CorbelException):
    """Raised when an evaluation run cannot be found."""

    def __init__(self, run_id: str) -> None:
        super().__init__(
            message=f"Evaluation run '{run_id}' not found.",
            error_code="EVALUATION_RUN_NOT_FOUND",
            status_code=404,
            details={"run_id": run_id},
        )
