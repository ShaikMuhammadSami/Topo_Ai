# Topo backend database operations

Run database commands from this `backend` directory. Production PostgreSQL
uses `TOPO_DATABASE_URL` and Alembic as its only schema authority. Unqualified
`postgresql://` and `postgres://` URLs use the synchronous psycopg 3 driver.

For an empty production database:

```powershell
python -m alembic -c alembic.ini heads
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini current
python -m app.db.schema_admin verify
```

## Local secrets

Copy `.env.example` to the ignored local `.env` file and replace only the
placeholders required by your environment. Never commit raw credentials or
place real credentials in example/template files; use an approved secret
source for deployed environments. Rotate or revoke any credential that is
accidentally committed.

From the repository root, check the current Git-tracked tree before opening a
pull request:

```powershell
python scripts/security/check_tracked_secrets.py
```

The check reports only a path, line number, and credential category. It does
not print the matching value and does not inspect ignored local `.env` files.

Application startup never upgrades or stamps PostgreSQL. It fails closed
unless the database is already at the application's single Alembic head.
`schema_admin verify` is the required deployment preflight: it additionally
compares the live schema with reviewed metadata and rejects out-of-band drift.
Application workers do not own migrations and do not run the full schema
comparison on every startup.

An existing database may be adopted only when it has no revision state and
its complete schema exactly matches current SQLAlchemy metadata:

```powershell
python -m app.db.schema_admin verify
python -m app.db.schema_admin adopt-current
```

`verify` is read-only. `adopt-current` first verifies tables, columns, types,
lengths, nullability, primary keys, unique constraints/indexes, ordinary
indexes, foreign keys, and server defaults. Any drift or existing revision
state is rejected; adoption does not repair Topo tables or delete legacy
tables. It only stamps the verified schema with the current revision.

`verify` prints a stable `state`, revision/head counts, schema parity, and
readable drift categories. Its automation exit codes are:

| Exit | State |
| ---: | --- |
| 0 | `CURRENT` |
| 10 | `REVISION_MISSING` |
| 11 | `REVISION_BEHIND` |
| 12 | `REVISION_AHEAD_OR_UNKNOWN` |
| 13 | `MULTIPLE_HEADS` |
| 14 | `SCHEMA_DRIFT` |
| 15 | `CONNECTION_ERROR` |
| 16 | migration-authority/configuration error |

Database connection errors are deliberately credential-free.

## Production deployment and rollback

Use one migration owner per deployment. The required order is: confirm the
database is reachable; confirm the repository has one reviewed Alembic head;
inspect the current revision; take the backup/snapshot required by the change;
run `python -m alembic -c alembic.ini upgrade head`; require
`python -m app.db.schema_admin verify` to exit 0; only then roll application
instances. Concurrent application startup is safe after migration because
workers only verify the revision.

For a new install, migrate, verify, then start the backend. For an exact
pre-existing schema without revision state, run `verify` (expect
`REVISION_MISSING` with exact parity), explicitly run `adopt-current`, verify
again, then start. Never adopt a drifted or unknown schema.

If strict verification reports drift, do not stamp the database or treat the
deployment as healthy. Investigate it and use a reviewed forward migration,
rebuild, or restore. Production rollback is a database backup/snapshot restore
or a schema-compatible application version, followed by a corrective forward
migration. `alembic downgrade base` is destructive and remains limited to
disposable migration tests.

Local development, tests, and controlled evaluation may continue using
intentional SQLite `create_all()` databases without `alembic_version`. Frozen
evaluation seeds are not migration targets.

`alembic downgrade base` drops every Topo domain table. It is only for
disposable migration tests and must never be used as a customer-data rollback.

## Disposable PostgreSQL compatibility suite

The ordinary test suite remains SQLite-compatible and skips the PostgreSQL
runtime acceptance module. To run that module, point it at a disposable
loopback PostgreSQL 16 database whose test-only role may create and drop
temporary databases:

```powershell
$env:TOPO_TEST_POSTGRES_URL = "postgresql://topo_test:<password>@127.0.0.1:<port>/topo_test"
python -m pytest tests/test_postgres_runtime_compatibility.py -q
```

The suite upgrades only disposable databases, verifies the accepted Alembic
head and ORM parity, exercises real repository/transaction behavior, and
cleans up the temporary databases it creates. Never point it at a customer or
production database.
