from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from src.core.config import ACCESS_SCOPE_CACHE_TTL_SECONDS, get_logger
from src.core.redis_cache import RedisCacheError, get_text, set_text
from src.databases.models import TenantDatabase
from src.permissions.service import AccessScope, PermissionDenied, get_effective_scope
from src.tenants.models import TenantUser

logger = get_logger(__name__)
WARMED_PERMISSION_CODES = ("METADATA_VIEW", "CHAT_QUERY")


def _cache_key(user_id, tenant_id, database_id, permission_code: str) -> str:
    return f"access-scope:{user_id}:{tenant_id}:{database_id}:{permission_code}"


def _serialize_scope(scope: AccessScope) -> str:
    if any(columns is None for columns in scope.table_columns.values()):
        raise ValueError("Cached access scopes must contain explicit column IDs")
    return json.dumps(
        {
            str(table_id): sorted(map(str, columns))
            for table_id, columns in scope.table_columns.items()
        }
    )


def _deserialize_scope(value: str) -> AccessScope:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("Cached access scope must be an object")
    scope = {}
    for table_id, columns in parsed.items():
        if isinstance(columns, list):
            scope[uuid.UUID(table_id)] = frozenset(uuid.UUID(column_id) for column_id in columns)
        else:
            raise ValueError("Cached access scope contains invalid resources")
    return AccessScope(table_columns=scope)


def get_cached_scope(*, user_id, tenant_id, database_id, permission_code: str) -> AccessScope | None:
    raw = get_text(_cache_key(user_id, tenant_id, database_id, permission_code))
    return _deserialize_scope(raw) if raw is not None else None


def cache_scope(*, user_id, tenant_id, database_id, permission_code: str, scope: AccessScope) -> None:
    set_text(
        _cache_key(user_id, tenant_id, database_id, permission_code),
        _serialize_scope(scope),
        ACCESS_SCOPE_CACHE_TTL_SECONDS,
    )


def warm_user_scopes(db: Session, user_id: uuid.UUID) -> None:
    """Resolve and cache permitted resources for every active tenant database."""
    memberships = db.query(TenantUser).filter(
        TenantUser.user_id == user_id,
        TenantUser.status == "active",
    ).all()
    for membership in memberships:
        database_ids = db.query(TenantDatabase.id).filter(
            TenantDatabase.tenant_id == membership.tenant_id,
        ).all()
        for (database_id,) in database_ids:
            for permission_code in WARMED_PERMISSION_CODES:
                try:
                    if get_cached_scope(
                        user_id=user_id,
                        tenant_id=membership.tenant_id,
                        database_id=database_id,
                        permission_code=permission_code,
                    ) is not None:
                        continue
                except (RedisCacheError, ValueError, TypeError):
                    # A missing, unavailable, or malformed cache entry is a miss.
                    logger.warning(
                        "Could not read cached access scope for user %s, tenant %s, database %s",
                        user_id,
                        membership.tenant_id,
                        database_id,
                        exc_info=True,
                    )

                try:
                    scope = get_effective_scope(
                        db,
                        tenant_id=membership.tenant_id,
                        user_id=user_id,
                        database_id=database_id,
                        permission_code=permission_code,
                    )
                    cache_scope(
                        user_id=user_id,
                        tenant_id=membership.tenant_id,
                        database_id=database_id,
                        permission_code=permission_code,
                        scope=scope,
                    )
                except PermissionDenied:
                    # Lack of a grant is expected; do not cache it as an allow.
                    continue
                except Exception:
                    logger.warning(
                        "Could not cache access scope for user %s, tenant %s, database %s",
                        user_id,
                        membership.tenant_id,
                        database_id,
                        exc_info=True,
                    )
                    return
