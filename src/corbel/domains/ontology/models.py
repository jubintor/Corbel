"""SQLAlchemy ORM models for Ontology Engine & Semantic Discovery (Phase 4)."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from corbel.core.database import Base


class PropertyType(str, enum.Enum):
    """Supported business data types for ontology properties."""

    STRING = "STRING"
    NUMBER = "NUMBER"
    DATETIME = "DATETIME"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"


class RelationshipCardinality(str, enum.Enum):
    """Cardinality of directed semantic relationships connecting business objects."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


class MappingStatus(str, enum.Enum):
    """Lifecycle status of a column-to-property semantic mapping."""

    SUGGESTED = "SUGGESTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class BusinessObject(Base):
    """Semantic enterprise entity representing a core operational concept.

    (e.g., Supplier, PurchaseOrder, GoodsReceipt, Invoice).
    Defined within exactly one Project workspace (Direct Project Scope).
    """

    __tablename__ = "business_objects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    primary_key_property: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    properties: Mapped[list["Property"]] = relationship(
        "Property",
        back_populates="business_object",
        cascade="all, delete-orphan",
        order_by="Property.name.asc()",
    )
    outgoing_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        primaryjoin="BusinessObject.id == Relationship.source_object_id",
        back_populates="source_object",
        cascade="all, delete-orphan",
    )
    incoming_relationships: Mapped[list["Relationship"]] = relationship(
        "Relationship",
        primaryjoin="BusinessObject.id == Relationship.target_object_id",
        back_populates="target_object",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "id", name="uq_business_objects_project_id"),
        UniqueConstraint("project_id", "name", name="uq_business_objects_project_name"),
    )


class Property(Base):
    """Strongly-typed business attribute belonging to a Business Object.

    (e.g., supplier_id, order_total_usd, invoice_amount).
    Inherited project scope via business_object_id.
    """

    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    business_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_objects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_type: Mapped[str] = mapped_column(
        String(32), default=PropertyType.STRING.value, nullable=False
    )
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_mapping_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    business_object: Mapped["BusinessObject"] = relationship(
        "BusinessObject", back_populates="properties"
    )
    mappings: Mapped[list["PropertyMapping"]] = relationship(
        "PropertyMapping",
        back_populates="property",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("business_object_id", "name", name="uq_properties_object_name"),
    )


class Relationship(Base):
    """Directed semantic link connecting two Business Objects.

    (e.g., Supplier -> supplies -> PurchaseOrder, PurchaseOrder -> billed_in -> Invoice).
    Must connect two Business Objects belonging to the exact same Project (composite foreign keys).
    """

    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    target_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    cardinality: Mapped[str] = mapped_column(
        String(32), default=RelationshipCardinality.ONE_TO_MANY.value, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    join_expression_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    source_object: Mapped["BusinessObject"] = relationship(
        "BusinessObject",
        foreign_keys=[source_object_id],
        back_populates="outgoing_relationships",
    )
    target_object: Mapped["BusinessObject"] = relationship(
        "BusinessObject",
        foreign_keys=[target_object_id],
        back_populates="incoming_relationships",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "source_object_id"],
            ["business_objects.project_id", "business_objects.id"],
            ondelete="CASCADE",
            name="fk_relationships_project_source_object",
        ),
        ForeignKeyConstraint(
            ["project_id", "target_object_id"],
            ["business_objects.project_id", "business_objects.id"],
            ondelete="CASCADE",
            name="fk_relationships_project_target_object",
        ),
        UniqueConstraint(
            "project_id",
            "name",
            "source_object_id",
            "target_object_id",
            name="uq_relationships_project_name_endpoints",
        ),
    )


class PropertyMapping(Base):
    """Explicit or candidate column-to-property mapping linking discovered dataset schema

    to business object properties.
    Must belong to the exact same Project as the referenced dataset and dataset version.
    """

    __tablename__ = "property_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
    )
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=MappingStatus.SUGGESTED.value, nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    property: Mapped["Property"] = relationship("Property", back_populates="mappings")

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            ondelete="CASCADE",
            name="fk_property_mappings_project_dataset",
        ),
        ForeignKeyConstraint(
            ["project_id", "dataset_version_id"],
            ["dataset_versions.project_id", "dataset_versions.id"],
            ondelete="CASCADE",
            name="fk_property_mappings_project_dataset_version",
        ),
        UniqueConstraint(
            "property_id",
            "dataset_version_id",
            "column_name",
            name="uq_property_mappings_version_col",
        ),
    )
