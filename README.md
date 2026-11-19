# Multi-Tenant RAG POC

## PostgreSQL Application Database + Qdrant Vector Database

## 1. Project objective

Build a proof of concept (POC) for a Retrieval-Augmented Generation
(RAG) application that supports **three tenants**.

The application uses:

-   **PostgreSQL** as the central application database.
-   **Qdrant** as the vector database.
-   **FastAPI** as the backend.
-   **SQLAlchemy** for PostgreSQL access.
-   An embedding model to convert metadata documents and user questions
    into vectors.
-   An LLM in a later phase, after retrieval quality has been tested.

The POC will test whether a user from each tenant receives relevant
database metadata---tables, columns, relationships, business definitions
and synonyms---without receiving metadata belonging to another tenant.

> Terminology: this POC does not train an LLM. It indexes metadata for
> RAG: extract metadata, create documents, generate embeddings, store
> them in Qdrant, and retrieve relevant documents at question time.

------------------------------------------------------------------------

## 2. Architecture

``` text
Tenant A user     Tenant B user     Tenant C user
      \                |                /
       +---------------+---------------+
                       |
                 FastAPI backend
                       |
          Authentication and tenant resolution
                       |
             Permission validation
                       |
          +------------+-------------+
          |                          |
          v                          v
 PostgreSQL application DB       Qdrant
          |                          ^
          |                          |
          v                          |
 Metadata extraction                 |
          |                          |
 Document builder                    |
          |                          |
 Embedding model --------------------+
                                     |
User question -> Embedding -> tenant/database-filtered search
                                     |
                              Relevant documents
                                     |
                              Retrieval evaluation
                                     |
                            LLM / SQL generation
                              (later phase)
```

### Responsibility of each database

  PostgreSQL                    Qdrant
  ----------------------------- ---------------------------------------------
  Tenants and users             Vector embeddings
  Tenant-user mapping           Searchable document payload
  Database registry             Tenant/database metadata filters
  Roles and permissions         Table, column and relationship documents
  Extracted database metadata   Business descriptions and synonyms
  Indexing jobs and versions    Similarity search
  Chat and audit records        No authoritative user or permission records

PostgreSQL remains the source of truth. Qdrant stores searchable copies
of metadata documents and their vectors.

------------------------------------------------------------------------

## 3. Scope and assumptions

1.  There are three tenants in the POC.
2.  Each tenant can register one or more source databases.
3.  Source databases may be PostgreSQL, SQL Server or MySQL. The
    application database itself is PostgreSQL.
4.  All three tenants share one Qdrant collection in the initial POC.
5.  Every Qdrant point carries `tenant_id` and `database_id` payload
    fields.
6.  The backend derives tenant identity from the authenticated user. It
    never trusts a tenant ID supplied in the question.
7.  Table-level access is included. **Data-scope policies and user
    data-scope assignments are intentionally excluded** from this POC.
8.  Column-level permissions can be added later if required. For this
    POC, the table permission is the primary resource-level permission.
9.  Actual customer database records are not copied into Qdrant. Only
    schema and business metadata are indexed.

------------------------------------------------------------------------

## 4. PostgreSQL application database schema

The following DDL is a proposed implementation based on the entities
visible in the supplied ER diagram. It is a clean, normalized POC
schema, not a byte-for-byte reconstruction of every field in the image.
Confirm naming and any additional attributes against your original
design before production use.

### 4.1 Extensions

``` sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### 4.2 Tenant and user management

``` sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    subscription_plan VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(150),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tenant_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, user_id)
);
```

A user can be associated with one or more tenants. The authenticated
tenant context must be resolved and validated for each request.

### 4.3 Tenant database registry

``` sql
CREATE TABLE tenant_databases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(150) NOT NULL,
    db_type VARCHAR(30) NOT NULL,
    host VARCHAR(255),
    port INTEGER,
    database_name VARCHAR(150) NOT NULL,
    username VARCHAR(150),
    secret_reference TEXT,
    default_schema VARCHAR(150),
    connection_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    last_connected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);
```

`secret_reference` should point to a secret manager or protected
configuration. Do not store plaintext database passwords in this table,
in Qdrant, or in source code.

### 4.4 Roles and permissions

``` sql
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    role_name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, role_name)
);

CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_code VARCHAR(100) NOT NULL UNIQUE,
    permission_name VARCHAR(150) NOT NULL,
    description TEXT
);

CREATE TABLE role_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    UNIQUE (role_id, permission_id)
);

CREATE TABLE user_roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_user_id UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_user_id, role_id)
);

CREATE TABLE user_table_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_user_id UUID NOT NULL REFERENCES tenant_users(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    table_id UUID,
    permission_type VARCHAR(30) NOT NULL DEFAULT 'read',
    effect VARCHAR(10) NOT NULL DEFAULT 'allow',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_user_id, database_id, table_id, permission_type)
);
```

`user_table_permissions.table_id` is linked to `database_tables.id`
after that table is created. The FK is added below to avoid a
forward-reference issue.

### 4.5 Extracted database schema metadata

``` sql
CREATE TABLE database_schemas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    schema_name VARCHAR(150) NOT NULL,
    description TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (database_id, schema_name)
);

CREATE TABLE database_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    schema_id UUID NOT NULL REFERENCES database_schemas(id) ON DELETE CASCADE,
    table_name VARCHAR(150) NOT NULL,
    table_type VARCHAR(50),
    technical_description TEXT,
    is_selected BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (schema_id, table_name)
);

ALTER TABLE user_table_permissions
ADD CONSTRAINT fk_user_table_permissions_table
FOREIGN KEY (table_id) REFERENCES database_tables(id) ON DELETE CASCADE;

CREATE TABLE database_columns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    column_name VARCHAR(150) NOT NULL,
    data_type VARCHAR(100) NOT NULL,
    character_maximum_length INTEGER,
    numeric_precision INTEGER,
    numeric_scale INTEGER,
    is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_unique BOOLEAN NOT NULL DEFAULT FALSE,
    is_indexed BOOLEAN NOT NULL DEFAULT FALSE,
    default_value TEXT,
    ordinal_position INTEGER,
    discovered_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (table_id, column_name)
);

CREATE TABLE database_constraints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    constraint_name VARCHAR(150),
    constraint_type VARCHAR(50) NOT NULL,
    column_names JSONB NOT NULL DEFAULT '[]'::jsonb,
    referenced_schema VARCHAR(150),
    referenced_table VARCHAR(150),
    referenced_columns JSONB,
    definition TEXT,
    discovered_at TIMESTAMPTZ,
    UNIQUE (table_id, constraint_name)
);

CREATE TABLE database_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    source_table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    source_column_id UUID NOT NULL REFERENCES database_columns(id) ON DELETE CASCADE,
    target_table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    target_column_id UUID NOT NULL REFERENCES database_columns(id) ON DELETE CASCADE,
    relationship_type VARCHAR(50) NOT NULL DEFAULT 'foreign_key',
    relationship_name VARCHAR(150),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (source_column_id, target_column_id, relationship_type)
);
```

### 4.6 Business metadata

``` sql
CREATE TABLE business_table_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    business_description TEXT,
    business_purpose TEXT,
    usage_instructions TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (table_id)
);

CREATE TABLE business_column_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    table_id UUID NOT NULL REFERENCES database_tables(id) ON DELETE CASCADE,
    column_id UUID NOT NULL REFERENCES database_columns(id) ON DELETE CASCADE,
    business_description TEXT,
    business_definition TEXT,
    usage_instructions TEXT,
    sensitivity_level VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (column_id)
);

CREATE TABLE business_synonyms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    table_id UUID REFERENCES database_tables(id) ON DELETE CASCADE,
    column_id UUID REFERENCES database_columns(id) ON DELETE CASCADE,
    term VARCHAR(200) NOT NULL,
    normalized_term VARCHAR(200),
    resource_type VARCHAR(30) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.7 Optional stored-procedure metadata

Include these tables if stored procedures are part of your POC retrieval
tests. Otherwise, they can be deferred.

``` sql
CREATE TABLE database_procedures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    schema_id UUID REFERENCES database_schemas(id) ON DELETE CASCADE,
    procedure_name VARCHAR(150) NOT NULL,
    procedure_type VARCHAR(50),
    definition TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    discovered_at TIMESTAMPTZ,
    UNIQUE (database_id, schema_id, procedure_name)
);

CREATE TABLE procedure_parameters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    procedure_id UUID NOT NULL REFERENCES database_procedures(id) ON DELETE CASCADE,
    parameter_name VARCHAR(150) NOT NULL,
    data_type VARCHAR(100),
    parameter_mode VARCHAR(30),
    is_required BOOLEAN NOT NULL DEFAULT FALSE,
    default_value TEXT,
    UNIQUE (procedure_id, parameter_name)
);

CREATE TABLE business_procedure_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    procedure_id UUID NOT NULL REFERENCES database_procedures(id) ON DELETE CASCADE,
    business_description TEXT,
    usage_instructions TEXT,
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (procedure_id)
);
```

### 4.8 Qdrant indexing management

Qdrant stores the actual vectors. PostgreSQL stores indexing
configuration, versions and job status.

``` sql
CREATE TABLE vector_indexes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    collection_name VARCHAR(150) NOT NULL,
    embedding_model VARCHAR(200) NOT NULL,
    vector_dimension INTEGER NOT NULL,
    distance_metric VARCHAR(30) NOT NULL DEFAULT 'Cosine',
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, database_id)
);

CREATE TABLE vector_index_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vector_index_id UUID NOT NULL REFERENCES vector_indexes(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    document_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (vector_index_id, version_number)
);

CREATE TABLE vector_index_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vector_index_id UUID NOT NULL REFERENCES vector_indexes(id) ON DELETE CASCADE,
    job_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    total_documents INTEGER NOT NULL DEFAULT 0,
    processed_documents INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

For the initial POC, all three `vector_indexes` records can use the same
collection name, `tenant_schema_metadata`, while retaining separate
tenant/database records in PostgreSQL.

### 4.9 Chat and audit tables

These tables support later conversational testing and traceability.

``` sql
CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    database_id UUID REFERENCES tenant_databases(id) ON DELETE SET NULL,
    title VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_type VARCHAR(30) NOT NULL,
    message_content TEXT NOT NULL,
    retrieved_point_ids JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    status VARCHAR(30),
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE query_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    database_id UUID NOT NULL REFERENCES tenant_databases(id) ON DELETE CASCADE,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    generated_sql TEXT,
    validation_status VARCHAR(30),
    execution_status VARCHAR(30),
    execution_time_ms INTEGER,
    row_count INTEGER,
    error_message TEXT,
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.10 Helpful indexes

``` sql
CREATE INDEX idx_tenant_users_user
    ON tenant_users(user_id);

CREATE INDEX idx_tenant_databases_tenant
    ON tenant_databases(tenant_id);

CREATE INDEX idx_database_schemas_database
    ON database_schemas(database_id);

CREATE INDEX idx_database_tables_tenant_database
    ON database_tables(tenant_id, database_id);

CREATE INDEX idx_database_columns_table
    ON database_columns(table_id);

CREATE INDEX idx_database_relationships_database
    ON database_relationships(database_id);

CREATE INDEX idx_business_synonyms_term
    ON business_synonyms(tenant_id, normalized_term);

CREATE INDEX idx_user_table_permissions_user_database
    ON user_table_permissions(tenant_user_id, database_id);

CREATE INDEX idx_audit_logs_tenant_created
    ON audit_logs(tenant_id, created_at DESC);
```

------------------------------------------------------------------------

## 5. Three-tenant sample setup

Create three tenants and three test users. Use fictional test identities
and secure password hashes generated by your application.

``` sql
INSERT INTO tenants (name, slug, status)
VALUES
    ('Tenant A', 'tenant-a', 'active'),
    ('Tenant B', 'tenant-b', 'active'),
    ('Tenant C', 'tenant-c', 'active');
```

Create three test users through the FastAPI registration/seed script. Do
not insert plaintext passwords.

Register one source database for each tenant using `tenant_databases`.
For the POC, they can point to separate sample databases or to
controlled test databases. The application database remains the central
PostgreSQL database.

Example tenant mapping:

  Test user             Tenant
  --------------------- ----------
  user_a@example.test   Tenant A
  user_b@example.test   Tenant B
  user_c@example.test   Tenant C

The test users should only have the permissions required for their
tenant's sample tables.

------------------------------------------------------------------------

## 6. Qdrant setup

### 6.1 Run Qdrant locally

Example Docker Compose service:

``` yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: rag-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    restart: unless-stopped

volumes:
  qdrant_storage:
```

For repeatable deployments, pin a tested Qdrant image version instead of
using `latest`. Do not expose an unauthenticated Qdrant instance
publicly.

### 6.2 Create one shared collection

Use one collection for the three tenants:

``` python
from qdrant_client import QdrantClient, models

client = QdrantClient(url="http://localhost:6333")

client.create_collection(
    collection_name="tenant_schema_metadata",
    vectors_config=models.VectorParams(
        size=384,
        distance=models.Distance.COSINE
    )
)
```

The dimension `384` is an example for `BAAI/bge-small-en-v1.5`. It must
match the selected embedding model's output dimension.

### 6.3 Create payload indexes

``` python
for field in [
    "tenant_id",
    "database_id",
    "document_type",
    "table_id",
    "is_active"
]:
    client.create_payload_index(
        collection_name="tenant_schema_metadata",
        field_name=field,
        field_schema=models.PayloadSchemaType.KEYWORD
    )
```

Store UUID values as consistent strings in Qdrant payloads and use the
same representation in filters.

### 6.4 Example point payload

``` json
{
  "tenant_id": "tenant-a-uuid",
  "database_id": "database-a-uuid",
  "schema_id": "schema-a-uuid",
  "table_id": "table-a-uuid",
  "document_type": "table",
  "schema_name": "public",
  "table_name": "sales_orders",
  "is_active": true,
  "source_version": 1,
  "document_content": "Sales orders table contains customer purchase information..."
}
```

Use stable point IDs so that re-indexing updates existing points instead
of inserting duplicates.

------------------------------------------------------------------------

## 7. How to index PostgreSQL metadata into Qdrant

### 7.1 Metadata sources

  -----------------------------------------------------------------------
  Document type                       PostgreSQL source tables
  ----------------------------------- -----------------------------------
  Table document                      `database_tables`,
                                      `business_table_metadata`

  Column document                     `database_columns`,
                                      `business_column_metadata`

  Relationship document               `database_relationships`,
                                      `database_constraints`

  Business synonym document           `business_synonyms`

  Procedure document (optional)       `database_procedures`,
                                      `procedure_parameters`,
                                      `business_procedure_metadata`
  -----------------------------------------------------------------------

### 7.2 Example table document

``` text
Tenant: Tenant A
Database: Retail Database
Schema: public

Table: sales_orders

Technical description:
Stores sales order records.

Business description:
Contains customer purchase information.

Business purpose:
Used for sales reporting.

Columns:
- order_id: Unique order identifier.
- customer_id: Customer identifier.
- order_amount: Total amount of the order.
- order_date: Date of the order.

Relationships:
- sales_orders.customer_id references customers.customer_id.

Business synonyms:
- Revenue
- Sales amount
- Order value
```

### 7.3 Indexing flow

``` text
PostgreSQL metadata tables
          |
          v
Read metadata for one tenant/database
          |
          v
Combine technical + business metadata
          |
          v
Build table/column/relationship/synonym documents
          |
          v
Generate embeddings
          |
          v
Upsert points into Qdrant
          |
          v
Update vector_index_versions and vector_index_jobs
```

### 7.4 Python indexing outline

``` python
def index_database_metadata(tenant_id, database_id):

    # 1. Validate tenant/database relationship.
    # 2. Read technical schema metadata from PostgreSQL.
    # 3. Read business metadata from PostgreSQL.
    # 4. Build table, column, relationship and synonym documents.
    # 5. Generate embeddings using the selected embedding model.
    # 6. Create stable Qdrant point IDs.
    # 7. Upsert vectors and payloads into Qdrant.
    # 8. Record indexing version and job status in PostgreSQL.

    pass
```

The metadata query layer must always filter by both tenant and database
IDs. Do not load all tenants' metadata into an unrestricted indexing
job.

### 7.5 Re-indexing strategy

For this POC:

-   Initial indexing: index all selected metadata for each tenant.
-   Metadata update: rebuild and upsert the affected document.
-   Metadata deletion: delete or deactivate the corresponding Qdrant
    point.
-   Embedding model change: create a new collection or a versioned index
    and re-embed all documents.
-   Index failure: record the error in `vector_index_jobs` and allow a
    retry.

------------------------------------------------------------------------

## 8. RAG retrieval implementation

### 8.1 User request flow

Example:

``` text
Authenticated user: user_a@example.test
Resolved tenant: Tenant A
Selected database: Retail Database

Question:
"Show me the tables related to customer revenue."
```

Backend process:

1.  Validate the login/session.
2.  Resolve the user's tenant membership.
3.  Validate the selected database belongs to that tenant.
4.  Load the user's permitted tables.
5.  Generate the question embedding.
6.  Search Qdrant with mandatory tenant/database filters.
7.  Restrict results to permitted table IDs.
8.  Return the relevant documents.

### 8.2 Qdrant filter example

``` python
from qdrant_client import models

query_filter = models.Filter(
    must=[
        models.FieldCondition(
            key="tenant_id",
            match=models.MatchValue(value=tenant_id)
        ),
        models.FieldCondition(
            key="database_id",
            match=models.MatchValue(value=database_id)
        ),
        models.FieldCondition(
            key="is_active",
            match=models.MatchValue(value=True)
        )
    ]
)
```

Also restrict by the user's authorized table IDs. For example, use a
Qdrant `MatchAny` condition on `table_id` when the allowed IDs are
known. Handle relationship documents carefully: verify that both source
and target tables are permitted before including a relationship in the
LLM context. If the user has no permitted tables, return no schema
context.

### 8.3 Search example

``` python
results = client.query_points(
    collection_name="tenant_schema_metadata",
    query=query_embedding,
    query_filter=query_filter,
    limit=5,
    with_payload=True
)

for point in results.points:
    print(point.score, point.payload["document_content"])
```

Use the authenticated tenant and authorized database values from the
backend. Never accept these filter values from the natural-language
question.

------------------------------------------------------------------------

## 9. POC test plan

Use real metadata from three selected tenants. Prepare expected answers
before running retrieval tests.

### Tenant-specific tests

  -----------------------------------------------------------------------
  Tenant                  Example question        Expected retrieval
  ----------------------- ----------------------- -----------------------
  A                       Which tables store      Tenant A customer
                          customer details?       tables

  A                       Which columns contain   Tenant A sales amount
                          sales amounts?          columns

  A                       How are orders linked   Tenant A relationship
                          to customers?           metadata

  B                       Which tables store      Tenant B employee
                          employee information?   tables

  B                       Which columns contain   Tenant B salary columns
                          salary details?         

  B                       How are employees       Tenant B relationship
                          linked to departments?  metadata

  C                       Which tables store      Tenant C invoice tables
                          invoice information?    

  C                       Which columns contain   Tenant C payment
                          payment amounts?        columns

  C                       How are invoices linked Tenant C relationship
                          to vendors?             metadata
  -----------------------------------------------------------------------

Replace these sample questions with questions based on the selected
tenants' actual metadata.

### Cross-tenant isolation tests

  Authenticated tenant   Attempted question                     Expected result
  ---------------------- -------------------------------------- -----------------------
  A                      Ask about Tenant B's employee schema   No Tenant B documents
  B                      Ask about Tenant C's payment schema    No Tenant C documents
  C                      Ask about Tenant A's customer schema   No Tenant A documents

Also test: - User requests a database belonging to a different tenant. -
User asks about a table they do not have permission to access. - User
asks a question for which no matching schema metadata exists. - A
relationship connects an allowed table to a disallowed table. - A
metadata record is changed and re-indexed.

### Evaluation metrics

  -----------------------------------------------------------------------
  Metric                              Meaning
  ----------------------------------- -----------------------------------
  Recall@5                            Fraction of expected relevant
                                      documents present in top five

  Precision@5                         Fraction of top five results that
                                      are relevant

  MRR                                 Ranking position of the first
                                      relevant result

  Table accuracy                      Correct table retrieval

  Column accuracy                     Correct column retrieval

  Relationship accuracy               Correct relationship retrieval

  Tenant isolation failures           Number of unauthorized documents
                                      returned
  -----------------------------------------------------------------------

Security target: **zero unauthorized tenant or table documents in the
context returned to the LLM.**

------------------------------------------------------------------------

## 10. Development folder structure

The application uses a **modular monolithic architecture**. Each module
owns a specific responsibility, while FastAPI runs as a single backend
application.

The existing JWT authentication functionality is retained and organized
under `auth/`. API endpoints are kept separate from business logic,
database access, metadata extraction, indexing and retrieval.

``` text
multi_tenant_rag_poc/
│
├── src/
│   ├── __init__.py
│   ├── main.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── logging.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       ├── auth.py
│   │       ├── tenants.py
│   │       ├── databases.py
│   │       ├── indexing.py
│   │       └── rag.py
│   │
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   ├── dependencies.py
│   │   ├── jwt_handler.py
│   │   └── password_helper.py
│   │
│   ├── tenants/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── resolver.py
│   │
│   ├── permissions/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   └── service.py
│   │
│   ├── databases/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── connectors/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── postgres.py
│   │       ├── mysql.py
│   │       └── sqlserver.py
│   │
│   ├── metadata/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── schema_extractor.py
│   │   │   ├── table_extractor.py
│   │   │   ├── column_extractor.py
│   │   │   └── relationship_extractor.py
│   │   └── document_builder.py
│   │
│   ├── embeddings/
│   │   ├── __init__.py
│   │   ├── model.py
│   │   └── service.py
│   │
│   ├── vector_store/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── repository.py
│   │   ├── collections.py
│   │   └── filters.py
│   │
│   ├── indexing/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── job_manager.py
│   │
│   ├── retrieval/
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── service.py
│   │   └── permission_filter.py
│   │
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   └── service.py
│   │
│   └── audit/
│       ├── __init__.py
│       ├── models.py
│       └── service.py
│
├── alembic/
│   └── versions/
│
├── scripts/
│   ├── seed_tenants.py
│   ├── seed_users.py
│   └── index_metadata.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_auth.py
│   │   ├── test_tenant_resolver.py
│   │   ├── test_permissions.py
│   │   ├── test_document_builder.py
│   │   └── test_embeddings.py
│   │
│   ├── integration/
│   │   ├── test_database_connection.py
│   │   ├── test_metadata_extraction.py
│   │   ├── test_qdrant_indexing.py
│   │   └── test_rag_retrieval.py
│   │
│   └── security/
│       ├── test_tenant_isolation.py
│       └── test_table_permissions.py
│
├── docker-compose.yml
├── Dockerfile
├── docker-entrypoint.sh
├── alembic.ini
├── pyproject.toml
├── poetry.lock
├── .env.example
├── .gitignore
└── README.md
```

### 10.1 Module responsibilities

  -----------------------------------------------------------------------
  Module                              Responsibility
  ----------------------------------- -----------------------------------
  `core/`                             Application settings, central
                                      PostgreSQL session/engine, shared
                                      security utilities and logging

  `api/v1/`                           Versioned FastAPI routes and API
                                      router registration

  `auth/`                             Existing JWT authentication,
                                      password hashing, token handling
                                      and authenticated-user dependencies

  `tenants/`                          Tenant management, tenant-user
                                      mapping and authenticated tenant
                                      resolution

  `permissions/`                      Roles, permissions and table-level
                                      access validation

  `databases/`                        Tenant source-database registry and
                                      database connectors for PostgreSQL,
                                      MySQL and SQL Server

  `metadata/`                         Schema extraction, metadata
                                      persistence and technical/business
                                      metadata document construction

  `embeddings/`                       Embedding model initialization and
                                      text-to-vector generation

  `vector_store/`                     Qdrant client, collection setup,
                                      vector operations and payload
                                      filter construction

  `indexing/`                         Metadata indexing workflow, job
                                      tracking and indexing status

  `retrieval/`                        Similarity search, tenant/database
                                      filtering and table-permission
                                      filtering

  `rag/`                              Orchestration of the
                                      question-to-retrieval workflow and
                                      RAG response

  `audit/`                            Audit records for relevant user,
                                      indexing and retrieval operations

  `alembic/`                          PostgreSQL application database
                                      migrations

  `scripts/`                          Tenant/user seed scripts and
                                      metadata indexing utilities

  `tests/`                            Unit, integration and security
                                      tests
  -----------------------------------------------------------------------

### 10.2 Database connection responsibilities

The project uses separate connection responsibilities:

-   `core/database.py` manages the central PostgreSQL **application
    database** using SQLAlchemy.
-   `databases/connectors/` manages connections to tenant-owned **source
    databases** used for metadata extraction.
-   `vector_store/client.py` manages the Qdrant **vector database**
    connection.

Do not use the central application database session as a substitute for
a tenant source-database connection.

### 10.3 Existing authentication file mapping

The current authentication implementation can be moved into the new
structure as follows. Preserve its existing behavior and update imports
after moving the files.

  Existing file                           New location
  --------------------------------------- -------------------------------
  `src/main.py`                           `src/main.py`
  `src/config.py`                         `src/core/config.py`
  `src/database.py`                       `src/core/database.py`
  `src/jwt_auth/api.py`                   `src/api/v1/auth.py`
  `src/jwt_auth/models.py`                `src/auth/models.py`
  `src/jwt_auth/schema.py`                `src/auth/schemas.py`
  `src/services/jwt_auth/service.py`      `src/auth/service.py`
  `src/services/jwt_auth/dependency.py`   `src/auth/dependencies.py`
  `src/utils/jwt_handler.py`              `src/auth/jwt_handler.py`
  `src/utils/password_helper.py`          `src/auth/password_helper.py`
  `src/insert_user.py`                    `scripts/seed_users.py`

The `api/v1/auth.py` file should contain the authentication routes and
delegate authentication operations to `auth/service.py`. Keep JWT
handling and password hashing in their respective helper modules rather
than duplicating that logic in the API layer.

### 10.4 Implementation boundaries

-   API route files should validate requests, invoke services and return
    responses. They should not contain database queries or Qdrant search
    logic.
-   Service files should coordinate application workflows and enforce
    business rules.
-   Repository files should own persistence queries for their respective
    modules.
-   Tenant identity must come from the authenticated server-side
    context, not from an untrusted question or request-body field.
-   Qdrant filters must include the authenticated `tenant_id` and
    validated `database_id`.
-   Table permissions must be checked before retrieved documents are
    returned to the caller.
-   Keep the initial implementation as one FastAPI application. Separate
    microservices are not required for this POC.

## 11. API endpoints for the POC

  Method   Endpoint                           Purpose
  -------- ---------------------------------- ---------------------------------------
  POST     `/auth/login`                      Authenticate test user
  GET      `/tenants/me`                      Resolve authenticated tenant context
  GET      `/databases`                       List databases accessible to the user
  POST     `/indexing/{database_id}`          Start metadata indexing
  GET      `/indexing/{database_id}/status`   Get indexing status
  POST     `/rag/search`                      Retrieve relevant metadata documents
  GET      `/rag/search/{request_id}`         Optional retrieval audit lookup

Example request:

``` json
{
  "database_id": "database-uuid",
  "question": "Which tables store customer revenue?",
  "top_k": 5
}
```

The request does not contain a trusted `tenant_id`. Resolve the tenant
from the authenticated user's membership and validate that the database
belongs to it.

Example response:

``` json
{
  "tenant_id": "tenant-a-uuid",
  "database_id": "database-a-uuid",
  "question": "Which tables store customer revenue?",
  "results": [
    {
      "document_type": "table",
      "table_name": "sales_orders",
      "score": 0.89,
      "content": "Sales orders table contains customer purchase information..."
    }
  ]
}
```

Scores are illustrative. Actual scores depend on the embedding model and
query.

------------------------------------------------------------------------

## 12. Implementation phases

  -----------------------------------------------------------------------
  Phase                   Work                    Completion criteria
  ----------------------- ----------------------- -----------------------
  1                       Create PostgreSQL       Application tables and
                          schema                  constraints created

  2                       Seed three tenants and  Tenant membership and
                          users                   login work

  3                       Add sample source       Three tenants have
                          metadata                metadata to index

  4                       Implement permissions   Users only access
                                                  permitted tables

  5                       Run Qdrant              Collection and payload
                                                  indexes exist

  6                       Build document          Table, column,
                          generator               relationship and
                                                  synonym documents
                                                  generated

  7                       Implement embeddings    Documents converted
                                                  into vectors

  8                       Implement indexing      All three tenants
                                                  indexed

  9                       Implement retrieval     Tenant-filtered search
                                                  works

  10                      Run evaluation          30--50 test questions
                                                  evaluated

  11                      Improve retrieval       Add hybrid
                                                  search/reranking if
                                                  measurements justify it

  12                      Add LLM                 Generate SQL using
                                                  retrieved context
  -----------------------------------------------------------------------

### Recommended first milestone

Do not implement SQL generation immediately.

First complete:

1.  PostgreSQL schema.
2.  Three tenants and test users.
3.  Sample technical and business metadata.
4.  Qdrant collection.
5.  Metadata indexing.
6.  `/rag/search` endpoint.
7.  Tenant isolation and retrieval accuracy tests.

After this milestone, you will have a working multi-tenant RAG POC.

------------------------------------------------------------------------

## 13. Environment configuration

Example `.env.example`:

``` env
APP_NAME=multi-tenant-rag-poc
APP_ENV=development

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=rag_application
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change_me

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=

QDRANT_COLLECTION=tenant_schema_metadata

EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384

DEFAULT_TOP_K=5
```

Do not commit the real `.env` file or credentials to Git.

------------------------------------------------------------------------

## 14. Suggested Python dependencies

``` text
fastapi
uvicorn[standard]
sqlalchemy
psycopg[binary]
alembic
qdrant-client
sentence-transformers
pydantic-settings
python-jose[cryptography]
passlib[bcrypt]
pytest
httpx
```

Pin and test compatible versions in your project. Choose a
password-hashing library and configuration appropriate for the current
security requirements of your application.

------------------------------------------------------------------------

## 15. Important design rules

1.  PostgreSQL is the authoritative application and metadata database.
2.  Qdrant is only the vector search store; it is not the authorization
    source.
3.  Use one shared Qdrant collection for the initial three-tenant POC.
4.  Every Qdrant point must include `tenant_id` and `database_id`.
5.  Resolve tenant identity from authenticated server-side context.
6.  Validate user table permissions before returning retrieved
    documents.
7.  Do not put database passwords, personal records or sensitive
    credentials in Qdrant payloads.
8.  Keep metadata document IDs stable so indexing can be repeated
    safely.
9.  Use the same embedding model for indexing and query embedding.
10. Measure retrieval accuracy before adding an LLM.
11. Keep data-scope policies and user data-scope assignments out of this
    POC as requested.
12. Do not execute LLM-generated SQL without parsing, authorization
    checks, read-only restrictions where applicable, and query limits.

------------------------------------------------------------------------

## 16. Definition of done

The POC is complete when:

-   [ ] PostgreSQL application schema is created.
-   [ ] Three tenants and test users are created.
-   [ ] Each tenant has at least one registered source database.
-   [ ] Technical and business metadata are stored for all three
    tenants.
-   [ ] Qdrant collection and payload indexes are created.
-   [ ] Metadata documents are generated and indexed.
-   [ ] Tenant A retrieves only Tenant A's authorized metadata.
-   [ ] Tenant B retrieves only Tenant B's authorized metadata.
-   [ ] Tenant C retrieves only Tenant C's authorized metadata.
-   [ ] Table, column and relationship questions return relevant
    results.
-   [ ] Cross-tenant and unauthorized-table tests pass.
-   [ ] Retrieval evaluation results are recorded.

**Expected final outcome:** A working three-tenant RAG application that
uses your PostgreSQL application database for tenant management,
permissions and schema metadata, and Qdrant for vector storage and
semantic retrieval.
