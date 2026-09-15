"""Bounded PostgreSQL role bootstrap and runtime-grant reconciliation.

The bootstrap mode is intended for a one-time Kubernetes Job with a temporary
Secret mount. The reconcile mode runs as ``topo_migrator`` after Alembic. No
secret or connection string is ever rendered by this program.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

APP_ROLE = "topo_app"
MIGRATOR_ROLE = "topo_migrator"
APPLICATION_SCHEMA = "public"
BOOTSTRAP_LOCK_KEY = 7_321_417_001
RECONCILE_LOCK_KEY = 7_321_417_002
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MILLISECONDS = 30_000
MAX_SECRET_FILE_BYTES = 4096

BOOTSTRAP_SECRET_KEYS = (
    "database-host",
    "database-port",
    "database-name",
    "master-username",
    "master-password",
    "topo-app-password",
    "topo-migrator-password",
)


class DatabaseAdminError(RuntimeError):
    """Bounded failure code; values and driver exceptions never cross it."""


@dataclass(frozen=True, repr=False)
class BootstrapSettings:
    host: str
    port: int
    database: str
    master_username: str
    master_password: str
    app_password: str
    migrator_password: str


def _read_secret_file(directory: Path, key: str) -> str:
    try:
        path = directory / key
        content = path.read_bytes()
        if not content or len(content) > MAX_SECRET_FILE_BYTES:
            raise ValueError()
        value = content.decode("utf-8")
        if not value or "\x00" in value or "\r" in value or "\n" in value:
            raise ValueError()
        return value
    except (OSError, UnicodeError, ValueError) as exc:
        raise DatabaseAdminError("BOOTSTRAP_SECRET_INVALID") from exc


def load_bootstrap_settings(
    secret_directory: str | os.PathLike[str],
) -> BootstrapSettings:
    try:
        directory = Path(secret_directory)
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError()
        values = {
            key: _read_secret_file(directory, key) for key in BOOTSTRAP_SECRET_KEYS
        }
        port = int(values["database-port"])
        if not 1 <= port <= 65535:
            raise ValueError()
        for key in ("database-host", "database-name", "master-username"):
            value = values[key]
            if value != value.strip() or any(
                ord(character) < 32 for character in value
            ):
                raise ValueError()
        if (
            len(values["topo-app-password"]) < 32
            or len(values["topo-migrator-password"]) < 32
        ):
            raise ValueError()
        if values["topo-app-password"] == values["topo-migrator-password"]:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise DatabaseAdminError("BOOTSTRAP_SECRET_INVALID") from exc
    return BootstrapSettings(
        host=values["database-host"],
        port=port,
        database=values["database-name"],
        master_username=values["master-username"],
        master_password=values["master-password"],
        app_password=values["topo-app-password"],
        migrator_password=values["topo-migrator-password"],
    )


def _connection_options() -> dict[str, object]:
    return {
        "sslmode": "require",
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": (
            f"-c statement_timeout={STATEMENT_TIMEOUT_MILLISECONDS} "
            "-c lock_timeout=10000"
        ),
    }


def _connect(
    settings: BootstrapSettings,
    *,
    username: str,
    password: str,
) -> psycopg.Connection:
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.database,
        user=username,
        password=password,
        application_name="topo-database-bootstrap",
        **_connection_options(),
    )


def _connect_url(database_url: str) -> psycopg.Connection:
    if not database_url:
        raise DatabaseAdminError("MIGRATION_DATABASE_URL_MISSING")
    return psycopg.connect(
        database_url,
        application_name="topo-database-privilege-reconcile",
        **_connection_options(),
    )


def _acquire_lock(cursor: psycopg.Cursor, lock_key: int) -> None:
    cursor.execute("SELECT pg_catalog.pg_try_advisory_lock(%s)", (lock_key,))
    if cursor.fetchone() != (True,):
        raise DatabaseAdminError("DATABASE_ADMIN_LOCK_UNAVAILABLE")


def _release_lock(connection: psycopg.Connection, lock_key: int) -> None:
    with suppress(Exception):
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_catalog.pg_advisory_unlock(%s)", (lock_key,))
        connection.commit()


def _role_exists(cursor: psycopg.Cursor, role_name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s",
        (role_name,),
    )
    return cursor.fetchone() is not None


def _remove_role_memberships(cursor: psycopg.Cursor, role_name: str) -> None:
    cursor.execute(
        """
        SELECT granted.rolname
        FROM pg_catalog.pg_auth_members AS membership
        JOIN pg_catalog.pg_roles AS granted
          ON granted.oid = membership.roleid
        JOIN pg_catalog.pg_roles AS member
          ON member.oid = membership.member
        WHERE member.rolname = %s
        ORDER BY granted.rolname
        """,
        (role_name,),
    )
    for (granted_role,) in cursor.fetchall():
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(granted_role),
                sql.Identifier(role_name),
            )
        )


def _converge_role(
    connection: psycopg.Connection,
    cursor: psycopg.Cursor,
    *,
    role_name: str,
    password: str,
) -> None:
    if not _role_exists(cursor, role_name):
        cursor.execute(
            sql.SQL(
                "CREATE ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB "
                "NOCREATEROLE INHERIT NOREPLICATION NOBYPASSRLS"
            ).format(sql.Identifier(role_name))
        )

    encoding = connection.info.encoding
    verifier = connection.pgconn.encrypt_password(
        password.encode(encoding),
        role_name.encode(encoding),
        b"scram-sha-256",
    ).decode(encoding)
    cursor.execute(
        sql.SQL(
            "ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "INHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT -1 "
            "PASSWORD {} VALID UNTIL 'infinity'"
        ).format(sql.Identifier(role_name), sql.Literal(verifier))
    )
    cursor.execute(sql.SQL("ALTER ROLE {} RESET ALL").format(sql.Identifier(role_name)))
    _remove_role_memberships(cursor, role_name)


def _role_attributes(cursor: psycopg.Cursor, role_name: str) -> tuple:
    cursor.execute(
        """
        SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
               rolinherit, rolreplication, rolbypassrls, rolconnlimit,
               (rolvaliduntil IS NULL OR
                rolvaliduntil = 'infinity'::timestamptz),
               rolconfig IS NULL
        FROM pg_catalog.pg_roles
        WHERE rolname = %s
        """,
        (role_name,),
    )
    value = cursor.fetchone()
    if value is None:
        raise DatabaseAdminError("DATABASE_ROLE_MISSING")
    return value


def _verify_role_attributes(cursor: psycopg.Cursor) -> None:
    expected = (True, False, False, False, True, False, False, -1, True, True)
    for role_name in (APP_ROLE, MIGRATOR_ROLE):
        if _role_attributes(cursor, role_name) != expected:
            raise DatabaseAdminError("DATABASE_ROLE_ATTRIBUTE_DRIFT")
        cursor.execute(
            """
            SELECT 1
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
            WHERE member.rolname = %s
            LIMIT 1
            """,
            (role_name,),
        )
        if cursor.fetchone() is not None:
            raise DatabaseAdminError("DATABASE_ROLE_MEMBERSHIP_DRIFT")


def _ensure_ownership_boundaries(cursor: psycopg.Cursor, database_name: str) -> None:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_database AS database
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = database.datdba
            WHERE database.datname = %s AND owner.rolname IN (%s, %s)
            UNION ALL
            SELECT 1 FROM pg_catalog.pg_namespace AS namespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = namespace.nspowner
            WHERE namespace.nspname = %s AND owner.rolname IN (%s, %s)
        )
        """,
        (
            database_name,
            APP_ROLE,
            MIGRATOR_ROLE,
            APPLICATION_SCHEMA,
            APP_ROLE,
            MIGRATOR_ROLE,
        ),
    )
    if cursor.fetchone() != (False,):
        raise DatabaseAdminError("DATABASE_OR_SCHEMA_OWNERSHIP_DRIFT")

    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = relation.relowner
            WHERE namespace.nspname = %s AND owner.rolname = %s
            UNION ALL
            SELECT 1
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = procedure.proowner
            WHERE namespace.nspname = %s AND owner.rolname = %s
        )
        """,
        (APPLICATION_SCHEMA, APP_ROLE, APPLICATION_SCHEMA, APP_ROLE),
    )
    if cursor.fetchone() != (False,):
        raise DatabaseAdminError("APPLICATION_ROLE_OWNS_OBJECTS")


def _converge_database_and_schema_grants(
    cursor: psycopg.Cursor,
    database_name: str,
) -> None:
    database = sql.Identifier(database_name)
    schema = sql.Identifier(APPLICATION_SCHEMA)
    app = sql.Identifier(APP_ROLE)
    migrator = sql.Identifier(MIGRATOR_ROLE)
    cursor.execute(
        sql.SQL("REVOKE CONNECT, CREATE, TEMPORARY ON DATABASE {} FROM PUBLIC").format(
            database
        )
    )
    for role in (app, migrator):
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                database, role
            )
        )
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(database, role)
        )
    cursor.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM PUBLIC").format(schema))
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(schema, app)
    )
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON SCHEMA {} FROM {}").format(schema, migrator)
    )
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema, app))
    cursor.execute(
        sql.SQL("GRANT USAGE, CREATE ON SCHEMA {} TO {}").format(schema, migrator)
    )


def _verify_database_and_schema_grants(
    cursor: psycopg.Cursor,
    database_name: str,
) -> None:
    expected = {
        APP_ROLE: (True, False, False, True, False),
        MIGRATOR_ROLE: (True, False, False, True, True),
    }
    for role_name, role_expected in expected.items():
        cursor.execute(
            """
            SELECT pg_catalog.has_database_privilege(%s, %s, 'CONNECT'),
                   pg_catalog.has_database_privilege(%s, %s, 'CREATE'),
                   pg_catalog.has_database_privilege(%s, %s, 'TEMPORARY'),
                   pg_catalog.has_schema_privilege(%s, %s, 'USAGE'),
                   pg_catalog.has_schema_privilege(%s, %s, 'CREATE')
            """,
            (
                role_name,
                database_name,
                role_name,
                database_name,
                role_name,
                database_name,
                role_name,
                APPLICATION_SCHEMA,
                role_name,
                APPLICATION_SCHEMA,
            ),
        )
        if cursor.fetchone() != role_expected:
            raise DatabaseAdminError("DATABASE_ROLE_PRIVILEGE_DRIFT")


def _configure_default_privileges(cursor: psycopg.Cursor) -> None:
    schema = sql.Identifier(APPLICATION_SCHEMA)
    owner = sql.Identifier(MIGRATOR_ROLE)
    app = sql.Identifier(APP_ROLE)
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "REVOKE ALL PRIVILEGES ON TABLES FROM {}"
        ).format(owner, schema, app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(owner, schema, app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "REVOKE ALL PRIVILEGES ON SEQUENCES FROM {}"
        ).format(owner, schema, app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "GRANT USAGE ON SEQUENCES TO {}"
        ).format(owner, schema, app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "REVOKE ALL PRIVILEGES ON FUNCTIONS FROM {}"
        ).format(owner, schema, app)
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
            "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
        ).format(owner, schema)
    )


def _reconcile_existing_objects(cursor: psycopg.Cursor) -> None:
    schema = sql.Identifier(APPLICATION_SCHEMA)
    app = sql.Identifier(APP_ROLE)
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {} FROM {}").format(
            schema, app
        )
    )
    cursor.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}"
        ).format(schema, app)
    )
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {} FROM {}").format(
            schema, app
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA {} TO {}").format(schema, app)
    )
    cursor.execute(
        sql.SQL("REVOKE ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA {} FROM {}").format(
            schema, app
        )
    )
    cursor.execute(
        sql.SQL("REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC").format(
            schema
        )
    )

    cursor.execute("SELECT pg_catalog.to_regclass(%s)", ("public.alembic_version",))
    if cursor.fetchone() != (None,):
        version_table = sql.Identifier(APPLICATION_SCHEMA, "alembic_version")
        cursor.execute(
            sql.SQL(
                "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER "
                "ON TABLE {} FROM {}"
            ).format(version_table, app)
        )
        cursor.execute(
            sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(version_table, app)
        )


def _verify_reconcile_identity(cursor: psycopg.Cursor) -> None:
    cursor.execute("SELECT current_user")
    if cursor.fetchone() != (MIGRATOR_ROLE,):
        raise DatabaseAdminError("RECONCILE_REQUIRES_MIGRATOR")
    if _role_attributes(cursor, MIGRATOR_ROLE) != (
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        -1,
        True,
        True,
    ):
        raise DatabaseAdminError("DATABASE_ROLE_ATTRIBUTE_DRIFT")


def reconcile_connection(connection: psycopg.Connection) -> None:
    locked = False
    try:
        with connection.cursor() as cursor:
            _acquire_lock(cursor, RECONCILE_LOCK_KEY)
            locked = True
            _verify_reconcile_identity(cursor)
            _configure_default_privileges(cursor)
            _reconcile_existing_objects(cursor)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if locked:
            _release_lock(connection, RECONCILE_LOCK_KEY)


def _verify_app_connection(connection: psycopg.Connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_user,
                   pg_catalog.has_database_privilege(current_user, current_database(), 'CONNECT'),
                   pg_catalog.has_database_privilege(current_user, current_database(), 'CREATE'),
                   pg_catalog.has_database_privilege(current_user, current_database(), 'TEMPORARY'),
                   pg_catalog.has_schema_privilege(current_user, %s, 'USAGE'),
                   pg_catalog.has_schema_privilege(current_user, %s, 'CREATE')
            """,
            (APPLICATION_SCHEMA, APPLICATION_SCHEMA),
        )
        if cursor.fetchone() != (APP_ROLE, True, False, False, True, False):
            raise DatabaseAdminError("APPLICATION_ROLE_PRIVILEGE_DRIFT")
    connection.rollback()


def bootstrap_database(settings: BootstrapSettings) -> None:
    with _connect(
        settings,
        username=settings.master_username,
        password=settings.master_password,
    ) as master_connection:
        locked = False
        try:
            with master_connection.cursor() as cursor:
                _acquire_lock(cursor, BOOTSTRAP_LOCK_KEY)
                locked = True
                _converge_role(
                    master_connection,
                    cursor,
                    role_name=APP_ROLE,
                    password=settings.app_password,
                )
                _converge_role(
                    master_connection,
                    cursor,
                    role_name=MIGRATOR_ROLE,
                    password=settings.migrator_password,
                )
                _verify_role_attributes(cursor)
                _ensure_ownership_boundaries(cursor, settings.database)
                _converge_database_and_schema_grants(cursor, settings.database)
                _verify_database_and_schema_grants(cursor, settings.database)
            master_connection.commit()

            with _connect(
                settings,
                username=MIGRATOR_ROLE,
                password=settings.migrator_password,
            ) as migrator_connection:
                reconcile_connection(migrator_connection)
            with _connect(
                settings,
                username=APP_ROLE,
                password=settings.app_password,
            ) as app_connection:
                _verify_app_connection(app_connection)
        except Exception:
            master_connection.rollback()
            raise
        finally:
            if locked:
                _release_lock(master_connection, BOOTSTRAP_LOCK_KEY)


def reconcile_from_environment() -> None:
    database_url = os.environ.get("TOPO_DATABASE_URL", "")
    with _connect_url(database_url) as connection:
        reconcile_connection(connection)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Converge TopoAI PostgreSQL roles or runtime object grants."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap = subparsers.add_parser(
        "bootstrap",
        help="Use a temporary Secret mount to converge dedicated roles.",
    )
    bootstrap.add_argument(
        "--secret-dir",
        required=True,
        help="Absolute directory containing the seven bootstrap Secret files.",
    )
    subparsers.add_parser(
        "reconcile",
        help="Reconcile app grants using the topo_migrator database URL.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "bootstrap":
            bootstrap_database(load_bootstrap_settings(arguments.secret_dir))
            message = "Database role bootstrap converged."
        else:
            reconcile_from_environment()
            message = "Runtime database privileges reconciled."
    # This CLI boundary deliberately suppresses unexpected driver details as
    # well as expected bounded failures so credentials cannot leak in a trace.
    except Exception:  # noqa: BLE001
        print("Topo database administration failed safely.", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
