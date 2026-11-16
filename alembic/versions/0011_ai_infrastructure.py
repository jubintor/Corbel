"""Phase 8: Complete AI Infrastructure & Bounded State Machines schema.

Revision ID: 0011_ai_infrastructure
Revises: 0010_findings_indexes_sync
Create Date: 2026-11-16 11:15:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_ai_infrastructure"
down_revision: str | None = "0010_findings_indexes_sync"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create task_executions table
    op.create_table(
        "task_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_retries", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("checkpoint_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cancellation_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_task_executions_project_id_id"),
    )
    op.create_index("ix_task_executions_project_id", "task_executions", ["project_id"], unique=False)
    op.create_index("ix_task_executions_status", "task_executions", ["status"], unique=False)
    op.create_index("ix_task_executions_worker_id", "task_executions", ["worker_id"], unique=False)
    op.create_index("ix_task_executions_lease_expires_at", "task_executions", ["lease_expires_at"], unique=False)

    # 2. Create workflow_executions table
    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_execution_id", sa.UUID(), nullable=True),
        sa.Column("workflow_type", sa.String(length=64), nullable=False),
        sa.Column("workflow_version", sa.String(length=32), server_default=sa.text("'1.0.0'"), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'INITIALIZED'"), nullable=False),
        sa.Column("current_state", sa.String(length=64), nullable=False),
        sa.Column("step_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_steps", sa.Integer(), server_default=sa.text("8"), nullable=False),
        sa.Column("token_budget", sa.Integer(), server_default=sa.text("50000"), nullable=False),
        sa.Column("cost_budget_usd", sa.Float(), server_default=sa.text("5.0"), nullable=False),
        sa.Column("input_parameters_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("state_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("result_data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parent_execution_id", sa.UUID(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "task_execution_id"],
            ["task_executions.project_id", "task_executions.id"],
            ondelete="SET NULL",
            name="fk_workflow_executions_project_task",
        ),
        sa.ForeignKeyConstraint(["parent_execution_id"], ["workflow_executions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_workflow_executions_project_id_id"),
        sa.UniqueConstraint("task_execution_id", "id", name="uq_workflow_executions_task_id_id"),
    )
    op.create_index("ix_workflow_executions_project_id", "workflow_executions", ["project_id"], unique=False)
    op.create_index("ix_workflow_executions_task_execution_id", "workflow_executions", ["task_execution_id"], unique=False)
    op.create_index("ix_workflow_executions_status", "workflow_executions", ["status"], unique=False)
    op.create_index("ix_workflow_executions_workflow_type", "workflow_executions", ["workflow_type"], unique=False)

    # 3. Create prompt_definitions table
    op.create_table(
        "prompt_definitions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("workflow_association", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=1024), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prompt_definitions_organization_id", "prompt_definitions", ["organization_id"], unique=False)
    op.create_index("ix_prompt_definitions_is_system", "prompt_definitions", ["is_system"], unique=False)
    op.create_index("ix_prompt_definitions_name", "prompt_definitions", ["name"], unique=False)

    # 4. Create prompt_versions table
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prompt_definition_id", sa.UUID(), nullable=False),
        sa.Column("version_tag", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("model_compatibility", sa.String(length=64), server_default=sa.text("'claude-3-5-sonnet'"), nullable=False),
        sa.Column("token_budget_input", sa.Integer(), server_default=sa.text("4096"), nullable=False),
        sa.Column("token_budget_output", sa.Integer(), server_default=sa.text("1024"), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("input_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_schema_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["prompt_definition_id"], ["prompt_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prompt_definition_id", "version_tag", name="uq_prompt_versions_def_tag"),
    )
    op.create_index("ix_prompt_versions_prompt_definition_id", "prompt_versions", ["prompt_definition_id"], unique=False)
    op.create_index("ix_prompt_versions_lifecycle_state", "prompt_versions", ["lifecycle_state"], unique=False)

    # 5. Create model_invocations table
    op.create_table(
        "model_invocations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workflow_execution_id", sa.UUID(), nullable=True),
        sa.Column("prompt_version_id", sa.UUID(), nullable=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("latency_ms", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("model_call_outcome", sa.String(length=32), server_default=sa.text("'SUCCESS'"), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("span_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_execution_id"], ["workflow_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_execution_id", "id", name="uq_model_invocations_wf_id"),
    )
    op.create_index("ix_model_invocations_workflow_execution_id", "model_invocations", ["workflow_execution_id"], unique=False)
    op.create_index("ix_model_invocations_prompt_version_id", "model_invocations", ["prompt_version_id"], unique=False)
    op.create_index("ix_model_invocations_created_at", "model_invocations", ["created_at"], unique=False)

    # 6. Create cost_records table
    op.create_table(
        "cost_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("model_invocation_id", sa.UUID(), nullable=False),
        sa.Column("task_execution_id", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("use_case", sa.String(length=64), server_default=sa.text("'procure-to-pay'"), nullable=False),
        sa.Column("workflow_name", sa.String(length=64), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=True),
        sa.Column("cost_usd", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("model_call_outcome", sa.String(length=32), nullable=False),
        sa.Column("workflow_outcome", sa.String(length=32), server_default=sa.text("'SUCCESS'"), nullable=False),
        sa.Column("task_outcome", sa.String(length=32), server_default=sa.text("'COMPLETED'"), nullable=False),
        sa.Column("pricing_tier_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_estimated", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_invocation_id"], ["model_invocations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_execution_id"], ["task_executions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "project_id"],
            ["projects.organization_id", "projects.id"],
            ondelete="CASCADE",
            name="fk_cost_records_org_project",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_records_model_invocation_id", "cost_records", ["model_invocation_id"], unique=False)
    op.create_index("ix_cost_records_organization_id", "cost_records", ["organization_id"], unique=False)
    op.create_index("ix_cost_records_project_id", "cost_records", ["project_id"], unique=False)
    op.create_index("ix_cost_records_task_execution_id", "cost_records", ["task_execution_id"], unique=False)
    op.create_index("ix_cost_records_workflow_name", "cost_records", ["workflow_name"], unique=False)
    op.create_index("ix_cost_records_timestamp", "cost_records", ["timestamp"], unique=False)

    # 7. Create evaluation_datasets table
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=True),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), server_default=sa.text("'1.0.0'"), nullable=False),
        sa.Column("domain", sa.String(length=64), server_default=sa.text("'procure-to-pay'"), nullable=False),
        sa.Column("test_cases_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_datasets_organization_id", "evaluation_datasets", ["organization_id"], unique=False)
    op.create_index("ix_evaluation_datasets_is_system", "evaluation_datasets", ["is_system"], unique=False)
    op.create_index("ix_evaluation_datasets_domain", "evaluation_datasets", ["domain"], unique=False)

    # 8. Create evaluation_runs table
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("evaluation_dataset_id", sa.UUID(), nullable=False),
        sa.Column("target_prompt_version_id", sa.UUID(), nullable=True),
        sa.Column("target_model_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_dataset_id"], ["evaluation_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_prompt_version_id"], ["prompt_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_runs_organization_id", "evaluation_runs", ["organization_id"], unique=False)
    op.create_index("ix_evaluation_runs_evaluation_dataset_id", "evaluation_runs", ["evaluation_dataset_id"], unique=False)
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"], unique=False)

    # 9. Create evaluation_results table
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("evaluation_run_id", sa.UUID(), nullable=False),
        sa.Column("test_case_id", sa.String(length=128), nullable=False),
        sa.Column("metric_name", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), server_default=sa.text("0.0"), nullable=False),
        sa.Column("passed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_results_evaluation_run_id", "evaluation_results", ["evaluation_run_id"], unique=False)
    op.create_index("ix_evaluation_results_metric_name", "evaluation_results", ["metric_name"], unique=False)


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_datasets")
    op.drop_table("cost_records")
    op.drop_table("model_invocations")
    op.drop_table("prompt_versions")
    op.drop_table("prompt_definitions")
    op.drop_table("workflow_executions")
    op.drop_table("task_executions")
