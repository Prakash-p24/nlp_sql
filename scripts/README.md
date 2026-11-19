# Scripts Guide and Multi-Tenant RAG Seed Data

This folder contains the schema indexing command, a local user seeder, and
the sample multi-tenant metadata SQL seed. The indexer reads schema metadata
from the application's PostgreSQL database and writes embedded table
documents to Qdrant.

## Index stored schema metadata into Qdrant

`index_schema.py` is the command-line entry point for the current
PostgreSQL-to-Qdrant indexing flow. It authenticates a tenant admin and
verifies the account's active membership and `admin` role in the selected
tenant. It then calls the dynamic document builder, embeds documents with
`BAAI/bge-small-en-v1.5`, and upserts vectors and payloads to Qdrant in
batches.

This is an admin-only operation: regular tenant users are rejected before
the document builder or embedding model is called.

### Prerequisites

- `DATABASE_URL` in `.env` connects to the PostgreSQL application database.
- That database has been migrated and already contains schema metadata
  rows for the tenant and database you want to index. The sample rows are
  defined in `seed_multi_tenant.sql`.
- Qdrant is running and reachable using `QDRANT_URL`. When running the
  indexer in Docker Compose, its Qdrant URL is set to `http://qdrant:6333`.
- The Python dependencies in `pyproject.toml` and `poetry.lock` are
  installed. The model is downloaded from Hugging Face on first use.

This repository's Compose file does not start PostgreSQL. PostgreSQL must
already be running separately. The sample SQL file seeds metadata in the
application database; it does not create the registered customer databases.

#### Connection addresses by run location

Set `DATABASE_URL` in `.env` to an address reachable from the process that
runs the indexer:

- **Docker Compose:** if PostgreSQL runs on the Windows host, use
  `host.docker.internal` as the host in `DATABASE_URL`. `localhost` inside
  the container refers to that container itself.
- **Windows / Poetry:** use `localhost` (or the PostgreSQL server's host/IP)
  when PostgreSQL is running on the same machine. PostgreSQL must allow the
  connection in `pg_hba.conf` and listen on the requested interface.

Likewise, use `QDRANT_URL=http://qdrant:6333` from a Compose container and
`QDRANT_URL=http://localhost:6333` from a process running directly on
Windows when Qdrant is published on the default port. Compose overrides the
Qdrant URL for its containers. Keep credentials in `.env`; do not put them
in command-line arguments or commit `.env`.

### Run with Docker Compose

Build or rebuild the FastAPI image when dependencies change, start
Qdrant, and run the index command from the repository root:

```powershell
docker compose build fastapi
docker compose up -d qdrant
docker compose run --rm --no-deps --entrypoint python fastapi -m scripts.index_schema --tenant-slug tenant-a --admin-email tenant-a@example.test --database-name "Retail Source DB"
```

The command prompts for the admin password. It does not accept a password
argument or save it in shell history. Do not run it with a restricted user:
the caller must be an active member with the tenant's `admin` role.

Sample database names:

| Tenant slug | Tenant admin email | Registered database |
|---|---|---|
| `tenant-a` | `tenant-a@example.test` | `Retail Source DB` |
| `tenant-b` | `tenant-b@example.test` | `Healthcare Source DB` |
| `tenant-c` | `tenant-c@example.test` | `Finance Source DB` |

If a tenant has only one registered database, `--database-name` can be
omitted. If it has multiple databases, specify the name to avoid
ambiguity.

For an installed local Poetry environment, run this from the repository
root. Make sure `.env` uses host-reachable PostgreSQL and Qdrant addresses
as described above:

```powershell
poetry run python -m scripts.index_schema --tenant-slug tenant-a --admin-email tenant-a@example.test --database-name "Retail Source DB"
```

The first run downloads the embedding model and can take longer while the
model is cached. Keep the process connected to the network for that initial
download. In Docker Compose, the cache is persisted in the
`huggingface_cache` volume.

### What the indexer writes

The indexer builds one document per selected, active table. Each document
can include schema and table names, column definitions, relationships,
business descriptions and synonyms. Columns marked sensitive in
`business_column_metadata` are excluded. The builder does not connect to
the customer database listed in `tenant_databases`; it uses metadata
already stored in the application database.

For each batch, the indexer:

1. Reads metadata for the selected tenant and database.
2. Builds LangChain documents dynamically from those records.
3. Embeds the document text with the configured embedding model.
4. Creates the Qdrant collection and payload indexes if needed.
5. Upserts each dense vector with its searchable text and metadata
   payload.

Point IDs are stable across runs, so re-indexing updates the matching
table points. The command reports the tenant, database, model,
collection, document count and batch count. `SCHEMA_INDEX_BATCH_SIZE`
sets the default batch size; override it for a run with `--batch-size`.
Docker Compose stores the Hugging Face model cache in a named volume.

The script does not remove Qdrant points for tables deleted from the
metadata database, persist job progress in `vector_index_jobs`, or expose
a retrieval API. Qdrant has payload indexes for tenant/database filters
and full-text matching, but keyword/hybrid retrieval is not implemented
yet.

## Other script notes

### `insert_user.py`

Seeds a default tenant, sample admin and user accounts, and their basic role
and permission assignments in the application database. It uses
`DATABASE_URL` from `.env`. Run it from the repository root with:

```powershell
poetry run python -m scripts.insert_user
```

The sample credentials are defined in the script and are intended only for
local development. Change or remove them before using this seeder in any
shared or production environment.

### `seed_multi_tenant.sql`

Seeds the three sample tenant metadata sets described below. Apply it to the
migrated application database using your PostgreSQL SQL client. It is safe
to re-run for the supplied IDs because inserts use `ON CONFLICT (id) DO
NOTHING`; that does not update existing rows.

`seed_multi_tenant.sql` seeds application-side metadata. It does not
create the sample customer databases themselves, create Qdrant vectors,
or populate customer, patient, sales, or invoice records. The remainder
of this README summarizes those seed rows and gives SQL verification
queries.

## 1. Overview

This document summarizes the sample data defined in the supplied multi-tenant RAG SQL seed script.

| Item | Count |
|---|---:|
| Tenant records defined | **3** |
| Application tables populated | **24** |
| Total seed rows defined across those tables | **103** |
| User accounts defined | **4** |
| Tenant database registry records defined | **3** |
| Metadata tables represented across the tenants | **6** |

> **Important:** These are the rows defined by the seed script. The script uses `ON CONFLICT (id) DO NOTHING`, so the number of newly inserted rows may be lower if matching IDs already exist. Run the verification queries against the database to confirm actual counts.

## 2. Tenants

The script defines three tenants:

| # | Tenant name | Slug | Domain |
|---:|---|---|---|
| 1 | Tenant A - Retail | `tenant-a` | Retail |
| 2 | Tenant B - Healthcare | `tenant-b` | Healthcare |
| 3 | Tenant C - Finance | `tenant-c` | Finance |

**Total tenants defined: 3**

Each tenant has one sample admin user and one registered source-database connection.

## 3. Tables populated and seed row counts

| # | Table | Rows defined |
|---:|---|---:|
| 1 | `tenants` | 3 |
| 2 | `users` | 3 |
| 3 | `tenant_users` | 3 |
| 4 | `roles` | 3 |
| 5 | `permissions` | 5 |
| 6 | `role_permissions` | 15 |
| 7 | `user_roles` | 3 |
| 8 | `data_scope_policies` | 6 |
| 9 | `role_data_scope_assignments` | 3 |
| 10 | `user_data_scope_assignments` | 3 |
| 11 | `tenant_databases` | 3 |
| 12 | `database_schemas` | 3 |
| 13 | `database_tables` | 6 |
| 14 | `database_columns` | 10 |
| 15 | `database_constraints` | 4 |
| 16 | `database_relationships` | 3 |
| 17 | `business_table_metadata` | 6 |
| 18 | `business_column_metadata` | 6 |
| 19 | `business_synonyms` | 3 |
| 20 | `vector_index_versions` | 3 |
| 21 | `vector_index_jobs` | 3 |
| 22 | `chat_sessions` | 1 |
| 23 | `chat_messages` | 2 |
| 24 | `audit_logs` | 3 |
| | **Total** | **103** |

## 4. Tenant-level sample data

| Tenant | Source DB registry | Metadata tables | Metadata columns | Vector index versions | Vector index jobs |
|---|---:|---:|---:|---:|---:|
| Tenant A - Retail | 1 | 2 | 5 | 1 | 1 |
| Tenant B - Healthcare | 1 | 2 | 4 | 1 | 1 |
| Tenant C - Finance | 1 | 2 | 2 | 1 | 1 |
| **Total** | **3** | **6** | **11** | **3** | **3** |

The `database_columns` table has 10 rows in total, as shown in the table-level count. The tenant-level column breakdown above is illustrative only if grouped from the supplied seed rows: Tenant A has 5, Tenant B has 3, and Tenant C has 2. Therefore, use the corrected breakdown below:

| Tenant | Metadata columns |
|---|---:|
| Tenant A - Retail | 5 |
| Tenant B - Healthcare | 3 |
| Tenant C - Finance | 2 |
| **Total** | **10** |

## 5. What this seed script does not create

The supplied SQL comments explicitly state that the script seeds application metadata only. It does **not**:

- Create the actual tenant-owned source databases.
- Create Qdrant collections or insert vectors.
- Create source database contents or real Qdrant vectors.
- Populate actual customer, patient, sales, invoice, or other business records in tenant source databases.

The three `tenant_databases` rows are connection-registry entries only. Their `connection_status` is seeded as `pending`.

## 6. Verification queries

Run these queries after executing the seed script to check the actual database state.

### Count tenants

```sql
SELECT COUNT(*) AS tenant_count
FROM tenants
WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c');
```

### List seeded tenants

```sql
SELECT id, name, slug, status, subscription_plan
FROM tenants
WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
ORDER BY slug;
```

### Count rows in each populated table

```sql
SELECT 'tenants' AS table_name, COUNT(*) AS row_count
FROM tenants
WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')

UNION ALL
SELECT 'users', COUNT(*)
FROM users
WHERE email IN (
    'tenant-a@example.test',
    'tenant-a-analyst@example.test',
    'tenant-b@example.test',
    'tenant-c@example.test'
)

UNION ALL
SELECT 'tenant_users', COUNT(*)
FROM tenant_users
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'roles', COUNT(*)
FROM roles
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'permissions', COUNT(*)
FROM permissions
WHERE permission_code IN (
    'DATABASE_VIEW', 'DATABASE_CONNECT', 'METADATA_VIEW',
    'INDEX_CREATE', 'CHAT_QUERY'
)

UNION ALL
SELECT 'role_permissions', COUNT(*)
FROM role_permissions
WHERE role_id IN (
    SELECT id FROM roles
    WHERE tenant_id IN (
        SELECT id FROM tenants
        WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
    )
)

UNION ALL
SELECT 'user_roles', COUNT(*)
FROM user_roles
WHERE tenant_user_id IN (
    SELECT id FROM tenant_users
    WHERE tenant_id IN (
        SELECT id FROM tenants
        WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
    )
)

UNION ALL
SELECT 'tenant_databases', COUNT(*)
FROM tenant_databases
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'database_schemas', COUNT(*)
FROM database_schemas
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'database_tables', COUNT(*)
FROM database_tables
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'database_columns', COUNT(*)
FROM database_columns
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'database_constraints', COUNT(*)
FROM database_constraints
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'database_relationships', COUNT(*)
FROM database_relationships
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'business_table_metadata', COUNT(*)
FROM business_table_metadata
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'business_column_metadata', COUNT(*)
FROM business_column_metadata
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'business_synonyms', COUNT(*)
FROM business_synonyms
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'vector_index_versions', COUNT(*)
FROM vector_index_versions
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'vector_index_jobs', COUNT(*)
FROM vector_index_jobs
WHERE version_id IN (
    SELECT id FROM vector_index_versions
    WHERE tenant_id IN (
        SELECT id FROM tenants
        WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
    )
)

UNION ALL
SELECT 'chat_sessions', COUNT(*)
FROM chat_sessions
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)

UNION ALL
SELECT 'chat_messages', COUNT(*)
FROM chat_messages
WHERE session_id IN (
    SELECT id FROM chat_sessions
    WHERE tenant_id IN (
        SELECT id FROM tenants
        WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
    )
)

UNION ALL
SELECT 'audit_logs', COUNT(*)
FROM audit_logs
WHERE tenant_id IN (
    SELECT id FROM tenants
    WHERE slug IN ('tenant-a', 'tenant-b', 'tenant-c')
)
ORDER BY table_name;
```

The seed assigns roles through `user_roles`, which connects a role to a
`tenant_users` membership. For an access-control comparison, sign in as
`tenant-a@example.test` (admin: all seeded Tenant A tables and columns) and
`tenant-a-analyst@example.test` (analyst: only `customers.customer_id` after
the individual restriction). Both use password `Demo@12345`.

## 7. Summary

The supplied seed script defines sample records for **3 tenants**, populates **24 application tables**, and contains **103 seed rows** across those tables. It provides a starting dataset for testing tenant registration, user membership, role permissions, role-level and user-level table/column scopes, source database registration, schema metadata, business metadata, indexing job records, chat history, and audit logging.

Actual inserted counts must be confirmed in PostgreSQL because conflict handling can skip rows whose IDs already exist.
