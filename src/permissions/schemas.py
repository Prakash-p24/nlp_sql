from uuid import UUID
from typing import Literal
from pydantic import BaseModel, Field


class ScopeDefinition(BaseModel):
    actions: list[str] = Field(min_length=1)
    tables: dict[UUID, list[UUID] | Literal["*"]]


class DataScopePolicyCreate(BaseModel):
    tenant_id: UUID
    database_id: UUID
    policy_name: str = Field(min_length=1, max_length=150)
    resource_type: Literal["table_column"] = "table_column"
    scope_type: Literal["allowlist", "denylist"]
    policy_definition: ScopeDefinition


class ScopeValues(BaseModel):
    """Optional per-assignment narrowing; never expands the policy grant."""
    tables: dict[UUID, list[UUID] | Literal["*"]] | None = None


class UserScopeAssignmentCreate(BaseModel):
    tenant_user_id: UUID
    policy_id: UUID
    scope_values: ScopeValues | None = None


class RoleScopeAssignmentCreate(BaseModel):
    role_id: UUID
    policy_id: UUID
