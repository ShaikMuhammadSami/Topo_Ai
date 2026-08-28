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

## Authentication mode

Authentication is required when `TOPO_AUTH_MODE` is absent or set to
`required`. Required mode must be configured with a non-empty
`TOPO_API_TOKEN_HASHES_JSON` object whose keys are lowercase SHA-256 token
digests and whose values provide a stable `subject`, optional string
`display_name`, and a JSON `roles` list. This digest registry is a transitional
bootstrap authority; raw bearer credentials must not be stored in repository
configuration or logs.

Human browsers exchange one valid transitional bearer for an opaque,
server-side session through `POST /api/v1/auth/session`. The backend persists
only SHA-256 digests for the session and CSRF secrets. It sets `topo_session`
as `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/` and sets the readable,
non-authenticating `topo_csrf` cookie with the same Secure/SameSite/Path
boundary. Unsafe cookie-authenticated human requests must echo that CSRF value
in `X-Topo-CSRF`. `GET /api/v1/auth/session` restores browser identity and
`DELETE /api/v1/auth/session` revokes the session before clearing both cookies.

Session lifetimes default to an eight-hour absolute bound and a one-hour idle
bound. They may be narrowed with positive bounded integer values in
`TOPO_SESSION_ABSOLUTE_TTL_MINUTES` and
`TOPO_SESSION_IDLE_TTL_MINUTES`; idle may not exceed absolute. Every session
use revalidates the source digest and metadata against the transitional token
registry, so removing or changing that source mapping invalidates its sessions
on their next request. A fresh exchange always creates a new independent
session and replaces the browser cookies; any older server-side session keeps
its original expiry/revocation lifecycle and is not silently extended.

Browser origins are an exact, fail-closed JSON list in
`TOPO_BROWSER_ALLOWED_ORIGINS_JSON`, for example
`["https://topo.example.com"]`. Wildcards, suffix matches, URLs with paths,
and implicit origin defaults are rejected. Bearer clients without an `Origin`
header remain supported. Production frontend traffic should use the relative
same-origin `/api` boundary; configure the private Next.js server variable
`TOPO_BACKEND_URL` as the backend rewrite destination. Never put a bearer or
session value in `NEXT_PUBLIC_*`, browser storage, or a query string.

Local SQLite development may explicitly set:

```text
TOPO_AUTH_MODE=development-disabled
```

That mode is rejected with PostgreSQL or any other non-SQLite database and
must never be used in production. `TOPO_AUTH_ENABLED=false` no longer disables
authentication; remove the legacy variable and select the new mode explicitly.

Swagger, ReDoc, and OpenAPI endpoints are unavailable in required mode and
remain available only in explicit SQLite development mode. Explicit SQLite
development mode continues to expose its synthetic principal through session
introspection without creating persistent browser sessions. The isolated
evaluation harness also uses explicit SQLite development mode temporarily
until PH-2E moves it to an ephemeral required-auth credential.

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
