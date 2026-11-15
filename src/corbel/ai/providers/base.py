"""Base class for model providers with common extraction and validation logic."""

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from corbel.ai.exceptions import InvalidModelResponseException
from corbel.ai.interfaces import ModelProvider

T = TypeVar("T", bound=BaseModel)


class BaseAIProvider(ModelProvider):
    """Base class with shared helpers for extracting JSON and validating Pydantic models."""

    @staticmethod
    def extract_json_payload(text: str) -> dict[str, Any]:
        """Extract JSON from raw model output, supporting markdown code blocks or naked JSON."""
        clean = text.strip()

        # Handle ```json ... ``` code blocks
        json_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
        if json_block_match:
            candidate = json_block_match.group(1).strip()
        else:
            # Look for outermost { ... }
            start_idx = clean.find("{")
            end_idx = clean.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                candidate = clean[start_idx : end_idx + 1]
            else:
                candidate = clean

        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                raise InvalidModelResponseException(
                    f"Model output root must be a JSON object, got {type(parsed).__name__}.",
                    raw_response=text,
                )
            return parsed
        except json.JSONDecodeError as err:
            raise InvalidModelResponseException(
                f"Failed to parse JSON from model output: {err}",
                raw_response=text,
            ) from err

    @classmethod
    def validate_structured_payload(cls, payload: dict[str, Any], schema_class: type[T]) -> T:
        """Validate an extracted JSON dictionary against a Pydantic schema class."""
        try:
            return schema_class.model_validate(payload)
        except ValidationError as err:
            raise InvalidModelResponseException(
                f"Model output failed Pydantic validation for '{schema_class.__name__}': {err}",
                raw_response=json.dumps(payload),
            ) from err
