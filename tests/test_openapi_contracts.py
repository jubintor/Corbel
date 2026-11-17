"""Automated test suite verifying OpenAPI contract export and TypeScript generation (P1-LIM-004, REG-FE-001)."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.generate_openapi import (
    check_schema_collisions,
    export_openapi,
    generate_typescript_definitions,
    normalize_ts_identifier,
)


def test_normalize_ts_identifier_preserves_valid_and_sanitizes_invalid() -> None:
    """Verify that normalize_ts_identifier sanitizes invalid chars and preserves valid identifiers (REG-FE-001)."""
    # 1. Standard valid identifiers preserved
    assert normalize_ts_identifier("SystemHealthResponse") == "SystemHealthResponse"
    assert normalize_ts_identifier("UserSession") == "UserSession"
    assert normalize_ts_identifier("valid_identifier_123") == "valid_identifier_123"
    assert normalize_ts_identifier("$special_var") == "$special_var"

    # 2. Hyphenated Pydantic v2 schemas converted to valid TypeScript identifiers
    assert normalize_ts_identifier("StructuredQueryRequest-Input") == "StructuredQueryRequest_Input"
    assert normalize_ts_identifier("StructuredQueryRequest-Output") == "StructuredQueryRequest_Output"

    # 3. Special invalid characters converted to underscores
    assert normalize_ts_identifier("foo.bar-baz@qux") == "foo_bar_baz_qux"
    assert normalize_ts_identifier("hello world") == "hello_world"
    assert normalize_ts_identifier("complex/ref:type#v1") == "complex_ref_type_v1"

    # 4. Leading digit prefixed with underscore
    assert normalize_ts_identifier("123NumericModel") == "_123NumericModel"

    # 5. Empty or missing name returns fallback
    assert normalize_ts_identifier("") == "Anonymous"


def test_schema_collision_detection_raises_on_duplicates() -> None:
    """Verify that schema name collisions trigger a descriptive ValueError rather than silent overwrites (REG-FE-001)."""
    # Distinct valid schemas pass
    schemas: dict[str, Any] = {
        "StructuredQueryRequest-Input": {},
        "StructuredQueryRequest-Output": {},
        "UserSession": {},
    }
    mapping = check_schema_collisions(schemas)
    assert mapping["StructuredQueryRequest-Input"] == "StructuredQueryRequest_Input"
    assert mapping["StructuredQueryRequest-Output"] == "StructuredQueryRequest_Output"

    # Colliding schemas (hyphen vs underscore) trigger ValueError
    colliding: dict[str, Any] = {
        "Query-Model": {},
        "Query_Model": {},
    }
    with pytest.raises(ValueError, match="Schema name collision detected: distinct schemas"):
        check_schema_collisions(colliding)


def test_nested_and_referenced_schema_normalization() -> None:
    """Verify that nested $ref references in properties, arrays, anyOf, and allOf are normalized (REG-FE-001)."""
    mock_schemas: dict[str, Any] = {
        "QueryFilter-Input": {
            "type": "object",
            "properties": {"field": {"type": "string"}},
        },
        "Nested-Model": {
            "type": "object",
            "properties": {
                "single_ref": {"$ref": "#/components/schemas/QueryFilter-Input"},
                "array_ref": {
                    "type": "array",
                    "items": {"$ref": "#/components/schemas/QueryFilter-Input"},
                },
                "union_ref": {
                    "anyOf": [
                        {"type": "null"},
                        {"$ref": "#/components/schemas/QueryFilter-Input"},
                    ],
                },
                "composite_ref": {
                    "allOf": [
                        {"$ref": "#/components/schemas/QueryFilter-Input"},
                    ],
                },
            },
        },
    }

    mock_openapi = {
        "info": {"title": "TestAPI", "version": "1.0"},
        "components": {"schemas": mock_schemas},
    }

    ts_output = generate_typescript_definitions(mock_openapi)

    # Declarations normalized
    assert "export interface QueryFilter_Input {" in ts_output
    assert "export interface Nested_Model {" in ts_output
    assert "QueryFilter-Input" not in ts_output
    assert "Nested-Model" not in ts_output

    # References normalized
    assert "single_ref?: QueryFilter_Input;" in ts_output
    assert "array_ref?: QueryFilter_Input[];" in ts_output
    assert "union_ref?: null | QueryFilter_Input;" in ts_output
    assert "composite_ref?: QueryFilter_Input;" in ts_output


def test_openapi_schema_generation_and_export() -> None:
    """Verify that export_openapi produces valid openapi.json and valid TypeScript contracts (REG-FE-001)."""
    export_openapi()

    root_dir = Path(__file__).resolve().parent.parent
    openapi_json_path = root_dir / "frontend" / "openapi.json"
    ts_generated_path = root_dir / "frontend" / "src" / "types" / "api_generated.ts"

    assert openapi_json_path.exists(), "frontend/openapi.json must exist"
    assert ts_generated_path.exists(), "frontend/src/types/api_generated.ts must exist"

    with open(openapi_json_path, encoding="utf-8") as f:
        schema = json.load(f)

    assert "openapi" in schema
    assert "components" in schema
    assert "schemas" in schema["components"]

    # Verify baseline Phase 1 schemas exist in OpenAPI
    schemas = schema["components"]["schemas"]
    assert "SystemHealthResponse" in schemas
    assert "DatabaseHealth" in schemas
    assert "ErrorResponse" in schemas

    with open(ts_generated_path, encoding="utf-8") as f:
        ts_content = f.read()

    # Baseline Phase 1 interfaces
    assert "export interface SystemHealthResponse" in ts_content
    assert "export interface DatabaseHealth" in ts_content
    assert "export interface ErrorResponse" in ts_content

    # REG-FE-001 specific checks: validate the actual current API contract
    assert "export interface StructuredQueryRequest {" in ts_content
    assert "export interface StructuredQueryResponse {" in ts_content
    assert "StructuredQueryRequest-Input" not in ts_content
    assert "StructuredQueryRequest-Output" not in ts_content

    # Reference in NaturalLanguageQueryResponse
    assert "parsed_query: StructuredQueryRequest;" in ts_content

    # Verify every interface declaration in generated file is a valid TypeScript identifier
    interface_declarations = re.findall(r"export interface\s+([^\s{]+)", ts_content)
    assert len(interface_declarations) > 0
    identifier_pattern = re.compile(r"^[a-zA-Z_$][a-zA-Z0-9_$]*$")
    for iface_name in interface_declarations:
        assert identifier_pattern.match(iface_name), f"Invalid TypeScript interface name: '{iface_name}'"
