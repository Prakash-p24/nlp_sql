"""Embed a tenant's stored schema metadata and upsert it into Qdrant."""

from __future__ import annotations

import argparse
from getpass import getpass
import sys

import src.model_registry  # noqa: F401 - register ORM models before querying
from sqlalchemy import select

from src.auth.service import authenticate_user
from src.core.config import EMBEDDING_MODEL, QDRANT_COLLECTION, SCHEMA_INDEX_BATCH_SIZE
from src.core.database import SessionLocal
from src.databases.models import TenantDatabase
from src.indexing.service import index_database_schema
from src.permissions.service import PermissionDenied
from src.tenants.models import Role, Tenant, TenantUser, UserRole


def _authenticate_tenant_admin(db, tenant: Tenant, email: str, password: str):
    """Authenticate the account and require its admin role in this tenant."""
    admin = authenticate_user(db, email, password)
    if admin is None:
        raise PermissionDenied("Admin email or password is invalid, or the account is inactive")

    membership = db.scalar(
        select(TenantUser).where(
            TenantUser.tenant_id == tenant.id,
            TenantUser.user_id == admin.id,
            TenantUser.status == "active",
        )
    )
    if membership is None:
        raise PermissionDenied("The authenticated user has no active membership in this tenant")

    admin_role_id = db.scalar(
        select(Role.id)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.tenant_user_id == membership.id,
            Role.tenant_id == tenant.id,
            Role.role_name == "admin",
        )
    )
    if admin_role_id is None:
        raise PermissionDenied("Tenant administrator role required; regular users cannot index schemas")
    return admin


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Admin-only: authenticate a tenant administrator, load stored schema metadata, "
            "embed table documents, and upsert vectors and payloads into Qdrant."
        )
    )
    parser.add_argument("--tenant-slug", required=True, help="Tenant slug, e.g. tenant-a")
    parser.add_argument(
        "--admin-email",
        required=True,
        help="Email address of an active administrator in the selected tenant.",
    )
    parser.add_argument(
        "--database-name",
        help="Registered source database name; required if the tenant has multiple databases.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=SCHEMA_INDEX_BATCH_SIZE,
        help=f"Tables per document/embedding batch (default: {SCHEMA_INDEX_BATCH_SIZE}).",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be greater than zero")

    try:
        admin_password = getpass("Tenant admin password: ")
        with SessionLocal() as db:
            tenant = db.scalar(select(Tenant).where(Tenant.slug == args.tenant_slug))
            if tenant is None:
                raise ValueError(f"Tenant '{args.tenant_slug}' was not found.")

            admin = _authenticate_tenant_admin(
                db,
                tenant,
                args.admin_email,
                admin_password,
            )

            database_query = select(TenantDatabase).where(
                TenantDatabase.tenant_id == tenant.id
            )
            if args.database_name:
                database_query = database_query.where(
                    TenantDatabase.name == args.database_name
                )
            databases = db.scalars(database_query.order_by(TenantDatabase.name)).all()
            if not databases:
                raise ValueError(
                    f"No registered source database found for tenant '{args.tenant_slug}'."
                )
            if len(databases) > 1:
                names = ", ".join(database.name for database in databases)
                raise ValueError(
                    f"Tenant '{args.tenant_slug}' has multiple databases ({names}); "
                    "pass --database-name."
                )

            database = databases[0]
            summary = index_database_schema(
                db,
                tenant.id,
                database.id,
                batch_size=args.batch_size,
            )

        if summary["indexed_documents"] == 0:
            raise ValueError(
                "No selected active table metadata was found for this database."
            )

        print(f"Tenant: {tenant.name} ({tenant.slug})")
        print(f"Database: {database.name} ({database.database_name})")
        print(f"Embedding model: {EMBEDDING_MODEL}")
        print(f"Qdrant collection: {QDRANT_COLLECTION}")
        print(f"Documents upserted: {summary['indexed_documents']}")
        print(f"Batches: {summary['batches']}")
        return 0
    except Exception as exc:
        print(f"Schema indexing failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
