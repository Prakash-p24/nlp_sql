# Running the scripts

This guide covers the minimum setup to seed demo metadata and index it into
Qdrant.

## Install Poetry and prepare the environment

- Install Python 3.12 or newer and [Poetry](https://python-poetry.org/docs/#installation).
- PostgreSQL running separately. Docker Compose in this project does not
  start PostgreSQL.
- Docker Desktop with Docker Compose, to run Qdrant.
- A PostgreSQL IDE such as DBeaver, pgAdmin, or VS Code with a PostgreSQL
  extension, to run the demo SQL.

From the repository root, create a Pvirtual environment using Python
3.12 or newer, update the dependencies`:

```powershell
py -m venv env
env\Scripts\activate
py -m pip install poetry
poetry --version
poetry update
```

`poetry update` resolves and installs the dependencies declared in
`pyproject.toml`. Edit `.env` and set `DATABASE_URL` to your application
PostgreSQL database. For local PostgreSQL, use this format:

```env
DATABASE_URL=postgresql+psycopg://<username>:<password>@localhost:5432/<database>
QDRANT_URL=http://localhost:6333
```

Keep the real database credentials in `.env`; do not commit that file.

## Seed demo metadata


In your PostgreSQL IDE, connect to the same application database configured
in `DATABASE_URL`, open `scripts/seed_multi_tenant.sql`, and execute the
whole file. It creates the demo tenants, accounts, permissions, registered
databases, and schema metadata. It does not create the tenants' actual
source databases.

All four demo accounts use password `Demo@12345`:

| Tenant | Admin email | Registered database |
|---|---|---|
| Tenant A - Retail | `tenant-a@example.test` | `Retail Source DB` |
| Tenant B - Healthcare | `tenant-b@example.test` | `Healthcare Source DB` |
| Tenant C - Finance | `tenant-c@example.test` | `Finance Source DB` |

Tenant A also has analyst account `tenant-a-analyst@example.test`. The
indexing command requires an admin account.

## Start Qdrant and run `index_schema.py`

Start Qdrant from the repository root:

```powershell
docker compose up -d qdrant
```

Run the indexer with Poetry. It prompts for the admin password; enter
`Demo@12345` for the demo accounts. Run one command at a time:

```powershell
poetry run python -m scripts.index_schema --tenant-slug tenant-a --admin-email tenant-a@example.test --database-name "Retail Source DB"
poetry run python -m scripts.index_schema --tenant-slug tenant-b --admin-email tenant-b@example.test --database-name "Healthcare Source DB"
poetry run python -m scripts.index_schema --tenant-slug tenant-c --admin-email tenant-c@example.test --database-name "Finance Source DB"
```

`--database-name` can be omitted when a tenant has exactly one registered
database. If it has multiple databases, pass the selected database name.
To change the number of tables per batch, add `--batch-size 32` (default:
`64`).

### Indexing flow

1. Parse `--tenant-slug`, `--admin-email`, optional `--database-name`, and
   optional `--batch-size`; reject a batch size below 1.
2. Prompt for the password, find the tenant in PostgreSQL, authenticate the
   account, and require an active tenant membership with the `admin` role.
3. Select that tenant's registered database. Stop if none exists or if
   multiple databases exist and no database name was supplied.
4. Read selected, active schema/table metadata from the application database
   in batches. Build one text document per table, including columns,
   descriptions, synonyms, and relationships; omit columns marked sensitive.
5. Embed each batch using the configured Hugging Face model (default
   `BAAI/bge-small-en-v1.5`), ensure the Qdrant collection exists, and
   upsert each vector with its text and tenant/database/table metadata.
6. Print the tenant, database, model, collection, document count, and batch
   count. No document files are written to the project directory.

The first run downloads the embedding model and may take longer.

## End-to-end order

1. Install Poetry, create the environment, and run `poetry update`.
2. Configure `.env` and run `poetry run alembic upgrade head`.
3. Execute `scripts/seed_multi_tenant.sql` in the application database using
   your PostgreSQL IDE.
4. Start Qdrant with `docker compose up -d qdrant`.
5. Run `poetry run python -m scripts.index_schema ...` for each tenant.
