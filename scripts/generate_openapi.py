"""Generate OpenAPI JSON specification and synchronized TypeScript definitions (P1-LIM-004, REG-FE-001).

Exports the authoritative FastAPI OpenAPI schema and generates synchronized
TypeScript type definitions in frontend/src/types/api_generated.ts to prevent
contract drift between backend Pydantic models and frontend client interfaces.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from corbel.main import create_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("corbel.openapi_codegen")


def normalize_ts_identifier(raw_name: str) -> str:
    """Normalize a raw OpenAPI schema or reference name to a valid TypeScript identifier (REG-FE-001).

    Converts invalid identifier characters (hyphens, dots, spaces, special symbols)
    into underscores while preserving valid alphanumeric characters and underscores.
    Ensures the identifier does not start with a digit.
    """
    if not raw_name:
        return "Anonymous"

    # Replace all characters that are not ASCII letters, digits, underscores, or dollar signs
    sanitized = re.sub(r"[^a-zA-Z0-9_$]", "_", raw_name)

    # TypeScript identifiers cannot begin with a digit
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    return sanitized


def check_schema_collisions(schemas: dict[str, Any]) -> dict[str, str]:
    """Verify that normalization does not cause distinct OpenAPI schemas to collide (REG-FE-001).

    Returns a mapping of raw_schema_name -> normalized_ts_identifier.
    Raises ValueError if two distinct raw schema names normalize to the same TypeScript identifier.
    """
    normalized_to_raw: dict[str, str] = {}
    raw_to_normalized: dict[str, str] = {}

    for raw_name in sorted(schemas.keys()):
        normalized = normalize_ts_identifier(raw_name)
        if normalized in normalized_to_raw and normalized_to_raw[normalized] != raw_name:
            colliding_raw = normalized_to_raw[normalized]
            raise ValueError(
                f"Schema name collision detected: distinct schemas '{colliding_raw}' and '{raw_name}' "
                f"both normalize to TypeScript identifier '{normalized}'."
            )
        normalized_to_raw[normalized] = raw_name
        raw_to_normalized[raw_name] = normalized

    return raw_to_normalized


def map_openapi_type_to_ts(prop_schema: dict[str, Any], schemas: dict[str, Any]) -> str:
    """Map an OpenAPI property schema to a TypeScript type string."""
    if "$ref" in prop_schema:
        ref_name = prop_schema["$ref"].split("/")[-1]
        return normalize_ts_identifier(ref_name)

    if "anyOf" in prop_schema:
        types = []
        for variant in prop_schema["anyOf"]:
            if variant.get("type") == "null":
                types.append("null")
            else:
                types.append(map_openapi_type_to_ts(variant, schemas))
        return " | ".join(types)

    if "allOf" in prop_schema:
        return " & ".join(map_openapi_type_to_ts(v, schemas) for v in prop_schema["allOf"])

    schema_type = prop_schema.get("type")

    if schema_type == "string":
        if "enum" in prop_schema:
            return " | ".join(f"'{val}'" for val in prop_schema["enum"])
        return "string"

    if schema_type in ("integer", "number"):
        return "number"

    if schema_type == "boolean":
        return "boolean"

    if schema_type == "array":
        items_schema = prop_schema.get("items", {})
        item_ts = map_openapi_type_to_ts(items_schema, schemas)
        if " | " in item_ts:
            return f"({item_ts})[]"
        return f"{item_ts}[]"

    if schema_type == "object" or "properties" in prop_schema:
        additional_props = prop_schema.get("additionalProperties")
        if isinstance(additional_props, dict):
            val_type = map_openapi_type_to_ts(additional_props, schemas)
            return f"Record<string, {val_type}>"
        return "Record<string, unknown>"

    return "unknown"


def generate_typescript_definitions(openapi_schema: dict[str, Any]) -> str:
    """Generate clean TypeScript interfaces from OpenAPI components schemas."""
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    raw_to_norm = check_schema_collisions(schemas)

    ts_lines: list[str] = [
        "/**",
        " * Automatically generated OpenAPI TypeScript contracts for Corbel.",
        f" * Generated from FastAPI specification: {openapi_schema.get('info', {}).get('title')} v{openapi_schema.get('info', {}).get('version')}",
        " * DO NOT EDIT MANUALLY - re-run: npm run generate-api or python scripts/generate_openapi.py",
        " */",
        "",
    ]

    for raw_schema_name, schema_def in sorted(schemas.items()):
        ts_name = raw_to_norm[raw_schema_name]
        description = schema_def.get("description", "")
        if description:
            ts_lines.append(f"/** {description.strip()} */")

        # Enum type
        if "enum" in schema_def:
            enum_values = " | ".join(f"'{v}'" for v in schema_def["enum"])
            ts_lines.append(f"export type {ts_name} = {enum_values};")
            ts_lines.append("")
            continue

        # Interface definition
        properties = schema_def.get("properties", {})
        required_fields = set(schema_def.get("required", []))

        ts_lines.append(f"export interface {ts_name} {{")
        for prop_name, prop_schema in properties.items():
            prop_desc = prop_schema.get("description", "")
            if prop_desc:
                ts_lines.append(f"  /** {prop_desc.strip()} */")
            is_optional = prop_name not in required_fields
            opt_mark = "?" if is_optional else ""
            ts_type = map_openapi_type_to_ts(prop_schema, schemas)
            ts_lines.append(f"  {prop_name}{opt_mark}: {ts_type};")

        ts_lines.append("}")
        ts_lines.append("")

    return "\n".join(ts_lines)


def export_openapi() -> None:
    """Export openapi.json and generate TypeScript type definitions."""
    root_dir = Path(__file__).resolve().parent.parent
    frontend_dir = root_dir / "frontend"
    types_dir = frontend_dir / "src" / "types"
    types_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing FastAPI application to extract OpenAPI schema...")
    app = create_application()
    openapi_schema = app.openapi()

    openapi_json_path = frontend_dir / "openapi.json"
    with open(openapi_json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
    logger.info(f"Saved OpenAPI JSON schema to {openapi_json_path}")

    ts_output_path = types_dir / "api_generated.ts"
    ts_content = generate_typescript_definitions(openapi_schema)
    with open(ts_output_path, "w", encoding="utf-8") as f:
        f.write(ts_content)
    logger.info(f"Generated {len(openapi_schema.get('components', {}).get('schemas', {}))} TypeScript contracts in {ts_output_path}")


if __name__ == "__main__":
    export_openapi()
