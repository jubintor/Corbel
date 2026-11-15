"""HTTP-level unit tests for OpenAI and Anthropic cloud model providers."""

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, Field

from corbel.ai.exceptions import (
    AIGatewayException,
    InvalidModelResponseException,
    ModelProviderAuthException,
    ModelProviderRateLimitException,
    ModelProviderTimeoutException,
)
from corbel.ai.providers.anthropic import AnthropicModelProvider
from corbel.ai.providers.openai import OpenAIModelProvider
from corbel.ai.schemas import ModelRequest


class TargetSchema(BaseModel):
    decision: str
    confidence: float = Field(ge=0.0, le=1.0)
    items: list[str] = Field(default_factory=list)


# ==============================================================================
# OpenAI Provider Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_openai_provider_endpoint_and_headers() -> None:
    captured_request: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["method"] = request.method
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [{"message": {"content": "Hello from mock OpenAI"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test-secret-key", default_model="gpt-4o", transport=transport)

    req = ModelRequest(system_prompt="System instructions", user_prompt="User query prompt")
    resp = await provider.generate_text(req)

    assert captured_request["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured_request["method"] == "POST"
    assert captured_request["headers"]["authorization"] == "Bearer sk-test-secret-key"
    assert captured_request["headers"]["content-type"] == "application/json"
    assert captured_request["body"]["model"] == "gpt-4o"
    assert captured_request["body"]["messages"][0] == {"role": "system", "content": "System instructions"}
    assert captured_request["body"]["messages"][1] == {"role": "user", "content": "User query prompt"}
    assert resp.content == "Hello from mock OpenAI"
    assert resp.token_usage.prompt_tokens == 12
    assert resp.token_usage.completion_tokens == 8
    assert resp.token_usage.total_tokens == 20


@pytest.mark.asyncio
async def test_openai_provider_structured_generation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"decision": "APPROVE", "confidence": 0.98, "items": ["item1", "item2"]}
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 50, "completion_tokens": 25},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test", transport=transport)

    req = ModelRequest(system_prompt="Evaluate decision.", user_prompt="Evaluate request #123")
    validated, resp = await provider.generate_structured(req, TargetSchema)

    assert isinstance(validated, TargetSchema)
    assert validated.decision == "APPROVE"
    assert validated.confidence == 0.98
    assert validated.items == ["item1", "item2"]
    assert resp.token_usage.total_tokens == 75


@pytest.mark.asyncio
async def test_openai_provider_auth_error_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key provided"}})

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-bad-key", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderAuthException) as exc:
        await provider.generate_text(req)
    assert "Authentication failed" in str(exc.value)
    # Ensure secret API key is not leaked in exception message
    assert "sk-bad-key" not in str(exc.value)


@pytest.mark.asyncio
async def test_openai_provider_rate_limit_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "Rate limit reached"}})

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderRateLimitException) as exc:
        await provider.generate_text(req)
    assert "Rate limit exceeded" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_provider_timeout_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out after 30s")

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderTimeoutException) as exc:
        await provider.generate_text(req)
    assert "timed out" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_provider_network_error_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to connect to api.openai.com")

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(AIGatewayException) as exc:
        await provider.generate_text(req)
    assert "Network error" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_provider_missing_api_key() -> None:
    provider = OpenAIModelProvider(api_key="")
    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderAuthException) as exc:
        await provider.generate_text(req)
    assert "Authentication failed" in str(exc.value)
    assert exc.value.details.get("reason") == "OPENAI_API_KEY is not configured"


@pytest.mark.asyncio
async def test_openai_provider_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Not JSON at all! Just raw plain text"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = OpenAIModelProvider(api_key="sk-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(InvalidModelResponseException):
        await provider.generate_structured(req, TargetSchema)


# ==============================================================================
# Anthropic Provider Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_anthropic_provider_endpoint_and_headers() -> None:
    captured_request: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["method"] = request.method
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "model": "claude-3-5-sonnet-20241022",
                "content": [{"type": "text", "text": "Hello from mock Anthropic"}],
                "usage": {"input_tokens": 15, "output_tokens": 10},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test-secret-key", transport=transport)

    req = ModelRequest(system_prompt="System instructions", user_prompt="User query prompt")
    resp = await provider.generate_text(req)

    assert captured_request["url"] == "https://api.anthropic.com/v1/messages"
    assert captured_request["method"] == "POST"
    assert captured_request["headers"]["x-api-key"] == "ant-test-secret-key"
    assert captured_request["headers"]["anthropic-version"] == "2023-06-01"
    assert captured_request["headers"]["content-type"] == "application/json"
    assert captured_request["body"]["system"] == "System instructions"
    assert captured_request["body"]["messages"] == [{"role": "user", "content": "User query prompt"}]
    assert resp.content == "Hello from mock Anthropic"
    assert resp.token_usage.prompt_tokens == 15
    assert resp.token_usage.completion_tokens == 10
    assert resp.token_usage.total_tokens == 25


@pytest.mark.asyncio
async def test_anthropic_provider_structured_generation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({"decision": "REJECT", "confidence": 0.85, "items": ["alert1"]}),
                }
            ],
            "usage": {"input_tokens": 40, "output_tokens": 20},
        }
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test", transport=transport)

    req = ModelRequest(system_prompt="Review risk", user_prompt="Assess transaction")
    validated, resp = await provider.generate_structured(req, TargetSchema)

    assert isinstance(validated, TargetSchema)
    assert validated.decision == "REJECT"
    assert validated.confidence == 0.85
    assert validated.items == ["alert1"]
    assert resp.token_usage.total_tokens == 60


@pytest.mark.asyncio
async def test_anthropic_provider_auth_error_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-invalid-key", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderAuthException) as exc:
        await provider.generate_text(req)
    assert "Authentication failed" in str(exc.value)
    assert "ant-invalid-key" not in str(exc.value)


@pytest.mark.asyncio
async def test_anthropic_provider_rate_limit_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"type": "error", "error": {"type": "rate_limit_error", "message": "Too many requests"}})

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderRateLimitException) as exc:
        await provider.generate_text(req)
    assert "Rate limit exceeded" in str(exc.value)


@pytest.mark.asyncio
async def test_anthropic_provider_timeout_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Anthropic timed out")

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderTimeoutException) as exc:
        await provider.generate_text(req)
    assert "timed out" in str(exc.value)


@pytest.mark.asyncio
async def test_anthropic_provider_network_error_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to reach api.anthropic.com")

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(AIGatewayException) as exc:
        await provider.generate_text(req)
    assert "Network error" in str(exc.value)


@pytest.mark.asyncio
async def test_anthropic_provider_missing_api_key() -> None:
    provider = AnthropicModelProvider(api_key=None)
    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(ModelProviderAuthException) as exc:
        await provider.generate_text(req)
    assert "Authentication failed" in str(exc.value)
    assert exc.value.details.get("reason") == "ANTHROPIC_API_KEY is not configured"


@pytest.mark.asyncio
async def test_anthropic_provider_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Sorry, I cannot return JSON right now."}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    provider = AnthropicModelProvider(api_key="ant-test", transport=transport)

    req = ModelRequest(system_prompt="sys", user_prompt="hello")
    with pytest.raises(InvalidModelResponseException):
        await provider.generate_structured(req, TargetSchema)
