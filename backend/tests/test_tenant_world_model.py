"""PH-3F same-ID worlds through real persistence, RCA, and authenticated APIs."""

import json
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.db.models import IncidentRecord, SnapshotRecord, ChangeEventRecord, CausalAnalysisRecord
from app.models.causal_rca import CausalAnalysisRequest
from app.models.incident_outcome import IncidentOutcome
from app.models.ownership import OwnershipMappingCreate
from app.models.signals import NormalizedSignal
from app.models.topology import GraphSnapshot
from app.repositories.snapshot_repository import save_snapshot, load_snapshot
from app.repositories.signal_repository import save_signals
from app.repositories.tenant_scope import tenant_get, tenant_commit, TenantResourceNotFound
from app.repositories.causal_analysis_repository import latest_causal_analysis
from app.repositories.incident_record_repository import load_incident_record
from app.repositories.incident_outcome_repository import save_incident_outcome, list_incident_outcome_records
from app.services.causal_rca import analyze_causal_rca, _snapshot_for_incident
from app.services.incident_change_analysis import analyze_incident_change_events
from app.services.incident_context import build_incident_operational_context
from app.services.response_plan import build_incident_response_plan
from app.services.ownership_resolver import create_ownership_mapping, resolve_ownership_by_ids
from app.services.tenant_world_model import (
    bind_world_value, require_world_value, snapshot_from_owned_record,
)
from app.services import incident_briefing
from app.services.incident_memory import build_current_incident_profile
from app.services.incident_similarity import build_historical_incident_intelligence
from app.services.continuous_lifecycle import ingest_failure_signal_batch, reconcile_pending_incidents_for_checkpoint
from app.services.topology_checkpoint import persist_topology_checkpoint
from app.models.lifecycle_automation import TopologyCheckpointReason
from test_domain_tenant_enforcement import two_tenants, tenant_app, sqlite_tenant_app
from test_tenant_foundation import _bearer
import test_lineage_candidate_admission as lineage
import test_continuous_lifecycle as lifecycle_fixture
from authorization_test_support import tenant_admin_authorization


def seed_world(session, tenant, *, provider=True, source=True, label="A-world", incident_id="incident:same"):
    snapshot = lineage._snapshot()
    snapshot.entities[0].labels["world-test"] = label
    save_snapshot(session, snapshot, tenant_id=tenant)
    signal = NormalizedSignal(
        signal_id="signal:same", fingerprint="signal:same-fingerprint",
        signal_type="kubernetes_event", severity="error", category="health",
        source_system="kubernetes", title=f"{label} runtime failure", summary=label,
        reason="CrashLoopBackOff", first_observed_at=lineage.INCIDENT_TIME,
        last_observed_at=lineage.INCIDENT_TIME, cluster_name="prod", namespace="payments",
        topology_snapshot_id=snapshot.snapshot_id, involved_entity_id="pod:app",
        involved_object_uid="pod-uid", involved_object_kind="Pod", involved_object_name="app-pod",
        attributes={"field_path": "spec.containers{app}"},
    )
    save_signals(session, [signal], tenant_id=tenant)
    now = lineage.INCIDENT_TIME.isoformat()
    session.add(IncidentRecord(
        tenant_id=tenant, incident_id=incident_id, fingerprint="same-failure-family",
        status="investigating", severity="critical", title=label, summary=label,
        cluster_name="prod", namespace="payments", primary_signal_id=signal.signal_id,
        latest_signal_id=signal.signal_id, topology_snapshot_id=snapshot.snapshot_id,
        affected_entity_id="pod:app", affected_object_kind="Pod", affected_object_name="app-pod",
        first_observed_at=now, last_observed_at=now, created_at=now, updated_at=now,
    ))
    tenant_commit(session, tenant_id=tenant)
    event_id = lineage._add_source_change(session, tenant_id=tenant) if source else None
    if provider:
        lineage._add_provider(session, tenant_id=tenant)
    if event_id:
        row = tenant_get(session, ChangeEventRecord, event_id, tenant_id=tenant)
        row.title = f"{label} source revision"
        tenant_commit(session, tenant_id=tenant)
    return snapshot.snapshot_id, event_id


def test_same_ids_real_lineage_rca_briefing_ownership_and_llm_are_isolated(two_tenants, monkeypatch):
    client, factory, tokens, a, b = two_tenants
    snapshots, events, analyses = {}, {}, {}
    with factory() as session:
        for tenant, label in [(a, "A-only-evidence"), (b, "B-private-evidence")]:
            snapshots[tenant], events[tenant] = seed_world(session, tenant, label=label)
            create_ownership_mapping(session, OwnershipMappingCreate(
                entity_id="pod:app", owner_team=label, service_name="payments",
                business_capability=label, criticality="tier_1",
            ), tenant_id=tenant)
            analyses[tenant] = analyze_causal_rca(session, incident_id="incident:same",
                request=CausalAnalysisRequest(), persist=True, tenant_id=tenant)
        assert snapshots[a] == snapshots[b]
        assert events[a] == events[b]
        assert analyses[a].candidate_selection_audit
        assert analyses[b].candidate_selection_audit
        assert analyses[a].hypotheses
        assert analyses[b].hypotheses
        after_foreign_insert = analyze_causal_rca(session, incident_id="incident:same",
            request=CausalAnalysisRequest(), persist=False, tenant_id=a)
        # Adding a complete B world supplies neither supporting nor contradicting
        # evidence to A. Compare real causal structures, not only display strings.
        assert after_foreign_insert.candidate_selection_audit == analyses[a].candidate_selection_audit
        assert after_foreign_insert.hypotheses == analyses[a].hypotheses
        assert after_foreign_insert.evidence == analyses[a].evidence
        assert after_foreign_insert.nodes == analyses[a].nodes
        assert after_foreign_insert.edges == analyses[a].edges
        assert "B-private-evidence" not in analyses[a].model_dump_json()
        assert "A-only-evidence" not in analyses[b].model_dump_json()
        assert latest_causal_analysis(session, incident_id="incident:same", tenant_id=a).analysis_id == analyses[a].analysis_id
        for tenant, label in [(a, "A-only-evidence"), (b, "B-private-evidence")]:
            owner = resolve_ownership_by_ids(session, snapshots[tenant], "pod:app", tenant_id=tenant)
            assert owner.owner_team == label
        captured = []
        monkeypatch.setattr(incident_briefing, "openai_is_configured", lambda: True)
        def narrative(**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(text="Grounded test narrative", model_name="mock-no-network")
        monkeypatch.setattr(incident_briefing, "generate_openai_text", narrative)
        result = incident_briefing.build_incident_briefing(session, incident_id="incident:same", include_ai=True, tenant_id=a)
        assert result.incident.incident_id == "incident:same"
        assert len(captured) == 1
        assert "A-only-evidence" in json.dumps(captured)
        assert "B-private-evidence" not in json.dumps(captured)
        assert "B-private-evidence" not in result.model_dump_json()
        assert "_topo_world_ownership" not in result.model_dump_json()
        assert a not in result.model_dump_json() and b not in result.model_dump_json()
    for tenant, token, label, foreign in [(a, "bootstrap", "A-only-evidence", "B-private-evidence"),
                                         (b, "other_admin", "B-private-evidence", "A-only-evidence")]:
        headers = _bearer(tokens[token], tenant)
        root = "/api/v1/incidents/" + quote("incident:same", safe="")
        response = client.get(root + "/causal-rca/latest", headers=headers)
        assert response.status_code == 200
        assert foreign not in response.text
        response = client.get(root + "/briefing", headers=headers)
        assert response.status_code == 200
        assert label in response.text and foreign not in response.text


@pytest.mark.parametrize("missing", ["provider", "source"])
def test_foreign_matching_lineage_is_missing_not_support_or_contradiction(two_tenants, missing):
    _, factory, _, a, b = two_tenants
    with factory() as session:
        seed_world(session, a, provider=missing != "provider", source=missing != "source")
        before = analyze_incident_change_events(session, incident_id="incident:same", lookback_minutes=180, tenant_id=a)
        assert before.candidates == []
        baseline = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), persist=False, tenant_id=a)
        seed_world(session, b, label="B-private-evidence")
        after = analyze_incident_change_events(session, incident_id="incident:same", lookback_minutes=180, tenant_id=a)
        assert after.candidates == []
        assert after.lineage_admission_audit == before.lineage_admission_audit
        analysis = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=a)
        assert analysis.hypotheses == []
        assert analysis.evidence == baseline.evidence
        assert all(item.event_id is None for item in analysis.evidence)
        assert "B-private-evidence" not in analysis.model_dump_json()


def test_graph_constructor_and_reused_context_reject_foreign_owned_values(two_tenants):
    _, factory, _, a, b = two_tenants
    with factory() as session:
        seed_world(session, a)
        snapshot_id, _ = seed_world(session, b, label="B-private-evidence")
        record = tenant_get(session, SnapshotRecord, snapshot_id, tenant_id=b)
        with pytest.raises(TenantResourceNotFound):
            snapshot_from_owned_record(record, tenant_id=a)
        analysis = analyze_causal_rca(session, incident_id="incident:same", request=CausalAnalysisRequest(), tenant_id=b)
        with pytest.raises(TenantResourceNotFound):
            build_incident_operational_context(session, "incident:same", causal_analysis=analysis, tenant_id=a)
        with pytest.raises(TenantResourceNotFound):
            build_incident_response_plan(session, "incident:same", causal_analysis=analysis, tenant_id=a)
        profile = build_current_incident_profile(session, incident_id="incident:same", tenant_id=b)
        with pytest.raises(TenantResourceNotFound):
            build_historical_incident_intelligence(session, incident_id="incident:same", current_profile=profile, tenant_id=a)
        graph_a = load_snapshot(session, snapshot_id, tenant_id=a)
        graph_b = load_snapshot(session, snapshot_id, tenant_id=b)
        graph_a.entities.append(graph_b.entities[0])
        with pytest.raises(TenantResourceNotFound):
            bind_world_value(graph_a, tenant_id=a)
        with pytest.raises(TenantResourceNotFound):
            save_snapshot(session, graph_a, tenant_id=a)


def test_caller_json_cannot_construct_world_ownership(two_tenants):
    _, _, _, a, b = two_tenants
    graph = lineage._snapshot()
    bind_world_value(graph, tenant_id=b)
    restored = GraphSnapshot.model_validate_json(graph.model_dump_json())
    with pytest.raises(TenantResourceNotFound):
        require_world_value(restored, tenant_id=b)
    forged = graph.model_dump(mode="json")
    forged["_topo_world_ownership"] = {"tenant_id": a}
    with pytest.raises(ValidationError):
        GraphSnapshot.model_validate(forged)
    forged.pop("_topo_world_ownership")
    forged["metadata"]["_topo_world_ownership"] = {"tenant_id": a}
    with pytest.raises(TenantResourceNotFound):
        require_world_value(GraphSnapshot.model_validate(forged), tenant_id=a)


def test_foreign_snapshot_reference_rejected_and_reconciliation_never_uses_it(two_tenants):
    _, factory, _, a, b = two_tenants
    with factory() as session:
        snapshot = lifecycle_fixture._snapshot("snapshot:foreign", observed_at=lifecycle_fixture.NOW)
        persist_topology_checkpoint(session, snapshot=snapshot, reason=TopologyCheckpointReason.PERIODIC_RECONCILE, tenant_id=b, authorization_context=tenant_admin_authorization(session, b))
        pending = ingest_failure_signal_batch(session, signals=[lifecycle_fixture._signal("signal:pending", snapshot_id=None)], tenant_id=a, authorization_context=tenant_admin_authorization(session, a))
        identifier = pending.results[0].incident_id
        incident = tenant_get(session, IncidentRecord, identifier, tenant_id=a)
        assert incident.topology_snapshot_id is None
        assert reconcile_pending_incidents_for_checkpoint(session, snapshot_id=snapshot.snapshot_id, tenant_id=a, authorization_context=tenant_admin_authorization(session, a)) == []
        incident.topology_snapshot_id = snapshot.snapshot_id
        with pytest.raises(TenantResourceNotFound):
            tenant_commit(session, tenant_id=a)
        session.rollback()
        assert tenant_get(session, IncidentRecord, identifier, tenant_id=a).topology_snapshot_id is None


def test_owned_parent_does_not_authorize_an_unowned_inserted_child(two_tenants):
    _, _, _, a, _ = two_tenants
    graph = bind_world_value(lineage._snapshot(), tenant_id=a)
    child_type = type(graph.entities[0])
    child = child_type.model_validate_json(graph.entities[0].model_dump_json())
    graph.entities.append(child)
    with pytest.raises(TenantResourceNotFound):
        require_world_value(graph, tenant_id=a)


def test_same_failure_family_creates_distinct_automatic_incidents_and_fixed_pins(two_tenants):
    _, factory, _, a, b = two_tenants
    with factory() as session:
        identifiers = []
        for tenant in (a, b):
            graph = lifecycle_fixture._snapshot("snapshot:same-boundary")
            authorization = tenant_admin_authorization(session, tenant)
            persist_topology_checkpoint(session, snapshot=graph, reason=TopologyCheckpointReason.INCIDENT_BOUNDARY, tenant_id=tenant, authorization_context=authorization)
            result = ingest_failure_signal_batch(session, signals=[lifecycle_fixture._signal("signal:same-auto", snapshot_id=graph.snapshot_id)], tenant_id=tenant, authorization_context=authorization)
            identifier = result.results[0].incident_id
            identifiers.append(identifier)
            assert identifier
            assert latest_causal_analysis(session, incident_id=identifier, tenant_id=tenant) is not None
            again = ingest_failure_signal_batch(session, signals=[lifecycle_fixture._signal("signal:same-auto", snapshot_id=graph.snapshot_id)], tenant_id=tenant, authorization_context=authorization)
            assert again.results[0].incident_id == identifier
            incident = tenant_get(session, IncidentRecord, identifier, tenant_id=tenant)
            assert incident.topology_snapshot_id == graph.snapshot_id
            assert incident.affected_entity_id == "entity:pod:pod-uid-1"
        assert identifiers[0] == identifiers[1]
        assert tenant_get(session, IncidentRecord, identifiers[0], tenant_id=a) is not tenant_get(session, IncidentRecord, identifiers[1], tenant_id=b)


def test_outcomes_with_equal_ids_stay_local_and_foreign_history_is_not_reused(two_tenants):
    _, factory, _, a, b = two_tenants
    with factory() as session:
        for tenant in (a, b):
            seed_world(session, tenant, label="A-outcome" if tenant == a else "B-private-outcome")
            outcome = IncidentOutcome(
                outcome_id="outcome:same", incident_id="incident:same", status="resolved",
                historical_topology_snapshot_id=lineage._snapshot().snapshot_id,
                started_at=lineage.INCIDENT_TIME, resolved_at=lineage.INCIDENT_TIME + timedelta(minutes=10),
                rca_verdict="confirmed", rca_confidence=0.9,
                resolution_summary="A-outcome" if tenant == a else "B-private-outcome",
            )
            save_incident_outcome(session, outcome=outcome, source={}, tenant_id=tenant)
        assert len(list_incident_outcome_records(session, tenant_id=a)) == 1
        assert "B-private-outcome" not in list_incident_outcome_records(session, tenant_id=a)[0].payload_json
        history = build_historical_incident_intelligence(session, incident_id="incident:same", min_similarity=0, tenant_id=a)
        assert history.matches == []
        assert "B-private-outcome" not in history.model_dump_json()
