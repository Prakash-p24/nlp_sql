from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.core.config import get_logger
from src.core.redis_cache import RedisCacheError
from src.permissions.service import AccessScope, PermissionDenied, get_effective_scope
from src.permissions.scope_cache import cache_scope, get_cached_scope

logger = get_logger(__name__)


def require_data_scope(permission_code: str):
    """FastAPI dependency for endpoints that access tenant database metadata.

    The endpoint must accept tenant_id and database_id path/query parameters.
    It receives an AccessScope and must apply it to retrieval and query planning.
    """
    def dependency(
        tenant_id: UUID,
        database_id: UUID,
        current_user: dict = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> AccessScope:
        try:
            try:
                cached_scope = get_cached_scope(
                    user_id=current_user.get("sub"),
                    tenant_id=tenant_id,
                    database_id=database_id,
                    permission_code=permission_code,
                )
                if cached_scope is not None:
                    return cached_scope
            except (RedisCacheError, ValueError, TypeError):
                logger.warning("Could not read cached access scope; resolving from database", exc_info=True)

            scope = get_effective_scope(
                db,
                tenant_id=tenant_id,
                user_id=current_user.get("sub"),
                database_id=database_id,
                permission_code=permission_code,
            )
            try:
                cache_scope(
                    user_id=current_user.get("sub"),
                    tenant_id=tenant_id,
                    database_id=database_id,
                    permission_code=permission_code,
                    scope=scope,
                )
            except RedisCacheError:
                logger.warning("Could not cache resolved access scope", exc_info=True)
            return scope
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc

    return dependency
