"""Deterministic Blueprint Validator for Phase 12: Application Builder."""

import re
from typing import Any

from corbel.domains.app_builder.catalogue import get_component_spec
from corbel.domains.app_builder.schemas import (
    ApplicationDefinition,
    ApplicationValidationResponse,
    DataSourceType,
    GovernedActionType,
    InteractionActionType,
    ValidationErrorItem,
    ValidationWarningItem,
)

PROHIBITED_CODE_PATTERNS = [
    re.compile(r"<\s*script[^>]*>", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
]

MAX_PAGES = 50
MAX_COMPONENTS_PER_PAGE = 100


class ApplicationValidator:
    """Validates application blueprints against component specifications and safety boundaries."""

    @classmethod
    def validate(cls, definition: ApplicationDefinition) -> ApplicationValidationResponse:
        errors: list[ValidationErrorItem] = []
        warnings: list[ValidationWarningItem] = []

        # 1. Page & Navigation Structure
        if not definition.pages:
            errors.append(
                ValidationErrorItem(
                    path="pages",
                    message="Application must define at least one page.",
                    code="EMPTY_PAGES",
                )
            )

        if len(definition.pages) > MAX_PAGES:
            errors.append(
                ValidationErrorItem(
                    path="pages",
                    message=f"Application exceeds maximum page limit of {MAX_PAGES}.",
                    code="MAX_PAGES_EXCEEDED",
                )
            )

        page_ids: set[str] = set()
        component_ids: set[str] = set()

        for p_idx, page in enumerate(definition.pages):
            page_path = f"pages[{p_idx}]"
            if not page.id or not page.id.strip():
                errors.append(
                    ValidationErrorItem(
                        path=f"{page_path}.id",
                        message="Page ID cannot be empty.",
                        code="EMPTY_PAGE_ID",
                    )
                )
            elif page.id in page_ids:
                errors.append(
                    ValidationErrorItem(
                        path=f"{page_path}.id",
                        message=f"Duplicate page ID '{page.id}'.",
                        code="DUPLICATE_PAGE_ID",
                    )
                )
            else:
                page_ids.add(page.id)

            if not page.title or not page.title.strip():
                errors.append(
                    ValidationErrorItem(
                        path=f"{page_path}.title",
                        message="Page title cannot be empty.",
                        code="EMPTY_PAGE_TITLE",
                    )
                )

            # Check sections & components
            page_components_count = 0
            for s_idx, section in enumerate(page.sections):
                section_path = f"{page_path}.sections[{s_idx}]"
                for c_idx, component in enumerate(section.components):
                    page_components_count += 1
                    comp_path = f"{section_path}.components[{c_idx}]"

                    cls._validate_component(
                        comp_path=comp_path,
                        component=component,
                        component_ids=component_ids,
                        page_ids_context=page_ids,
                        errors=errors,
                        warnings=warnings,
                    )

            if page_components_count > MAX_COMPONENTS_PER_PAGE:
                errors.append(
                    ValidationErrorItem(
                        path=page_path,
                        message=f"Page '{page.id}' exceeds maximum component limit of {MAX_COMPONENTS_PER_PAGE}.",
                        code="MAX_COMPONENTS_EXCEEDED",
                    )
                )

        # 2. Navigation Integrity
        nav = definition.navigation
        if not nav.default_page_id:
            errors.append(
                ValidationErrorItem(
                    path="navigation.default_page_id",
                    message="Default page ID must be specified.",
                    code="MISSING_DEFAULT_PAGE",
                )
            )
        elif nav.default_page_id not in page_ids:
            errors.append(
                ValidationErrorItem(
                    path="navigation.default_page_id",
                    message=f"Default page '{nav.default_page_id}' does not exist in pages list.",
                    code="INVALID_DEFAULT_PAGE",
                )
            )

        for n_idx, item in enumerate(nav.items):
            if item.page_id not in page_ids:
                errors.append(
                    ValidationErrorItem(
                        path=f"navigation.items[{n_idx}].page_id",
                        message=f"Navigation item targets non-existent page '{item.page_id}'.",
                        code="ORPHAN_NAV_ITEM",
                    )
                )

        # 3. Security & Injection Checks on Application Text Fields
        cls._scan_for_prohibited_code("name", definition.name, errors)
        cls._scan_for_prohibited_code("description", definition.description, errors)

        return ApplicationValidationResponse(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    @classmethod
    def _validate_component(
        cls,
        comp_path: str,
        component: Any,
        component_ids: set[str],
        page_ids_context: set[str],
        errors: list[ValidationErrorItem],
        warnings: list[ValidationWarningItem],
    ) -> None:
        """Validate an individual component against the catalogue and safety boundaries."""
        # 1. Unique ID
        if not component.id or not component.id.strip():
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.id",
                    message="Component ID cannot be empty.",
                    code="EMPTY_COMPONENT_ID",
                )
            )
        elif component.id in component_ids:
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.id",
                    message=f"Duplicate component ID '{component.id}'.",
                    code="DUPLICATE_COMPONENT_ID",
                )
            )
        else:
            component_ids.add(component.id)

        # 2. Catalogue Resolution
        spec = get_component_spec(component.component_type)
        if not spec:
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.component_type",
                    message=f"Unknown or unsupported component type '{component.component_type}'.",
                    code="UNSUPPORTED_COMPONENT_TYPE",
                )
            )
            return

        # 3. Required Properties
        for req_prop in spec.required_properties:
            if req_prop not in component.properties or component.properties[req_prop] is None:
                errors.append(
                    ValidationErrorItem(
                        path=f"{comp_path}.properties.{req_prop}",
                        message=f"Component '{component.component_type.value}' requires property '{req_prop}'.",
                        code="MISSING_REQUIRED_PROPERTY",
                    )
                )

        # 4. Data Binding Conformance
        if component.data_binding:
            cls._validate_data_binding(comp_path, component, spec, errors)

        # 5. Interaction Conformance
        if component.interaction:
            cls._validate_interaction(comp_path, component, spec, errors, warnings)

        # 6. Prohibited Executable Code Scanning
        cls._scan_prohibited_in_dict(f"{comp_path}.properties", component.properties, errors)

    @classmethod
    def _validate_data_binding(
        cls,
        comp_path: str,
        component: Any,
        spec: Any,
        errors: list[ValidationErrorItem],
    ) -> None:
        """Validate data-binding compatibility against component specifications."""
        binding = component.data_binding
        if binding.source_type not in spec.supported_data_sources:
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.data_binding.source_type",
                    message=(
                        f"Component '{component.component_type.value}' does not support "
                        f"data source '{binding.source_type.value}'."
                    ),
                    code="INCOMPATIBLE_DATA_SOURCE",
                )
            )
        if binding.source_type == DataSourceType.ONTOLOGY_OBJECT and not binding.entity_name:
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.data_binding.entity_name",
                    message="Ontology data binding requires a non-empty entity_name.",
                    code="MISSING_ENTITY_NAME",
                )
            )

    @classmethod
    def _validate_interaction(
        cls,
        comp_path: str,
        component: Any,
        spec: Any,
        errors: list[ValidationErrorItem],
        warnings: list[ValidationWarningItem],
    ) -> None:
        """Validate user interaction configuration and governed action allowlist."""
        inter = component.interaction
        if not spec.supports_interactions:
            warnings.append(
                ValidationWarningItem(
                    path=f"{comp_path}.interaction",
                    message=f"Component '{component.component_type.value}' does not typically trigger interactions.",
                    code="UNEXPECTED_INTERACTION",
                )
            )
        if inter.action_type == InteractionActionType.NAVIGATE and not inter.target_page_id:
            errors.append(
                ValidationErrorItem(
                    path=f"{comp_path}.interaction.target_page_id",
                    message="Navigate interaction requires a target_page_id.",
                    code="MISSING_TARGET_PAGE",
                )
            )
        if inter.action_type == InteractionActionType.EXECUTE_ACTION and inter.governed_action_type:
            valid_action_values = {a.value for a in GovernedActionType}
            action_val = (
                inter.governed_action_type.value
                if hasattr(inter.governed_action_type, "value")
                else str(inter.governed_action_type)
            )
            if action_val not in valid_action_values:
                errors.append(
                    ValidationErrorItem(
                        path=f"{comp_path}.interaction.governed_action_type",
                        message=f"Action type '{action_val}' is not recognized or permitted.",
                        code="INVALID_GOVERNED_ACTION_TYPE",
                    )
                )

    @classmethod
    def _scan_for_prohibited_code(
        cls,
        path: str,
        value: str,
        errors: list[ValidationErrorItem],
    ) -> None:
        if not isinstance(value, str):
            return
        for pattern in PROHIBITED_CODE_PATTERNS:
            if pattern.search(value):
                errors.append(
                    ValidationErrorItem(
                        path=path,
                        message="Prohibited executable script or unsafe SQL pattern detected in definition.",
                        code="UNSAFE_CODE_REJECTED",
                    )
                )
                break

    @classmethod
    def _scan_prohibited_in_dict(
        cls,
        base_path: str,
        data: Any,
        errors: list[ValidationErrorItem],
    ) -> None:
        if isinstance(data, dict):
            for k, v in data.items():
                cls._scan_prohibited_in_dict(f"{base_path}.{k}", v, errors)
        elif isinstance(data, list):
            for i, v in enumerate(data):
                cls._scan_prohibited_in_dict(f"{base_path}[{i}]", v, errors)
        elif isinstance(data, str):
            cls._scan_for_prohibited_code(base_path, data, errors)
