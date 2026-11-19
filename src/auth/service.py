from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.core.config import get_logger
from src.auth.models import AccessTokenBlacklist, RefreshToken, User
from src.tenants.models import Role, TenantUser, UserRole
from src.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.auth.password_helper import verify_password

logger = get_logger(__name__)


def _resolve_legacy_role(db: Session, user_id) -> str:
    """Resolve a legacy role claim only when the user has one tenant context."""
    assigned_roles = (
        db.query(TenantUser.tenant_id, Role.role_name)
        .join(UserRole, UserRole.role_id == Role.id)
        .join(TenantUser, TenantUser.id == UserRole.tenant_user_id)
        .filter(TenantUser.user_id == user_id, TenantUser.status == "active")
        .order_by(TenantUser.created_at, Role.role_name)
        .all()
    )
    tenant_ids = {tenant_id for tenant_id, _ in assigned_roles}
    if len(tenant_ids) != 1:
        return "user"
    role_names = [name for _, name in assigned_roles]
    if "admin" in role_names:
        return "admin"
    return role_names[0] if role_names else "user"


def authenticate_user(db: Session, email_address: str, password: str):
    try:
        user = db.query(User).filter(User.email_address == email_address).first()
        if not user:
            logger.warning("Authentication failed: user not found (%s)", email_address)
            return None

        if not user.is_active:
            logger.warning("Authentication failed: inactive user (%s)", email_address)
            return None

        if not verify_password(password, user.password_hash):
            logger.warning("Authentication failed: invalid password (%s)", email_address)
            return None

        logger.info("User authenticated: %s", email_address)
        return user
    except Exception:
        logger.exception("Error authenticating user: %s", email_address)
        raise


def create_tokens(db: Session, user: User):
    try:
        role = _resolve_legacy_role(db, user.id)

        access_token = create_access_token(
            user_id=str(user.user_id),
            email=user.email_address,
            role=role,
        )

        refresh_token = create_refresh_token(
            user_id=str(user.user_id),
            email=user.email_address,
            role=role,
        )

        access_payload = decode_token(access_token)
        refresh_payload = decode_token(refresh_token)

        refresh_token_record = RefreshToken(
            user_id = user.user_id,
            jti = refresh_payload["jti"],
            token = refresh_token,
            access_token_jti = access_payload.get("jti"),
            expires_at = datetime.fromtimestamp(
                refresh_payload["exp"],
                tz=timezone.utc,
            ),
            is_revoked=False,
            created_by = user.email_address,
            updated_by = user.email_address,
        )

        db.add(refresh_token_record)
        db.commit()
        logger.info("Tokens created for user: %s", user.email_address)

        return access_token, refresh_token
    except Exception:
        db.rollback()
        logger.exception("Error creating tokens for user: %s", user.email_address)
        raise


def refresh_access_token(db: Session, refresh_token: str):
    try:
        payload = decode_token(refresh_token)
    except Exception:
        logger.warning("Refresh failed: invalid token")
        return None

    if payload.get("type") != "refresh":
        logger.warning("Refresh failed: token type is not refresh")
        return None

    jti = payload.get("jti")

    if not jti:
        logger.warning("Refresh failed: missing jti claim")
        return None

    token_record = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.jti == jti,
            RefreshToken.is_revoked.is_(False),
        )
        .first()
    )

    if not token_record:
        logger.warning("Refresh failed: token not found or revoked (jti=%s)", jti)
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role")

    if not user_id or not email or not role:
        logger.warning("Refresh failed: missing claims in token")
        return None

    if token_record.access_token_jti:
        existing_blacklist = (
            db.query(AccessTokenBlacklist)
            .filter(AccessTokenBlacklist.jti == token_record.access_token_jti)
            .first()
        )
        if not existing_blacklist:
            blacklist_record = AccessTokenBlacklist(
                jti=token_record.access_token_jti,
                token="",
                expires_at=token_record.expires_at,
                created_by=email,
            )
            db.add(blacklist_record)

    new_access_token = create_access_token(
        user_id=user_id,
        email=email,
        role=role,
    )

    new_access_payload = decode_token(new_access_token)
    token_record.access_token_jti = new_access_payload.get("jti")
    token_record.updated_at = datetime.now(timezone.utc)
    token_record.updated_by = email

    db.commit()

    logger.info("Access token refreshed for user: %s", email)
    return new_access_token


def revoke_refresh_token(db: Session, refresh_token: str) -> bool:
    try:
        payload = decode_token(refresh_token)
    except Exception:
        logger.warning("Revoke failed: invalid token")
        return False

    if payload.get("type") != "refresh":
        logger.warning("Revoke failed: token type is not refresh")
        return False

    jti = payload.get("jti")

    if not jti:
        logger.warning("Revoke failed: missing jti claim")
        return False

    token_record = (
        db.query(RefreshToken)
        .filter(RefreshToken.jti == jti)
        .first()
    )

    if not token_record:
        logger.warning("Revoke failed: token not found (jti=%s)", jti)
        return False

    if token_record.is_revoked:
        logger.warning("Revoke failed: token already revoked (jti=%s)", jti)
        return False

    token_record.is_revoked = True
    token_record.revoked_at = datetime.now(timezone.utc)
    token_record.updated_at = datetime.now(timezone.utc)
    token_record.updated_by = payload.get("email")

    if token_record.access_token_jti:
        existing_blacklist = (
            db.query(AccessTokenBlacklist)
            .filter(AccessTokenBlacklist.jti == token_record.access_token_jti)
            .first()
        )
        if not existing_blacklist:
            blacklist_record = AccessTokenBlacklist(
                jti=token_record.access_token_jti,
                token="",
                expires_at=token_record.expires_at,
                created_by=payload.get("email"),
            )
            db.add(blacklist_record)

    db.commit()
    logger.info("Refresh token revoked (jti=%s)", jti)

    return True


def is_token_blacklisted(db: Session, jti: str) -> bool:
    return db.query(AccessTokenBlacklist).filter(AccessTokenBlacklist.jti == jti).first() is not None
