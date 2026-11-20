# Multi-Tenant Schema RAG POC

This project stores tenant, user, permission, and schema metadata in
PostgreSQL. It builds one searchable document per selected table, embeds the
documents, and stores the vectors and text payloads in Qdrant.

The current runnable flow covers the FastAPI authentication and permission
API plus the schema indexing CLI. The RAG query/retrieval API and LLM answer
generation are not wired into the running application yet.

## Requirements

- Python 3.12+
- Poetry
- PostgreSQL, running separately (Compose does not provide PostgreSQL)
- Docker Desktop with Docker Compose, for Qdrant
- A PostgreSQL IDE to run the demo seed SQL

## Setup

From PowerShell, install Poetry and create the project environment:

```powershell
py -m pip install poetry
poetry --version
poetry env use 3.12
poetry update
Copy-Item .env.example .env
```

Edit `.env` and set `DATABASE_URL` to your PostgreSQL application database.
For a local PostgreSQL server:

```env
DATABASE_URL=postgresql+psycopg://<username>:<password>@localhost:5432/<database>
QDRANT_URL=http://localhost:6333
```

Keep actual credentials in `.env` and do not commit it.

Apply the database migrations:

```powershell
poetry run alembic upgrade head
```

In your PostgreSQL IDE, connect to the same application database, open
`scripts/seed_multi_tenant.sql`, and execute the whole file. This seeds the
three demo tenants, users, roles, permissions, registered databases, and
schema metadata. It does not create the tenant source databases.

Demo accounts use password `Demo@12345`:

| Tenant | Admin email | Registered database |
|---|---|---|
| Tenant A - Retail | `tenant-a@example.test` | `Retail Source DB` |
| Tenant B - Healthcare | `tenant-b@example.test` | `Healthcare Source DB` |
| Tenant C - Finance | `tenant-c@example.test` | `Finance Source DB` |

Tenant A also has `tenant-a-analyst@example.test` with the same password.

## Run the application and index schemas

Start Qdrant:

```powershell
docker compose up -d qdrant
```

Start FastAPI in one terminal:

```powershell
poetry run uvicorn src.main:app --reload
```

Open `http://localhost:8000/docs` for the API docs or
`http://localhost:8000/health_check` for the health check. Current mounted
API routes cover authentication and permission administration.

Run the indexing CLI in another terminal. It prompts for the demo admin
password. Run one command at a time:

```powershell
poetry run python -m scripts.index_schema --tenant-slug tenant-a --admin-email tenant-a@example.test --database-name "Retail Source DB"
poetry run python -m scripts.index_schema --tenant-slug tenant-b --admin-email tenant-b@example.test --database-name "Healthcare Source DB"
poetry run python -m scripts.index_schema --tenant-slug tenant-c --admin-email tenant-c@example.test --database-name "Finance Source DB"
```

The first indexing run downloads the embedding model. The default batch size
is 64 tables; override it with `--batch-size`, for example
`--batch-size 32`. Re-indexing updates the same Qdrant points. The CLI reads
stored metadata from PostgreSQL; it does not save document files locally.

## Start with Docker Compose

Start Docker Desktop and make sure PostgreSQL is running. PostgreSQL is
external to this Compose project. In `.env`, set `DATABASE_URL` to an
address reachable from containers. For PostgreSQL running on the Windows
host, use `host.docker.internal` instead of `localhost`, for example:

```env
DATABASE_URL=postgresql+psycopg://<username>:<password>@host.docker.internal:5432/<database>
```

From the repository root, build and start the API, Qdrant, and Redis:

```powershell
docker compose up --build -d
```

The API container waits for Qdrant and Redis, checks the PostgreSQL
connection, runs migrations, and then starts FastAPI. Watch the startup log:

```powershell
docker compose logs -f fastapi
```

After migrations finish, run `scripts/seed_multi_tenant.sql` in your
PostgreSQL IDE as described above. Check the API at
`http://localhost:8000/health_check` and its docs at
`http://localhost:8000/docs`.

To index a tenant from a one-off Compose container, run:

```powershell
docker compose run --rm --no-deps --entrypoint python fastapi -m scripts.index_schema --tenant-slug tenant-a --admin-email tenant-a@example.test --database-name "Retail Source DB"
```

Enter `Demo@12345` at the password prompt. Change the tenant slug, admin
email, and database name to index another tenant. Stop the services with:

```powershell
docker compose down
```

## Multi-tenant workflow

### Schema indexing (implemented)

1. The CLI selects a tenant by slug and authenticates an active user.
2. It verifies that the user has an active membership and the tenant's
   `admin` role.
3. It selects the registered database for that tenant.
4. The document builder loads selected, active schema/table metadata from
   PostgreSQL. It includes table and column details, business descriptions,
   synonyms, and relationships, and omits columns marked sensitive.
5. The embedding service converts each table document to a vector.
6. The vector store upserts each vector and its text/tenant/database/table
   metadata into the shared Qdrant collection.

### Query-time RAG (planned)

The intended query flow is to authenticate the user, resolve the tenant and
database from trusted server-side context, check the user's access scope,
search Qdrant with tenant/database filters, and return only permitted
results as context for an answer. An LLM or SQL generation step can be added
after retrieval and access control are implemented and evaluated. The
query-time RAG endpoint is not currently mounted in FastAPI.

## Source modules

| Module | Purpose |
|---|---|
| `src/main.py`, `src/api/` | Create the FastAPI app and define mounted HTTP routes. |
| `src/core/` | Load configuration, logging, and the application PostgreSQL session. |
| `src/auth/` | User authentication, password checking, JWTs, and request dependencies. |
| `src/tenants/` | Tenant, membership, role models and tenant resolution. |
| `src/permissions/` | Permission checks and role/user data-scope policies. |
| `src/databases/` | Registered source database models, services, and PostgreSQL/MySQL/SQL Server connectors. |
| `src/metadata/` | Extracted schema metadata models, repositories, extractors, and table document builder. |
| `src/indexing/` | Indexing workflow and supporting job models. |
| `src/embeddings/` | Load the Hugging Face embedding model and embed documents or queries. |
| `src/vector_store/` | Qdrant client, collection setup, filters, and vector upserts. |
| `src/retrieval/`, `src/rag/` | Retrieval/RAG scaffolding; no query endpoint is currently mounted. |
| `src/audit/` | Audit log models and service. |
| `scripts/` | Demo SQL seed and schema indexing CLI. |
| `alembic/` | Application database migrations. |

PostgreSQL is the source of truth for identity, authorization, registered
databases, and schema metadata. Qdrant stores searchable vector copies of
schema documents. Tenant and database IDs are included in Qdrant payloads to
support isolation during retrieval.
