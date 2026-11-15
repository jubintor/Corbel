"""Phase 4: Ontology Engine & Semantic Discovery (Business Objects, Properties, Relationships, Property Mappings)

Revision ID: 0006_ontology_engine_semantic_discovery
Revises: 0005_data_intelligence_profiling
Create Date: 2026-11-15 11:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_ontology_semantic_discovery"
down_revision: str | None = "0005_data_intelligence_profiling"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create business_objects table
    op.create_table(
        "business_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("primary_key_property", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "id", name="uq_business_objects_project_id"),
        sa.UniqueConstraint("project_id", "name", name="uq_business_objects_project_name"),
    )

    # 2. Create properties table
    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "business_object_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_objects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "data_type",
            sa.String(length=32),
            server_default=sa.text("'STRING'"),
            nullable=False,
        ),
        sa.Column("is_nullable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_primary_key", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("source_mapping_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("business_object_id", "name", name="uq_properties_object_name"),
    )

    # 3. Create relationships table
    op.create_table(
        "relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_object_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("target_object_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column(
            "cardinality",
            sa.String(length=32),
            server_default=sa.text("'ONE_TO_MANY'"),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("join_expression_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_object_id"],
            ["business_objects.project_id", "business_objects.id"],
            ondelete="CASCADE",
            name="fk_relationships_project_source_object",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "target_object_id"],
            ["business_objects.project_id", "business_objects.id"],
            ondelete="CASCADE",
            name="fk_relationships_project_target_object",
        ),
        sa.UniqueConstraint(
            "project_id",
            "name",
            "source_object_id",
            "target_object_id",
            name="uq_relationships_project_name_endpoints",
        ),
    )

    # 4. Create property_mappings table
    op.create_table(
        "property_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "property_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("properties.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("column_name", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), server_default=sa.text("1.0"), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'SUGGESTED'"),
            nullable=False,
        ),
        sa.Column("explanation", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "dataset_id"],
            ["datasets.project_id", "datasets.id"],
            ondelete="CASCADE",
            name="fk_property_mappings_project_dataset",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "dataset_version_id"],
            ["dataset_versions.project_id", "dataset_versions.id"],
            ondelete="CASCADE",
            name="fk_property_mappings_project_dataset_version",
        ),
        sa.UniqueConstraint(
            "property_id",
            "dataset_version_id",
            "column_name",
            name="uq_property_mappings_version_col",
        ),
    )


def downgrade() -> None:
    op.drop_table("property_mappings")
    op.drop_table("relationships")
    op.drop_table("properties")
    op.drop_table("business_objects")
