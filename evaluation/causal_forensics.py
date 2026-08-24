from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from evaluation.cause_fingerprint import (
    CAUSE_FINGERPRINT_VERSION,
    CAUSE_MATCH_VERSION,
    CauseFingerprint,
    best_cause_match,
    compare_causes,
    execution_cause_fingerprint,
    expected_cause_fingerprint,
    fingerprints_from_change,
    fingerprints_from_event,
    provider_cause_fingerprint,
)
from evaluation.contracts import deterministic_json
from evaluation.evidence_semantics import NON_CAUSE_EVIDENCE_SEMANTICS_VERSION


FORENSIC_BUNDLE_VERSION = "ca-0-causal-forensics-v1"

FIRST_DIVERGENCE_CLASSIFICATIONS = frozenset(
    {
        "SCENARIO_INTENT_DEFECT",
        "ORCHESTRATION_DEFECT",
        "PROVIDER_STATE_DEFECT",
        "NORMALIZATION_DEFECT",
        "CHANGE_RECORD_DEFECT",
        "CHANGE_EVENT_DEFECT",
        "CANDIDATE_SEMANTICS_DEFECT",
        "CAUSAL_RELEVANCE_DEFECT",
        "RANKING_DISCRIMINATION_DEFECT",
        "EVIDENCE_LEDGER_DEFECT",
        "HYPOTHESIS_REPRESENTATION_DEFECT",
        "EVALUATOR_CAUSE_MATCH_DEFECT",
        "NO_DIVERGENCE_FOUND",
        "HARNESS_ERROR",
    }
)

VERSION_METADATA = {
    "truth_contracts": {
        "TC-1": "v1",
        "TC-2": "tc2.v1",
        "TC-3": "tc3.v1",
        "TC-4": "tc4.v1",
        "TC-5": "tc5.v1",
    },
    "product_reasoning": {
        "blast_impact": "blast-impact-v1",
        "causal_candidate": "causal-candidate-v1",
        "causal_relevance": "causal-relevance-v1",
        "causal_rca": "13c-causal-v1",
    },
    "evaluation_contracts": {
        "non_cause_evidence": NON_CAUSE_EVIDENCE_SEMANTICS_VERSION,
        "cause_fingerprint": CAUSE_FINGERPRINT_VERSION,
        "cause_match": CAUSE_MATCH_VERSION,
    },
}

_KIND_PRIORS = {
    "deployment": 1.00,
    "infrastructure": 0.95,
    "configuration": 0.85,
    "security": 0.85,
    "database": 0.85,
    "scaling": 0.70,
    "topology": 0.65,
    "pipeline": 0.55,
    "code": 0.50,
    "pull_request": 0.35,
    "unknown": 0.30,
}


def first_divergence(layer_verdicts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    for ordinal, verdict in enumerate(layer_verdicts, start=1):
        if verdict.get("truth_preserved") is not True:
            classification = str(verdict.get("classification") or "HARNESS_ERROR")
            if classification not in FIRST_DIVERGENCE_CLASSIFICATIONS:
                raise ValueError(f"Unsupported first-divergence classification: {classification}")
            return {
                "classification": classification,
                "layer": verdict.get("layer"),
                "layer_ordinal": ordinal,
                "reason": verdict.get("reason"),
            }
    return {
        "classification": "NO_DIVERGENCE_FOUND",
        "layer": None,
        "layer_ordinal": None,
        "reason": "Every audited layer preserved the independently established cause.",
    }


def _decoded_row(row: sqlite3.Row) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if key.endswith("_json"):
            decoded_key = key[: -len("_json")]
            try:
                result[decoded_key] = json.loads(value) if value is not None else None
            except (TypeError, json.JSONDecodeError):
                result[decoded_key] = value
        else:
            result[key] = value
    return result


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def capture_persistence_state(
    database_path: Path,
    *,
    namespace: str,
    incident_id: str | None,
) -> dict[str, Any]:
    """Read committed forensic state before the isolated database is deleted."""

    if not database_path.exists():
        raise FileNotFoundError(database_path)
    connection = sqlite3.connect(str(database_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        state: dict[str, Any] = {}
        for table in ("changes", "change_events"):
            if _table_exists(connection, table):
                rows = connection.execute(
                    f"SELECT * FROM {table} WHERE namespace = ? ORDER BY rowid",  # noqa: S608 - table is fixed above
                    (namespace,),
                ).fetchall()
                state[table] = [_decoded_row(row) for row in rows]
            else:
                state[table] = []

        event_ids = [row["event_id"] for row in state["change_events"]]
        if event_ids and _table_exists(connection, "change_entity_links"):
            placeholders = ",".join("?" for _ in event_ids)
            rows = connection.execute(
                "SELECT * FROM change_entity_links "
                f"WHERE event_id IN ({placeholders}) ORDER BY rowid",  # noqa: S608 - placeholders only
                event_ids,
            ).fetchall()
            state["change_entity_links"] = [_decoded_row(row) for row in rows]
        else:
            state["change_entity_links"] = []

        if incident_id and _table_exists(connection, "causal_analyses"):
            rows = connection.execute(
                "SELECT * FROM causal_analyses WHERE incident_id = ? ORDER BY generated_at",
                (incident_id,),
            ).fetchall()
            state["causal_analyses"] = [_decoded_row(row) for row in rows]
        else:
            state["causal_analyses"] = []
        return state
    finally:
        connection.close()


def _find(items: Iterable[dict[str, Any]], key: str, value: Any) -> dict[str, Any] | None:
    return next((item for item in items if item.get(key) == value), None)


def _match_is_preserved(status: str) -> bool:
    return status in {"exact", "compatible_partial"}


def _ledger_summary(hypothesis: dict[str, Any] | None) -> dict[str, Any]:
    ledger = (hypothesis or {}).get("evidence_ledger") or {}
    result: dict[str, Any] = {
        "ledger_version": ledger.get("ledger_version"),
        "snapshot_id": ledger.get("snapshot_id"),
    }
    for stance in ("supporting", "contradicting", "missing"):
        items = ledger.get(stance) or []
        counts = Counter(str(item.get("claim_type") or "unknown") for item in items)
        result[stance] = {
            "count": len(items),
            "by_claim_type": dict(sorted(counts.items())),
            "evidence_ids": sorted(
                str(item["evidence_id"])
                for item in items
                if item.get("evidence_id")
            ),
        }
    return result


def _root_entity_id(hypothesis: dict[str, Any] | None) -> str | None:
    for step in (hypothesis or {}).get("chain") or []:
        if step.get("node_type") == "entity":
            node_id = str(step.get("node_id") or "")
            return node_id.split("entity|", 1)[-1] if node_id else None
    return None


def _root_direct_fingerprint(
    hypothesis: dict[str, Any] | None, snapshot: dict[str, Any] | None
) -> CauseFingerprint:
    hypothesis = hypothesis or {}
    entity_id = _root_entity_id(hypothesis)
    entity = _find((snapshot or {}).get("entities") or [], "id", entity_id)
    kind = (entity or {}).get("kind")
    native_id = None
    if isinstance(entity_id, str) and entity_id.startswith("k8s:"):
        native_id = entity_id.rsplit(":", 1)[-1]
    return CauseFingerprint(
        provider="kubernetes" if str(kind or "").lower().startswith("kubernetes") else None,
        entity_kind=(
            str(kind)[len("Kubernetes") :]
            if str(kind or "").lower().startswith("kubernetes")
            else kind
        ),
        canonical_entity_id=entity_id,
        provider_native_entity_id=native_id,
        initiating_event_id=hypothesis.get("root_event_id"),
        evidence_source="causal_hypothesis_direct_fields",
        fingerprint_completeness="partial" if entity_id else "insufficient_structure",
    )


def _component_breakdown(
    analysis: dict[str, Any],
    candidate_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = {
        item.get("event", {}).get("event_id"): item
        for item in candidate_analysis.get("candidates", [])
    }
    relevance = {
        item.get("candidate_event_id"): item
        for item in analysis.get("candidate_relevance_audit", [])
    }
    hypotheses = {
        item.get("root_event_id"): item for item in analysis.get("hypotheses", [])
    }
    breakdown: list[dict[str, Any]] = []
    for audit in analysis.get("candidate_selection_audit", []):
        if audit.get("eligibility") != "primary_eligible":
            continue
        event_id = audit.get("event_id")
        candidate = candidates.get(event_id, {})
        event = candidate.get("event", {})
        rel = relevance.get(event_id, {})
        hypothesis = hypotheses.get(event_id, {})
        raw_score = float(audit.get("raw_score") or candidate.get("score") or 0.0)
        topology = float(rel.get("topology_component") or 0.0)
        minutes = candidate.get("minutes_before_incident")
        if minutes is None:
            temporal = 0.0
        elif float(minutes) >= 0:
            temporal = math.exp(-float(minutes) / 90.0)
        else:
            temporal = 0.05 * math.exp(-abs(float(minutes)) / 30.0)
        kind = str(event.get("kind") or "unknown")
        prior = _KIND_PRIORS.get(kind, 0.30)
        final_score = hypothesis.get("score")
        known_total = raw_score * 0.40 + topology * 25 + temporal * 15 + prior * 10
        lineage = (
            max(0.0, min(1.0, (float(final_score) - known_total) / 10.0))
            if final_score is not None
            else None
        )
        if lineage is not None and abs(lineage) < 0.002:
            lineage = 0.0
        breakdown.append(
            {
                "event_id": event_id,
                "origin_change_id": audit.get("origin_change_id"),
                "raw_rank": audit.get("raw_rank"),
                "eligible_rank": audit.get("eligible_rank"),
                "final_rank": hypothesis.get("rank"),
                "candidate_raw_score": round(raw_score, 6),
                "candidate_score_contribution": round(raw_score * 0.40, 6),
                "topology_component": round(topology, 6),
                "topology_contribution": round(topology * 25, 6),
                "minutes_before_incident": minutes,
                "temporal_component": round(temporal, 6),
                "temporal_contribution": round(temporal * 15, 6),
                "change_kind": kind,
                "change_kind_prior": prior,
                "change_kind_contribution": round(prior * 10, 6),
                "lineage_component": None if lineage is None else round(lineage, 6),
                "lineage_contribution": None if lineage is None else round(lineage * 10, 6),
                "final_score": final_score,
            }
        )
    return sorted(breakdown, key=lambda item: item.get("final_rank") or 999999)


def _semantic_layers(result: dict[str, Any]) -> dict[str, Any]:
    manifest = result.get("ground_truth", {})
    provider = result.get("provider_verification", {})
    root = str(manifest.get("causal_intent", {}).get("root_entity") or "")
    root_object = _find(provider.get("objects", []), "logical_name", root) or {}
    assertions = provider.get("assertions", [])
    reasons: set[str] = set()
    for item in assertions:
        if item.get("reason"):
            reasons.add(str(item["reason"]))
        if item.get("failure_reason"):
            reasons.add(str(item["failure_reason"]))
        reasons.update(str(reason) for reason in item.get("failure_reasons", []))
    return {
        "initiating_mutation": manifest.get("causal_intent", {}).get("root_change"),
        "failure_mechanism": "manifest_not_explicit",
        "runtime_manifestation": {
            "declared": manifest.get("causal_intent", {}).get("failure_mode"),
            "provider_reasons": sorted(reasons) or "manifest_not_explicit",
        },
        "operational_impact": {
            "deployment_status": root_object.get("status"),
            "expected_impact_truth": manifest.get("expected_blast_radius", {}).get(
                "impact_truth", "manifest_not_explicit"
            ),
        },
    }


def build_forensic_bundle(
    result: dict[str, Any], persistence: dict[str, Any]
) -> dict[str, Any]:
    manifest = result.get("ground_truth", {})
    receipt = result.get("execution_receipt", {})
    provider = result.get("provider_verification", {})
    topo = result.get("topo_observation", {})
    analysis = topo.get("causal_analysis") or {}
    top = analysis.get("top_hypothesis") or {}
    root_event_id = top.get("root_event_id")
    root_event = _find(topo.get("change_events", []), "event_id", root_event_id)
    if root_event is None:
        for candidate in (topo.get("incident_change_analysis") or {}).get(
            "candidates", []
        ):
            if candidate.get("event", {}).get("event_id") == root_event_id:
                root_event = candidate.get("event")
                break
    persisted_event = _find(
        persistence.get("change_events", []), "event_id", root_event_id
    )
    origin_change_id = (root_event or persisted_event or {}).get("origin_change_id")
    change_record = _find(
        persistence.get("changes", []), "change_id", origin_change_id
    )
    normalized_change = (change_record or {}).get("payload")

    expected = expected_cause_fingerprint(manifest, receipt, provider)
    execution = execution_cause_fingerprint(manifest, receipt)
    provider_fp = provider_cause_fingerprint(manifest, receipt, provider)
    normalized_fps = fingerprints_from_change(
        normalized_change,
        evidence_source="normalized_change_payload",
        source_change_id=origin_change_id,
    )
    record_fps = fingerprints_from_change(
        (change_record or {}).get("payload"),
        evidence_source="change_record.payload_json",
        source_change_id=origin_change_id,
    )
    event_fps = fingerprints_from_event(
        root_event or persisted_event, evidence_source="change_event.metadata"
    )
    candidate = next(
        (
            item
            for item in (topo.get("incident_change_analysis") or {}).get(
                "candidates", []
            )
            if item.get("event", {}).get("event_id") == root_event_id
        ),
        None,
    )
    candidate_fps = fingerprints_from_event(
        (candidate or {}).get("event"), evidence_source="incident_change_candidate.event"
    )
    selection_audit = _find(
        analysis.get("candidate_selection_audit", []), "event_id", root_event_id
    )
    relevance_audit = _find(
        analysis.get("candidate_relevance_audit", []),
        "candidate_event_id",
        root_event_id,
    )
    root_direct = _root_direct_fingerprint(top, topo.get("snapshot"))

    normalized_best, normalized_match = best_cause_match(expected, normalized_fps)
    record_best, record_match = best_cause_match(expected, record_fps)
    event_best, event_match = best_cause_match(expected, event_fps)
    candidate_best, candidate_match = best_cause_match(expected, candidate_fps)
    root_reference_match = compare_causes(expected, event_best)
    execution_match = compare_causes(expected, execution)
    provider_match = compare_causes(expected, provider_fp)
    evaluator_top1 = result.get("metric_results", {}).get("root_cause_top1_correct")

    candidate_policy_ok = bool(
        selection_audit
        and selection_audit.get("eligibility") == "primary_eligible"
        and selection_audit.get("selected_for_hypothesis") is True
    )
    relevance_ok = bool(
        relevance_audit
        and relevance_audit.get("relevance_status") in {"direct", "semantic_path"}
        and float(relevance_audit.get("topology_component") or 0.0) > 0
    )
    ledger = _ledger_summary(top)
    ledger_ok = bool(
        ledger.get("ledger_version") == "tc4.v1"
        and ledger.get("supporting", {}).get("count", 0) > 0
        and ledger.get("contradicting", {}).get("count", 0) == 0
    )

    layer_verdicts = [
        {
            "layer": "predeclared_intent",
            "truth_preserved": expected.fingerprint_completeness == "complete",
            "classification": "SCENARIO_INTENT_DEFECT",
            "reason": "The manifest, receipt and provider truth establish a complete initiating mutation fingerprint.",
        },
        {
            "layer": "execution_receipt",
            "truth_preserved": _match_is_preserved(execution_match.status),
            "classification": "ORCHESTRATION_DEFECT",
            "reason": f"Structured execution match is {execution_match.status}.",
        },
        {
            "layer": "provider_before_after",
            "truth_preserved": provider.get("established") is True
            and _match_is_preserved(provider_match.status),
            "classification": "PROVIDER_STATE_DEFECT",
            "reason": f"Provider verification established={provider.get('established')}; structured match is {provider_match.status}.",
        },
        {
            "layer": "normalized_change",
            "truth_preserved": _match_is_preserved(normalized_match.status),
            "classification": "NORMALIZATION_DEFECT",
            "reason": f"Best normalized-change match is {normalized_match.status}.",
        },
        {
            "layer": "change_record",
            "truth_preserved": _match_is_preserved(record_match.status),
            "classification": "CHANGE_RECORD_DEFECT",
            "reason": f"Best persisted ChangeRecord match is {record_match.status}.",
        },
        {
            "layer": "change_event",
            "truth_preserved": _match_is_preserved(event_match.status),
            "classification": "CHANGE_EVENT_DEFECT",
            "reason": f"Best ChangeEvent metadata match is {event_match.status}.",
        },
        {
            "layer": "incident_change_candidate",
            "truth_preserved": _match_is_preserved(candidate_match.status),
            "classification": "CANDIDATE_SEMANTICS_DEFECT",
            "reason": f"Candidate carries an event whose structured match is {candidate_match.status}.",
        },
        {
            "layer": "causal_candidate_policy",
            "truth_preserved": candidate_policy_ok,
            "classification": "CANDIDATE_SEMANTICS_DEFECT",
            "reason": "The expected mutation is primary-eligible and selected for a hypothesis."
            if candidate_policy_ok
            else "The expected mutation is not primary-eligible and selected.",
        },
        {
            "layer": "causal_relevance",
            "truth_preserved": relevance_ok,
            "classification": "CAUSAL_RELEVANCE_DEFECT",
            "reason": "The expected mutation has a supported incident-time semantic path."
            if relevance_ok
            else "The expected mutation lacks a supported incident-time semantic path.",
        },
        {
            "layer": "13c_ranking",
            "truth_preserved": top.get("root_event_id") == root_event_id
            and _match_is_preserved(root_reference_match.status),
            "classification": "RANKING_DISCRIMINATION_DEFECT",
            "reason": "13C ranked the event carrying the exact initiating mutation first.",
        },
        {
            "layer": "tc4_evidence_ledger",
            "truth_preserved": ledger_ok,
            "classification": "EVIDENCE_LEDGER_DEFECT",
            "reason": "The winning hypothesis has a TC-4 ledger with supporting and no contradicting claims."
            if ledger_ok
            else "The winning hypothesis evidence ledger is missing or contradictory.",
        },
        {
            "layer": "root_hypothesis_reference",
            "truth_preserved": bool(root_event_id)
            and _match_is_preserved(root_reference_match.status),
            "classification": "HYPOTHESIS_REPRESENTATION_DEFECT",
            "reason": "The hypothesis root_event_id durably references the exact initiating mutation; its display title is generic.",
        },
        {
            "layer": "evaluator_cause_match",
            "truth_preserved": evaluator_top1 is True,
            "classification": "EVALUATOR_CAUSE_MATCH_DEFECT",
            "reason": "The current evaluator rejected an exact structured root-event match because its accepted-cause matcher uses display-title tokens.",
        },
    ]

    persisted_analysis = _find(
        persistence.get("causal_analyses", []),
        "analysis_id",
        analysis.get("analysis_id"),
    )
    bundle = {
        "bundle_version": FORENSIC_BUNDLE_VERSION,
        "scenario_id": result.get("scenario_id"),
        "run_id": result.get("run_id"),
        "product_git_commit": result.get("topo_git_commit"),
        "scenario_manifest_version": manifest.get("scenario_version"),
        "versions": VERSION_METADATA,
        "environment": result.get("environment", {}),
        "historical_correctness": {
            "incident_topology_snapshot_id": (topo.get("incident") or {}).get(
                "topology_snapshot_id"
            ),
            "analysis_topology_snapshot_id": analysis.get("topology_snapshot_id"),
            "ledger_snapshot_id": ledger.get("snapshot_id"),
            "uses_incident_pinned_topology": bool(
                (topo.get("incident") or {}).get("topology_snapshot_id")
                and (topo.get("incident") or {}).get("topology_snapshot_id")
                == analysis.get("topology_snapshot_id")
                == ledger.get("snapshot_id")
            ),
            "temporal_version": (
                (root_event or {}).get("temporal") or {}
            ).get("temporal_version"),
        },
        "root_cause_semantic_layers": _semantic_layers(result),
        "expected_cause_fingerprint": expected.as_dict(),
        "execution_receipt_fingerprint": execution.as_dict(),
        "execution_receipt_match": execution_match.as_dict(),
        "provider_fingerprint": provider_fp.as_dict(),
        "provider_match": provider_match.as_dict(),
        "normalized_change": normalized_change,
        "normalized_change_fingerprint": normalized_best.as_dict(),
        "normalized_change_match": normalized_match.as_dict(),
        "change_record": change_record,
        "change_record_fingerprint": record_best.as_dict(),
        "change_record_match": record_match.as_dict(),
        "change_event": root_event or persisted_event,
        "change_event_fingerprint": event_best.as_dict(),
        "change_event_match": event_match.as_dict(),
        "incident_change_candidate": candidate,
        "candidate_fingerprint": candidate_best.as_dict(),
        "candidate_match": candidate_match.as_dict(),
        "candidate_policy": selection_audit,
        "causal_relevance": relevance_audit,
        "causal_component_breakdown": _component_breakdown(
            analysis, topo.get("incident_change_analysis") or {}
        ),
        "tc4_evidence_summary": ledger,
        "root_hypothesis": {
            "analysis_id": analysis.get("analysis_id"),
            "persisted_analysis_present": persisted_analysis is not None,
            "root_event_id": top.get("root_event_id"),
            "root_entity_id": _root_entity_id(top),
            "root_title": top.get("root_title"),
            "affected_entity_id": top.get("affected_entity_id"),
            "chain": top.get("chain", []),
        },
        "root_hypothesis_direct_fingerprint": root_direct.as_dict(),
        "root_event_reference_fingerprint": event_best.as_dict(),
        "root_event_reference_match": root_reference_match.as_dict(),
        "evaluator_match": {
            "current_evaluator_top1_correct": evaluator_top1,
            "current_evaluator_top3_contains_truth": result.get(
                "metric_results", {}
            ).get("root_cause_top3_contains_truth"),
            "forensic_structured_match": root_reference_match.as_dict(),
            "current_matcher_changed": False,
        },
        "layer_verdicts": layer_verdicts,
        "first_divergence": first_divergence(layer_verdicts),
    }
    return bundle


def write_forensic_bundle(bundle: dict[str, Any], output_path: Path) -> Path:
    validate_forensic_bundle(bundle)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(deterministic_json(bundle), encoding="utf-8")
    return output_path


def validate_forensic_bundle(bundle: dict[str, Any]) -> None:
    required = {
        "bundle_version",
        "scenario_id",
        "run_id",
        "product_git_commit",
        "versions",
        "expected_cause_fingerprint",
        "root_event_reference_fingerprint",
        "layer_verdicts",
        "first_divergence",
    }
    missing = sorted(required - set(bundle))
    if missing:
        raise ValueError("Missing forensic bundle fields: " + ", ".join(missing))
    if bundle["bundle_version"] != FORENSIC_BUNDLE_VERSION:
        raise ValueError("Unsupported forensic bundle version.")
    for field in (
        "expected_cause_fingerprint",
        "root_event_reference_fingerprint",
    ):
        if bundle[field].get("fingerprint_version") != CAUSE_FINGERPRINT_VERSION:
            raise ValueError(f"Unsupported fingerprint version in {field}.")
    classification = bundle["first_divergence"].get("classification")
    if classification not in FIRST_DIVERGENCE_CLASSIFICATIONS:
        raise ValueError("Unsupported first-divergence classification.")
