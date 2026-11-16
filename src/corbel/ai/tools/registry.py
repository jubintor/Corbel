"""Validated, strongly-typed tool registry for Corbel bounded state machines."""

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from corbel.ai.exceptions import (
    ToolNotFoundException,
    ToolPermissionException,
    ToolValidationException,
)
from corbel.ai.schemas import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)


class RegisteredTool:
    """Internal metadata and execution wrapper for a registered tool."""

    def __init__(
        self,
        name: str,
        description: str,
        parameter_model: type[BaseModel],
        handler: Callable[..., Any] | Callable[..., Awaitable[Any]],
        is_read_only: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.parameter_model = parameter_model
        self.handler = handler
        self.is_read_only = is_read_only

    def to_definition(self) -> ToolDefinition:
        """Export tool metadata into standard ToolDefinition schema."""
        schema = self.parameter_model.model_json_schema()
        properties = schema.get("properties", {})
        required_fields = set(schema.get("required", []))

        params = []
        for prop_name, prop_data in properties.items():
            params.append(
                ToolParameter(
                    name=prop_name,
                    type=str(prop_data.get("type", "any")),
                    description=prop_data.get("description", ""),
                    required=prop_name in required_fields,
                    default=prop_data.get("default"),
                )
            )

        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=params,
            is_read_only=self.is_read_only,
            schema_dict=schema,
        )

    async def execute(self, arguments: dict[str, Any]) -> Any:
        """Validate input arguments via Pydantic model and execute handler."""
        try:
            validated_args = self.parameter_model.model_validate(arguments)
        except ValidationError as e:
            err_details = "; ".join(f"{err['loc']}: {err['msg']}" for err in e.errors())
            raise ToolValidationException(self.name, err_details) from e

        # Call handler (sync or async)
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(validated_args)
        return self.handler(validated_args)


class ToolRegistry:
    """Thread-safe registry managing permitted analytical tools for AI state machines."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameter_model: type[BaseModel],
        handler: Callable[..., Any] | Callable[..., Awaitable[Any]],
        is_read_only: bool = True,
    ) -> None:
        """Register a new strongly-typed tool with parameter model."""
        self._tools[name] = RegisteredTool(
            name=name,
            description=description,
            parameter_model=parameter_model,
            handler=handler,
            is_read_only=is_read_only,
        )
        logger.debug("Registered tool: %s (read_only=%s)", name, is_read_only)

    def get_tool(self, name: str) -> RegisteredTool:
        """Retrieve registered tool by name."""
        tool = self._tools.get(name)
        if not tool:
            raise ToolNotFoundException(name)
        return tool

    def list_tools(self, allowed_tools: list[str] | None = None) -> list[ToolDefinition]:
        """List registered tools, optionally filtered by an active allowlist."""
        tools_list = list(self._tools.values())
        if allowed_tools is not None:
            allowed_set = set(allowed_tools)
            tools_list = [t for t in tools_list if t.name in allowed_set]
        return [t.to_definition() for t in tools_list]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        allowed_tools: list[str] | None = None,
        require_read_only: bool = True,
    ) -> Any:
        """Validate permissions and execute registered tool."""
        if allowed_tools is not None and name not in allowed_tools:
            raise ToolPermissionException(
                name, f"Tool is not permitted in the current state machine allowlist ({allowed_tools})."
            )

        tool = self.get_tool(name)
        if require_read_only and not tool.is_read_only:
            raise ToolPermissionException(
                name, "Analytical state machines are strictly restricted to read-only tools."
            )

        logger.info("Executing tool: %s with args: %s", name, arguments)
        return await tool.execute(arguments)


# -----------------------------------------------------------------------------
# Default Tool Implementations for Procure-to-Pay (P2P) Workflows
# -----------------------------------------------------------------------------


class InspectSchemaArgs(BaseModel):
    dataset_name: str
    target_columns: list[str] | None = None


class ProfileDistributionArgs(BaseModel):
    dataset_name: str
    column_name: str


class RetrieveEventsArgs(BaseModel):
    case_identifier: str
    limit: int = 50


class CorrelateObjectsArgs(BaseModel):
    entity_type: str
    entity_id: str


class CalculateVarianceArgs(BaseModel):
    invoice_amount: float
    po_amount: float
    tolerance_pct: float = 0.5


class CheckSlaDurationArgs(BaseModel):
    duration_seconds: float
    sla_seconds: float


def _default_inspect_schema(args: InspectSchemaArgs) -> dict[str, Any]:
    return {
        "dataset_name": args.dataset_name,
        "columns": [
            {"name": "po_number", "type": "STRING", "null_ratio": 0.0},
            {"name": "supplier_id", "type": "STRING", "null_ratio": 0.0},
            {"name": "amount", "type": "NUMBER", "null_ratio": 0.01},
            {"name": "order_date", "type": "DATETIME", "null_ratio": 0.0},
        ],
        "row_count": 1250,
    }


def _default_profile_distribution(args: ProfileDistributionArgs) -> dict[str, Any]:
    return {
        "dataset_name": args.dataset_name,
        "column_name": args.column_name,
        "min": 100.0,
        "max": 50000.0,
        "mean": 12450.50,
        "null_count": 2,
    }


def _default_retrieve_events(args: RetrieveEventsArgs) -> dict[str, Any]:
    return {
        "case_identifier": args.case_identifier,
        "events": [
            {"activity": "PO Issued", "timestamp": "2026-11-01T08:00:00Z"},
            {"activity": "Goods Received", "timestamp": "2026-11-05T14:30:00Z"},
            {"activity": "Invoice Received", "timestamp": "2026-11-06T09:15:00Z"},
        ],
        "count": 3,
    }


def _default_correlate_objects(args: CorrelateObjectsArgs) -> dict[str, Any]:
    return {
        "entity_type": args.entity_type,
        "entity_id": args.entity_id,
        "correlated_records": [
            {"type": "PurchaseOrder", "id": "PO-10023", "amount": 15000.00},
            {"type": "GoodsReceipt", "id": "GR-9021", "received_date": "2026-11-05"},
            {"type": "Invoice", "id": "INV-7844", "billed_amount": 16250.00},
        ],
    }


def _default_calculate_variance(args: CalculateVarianceArgs) -> dict[str, Any]:
    delta = args.invoice_amount - args.po_amount
    variance_pct = (delta / args.po_amount * 100.0) if args.po_amount else 0.0
    breach = abs(variance_pct) > args.tolerance_pct
    return {
        "invoice_amount": args.invoice_amount,
        "po_amount": args.po_amount,
        "delta_amount": round(delta, 2),
        "variance_pct": round(variance_pct, 4),
        "tolerance_pct": args.tolerance_pct,
        "is_breach": breach,
    }


def _default_check_sla_duration(args: CheckSlaDurationArgs) -> dict[str, Any]:
    delay = max(0.0, args.duration_seconds - args.sla_seconds)
    is_breached = delay > 0.0
    return {
        "actual_duration_seconds": args.duration_seconds,
        "target_sla_seconds": args.sla_seconds,
        "delay_seconds": round(delay, 2),
        "is_breached": is_breached,
    }


_global_registry: ToolRegistry | None = None


def get_default_tool_registry() -> ToolRegistry:
    """Retrieve the singleton default tool registry initialized with standard P2P analytical tools."""
    global _global_registry
    if _global_registry is None:
        reg = ToolRegistry()
        reg.register(
            name="inspect_schema",
            description="Inspect dataset column definitions, types, and null ratios.",
            parameter_model=InspectSchemaArgs,
            handler=_default_inspect_schema,
            is_read_only=True,
        )
        reg.register(
            name="profile_distribution",
            description="Retrieve statistical distribution metrics for a dataset column.",
            parameter_model=ProfileDistributionArgs,
            handler=_default_profile_distribution,
            is_read_only=True,
        )
        reg.register(
            name="retrieve_events",
            description="Retrieve process execution history events for an operational case ID.",
            parameter_model=RetrieveEventsArgs,
            handler=_default_retrieve_events,
            is_read_only=True,
        )
        reg.register(
            name="correlate_objects",
            description="Find related business objects across purchase orders, goods receipts, and invoices.",
            parameter_model=CorrelateObjectsArgs,
            handler=_default_correlate_objects,
            is_read_only=True,
        )
        reg.register(
            name="calculate_variance",
            description="Deterministically calculate financial and percentage price/quantity variances.",
            parameter_model=CalculateVarianceArgs,
            handler=_default_calculate_variance,
            is_read_only=True,
        )
        reg.register(
            name="check_sla_duration",
            description="Calculate cycle-time duration and SLA breach delays deterministically.",
            parameter_model=CheckSlaDurationArgs,
            handler=_default_check_sla_duration,
            is_read_only=True,
        )
        _global_registry = reg
    return _global_registry
