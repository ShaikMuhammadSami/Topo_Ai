"""Real authentication + two-tenant persistence; no TenantContext override."""

from collections import Counter
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.db import models
from app.models.incident_records import IncidentSeverity
from app.repositories.tenant_scope import (
    TenantResourceNotFound,
    UNOWNED_MACHINE,
    tenant_commit,
    tenant_get,
)
from app.security.tenant_context import require_tenant_context
from app.security.tenant_routing import (
    MACHINE_AUTHORITY_ROUTES,
    TenantRouteDomain,
    classify_tenant_route,
)
from test_authentication_acceptance import _registered_routes
from test_domain_tenant_migration import PH3C_DOMAIN, _seed_pre_tenancy_row
from test_tenant_foundation import (
    tenant_app as sqlite_tenant_app,
    _bearer,
    _create_named,
    _create_tenant,
)


@pytest.fixture
def tenant_app(sqlite_tenant_app):
    if not os.getenv("TOPO_TEST_POSTGRES_URL"):
        yield sqlite_tenant_app
        return
    from sqlalchemy.orm import sessionmaker
    from app.main import create_app
    from test_postgres_runtime_compatibility import _temporary_database, _upgrade

    sqlite_application, _, tokens = sqlite_tenant_app
    with _temporary_database("ph3d_domain") as engine:
        _upgrade(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        application = create_app(
            auth_configuration=sqlite_application.state.auth_configuration,
            session_factory=factory,
            database_initializer=lambda: None,
        )
        yield application, factory, tokens


@pytest.fixture
def two_tenants(tenant_app):
    application, factory, tokens = tenant_app
    with TestClient(application) as client:
        a = _create_tenant(client, tokens["bootstrap"], "Shared display name")[
            "tenant_id"
        ]
        b = _create_tenant(client, tokens["other_admin"], "Shared display name")[
            "tenant_id"
        ]
        yield client, factory, tokens, a, b


def _has_tenant_dependency(dependency):
    return dependency.call is require_tenant_context or any(
        _has_tenant_dependency(child) for child in dependency.dependencies
    )


def test_route_accounting_and_real_dependency_graph(tenant_app):
    application, _, _ = tenant_app
    counts = Counter()
    deferred = set()
    for route in _registered_routes(application):
        for method in route.methods:
            classification = classify_tenant_route(method, route.path)
            assert classification is not None, (method, route.path)
            counts[classification] += 1
            if classification is TenantRouteDomain.PH3D_TENANT_REQUIRED:
                assert _has_tenant_dependency(route.dependant), (method, route.path)
            if classification is TenantRouteDomain.MACHINE_AUTHORITY_DEFERRED:
                deferred.add((method, route.path))
                assert not _has_tenant_dependency(route.dependant)
    assert deferred == set(MACHINE_AUTHORITY_ROUTES)
    assert counts == {
        TenantRouteDomain.PH3D_TENANT_REQUIRED: 104,
        TenantRouteDomain.MACHINE_AUTHORITY_DEFERRED: 12,
        TenantRouteDomain.MACHINE_DEFERRED: 9,
        TenantRouteDomain.TENANT_CONTROL: 7,
        TenantRouteDomain.SECURITY_GLOBAL: 9,
        TenantRouteDomain.PUBLIC: 2,
    }


@pytest.mark.parametrize("method,path", sorted(MACHINE_AUTHORITY_ROUTES))
def test_deferred_administration_remains_authenticated(tenant_app, method, path):
    application, _, _ = tenant_app
    with TestClient(application) as client:
        response = client.request(
            method,
            path.replace("{agent_id}", "absent").replace("{source_id}", "absent"),
        )
    assert response.status_code == 401


@pytest.mark.parametrize("table_name", sorted(PH3C_DOMAIN))
def test_every_domain_get_scopes_before_identity_lookup(two_tenants, table_name):
    _, factory, _, a, b = two_tenants
    model = next(
        mapper.class_
        for mapper in models.Base.registry.mappers
        if mapper.local_table.name == table_name
    )
    primary = inspect(model).primary_key[0].key
    with factory.begin() as session:
        _seed_pre_tenancy_row(
            session.connection(), table_name, **{primary: "foreign-row", "tenant_id": b}
        )
    with factory() as session:
        assert tenant_get(session, model, "foreign-row", tenant_id=a) is None
        assert tenant_get(session, model, "foreign-row", tenant_id=b) is not None
        assert (
            tenant_get(session, model, "foreign-row", tenant_id=UNOWNED_MACHINE) is None
        )
        with pytest.raises(ValueError, match="TENANT_CONTEXT_REQUIRED"):
            tenant_get(session, model, "foreign-row", tenant_id=None)


def _incident(factory, tenant_id, identifier):
    with factory.begin() as session:
        _seed_pre_tenancy_row(
            session.connection(),
            "incidents",
            tenant_id=tenant_id,
            incident_id=identifier,
            fingerprint=identifier,
            status="open",
            severity=IncidentSeverity.CRITICAL.value,
            title="Same workload failure",
            cluster_name="shared",
            namespace="payments",
        )


def test_incident_idor_list_update_and_service_fixed_binding(two_tenants):
    client, factory, tokens, a, b = two_tenants
    _incident(factory, a, "incident:a")
    _incident(factory, b, "incident:b")
    headers = _bearer(tokens["bootstrap"], a)
    assert client.get("/api/v1/incident-records").status_code == 401
    missing = client.get(
        "/api/v1/incident-records", headers=_bearer(tokens["bootstrap"])
    )
    assert (
        missing.status_code == 400
        and missing.json()["detail"] == "TENANT_CONTEXT_REQUIRED"
    )
    assert (
        client.get(
            "/api/v1/incident-records", headers=_bearer(tokens["bootstrap"], b)
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/incident-records/incident:a", headers=headers).status_code
        == 200
    )
    assert (
        client.get("/api/v1/incident-records/incident:b", headers=headers).status_code
        == 404
    )
    listed = client.get(
        "/api/v1/incident-records?limit=1&namespace=payments", headers=headers
    )
    assert [item["incident_id"] for item in listed.json()] == ["incident:a"]
    assert (
        client.patch(
            "/api/v1/incident-records/incident:b/status",
            headers=headers,
            json={"status": "resolved"},
        ).status_code
        == 404
    )
    service = _create_named(
        client,
        tokens["bootstrap"],
        caller_type="service_api",
        subject="test:worker",
        roles=["admin"],
        tenant_id=a,
    )
    service_headers = _bearer(service["api_credential"])
    assert (
        client.get(
            "/api/v1/incident-records/incident:a", headers=service_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v1/incident-records/incident:b", headers=service_headers
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/v1/incident-records",
            headers={**service_headers, "X-Topo-Tenant-ID": b},
        ).status_code
        == 403
    )
    # A legacy/unbound service still authenticates, but has no domain authority.
    with factory.begin() as session:
        binding = session.scalar(
            select(models.ServiceApiTenantBindingRecord).where(
                models.ServiceApiTenantBindingRecord.credential_id
                == service["credential_id"]
            )
        )
        session.delete(binding)
    assert (
        client.get("/api/v1/system/whoami", headers=service_headers).status_code == 200
    )
    denied = client.get("/api/v1/incident-records/incident:a", headers=service_headers)
    assert denied.status_code == 403
    assert denied.json() == {"detail": "TENANT_ACCESS_DENIED"}


def test_human_write_context_and_cross_tenant_parent(two_tenants):
    client, factory, tokens, a, b = two_tenants
    headers = _bearer(tokens["bootstrap"], a)
    body = {"service_name": "payments", "owner_team": "platform"}
    created = client.post("/api/v1/ownership/mappings", headers=headers, json=body)
    assert created.status_code == 201
    assert (
        client.post(
            "/api/v1/ownership/mappings", headers=headers, json={**body, "tenant_id": b}
        ).status_code
        == 422
    )
    with factory() as session:
        record = session.scalar(select(models.OwnershipMappingRecord))
        assert record.tenant_id == a
    _incident(factory, b, "incident:foreign")
    with factory() as session:
        child = models.CopilotSessionRecord(
            session_id="copilot:cross",
            incident_id="incident:foreign",
            title="Foreign parent",
            tenant_id=a,
        )
        session.add(child)
        with pytest.raises(TenantResourceNotFound):
            tenant_commit(session, tenant_id=a)
        session.rollback()


def test_cross_tenant_domain_ids_and_delete_are_absent(two_tenants):
    client, factory, tokens, a, b = two_tenants
    headers = _bearer(tokens["bootstrap"], a)
    _incident(factory, b, "incident:foreign")
    with factory.begin() as session:
        for table, key, identifier in (
            ("topology_snapshots", "snapshot_id", "snapshot:foreign"),
            ("change_events", "event_id", "event:foreign"),
            ("identity_overrides", "override_id", "override:foreign"),
            ("post_incident_reports", "report_id", "report:foreign"),
        ):
            _seed_pre_tenancy_row(
                session.connection(), table, **{key: identifier, "tenant_id": b}
            )
    for path in (
        "/api/v1/snapshots/snapshot:foreign",
        "/api/v1/change-events/event:foreign",
        "/api/v1/incidents/incident:foreign/ownership-impact",
        "/api/v1/incidents/incident:foreign/outcome",
        "/api/v1/incidents/incident:foreign/reports/report:foreign",
    ):
        assert client.get(path, headers=headers).status_code == 404, path
    assert (
        client.delete(
            "/api/v1/identities/overrides/override:foreign", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/v1/incidents/incident:foreign/reports/report:foreign",
            headers=headers,
            json={"review_notes": "Reviewed"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/incidents/incident:foreign/copilot/sessions",
            headers=headers,
            json={},
        ).status_code
        == 404
    )
    with factory() as session:
        assert (
            session.get(models.IdentityOverrideRecord, "override:foreign").tenant_id
            == b
        )


def test_snapshot_latest_and_unowned_quarantine(two_tenants):
    from datetime import timedelta
    from app.repositories.snapshot_repository import list_snapshots, save_snapshot
    from app.services.lifecycle_status import build_lifecycle_status
    from test_continuous_lifecycle import NOW, _snapshot

    client, factory, tokens, a, b = two_tenants
    with factory() as session:
        save_snapshot(session, _snapshot("snapshot:a", observed_at=NOW), tenant_id=a)
        save_snapshot(
            session,
            _snapshot("snapshot:b", observed_at=NOW + timedelta(minutes=1)),
            tenant_id=b,
        )
        save_snapshot(
            session,
            _snapshot("snapshot:unowned", observed_at=NOW + timedelta(minutes=2)),
            tenant_id=UNOWNED_MACHINE,
        )
        assert [
            s.snapshot_id for s in list_snapshots(session, limit=1, tenant_id=a)
        ] == ["snapshot:a"]
        assert list_snapshots(session, offset=1, tenant_id=a) == []
        status = build_lifecycle_status(session, tenant_id=a)
        assert "snapshot:b" not in status.model_dump_json()
        assert "snapshot:unowned" not in status.model_dump_json()
    headers = _bearer(tokens["bootstrap"], a)
    assert (
        client.get("/api/v1/snapshots/snapshot:a", headers=headers).status_code == 200
    )
    assert (
        client.get("/api/v1/snapshots/snapshot:unowned", headers=headers).status_code
        == 404
    )


def test_background_lifecycle_propagates_owned_root_and_correlates_in_tenant(
    two_tenants,
):
    from app.repositories.incident_record_repository import find_correlatable_incident
    from app.repositories.snapshot_repository import save_snapshot
    from app.services.continuous_lifecycle import ingest_failure_signal_batch
    from app.services.incident_briefing import build_incident_briefing
    from test_continuous_lifecycle import NOW, _signal, _snapshot

    _, factory, _, a, b = two_tenants
    with factory() as session:
        snapshot = _snapshot("snapshot:background")
        save_snapshot(session, snapshot, tenant_id=a)
        result = ingest_failure_signal_batch(
            session,
            signals=[_signal("signal:background", snapshot_id=snapshot.snapshot_id)],
            tenant_id=a,
        )
        incident_id = result.results[0].incident_id
        incident = session.get(models.IncidentRecord, incident_id)
        assert (
            incident.tenant_id == a
            and incident.topology_snapshot_id == snapshot.snapshot_id
        )
        assert (
            find_correlatable_incident(
                session,
                fingerprint=incident.fingerprint,
                observed_after=NOW,
                tenant_id=b,
            )
            is None
        )
        assert (
            find_correlatable_incident(
                session,
                fingerprint=incident.fingerprint,
                observed_after=NOW,
                tenant_id=a,
            ).incident_id
            == incident_id
        )
        assert (
            session.scalar(
                select(models.CausalAnalysisRecord).where(
                    models.CausalAnalysisRecord.incident_id == incident_id
                )
            ).tenant_id
            == a
        )
        with pytest.raises(ValueError, match="not found"):
            build_incident_briefing(session, incident_id=incident_id, tenant_id=b)
        # Every converted writer used in this real pipeline owns its output.
        for model in (
            models.SnapshotRecord,
            models.SignalRecord,
            models.IncidentRecord,
            models.CausalAnalysisRecord,
        ):
            assert all(row.tenant_id == a for row in session.scalars(select(model)))
        from domain_tenant_fixtures import null_ownership_inventory

        assert all(
            item["null"] == 0 for item in null_ownership_inventory(session).values()
        )


def test_revoked_membership_and_disabled_tenant_preserve_authentication(two_tenants):
    client, factory, tokens, a, b = two_tenants
    headers = _bearer(tokens["bootstrap"], a)
    assert client.get("/api/v1/incident-records", headers=headers).status_code == 200
    with factory.begin() as session:
        membership = session.scalar(
            select(models.TenantMembershipRecord).where(
                models.TenantMembershipRecord.tenant_id == a
            )
        )
        membership.status = "disabled"
    assert client.get("/api/v1/incident-records", headers=headers).status_code == 403
    assert client.get("/api/v1/system/whoami", headers=headers).status_code == 200
    with factory.begin() as session:
        session.get(models.TenantRecord, b).status = "disabled"
    assert (
        client.get(
            "/api/v1/incident-records", headers=_bearer(tokens["other_admin"], b)
        ).status_code
        == 403
    )


def test_payload_snapshot_and_autoflush_child_cannot_reference_foreign_parent(
    two_tenants,
):
    from app.models.incident_copilot import CopilotMessageRole
    from app.repositories.copilot_repository import save_copilot_message
    from app.repositories.signal_repository import save_signals
    from app.repositories.snapshot_repository import save_snapshot
    from test_continuous_lifecycle import _signal, _snapshot

    _, factory, _, a, b = two_tenants
    _incident(factory, b, "incident:foreign-parent")
    with factory() as session:
        save_snapshot(session, _snapshot("snapshot:foreign-parent"), tenant_id=b)
        with pytest.raises(TenantResourceNotFound):
            save_signals(
                session,
                [_signal("signal:bad-parent", snapshot_id="snapshot:foreign-parent")],
                tenant_id=a,
            )
        session.rollback()
        # save_copilot_message performs a session lookup after adding its child.
        # Even autoflush=True must not bypass ownership/reference validation.
        session.autoflush = True
        with pytest.raises(TenantResourceNotFound):
            save_copilot_message(
                session,
                session_id="session:absent",
                incident_id="incident:foreign-parent",
                role=CopilotMessageRole.USER,
                content="Must not persist",
                tenant_id=a,
            )
        session.rollback()
        assert session.scalar(select(models.SignalRecord)) is None
        assert session.scalar(select(models.CopilotMessageRecord)) is None
