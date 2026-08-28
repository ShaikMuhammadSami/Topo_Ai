"""Opt-in PostgreSQL migration-operations acceptance for PH-1D.

The suite creates and drops isolated databases derived from
``TOPO_TEST_POSTGRES_URL``. It never targets the configured database itself.
Set ``TOPO_TEST_POSTGRES_CONTAINER`` to exercise pg_dump/pg_restore inside the
disposable PostgreSQL container.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.db import models as db_models
from app.db import schema_admin
from app.db.database import Base, _synchronous_database_url, init_db
from app.db.schema_admin import SchemaAdminExitCode
from app.db.schema_management import (
    MultipleMigrationHeadsError,
    SchemaAuthorityError,
    SchemaAuthorityState,
    SchemaVerification,
    adopt_current_schema,
    alembic_config,
    current_revisions,
    expected_head,
    inspect_schema_authority,
)


POSTGRES_URL = os.getenv("TOPO_TEST_POSTGRES_URL", "").strip()
POSTGRES_CONTAINER = os.getenv("TOPO_TEST_POSTGRES_CONTAINER", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TOPO_TEST_POSTGRES_URL to run PostgreSQL operations tests",
)

NOW = "2026-08-28T12:00:00+00:00"
DOMAIN_TABLE_NAMES = tuple(sorted(Base.metadata.tables))
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
DEVELOPER_DB = BACKEND_DIR / "data" / "topo.db"
FROZEN_DB = (
    REPOSITORY_ROOT
    / "evaluation"
    / "results"
    / "lineage"
    / "post-sc4"
    / "topo-product-32695735269.db"
)
DEVELOPER_DB_SHA256 = (
    "c3a2ab62dc6b8b8c68dedfd26b858ebb3bb7199323217be96b7764aef7821baf"
)
FROZEN_DB_SHA256 = (
    "9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f"
)


def _postgres_url() -> str:
    return _synchronous_database_url(POSTGRES_URL)


def _database_identifier(prefix: str) -> str:
    value = f"topo_ph1d_{prefix}_{uuid4().hex[:12]}"
    assert re.fullmatch(r"[a-z0-9_]+", value)
    return value


def _drop_database(admin: Engine, database_name: str) -> None:
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :database_name AND pid <> pg_backend_pid()"
            ),
            {"database_name": database_name},
        )
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')


@contextmanager
def _temporary_database(prefix: str):
    base_url = make_url(_postgres_url())
    database_name = _database_identifier(prefix)
    admin = create_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    engine = create_engine(base_url.set(database=database_name), pool_pre_ping=True)
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        yield engine, database_name
    finally:
        engine.dispose()
        _drop_database(admin, database_name)
        admin.dispose()


def _upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection=connection), revision)


def _domain_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names()) & set(DOMAIN_TABLE_NAMES)


def _schema_summary(engine: Engine) -> str:
    """Return deterministic reviewed domain structure, excluding Alembic state."""
    inspector = inspect(engine)
    summary: list[dict[str, object]] = []
    for table_name in sorted(_domain_tables(engine)):
        summary.append(
            {
                "table": table_name,
                "columns": [
                    {
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column["nullable"],
                        "default": column.get("default"),
                    }
                    for column in inspector.get_columns(table_name)
                ],
                "primary_key": inspector.get_pk_constraint(table_name).get(
                    "constrained_columns"
                ),
                "unique_constraints": sorted(
                    (
                        item.get("name") or "",
                        tuple(item.get("column_names") or ()),
                    )
                    for item in inspector.get_unique_constraints(table_name)
                ),
                "indexes": sorted(
                    (
                        item.get("name") or "",
                        tuple(item.get("column_names") or ()),
                        bool(item.get("unique")),
                    )
                    for item in inspector.get_indexes(table_name)
                    if not item.get("duplicates_constraint")
                ),
                "foreign_keys": sorted(
                    json.dumps(item, sort_keys=True, default=str)
                    for item in inspector.get_foreign_keys(table_name)
                ),
            }
        )
    return json.dumps(summary, sort_keys=True, separators=(",", ":"))


def _mapper_for(table_name: str):
    return next(
        mapper
        for mapper in Base.registry.mappers
        if mapper.local_table.name == table_name
    )


def _column_value(table_name: str, column, row: int):
    if isinstance(column.type, Boolean):
        return False
    if isinstance(column.type, Integer):
        return row
    if isinstance(column.type, Float):
        return float(row)
    if isinstance(column.type, (String, Text)):
        if column.name.endswith("_at"):
            return NOW
        if column.name.endswith("_json"):
            return json.dumps({"ph1d": table_name, "row": row}, sort_keys=True)
        value = f"{table_name}:{column.name}:ph1d-{row}"
        length = getattr(column.type, "length", None)
        return value[:length] if length else value
    raise AssertionError(f"unsupported fixture type: {table_name}.{column.name}")


def _record(table_name: str, row: int, **overrides):
    values = {
        column.name: _column_value(table_name, column, row)
        for column in Base.metadata.tables[table_name].columns
    }
    values.update(overrides)
    return _mapper_for(table_name).class_(**values)


def _seed_representative_history(engine: Engine) -> dict[str, str]:
    identifiers = {
        "snapshot_id": "snapshot:ph1d-preserved",
        "signal_id": "signal:ph1d-preserved",
        "incident_id": "incident:ph1d-preserved",
        "analysis_id": "analysis:ph1d-preserved",
        "change_event_id": "change-event:ph1d-preserved",
        "ownership_id": "ownership:ph1d-preserved",
    }
    snapshot_payload = json.dumps(
        {"snapshot_id": identifiers["snapshot_id"], "nested": [1, {"ok": True}]},
        sort_keys=True,
        separators=(",", ":"),
    )
    causal_payload = json.dumps(
        {
            "analysis_id": identifiers["analysis_id"],
            "incident_id": identifiers["incident_id"],
            "evidence": ["evidence:ph1d"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with Session(engine) as session:
        session.add_all(
            [
                _record(
                    "topology_snapshots",
                    1,
                    snapshot_id=identifiers["snapshot_id"],
                    collected_at=NOW,
                    payload_json=snapshot_payload,
                ),
                _record(
                    "signals",
                    2,
                    signal_id=identifiers["signal_id"],
                    first_observed_at=NOW,
                    last_observed_at=NOW,
                ),
                _record(
                    "incidents",
                    3,
                    incident_id=identifiers["incident_id"],
                    topology_snapshot_id=identifiers["snapshot_id"],
                    first_observed_at=NOW,
                    last_observed_at=NOW,
                ),
                _record(
                    "causal_analyses",
                    4,
                    analysis_id=identifiers["analysis_id"],
                    incident_id=identifiers["incident_id"],
                    payload_json=causal_payload,
                    generated_at=NOW,
                ),
                _record(
                    "change_events",
                    5,
                    event_id=identifiers["change_event_id"],
                    occurred_at=NOW,
                ),
                _record(
                    "ownership_mappings",
                    6,
                    ownership_id=identifiers["ownership_id"],
                ),
            ]
        )
        session.commit()
    return {**identifiers, "snapshot_payload": snapshot_payload, "causal_payload": causal_payload}


def _synthetic_config(tmp_path: Path, connection, failure_body: str) -> Config:
    scripts = tmp_path / f"ph1d_scripts_{uuid4().hex}"
    versions = scripts / "versions"
    versions.mkdir(parents=True)
    (scripts / "env.py").write_text(
        "from alembic import context\n"
        "connection = context.config.attributes['connection']\n"
        "context.configure(connection=connection)\n"
        "with context.begin_transaction():\n"
        "    context.run_migrations()\n",
        encoding="utf-8",
    )
    (versions / "failure.py").write_text(
        "from alembic import op\n"
        "import sqlalchemy as sa\n"
        "revision = 'ph1d_failure'\n"
        "down_revision = None\n"
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade():\n"
        f"{failure_body}\n"
        "def downgrade():\n"
        "    pass\n",
        encoding="utf-8",
    )
    config = Config()
    config.set_main_option("script_location", str(scripts))
    config.attributes["connection"] = connection
    return config


def test_fresh_install_strict_verify_and_restart_are_stable() -> None:
    with _temporary_database("fresh") as (engine, _):
        with pytest.raises(SchemaAuthorityError, match="state=missing"):
            init_db(bind=engine)
        assert _domain_tables(engine) == set()

        _upgrade(engine)
        before = _schema_summary(engine)
        with engine.connect() as connection:
            report = inspect_schema_authority(connection)
        assert report.state is SchemaAuthorityState.CURRENT
        assert report.ok
        with engine.connect() as connection:
            assert current_revisions(connection) == (expected_head(),)

        for _ in range(3):
            init_db(bind=engine)
        assert _schema_summary(engine) == before
        with engine.connect() as connection:
            assert current_revisions(connection) == (expected_head(),)


def test_exact_schema_adoption_changes_only_revision_state() -> None:
    with _temporary_database("adopt") as (engine, _):
        Base.metadata.create_all(engine)
        before = _schema_summary(engine)
        with engine.begin() as connection:
            report = inspect_schema_authority(connection)
            assert report.state is SchemaAuthorityState.REVISION_MISSING
            assert report.schema_matches
            with pytest.raises(SchemaAuthorityError, match="state=missing"):
                init_db(bind=engine)
            adopted = adopt_current_schema(connection)
        assert adopted.state is SchemaAuthorityState.CURRENT
        assert _schema_summary(engine) == before
        init_db(bind=engine)


@pytest.mark.parametrize("drift_kind", ["extra_table", "missing_index"])
def test_current_revision_with_schema_drift_fails_strict_preflight(
    drift_kind: str,
) -> None:
    with _temporary_database(f"drift_{drift_kind}") as (engine, _):
        _upgrade(engine)
        with engine.begin() as connection:
            if drift_kind == "extra_table":
                connection.exec_driver_sql(
                    "CREATE TABLE ph1d_unexpected_table (id INTEGER PRIMARY KEY)"
                )
            else:
                index = next(
                    index
                    for table in Base.metadata.tables.values()
                    for index in table.indexes
                    if not index.unique and index.name
                )
                connection.exec_driver_sql(f'DROP INDEX "{index.name}"')

        with engine.connect() as connection:
            report = inspect_schema_authority(connection)
        assert report.current_revisions == (expected_head(),)
        assert report.state is SchemaAuthorityState.SCHEMA_DRIFT
        assert {item.kind for item in report.differences} & {
            "remove_table",
            "add_index",
        }
        # Startup remains intentionally revision-only; deployment preflight is strict.
        init_db(bind=engine)


def test_revision_states_and_automation_exit_codes(monkeypatch, capsys) -> None:
    behind = SchemaVerification(
        expected_head="head",
        current_revisions=("known_parent",),
        differences=(),
        known_revisions=("known_parent", "head"),
    )
    assert behind.state is SchemaAuthorityState.REVISION_BEHIND

    with _temporary_database("revision_states") as (engine, _):
        monkeypatch.setattr(schema_admin, "engine", engine)
        assert schema_admin.verify() == SchemaAdminExitCode.REVISION_MISSING

        _upgrade(engine)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num='future_unknown_head'")
            )
        assert schema_admin.verify() == SchemaAdminExitCode.REVISION_AHEAD_OR_UNKNOWN
        with pytest.raises(SchemaAuthorityError, match="ahead-or-unknown"):
            init_db(bind=engine)

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) "
                    "VALUES ('second_unknown_head')"
                )
            )
        assert schema_admin.verify() == SchemaAdminExitCode.MULTIPLE_HEADS
    output = capsys.readouterr().out
    assert "state=REVISION_MISSING" in output
    assert "state=REVISION_AHEAD_OR_UNKNOWN" in output
    assert "state=MULTIPLE_HEADS" in output


def test_connection_error_is_credential_safe(monkeypatch, capsys) -> None:
    secret = "ph1d-not-for-output"
    unreachable = create_engine(
        f"postgresql+psycopg://ph1d:{secret}@127.0.0.1:1/topo",
        connect_args={"connect_timeout": 1},
    )
    monkeypatch.setattr(schema_admin, "engine", unreachable)
    try:
        assert schema_admin.main(["verify"]) == SchemaAdminExitCode.CONNECTION_ERROR
    finally:
        unreachable.dispose()
    output = capsys.readouterr().out
    assert "state=CONNECTION_ERROR" in output
    assert secret not in output
    assert "postgresql" not in output


def test_multiple_migration_heads_have_a_distinct_exit(monkeypatch, capsys) -> None:
    def reject_multiple_heads() -> int:
        raise MultipleMigrationHeadsError(2)

    monkeypatch.setattr(schema_admin, "verify", reject_multiple_heads)
    assert schema_admin.main(["verify"]) == SchemaAdminExitCode.MULTIPLE_HEADS
    output = capsys.readouterr().out
    assert "state=MULTIPLE_HEADS" in output
    assert "migration_head_count=2" in output


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("before_ddl", "    raise RuntimeError('ph1d before ddl')"),
        (
            "after_ddl",
            "    op.create_table('ph1d_partial_probe', "
            "sa.Column('id', sa.Integer(), primary_key=True))\n"
            "    raise RuntimeError('ph1d after ddl')",
        ),
    ],
)
def test_failed_test_only_migration_rolls_back_and_application_cannot_start(
    tmp_path: Path,
    name: str,
    body: str,
) -> None:
    with _temporary_database(name) as (engine, _):
        with pytest.raises(RuntimeError, match=f"ph1d {name.replace('_', ' ')}"):
            with engine.begin() as connection:
                command.upgrade(_synthetic_config(tmp_path, connection, body), "head")

        inspector = inspect(engine)
        assert "ph1d_partial_probe" not in inspector.get_table_names()
        assert _domain_tables(engine) == set()
        with engine.connect() as connection:
            assert current_revisions(connection) == ()
            assert (
                inspect_schema_authority(connection).state
                is SchemaAuthorityState.REVISION_MISSING
            )
        with pytest.raises(SchemaAuthorityError, match="state=missing"):
            init_db(bind=engine)

        # The measured recovery path is to fix the issue and rerun forward.
        _upgrade(engine)
        init_db(bind=engine)


def test_operator_interruption_rolls_back_without_advancing_revision(
    tmp_path: Path,
) -> None:
    with _temporary_database("interrupted") as (engine, _):
        body = (
            "    op.create_table('ph1d_interrupted_probe', "
            "sa.Column('id', sa.Integer(), primary_key=True))\n"
            "    raise KeyboardInterrupt('ph1d operator interruption')"
        )
        with pytest.raises(KeyboardInterrupt, match="operator interruption"):
            with engine.begin() as connection:
                command.upgrade(_synthetic_config(tmp_path, connection, body), "head")

        assert "ph1d_interrupted_probe" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert current_revisions(connection) == ()
        with pytest.raises(SchemaAuthorityError, match="state=missing"):
            init_db(bind=engine)


def test_backup_restore_preserves_representative_history() -> None:
    if not POSTGRES_CONTAINER:
        pytest.skip("set TOPO_TEST_POSTGRES_CONTAINER for pg_dump/pg_restore proof")

    with _temporary_database("backup_restore") as (engine, database_name):
        _upgrade(engine)
        expected = _seed_representative_history(engine)
        dump_path = f"/tmp/{database_name}.dump"
        database_user = make_url(_postgres_url()).username
        assert database_user
        try:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "pg_dump",
                    "-U",
                    database_user,
                    "-d",
                    database_name,
                    "--format=custom",
                    f"--file={dump_path}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            base_url = make_url(_postgres_url())
            admin = create_engine(
                base_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
            )
            engine.dispose()
            try:
                _drop_database(admin, database_name)
                with admin.connect() as connection:
                    connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            finally:
                admin.dispose()

            subprocess.run(
                [
                    "docker",
                    "exec",
                    POSTGRES_CONTAINER,
                    "pg_restore",
                    "-U",
                    database_user,
                    "-d",
                    database_name,
                    "--exit-on-error",
                    dump_path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            restored = create_engine(base_url.set(database=database_name))
            try:
                with restored.connect() as connection:
                    assert inspect_schema_authority(connection).ok
                with Session(restored) as session:
                    snapshot = session.get(
                        db_models.SnapshotRecord, expected["snapshot_id"]
                    )
                    incident = session.get(
                        db_models.IncidentRecord, expected["incident_id"]
                    )
                    analysis = session.get(
                        db_models.CausalAnalysisRecord, expected["analysis_id"]
                    )
                    assert snapshot is not None
                    assert incident is not None
                    assert analysis is not None
                    assert snapshot.payload_json == expected["snapshot_payload"]
                    assert snapshot.collected_at == NOW
                    assert incident.topology_snapshot_id == expected["snapshot_id"]
                    assert analysis.payload_json == expected["causal_payload"]
                    assert session.get(
                        db_models.SignalRecord, expected["signal_id"]
                    ) is not None
                    assert session.get(
                        db_models.ChangeEventRecord, expected["change_event_id"]
                    ) is not None
                    assert session.get(
                        db_models.OwnershipMappingRecord, expected["ownership_id"]
                    ) is not None
            finally:
                restored.dispose()
        finally:
            subprocess.run(
                ["docker", "exec", POSTGRES_CONTAINER, "rm", "-f", dump_path],
                check=False,
                capture_output=True,
                text=True,
            )


def test_two_application_instances_fail_before_and_pass_after_migration() -> None:
    with _temporary_database("multi_app") as (engine, _):
        def initialize(_: int) -> str:
            try:
                init_db(bind=engine)
                return "started"
            except SchemaAuthorityError:
                return "refused"

        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(initialize, (1, 2))) == ["refused", "refused"]
        assert _domain_tables(engine) == set()

        _upgrade(engine)
        before = _schema_summary(engine)
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(initialize, (1, 2))) == ["started", "started"]
        assert _schema_summary(engine) == before
        with engine.connect() as connection:
            assert current_revisions(connection) == (expected_head(),)


def test_bounded_concurrent_migration_attempt_has_one_authoritative_result() -> None:
    with _temporary_database("concurrent_migrate") as (engine, _):
        barrier = Barrier(2)

        def migrate(_: int) -> str:
            barrier.wait(timeout=10)
            environment = os.environ.copy()
            environment["TOPO_DATABASE_URL"] = engine.url.render_as_string(
                hide_password=False
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    "alembic.ini",
                    "upgrade",
                    "head",
                ],
                cwd=BACKEND_DIR,
                env=environment,
                capture_output=True,
                text=True,
            )
            return "upgraded" if result.returncode == 0 else "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(migrate, (1, 2)))
        print(f"PH1D_CONCURRENT_MIGRATION_RESULTS={sorted(results)}")
        assert "upgraded" in results
        with engine.connect() as connection:
            assert inspect_schema_authority(connection).ok


def test_destructive_downgrade_is_limited_to_disposable_database() -> None:
    with _temporary_database("downgrade") as (engine, _):
        _upgrade(engine)
        with engine.begin() as connection:
            command.downgrade(alembic_config(connection=connection), "base")
        assert _domain_tables(engine) == set()
        with engine.connect() as connection:
            assert current_revisions(connection) == ()


def test_frozen_sqlite_custody_is_unchanged() -> None:
    assert hashlib.sha256(DEVELOPER_DB.read_bytes()).hexdigest() == DEVELOPER_DB_SHA256
    assert hashlib.sha256(FROZEN_DB.read_bytes()).hexdigest() == FROZEN_DB_SHA256


def test_cli_module_does_not_accept_an_expected_head_override() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "app.db.schema_admin", "verify", "--expected-head", "x"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
