"""RAG Upgrade: pgvector, vector embeddings, and epistemic evidence classification.

Revision ID: 0014_rag_pgvector_and_evidence
Revises: 0013_governance_and_rag
Create Date: 2026-11-16 14:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_rag_pgvector_and_evidence"
down_revision: str | None = "0013_governance_and_rag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Add document_extracts_json to investigations table
    op.add_column(
        "investigations",
        sa.Column(
            "document_extracts_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 3. Add evidence_classification to investigation_evidence table
    op.add_column(
        "investigation_evidence",
        sa.Column(
            "evidence_classification",
            sa.String(length=32),
            nullable=False,
            server_default="TRANSACTION_FACT",
        ),
    )
    op.create_index(
        "ix_investigation_evidence_evidence_classification",
        "investigation_evidence",
        ["evidence_classification"],
    )

    # 4. Add native vector and metadata columns to document_chunks table
    op.add_column(
        "document_chunks",
        sa.Column("embedding_vector", Vector(1536), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_model", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_document_chunks_embedding_model",
        "document_chunks",
        ["embedding_model"],
    )

    # 5. Add HNSW cosine index on embedding_vector
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_vector "
        "ON document_chunks USING hnsw (embedding_vector vector_cosine_ops);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_vector;")
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_model;")
    op.drop_column("document_chunks", "embedding_dim")
    op.drop_column("document_chunks", "embedding_version")
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("document_chunks", "embedding_vector")

    op.execute("DROP INDEX IF EXISTS ix_investigation_evidence_evidence_classification;")
    op.execute("DROP INDEX IF EXISTS ix_investigation_evidence_classification;")
    op.drop_column("investigation_evidence", "evidence_classification")
    op.drop_column("investigations", "document_extracts_json")
