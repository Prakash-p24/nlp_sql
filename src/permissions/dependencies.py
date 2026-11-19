from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.permissions.service import AccessScope, PermissionDenied, get_effective_scope


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
            return get_effective_scope(
                db,
                tenant_id=tenant_id,
                user_id=current_user.get("sub"),
                database_id=database_id,
                permission_code=permission_code,
            )
        except PermissionDenied as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc

    return dependency
