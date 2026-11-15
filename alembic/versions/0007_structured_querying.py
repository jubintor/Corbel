"""Phase 5: Structured Querying & Early AI Gateway schema.

Revision ID: 0007_structured_querying
Revises: 0006_ontology_semantic_discovery
Create Date: 2026-11-15 14:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_structured_querying"
down_revision: str | None = "0006_ontology_semantic_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create query_executions table
    op.create_table(
        "query_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("business_object_id", sa.UUID(), nullable=True),
        sa.Column("entity_name", sa.String(length=100), nullable=False),
        sa.Column("query_ast_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("compiled_sql", sa.Text(), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_time_ms", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_nlq", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("nlq_prompt", sa.Text(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["business_object_id"], ["business_objects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_executions_project_id", "query_executions", ["project_id"], unique=False)
    op.create_index("ix_query_executions_user_id", "query_executions", ["user_id"], unique=False)
    op.create_index("ix_query_executions_business_object_id", "query_executions", ["business_object_id"], unique=False)
    op.create_index("ix_query_executions_created_at", "query_executions", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_query_executions_created_at", table_name="query_executions")
    op.drop_index("ix_query_executions_business_object_id", table_name="query_executions")
    op.drop_index("ix_query_executions_user_id", table_name="query_executions")
    op.drop_index("ix_query_executions_project_id", table_name="query_executions")
    op.drop_table("query_executions")
