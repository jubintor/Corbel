"""Deterministic Mock Model Provider for automated testing and local offline runs."""

import json
import re
import time
from typing import Any, TypeVar

from pydantic import BaseModel

from corbel.ai.exceptions import (
    ModelProviderAuthException,
    ModelProviderRateLimitException,
    ModelProviderTimeoutException,
)
from corbel.ai.providers.base import BaseAIProvider
from corbel.ai.schemas import ModelRequest, ModelResponse, TokenUsage

T = TypeVar("T", bound=BaseModel)


class MockModelProvider(BaseAIProvider):
    """Deterministic, provider-neutral fake provider for offline testing."""

    def __init__(self, default_model: str = "mock-corbel-model") -> None:
        self._default_model = default_model
        self._failure_mode: str | None = None
        self._registered_responses: dict[str, Any] = {}

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def default_model(self) -> str:
        return self._default_model

    def set_failure_mode(self, mode: str | None) -> None:
        """Configure intentional failure mode: 'timeout', 'auth_error', 'rate_limit', 'invalid_json'."""
        self._failure_mode = mode

    def register_mock_response(self, keyword: str, response: dict[str, Any] | str) -> None:
        """Register a specific mock response when keyword appears in user prompt."""
        self._registered_responses[keyword.lower()] = response

    def clear_registrations(self) -> None:
        """Clear registered responses and failure modes."""
        self._registered_responses.clear()
        self._failure_mode = None

    async def generate_text(self, request: ModelRequest) -> ModelResponse:
        start_time = time.perf_counter()

        if self._failure_mode == "timeout":
            raise ModelProviderTimeoutException("mock", 30.0)
        elif self._failure_mode == "auth_error":
            raise ModelProviderAuthException("mock")
        elif self._failure_mode == "rate_limit":
            raise ModelProviderRateLimitException("mock")

        prompt_tokens = len(request.user_prompt.split()) + len(request.system_prompt.split())

        # Check registered responses
        content: str
        user_lower = request.user_prompt.lower()
        matched = None
        for k, v in self._registered_responses.items():
            if k in user_lower:
                matched = v
                break

        if self._failure_mode == "invalid_json":
            content = "This is definitely NOT valid JSON content {{{ {"
        elif matched is not None:
            content = json.dumps(matched) if isinstance(matched, dict) else str(matched)
        else:
            # Deterministic heuristic generator for Natural Language Queries
            content = self._heuristic_query_response(request.user_prompt)

        completion_tokens = len(content.split())
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return ModelResponse(
            provider=self.provider_name,
            model=self.default_model,
            content=content,
            token_usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
            latency_ms=latency_ms,
        )

    async def generate_structured(
        self,
        request: ModelRequest,
        schema_class: type[T],
    ) -> tuple[T, ModelResponse]:
        raw_resp = await self.generate_text(request)
        payload = self.extract_json_payload(raw_resp.content)
        validated = self.validate_structured_payload(payload, schema_class)
        raw_resp.structured_data = payload
        return validated, raw_resp

    def _heuristic_query_response(self, prompt: str) -> str:
        """Heuristically generate valid StructuredQueryRequest JSON from natural language prompt."""
        p_lower = prompt.lower()

        # Identify entity
        entity_name = "PurchaseOrder"
        if "supplier" in p_lower:
            entity_name = "Supplier"
        elif "invoice" in p_lower:
            entity_name = "Invoice"
        elif "goods" in p_lower or "receipt" in p_lower:
            entity_name = "GoodsReceipt"

        filters: list[dict[str, Any]] = []

        # Check numeric filter (e.g. > 10000 or > $10,000)
        num_gt_match = re.search(r"(?:>|exceeding|greater than|more than)\s*\$?([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)", p_lower)
        if num_gt_match:
            val_str = num_gt_match.group(1).replace(",", "")
            val_num = float(val_str) if "." in val_str else int(val_str)
            target_field = (
                "total_amount"
                if entity_name == "PurchaseOrder"
                else ("invoice_amount" if entity_name == "Invoice" else "amount")
            )
            filters.append({"field": target_field, "operator": "gt", "value": val_num})

        # Check status filter (e.g. status OPEN, PENDING, COMPLETED, DELIVERED)
        status_match = re.search(r"status\s+(?:is\s+|equal(?:s)?\s+to\s+)?['\"]?([A-Za-z_]+)['\"]?", p_lower)
        if status_match:
            status_val = status_match.group(1).upper()
            filters.append({"field": "status", "operator": "eq", "value": status_val})

        # Check equality filter (e.g. supplier X or po_number X)
        po_match = re.search(r"po[_\s-]?number\s+(?:is\s+|equal(?:s)?\s+to\s+)?['\"]?([A-Za-z0-9_-]+)['\"]?", p_lower)
        if po_match:
            filters.append({"field": "po_number", "operator": "eq", "value": po_match.group(1)})

        limit = 50
        limit_match = re.search(r"limit\s+(\d+)", p_lower)
        if limit_match:
            limit = int(limit_match.group(1))

        query_payload = {
            "entity_name": entity_name,
            "fields": [],
            "filters": filters,
            "sorts": [],
            "limit": limit,
            "offset": 0,
        }
        return json.dumps(query_payload)
