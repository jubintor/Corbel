"""Central AI Gateway orchestrating provider selection, token accounting, and safety boundaries."""

import logging
from typing import TypeVar

from pydantic import BaseModel

from corbel.ai.exceptions import UnsupportedModelProviderException
from corbel.ai.interfaces import ModelProvider
from corbel.ai.providers.anthropic import AnthropicModelProvider
from corbel.ai.providers.mock import MockModelProvider
from corbel.ai.providers.openai import OpenAIModelProvider
from corbel.ai.schemas import ModelProviderType, ModelRequest, ModelResponse
from corbel.ai.telemetry.phoenix import PhoenixTelemetryAdapter
from corbel.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIGateway:
    """Provider-neutral model gateway for Corbel."""

    def __init__(
        self,
        settings: Settings | None = None,
        phoenix_adapter: PhoenixTelemetryAdapter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._provider_override: ModelProvider | None = None
        self._mock_provider = MockModelProvider()
        self.phoenix = phoenix_adapter or PhoenixTelemetryAdapter(settings=self.settings)

    def set_provider(self, provider: ModelProvider | None) -> None:
        """Override the active provider (primarily for test fixtures)."""
        self._provider_override = provider

    def set_phoenix_adapter(self, adapter: PhoenixTelemetryAdapter) -> None:
        """Override the active Phoenix telemetry adapter (primarily for test fixtures)."""
        self.phoenix = adapter

    def get_provider(self) -> ModelProvider:
        """Resolve the active model provider according to configuration."""
        if self._provider_override is not None:
            return self._provider_override

        provider_type = self.settings.AI_PROVIDER.lower().strip()

        if provider_type == ModelProviderType.MOCK.value:
            return self._mock_provider
        elif provider_type == ModelProviderType.ANTHROPIC.value:
            return AnthropicModelProvider(
                api_key=self.settings.ANTHROPIC_API_KEY,
                default_model=self.settings.ANTHROPIC_MODEL,
                timeout_seconds=self.settings.AI_REQUEST_TIMEOUT_SECONDS,
            )
        elif provider_type == ModelProviderType.OPENAI.value:
            return OpenAIModelProvider(
                api_key=self.settings.OPENAI_API_KEY,
                default_model=self.settings.OPENAI_MODEL,
                timeout_seconds=self.settings.AI_REQUEST_TIMEOUT_SECONDS,
            )
        else:
            supported = [p.value for p in ModelProviderType]
            raise UnsupportedModelProviderException(provider_type, supported)

    async def generate_text(self, request: ModelRequest) -> ModelResponse:
        """Generate text through the active model provider with telemetry."""
        provider = self.get_provider()
        logger.info(
            "ai_gateway_generate_text_start provider=%s model=%s",
            provider.provider_name,
            provider.default_model,
        )
        response = await provider.generate_text(request)
        logger.info(
            "ai_gateway_generate_text_complete provider=%s model=%s tokens=%d latency_ms=%.2f",
            response.provider,
            response.model,
            response.token_usage.total_tokens,
            response.latency_ms,
        )
        # Export telemetry to Arize Phoenix if enabled (non-blocking, fault tolerant)
        await self.phoenix.export_span(
            span_name="corbel.ai.gateway.generate_text",
            model_name=response.model,
            provider=response.provider,
            input_tokens=response.token_usage.prompt_tokens,
            output_tokens=response.token_usage.completion_tokens,
            latency_ms=response.latency_ms,
            prompt=request.user_prompt,
            response_text=response.content,
            status="SUCCESS",
        )
        return response

    async def generate_structured(
        self,
        request: ModelRequest,
        schema_class: type[T],
    ) -> tuple[T, ModelResponse]:
        """Generate structured output strictly validated against a target Pydantic schema."""
        provider = self.get_provider()
        logger.info(
            "ai_gateway_generate_structured_start provider=%s model=%s target_schema=%s",
            provider.provider_name,
            provider.default_model,
            schema_class.__name__,
        )
        validated, response = await provider.generate_structured(request, schema_class)
        logger.info(
            "ai_gateway_generate_structured_complete provider=%s model=%s target_schema=%s tokens=%d latency_ms=%.2f",
            response.provider,
            response.model,
            schema_class.__name__,
            response.token_usage.total_tokens,
            response.latency_ms,
        )
        # Export telemetry to Arize Phoenix if enabled (non-blocking, fault tolerant)
        await self.phoenix.export_span(
            span_name=f"corbel.ai.gateway.generate_structured[{schema_class.__name__}]",
            model_name=response.model,
            provider=response.provider,
            input_tokens=response.token_usage.prompt_tokens,
            output_tokens=response.token_usage.completion_tokens,
            latency_ms=response.latency_ms,
            prompt=request.user_prompt,
            response_text=response.content,
            status="SUCCESS",
        )
        return validated, response
