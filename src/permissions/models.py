import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.core.database import Base


def utcnow(): return datetime.now(timezone.utc)

class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    permission_code: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

class RolePermission(Base):
    __tablename__ = "role_permissions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False, index=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("permissions.id"), nullable=False, index=True)
    effect: Mapped[str] = mapped_column(String(32), nullable=False, default="allow")
    conditions: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),)


class DataScopePolicy(Base):
    """A tenant/database-scoped table and column allow/deny policy.

    policy_definition shape:
      {"actions": ["METADATA_VIEW"],
       "tables": {"<table UUID>": ["<column UUID>"], "<other table UUID>": "*"}}

    scope_type is "allowlist" or "denylist". An empty column list allows the
    table metadata but no columns; "*" allows every column in that table.
    """

    __tablename__ = "data_scope_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    database_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_databases.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_name: Mapped[str] = mapped_column(String(150), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="table_column", server_default="table_column")
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    __table_args__ = (
        UniqueConstraint("tenant_id", "database_id", "policy_name", name="uq_data_scope_policy_name"),
        Index("ix_data_scope_policy_tenant_database", "tenant_id", "database_id"),
    )


class RoleDataScopeAssignment(Base):
    """Attach a scope policy to a role; service code enforces tenant matching."""

    __tablename__ = "role_data_scope_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("data_scope_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    __table_args__ = (UniqueConstraint("role_id", "policy_id", name="uq_role_data_scope_assignment"),)


class UserDataScopeAssignment(Base):
    """Attach a policy to one tenant membership; scope_values only narrows it."""

    __tablename__ = "user_data_scope_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenant_users.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("data_scope_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_values: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now())

    __table_args__ = (UniqueConstraint("tenant_user_id", "policy_id", name="uq_user_data_scope_assignment"),)


