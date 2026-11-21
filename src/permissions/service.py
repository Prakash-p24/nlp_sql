from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy.orm import Session

from src.databases.models import TenantDatabase
from src.metadata.models import DatabaseColumn, DatabaseSchema, DatabaseTable
from src.permissions.models import (
    DataScopePolicy,
    Permission,
    RoleDataScopeAssignment,
    RolePermission,
    UserDataScopeAssignment,
)
from src.tenants.models import Role, Tenant, TenantUser, UserRole


class PermissionDenied(Exception):
    """Raised when a tenant member lacks an action or data-scope grant."""


def create_scope_policy(
    db: Session,
    *,
    tenant_id: uuid.UUID | str,
    database_id: uuid.UUID | str,
    policy_name: str,
    scope_type: str,
    policy_definition: dict,
    resource_type: str = "table_column",
) -> DataScopePolicy:
    """Create a policy after validating its action codes and resource IDs."""
    tenant_uuid, database_uuid = _as_uuid(tenant_id), _as_uuid(database_id)
    database = db.query(TenantDatabase).filter(
        TenantDatabase.id == database_uuid,
        TenantDatabase.tenant_id == tenant_uuid,
    ).one_or_none()
    if database is None:
        raise PermissionDenied("Database does not belong to the requested tenant")
    if db.query(Tenant).filter(Tenant.id == tenant_uuid).one_or_none() is None:
        raise PermissionDenied("Tenant does not exist")
    if scope_type.lower() not in ("allowlist", "denylist", "allow", "deny"):
        raise PermissionDenied("scope_type must be allowlist or denylist")
    if resource_type != "table_column":
        raise PermissionDenied("Only table_column policies are currently supported")

    actions = policy_definition.get("actions")
    if not isinstance(actions, list) or not actions:
        raise PermissionDenied("Policy must declare at least one permission action")
    known_actions = {
        code for (code,) in db.query(Permission.permission_code)
        .filter(Permission.permission_code.in_(actions)).all()
    }
    if known_actions != set(actions):
        raise PermissionDenied("Policy references an unknown permission code")

    table_scope = _parse_tables(policy_definition.get("tables"))
    _validate_scope(db, table_scope, tenant_uuid, database_uuid)
    policy = DataScopePolicy(
        tenant_id=tenant_uuid,
        database_id=database_uuid,
        policy_name=policy_name,
        resource_type=resource_type,
        scope_type=scope_type.lower(),
        policy_definition=policy_definition,
        is_active=True,
    )
    db.add(policy)
    db.flush()
    return policy


def assign_scope_policy_to_role(
    db: Session, *, tenant_id: uuid.UUID | str, role_id: uuid.UUID | str,
    policy_id: uuid.UUID | str,
) -> RoleDataScopeAssignment:
    tenant_uuid, role_uuid, policy_uuid = map(_as_uuid, (tenant_id, role_id, policy_id))
    role = db.query(Role).filter(
        Role.id == role_uuid,
        (Role.tenant_id == tenant_uuid) | (Role.tenant_id.is_(None)),
    ).one_or_none()
    policy = db.query(DataScopePolicy).filter(
        DataScopePolicy.id == policy_uuid,
        DataScopePolicy.tenant_id == tenant_uuid,
    ).one_or_none()
    if role is None or policy is None:
        raise PermissionDenied("Role and policy must belong to the requested tenant")
    if role.role_name == "admin":
        raise PermissionDenied("Tenant administrator roles are unrestricted and cannot receive data-scope policies")
    assignment = RoleDataScopeAssignment(role_id=role_uuid, policy_id=policy_uuid)
    db.add(assignment)
    db.flush()
    return assignment


def assign_scope_policy_to_user(
    db: Session, *, tenant_id: uuid.UUID | str, tenant_user_id: uuid.UUID | str,
    policy_id: uuid.UUID | str, scope_values: dict | None = None,
) -> UserDataScopeAssignment:
    tenant_uuid, member_uuid, policy_uuid = map(_as_uuid, (tenant_id, tenant_user_id, policy_id))
    membership = db.query(TenantUser).filter(
        TenantUser.id == member_uuid,
        TenantUser.tenant_id == tenant_uuid,
        TenantUser.status == "active",
    ).one_or_none()
    policy = db.query(DataScopePolicy).filter(
        DataScopePolicy.id == policy_uuid,
        DataScopePolicy.tenant_id == tenant_uuid,
    ).one_or_none()
    if membership is None or policy is None:
        raise PermissionDenied("Membership and policy must belong to the requested tenant")

    is_admin = db.query(UserRole.id).join(
        Role, Role.id == UserRole.role_id
    ).filter(
        UserRole.tenant_user_id == membership.id,
        Role.tenant_id == tenant_uuid,
        Role.role_name == "admin",
    ).first()
    if is_admin is not None:
        raise PermissionDenied("Tenant administrators are unrestricted and cannot receive user data-scope policies")

    if scope_values and "tables" in scope_values:
        policy_scope = _parse_tables((policy.policy_definition or {}).get("tables"))
        requested_scope = _parse_tables(scope_values["tables"])
        if _intersect(policy_scope, requested_scope) != requested_scope:
            raise PermissionDenied("User scope_values may narrow a policy, never expand it")
        _validate_scope(db, requested_scope, tenant_uuid, policy.database_id)

    assignment = UserDataScopeAssignment(
        tenant_user_id=member_uuid,
        policy_id=policy_uuid,
        scope_values=scope_values,
    )
    db.add(assignment)
    db.flush()
    return assignment


@dataclass(frozen=True)
class AccessScope:
    """Allowed tables and columns for one tenant, database, and action.

    A table mapped to None means all of that table's columns are allowed.
    A table mapped to an empty set is visible, but no columns are allowed.
    """

    table_columns: Mapping[uuid.UUID, frozenset[uuid.UUID] | None]

    @property
    def table_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(self.table_columns)

    def allows_table(self, table_id: uuid.UUID | str) -> bool:
        return _as_uuid(table_id) in self.table_columns

    def allows_column(self, table_id: uuid.UUID | str, column_id: uuid.UUID | str) -> bool:
        table_uuid, column_uuid = _as_uuid(table_id), _as_uuid(column_id)
        if table_uuid not in self.table_columns:
            return False
        columns = self.table_columns[table_uuid]
        return columns is None or column_uuid in columns


def _as_uuid(value: uuid.UUID | str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise PermissionDenied("A scope contains an invalid resource ID") from exc


def _parse_tables(value: object) -> dict[uuid.UUID, frozenset[uuid.UUID] | None]:
    if not isinstance(value, dict):
        raise PermissionDenied("A scope policy must define a 'tables' object")
    result: dict[uuid.UUID, frozenset[uuid.UUID] | None] = {}
    for raw_table_id, raw_columns in value.items():
        table_id = _as_uuid(raw_table_id)
        if raw_columns == "*":
            result[table_id] = None
        elif isinstance(raw_columns, list):
            result[table_id] = frozenset(_as_uuid(column_id) for column_id in raw_columns)
        else:
            raise PermissionDenied("Table scope values must be '*' or a list of column IDs")
    return result


def _union(*scopes: Mapping[uuid.UUID, frozenset[uuid.UUID] | None]) -> dict[uuid.UUID, frozenset[uuid.UUID] | None]:
    combined: dict[uuid.UUID, frozenset[uuid.UUID] | None] = {}
    for scope in scopes:
        for table_id, columns in scope.items():
            if table_id not in combined:
                combined[table_id] = columns
                continue
            current = combined[table_id]
            combined[table_id] = None if current is None or columns is None else current | columns
    return combined


def _intersect(
    left: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
    right: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
) -> dict[uuid.UUID, frozenset[uuid.UUID] | None]:
    result = {}
    for table_id in left.keys() & right.keys():
        left_columns, right_columns = left[table_id], right[table_id]
        if left_columns is None:
            result[table_id] = right_columns
        elif right_columns is None:
            result[table_id] = left_columns
        else:
            result[table_id] = left_columns & right_columns
    return result


def _subtract(
    allowed: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
    denied: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
) -> dict[uuid.UUID, frozenset[uuid.UUID] | None]:
    result = dict(allowed)
    for table_id, denied_columns in denied.items():
        if table_id not in result:
            continue
        if denied_columns is None:
            result.pop(table_id)
            continue
        allowed_columns = result[table_id]
        if allowed_columns is None:
            # A wildcard allow cannot be represented safely after subtracting
            # selected columns without knowing the table's full column set.
            # The caller expands wildcards before applying deny policies.
            raise PermissionDenied("Wildcard table grants cannot be combined with column deny policies")
        result[table_id] = allowed_columns - denied_columns
    return result


def _policy_scope(
    policy: DataScopePolicy,
    action: str,
    assignment_values: dict | None = None,
) -> tuple[str, dict[uuid.UUID, frozenset[uuid.UUID] | None]] | None:
    if not policy.is_active:
        return None
    if policy.resource_type != "table_column":
        raise PermissionDenied(f"Unsupported policy resource type: {policy.resource_type}")
    definition = policy.policy_definition or {}
    actions = definition.get("actions", [])
    if action not in actions and "*" not in actions:
        return None
    tables = _parse_tables(definition.get("tables"))

    # assignment.scope_values can only narrow the policy's table/column scope.
    if assignment_values and "tables" in assignment_values:
        tables = _intersect(tables, _parse_tables(assignment_values["tables"]))

    scope_type = policy.scope_type.lower()
    if scope_type in ("allow", "allowlist"):
        effect = "allow"
    elif scope_type in ("deny", "denylist"):
        effect = "deny"
    else:
        raise PermissionDenied(f"Unsupported scope type: {policy.scope_type}")
    return effect, tables


def _expand_wildcards(
    db: Session,
    scope: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
    tenant_id: uuid.UUID,
    database_id: uuid.UUID,
) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
    expanded: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for table_id, column_ids in scope.items():
        if column_ids is not None:
            expanded[table_id] = column_ids
            continue
        all_columns = (
            db.query(DatabaseColumn.id)
            .join(DatabaseTable, DatabaseTable.id == DatabaseColumn.table_id)
            .filter(
                DatabaseTable.id == table_id,
                DatabaseTable.tenant_id == tenant_id,
                DatabaseTable.database_id == database_id,
            )
            .all()
        )
        expanded[table_id] = frozenset(column_id for (column_id,) in all_columns)
    return expanded


def _validate_scope(
    db: Session,
    scope: Mapping[uuid.UUID, frozenset[uuid.UUID] | None],
    tenant_id: uuid.UUID,
    database_id: uuid.UUID,
) -> None:
    if not scope:
        return
    valid_tables = {
        table_id
        for (table_id,) in db.query(DatabaseTable.id).filter(
            DatabaseTable.id.in_(scope),
            DatabaseTable.tenant_id == tenant_id,
            DatabaseTable.database_id == database_id,
            DatabaseTable.is_active.is_(True),
        ).all()
    }
    if valid_tables != set(scope):
        raise PermissionDenied("A scope references a table outside its tenant/database")

    requested_columns = {
        (table_id, column_id)
        for table_id, columns in scope.items()
        if columns is not None
        for column_id in columns
    }
    if not requested_columns:
        return
    valid_pairs = set(
        db.query(DatabaseColumn.table_id, DatabaseColumn.id)
        .join(DatabaseTable, DatabaseTable.id == DatabaseColumn.table_id)
        .filter(
            DatabaseColumn.table_id.in_(scope),
            DatabaseColumn.tenant_id == tenant_id,
            DatabaseTable.database_id == database_id,
        )
        .all()
    )
    if not requested_columns.issubset(valid_pairs):
        raise PermissionDenied("A scope references a column outside its table/tenant/database")


def _full_database_scope(
    db: Session,
    tenant_id: uuid.UUID,
    database_id: uuid.UUID,
) -> AccessScope:
    """Return all selected active tables and columns inside one tenant database."""
    table_ids = db.query(DatabaseTable.id).join(
        DatabaseSchema, DatabaseSchema.id == DatabaseTable.schema_id
    ).filter(
        DatabaseTable.tenant_id == tenant_id,
        DatabaseTable.database_id == database_id,
        DatabaseTable.is_active.is_(True),
        DatabaseTable.is_selected.is_(True),
        DatabaseSchema.is_selected.is_(True),
    ).all()
    scope: dict[uuid.UUID, set[uuid.UUID]] = {
        table_id: set() for (table_id,) in table_ids
    }
    if scope:
        column_rows = db.query(DatabaseColumn.table_id, DatabaseColumn.id).filter(
            DatabaseColumn.table_id.in_(scope),
            DatabaseColumn.tenant_id == tenant_id,
        ).all()
        for table_id, column_id in column_rows:
            scope[table_id].add(column_id)
    return AccessScope(
        table_columns={table_id: frozenset(column_ids) for table_id, column_ids in scope.items()}
    )


def get_effective_scope(
    db: Session,
    *,
    tenant_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    database_id: uuid.UUID | str,
    permission_code: str,
) -> AccessScope:
    """Return effective table/column access for one active tenant membership.

    Tenant administrators receive all selected active tables and columns in
    the requested tenant database for any registered permission code. Regular
    users are governed by role policies, then narrowed by their user policies.
    """
    tenant_uuid, user_uuid, database_uuid = map(_as_uuid, (tenant_id, user_id, database_id))
    database = db.query(TenantDatabase).filter(
        TenantDatabase.id == database_uuid,
        TenantDatabase.tenant_id == tenant_uuid,
    ).one_or_none()
    if database is None:
        raise PermissionDenied("Database does not belong to the requested tenant")

    membership = db.query(TenantUser).filter(
        TenantUser.tenant_id == tenant_uuid,
        TenantUser.user_id == user_uuid,
        TenantUser.status == "active",
    ).one_or_none()
    if membership is None:
        raise PermissionDenied("User has no active membership in this tenant")

    role_ids = [role_id for (role_id,) in db.query(UserRole.role_id).join(
        Role, Role.id == UserRole.role_id
    ).filter(
        UserRole.tenant_user_id == membership.id,
        (Role.tenant_id == tenant_uuid) | (Role.tenant_id.is_(None)),
    ).all()]
    if not role_ids:
        raise PermissionDenied("User has no role in this tenant")

    action_exists = db.query(Permission.id).filter(
        Permission.permission_code == permission_code
    ).first()
    if action_exists is None:
        raise PermissionDenied(f"Unknown permission action: {permission_code}")

    is_tenant_admin = db.query(Role.id).filter(
        Role.id.in_(role_ids),
        Role.tenant_id == tenant_uuid,
        Role.role_name == "admin",
    ).first()
    if is_tenant_admin is not None:
        return _full_database_scope(db, tenant_uuid, database_uuid)

    action_effects = [effect.lower() for (effect,) in db.query(RolePermission.effect)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .filter(RolePermission.role_id.in_(role_ids), Permission.permission_code == permission_code)
        .all()]
    if "deny" in action_effects or "allow" not in action_effects:
        raise PermissionDenied(f"Role does not grant action {permission_code}")

    role_policy_rows = (
        db.query(DataScopePolicy)
        .join(RoleDataScopeAssignment, RoleDataScopeAssignment.policy_id == DataScopePolicy.id)
        .filter(
            RoleDataScopeAssignment.role_id.in_(role_ids),
            DataScopePolicy.tenant_id == tenant_uuid,
            DataScopePolicy.database_id == database_uuid,
            DataScopePolicy.is_active.is_(True),
        )
        .all()
    )
    role_allows, role_denies = [], []
    for policy in role_policy_rows:
        parsed = _policy_scope(policy, permission_code)
        if parsed is None:
            continue
        effect, scope = parsed
        (role_allows if effect == "allow" else role_denies).append(scope)
    if not role_allows:
        raise PermissionDenied("No role data-scope allow policy grants this action")

    role_baseline = _union(*role_allows)
    if role_denies:
        role_baseline = _subtract(
            _expand_wildcards(db, role_baseline, tenant_uuid, database_uuid),
            _union(*role_denies),
        )

    user_policy_rows = (
        db.query(DataScopePolicy, UserDataScopeAssignment.scope_values)
        .join(UserDataScopeAssignment, UserDataScopeAssignment.policy_id == DataScopePolicy.id)
        .filter(
            UserDataScopeAssignment.tenant_user_id == membership.id,
            DataScopePolicy.tenant_id == tenant_uuid,
            DataScopePolicy.database_id == database_uuid,
            DataScopePolicy.is_active.is_(True),
        )
        .all()
    )
    user_allows, user_denies = [], []
    for policy, scope_values in user_policy_rows:
        parsed = _policy_scope(policy, permission_code, scope_values)
        if parsed is None:
            continue
        effect, scope = parsed
        (user_allows if effect == "allow" else user_denies).append(scope)

    effective = role_baseline
    if user_allows:
        effective = _intersect(effective, _union(*user_allows))
    if user_denies:
        effective = _subtract(
            _expand_wildcards(db, effective, tenant_uuid, database_uuid),
            _union(*user_denies),
        )

    _validate_scope(db, effective, tenant_uuid, database_uuid)
    # Store explicit column IDs in AccessScope so cache and Qdrant filters can
    # operate on concrete resources rather than wildcard grants.
    exact_scope = _expand_wildcards(db, effective, tenant_uuid, database_uuid)
    return AccessScope(table_columns=exact_scope)
