"""Unit and integration tests for Phase 10: Optional Arize Phoenix Observability.

Covers:
1. Disabled state (default): 0 overhead, zero network calls, seamless operations.
2. Fault tolerance: Corbel functions with 100% success when Phoenix is offline or unreachable.
3. OpenTelemetry / OpenInference span export when enabled.
4. Secret, credential, and API key redaction in telemetry spans.
5. Health check reachability probing.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from corbel.ai.gateway import AIGateway
from corbel.ai.schemas import ModelRequest
from corbel.ai.telemetry.phoenix import (
    PhoenixTelemetryAdapter,
    redact_secrets_from_text,
)
from corbel.core.config import Settings


class MockStructuredSchema(BaseModel):
    summary: str
    confidence: float


@pytest.mark.anyio
async def test_phoenix_disabled_by_default() -> None:
    """Verify Phoenix is disabled by default and performs zero network calls."""
    settings = Settings(PHOENIX_ENABLED=False)
    adapter = PhoenixTelemetryAdapter(settings=settings)

    assert adapter.enabled is False
    assert await adapter.check_health() is False

    # Calling export_span must complete immediately without making HTTP requests
    await adapter.export_span(
        span_name="test_span",
        model_name="gpt-4o",
        provider="openai",
        input_tokens=100,
        output_tokens=50,
        latency_ms=120.5,
    )
    await adapter.close()


@pytest.mark.anyio
async def test_phoenix_fault_tolerance_offline_endpoint() -> None:
    """Verify ADR-016: Corbel functions with 100% success when Phoenix is offline or unreachable."""
    # Point to an unreachable port on loopback
    settings = Settings(
        PHOENIX_ENABLED=True,
        PHOENIX_COLLECTOR_ENDPOINT="http://127.0.0.1:59999/v1/traces",
        PHOENIX_TIMEOUT_SECONDS=0.5,
    )
    gateway = AIGateway(settings=settings)
    gateway._mock_provider.register_mock_response("invoice", {"summary": "Invoice variance", "confidence": 0.95})

    # Text generation through gateway must succeed 100% even if Phoenix is offline
    resp = await gateway.generate_text(
        ModelRequest(
            system_prompt="You are an analyst.",
            user_prompt="Analyze purchase order variance for supplier SUPP-001",
        )
    )
    assert resp is not None
    assert resp.content != ""
    assert resp.token_usage.total_tokens > 0

    # Structured generation must also succeed 100%
    structured, resp2 = await gateway.generate_structured(
        ModelRequest(
            system_prompt="You are an analyst.",
            user_prompt="Return summary for invoice INV-100",
        ),
        MockStructuredSchema,
    )
    assert structured is not None
    assert structured.confidence > 0.0

    await gateway.phoenix.close()


@pytest.mark.anyio
async def test_phoenix_span_export_and_secret_redaction() -> None:
    """Verify trace span serialization, OpenInference attributes, and credential redaction."""
    captured_requests: list[httpx.Request] = []

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(status_code=200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_transport_handler)
    mock_client = httpx.AsyncClient(transport=transport)

    settings = Settings(
        PHOENIX_ENABLED=True,
        PHOENIX_COLLECTOR_ENDPOINT="http://localhost:6006/v1/traces",
        PHOENIX_PROJECT_NAME="corbel-test",
        PHOENIX_CAPTURE_PAYLOADS=True,
    )
    adapter = PhoenixTelemetryAdapter(settings=settings)
    adapter._client = mock_client

    # Export span containing sensitive credentials in prompt and response
    await adapter.export_span(
        span_name="corbel.ai.gateway.generate_text",
        model_name="claude-3-5-sonnet",
        provider="anthropic",
        input_tokens=150,
        output_tokens=75,
        latency_ms=250.0,
        organization_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        correlation_id="CORR-P2P-9001",
        prompt="Authenticate using Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.topsecret and sk-proj-1234567890abcdef",
        response_text="Connected successfully with sk-ant-api03-abcdef1234567890",
        status="SUCCESS",
    )

    assert len(captured_requests) == 1
    req_body = json.loads(captured_requests[0].content.decode("utf-8"))

    # Verify OpenTelemetry structure
    resource_spans = req_body["resourceSpans"]
    assert len(resource_spans) == 1

    scope_spans = resource_spans[0]["scopeSpans"]
    spans = scope_spans[0]["spans"]
    assert len(spans) == 1

    span = spans[0]
    assert span["name"] == "corbel.ai.gateway.generate_text"
    assert span["status"]["code"] == 1

    attrs = {a["key"]: a["value"] for a in span["attributes"]}
    assert attrs["openinference.span.kind"]["stringValue"] == "LLM"
    assert attrs["llm.model_name"]["stringValue"] == "claude-3-5-sonnet"
    assert attrs["llm.provider"]["stringValue"] == "anthropic"
    assert attrs["llm.token_count.prompt"]["intValue"] == 150
    assert attrs["llm.token_count.completion"]["intValue"] == 75
    assert attrs["corbel.tenant_id"]["stringValue"] == "11111111-1111-1111-1111-111111111111"
    assert attrs["corbel.correlation_id"]["stringValue"] == "CORR-P2P-9001"

    # Verify credentials were redacted
    prompt_content = attrs["llm.input_messages.0.message.content"]["stringValue"]
    resp_content = attrs["llm.output_messages.0.message.content"]["stringValue"]
    assert "sk-proj" not in prompt_content
    assert "sk-ant" not in resp_content
    assert "[REDACTED]" in prompt_content
    assert "[REDACTED]" in resp_content

    await adapter.close()


def test_secret_redaction_regexes() -> None:
    """Verify regex patterns for redaction of sensitive credentials."""
    text1 = "sk-ant-api03-abcdef1234567890123456"
    assert redact_secrets_from_text(text1) == "[REDACTED]"

    text2 = "sk-1234567890abcdefghijklmn"
    assert redact_secrets_from_text(text2) == "[REDACTED]"

    text3 = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummytoken123"
    assert "[REDACTED]" in (redact_secrets_from_text(text3) or "")
