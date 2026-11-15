"""OpenAI hosted model provider adapter."""

import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from corbel.ai.exceptions import (
    AIGatewayException,
    ModelProviderAuthException,
    ModelProviderRateLimitException,
    ModelProviderTimeoutException,
)
from corbel.ai.providers.base import BaseAIProvider
from corbel.ai.schemas import ModelRequest, ModelResponse, TokenUsage

T = TypeVar("T", bound=BaseModel)


class OpenAIModelProvider(BaseAIProvider):
    """Adapter for hosted OpenAI GPT API."""

    def __init__(
        self,
        api_key: str | None,
        default_model: str = "gpt-4o",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._timeout_seconds = timeout_seconds
        self._endpoint = "https://api.openai.com/v1/chat/completions"
        self._transport = transport

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return self._default_model

    async def generate_text(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key or not self._api_key.strip():
            raise ModelProviderAuthException("openai", {"reason": "OPENAI_API_KEY is not configured"})

        start_time = time.perf_counter()

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        messages = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        payload: dict[str, Any] = {
            "model": self.default_model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout_seconds) as client:
                resp = await client.post(self._endpoint, headers=headers, json=payload)
        except httpx.TimeoutException as err:
            raise ModelProviderTimeoutException("openai", self._timeout_seconds) from err
        except httpx.RequestError as err:
            raise AIGatewayException(f"Network error calling OpenAI API: {err}") from err

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        if resp.status_code in (401, 403):
            raise ModelProviderAuthException("openai", {"status_code": resp.status_code, "body": resp.text[:200]})
        elif resp.status_code == 429:
            raise ModelProviderRateLimitException("openai", {"body": resp.text[:200]})
        elif resp.status_code >= 400:
            raise AIGatewayException(
                f"OpenAI API returned error HTTP {resp.status_code}: {resp.text[:300]}",
                status_code=502,
            )

        data = resp.json()
        choices = data.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""

        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        return ModelResponse(
            provider=self.provider_name,
            model=data.get("model", self.default_model),
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
        schema_json = schema_class.model_json_schema()
        augmented_prompt = (
            f"{request.system_prompt}\n\n"
            f"You MUST output valid JSON conforming strictly to this JSON Schema:\n"
            f"{schema_json}"
        )
        req = ModelRequest(
            system_prompt=augmented_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            response_schema=schema_json,
        )
        raw_resp = await self.generate_text(req)
        extracted = self.extract_json_payload(raw_resp.content)
        validated = self.validate_structured_payload(extracted, schema_class)
        raw_resp.structured_data = extracted
        return validated, raw_resp
