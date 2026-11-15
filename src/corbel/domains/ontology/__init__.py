"""Ontology Engine & Semantic Discovery domain module for Corbel."""

from corbel.domains.ontology.models import (
    BusinessObject,
    MappingStatus,
    Property,
    PropertyMapping,
    PropertyType,
    Relationship,
    RelationshipCardinality,
)
from corbel.domains.ontology.service import OntologyService

__all__ = [
    "BusinessObject",
    "MappingStatus",
    "OntologyService",
    "Property",
    "PropertyMapping",
    "PropertyType",
    "Relationship",
    "RelationshipCardinality",
]
