"""PH-3G independent hostile corpus. Real auth, repositories and reasoning.

Only outbound network transports are substituted. No default tenant, authority
override or globally autouse fixture is installed. The app/database fixture runs
on disposable PostgreSQL when TOPO_TEST_POSTGRES_URL is explicitly configured.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db import models
from app.models.causal_rca import CausalAnalysisRequest
from app.models.auth import ApiCredentialCallerType, ApiCredentialCreate
from app.models.incident_outcome import IncidentOutcome, IncidentResponseActionObservation
from app.models.ownership import OwnershipMappingCreate
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.repositories.incident_outcome_repository import load_incident_outcome, save_incident_outcome
from app.repositories.incident_record_repository import load_incident_record
from app.repositories.snapshot_repository import load_snapshot
from app.repositories.tenant_scope import TenantResourceNotFound, tenant_get, tenant_commit
from app.services.causal_rca import analyze_causal_rca
from app.services.auth_api_credential_service import create_auth_api_credential
from app.services.incident_context import build_incident_operational_context
from app.services.incident_memory import build_incident_feature_profile
from app.services.ownership_resolver import create_ownership_mapping
from app.services.tenant_world_model import require_world_value
from test_domain_tenant_enforcement import two_tenants, tenant_app, sqlite_tenant_app
from test_tenant_foundation import _bearer, _create_named
from test_tenant_world_model import seed_world
import test_lineage_candidate_admission as lineage
import test_continuous_lifecycle as lifecycle


@pytest.fixture
def hostile(two_tenants):
    client, factory, tokens, a, b = two_tenants
    principals = {}
    for name, subject, roles in (
        ("AB", "ph3g:both", ["operator"]),
        ("AdminNoB", "ph3g:admin-no-b", ["admin"]),
    ):
        with factory() as session:
            principals[name] = create_auth_api_credential(
                session,
                request=ApiCredentialCreate(
                    name=f"PH-3G {name}",
                    caller_type=ApiCredentialCallerType.HUMAN_API,
                    subject=subject,
                    display_name=subject,
                    roles=roles,
                    expires_in_days=30,
                ),
                created_by_subject="test:bootstrap-admin",
            ).api_credential
        for tenant, administrator in ((a, "bootstrap"), (b, "other_admin")):
            if name == "AdminNoB" and tenant == b:
                continue
            response = client.post("/api/v1/tenant-memberships",
                headers=_bearer(tokens[administrator], tenant),
                json={"subject": subject, "role": "tenant_admin"})
            assert response.status_code == 200, response.text
    for name, tenant, administrator in (("ServiceA", a, "bootstrap"), ("ServiceB", b, "other_admin")):
        principals[name] = _create_named(client, tokens[administrator],
            caller_type="service_api", subject="ph3g:" + name, roles=["operator"],
            tenant_id=tenant)["api_credential"]
    principals.update(A=tokens["bootstrap"], B=tokens["other_admin"])
    return SimpleNamespace(client=client, factory=factory, a=a, b=b, tokens=principals)


def worlds(corpus, *, analysis=True):
    with corpus.factory() as session:
        for tenant, label in ((corpus.a, "A_PRIVATE_EVIDENCE"), (corpus.b, "B_PRIVATE_EVIDENCE")):
            seed_world(session, tenant, label=label)
            create_ownership_mapping(session, OwnershipMappingCreate(
                entity_id="pod:app", owner_team="payments", service_name="checkout",
                owner_email=label + "@example.test", oncall_contact=label,
                business_capability=label, criticality="tier_1"), tenant_id=tenant)
            if analysis:
                analyze_causal_rca(session, incident_id="incident:same",
                    request=CausalAnalysisRequest(), tenant_id=tenant)


def tenant_rows(session, model, tenant):
    return session.scalars(select(model).where(model.tenant_id == tenant)).all()


def test_human_membership_switch_and_fixed_service_authority(hostile):
    h = hostile
    worlds(h)
    path = "/api/v1/incidents/incident:same/briefing"
    for tenant, own, other, label, foreign in ((h.a, "A", h.b, "A_PRIVATE", "B_PRIVATE"),
                                              (h.b, "B", h.a, "B_PRIVATE", "A_PRIVATE")):
        for actor in (own, "AB", "Service" + own):
            response = h.client.get(path, headers=_bearer(h.tokens[actor], tenant))
            assert response.status_code == 200, response.text
            assert label in response.text and foreign not in response.text
        assert h.client.get(path, headers=_bearer(h.tokens[own], other)).status_code == 403
        service = h.tokens["Service" + own]
        assert h.client.get(path, headers=_bearer(service)).status_code == 200
        denied = h.client.get(path, headers=_bearer(service, other))
        assert denied.status_code == 403 and denied.json() == {"detail": "TENANT_ACCESS_DENIED"}
    assert h.client.get(path, headers=_bearer(h.tokens["AdminNoB"], h.b)).status_code == 403
    assert h.client.get(path, headers=_bearer(h.tokens["AB"])).status_code == 400
    # An authenticated AB actor loses only its A membership, not its credential.
    members = h.client.get("/api/v1/tenant-memberships", headers=_bearer(h.tokens["A"], h.a)).json()
    member = next(item for item in members if item["subject"] == "ph3g:both")
    assert h.client.post(f'/api/v1/tenant-memberships/{member["membership_id"]}/disable',
        headers=_bearer(h.tokens["A"], h.a)).status_code == 200
    assert h.client.get(path, headers=_bearer(h.tokens["AB"], h.a)).json() == {"detail": "TENANT_ACCESS_DENIED"}
    assert h.client.get(path, headers=_bearer(h.tokens["AB"], h.b)).status_code == 200
    assert h.client.get("/api/v1/system/whoami", headers=_bearer(h.tokens["AB"])).status_code == 200


def test_real_lineage_rank_ledger_impact_stable_after_foreign_insertion(hostile):
    h = hostile
    with h.factory() as session:
        seed_world(session, h.a, label="A_PRIVATE_EVIDENCE")
        before = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=h.a)
        impact = build_incident_operational_context(session, "incident:same", tenant_id=h.a)
        seed_world(session, h.b, label="B_PRIVATE_STRONG_NEWER_EVIDENCE")
        foreign = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=h.b)
        after = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), persist=False, tenant_id=h.a)
        assert before.hypotheses and foreign.hypotheses
        # Exact semantic collections; no score, stance, support, ID or time masking.
        for name in ("analysis_id", "topology_snapshot_id", "candidate_selection_audit", "hypotheses", "top_hypothesis", "evidence", "nodes", "edges", "confidence_semantics"):
            assert getattr(before, name) == getattr(after, name), name
        assert impact == build_incident_operational_context(session, "incident:same", tenant_id=h.a)
        assert "B_PRIVATE" not in after.model_dump_json()
        assert latest_causal_analysis(session, incident_id="incident:same", tenant_id=h.a).analysis_id == before.analysis_id


@pytest.mark.parametrize("child", ["entity", "relationship", "serialized", "metadata"])
def test_mixed_world_children_and_lost_authority_are_rejected(hostile, child):
    h = hostile
    worlds(h, analysis=False)
    with h.factory() as session:
        a = load_snapshot(session, "snapshot:pinned", tenant_id=h.a)
        b = load_snapshot(session, "snapshot:pinned", tenant_id=h.b)
        if child == "entity":
            a.entities[0] = b.entities[0]
        elif child == "relationship":
            a.relationships[0] = b.relationships[0]
        else:
            a = type(a).model_validate_json(b.model_dump_json())
            if child == "metadata":
                a.metadata.update(tenant_id=h.a, owner=h.a, _topo_world_ownership={"tenant_id": h.a})
        with pytest.raises(TenantResourceNotFound):
            require_world_value(a, tenant_id=h.a)


def save_outcome(session, tenant, *, incident="incident:same", label="outcome"):
    outcome = IncidentOutcome(outcome_id="outcome:" + incident, incident_id=incident,
        status="resolved", started_at=lineage.INCIDENT_TIME,
        resolved_at=lineage.INCIDENT_TIME + timedelta(minutes=10),
        historical_topology_snapshot_id="snapshot:pinned", rca_verdict="confirmed",
        rca_confidence=0.9, resolution_summary=label)
    save_incident_outcome(session, outcome=outcome, source={}, tenant_id=tenant)
    return load_incident_outcome(session, incident_id=incident, tenant_id=tenant)


def test_foreign_outcome_prefetch_rejected_before_historical_profile(hostile):
    h = hostile
    worlds(h)
    with h.factory() as session:
        save_outcome(session, h.a, label="A_PRIVATE_OUTCOME")
        foreign = save_outcome(session, h.b, label="B_PRIVATE_OUTCOME")
        incident = load_incident_record(session, "incident:same", tenant_id=h.a)
        analysis = latest_causal_analysis(session, incident_id="incident:same", tenant_id=h.a)
        with pytest.raises(TenantResourceNotFound):
            build_incident_feature_profile(session, incident=incident, analysis=analysis,
                outcome=foreign, historical=True, tenant_id=h.a)


def test_unowned_outcome_source_cannot_inject_foreign_history(hostile):
    h = hostile
    worlds(h)
    with h.factory() as session:
        own = save_outcome(session, h.a, label="A_PRIVATE_OUTCOME")
        action = IncidentResponseActionObservation(action_instance_id="action:manual",
            response_plan_action_id="plan:rollback", action_type="rollback", title="Manual rollback",
            source="responder", result="successful", effectiveness="effective", effectiveness_reason="Observed recovery")
        own.primary_resolution_action = action
        save_incident_outcome(session, outcome=own, source={"response_plan": {"actions": [
            {"action_id": "plan:rollback", "runbook_url": "https://a.example.test/owned"}]}}, tenant_id=h.a)
        own = load_incident_outcome(session, incident_id="incident:same", tenant_id=h.a)
        with pytest.raises(TenantResourceNotFound):
            build_incident_feature_profile(session,
                incident=load_incident_record(session, "incident:same", tenant_id=h.a),
                analysis=latest_causal_analysis(session, incident_id="incident:same", tenant_id=h.a),
                outcome=own, outcome_source_data={"response_plan": {"actions": [
                    {"action_id": "plan:rollback", "runbook_url": "https://b.example.test/private"}]}},
                historical=True, tenant_id=h.a)


def test_foreign_loaded_outcome_cannot_overwrite_owned_outcome(hostile):
    h = hostile
    worlds(h)
    with h.factory() as session:
        own = save_outcome(session, h.a, label="A_PRIVATE_OUTCOME")
        foreign = save_outcome(session, h.b, label="B_PRIVATE_OUTCOME")
        with pytest.raises(TenantResourceNotFound):
            save_incident_outcome(session, outcome=foreign, source={}, tenant_id=h.a)
        session.rollback()
        assert load_incident_outcome(session, incident_id="incident:same", tenant_id=h.a) == own


@pytest.mark.parametrize("actor", ["A", "B"])
def test_history_and_response_prefetch_cannot_borrow_other_tenant(hostile, actor):
    from test_tenant_adversarial_llm import history
    from app.services.incident_similarity import build_historical_incident_intelligence
    from app.services.response_plan import build_incident_response_plan
    from app.services.response_intelligence import build_incident_response_intelligence
    h = hostile
    worlds(h)
    own, other = (h.a, h.b) if actor == "A" else (h.b, h.a)
    with h.factory() as session:
        # B contains an exact matching historical case before A has any. It
        # must not appear as A's nearest result or historical action support.
        history(session, other, "FOREIGN_PRIVATE")
        empty = build_historical_incident_intelligence(session, incident_id="incident:same", min_similarity=0, tenant_id=own)
        assert empty.matches == []
        history(session, own, "OWN_PRIVATE")
        local = build_historical_incident_intelligence(session, incident_id="incident:same", min_similarity=0, tenant_id=own)
        assert len(local.matches) == 1 and "OWN_PRIVATE" in local.model_dump_json()
        assert "FOREIGN_PRIVATE" not in local.model_dump_json()
        foreign = build_historical_incident_intelligence(session, incident_id="incident:same", min_similarity=0, tenant_id=other)
        with pytest.raises(TenantResourceNotFound):
            build_incident_response_intelligence(session, incident_id="incident:same", historical_intelligence=foreign, tenant_id=own)
        plan = build_incident_response_plan(session, "incident:same", tenant_id=other)
        with pytest.raises(TenantResourceNotFound):
            build_incident_response_intelligence(session, incident_id="incident:same", response_plan=plan, tenant_id=own)


@pytest.mark.parametrize("missing", ["source", "provider"])
def test_foreign_lineage_cannot_change_missing_into_support_or_contradiction(hostile, missing):
    h = hostile
    with h.factory() as session:
        seed_world(session, h.a, source=missing != "source", provider=missing != "provider", label="A_PRIVATE")
        before = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=h.a)
        assert not before.hypotheses
        seed_world(session, h.b, label="B_PRIVATE")
        foreign = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=h.b)
        assert foreign.hypotheses
        after = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), persist=False, tenant_id=h.a)
        assert after.hypotheses == before.hypotheses == []
        assert after.candidate_selection_audit == before.candidate_selection_audit
        assert after.confidence_semantics == before.confidence_semantics
        assert after.evidence == before.evidence


def test_actual_canonical_builders_coexist_in_owned_worlds_without_id_rewrite(hostile):
    from app.services import canonical_identity as identity
    from app.models.topology import Entity
    from app.repositories.snapshot_repository import save_snapshot
    h = hostile
    repository = identity.canonical_git_repository_identity(provider="github", api_url="https://api.github.com",
        repository_native_id=9001, repository_name="acme/checkout")
    native = [
        identity.canonical_kubernetes_identity(cluster_name="prod", kind="Pod", name="checkout-rs-pod", namespace="default", uid="pod-shared"),
        identity.canonical_aws_identity(account_id="123456789012", region="us-east-1", resource_type="aws_vpc", resource_id="vpc-shared"),
        identity.canonical_azure_identity(subscription_id="sub-shared", resource_type="azure_virtual_machine", resource_id="/subscriptions/sub-shared/resourceGroups/shared/providers/Microsoft.Compute/virtualMachines/checkout"),
        identity.canonical_gcp_identity(project_id="project-shared", resource_type="gcp_compute_instance", resource_id="//compute.googleapis.com/projects/project-shared/zones/us-central1-a/instances/checkout"),
        repository,
        identity.canonical_git_commit_identity(repository_canonical_id=repository.canonical_id, commit_sha="c" * 40),
        identity.canonical_github_workflow_run_identity(api_url="https://api.github.com", run_id=32695735269),
        identity.canonical_container_image_identity(normalized_reference="ghcr.io/acme/checkout:shared", digest=lineage.DIGEST),
    ]
    with h.factory() as session:
        for tenant, label in ((h.a, "A_PRIVATE"), (h.b, "B_PRIVATE")):
            graph = lineage._snapshot(snapshot_id="snapshot:canonical-shared")
            graph.relationships = []  # inventory identity test, no invented edges
            graph.entities = [Entity(id=n.canonical_id, kind=n.entity_kind, entity_type="unknown", name="checkout",
                source_system=n.source_system, external_id=n.source_native_id, identity_version=n.identity_version,
                aliases=n.aliases, observed_at=graph.collected_at, properties={"acceptance_marker": label}) for n in native]
            save_snapshot(session, graph, tenant_id=tenant)
        ga = load_snapshot(session, "snapshot:canonical-shared", tenant_id=h.a)
        gb = load_snapshot(session, "snapshot:canonical-shared", tenant_id=h.b)
        assert [e.id for e in ga.entities] == [e.id for e in gb.entities] == [n.canonical_id for n in native]
        for tenant, graph, marker in ((h.a, ga, "A_PRIVATE"), (h.b, gb, "B_PRIVATE")):
            require_world_value(graph, tenant_id=tenant)
            for n in native:
                resolved = identity.resolve_snapshot_entity_identity(graph, identifier=n.canonical_id)
                assert resolved.resolved_entity_id == n.canonical_id
            assert marker in graph.model_dump_json()
        assert "B_PRIVATE" not in ga.model_dump_json() and "A_PRIVATE" not in gb.model_dump_json()



def machine(corpus, tenant, actor):
    c = corpus.client
    issued = c.post("/api/v1/agents/enrollment-tokens", headers=_bearer(corpus.tokens[actor], tenant),
        json={"label": "same-checkout", "max_uses": 2})
    assert issued.status_code == 201, issued.text
    foreign = corpus.b if tenant == corpus.a else corpus.a
    enrolled = c.post("/api/v1/agents/enroll", headers={"X-Topo-Tenant-ID": foreign}, json={
        "enrollment_token": issued.json()["enrollment_token"], "name": "checkout",
        "cluster_name": "prod", "namespace_scope": ["default"], "version": "1.0",
        "metadata": {"tenant_id": foreign}})
    assert enrolled.status_code == 201, enrolled.text
    return enrolled.json()


def submission(number, *, failure=None):
    value = lifecycle._agent_submission(f"ph3g-shared-{number}",
        collected_at=lifecycle.NOW + timedelta(minutes=number), image=f"example/checkout:v{number}",
        pod_uid=f"pod-{number}", pod_name=f"checkout-rs{number}-pod{number}", replica_uid=f"rs-{number}",
        failure_reason=failure).model_dump(mode="json")
    # Fixture input only: preserve actual collector schema and production builders.
    value = json.loads(json.dumps(value).replace("payments", "default").replace("production", "prod").replace("payment-api", "checkout"))
    value["inventory"]["aws_accounts"] = [{"provider": "aws", "account_id": "123456789012", "region": "global",
        "resource_type": "aws_account", "resource_id": "123456789012", "name": "Account"}]
    value["inventory"]["aws_vpcs"] = [{"provider": "aws", "account_id": "123456789012", "region": "us-east-1",
        "resource_type": "aws_vpc", "resource_id": "vpc-shared", "name": "VPC"}]
    return value


def test_both_real_machine_pipelines_collide_without_crossing_worlds(hostile, monkeypatch):
    h = hostile
    from app.models.webhooks import WebhookEndpointCreate
    from app.services.secret_consumers import create_webhook_endpoint_secure
    from app.services import webhook_delivery
    delivered = []

    monkeypatch.setattr(
        webhook_delivery,
        "deliver_webhook_once",
        lambda destination, **_: delivered.append(destination.destination.url) or 200,
    )
    with h.factory() as session:
        for tenant, actor in ((h.a, "A"), (h.b, "B")):
            create_webhook_endpoint_secure(
                session,
                request=WebhookEndpointCreate(
                    name="checkout", url=f"https://{actor.lower()}.example.test/incidents", max_attempts=1
                ),
                tenant_id=tenant, actor="test:adversarial",
                store=h.client.app.state.secret_store,
            )
    facts = {}
    for tenant, actor, other in ((h.a, "A", h.b), (h.b, "B", h.a)):
        agent = machine(h, tenant, actor)
        headers = _bearer(agent["agent_token"], other)
        assert h.client.get("/api/v1/agent/config", headers=headers).status_code == 200
        heartbeat = {"sensor_id": "sensor:shared", "node_name": "worker", "cluster_name": "prod", "version": "1.0"}
        assert h.client.post("/api/v1/agent/runtime/heartbeat", headers=headers, json=heartbeat).status_code == 200
        batch = {**heartbeat, "batch_id": "batch:shared", "window_start": lifecycle.NOW.isoformat(), "window_end": lifecycle.NOW.isoformat(),
            "processed_event_count": 1, "dropped_event_count": 0, "parser_error_count": 0,
            "dependencies": [{"source": {"pod_uid": "pod-0", "namespace": "default"},
                "destination": {"address": "10.0.0.10", "port": 443}, "protocol": "tcp", "first_seen_at": lifecycle.NOW.isoformat(), "last_seen_at": lifecycle.NOW.isoformat()}],
            "processes": [{"binary": "/app/checkout", "pid": 42, "first_seen_at": lifecycle.NOW.isoformat(), "last_seen_at": lifecycle.NOW.isoformat()}]}
        assert h.client.post("/api/v1/agent/runtime/batches", headers=headers, json=batch).status_code == 201
        before_delivery = len(delivered)
        for n, failure in ((0, None), (1, "ImagePullBackOff")):
            response = h.client.post("/api/v1/agent/snapshots", headers=headers, json=submission(n, failure=failure))
            assert response.status_code == 201, response.text
        assert set(delivered[before_delivery:]) == {f"https://{actor.lower()}.example.test/incidents"}
        with h.factory() as session:
            incidents = tenant_rows(session, models.IncidentRecord, tenant)
            assert len(incidents) == 1
            incident = incidents[0]
            assert incident.affected_entity_id and incident.topology_snapshot_id
            graph = load_snapshot(session, incident.topology_snapshot_id, tenant_id=tenant)
            assert any(e.id == incident.affected_entity_id and e.external_id == "pod-1" for e in graph.entities)
            analysis = latest_causal_analysis(session, incident_id=incident.incident_id, tenant_id=tenant)
            assert analysis and analysis.topology_snapshot_id == incident.topology_snapshot_id
            facts[tenant] = (incident.incident_id, incident.topology_snapshot_id, incident.affected_entity_id)
            for model in (models.RuntimeSensorRecord, models.RuntimeDependencyRecord, models.RuntimeProcessRecord,
                          models.CloudAccountRecord, models.CloudResourceRecord, models.ChangeRecord,
                          models.ChangeEventRecord, models.ChangeEntityLinkRecord, models.SignalRecord):
                assert tenant_rows(session, model, tenant), model.__name__
        for n in (1, 2):
            assert h.client.post("/api/v1/agent/snapshots", headers=headers, json=submission(n, failure="ImagePullBackOff")).status_code == 201
        with h.factory() as session:
            incidents = tenant_rows(session, models.IncidentRecord, tenant)
            assert len(incidents) == 1
            assert (incidents[0].incident_id, incidents[0].topology_snapshot_id, incidents[0].affected_entity_id) == facts[tenant]
        briefing = h.client.get(f"/api/v1/incidents/{facts[tenant][0]}/briefing", headers=_bearer(h.tokens[actor], tenant))
        assert briefing.status_code == 200, briefing.text
    assert facts[h.a][0] == facts[h.b][0]  # same actual failure/incident builder
    assert facts[h.a][2] == facts[h.b][2]  # identical canonical Pod identity
    with h.factory() as session:
        assert tenant_get(session, models.IncidentRecord, facts[h.a][0], tenant_id=h.a) is not tenant_get(session, models.IncidentRecord, facts[h.b][0], tenant_id=h.b)


def test_provider_independent_secrets_delivery_collision_and_disabled_authority(hostile, monkeypatch):
    h = hostile
    sources = {}
    secrets = {"A": b"ph3g-fixture-A-not-a-credential", "B": b"ph3g-fixture-B-not-a-credential"}
    for actor, tenant in (("A", h.a), ("B", h.b)):
        response = h.client.post("/api/v1/change-sources", headers=_bearer(h.tokens[actor], tenant), json={
            "name": "shared-checkout", "source_type": "github", "credential": secrets[actor].decode()})
        assert response.status_code == 201, response.text
        sources[actor] = response.json()["source_id"]
    body = json.dumps({"repository": {"id": 9001, "full_name": "acme/checkout"},
        "head_commit": {"id": "c" * 40, "message": "shared change", "timestamp": lineage.INCIDENT_TIME.isoformat()},
        "ref": "refs/heads/main", "tenant_id": h.b}).encode()

    def send(actor, *, key=None, payload=body, delivery="shared-delivery"):
        return h.client.post(f"/api/v1/change-source-webhooks/{sources[actor]}", content=payload, headers={
            "X-GitHub-Event": "push", "X-GitHub-Delivery": delivery, "X-Topo-Tenant-ID": h.b if actor == "A" else h.a,
            "X-Hub-Signature-256": "sha256=" + hmac.new(secrets[key or actor], payload, hashlib.sha256).hexdigest()})

    for actor in ("A", "B"):
        assert send(actor, key="B" if actor == "A" else "A", payload=b"not-json").status_code == 401
    with h.factory() as session:
        assert session.scalar(select(models.ChangeSourceDeliveryRecord)) is None
        assert session.scalar(select(models.ChangeEventRecord)) is None
    for actor, tenant in (("A", h.a), ("B", h.b)):
        accepted = send(actor)
        assert accepted.status_code == 200, accepted.text
        duplicate = send(actor)
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
        with h.factory() as session:
            assert len(tenant_rows(session, models.ChangeSourceDeliveryRecord, tenant)) == 1
            assert tenant_rows(session, models.ChangeEventRecord, tenant)
    assert h.client.patch(f'/api/v1/change-sources/{sources["B"]}', headers=_bearer(h.tokens["A"], h.a), json={"enabled": False}).status_code == 404
    assert send("B", delivery="still-enabled").status_code == 200
    with h.factory.begin() as session:
        session.get(models.TenantRecord, h.a).status = "disabled"
    assert send("A", payload=b"not-json", delivery="blocked").status_code == 401
    assert h.client.get("/api/v1/change-sources", headers=_bearer(h.tokens["ServiceA"])).status_code == 403
    assert h.client.get("/api/v1/change-sources", headers=_bearer(h.tokens["A"], h.a)).status_code == 403
    assert send("B", delivery="unaffected-B").status_code == 200
    with h.factory() as session:
        assert len(tenant_rows(session, models.ChangeSourceDeliveryRecord, h.a)) == 1
