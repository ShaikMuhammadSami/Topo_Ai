"""Opt-in PostgreSQL 16 compatibility and migration-authority acceptance.

These tests intentionally skip during the ordinary SQLite suite.  PH-1C runs
them against a disposable, loopback-only PostgreSQL database by setting
``TOPO_TEST_POSTGRES_URL``.  The accepted Alembic revision and ORM schema are
inputs to this suite, not things this suite is permitted to rewrite.
"""

from __future__ import annotations
from domain_tenant_fixtures import TEST_HEADERS, TEST_TENANT, seed_domain_tenant

import json
import os
import re
import secrets
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import (
    Boolean,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.db import models as db_models
from app.db.database import Base, _synchronous_database_url, init_db
from app.db.models import (
    AuthApiCredentialRecord,
    AuthSessionRecord,
    ServiceApiTenantBindingRecord,
    TenantMembershipRecord,
    TenantRecord,
)
from app.main import create_app
from app.db.schema_management import (
    SchemaAuthorityError,
    adopt_current_schema,
    alembic_config,
    current_revisions,
    expected_head,
    inspect_schema_authority,
    schema_differences,
    script_directory,
)
from app.models.build_artifacts import (
    BuildArtifactEvidence,
    BuildArtifactEvidenceCompleteness,
    BuildArtifactEvidenceType,
    BuildArtifactType,
)
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalConfidenceLevel,
    CausalEvidenceClaimType,
    CausalEvidenceLedger,
    CausalEvidenceLedgerItem,
    CausalEvidenceQuality,
    CausalEvidenceSourceCategory,
    CausalEvidenceStance,
    CausalHypothesis,
)
from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventEntityReference,
    ChangeEventKind,
    ChangeEventSource,
)
from app.models.change_sources import ChangeSourceCreate, ChangeSourceType
from app.models.execution_readiness import (
    ExecutionReadinessStatus,
    ExecutionReadinessTarget,
)
from app.models.execution_transaction import ExecutionContractSnapshot
from app.models.ownership import OwnershipMappingCreate
from app.models.recommendations import RecommendationRisk
from app.models.response_intelligence import (
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import ResponseActionCategory
from app.models.runtime_observability import (
    RuntimeDependencyObservation,
    RuntimeDestinationIdentity,
    RuntimeEventBatchRequest,
    RuntimeSourceIdentity,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
    SignalSeverity,
    SignalType,
)
from app.models.topology import Entity, EntityType, GraphSnapshot
from app.models.webhooks import (
    WebhookDeliveryStatus,
    WebhookEndpointCreate,
    WebhookEventType,
)
from app.repositories.build_artifact_evidence_repository import (
    list_build_artifact_evidence,
    save_build_artifact_evidence,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
    load_causal_analysis,
    save_causal_analysis,
)
from app.repositories.change_event_repository import (
    ingest_change_event,
    load_change_event,
)
from app.repositories.change_source_repository import (
    load_change_source,
)
from app.repositories.cloud_repository import (
    list_cloud_accounts,
    list_cloud_resources,
)
from app.repositories.execution_intent_repository import (
    atomic_cancel_execution_intent_record,
    create_execution_intent_record,
    load_execution_intent_record,
)
from app.repositories.incident_record_repository import load_incident_record
from app.repositories.incident_outcome_repository import (
    list_incident_outcome_records,
)
from app.repositories.ownership_repository import load_ownership_mapping
from app.repositories.runtime_observability_repository import (
    ingest_runtime_event_batch,
    list_runtime_dependencies,
    list_runtime_sensors,
)
from app.repositories.signal_repository import load_signal, save_signals
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.repositories.webhook_repository import (
    load_webhook_endpoint,
    save_delivery_result,
)
from app.security.secret_keyring import SecretKeyring, SecretStoreConfiguration
from app.security.api_tokens import AuthPrincipal, token_digest
from app.security.auth_config import (
    AuthConfigurationError,
    AuthConfigurationFailure,
    load_auth_configuration,
)
from app.security.session_auth import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME
from app.security.authorization_enforcement import authorize_agent_fixed_purpose
from app.services.causal_rca import _confidence_level
from app.services.auth_api_credential_service import (
    authenticate_auth_api_credential,
    create_auth_api_credential,
    revoke_auth_api_credential,
)
from app.services import change_source_ingest
from app.services.secret_consumers import (
    create_change_source_secure,
    create_webhook_endpoint_secure,
)
from app.services.secret_store import EncryptedDatabaseSecretStore
from app.services.confidence_semantics import ensure_analysis_confidence_semantics
from app.services.incident_lifecycle import upsert_incident_from_orchestration
from app.services.lifecycle_status import build_lifecycle_status
from app.services.ownership_resolver import create_ownership_mapping
from app.services.temporal_semantics import (
    build_temporal_metadata,
    parse_utc,
    safe_snapshot_record_at_or_before,
)
from app.repositories import tenant_repository
from app.services.tenant_service import create_tenant_with_creator_membership
from app.services.authority_assignments import grant_installation_operator
from app.services.principal_identity import provision_external_human_principal
from app.models.principal_identity import LEGACY_LOCAL_ISSUER

POSTGRES_URL = os.getenv("TOPO_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="set TOPO_TEST_POSTGRES_URL to run PostgreSQL compatibility tests",
)

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)
from frozen_schema_fixtures import frozen_0008_metadata

# Preserve this accepted 43-table PH-1/PH-3 generic fixture verbatim. PH-4B's
# constrained binary store has its own real-engine corpus, not fabricated strings.
DOMAIN_TABLE_NAMES = tuple(sorted(frozen_0008_metadata().tables))
DOMAIN_OWNERSHIP_REVISION = "0005_domain_tenant_ownership"
TENANT_FOUNDATION_REVISION = "0004_tenant_foundation"
PH3C_DOMAIN_TABLE_NAMES = tuple(
    script_directory()
    .get_revision(DOMAIN_OWNERSHIP_REVISION)
    .module.PH3C_DOMAIN_TABLES
)
POSTGRES_TENANT_A = "tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
POSTGRES_TENANT_B = "tenant:bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
POSTGRES_UNKNOWN_TENANT = "tenant:cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _postgres_url() -> str:
    return _synchronous_database_url(POSTGRES_URL)


def _upgrade(
    engine: Engine,
    revision: str = "head",
    *,
    legacy_tenant_id: str | None = None,
) -> None:
    with engine.begin() as connection:
        config = alembic_config(connection=connection)
        config.cmd_opts = Namespace(
            x=(
                []
                if legacy_tenant_id is None
                else [f"legacy_tenant_id={legacy_tenant_id}"]
            )
        )
        command.upgrade(
            config,
            revision,
        )


def _truncate(engine: Engine) -> None:
    preparer = engine.dialect.identifier_preparer
    # Include PH-4B custody tables as well as the historical 43 domain tables.
    # Consumer integration tests now create real encrypted records, and those
    # records must not leak into the next independently configured app test.
    names = ", ".join(
        preparer.quote(name) for name in sorted(Base.metadata.tables)
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(f"TRUNCATE TABLE {names}")


@pytest.fixture(scope="session")
def postgres_engine() -> Engine:
    engine = create_engine(_postgres_url(), pool_pre_ping=True)
    _upgrade(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(postgres_engine: Engine):
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_domain_rows(postgres_engine: Engine):
    _truncate(postgres_engine)
    yield
    _truncate(postgres_engine)


def _database_identifier(prefix: str) -> str:
    value = f"topo_ph1c_{prefix}_{uuid4().hex[:12]}"
    assert re.fullmatch(r"[a-z0-9_]+", value)
    return value


@contextmanager
def _temporary_database(prefix: str):
    base_url = make_url(_postgres_url())
    database_name = _database_identifier(prefix)
    admin_url = base_url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    target = create_engine(base_url.set(database=database_name))
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        yield target
    finally:
        target.dispose()
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :database_name AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{database_name}"'
            )
        admin.dispose()


def _mapper_for(table_name: str):
    return next(
        mapper
        for mapper in Base.registry.mappers
        if mapper.local_table.name == table_name
    )


def _string_value(table_name: str, column_name: str, length: int | None, row: int):
    if column_name.endswith("_at"):
        return (NOW + timedelta(seconds=row)).isoformat()
    if column_name.endswith("_json"):
        if any(
            token in column_name
            for token in (
                "ids_json",
                "roles_json",
                "types_json",
                "actions_json",
                "steps_json",
                "evidence_json",
                "warnings_json",
            )
        ):
            return "[]"
        return json.dumps({"fixture": "postgres", "row": row}, sort_keys=True)
    value = f"{table_name}:{column_name}:row-{row}"
    if length is not None:
        return value[:length]
    return value


def _column_value(table_name: str, column, row: int):
    column_type = column.type
    if isinstance(column_type, Boolean):
        return True
    if isinstance(column_type, Integer):
        return row + 1
    if isinstance(column_type, Float):
        return float(row) + 0.5
    if isinstance(column_type, String):
        return _string_value(table_name, column.name, column_type.length, row)
    if isinstance(column_type, Text):
        return _string_value(table_name, column.name, None, row)
    raise AssertionError(
        f"PH-1C fixture has no deterministic value for {table_name}.{column.name} "
        f"({column_type!r})"
    )


def _mapped_instance(table_name: str, row: int = 1, **overrides):
    table = Base.metadata.tables[table_name]
    values = {
        column.name: _column_value(table_name, column, row)
        for column in table.columns
    }
    if table_name in PH3C_DOMAIN_TABLE_NAMES:
        values["tenant_id"] = TEST_TENANT
    if table_name == "change_sources":
        values.update(
            source_type="github",
            enabled=False,
            secret_ref=None,
            config_json="{}",
            filters_json="{}",
        )
    elif table_name == "webhook_endpoints":
        values.update(
            signing_secret_ref=None,
            protected_headers_secret_ref=None,
            protected_header_names_json="[]",
        )
    elif table_name == "tenant_memberships":
        values["role"] = "tenant_viewer"
    values.update(overrides)
    return _mapper_for(table_name).class_(**values)


def _domain_table_names(connection) -> set[str]:
    return set(inspect(connection).get_table_names()) & set(DOMAIN_TABLE_NAMES)


def _seed_migration_tenant(
    connection,
    tenant_id: str,
    *,
    status: str = "active",
) -> None:
    connection.execute(
        text(
            "INSERT INTO tenants "
            "(tenant_id, display_name, status, created_at, updated_at, "
            "created_by_subject) VALUES "
            "(:tenant_id, :display_name, :status, :created_at, :updated_at, "
            ":created_by_subject)"
        ),
        {
            "tenant_id": tenant_id,
            "display_name": f"PostgreSQL fixture {tenant_id[-1]}",
            "status": status,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "created_by_subject": "test:ph3c-postgres-operator",
        },
    )


def _migration_string_value(table_name: str, column) -> str:
    if column.name.endswith("_json"):
        return "{}"
    if column.name.endswith("_at"):
        return NOW.isoformat()
    value = f"legacy-{table_name}-{column.name}"
    length = getattr(column.type, "length", None)
    return value[:length] if length is not None else value


def _seed_pre_tenancy_record(
    connection,
    table_name: str,
    **overrides,
) -> dict[str, object]:
    table = sa.Table(
        table_name,
        sa.MetaData(),
        autoload_with=connection,
    )
    values: dict[str, object] = {}
    for column in table.columns:
        if column.name in overrides:
            values[column.name] = overrides[column.name]
        elif column.nullable or column.server_default is not None:
            continue
        elif isinstance(column.type, Boolean):
            values[column.name] = False
        elif isinstance(column.type, Integer):
            values[column.name] = 1
        elif isinstance(column.type, Float):
            values[column.name] = 0.5
        elif isinstance(column.type, (String, Text)):
            values[column.name] = _migration_string_value(
                table_name,
                column,
            )
        else:  # pragma: no cover - fails explicitly for a new storage type
            raise AssertionError(
                f"Unsupported migration fixture type {column.type} for "
                f"{table_name}.{column.name}"
            )
    values.update(overrides)
    connection.execute(table.insert().values(**values))
    return values


def test_postgresql_environment_and_unqualified_driver_selection(
    postgres_engine: Engine,
) -> None:
    assert postgres_engine.dialect.name == "postgresql"
    with postgres_engine.connect() as connection:
        facts = connection.execute(
            text(
                "SELECT current_setting('server_version'), "
                "current_setting('server_encoding'), "
                "current_setting('TimeZone'), "
                "current_setting('transaction_isolation')"
            )
        ).one()
        assert facts[0].startswith("16.")
        assert facts[1] == "UTF8"
        assert facts[2] in {"Etc/UTC", "UTC"}
        assert facts[3] == "read committed"

    qualified = _postgres_url()
    unqualified = qualified.replace("postgresql+psycopg://", "postgresql://", 1)
    selected = _synchronous_database_url(unqualified)
    assert selected.startswith("postgresql+psycopg://")
    probe = create_engine(selected)
    try:
        with probe.connect() as connection:
            assert connection.scalar(text("SELECT 1")) == 1
    finally:
        probe.dispose()


def test_accepted_schema_parity_and_postgresql_storage_contract(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as connection:
        verification = inspect_schema_authority(connection)
        assert verification.ok
        assert current_revisions(connection) == (expected_head(),)
        assert schema_differences(connection) == ()
        inspector = inspect(connection)
        assert len(_domain_table_names(connection)) == 43
        assert sum(len(table.columns) for table in Base.metadata.tables.values()) == 844
        assert sum(
            1 for table in Base.metadata.tables.values() for _ in table.primary_key
        ) == 76
        assert sum(len(table.indexes) for table in Base.metadata.tables.values()) == 352
        assert sum(
            1
            for table in Base.metadata.tables.values()
            for index in table.indexes
            if index.unique
        ) == 9
        assert sum(
            1
            for table in Base.metadata.tables.values()
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ) == 17

        database_indexes = [
            item
            for table_name in DOMAIN_TABLE_NAMES
            for item in inspector.get_indexes(table_name)
            if not item.get("duplicates_constraint")
        ]
        assert len(database_indexes) == 346
        assert sum(bool(item["unique"]) for item in database_indexes) == 9
        assert sum(not item["unique"] for item in database_indexes) == 337
        assert all(
            inspector.get_pk_constraint(name).get("constrained_columns")
            for name in DOMAIN_TABLE_NAMES
        )
        domain_foreign_keys = {
            name: inspector.get_foreign_keys(name)
            for name in DOMAIN_TABLE_NAMES
            if inspector.get_foreign_keys(name)
        }
        assert set(domain_foreign_keys) == {
            "auth_api_credentials",
            "auth_sessions",
            "tenant_memberships",
        }
        checks = {
            name: {
                item["name"] for item in inspector.get_check_constraints(name)
            }
            for name in DOMAIN_TABLE_NAMES
            if inspector.get_check_constraints(name)
        }
        assert checks == {
            "tenant_memberships": {"ck_tenant_memberships_role"},
            "change_sources": {
                "ck_change_sources_enabled_secret",
                "ck_change_sources_secret_ref",
            },
            "webhook_endpoints": {
                "ck_webhook_headers_secret_ref",
                "ck_webhook_signing_secret_ref",
            },
        }
        assert all(
            column.get("default") is None
            for name in DOMAIN_TABLE_NAMES
            for column in inspector.get_columns(name)
        )

        storage_rows = connection.execute(
            text(
                "SELECT table_name, column_name, data_type, "
                "character_maximum_length FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )
        ).mappings()
        storage = {
            (row["table_name"], row["column_name"]): (
                row["data_type"],
                row["character_maximum_length"],
            )
            for row in storage_rows
            if row["table_name"] in DOMAIN_TABLE_NAMES
        }
        json_columns = [
            (table.name, column.name)
            for table in Base.metadata.tables.values()
            for column in table.columns
            if table.name in DOMAIN_TABLE_NAMES and column.name.endswith("_json")
        ]
        timestamp_columns = [
            (table.name, column.name)
            for table in frozen_0008_metadata().tables.values()
            for column in table.columns
            if column.name.endswith("_at")
        ]
        assert len(json_columns) == 61
        assert len(timestamp_columns) == 149
        assert all(storage[key][0] == "text" for key in json_columns)
        assert all(storage[key] == ("character varying", 50) for key in timestamp_columns)
        assert not any(
            data_type
            in {
                "json",
                "jsonb",
                "timestamp without time zone",
                "timestamp with time zone",
                "USER-DEFINED",
            }
            for data_type, _ in storage.values()
        )


def test_empty_postgresql_startup_fails_closed_without_creating_domain_tables() -> None:
    with _temporary_database("empty") as engine:
        with pytest.raises(SchemaAuthorityError, match="state=missing") as exc_info:
            init_db(bind=engine)
        assert "topo_ph1c_local_only" not in str(exc_info.value)
        assert "postgresql" not in str(exc_info.value)
        with engine.connect() as connection:
            assert _domain_table_names(connection) == set()


def test_postgresql_0001_to_0002_0003_0004_to_0005_lifecycle() -> None:
    with _temporary_database("auth_migration") as engine:
        _upgrade(engine, "0001_current_schema")
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0001_current_schema",)
            assert "auth_sessions" not in inspect(connection).get_table_names()
            assert len(_domain_table_names(connection)) == 38
        with pytest.raises(SchemaAuthorityError, match="state=behind"):
            init_db(bind=engine)

        _upgrade(engine, "0002_auth_sessions")
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0002_auth_sessions",)
            assert "auth_sessions" in inspect(connection).get_table_names()
            assert "auth_api_credentials" not in inspect(connection).get_table_names()

        _upgrade(engine, "0003_auth_api_credentials")
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0003_auth_api_credentials",)
            assert not {
                "tenants",
                "tenant_memberships",
                "service_api_tenant_bindings",
            }.intersection(inspect(connection).get_table_names())
        with pytest.raises(SchemaAuthorityError, match="state=behind"):
            init_db(bind=engine)

        _upgrade(engine, TENANT_FOUNDATION_REVISION)
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0004_tenant_foundation",)
            assert "tenant_id" not in {
                column["name"]
                for column in inspect(connection).get_columns("topology_snapshots")
            }
        with pytest.raises(SchemaAuthorityError, match="state=behind"):
            init_db(bind=engine)

        _upgrade(engine)
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0015_security_audit",)
            assert inspect_schema_authority(connection).ok
            assert schema_differences(connection) == ()

        with engine.begin() as connection:
            command.downgrade(
                alembic_config(connection=connection),
                "0003_auth_api_credentials",
            )
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0003_auth_api_credentials",)
            assert "auth_api_credentials" in inspect(connection).get_table_names()
            assert "tenants" not in inspect(connection).get_table_names()

        _upgrade(engine)
        with engine.connect() as connection:
            assert inspect_schema_authority(connection).ok

        with engine.begin() as connection:
            command.downgrade(
                alembic_config(connection=connection),
                "0002_auth_sessions",
            )
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0002_auth_sessions",)
            assert "auth_sessions" in inspect(connection).get_table_names()
            assert "auth_api_credentials" not in inspect(connection).get_table_names()

        _upgrade(engine)
        with engine.connect() as connection:
            assert inspect_schema_authority(connection).ok

        with engine.begin() as connection:
            command.downgrade(
                alembic_config(connection=connection),
                "0001_current_schema",
            )
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0001_current_schema",)
            assert "auth_sessions" not in inspect(connection).get_table_names()
            assert len(_domain_table_names(connection)) == 38

        _upgrade(engine)
        with engine.connect() as connection:
            assert inspect_schema_authority(connection).ok


def test_postgresql_domain_backfill_authority_fails_atomically() -> None:
    with _temporary_database("tenant_backfill_guard") as engine:
        _upgrade(engine, TENANT_FOUNDATION_REVISION)
        with engine.begin() as connection:
            _seed_migration_tenant(connection, POSTGRES_TENANT_A)
            _seed_migration_tenant(
                connection,
                POSTGRES_TENANT_B,
                status="disabled",
            )
            _seed_pre_tenancy_record(
                connection,
                "topology_snapshots",
                snapshot_id="snapshot:postgres-backfill-guard",
            )

        attempts = (
            (None, "LEGACY_TENANT_REQUIRED"),
            (POSTGRES_UNKNOWN_TENANT, "LEGACY_TENANT_NOT_FOUND"),
            (POSTGRES_TENANT_B, "LEGACY_TENANT_DISABLED"),
        )
        for tenant_id, error in attempts:
            with pytest.raises(RuntimeError, match=error):
                _upgrade(engine, legacy_tenant_id=tenant_id)
            with engine.connect() as connection:
                assert current_revisions(connection) == (
                    TENANT_FOUNDATION_REVISION,
                )
                assert "tenant_id" not in {
                    column["name"]
                    for column in inspect(connection).get_columns(
                        "topology_snapshots"
                    )
                }


def test_postgresql_two_tenant_explicit_backfill_parity_and_reupgrade() -> None:
    with _temporary_database("tenant_backfill") as engine:
        _upgrade(engine, TENANT_FOUNDATION_REVISION)
        with engine.begin() as connection:
            _seed_migration_tenant(connection, POSTGRES_TENANT_A)
            _seed_migration_tenant(connection, POSTGRES_TENANT_B)
            identities: dict[str, str] = {}
            for table_name in PH3C_DOMAIN_TABLE_NAMES:
                overrides: dict[str, object] = {}
                if table_name == "topology_snapshots":
                    overrides["snapshot_id"] = "snapshot:postgres-legacy"
                elif table_name == "signals":
                    overrides["signal_id"] = "signal:postgres-legacy"
                    overrides["involved_entity_id"] = "entity:postgres-legacy"
                elif table_name == "incidents":
                    overrides.update(
                        incident_id="incident:postgres-legacy",
                        topology_snapshot_id="snapshot:postgres-legacy",
                        primary_signal_id="signal:postgres-legacy",
                    )
                elif table_name == "causal_analyses":
                    overrides.update(
                        analysis_id="causal-analysis:postgres-legacy",
                        incident_id="incident:postgres-legacy",
                    )
                elif table_name == "change_events":
                    overrides["event_id"] = "change-event:postgres-legacy"
                elif table_name == "change_entity_links":
                    overrides.update(
                        link_id="change-link:postgres-legacy",
                        event_id="change-event:postgres-legacy",
                        entity_id="entity:postgres-legacy",
                        snapshot_id="snapshot:postgres-legacy",
                    )
                elif table_name == "webhook_endpoints":
                    overrides.update(
                        url="https://legacy.example.test/topo-events",
                        headers_json="{}",
                        signing_secret=None,
                    )
                elif table_name == "post_incident_reports":
                    overrides.update(
                        report_id="report:postgres-legacy",
                        incident_id="incident:postgres-legacy",
                    )

                values = _seed_pre_tenancy_record(
                    connection,
                    table_name,
                    **overrides,
                )
                primary_key = inspect(connection).get_pk_constraint(table_name)[
                    "constrained_columns"
                ][0]
                identities[table_name] = str(values[primary_key])

        _upgrade(engine, legacy_tenant_id=POSTGRES_TENANT_B)
        with engine.connect() as connection:
            assert current_revisions(connection) == ("0015_security_audit",)
            assert inspect_schema_authority(connection).ok
            assert schema_differences(connection) == ()
            assert len(_domain_table_names(connection)) == 43
            for table_name, identity in identities.items():
                table = sa.Table(
                    table_name,
                    sa.MetaData(),
                    autoload_with=connection,
                )
                primary_key = next(column for column in table.primary_key.columns if column.name != "tenant_id")
                row = connection.execute(
                    sa.select(primary_key, table.c.tenant_id)
                ).one()
                assert str(row[0]) == identity
                assert row[1] == POSTGRES_TENANT_B
                assert (
                    connection.scalar(
                        sa.select(sa.func.count())
                        .select_from(table)
                        .where(table.c.tenant_id.is_(None))
                    )
                    == 0
                )

            assert (
                connection.scalar(
                    text(
                        "SELECT COUNT(*) FROM tenants WHERE tenant_id NOT IN "
                        "(:tenant_a, :tenant_b)"
                    ),
                    {
                        "tenant_a": POSTGRES_TENANT_A,
                        "tenant_b": POSTGRES_TENANT_B,
                    },
                )
                == 0
            )
            assert (
                connection.scalar(text("SELECT COUNT(*) FROM tenant_memberships")) == 0
            )

        with engine.begin() as connection:
            command.downgrade(
                alembic_config(connection=connection),
                TENANT_FOUNDATION_REVISION,
            )
        with engine.connect() as connection:
            assert current_revisions(connection) == (TENANT_FOUNDATION_REVISION,)
            assert "tenant_id" not in {
                column["name"]
                for column in inspect(connection).get_columns("topology_snapshots")
            }

        _upgrade(engine, legacy_tenant_id=POSTGRES_TENANT_B)
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT snapshot_id, tenant_id FROM topology_snapshots")
            ).one()
            assert row == (
                "snapshot:postgres-legacy",
                POSTGRES_TENANT_B,
            )
            assert inspect_schema_authority(connection).ok


def test_migrated_postgresql_startup_succeeds(postgres_engine: Engine) -> None:
    init_db(bind=postgres_engine)


def test_postgresql_browser_session_survives_app_recreation_and_revokes(
    postgres_engine: Engine,
    session_factory,
    monkeypatch,
) -> None:
    bootstrap = "postgres-session-test-" + secrets.token_urlsafe(40)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(bootstrap): {
                    "subject": "test:postgres-browser",
                    "display_name": "PostgreSQL Browser",
                    "roles": ["operator"],
                }
            }
        ),
    )
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps(["https://topo.test"]),
    )
    configuration = load_auth_configuration(database_url=_postgres_url())

    def application():
        return create_app(
            auth_configuration=configuration,
            session_factory=session_factory,
            database_initializer=lambda: init_db(bind=postgres_engine),
        )

    with TestClient(application(), base_url="https://topo.test") as first:
        login = first.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": f"Bearer {bootstrap}",
                "Origin": "https://topo.test",
            },
        )
        assert login.status_code == 201
        session_secret = first.cookies.get(SESSION_COOKIE_NAME)
        csrf_secret = first.cookies.get(CSRF_COOKIE_NAME)

    with session_factory() as session:
        record = session.scalars(select(AuthSessionRecord)).one()
        assert session_secret not in {
            record.session_secret_digest,
            record.csrf_digest,
            record.source_credential_digest,
        }
        assert csrf_secret not in {
            record.session_secret_digest,
            record.csrf_digest,
            record.source_credential_digest,
        }

    with TestClient(application(), base_url="https://topo.test") as restarted:
        restarted.cookies.set(SESSION_COOKIE_NAME, session_secret)
        restarted.cookies.set(CSRF_COOKIE_NAME, csrf_secret)
        assert restarted.get("/api/v1/auth/session").status_code == 200
        assert restarted.delete(
            "/api/v1/auth/session",
            headers={"X-Topo-CSRF": csrf_secret},
        ).status_code == 204

    with TestClient(application(), base_url="https://topo.test") as revoked:
        revoked.cookies.set(SESSION_COOKIE_NAME, session_secret)
        assert revoked.get("/api/v1/auth/session").status_code == 401


def test_postgresql_named_credential_lifecycle_session_and_startup_authority(
    postgres_engine: Engine,
    session_factory,
    monkeypatch,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        created = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="PostgreSQL operator",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                subject="test:postgres-named-admin",
                display_name="PostgreSQL Named Admin",
                roles=["admin"],
                expires_in_days=30,
            ),
            created_by_subject="test:bootstrap-admin",
            now=now,
        )
        raw_secret = created.api_credential
        record = session.get(AuthApiCredentialRecord, created.credential_id)
        assert record is not None
        assert raw_secret not in record.credential_secret_digest
        resolved = authenticate_auth_api_credential(
            session,
            raw_secret=raw_secret,
            now=now + timedelta(seconds=1),
        )
        assert resolved is not None
        assert resolved.principal.authentication_type == "human_api_token"
        assert resolved.record.last_used_at is not None
        tenant = create_tenant_with_creator_membership(
            session,
            display_name="PostgreSQL credential tenant",
            creator_subject="test:postgres-named-admin",
            now=now,
        )
        service = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="PostgreSQL service",
                caller_type=ApiCredentialCallerType.SERVICE_API,
                permissions=["incident.read", "incident.respond"],
                subject="service:postgres-automation",
                display_name="PostgreSQL Automation",
                roles=["admin"],
                expires_in_days=30,
                tenant_id=tenant.tenant_id,
            ),
            created_by_subject="test:postgres-named-admin",
            now=now,
        )
        expired = create_auth_api_credential(
            session,
            request=ApiCredentialCreate(
                name="PostgreSQL expired human",
                caller_type=ApiCredentialCallerType.HUMAN_API,
                subject="test:postgres-expired",
                display_name="PostgreSQL Expired Human",
                roles=["admin"],
                expires_in_days=1,
            ),
            created_by_subject="test:postgres-named-admin",
            now=now - timedelta(days=2),
        )

    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv("TOPO_API_TOKEN_HASHES_JSON", "{}")
    monkeypatch.setenv(
        "TOPO_BROWSER_ALLOWED_ORIGINS_JSON",
        json.dumps(["https://topo.test"]),
    )
    configuration = load_auth_configuration(database_url=_postgres_url())

    application = create_app(
        auth_configuration=configuration,
        session_factory=session_factory,
        database_initializer=lambda: init_db(bind=postgres_engine),
    )
    with TestClient(application, base_url="https://topo.test") as client:
        identity = client.get(
            "/api/v1/system/whoami",
            headers={"Authorization": f"Bearer {raw_secret}"},
        )
        assert identity.status_code == 200
        assert identity.json()["authentication_type"] == "human_api_token"
        service_identity = client.get(
            "/api/v1/system/whoami",
            headers={"Authorization": f"Bearer {service.api_credential}"},
        )
        assert service_identity.status_code == 200
        assert service_identity.json()["authentication_type"] == "service_api_token"
        assert client.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": f"Bearer {service.api_credential}",
                "Origin": "https://topo.test",
            },
        ).status_code == 403
        assert client.get(
            "/api/v1/system/whoami",
            headers={"Authorization": f"Bearer {expired.api_credential}"},
        ).status_code == 401
        login = client.post(
            "/api/v1/auth/session",
            headers={
                "Authorization": f"Bearer {raw_secret}",
                "Origin": "https://topo.test",
            },
        )
        assert login.status_code == 201
        session_secret = client.cookies.get(SESSION_COOKIE_NAME)
        with session_factory() as session:
            record = session.get(AuthApiCredentialRecord, created.credential_id)
            assert record is not None
            revoke_auth_api_credential(
                session,
                record=record,
                revoked_by_subject="test:postgres-named-admin",
            )

        client.cookies.set(SESSION_COOKIE_NAME, session_secret)
        assert client.get("/api/v1/auth/session").status_code == 401
        assert client.get(
            "/api/v1/system/whoami",
            headers={"Authorization": f"Bearer {raw_secret}"},
        ).status_code == 401

    no_human_admin = create_app(
        auth_configuration=configuration,
        session_factory=session_factory,
        database_initializer=lambda: init_db(bind=postgres_engine),
    )
    with pytest.raises(AuthConfigurationError) as raised:
        with TestClient(no_human_admin):
            pass
    assert raised.value.category is AuthConfigurationFailure.EMPTY_REQUIRED_AUTHORITY


def test_postgresql_tenant_context_atomicity_and_fixed_service_binding(
    postgres_engine: Engine,
    session_factory,
    monkeypatch,
) -> None:
    bootstrap = "postgres-tenant-bootstrap-" + secrets.token_urlsafe(40)
    monkeypatch.setenv("TOPO_AUTH_MODE", "required")
    monkeypatch.delenv("TOPO_AUTH_ENABLED", raising=False)
    monkeypatch.setenv(
        "TOPO_API_TOKEN_HASHES_JSON",
        json.dumps(
            {
                token_digest(bootstrap): {
                    "subject": "test:postgres-tenant-admin",
                    "display_name": "PostgreSQL Tenant Admin",
                    "roles": ["admin"],
                }
            }
        ),
    )
    configuration = load_auth_configuration(database_url=_postgres_url())
    with session_factory() as session:
        bootstrap_principal = provision_external_human_principal(
            session,
            issuer=LEGACY_LOCAL_ISSUER,
            subject="test:postgres-tenant-admin",
            display_name="PostgreSQL Tenant Admin",
            authentication_type="api_token",
            roles=("admin",),
        )
        grant_installation_operator(
            session, principal_id=bootstrap_principal.principal_id
        )
    application = create_app(
        auth_configuration=configuration,
        session_factory=session_factory,
        database_initializer=lambda: init_db(bind=postgres_engine),
    )
    bearer = {"Authorization": f"Bearer {bootstrap}"}

    with TestClient(application) as client:
        created = client.post(
            "/api/v1/tenants",
            headers=bearer,
            json={"display_name": "PostgreSQL Tenant"},
        )
        assert created.status_code == 201
        tenant_id = created.json()["tenant_id"]
        tenant_headers = {**bearer, "X-Topo-Tenant-ID": tenant_id}
        context = client.get(
            "/api/v1/tenant-context",
            headers=tenant_headers,
        )
        assert context.status_code == 200
        assert context.json()["tenant_id"] == tenant_id

        with monkeypatch.context() as scoped:
            scoped.setattr(
                tenant_repository,
                "add_tenant_membership",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OperationalError("forced tenant atomicity", {}, None)
                ),
            )
            tenant_failure = client.post(
                "/api/v1/tenants",
                headers=bearer,
                json={"display_name": "Rolled back PostgreSQL tenant"},
            )
        assert tenant_failure.status_code == 503

        service_payload = {
            "name": "PostgreSQL tenant service",
            "caller_type": "service_api",
            "permissions": ["incident.read"],
            "subject": "service:postgres-tenant",
            "display_name": "PostgreSQL tenant service",
            "roles": [],
            "expires_in_days": 30,
            "tenant_id": tenant_id,
        }
        with monkeypatch.context() as scoped:
            scoped.setattr(
                tenant_repository,
                "add_service_api_tenant_binding",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    OperationalError("forced binding atomicity", {}, None)
                ),
            )
            binding_failure = client.post(
                "/api/v1/auth/api-credentials",
                headers=tenant_headers,
                json={**service_payload, "subject": "service:rolled-back"},
            )
        assert binding_failure.status_code == 503

        service = client.post(
            "/api/v1/auth/api-credentials",
            headers=tenant_headers,
            json=service_payload,
        )
        assert service.status_code == 201
        assert service.json()["tenant_id"] == tenant_id
        service_context = client.get(
            "/api/v1/tenant-context",
            headers={
                "Authorization": f"Bearer {service.json()['api_credential']}"
            },
        )
        assert service_context.status_code == 200
        assert service_context.json()["tenant_id"] == tenant_id
        assert service_context.json()["selection_source"] == "service_binding"

        disabled = client.post(
            (
                "/api/v1/tenant-memberships/"
                f"{created.json()['membership_id']}/disable"
            ),
            headers=tenant_headers,
        )
        assert disabled.status_code == 200
        assert client.get(
            "/api/v1/tenant-context",
            headers=tenant_headers,
        ).status_code == 403
        recovered = client.post(
            "/api/v1/tenant-memberships/recover",
            headers=bearer,
            json={
                "tenant_id": tenant_id,
                "subject": "test:postgres-tenant-admin",
                "role": "tenant_admin",
            },
        )
        assert recovered.status_code == 200
        assert client.get(
            "/api/v1/tenant-context",
            headers=tenant_headers,
        ).status_code == 200

    with session_factory() as session:
        assert session.scalar(
            select(func.count()).select_from(TenantRecord).where(
                TenantRecord.display_name == "Rolled back PostgreSQL tenant"
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(AuthApiCredentialRecord).where(
                AuthApiCredentialRecord.subject == "service:rolled-back"
            )
        ) == 0
        assert session.scalar(
            select(func.count())
            .select_from(ServiceApiTenantBindingRecord)
            .where(ServiceApiTenantBindingRecord.tenant_id == tenant_id)
        ) == 1
        assert session.scalar(
            select(func.count())
            .select_from(TenantMembershipRecord)
            .where(TenantMembershipRecord.tenant_id == tenant_id)
        ) == 1


def test_exact_but_unstamped_schema_fails_closed() -> None:
    with _temporary_database("unstamped") as engine:
        Base.metadata.create_all(engine)
        with pytest.raises(SchemaAuthorityError, match="state=missing"):
            init_db(bind=engine)
        with engine.connect() as connection:
            assert schema_differences(connection) == ()
            assert current_revisions(connection) == ()


def test_unknown_revision_fails_closed_without_credential_disclosure() -> None:
    with _temporary_database("unknown") as engine:
        _upgrade(engine)
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = 'future_unknown_head'")
            )
        with pytest.raises(SchemaAuthorityError, match="ahead-or-unknown") as exc_info:
            init_db(bind=engine)
        message = str(exc_info.value)
        assert "topo_ph1c_local_only" not in message
        assert "127.0.0.1" not in message


def test_every_mapped_table_supports_orm_write_read_and_false_booleans(
    session_factory,
) -> None:
    assert len(DOMAIN_TABLE_NAMES) == 43
    with session_factory() as session:
        principal_id = "principal:00000000-0000-4000-8000-000000000001"
        principal = _mapped_instance(
            "auth_principals",
            principal_id=principal_id,
            principal_type="human",
            status="active",
        )
        session.add(principal)
        session.flush()
        records = [
            _mapped_instance(
                table_name,
                **(
                    {"principal_id": principal_id}
                    if table_name
                    in {
                        "auth_api_credentials",
                        "auth_sessions",
                        "tenant_memberships",
                    }
                    else {}
                ),
            )
            for table_name in DOMAIN_TABLE_NAMES
        ]
        session.add_all(records)
        session.commit()
        for record in records:
            table = record.__table__
            key = tuple(getattr(record, column.name) for column in table.primary_key)
            identity = key[0] if len(key) == 1 else key
            assert session.get(type(record), identity) is not None

        boolean_attributes = []
        for record in records:
            for column in record.__table__.columns:
                if isinstance(column.type, Boolean):
                    setattr(record, column.name, False)
                    boolean_attributes.append((record, column.name))
        assert len(boolean_attributes) == 6
        session.commit()
        session.expire_all()
        assert all(getattr(record, name) is False for record, name in boolean_attributes)


def _snapshot(snapshot_id: str = "snapshot:postgres") -> GraphSnapshot:
    entity = Entity(
        id="kubernetes:cluster-a:default:Pod:payment-api-abc",
        entity_type=EntityType.RUNTIME_INSTANCE,
        kind="KubernetesPod",
        name="payment-api-abc",
        source_system="kubernetes",
        external_id="uid-payment-api-abc",
        environment="production",
        observed_at=NOW,
        labels={"app": "payment-api"},
        properties={"nested": {"ready": False}, "restarts": [1, 2]},
    )
    return GraphSnapshot(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        collector_name="ph-1c-postgres",
        collector_version="1.0",
        scope={"cluster": "cluster-a", "namespace": "default"},
        entities=[entity],
        metadata={"checkpoint_reason": "incident_boundary", "nested": [1, {"a": True}]},
    )


def _signal(snapshot_id: str = "snapshot:postgres") -> NormalizedSignal:
    return NormalizedSignal(
        signal_id="signal:postgres",
        fingerprint="signal-fingerprint-postgres",
        signal_type=SignalType.KUBERNETES_EVENT,
        severity=SignalSeverity.ERROR,
        category=SignalCategory.IMAGE,
        source_system="kubernetes",
        title="ImagePullBackOff",
        summary="payment-api image pull failed",
        reason="ImagePullBackOff",
        first_observed_at=NOW,
        last_observed_at=NOW + timedelta(seconds=30),
        cluster_name="cluster-a",
        namespace="default",
        topology_snapshot_id=snapshot_id,
        involved_entity_id="kubernetes:cluster-a:default:Pod:payment-api-abc",
        involved_object_uid="uid-payment-api-abc",
        involved_object_kind="Pod",
        involved_object_name="payment-api-abc",
        attributes={"container": "payment", "nested": {"exit": None}},
        raw_payload={"reason": "ImagePullBackOff", "count": 2},
    )


def _causal_analysis(incident_id: str, snapshot_id: str) -> CausalAnalysisResponse:
    hypothesis_id = "hypothesis:postgres"
    ledger_item = CausalEvidenceLedgerItem(
        evidence_id="evidence:runtime:postgres",
        hypothesis_id=hypothesis_id,
        stance=CausalEvidenceStance.SUPPORTING,
        claim_type=CausalEvidenceClaimType.RUNTIME_FAILURE,
        summary="The incident signal reports the workload failure.",
        reason="Direct runtime failure evidence.",
        source_category=CausalEvidenceSourceCategory.SIGNAL,
        signal_ids=["signal:postgres"],
        quality=CausalEvidenceQuality.STRONG,
        why_it_matters="Confirms the runtime manifestation without inventing a cause.",
    )
    ledger = CausalEvidenceLedger(
        hypothesis_id=hypothesis_id,
        snapshot_id=snapshot_id,
        supporting=[ledger_item],
    )
    hypothesis = CausalHypothesis(
        hypothesis_id=hypothesis_id,
        rank=1,
        root_event_id="change-event:postgres",
        root_source="kubernetes",
        root_title="Deployment image changed",
        target_event_id="signal:postgres",
        target_title="ImagePullBackOff",
        affected_entity_id="kubernetes:cluster-a:default:Pod:payment-api-abc",
        score=76.0,
        confidence=0.76,
        confidence_level=_confidence_level(0.76),
        summary="A persisted deterministic PostgreSQL causal fixture.",
        reasons=["Runtime evidence is attached to the pinned topology."],
        supporting_evidence_ids=[ledger_item.evidence_id],
        evidence_ledger=ledger,
    )
    return ensure_analysis_confidence_semantics(
        CausalAnalysisResponse(
            analysis_id="causal-analysis:postgres",
            incident_id=incident_id,
            incident_title="Image pull failure",
            incident_time=NOW.isoformat(),
            topology_snapshot_id=snapshot_id,
            algorithm_version="13c-causal-v1",
            generated_at=(NOW + timedelta(minutes=1)).isoformat(),
            parameters={"lookback_minutes": 180, "fixture": {"dialect": "postgres"}},
            candidate_count=1,
            node_count=0,
            edge_count=0,
            evidence_count=1,
            hypothesis_count=1,
            top_hypothesis=hypothesis,
            hypotheses=[hypothesis],
        )
    )


def _artifact() -> BuildArtifactEvidence:
    return BuildArtifactEvidence(
        evidence_id="build-artifact-evidence:postgres",
        provider="github_actions",
        repository_id="9876543210123456789",
        repository="acme/payment-api",
        workflow_id="9876543210123456780",
        workflow_ref="acme/payment-api/.github/workflows/build.yml@refs/heads/main",
        run_id="32695735269",
        run_attempt=1,
        commit_sha="a" * 40,
        artifact_type=BuildArtifactType.CONTAINER_IMAGE,
        image_repository="ghcr.io/acme/payment-api",
        image_reference="ghcr.io/acme/payment-api:release",
        image_digest="sha256:" + "b" * 64,
        immutable_image_ref="ghcr.io/acme/payment-api@sha256:" + "b" * 64,
        provider_evidence_type=(
            BuildArtifactEvidenceType.GITHUB_ACTIONS_DOCKER_BUILD_RECORD
        ),
        provider_evidence_id="9876543210123456700",
        provider_evidence_reference=(
            "https://api.github.com/repos/acme/payment-api/actions/artifacts/"
            "9876543210123456700"
        ),
        provider_evidence_digest="sha256:" + "c" * 64,
        provider_build_record_digest="sha256:" + "d" * 64,
        provider_builder_id=(
            "https://github.com/acme/payment-api/actions/runs/32695735269/attempts/1"
        ),
        provider_build_started_at=NOW - timedelta(minutes=2),
        provider_build_finished_at=NOW - timedelta(minutes=1),
        provider_run_updated_at=NOW,
        observed_at=NOW,
        temporal=build_temporal_metadata(
            source_event_at=NOW - timedelta(minutes=1),
            observed_at=NOW,
            recorded_at=NOW,
            source_time_trusted=True,
            source_field="provider.finished_at",
        ),
        completeness=BuildArtifactEvidenceCompleteness.COMPLETE,
    )


def test_representative_repositories_and_services_round_trip_on_postgresql(
    session_factory,
) -> None:
    # SecretStore authorization requires the same durable active tenant that
    # production consumer services require.  Earlier repository-only writes
    # did not need this authority row.
    seed_domain_tenant(session_factory.kw["bind"])
    snapshot = _snapshot()
    signal = _signal()
    with session_factory() as session:
        save_snapshot(session, snapshot, tenant_id=TEST_TENANT)
        loaded_snapshot = load_snapshot(
            session, snapshot.snapshot_id, tenant_id=TEST_TENANT
        )
        assert loaded_snapshot == load_snapshot(
            session, snapshot.snapshot_id, tenant_id=TEST_TENANT
        )
        assert loaded_snapshot is not None
        assert loaded_snapshot.scope == snapshot.scope
        assert loaded_snapshot.entities[0].properties == snapshot.entities[0].properties

        save_signals(session, [signal], tenant_id=TEST_TENANT)
        loaded_signal = load_signal(session, signal.signal_id, tenant_id=TEST_TENANT)
        assert loaded_signal is not None
        assert loaded_signal.raw_payload == signal.raw_payload
        incident = upsert_incident_from_orchestration(
            session=session,
            signal=loaded_signal,
            analysis=None,
            recommendations=[],
            tenant_id=TEST_TENANT,
        )
        loaded_incident = load_incident_record(
            session, incident.incident_id, tenant_id=TEST_TENANT
        )
        assert loaded_incident is not None
        assert loaded_incident.topology_snapshot_id == snapshot.snapshot_id
        assert loaded_incident.affected_entity_id == signal.involved_entity_id

        receipt = ingest_change_event(
            session=session,
            request=ChangeEventCreate(
                source=ChangeEventSource.GITHUB_ACTIONS,
                kind=ChangeEventKind.DEPLOYMENT,
                external_id="32695735269:1",
                title="Deploy payment-api image",
                summary="Provider-authentic deployment evidence.",
                occurred_at=(NOW - timedelta(minutes=5)).isoformat(),
                environment="production",
                cluster_name="cluster-a",
                namespace="default",
                repository="acme/payment-api",
                commit_sha="a" * 40,
                entity_refs=[
                    ChangeEventEntityReference(entity_id=signal.involved_entity_id)
                ],
                metadata={"nested": {"run_attempt": 1}},
                raw_payload={"provider": "github", "files": ["runtime-mode.txt"]},
            ),
            auto_correlate=False,
            source_time_trusted=True,
            observed_at=NOW,
            tenant_id=TEST_TENANT,
        )
        change = load_change_event(
            session, event_id=receipt.event_id, tenant_id=TEST_TENANT
        )
        assert change is not None
        assert json.loads(change.metadata_json)["nested"]["run_attempt"] == 1
        assert json.loads(change.raw_payload_json)["files"] == ["runtime-mode.txt"]

        artifact, created = save_build_artifact_evidence(
            session, evidence=_artifact(), tenant_id=TEST_TENANT
        )
        assert created is True
        listed = list_build_artifact_evidence(
            session, repository_id=artifact.repository_id, tenant_id=TEST_TENANT
        )
        assert listed == [artifact]

        analysis = _causal_analysis(incident.incident_id, snapshot.snapshot_id)
        saved = save_causal_analysis(session, analysis=analysis, tenant_id=TEST_TENANT)
        loaded_analysis = load_causal_analysis(
            session, analysis_id=analysis.analysis_id, tenant_id=TEST_TENANT
        )
        assert loaded_analysis == saved
        assert loaded_analysis is not None
        assert loaded_analysis.confidence_semantics is not None
        assert loaded_analysis.top_hypothesis is not None
        assert loaded_analysis.top_hypothesis.evidence_ledger == (
            analysis.top_hypothesis.evidence_ledger
        )
        assert (
            latest_causal_analysis(
                session, incident_id=incident.incident_id, tenant_id=TEST_TENANT
            )
            == loaded_analysis
        )

        ownership = create_ownership_mapping(
            session=session,
            request=OwnershipMappingCreate(
                entity_id=signal.involved_entity_id,
                owner_team="Payments Platform",
                owner_email="payments@example.com",
                oncall_contact="pagerduty:payments",
                repository_url="https://github.com/acme/payment-api",
                business_capability="Checkout",
            ),
            tenant_id=TEST_TENANT,
        )
        assert (
            load_ownership_mapping(
                session, ownership.ownership_id, tenant_id=TEST_TENANT
            )
            == ownership
        )

        cloud_account = _mapped_instance(
            "cloud_accounts",
            cloud_account_id="cloud-account:aws:123456789012",
            provider="aws",
            account_number="123456789012",
            display_name="production",
            principal_arn="arn:aws:iam::123456789012:role/topo-read-only",
            metadata_json=json.dumps({"partition": "aws"}),
            last_seen_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        cloud_resource = _mapped_instance(
            "cloud_resources",
            cloud_resource_id=(
                "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
                "loadbalancer/app/payment-api/0123456789abcdef"
            ),
            provider="aws",
            account_id="123456789012",
            region="us-east-1",
            resource_type="aws_alb",
            resource_id="payment-api-alb",
            arn=(
                "arn:aws:elasticloadbalancing:us-east-1:123456789012:"
                "loadbalancer/app/payment-api/0123456789abcdef"
            ),
            name="payment-api",
            status="active",
            vpc_id="vpc-0123456789abcdef0",
            subnet_ids_json=json.dumps(["subnet-0123456789abcdef0"]),
            tags_json=json.dumps({"service": "payment-api"}),
            properties_json=json.dumps({"scheme": "internal"}),
            observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        session.add_all([cloud_account, cloud_resource])
        session.commit()
        accounts = list_cloud_accounts(session, provider="aws", tenant_id=TEST_TENANT)
        resources = list_cloud_resources(
            session,
            provider="aws",
            account_id="123456789012",
            region="us-east-1",
            tenant_id=TEST_TENANT,
        )
        assert [item.cloud_account_id for item in accounts] == [
            cloud_account.cloud_account_id
        ]
        assert [item.cloud_resource_id for item in resources] == [
            cloud_resource.cloud_resource_id
        ]
        assert resources[0].tags == {"service": "payment-api"}

        agent = _mapped_instance(
            "topo_agents",
            row=80,
            agent_id="agent:runtime-postgres",
            cluster_name="cluster-a",
            tenant_id=TEST_TENANT,
            revoked_at=None,
        )
        session.add(agent)
        session.commit()
        runtime_now = datetime.now(UTC)
        runtime_receipt = ingest_runtime_event_batch(
            session,
            agent=agent,
            request=RuntimeEventBatchRequest(
                batch_id="runtime-batch:postgres",
                sensor_id="runtime-sensor:postgres",
                node_name="node-a",
                cluster_name="cluster-a",
                version="1.0",
                window_start=(runtime_now - timedelta(seconds=30)).isoformat(),
                window_end=runtime_now.isoformat(),
                dependencies=[
                    RuntimeDependencyObservation(
                        source=RuntimeSourceIdentity(
                            namespace="default",
                            pod_name="payment-api-abc",
                            pod_uid="uid-payment-api-abc",
                            workload_name="payment-api",
                            binary="/app/payment-api",
                        ),
                        destination=RuntimeDestinationIdentity(
                            name="checkout-db",
                            address="10.0.4.21",
                            port=5432,
                        ),
                        protocol="tcp",
                        observation_count=3,
                        success_count=2,
                        failure_count=1,
                        first_seen_at=(runtime_now - timedelta(seconds=20)).isoformat(),
                        last_seen_at=runtime_now.isoformat(),
                        metadata={"probe": "tetragon", "nested": {"pid": 42}},
                    )
                ],
                processes=[],
                processed_event_count=3,
                dropped_event_count=0,
                parser_error_count=0,
                metadata={"heartbeat_interval_seconds": 30},
            ),
            tenant_id=TEST_TENANT,
            authorization_context=authorize_agent_fixed_purpose(
                session,
                agent=agent,
                fixed_purpose=(
                    "app.repositories.runtime_observability_repository."
                    "ingest_runtime_event_batch"
                ),
            ),
        )
        assert runtime_receipt.dependency_count == 1
        sensors = list_runtime_sensors(
            session, agent_id=agent.agent_id, tenant_id=TEST_TENANT
        )
        dependencies = list_runtime_dependencies(
            session, agent_id=agent.agent_id, window_minutes=60, tenant_id=TEST_TENANT
        )
        assert [item.sensor_id for item in sensors] == ["runtime-sensor:postgres"]
        assert len(dependencies) == 1
        assert dependencies[0].destination_port == 5432
        assert dependencies[0].metadata["nested"]["pid"] == 42

        endpoint = create_webhook_endpoint_secure(
            session,
            request=WebhookEndpointCreate(
                name="Operations webhook",
                url="https://hooks.example.com/topo",
                event_types=[WebhookEventType.INCIDENT_CREATED],
                headers={"X-Topo-Environment": "production"},
                signing_secret="postgres-fixture-secret",
            ),
            tenant_id=TEST_TENANT,
            actor="test:postgres-runtime",
            store=EncryptedDatabaseSecretStore(SecretStoreConfiguration(
                "encrypted_db", SecretKeyring({"test": os.urandom(32)}, "test")
            )),
        )
        delivery = db_models.WebhookDeliveryRecord(
            delivery_id="webhook-delivery:postgres",
            webhook_id=endpoint.webhook_id,
            event_id="webhook-event:postgres",
            event_type=WebhookEventType.INCIDENT_CREATED.value,
            resource_type="incident",
            resource_id=incident.incident_id,
            status=WebhookDeliveryStatus.SUCCEEDED.value,
            attempt_count=1,
            response_status=202,
            response_body="accepted",
            error_message=None,
            requested_at=NOW.isoformat(),
            completed_at=(NOW + timedelta(seconds=1)).isoformat(),
            payload_json=json.dumps({"incident_id": incident.incident_id}),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
            tenant_id=TEST_TENANT,
        )
        delivered = save_delivery_result(session, delivery, tenant_id=TEST_TENANT)
        assert delivered.status == WebhookDeliveryStatus.SUCCEEDED
        assert (
            load_webhook_endpoint(session, endpoint.webhook_id, tenant_id=TEST_TENANT)
            == endpoint
        )


def _seed_execution_parents(session):
    session.add_all(
        [
            _mapped_instance("incidents", incident_id="incident:postgres-execution"),
            _mapped_instance(
                "action_approvals",
                approval_id="approval:postgres",
                incident_id="incident:postgres-execution",
            ),
        ]
    )
    session.commit()


def _execution_snapshot() -> ExecutionContractSnapshot:
    return ExecutionContractSnapshot(
        approval_id="approval:postgres",
        incident_id="incident:postgres-execution",
        action_id="action:postgres",
        action_family=ResponseActionFamily.ROLLBACK,
        action_category=ResponseActionCategory.ROLLBACK_CANDIDATE,
        action_semantics=ResponseActionSemantics.MITIGATION,
        policy_version="execution-readiness-v1",
        approval_evidence_fingerprint="e" * 64,
        target=ExecutionReadinessTarget(
            entity_ids=["kubernetes:cluster-a:default:Deployment:payment-api"],
            change_event_id="change-event:postgres",
            uniquely_identified=True,
        ),
        risk=RecommendationRisk.MEDIUM,
        requires_human_approval=True,
        created_from_readiness_status=(
            ExecutionReadinessStatus.READY_FOR_HUMAN_APPROVAL
        ),
        causal_analysis_id="causal-analysis:postgres",
        response_plan_reference="response-plan:postgres",
        root_event_id="change-event:postgres",
        readiness_evidence_ids=["evidence:runtime:postgres"],
    )


def _principal(subject: str = "user:postgres") -> AuthPrincipal:
    return AuthPrincipal(
        subject=subject,
        display_name="PostgreSQL operator",
        roles=("operator",),
        authentication_type="api_token",
    )


def test_execution_repository_idempotency_and_conditional_transition(
    session_factory,
) -> None:
    with session_factory() as session:
        _seed_execution_parents(session)
        record, created = create_execution_intent_record(
            session,
            snapshot=_execution_snapshot(),
            idempotency_key="f" * 64,
            creator=_principal(),
            created_at=NOW,
            tenant_id=TEST_TENANT,
        )
        assert created is True
        repeated, repeated_created = create_execution_intent_record(
            session,
            snapshot=_execution_snapshot(),
            idempotency_key="f" * 64,
            creator=_principal(),
            created_at=NOW,
            tenant_id=TEST_TENANT,
        )
        assert repeated_created is False
        assert repeated.execution_id == record.execution_id
        cancelled = atomic_cancel_execution_intent_record(
            session,
            record=record,
            actor=_principal(),
            reason="Manual operator cancellation.",
            cancelled_at=NOW + timedelta(minutes=1),
            tenant_id=TEST_TENANT,
        )
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert cancelled.row_version == 2


def test_json_text_exact_round_trip_and_timestamp_string_semantics(
    session_factory,
) -> None:
    snapshot = _snapshot("snapshot:json-text")
    with session_factory() as session:
        saved_record = save_snapshot(session, snapshot, tenant_id=TEST_TENANT)
        raw_payload = session.scalar(
            select(db_models.SnapshotRecord.payload_json).where(
                db_models.SnapshotRecord.snapshot_id == snapshot.snapshot_id
            )
        )
        assert isinstance(raw_payload, str)
        assert raw_payload == saved_record.payload_json
        parsed = GraphSnapshot.model_validate_json(raw_payload)
        assert parsed.metadata == snapshot.metadata
        assert parsed.entities[0].properties == snapshot.entities[0].properties
        assert isinstance(saved_record.collected_at, str)
        assert parse_utc("2026-08-28T12:00:00Z") == NOW
        assert parse_utc("2026-08-28T12:00:00+00:00") == NOW
        assert parse_utc("2026-08-28T12:00:00", allow_legacy_naive=True) == NOW


def test_historical_snapshot_selection_uses_only_at_or_before_boundary(
    session_factory,
) -> None:
    with session_factory() as session:
        before = _snapshot("snapshot:before").model_copy(
            update={"collected_at": NOW - timedelta(minutes=5)}
        )
        future = _snapshot("snapshot:future").model_copy(
            update={"collected_at": NOW + timedelta(minutes=5)}
        )
        legacy = _snapshot("snapshot:legacy-naive").model_copy(
            update={"collected_at": NOW - timedelta(minutes=10)}
        )
        save_snapshot(session, legacy, tenant_id=TEST_TENANT)
        record = session.get(db_models.SnapshotRecord, (TEST_TENANT, legacy.snapshot_id))
        assert record is not None
        record.collected_at = "2026-08-28T11:50:00"
        session.commit()
        save_snapshot(session, before, tenant_id=TEST_TENANT)
        save_snapshot(session, future, tenant_id=TEST_TENANT)
        selected = safe_snapshot_record_at_or_before(
            session,
            cluster_name="cluster-a",
            namespace="default",
            boundary_at=NOW,
            tenant_id=TEST_TENANT,
        )
        assert selected is not None
        assert selected.snapshot_id == before.snapshot_id
        too_early = safe_snapshot_record_at_or_before(
            session,
            cluster_name="cluster-a",
            namespace="default",
            boundary_at=NOW - timedelta(hours=1),
            tenant_id=TEST_TENANT,
        )
        assert too_early is None


def test_nullable_recent_ordering_keeps_real_times_ahead_of_missing_times(
    session_factory,
) -> None:
    """PostgreSQL DESC defaults NULL first; Topo's latest semantics do not."""
    with session_factory() as session:
        resolved = _mapped_instance(
            "incident_outcomes",
            row=70,
            outcome_id="outcome:resolved",
            incident_id="incident:resolved",
            resolved_at=(NOW - timedelta(hours=1)).isoformat(),
            updated_at=NOW.isoformat(),
        )
        unresolved = _mapped_instance(
            "incident_outcomes",
            row=71,
            outcome_id="outcome:unresolved",
            incident_id="incident:unresolved",
            resolved_at=None,
            updated_at=(NOW + timedelta(hours=1)).isoformat(),
        )
        snapshotted_agent = _mapped_instance(
            "topo_agents",
            row=72,
            agent_id="agent:snapshotted",
            cluster_name="cluster-ordering",
            last_snapshot_at=NOW.isoformat(),
        )
        never_snapshotted_agent = _mapped_instance(
            "topo_agents",
            row=73,
            agent_id="agent:never-snapshotted",
            cluster_name="cluster-ordering",
            last_snapshot_at=None,
        )
        session.add_all(
            [
                resolved,
                unresolved,
                snapshotted_agent,
                never_snapshotted_agent,
            ]
        )
        session.commit()

        outcomes = list_incident_outcome_records(
            session, limit=2, tenant_id=TEST_TENANT
        )
        assert [item.outcome_id for item in outcomes] == [
            "outcome:resolved",
            "outcome:unresolved",
        ]
        lifecycle = build_lifecycle_status(
            session, cluster_name="cluster-ordering", tenant_id=TEST_TENANT
        )
        assert lifecycle.last_successful_discovery_at is None
        # Human domain status must use owned discovery, not PH-3E agent status.
        owned_snapshot = _snapshot("snapshot:ordering").model_copy(
            update={"scope": {"cluster": "cluster-ordering"}}
        )
        save_snapshot(session, owned_snapshot, tenant_id=TEST_TENANT)
        assert (
            build_lifecycle_status(
                session, cluster_name="cluster-ordering", tenant_id=TEST_TENANT
            ).last_successful_discovery_at
            == NOW.isoformat()
        )


def test_realistic_identifiers_case_equality_and_varchar_boundary(
    session_factory,
) -> None:
    long_resource_id = (
        "projects/123456789012345678901234/locations/us-central1/clusters/"
        + "production-payment-platform-"
        + "x" * 500
    )
    with session_factory() as session:
        first = _mapped_instance(
            "cloud_resources",
            row=1,
            cloud_resource_id=long_resource_id,
            provider="gcp",
            account_id="123456789012345678901234",
            region="us-central1",
            resource_type="gke_cluster",
            resource_id="Payment-API",
            name="Payment-API",
            tags_json="{}",
            properties_json="{}",
            subnet_ids_json="[]",
            observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        second = _mapped_instance(
            "cloud_resources",
            row=2,
            cloud_resource_id=long_resource_id.upper(),
            provider="gcp",
            account_id="123456789012345678901234",
            region="us-central1",
            resource_type="gke_cluster",
            resource_id="payment-api",
            name="payment-api",
            tags_json="{}",
            properties_json="{}",
            subnet_ids_json="[]",
            observed_at=NOW.isoformat(),
            created_at=NOW.isoformat(),
            updated_at=NOW.isoformat(),
        )
        session.add_all([first, second])
        session.commit()
        assert first.cloud_resource_id != second.cloud_resource_id
        assert session.get(type(first), (TEST_TENANT, long_resource_id)) is not None

        max_id = "s" * 255
        session.add(
            _mapped_instance(
                "topology_snapshots",
                row=3,
                snapshot_id=max_id,
                collected_at=NOW.isoformat(),
                created_at=NOW.isoformat(),
                scope_json="{}",
                payload_json="{}",
            )
        )
        session.commit()
        assert session.get(db_models.SnapshotRecord, (TEST_TENANT, max_id)) is not None
        session.add(
            _mapped_instance(
                "topology_snapshots",
                row=4,
                snapshot_id="s" * 256,
                collected_at=NOW.isoformat(),
                created_at=NOW.isoformat(),
                scope_json="{}",
                payload_json="{}",
            )
        )
        with pytest.raises(DataError):
            session.commit()
        session.rollback()


UNIQUE_INDEX_CASES = [
    (table.name, index.name, tuple(column.name for column in index.columns))
    for table in Base.metadata.tables.values()
    for index in table.indexes
    if index.unique
]


@pytest.mark.parametrize(
    ("table_name", "index_name", "column_names"),
    UNIQUE_INDEX_CASES,
    ids=[item[1] for item in UNIQUE_INDEX_CASES],
)
def test_each_accepted_unique_index_is_enforced(
    session_factory,
    table_name: str,
    index_name: str,
    column_names: tuple[str, ...],
) -> None:
    assert index_name
    with session_factory() as session:
        first = _mapped_instance(table_name, row=10)
        second = _mapped_instance(table_name, row=11)
        for name in column_names:
            setattr(second, name, getattr(first, name))
        session.add(first)
        session.commit()
        session.add(second)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


REPRESENTATIVE_COMPOSITE_CONSTRAINTS = [
    ("build_artifact_evidence", "uq_tenant_build_artifact_provider_fact"),
    ("change_entity_links", "uq_tenant_change_event_entity_link"),
    ("action_approval_events", "uq_tenant_action_approval_event_sequence"),
    ("post_incident_reports", "uq_tenant_post_incident_report_version"),
    ("webhook_deliveries", "uq_tenant_webhook_delivery_event"),
]


@pytest.mark.parametrize(
    ("table_name", "constraint_name"),
    REPRESENTATIVE_COMPOSITE_CONSTRAINTS,
    ids=[item[1] for item in REPRESENTATIVE_COMPOSITE_CONSTRAINTS],
)
def test_representative_composite_unique_constraints_are_enforced(
    session_factory,
    table_name: str,
    constraint_name: str,
) -> None:
    table = Base.metadata.tables[table_name]
    constraint = next(
        item for item in table.constraints if item.name == constraint_name
    )
    with session_factory() as session:
        first = _mapped_instance(table_name, row=20)
        second = _mapped_instance(table_name, row=21)
        for column in constraint.columns:
            setattr(second, column.name, getattr(first, column.name))
        session.add(first)
        session.commit()
        session.add(second)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_nullable_pending_approval_key_allows_multiple_nulls(session_factory) -> None:
    with session_factory() as session:
        first = _mapped_instance("action_approvals", row=30, pending_key=None)
        second = _mapped_instance("action_approvals", row=31, pending_key=None)
        session.add_all([first, second])
        session.commit()
        assert session.scalar(select(db_models.ActionApprovalRecord).limit(1))


def test_transaction_rollback_and_causal_immutability(session_factory) -> None:
    with session_factory() as session:
        transient = _mapped_instance("cloud_accounts", row=40)
        key = transient.cloud_account_id
        session.add(transient)
        session.flush()
        session.rollback()
        assert session.get(db_models.CloudAccountRecord, (TEST_TENANT, key)) is None

        snapshot = _snapshot("snapshot:causal-immutable")
        save_snapshot(session, snapshot, tenant_id=TEST_TENANT)
        signal = _signal(snapshot.snapshot_id)
        save_signals(session, [signal], tenant_id=TEST_TENANT)
        incident = upsert_incident_from_orchestration(
            session, signal, None, [], tenant_id=TEST_TENANT
        )
        analysis = _causal_analysis(incident.incident_id, snapshot.snapshot_id)
        first = save_causal_analysis(session, analysis=analysis, tenant_id=TEST_TENANT)
        changed = analysis.model_copy(
            update={"generated_at": (NOW + timedelta(days=1)).isoformat()}
        )
        second = save_causal_analysis(session, analysis=changed, tenant_id=TEST_TENANT)
        assert second == first
        assert second.generated_at != changed.generated_at


def test_authenticated_change_source_receipt_survives_downstream_failure(
    session_factory,
    monkeypatch,
) -> None:
    """The commit before normalization is an intentional durability boundary."""
    seed_domain_tenant(session_factory.kw["bind"])
    with session_factory() as session:
        source_view = create_change_source_secure(
            session,
            tenant_id=TEST_TENANT,
            request=ChangeSourceCreate(
                name="PH-1C GitHub source",
                source_type=ChangeSourceType.GITHUB,
                credential="ph1c-github-webhook-secret",
                config={},
            ),
            actor="test:postgres-runtime",
            store=EncryptedDatabaseSecretStore(SecretStoreConfiguration(
                "encrypted_db", SecretKeyring({"test": os.urandom(32)}, "test")
            )),
        )
        source = load_change_source(session, source_id=source_view.source_id, tenant_id=TEST_TENANT)
        assert source is not None

        monkeypatch.setattr(change_source_ingest, "_verify", lambda *_, **__: None)

        def fail_normalization(**_):
            raise RuntimeError("deterministic downstream fixture failure")

        monkeypatch.setattr(change_source_ingest, "_normalize", fail_normalization)
        body = json.dumps(
            {
                "ref": "refs/heads/main",
                "after": "a" * 40,
                "repository": {"full_name": "acme/payment-api"},
            },
            sort_keys=True,
        ).encode()
        with pytest.raises(
            RuntimeError, match=r"Change source processing failed \(RuntimeError\)\."
        ):
            change_source_ingest.ingest_change_source_webhook(
                session,
                source=source,
                body=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "ph1c-delivery-1",
                },
            )

        session.expire_all()
        delivery = session.scalar(
            select(db_models.ChangeSourceDeliveryRecord).where(
                db_models.ChangeSourceDeliveryRecord.source_id
                == source_view.source_id
            )
        )
        dead_letter = session.scalar(
            select(db_models.ChangeSourceDeadLetterRecord).where(
                db_models.ChangeSourceDeadLetterRecord.source_id
                == source_view.source_id
            )
        )
        persisted_source = load_change_source(
            session, source_id=source_view.source_id, tenant_id=TEST_TENANT
        )
        assert delivery is not None
        assert delivery.status == "dead_letter"
        assert delivery.payload_sha256
        assert json.loads(delivery.payload_json)["after"] == "a" * 40
        assert dead_letter is not None
        assert dead_letter.delivery_id == delivery.delivery_id
        assert persisted_source is not None
        assert persisted_source.delivery_count == 1
        assert persisted_source.failure_count == 1
        assert persisted_source.status == "error"


def test_concurrent_deterministic_change_event_insert_has_one_winner(
    session_factory,
) -> None:
    barrier = Barrier(2)

    def insert(row: int) -> str:
        with session_factory() as session:
            record = _mapped_instance(
                "change_events",
                row=row,
                event_fingerprint="same-deterministic-fingerprint",
            )
            session.add(record)
            barrier.wait(timeout=10)
            try:
                session.commit()
                return "created"
            except IntegrityError:
                session.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(insert, (50, 51)))
    assert results == ["conflict", "created"]


def test_concurrent_execution_transition_has_one_winner(session_factory) -> None:
    with session_factory() as session:
        _seed_execution_parents(session)
        record, _ = create_execution_intent_record(
            session,
            snapshot=_execution_snapshot(),
            idempotency_key="9" * 64,
            creator=_principal(),
            created_at=NOW,
            tenant_id=TEST_TENANT,
        )
        execution_id = record.execution_id

    barrier = Barrier(2)

    def cancel(worker: int) -> bool:
        with session_factory() as session:
            record = load_execution_intent_record(
                session,
                incident_id="incident:postgres-execution",
                execution_id=execution_id,
                tenant_id=TEST_TENANT,
            )
            assert record is not None
            barrier.wait(timeout=10)
            result = atomic_cancel_execution_intent_record(
                session,
                record=record,
                actor=_principal(f"worker:{worker}"),
                reason=f"Concurrent cancellation {worker}",
                cancelled_at=NOW + timedelta(minutes=worker),
                tenant_id=TEST_TENANT,
            )
            return result is not None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(cancel, (1, 2)))
    assert sorted(results) == [False, True]


def test_read_modify_write_token_counter_observation(session_factory, capsys) -> None:
    with session_factory() as session:
        token = _mapped_instance(
            "agent_enrollment_tokens",
            row=60,
            enrollment_token_id="agent-token:postgres",
            use_count=0,
        )
        session.add(token)
        session.commit()

    barrier = Barrier(2)

    def increment(_: int) -> None:
        with session_factory() as session:
            token = session.get(
                db_models.AgentEnrollmentTokenRecord, "agent-token:postgres"
            )
            assert token is not None
            original = token.use_count
            barrier.wait(timeout=10)
            token.use_count = original + 1
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(increment, (1, 2)))
    with session_factory() as session:
        final_count = session.get(
            db_models.AgentEnrollmentTokenRecord, "agent-token:postgres"
        ).use_count
    print(f"PH1C_TOKEN_FINAL_USE_COUNT={final_count}")
    assert final_count in {1, 2}


def test_exact_schema_adoption_succeeds_and_drifted_adoption_refuses() -> None:
    with _temporary_database("adopt_exact") as engine:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            adopted = adopt_current_schema(connection)
            assert adopted.ok
        init_db(bind=engine)

    with _temporary_database("adopt_drift") as engine:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE ph1c_unexpected_table (id INTEGER)")
        with engine.begin() as connection:
            with pytest.raises(SchemaAuthorityError, match="not an exact match"):
                adopt_current_schema(connection)
            assert current_revisions(connection) == ()


def test_downgrade_then_reupgrade_restores_exact_schema() -> None:
    with _temporary_database("downgrade") as engine:
        _upgrade(engine)
        with engine.begin() as connection:
            command.downgrade(alembic_config(connection=connection), "base")
            assert current_revisions(connection) == ()
            assert _domain_table_names(connection) == set()
        _upgrade(engine)
        with engine.connect() as connection:
            assert inspect_schema_authority(connection).ok
