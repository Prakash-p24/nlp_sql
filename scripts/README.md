# Multi-Tenant RAG POC – Seed Data Summary

## 1. Overview

This document summarizes the sample data defined in the supplied multi-tenant RAG SQL seed script.

| Item | Count |
|---|---:|
| Tenant records defined | **3** |
| Application tables populated | **24** |
| Total seed rows defined across those tables | **103** |
| User accounts defined | **3** |
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
