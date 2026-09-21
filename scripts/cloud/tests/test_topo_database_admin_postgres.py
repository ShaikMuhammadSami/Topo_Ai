"""Optional PostgreSQL 16 acceptance for the C2 database authority contract.

Set ``TOPO_C2_TEST_POSTGRES_URL`` to a disposable, empty PostgreSQL database
owned by the URL's fixture superuser. The superuser only constructs an
RDS-master-like non-superuser and controlled drift; the actual Topo bootstrap
runs as that restricted administrator. The test deliberately disables TLS only
for that loopback disposable database; production source always requires TLS.
"""

from __future__ import annotations

import importlib.util
import os
import secrets
import sys
from argparse import Namespace
from pathlib import Path

import psycopg
import pytest
from alembic import command
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
if os.fspath(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(BACKEND_ROOT))

from app.db.schema_management import alembic_config

ADMIN_PATH = ROOT / "scripts/cloud/topo_database_admin.py"
SPEC = importlib.util.spec_from_file_location(
    "topo_database_admin_postgres", ADMIN_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load database administration utility.")
ADMIN = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ADMIN
SPEC.loader.exec_module(ADMIN)

POSTGRES_URL = os.getenv("TOPO_C2_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TOPO_C2_TEST_POSTGRES_URL to run the disposable PostgreSQL test",
)
RDS_LIKE_ADMIN_ROLE = "topo_c2_bootstrap_admin"


def _local_options() -> dict[str, object]:
    return {
        "sslmode": "disable",
        "connect_timeout": ADMIN.CONNECT_TIMEOUT_SECONDS,
        "options": (
            f"-c statement_timeout={ADMIN.STATEMENT_TIMEOUT_MILLISECONDS} "
            "-c lock_timeout=10000"
        ),
    }


def _role_url(
    parsed,
    *,
    username: str,
    password: str,
    sqlalchemy: bool = False,
) -> str:
    return URL.create(
        "postgresql+psycopg" if sqlalchemy else "postgresql",
        username=username,
        password=password,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
    ).render_as_string(hide_password=False)


def _expect_denied(connection_url: str, statement: str) -> None:
    with (
        psycopg.connect(connection_url, sslmode="disable") as connection,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
        connection.cursor() as cursor,
    ):
        cursor.execute(statement)


def _create_rds_like_admin(
    superuser_url: str,
    *,
    database_name: str,
    password: str,
) -> None:
    """Use fixture superuser authority only to create the restricted actor."""
    with psycopg.connect(superuser_url, sslmode="disable") as superuser:
        encoding = superuser.info.encoding
        verifier = superuser.pgconn.encrypt_password(
            password.encode(encoding),
            RDS_LIKE_ADMIN_ROLE.encode(encoding),
            b"scram-sha-256",
        ).decode(encoding)
        with superuser.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "CREATE ROLE {} WITH LOGIN NOSUPERUSER CREATEDB CREATEROLE "
                    "INHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(
                    sql.Identifier(RDS_LIKE_ADMIN_ROLE),
                    sql.Literal(verifier),
                )
            )
            cursor.execute(
                sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier(RDS_LIKE_ADMIN_ROLE),
                )
            )
        superuser.commit()


def _assert_rds_like_admin(superuser_url: str) -> None:
    with (
        psycopg.connect(superuser_url, sslmode="disable") as superuser,
        superuser.cursor() as cursor,
    ):
        cursor.execute(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolinherit, rolreplication, rolbypassrls
            FROM pg_catalog.pg_roles
            WHERE rolname = %s
            """,
            (RDS_LIKE_ADMIN_ROLE,),
        )
        assert cursor.fetchone() == (True, False, True, True, True, False, False)


def test_real_postgres_rds_like_bootstrap_migration_and_reconciliation(
    monkeypatch,
) -> None:
    parsed = make_url(POSTGRES_URL)
    if not all(
        (parsed.host, parsed.port, parsed.database, parsed.username, parsed.password)
    ):
        pytest.fail(
            "TOPO_C2_TEST_POSTGRES_URL must contain host, port, db, user, password"
        )

    app_password = secrets.token_urlsafe(48)
    migrator_password = secrets.token_urlsafe(48)
    rds_like_admin_password = secrets.token_urlsafe(48)
    _create_rds_like_admin(
        POSTGRES_URL,
        database_name=parsed.database,
        password=rds_like_admin_password,
    )
    _assert_rds_like_admin(POSTGRES_URL)
    settings = ADMIN.BootstrapSettings(
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
        master_username=RDS_LIKE_ADMIN_ROLE,
        master_password=rds_like_admin_password,
        app_password=app_password,
        migrator_password=migrator_password,
    )
    monkeypatch.setattr(ADMIN, "_connection_options", _local_options)

    # A second identical invocation is the required recovery for an ambiguous
    # first Job outcome.
    ADMIN.bootstrap_database(settings)
    ADMIN.bootstrap_database(settings)

    app_url = _role_url(
        parsed,
        username=ADMIN.APP_ROLE,
        password=app_password,
    )
    migrator_url = _role_url(
        parsed,
        username=ADMIN.MIGRATOR_ROLE,
        password=migrator_password,
    )
    migrator_engine_url = _role_url(
        parsed,
        username=ADMIN.MIGRATOR_ROLE,
        password=migrator_password,
        sqlalchemy=True,
    )

    with (
        psycopg.connect(POSTGRES_URL, sslmode="disable") as master,
        master.cursor() as cursor,
    ):
        cursor.execute(
            """
                SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                       rolinherit, rolreplication, rolbypassrls, rolconnlimit,
                       (rolvaliduntil IS NULL OR
                        rolvaliduntil = 'infinity'::timestamptz),
                       rolconfig IS NULL
                FROM pg_catalog.pg_roles
                WHERE rolname IN (%s, %s)
                ORDER BY rolname
                """,
            (ADMIN.APP_ROLE, ADMIN.MIGRATOR_ROLE),
        )
        assert cursor.fetchall() == [
            (
                ADMIN.APP_ROLE,
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
            ),
            (
                ADMIN.MIGRATOR_ROLE,
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
            ),
        ]
        cursor.execute(
            """
            SELECT member.rolname, granted.rolname
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS member ON member.oid = membership.member
            JOIN pg_catalog.pg_roles AS granted ON granted.oid = membership.roleid
            WHERE member.rolname IN (%s, %s)
            ORDER BY member.rolname, granted.rolname
            """,
            (ADMIN.APP_ROLE, ADMIN.MIGRATOR_ROLE),
        )
        assert cursor.fetchall() == []

    engine = create_engine(
        migrator_engine_url,
        connect_args={"sslmode": "disable"},
        pool_pre_ping=True,
    )
    try:
        with engine.begin() as connection:
            config = alembic_config(connection=connection)
            config.cmd_opts = Namespace(x=[])
            command.upgrade(config, "head")
    finally:
        engine.dispose()

    with psycopg.connect(migrator_url, sslmode="disable") as migrator:
        ADMIN.reconcile_connection(migrator)
    with psycopg.connect(migrator_url, sslmode="disable") as migrator:
        ADMIN.reconcile_connection(migrator)

    with (
        psycopg.connect(app_url, sslmode="disable") as app,
        app.cursor() as cursor,
    ):
        cursor.execute(
            """
                INSERT INTO public.tenants
                    (tenant_id, display_name, status, created_at, updated_at,
                     created_by_subject)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
            (
                "tenant:c2a1",
                "C2-A1 acceptance",
                "active",
                "2026-09-15T00:00:00Z",
                "2026-09-15T00:00:00Z",
                "test:bootstrap",
            ),
        )
        cursor.execute(
            "UPDATE public.tenants SET display_name = %s WHERE tenant_id = %s",
            ("C2-A1 updated", "tenant:c2a1"),
        )
        cursor.execute(
            "SELECT display_name FROM public.tenants WHERE tenant_id = %s",
            ("tenant:c2a1",),
        )
        assert cursor.fetchone() == ("C2-A1 updated",)
        cursor.execute(
            "DELETE FROM public.tenants WHERE tenant_id = %s",
            ("tenant:c2a1",),
        )
        cursor.execute("SELECT version_num FROM public.alembic_version")
        assert cursor.fetchone() == ("0015_security_audit",)

    _expect_denied(app_url, "CREATE TABLE public.c2a1_forbidden (id integer)")
    _expect_denied(app_url, "ALTER TABLE public.tenants ADD COLUMN forbidden text")
    _expect_denied(app_url, "DROP TABLE public.tenants")
    _expect_denied(
        app_url,
        "UPDATE public.alembic_version SET version_num = 'forbidden'",
    )
    _expect_denied(app_url, "DELETE FROM public.alembic_version")
    _expect_denied(
        app_url,
        "INSERT INTO public.alembic_version (version_num) VALUES ('forbidden')",
    )

    with psycopg.connect(migrator_url, sslmode="disable") as migrator:
        with migrator.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE public.c2a1_future_table "
                "(id integer PRIMARY KEY, value text NOT NULL)"
            )
            cursor.execute("CREATE SEQUENCE public.c2a1_future_sequence")
        migrator.commit()

    with (
        psycopg.connect(app_url, sslmode="disable") as app,
        app.cursor() as cursor,
    ):
        cursor.execute(
            "INSERT INTO public.c2a1_future_table (id, value) VALUES (1, 'ok')"
        )
        cursor.execute(
            "UPDATE public.c2a1_future_table SET value = 'updated' WHERE id = 1"
        )
        cursor.execute("SELECT value FROM public.c2a1_future_table WHERE id = 1")
        assert cursor.fetchone() == ("updated",)
        cursor.execute("SELECT nextval('public.c2a1_future_sequence')")
        assert cursor.fetchone() == (1,)
        cursor.execute("DELETE FROM public.c2a1_future_table WHERE id = 1")

    # Simulate dangerous drift and prove an identical bootstrap narrows it.
    with psycopg.connect(POSTGRES_URL, sslmode="disable") as master:
        with master.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} CREATEDB").format(sql.Identifier(ADMIN.APP_ROLE))
            )
        master.commit()
    ADMIN.bootstrap_database(settings)
    with psycopg.connect(POSTGRES_URL, sslmode="disable") as master:
        with master.cursor() as cursor:
            cursor.execute(
                "SELECT rolcreatedb FROM pg_catalog.pg_roles WHERE rolname = %s",
                (ADMIN.APP_ROLE,),
            )
            assert cursor.fetchone() == (False,)

            # Hold the same session lock to prove a racing bootstrap fails
            # before changing any role/grant state.
            cursor.execute(
                "SELECT pg_catalog.pg_advisory_lock(%s)",
                (ADMIN.BOOTSTRAP_LOCK_KEY,),
            )
            master.commit()
            with pytest.raises(
                ADMIN.DatabaseAdminError,
                match="^DATABASE_ADMIN_LOCK_UNAVAILABLE$",
            ):
                ADMIN.bootstrap_database(settings)
            cursor.execute(
                "SELECT pg_catalog.pg_advisory_unlock(%s)",
                (ADMIN.BOOTSTRAP_LOCK_KEY,),
            )
        master.commit()

    # A restricted RDS-style administrator must not attempt to clear elevated
    # flags it cannot legally manage. The preflight detects and rejects them
    # before normal ALTER convergence.
    try:
        with psycopg.connect(POSTGRES_URL, sslmode="disable") as superuser:
            with superuser.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER ROLE {} BYPASSRLS").format(
                        sql.Identifier(ADMIN.APP_ROLE)
                    )
                )
            superuser.commit()

        with pytest.raises(
            ADMIN.DatabaseAdminError,
            match="^DATABASE_ROLE_UNSAFE_ELEVATED_ATTRIBUTE$",
        ):
            ADMIN.bootstrap_database(settings)

        with (
            psycopg.connect(POSTGRES_URL, sslmode="disable") as superuser,
            superuser.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT rolbypassrls FROM pg_catalog.pg_roles WHERE rolname = %s",
                (ADMIN.APP_ROLE,),
            )
            assert cursor.fetchone() == (True,)
    finally:
        with psycopg.connect(POSTGRES_URL, sslmode="disable") as superuser:
            with superuser.cursor() as cursor:
                cursor.execute(
                    sql.SQL("ALTER ROLE {} NOBYPASSRLS").format(
                        sql.Identifier(ADMIN.APP_ROLE)
                    )
                )
            superuser.commit()
