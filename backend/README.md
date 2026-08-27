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

Application startup never upgrades or stamps PostgreSQL. It fails closed
unless the database is already at the application's single Alembic head.

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
