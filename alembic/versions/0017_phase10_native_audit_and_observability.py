"""Phase 10: Native Audit Immutability, Correlation Tracking, and Observability.

Revision ID: 0017_phase10_native_audit
Revises: 0016_phase2_security_remediation
Create Date: 2026-11-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_phase10_native_audit"
down_revision: str | None = "0016_phase2_security_remediation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add correlation_id and canonical_payload_hash to audit_events
    op.add_column(
        "audit_events",
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
        unique=False,
    )

    op.add_column(
        "audit_events",
        sa.Column("canonical_payload_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_audit_events_canonical_payload_hash",
        "audit_events",
        ["canonical_payload_hash"],
        unique=False,
    )

    # 2. Drop cascading foreign key from audit_events to projects.
    # Audit records are immutable historical logs and must not be cascade-deleted
    # when an operational project workspace is deleted (ADR-020).
    op.drop_constraint("fk_audit_events_org_project", "audit_events", type_="foreignkey")

    # 3. Database-level Append-Only Immutability Triggers (ADR-020)
    # Prevent any UPDATE or DELETE operations on audit_events
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_events_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events table is append-only. UPDATE and DELETE operations are strictly prohibited.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;
        CREATE TRIGGER trg_audit_events_immutable
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_events_mutation();
    """)

    # Prevent TRUNCATE operations on audit_events
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_events_truncate()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events table is append-only. TRUNCATE operation is strictly prohibited.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_audit_events_truncate ON audit_events;
        CREATE TRIGGER trg_audit_events_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION prevent_audit_events_truncate();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_truncate ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_events_truncate();")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_immutable ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_events_mutation();")

    op.create_foreign_key(
        "fk_audit_events_org_project",
        "audit_events",
        "projects",
        ["organization_id", "project_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )

    op.drop_index("ix_audit_events_canonical_payload_hash", table_name="audit_events")
    op.drop_column("audit_events", "canonical_payload_hash")
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_column("audit_events", "correlation_id")
