from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.password_helper import hash_password
from src.core.config import get_logger
from src.core.database import SessionLocal
from src.permissions.models import Permission, RolePermission
from src.tenants.models import Role, Tenant, TenantUser, UserRole

logger = get_logger(__name__)

SAMPLE_USERS = (
    {"full_name": "Test User", "email": "user@example.com", "password": "user@123", "role": "user"},
    {"full_name": "Test Admin", "email": "admin@example.com", "password": "admin@123", "role": "admin"},
)
DEFAULT_TENANT_NAME = "Default Tenant"
DEFAULT_TENANT_SLUG = "default"
SAMPLE_PERMISSIONS = (
    ("metadata:read", "metadata", "read", "Read indexed metadata"),
    ("database:read", "database", "read", "View configured databases"),
    ("chat:create", "chat", "create", "Create chat sessions"),
    ("query:execute", "query", "execute", "Execute approved queries"),
    ("tenant:manage", "tenant", "manage", "Manage tenant membership and settings"),
)


def _get_or_create_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.slug == DEFAULT_TENANT_SLUG).one_or_none()
    if tenant is None:
        tenant = Tenant(
            name=DEFAULT_TENANT_NAME,
            slug=DEFAULT_TENANT_SLUG,
            status="active",
            subscription_plan="free",
        )
        db.add(tenant)
        db.flush()
    return tenant


def _get_or_create_role(db: Session, tenant_id: uuid.UUID, role_name: str) -> Role:
    role = (
        db.query(Role)
        .filter(Role.tenant_id == tenant_id, Role.role_name == role_name)
        .one_or_none()
    )
    if role is None:
        role = Role(
            tenant_id=tenant_id,
            role_name=role_name,
            description=f"Default {role_name} role",
            is_system_role=True,
        )
        db.add(role)
        db.flush()
    return role


def _ensure_membership_and_role(
    db: Session, tenant: Tenant, user: User, role_name: str
) -> None:
    membership = (
        db.query(TenantUser)
        .filter(TenantUser.tenant_id == tenant.id, TenantUser.user_id == user.id)
        .one_or_none()
    )
    if membership is None:
        membership = TenantUser(
            tenant_id=tenant.id,
            user_id=user.id,
            status="active",
            account_type="member",
            joined_at=datetime.now(timezone.utc),
        )
        db.add(membership)
        db.flush()

    role = _get_or_create_role(db, tenant.id, role_name)
    assignment = (
        db.query(UserRole)
        .filter(
            UserRole.tenant_user_id == membership.id,
            UserRole.role_id == role.id,
        )
        .one_or_none()
    )
    if assignment is None:
        db.add(UserRole(tenant_user_id=membership.id, role_id=role.id))


def _seed_permissions(db: Session, tenant_id: uuid.UUID) -> None:
    permissions = {}
    for code, resource_type, operation, description in SAMPLE_PERMISSIONS:
        permission = (
            db.query(Permission)
            .filter(Permission.permission_code == code)
            .one_or_none()
        )
        if permission is None:
            permission = Permission(
                permission_code=code,
                resource_type=resource_type,
                operation=operation,
                description=description,
            )
            db.add(permission)
            db.flush()
        permissions[code] = permission

    admin_role = _get_or_create_role(db, tenant_id, "admin")
    user_role = _get_or_create_role(db, tenant_id, "user")
    role_permissions = {
        admin_role.id: tuple(permissions.values()),
        user_role.id: tuple(
            permissions[code]
            for code in ("metadata:read", "database:read", "chat:create")
        ),
    }
    for role_id, assigned_permissions in role_permissions.items():
        for permission in assigned_permissions:
            exists = (
                db.query(RolePermission)
                .filter(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id == permission.id,
                )
                .one_or_none()
            )
            if exists is None:
                db.add(
                    RolePermission(
                        role_id=role_id,
                        permission_id=permission.id,
                        effect="allow",
                    )
                )


def seed_users() -> None:
    db = SessionLocal()
    try:
        tenant = _get_or_create_tenant(db)
        _seed_permissions(db, tenant.id)
        for sample in SAMPLE_USERS:
            user = db.query(User).filter(User.email == sample["email"]).one_or_none()
            if user is None:
                user = User(
                    full_name=sample["full_name"],
                    email=sample["email"],
                    password_hash=hash_password(sample["password"]),
                    status="active",
                )
                db.add(user)
                db.flush()
            _ensure_membership_and_role(db, tenant, user, sample["role"])

        db.commit()
        logger.info("Sample tenant, users, memberships, and roles are ready")
    except Exception:
        db.rollback()
        logger.exception("Failed to seed sample tenant and users")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_users()


