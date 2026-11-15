"""Tests for Phase 5 Early AI Gateway and provider adapters."""

import pytest
from pydantic import BaseModel, Field

from corbel.ai.exceptions import (
    InvalidModelResponseException,
    ModelProviderAuthException,
    ModelProviderRateLimitException,
    ModelProviderTimeoutException,
    UnsupportedModelProviderException,
)
from corbel.ai.gateway import AIGateway
from corbel.ai.providers.mock import MockModelProvider
from corbel.ai.schemas import ModelRequest
from corbel.core.config import Settings


class SampleTargetSchema(BaseModel):
    summary: str
    score: float = Field(ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)


@pytest.mark.asyncio
async def test_mock_provider_text_generation() -> None:
    provider = MockModelProvider(default_model="mock-unit-test")
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(
        system_prompt="You are a test assistant.",
        user_prompt="Hello world query",
    )
    resp = await gateway.generate_text(req)

    assert resp.provider == "mock"
    assert resp.model == "mock-unit-test"
    assert resp.token_usage.total_tokens > 0
    assert resp.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_mock_provider_structured_output_success() -> None:
    provider = MockModelProvider()
    provider.register_mock_response(
        "sample query",
        {"summary": "Test summary", "score": 0.95, "tags": ["procurement", "po"]},
    )
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(
        system_prompt="Generate test JSON.",
        user_prompt="Run sample query now",
    )
    validated, resp = await gateway.generate_structured(req, SampleTargetSchema)

    assert isinstance(validated, SampleTargetSchema)
    assert validated.summary == "Test summary"
    assert validated.score == 0.95
    assert validated.tags == ["procurement", "po"]
    assert resp.structured_data == {"summary": "Test summary", "score": 0.95, "tags": ["procurement", "po"]}


@pytest.mark.asyncio
async def test_ai_gateway_timeout_handling() -> None:
    provider = MockModelProvider()
    provider.set_failure_mode("timeout")
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(system_prompt="sys", user_prompt="test timeout")
    with pytest.raises(ModelProviderTimeoutException) as exc:
        await gateway.generate_text(req)
    assert "timed out" in str(exc.value)


@pytest.mark.asyncio
async def test_ai_gateway_auth_failure_handling() -> None:
    provider = MockModelProvider()
    provider.set_failure_mode("auth_error")
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(system_prompt="sys", user_prompt="test auth error")
    with pytest.raises(ModelProviderAuthException) as exc:
        await gateway.generate_text(req)
    assert "Authentication failed" in str(exc.value)


@pytest.mark.asyncio
async def test_ai_gateway_rate_limit_handling() -> None:
    provider = MockModelProvider()
    provider.set_failure_mode("rate_limit")
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(system_prompt="sys", user_prompt="test rate limit")
    with pytest.raises(ModelProviderRateLimitException) as exc:
        await gateway.generate_text(req)
    assert "Rate limit exceeded" in str(exc.value)


@pytest.mark.asyncio
async def test_ai_gateway_invalid_json_handling() -> None:
    provider = MockModelProvider()
    provider.set_failure_mode("invalid_json")
    gateway = AIGateway()
    gateway.set_provider(provider)

    req = ModelRequest(system_prompt="sys", user_prompt="test invalid output")
    with pytest.raises(InvalidModelResponseException) as exc:
        await gateway.generate_structured(req, SampleTargetSchema)
    assert "Failed to parse JSON" in str(exc.value)


def test_ai_gateway_unsupported_provider() -> None:
    settings = Settings(AI_PROVIDER="unsupported_quantum_model_xyz")
    gateway = AIGateway(settings=settings)
    with pytest.raises(UnsupportedModelProviderException) as exc:
        gateway.get_provider()
    assert "not supported" in str(exc.value)
