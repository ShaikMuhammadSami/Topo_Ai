"""Bidirectional IDOR, parent, pagination and same-Session acceptance."""

from datetime import timedelta

import pytest
from sqlalchemy import event, select, func
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.models.post_incident_report import PostIncidentReportGenerateRequest
from app.repositories.snapshot_repository import save_snapshot, list_snapshots
from app.repositories.tenant_scope import tenant_commit, tenant_get, TenantResourceNotFound
from app.services.post_incident_report import generate_post_incident_report
from test_tenant_adversarial_acceptance import hostile, worlds, machine
from test_domain_tenant_enforcement import two_tenants, tenant_app, sqlite_tenant_app
from test_tenant_foundation import _bearer
import test_lineage_candidate_admission as lineage


def clone_incident(session, tenant, identifier, title):
    original = tenant_get(session, models.IncidentRecord, "incident:same", tenant_id=tenant)
    values = {c.name: getattr(original, c.name) for c in models.IncidentRecord.__table__.columns}
    values.update(incident_id=identifier, title=title, summary=title)
    row = models.IncidentRecord(**values)
    session.add(row)
    tenant_commit(session, tenant_id=tenant)
    return row


@pytest.mark.parametrize("actor", ["A", "B"])
def test_foreign_incident_is_indistinguishable_from_absent_before_and_after_insert(hostile, actor):
    h = hostile
    worlds(h)
    own, foreign = (h.a, h.b) if actor == "A" else (h.b, h.a)
    headers = _bearer(h.tokens[actor], own)
    root = "/api/v1/incidents/incident:foreign-only"
    requests = [("GET", "/api/v1/incident-records/incident:foreign-only", None),
        ("GET", "/api/v1/incident-records/incident:foreign-only/signals", None),
        ("PATCH", "/api/v1/incident-records/incident:foreign-only/status", {"status": "resolved"}),
        *[("GET", root + suffix, None) for suffix in
          ("/briefing", "/causal-rca/latest", "/operational-context", "/ownership-impact", "/response-plan", "/outcome")],
        ("POST", root + "/copilot/sessions", {})]
    before = [h.client.request(method, path, headers=headers, json=body) for method, path, body in requests]
    assert all(r.status_code == 404 for r in before), [(r.status_code, r.text) for r in before]
    with h.factory() as session:
        row = clone_incident(session, foreign, "incident:foreign-only", "FOREIGN_PRIVATE_INCIDENT")
        initial_status = row.status
    for (method, path, body), absent in zip(requests, before):
        response = h.client.request(method, path, headers=headers, json=body)
        assert response.status_code == absent.status_code == 404, path
        assert response.content == absent.content, path
        assert "FOREIGN_PRIVATE" not in response.text
    with h.factory() as session:
        assert tenant_get(session, models.IncidentRecord, "incident:foreign-only", tenant_id=foreign).status == initial_status


def test_interleaved_pagination_uses_tenant_before_order_limit_and_offset(hostile):
    h = hostile
    queries = []
    with h.factory() as session:
        for index in range(4):
            for tenant, marker in ((h.a, "A"), (h.b, "B")):
                graph = lineage._snapshot(snapshot_id=f"snapshot:{marker}:{index}")
                graph.collected_at += timedelta(minutes=2 * index + (tenant == h.b))
                save_snapshot(session, graph, tenant_id=tenant)
        engine = session.get_bind()
        def capture(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                queries.append(statement)
        event.listen(engine, "before_cursor_execute", capture)
        try:
            for tenant, marker in ((h.a, "A"), (h.b, "B")):
                assert [s.snapshot_id for s in list_snapshots(session, limit=1, offset=1, tenant_id=tenant)] == [f"snapshot:{marker}:2"]
                assert [s.snapshot_id for s in list_snapshots(session, limit=1, tenant_id=tenant)] == [f"snapshot:{marker}:3"]
                assert list_snapshots(session, limit=1, offset=4, tenant_id=tenant) == []
        finally:
            event.remove(engine, "before_cursor_execute", capture)
    assert len(queries) == 6
    for query in queries:
        lowered = query.lower()
        assert "tenant_id =" in lowered and lowered.index("where") < lowered.index("order by") < lowered.index("limit")


def test_same_session_four_incidents_update_delete_rollback_are_partitioned(hostile):
    h = hostile
    worlds(h, analysis=False)
    with h.factory() as session:
        for tenant, marker in ((h.a, "A"), (h.b, "B")):
            clone_incident(session, tenant, "incident:second", marker + "_SECOND")
        ax, bx = [tenant_get(session, models.IncidentRecord, "incident:same", tenant_id=t) for t in (h.a, h.b)]
        ay, by = [tenant_get(session, models.IncidentRecord, "incident:second", tenant_id=t) for t in (h.a, h.b)]
        assert len({id(r) for r in (ax, bx, ay, by)}) == 4
        b_before = [(r.title, r.status, r.topology_snapshot_id) for r in (bx, by)]
        ax.title = "A_UPDATE"
        tenant_commit(session, tenant_id=h.a)
        session.delete(ay)
        tenant_commit(session, tenant_id=h.a)
        assert [(r.title, r.status, r.topology_snapshot_id) for r in (bx, by)] == b_before
        assert tenant_get(session, models.IncidentRecord, "incident:second", tenant_id=h.a) is None
        ax.title = "A_UNCOMMITTED"
        bx.title = "ATTEMPTED_FOREIGN_WRITE"
        with pytest.raises(TenantResourceNotFound):
            tenant_commit(session, tenant_id=h.a)
        session.rollback()
        assert ax.title == "A_UPDATE"
        assert [(r.title, r.status, r.topology_snapshot_id) for r in (bx, by)] == b_before
        # Same-tenant duplicate fails closed, including after a prior rollback.
        with pytest.raises(IntegrityError):
            clone_incident(session, h.a, "incident:same", "DUPLICATE")
        session.rollback()
        assert bx.title == "B_PRIVATE_EVIDENCE"


def test_report_versions_children_and_exports_do_not_cross_tenants(hostile):
    h = hostile
    worlds(h)
    reports = {}
    with h.factory() as session:
        for tenant in (h.a, h.b):
            reports[tenant] = generate_post_incident_report(session, incident_id="incident:same",
                request=PostIncidentReportGenerateRequest(provider="deterministic"), tenant_id=tenant)
            assert reports[tenant].version == 1
    for own, foreign, actor in ((h.a, h.b, "A"), (h.b, h.a, "B")):
        own_id, foreign_id = reports[own].report_id, reports[foreign].report_id
        assert own_id != foreign_id  # content hash differs; version business key overlaps
        headers = _bearer(h.tokens[actor], own)
        base = "/api/v1/incidents/incident:same/reports/"
        good = h.client.get(base + own_id + "/export?format=json", headers=headers)
        assert good.status_code == 200 and actor + "_PRIVATE" in good.text
        assert ("B" if actor == "A" else "A") + "_PRIVATE" not in good.text
        for suffix in ("", "/export?format=json", "/export?format=markdown"):
            assert h.client.get(base + foreign_id + suffix, headers=headers).status_code == 404
        assert h.client.patch(base + foreign_id, headers=headers, json={"review_notes": "foreign edit"}).status_code == 404
        assert h.client.get("/api/v1/incidents/wrong-parent/reports/" + own_id, headers=headers).status_code == 404
        foreign_actions = reports[foreign].action_items
        assert foreign_actions
        response = h.client.patch(base + own_id + "/actions/" + foreign_actions[0].action_item_id,
            headers=headers, json={"notes": "foreign child mutation"})
        assert response.status_code == 404
    with h.factory() as session:
        assert session.scalar(select(func.count()).select_from(models.PostIncidentReportRecord)) == 2
        assert all(r.review_notes is None for r in session.scalars(select(models.PostIncidentReportRecord)))


def test_machine_admin_idor_revocation_disabled_tenant_and_auth_domains(hostile):
    h = hostile
    agents = {h.a: machine(h, h.a, "A"), h.b: machine(h, h.b, "B")}
    for own, other, actor in ((h.a, h.b, "A"), (h.b, h.a, "B")):
        own_agent, other_agent = agents[own], agents[other]
        headers = _bearer(h.tokens[actor], own)
        for suffix in ("", "/health", "/plugins", "/cloud-status"):
            assert h.client.get(f'/api/v1/agents/{other_agent["agent_id"]}{suffix}', headers=headers).status_code == 404
            assert h.client.get(f'/api/v1/agents/{own_agent["agent_id"]}{suffix}', headers=headers).status_code == 200
        assert h.client.post(f'/api/v1/agents/{other_agent["agent_id"]}/revoke', headers=headers).status_code == 404
        for name in (actor, "Service" + actor):
            assert h.client.get("/api/v1/agent/config", headers=_bearer(h.tokens[name], own)).status_code == 401
        assert h.client.get("/api/v1/incident-records", headers=_bearer(own_agent["agent_token"], own)).status_code == 401
    a, b = agents[h.a], agents[h.b]
    assert h.client.post(f'/api/v1/agents/{a["agent_id"]}/revoke', headers=_bearer(h.tokens["A"], h.a)).status_code == 200
    assert h.client.get("/api/v1/agent/config", headers=_bearer(a["agent_token"], h.b)).status_code == 401
    assert h.client.get("/api/v1/agent/config", headers=_bearer(b["agent_token"], h.a)).status_code == 200
    with h.factory.begin() as session:
        session.get(models.TenantRecord, h.b).status = "disabled"
    assert h.client.get("/api/v1/agent/config", headers=_bearer(b["agent_token"], h.a)).status_code == 401
    with h.factory() as session:
        assert session.get(models.TopoAgentRecord, b["agent_id"]).tenant_id == h.b


def test_identity_override_business_key_update_delete_and_count_are_scoped(hostile):
    h = hostile
    identifiers = {}
    for tenant, actor in ((h.a, "A"), (h.b, "B")):
        body = {"cluster_name": "prod", "namespace": "default", "entity_kind": "Deployment", "entity_name": "checkout",
            "action": "assign", "canonical_name": actor + "_PRIVATE_CHECKOUT", "reason": "Explicit fixture override"}
        response = h.client.post("/api/v1/identities/overrides", headers=_bearer(h.tokens[actor], tenant), json=body)
        assert response.status_code == 201, response.text
        identifiers[tenant] = response.json()["override_id"]
        again = h.client.post("/api/v1/identities/overrides", headers=_bearer(h.tokens[actor], tenant), json=body)
        assert again.status_code == 201 and again.json()["override_id"] == identifiers[tenant]
    for own, foreign, actor in ((h.a, h.b, "A"), (h.b, h.a, "B")):
        headers = _bearer(h.tokens[actor], own)
        listed = h.client.get("/api/v1/identities/overrides", headers=headers)
        assert listed.status_code == 200 and [r["override_id"] for r in listed.json()] == [identifiers[own]]
        assert h.client.delete("/api/v1/identities/overrides/" + identifiers[foreign], headers=headers).status_code == 404
    assert h.client.delete("/api/v1/identities/overrides/" + identifiers[h.a], headers=_bearer(h.tokens["A"], h.a)).status_code == 200
    with h.factory() as session:
        assert session.get(models.IdentityOverrideRecord, identifiers[h.b]).active
