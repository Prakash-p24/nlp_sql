from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.core.database import get_db
from src.permissions.schemas import (
    DataScopePolicyCreate,
    RoleScopeAssignmentCreate,
    UserScopeAssignmentCreate,
)
from src.permissions.service import (
    PermissionDenied,
    assign_scope_policy_to_role,
    assign_scope_policy_to_user,
    create_scope_policy,
)
from src.tenants.models import Role, TenantUser, UserRole

router = APIRouter(prefix="/tenants/{tenant_id}/permissions", tags=["Permissions"])


def _require_tenant_admin(db: Session, tenant_id: UUID, user_id: UUID) -> None:
    membership = db.query(TenantUser).filter(
        TenantUser.tenant_id == tenant_id,
        TenantUser.user_id == user_id,
        TenantUser.status == "active",
    ).one_or_none()
    if membership is None:
        raise HTTPException(status_code=403, detail="Active tenant membership required")

    is_admin = db.query(UserRole.id).join(
        Role, Role.id == UserRole.role_id
    ).filter(
        UserRole.tenant_user_id == membership.id,
        Role.tenant_id == tenant_id,
        Role.role_name == "admin",
    ).first()
    if is_admin is None:
        raise HTTPException(status_code=403, detail="Tenant administrator role required")


def _actor_id(current_user: dict) -> UUID:
    try:
        return UUID(str(current_user.get("sub")))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid user identity in token") from exc


@router.post("/scope-policies", status_code=status.HTTP_201_CREATED)
def create_policy(
    tenant_id: UUID,
    request: DataScopePolicyCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_tenant_admin(db, tenant_id, _actor_id(current_user))
    if request.tenant_id != tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID in body must match URL")
    try:
        policy = create_scope_policy(
            db,
            tenant_id=tenant_id,
            database_id=request.database_id,
            policy_name=request.policy_name,
            resource_type=request.resource_type,
            scope_type=request.scope_type,
            policy_definition=request.policy_definition.model_dump(mode="json"),
        )
        db.commit()
        return {"id": policy.id, "policy_name": policy.policy_name}
    except PermissionDenied as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Policy name already exists for this database") from exc


@router.post("/role-assignments", status_code=status.HTTP_201_CREATED)
def assign_policy_to_role(
    tenant_id: UUID,
    request: RoleScopeAssignmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_tenant_admin(db, tenant_id, _actor_id(current_user))
    try:
        assignment = assign_scope_policy_to_role(
            db,
            tenant_id=tenant_id,
            role_id=request.role_id,
            policy_id=request.policy_id,
        )
        db.commit()
        return {"id": assignment.id, "role_id": assignment.role_id, "policy_id": assignment.policy_id}
    except PermissionDenied as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This policy is already assigned to the role") from exc


@router.post("/user-assignments", status_code=status.HTTP_201_CREATED)
def assign_policy_to_user(
    tenant_id: UUID,
    request: UserScopeAssignmentCreate,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_tenant_admin(db, tenant_id, _actor_id(current_user))
    try:
        assignment = assign_scope_policy_to_user(
            db,
            tenant_id=tenant_id,
            tenant_user_id=request.tenant_user_id,
            policy_id=request.policy_id,
            scope_values=request.scope_values.model_dump(mode="json", exclude_none=True)
            if request.scope_values else None,
        )
        db.commit()
        return {
            "id": assignment.id,
            "tenant_user_id": assignment.tenant_user_id,
            "policy_id": assignment.policy_id,
        }
    except PermissionDenied as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This policy is already assigned to the user") from exc
