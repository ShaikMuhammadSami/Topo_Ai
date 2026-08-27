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
