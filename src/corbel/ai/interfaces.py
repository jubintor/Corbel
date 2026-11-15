"""Abstract interfaces defining provider-neutral model execution contracts."""

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from corbel.ai.schemas import ModelRequest, ModelResponse

T = TypeVar("T", bound=BaseModel)


class ModelProvider(ABC):
    """Abstract model provider contract ensuring provider neutrality."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'mock', 'anthropic', 'openai')."""
        ...

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model identifier for this provider."""
        ...

    @abstractmethod
    async def generate_text(self, request: ModelRequest) -> ModelResponse:
        """Generate unstructured text from the model."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        request: ModelRequest,
        schema_class: type[T],
    ) -> tuple[T, ModelResponse]:
        """Generate and strictly validate structured output against a target Pydantic schema."""
        ...
