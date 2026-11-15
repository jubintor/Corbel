"""Unit tests for the deterministic SemanticMatcher (Phase 4)."""

import uuid

from corbel.domains.ontology.matcher import SemanticMatcher
from corbel.domains.ontology.models import Property, PropertyType


def test_matcher_exact_name_match() -> None:
    """Verify exact name and type match yields near 1.0 confidence with explicit explanation."""
    prop = Property(
        id=uuid.uuid4(),
        business_object_id=uuid.uuid4(),
        name="invoice_id",
        data_type=PropertyType.STRING.value,
        is_primary_key=True,
        is_nullable=False,
    )
    col_meta = {"name": "invoice_id", "data_type": "STRING"}
    col_profile = {"unique_percentage": 100.0, "null_count": 0, "quality_warnings": ["POTENTIAL_PRIMARY_KEY"]}

    suggestion = SemanticMatcher.match_column_to_property(prop, col_meta, col_profile)
    assert suggestion is not None
    assert suggestion.property_name == "invoice_id"
    assert suggestion.column_name == "invoice_id"
    assert suggestion.confidence >= 0.95
    assert "Exact name match" in suggestion.explanation
    assert "verified primary key candidate" in suggestion.explanation


def test_matcher_p2p_alias_match() -> None:
    """Verify known P2P domain aliases (e.g. po_number -> po_id) match with high confidence."""
    prop = Property(
        id=uuid.uuid4(),
        business_object_id=uuid.uuid4(),
        name="po_id",
        data_type=PropertyType.STRING.value,
        is_primary_key=True,
        is_nullable=False,
    )
    col_meta = {"name": "po_number", "data_type": "STRING"}
    col_profile = {"unique_percentage": 100.0, "null_count": 0}

    suggestion = SemanticMatcher.match_column_to_property(prop, col_meta, col_profile)
    assert suggestion is not None
    assert suggestion.column_name == "po_number"
    assert suggestion.confidence >= 0.85
    assert "Known domain alias match" in suggestion.explanation


def test_matcher_type_incompatibility_rejected() -> None:
    """Verify incompatible types (e.g. DATETIME column to NUMBER property) produce no suggestion."""
    prop = Property(
        id=uuid.uuid4(),
        business_object_id=uuid.uuid4(),
        name="total_amount",
        data_type=PropertyType.NUMBER.value,
        is_primary_key=False,
        is_nullable=False,
    )
    col_meta = {"name": "total_amount", "data_type": "DATETIME"}
    col_profile: dict[str, object] = {}

    suggestion = SemanticMatcher.match_column_to_property(prop, col_meta, col_profile)
    assert suggestion is None


def test_matcher_discover_mappings_for_object() -> None:
    """Verify batch discovery matches multiple properties and sorts by confidence."""
    props = [
        Property(id=uuid.uuid4(), business_object_id=uuid.uuid4(), name="invoice_id", data_type=PropertyType.STRING.value, is_primary_key=True),
        Property(id=uuid.uuid4(), business_object_id=uuid.uuid4(), name="invoice_amount", data_type=PropertyType.NUMBER.value),
        Property(id=uuid.uuid4(), business_object_id=uuid.uuid4(), name="invoice_date", data_type=PropertyType.DATETIME.value),
        Property(id=uuid.uuid4(), business_object_id=uuid.uuid4(), name="supplier_id", data_type=PropertyType.STRING.value),
    ]

    dataset_schema = [
        {"name": "invoice_id", "data_type": "STRING"},
        {"name": "supplier_id", "data_type": "STRING"},
        {"name": "invoice_amount", "data_type": "FLOAT"},
        {"name": "invoice_date", "data_type": "DATETIME"},
        {"name": "unrelated_column", "data_type": "STRING"},
    ]

    suggestions = SemanticMatcher.discover_mappings_for_object(props, dataset_schema)
    assert len(suggestions) == 4
    matched_prop_names = {s.property_name for s in suggestions}
    assert matched_prop_names == {"invoice_id", "invoice_amount", "invoice_date", "supplier_id"}
    assert all(s.confidence >= 0.80 for s in suggestions)
