# Role and user table/column access

The permissions module combines action permissions (for example `CHAT_QUERY`)
with data scopes (which tables and columns that action may see).

## Policy shape

`data_scope_policies.policy_definition` is JSONB:

```json
{
  "actions": ["METADATA_VIEW", "CHAT_QUERY"],
  "tables": {
    "<table-uuid>": "*",
    "<another-table-uuid>": ["<column-uuid>"]
  }
}
```

`"*"` grants every column in a table. An empty list grants visibility of the
table metadata but no columns. `scope_type` is `allowlist` or `denylist`.

## How effective access is calculated

1. The user must have an active membership in the requested tenant.
2. If the membership has that tenant's `admin` role, the administrator is
   granted every registered permission code and all selected active tables
   and columns in the requested database. This remains scoped to that tenant
   and database. Role and user data-scope policies do not narrow admin access.
3. For regular users, a role assigned to the membership must have an `allow` action permission.
   Any matching `deny` action permission wins.
4. At least one role-level allow data-scope policy must match the action. The
   union of matching role allows is the role baseline; role denies are removed.
5. Matching user-level allow scopes intersect (narrow) the role baseline.
   User-level denies are then removed. A user grant cannot add access outside
   the role baseline.
6. Missing action grants, missing role scope grants, or invalid tenant/resource
   IDs fail closed with `PermissionDenied`.

After successful login, the API checks Redis for the user's permitted table and
column IDs for each active tenant/database pair and the `METADATA_VIEW` and
`CHAT_QUERY` actions. It calculates permissions from PostgreSQL only when a
scope is missing or invalid in the cache. Scope dependencies also read this
cache first and calculate from PostgreSQL on a miss. Entries expire after
`ACCESS_SCOPE_CACHE_TTL_SECONDS` (60 seconds by default), so permission changes
take effect after the cache entry expires.

User-level data-scope policies cannot be assigned to a tenant administrator,
and role-level data-scope policies cannot be assigned to the tenant's `admin`
role. Use regular tenant roles and user assignments to apply restrictions.

## Enforce it in a FastAPI endpoint

The dependency calculates the scope for the authenticated user's `sub` claim.
The endpoint must use that scope before returning metadata, building an LLM
context, or executing generated SQL:

```python
from fastapi import APIRouter, Depends
from uuid import UUID

from src.permissions.dependencies import require_data_scope
from src.permissions.service import AccessScope
from src.retrieval.permission_filter import filter_metadata_documents

router = APIRouter()

@router.get("/tenants/{tenant_id}/databases/{database_id}/metadata")
def get_metadata(
    tenant_id: UUID,
    database_id: UUID,
    scope: AccessScope = Depends(require_data_scope("METADATA_VIEW")),
):
    records = load_metadata_from_vector_store(tenant_id, database_id)
    return filter_metadata_documents(records, scope)
```

For generated SQL, resolve table and column IDs from the parsed query, then call
`require_resources_allowed(scope, table_ids=..., columns_by_table=...)` before
execution. Do not rely on filtering the response after SQL has already run.
The current retrieval/RAG API modules do not yet execute these calls, so those
routes need this integration before the policies protect their responses.

## Create and assign policies from application code

The service exposes these transaction-scoped functions:

```python
from src.permissions.service import (
    create_scope_policy,
    assign_scope_policy_to_role,
    assign_scope_policy_to_user,
)

role_policy = create_scope_policy(
    db,
    tenant_id=tenant_id,
    database_id=database_id,
    policy_name="analyst-baseline",
    scope_type="allowlist",
    policy_definition={
        "actions": ["METADATA_VIEW", "CHAT_QUERY"],
        "tables": {
            str(customers_table_id): "*",
            str(orders_table_id): "*",
        },
    },
)
assign_scope_policy_to_role(
    db, tenant_id=tenant_id, role_id=analyst_role_id, policy_id=role_policy.id
)

user_policy = create_scope_policy(
    db,
    tenant_id=tenant_id,
    database_id=database_id,
    policy_name="analyst-user-narrowing",
    scope_type="allowlist",
    policy_definition={
        "actions": ["METADATA_VIEW", "CHAT_QUERY"],
        "tables": {str(customers_table_id): [str(customer_id_column_id)]},
    },
)
assign_scope_policy_to_user(
    db,
    tenant_id=tenant_id,
    tenant_user_id=membership_id,
    policy_id=user_policy.id,
    # Optional still-stricter subset; omit to use user_policy as written.
    scope_values={"tables": {str(customers_table_id): [str(customer_id_column_id)]}},
)
db.commit()
```

The caller must first authenticate and authorize the administrator allowed to
change role assignments. The functions validate tenant/database/resource
ownership and prevent user assignment values from widening their policy.

## Database setup and seed

Apply the schema migration, then execute `scripts/seed_multi_tenant.sql` after
the ordinary tenant, role, database, table, and column rows are available. The
seed includes admin role policies for each tenant, plus a Tenant A analyst
account. Admin access is unrestricted within the selected tenant database
regardless of those policies. The analyst receives a role policy allowing two
customer columns and a user policy narrowing access to `customer_id` only.

Demo logins (password `Demo@12345`):

- `tenant-a@example.test`: Tenant A admin; all seeded Tenant A tables/columns.
- `tenant-a-analyst@example.test`: Tenant A analyst; only
  `customers.customer_id` after user-level narrowing.
- `tenant-b@example.test` and `tenant-c@example.test`: their tenant admins.

The seed creates application metadata only. A working RAG test also needs
reachable source database contents, generated vectors in Qdrant, and the RAG
routes to apply the effective data scope before returning metadata or running
SQL. The SQL seed itself does not create source databases or Qdrant vectors.

```powershell
docker compose exec fastapi alembic upgrade head
```
