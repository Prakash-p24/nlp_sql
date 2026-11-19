"""Add role-level and user-level data scope policy assignments.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_scope_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("database_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_name", sa.String(150), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False, server_default="table_column"),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("policy_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["database_id"], ["tenant_databases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "database_id", "policy_name", name="uq_data_scope_policy_name"),
    )
    op.create_index("ix_data_scope_policies_tenant_id", "data_scope_policies", ["tenant_id"])
    op.create_index("ix_data_scope_policies_database_id", "data_scope_policies", ["database_id"])
    op.create_index("ix_data_scope_policy_tenant_database", "data_scope_policies", ["tenant_id", "database_id"])

    op.create_table(
        "role_data_scope_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["data_scope_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "policy_id", name="uq_role_data_scope_assignment"),
    )
    op.create_index("ix_role_data_scope_assignments_role_id", "role_data_scope_assignments", ["role_id"])
    op.create_index("ix_role_data_scope_assignments_policy_id", "role_data_scope_assignments", ["policy_id"])

    op.create_table(
        "user_data_scope_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_user_id"], ["tenant_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["data_scope_policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_user_id", "policy_id", name="uq_user_data_scope_assignment"),
    )
    op.create_index("ix_user_data_scope_assignments_tenant_user_id", "user_data_scope_assignments", ["tenant_user_id"])
    op.create_index("ix_user_data_scope_assignments_policy_id", "user_data_scope_assignments", ["policy_id"])


def downgrade() -> None:
    op.drop_table("user_data_scope_assignments")
    op.drop_table("role_data_scope_assignments")
    op.drop_table("data_scope_policies")
