from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from evaluation.contracts import (
    EvaluationStatus,
    ProviderVerification,
    ScenarioManifest,
    TopoObservation,
)


CRITICAL_CLAIMS = {
    "source_change",
    "identity_resolution",
    "entity_linkage",
    "topology_path",
    "relationship_provenance",
}


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _latency(start: str | None, end: str | None) -> float | None:
    left, right = _time(start), _time(end)
    if left is None or right is None:
        return None
    return max(0.0, (right - left).total_seconds())


class IndependentEvaluator:
    """Compare immutable manifest/provider truth with read-only Topo output."""

    def evaluate(
        self,
        manifest: ScenarioManifest,
        provider: ProviderVerification,
        topo: TopoObservation,
        *,
        scenario_started_at: str | None = None,
    ) -> tuple[EvaluationStatus, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        assertions: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        metrics: dict[str, Any] = {}

        if not provider.established:
            failures.append(self._failure("provider_truth", "HARNESS", "Provider-native truth was not established."))
            return EvaluationStatus.HARNESS_ERROR, metrics, assertions, failures

        provider_by_alias = {item.logical_name: item for item in provider.objects}
        required_aliases = {
            manifest.value["causal_intent"]["root_entity"],
            manifest.value["causal_intent"]["affected_entity"],
        }
        missing_provider = sorted(alias for alias in required_aliases if alias not in provider_by_alias)
        if missing_provider:
            failures.append(self._failure("provider_identity", "INCONCLUSIVE", "Missing provider identities: " + ", ".join(missing_provider)))
            return EvaluationStatus.INCONCLUSIVE, metrics, assertions, failures

        snapshot = topo.snapshot or {}
        entities = snapshot.get("entities", [])
        alias_entity_ids: dict[str, list[str]] = {}
        for alias, provider_object in provider_by_alias.items():
            matches = [
                str(entity.get("id"))
                for entity in entities
                if self._entity_matches_provider(entity, provider_object.uid)
            ]
            alias_entity_ids[alias] = sorted(set(matches))

        affected_alias = manifest.value["causal_intent"]["affected_entity"]
        incident = topo.incident or {}
        affected_id = incident.get("affected_entity_id")
        expected_incident_count = int(manifest.value["expected_incident"]["expected_count"])
        observed_incident_count = len(topo.incident_candidates) or (1 if topo.incident else 0)
        metrics["incident_count"] = observed_incident_count
        metrics["incident_count_correct"] = observed_incident_count == expected_incident_count
        metrics["incident_fragmentation_count"] = max(0, observed_incident_count - expected_incident_count)
        self._assert(
            assertions,
            failures,
            "incident_correlation",
            metrics["incident_count_correct"],
            f"Expected {expected_incident_count} incident(s), observed {observed_incident_count}.",
        )
        metrics["identity_resolved"] = bool(affected_id)
        metrics["identity_correct"] = (
            bool(affected_id)
            and affected_id in alias_entity_ids.get(affected_alias, [])
        )
        self._assert(
            assertions,
            failures,
            "affected_identity",
            metrics["identity_correct"],
            f"Affected entity must resolve to provider object '{affected_alias}'.",
        )

        analysis = topo.causal_analysis or {}
        hypotheses = sorted(analysis.get("hypotheses", []), key=lambda item: item.get("rank", 999))
        expected = manifest.value["expected_behavior"]
        top1 = hypotheses[0] if hypotheses else None
        top3 = hypotheses[:3]
        top1_correct = bool(top1 and self._hypothesis_matches(top1, manifest, topo, alias_entity_ids))
        top3_correct = any(self._hypothesis_matches(item, manifest, topo, alias_entity_ids) for item in top3)
        metrics["root_cause_top1_correct"] = top1_correct
        metrics["root_cause_top3_contains_truth"] = top3_correct
        if not expected.get("should_abstain", False):
            self._assert(assertions, failures, "root_cause_top1", top1_correct, "Top-1 must match the predeclared cause.")
            self._assert(assertions, failures, "root_cause_top3", top3_correct, "Top-3 must contain the predeclared cause.")

        noncause_ids = {
            entity_id
            for alias in manifest.value["non_causes"]
            for entity_id in alias_entity_ids.get(alias, [])
        }
        noncause_supported = 0
        unsupported_claims = 0
        for hypothesis in hypotheses:
            ledger = hypothesis.get("evidence_ledger") or {}
            for item in ledger.get("supporting", []):
                claim = item.get("claim_type")
                ids = set(item.get("entity_ids", []))
                if ids & noncause_ids and claim in CRITICAL_CLAIMS:
                    noncause_supported += 1
                    unsupported_claims += 1
        metrics["explicit_non_cause_supported_count"] = noncause_supported
        metrics["unsupported_critical_claim_count"] = unsupported_claims
        self._assert(assertions, failures, "noncause_support", noncause_supported == 0, "Explicit non-causes must not receive supporting critical evidence.")
        self._assert(assertions, failures, "unsupported_claims", unsupported_claims == 0, "No critical claim may conflict with independent truth.")

        path = self._path_metrics(manifest, topo, alias_entity_ids)
        metrics.update(path)
        self._assert(assertions, failures, "required_path", path["causal_path_required_hops_present"], "All required semantic path hops must be present.")
        self._assert(assertions, failures, "forbidden_path", path["causal_path_forbidden_hops_absent"], "Forbidden path hops must be absent.")

        blast = self._blast_metrics(manifest, topo, alias_entity_ids)
        metrics.update(blast)
        self._assert(assertions, failures, "blast_required", blast["blast_radius_false_negative_count"] == 0, "Required affected entities must be present.")
        self._assert(assertions, failures, "blast_unaffected", blast["blast_radius_false_positive_count"] == 0, "Explicitly unaffected entities must be absent.")

        semantics = analysis.get("confidence_semantics") or (top1 or {}).get("confidence_semantics") or {}
        tc5_valid = (
            semantics.get("score_type") == "heuristic_ranking"
            and semantics.get("calibration_status") == "not_calibrated"
            and semantics.get("calibrated_probability") is None
        )
        metrics["tc5_probability_null_invariant"] = tc5_valid
        self._assert(assertions, failures, "tc5_invariant", tc5_valid, "TC-5 must remain heuristic, uncalibrated, and probability-null.")

        evidence_state = semantics.get("evidence_state")
        should_abstain = bool(expected.get("should_abstain"))
        abstained = not hypotheses or evidence_state in {"insufficient_evidence", "incomplete", "contested_with_gaps"}
        metrics["abstention_correct"] = (abstained == should_abstain) if should_abstain else None
        false_certainty = bool(
            (should_abstain or manifest.value["expected_evidence"].get("expected_missing"))
            and hypotheses
            and evidence_state == "supported_under_current_model"
        )
        metrics["false_certainty"] = false_certainty
        if should_abstain:
            self._assert(assertions, failures, "abstention", abstained, "Scenario requires supported abstention.")
        self._assert(assertions, failures, "false_certainty", not false_certainty, "Strong support is not justified by declared missing evidence.")

        event_time = (
            provider.assertions[0].get("causal_action_executed_at")
            or provider.assertions[0].get("failure_observed_at")
            if provider.assertions
            else scenario_started_at
        )
        metrics["time_to_incident"] = _latency(event_time, topo.observed_times.get("incident"))
        metrics["time_to_persisted_rca"] = _latency(event_time, topo.observed_times.get("causal_analysis"))
        metrics["time_to_useful_briefing"] = _latency(event_time, topo.observed_times.get("briefing"))

        status = EvaluationStatus.FAIL if failures else EvaluationStatus.PASS
        return status, metrics, assertions, failures

    @staticmethod
    def _failure(name: str, category: str, detail: str) -> dict[str, Any]:
        return {"assertion": name, "category": category, "detail": detail}

    def _assert(self, assertions: list[dict[str, Any]], failures: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
        assertions.append({"name": name, "passed": bool(passed), "detail": detail})
        if not passed:
            failures.append(self._failure(name, "PRODUCT", detail))

    @staticmethod
    def _entity_matches_provider(entity: dict[str, Any], uid: str) -> bool:
        properties = entity.get("properties") or {}
        return uid in {
            str(entity.get("external_id") or ""),
            str(properties.get("uid") or ""),
            str(properties.get("object_uid") or ""),
        }

    def _hypothesis_matches(
        self,
        hypothesis: dict[str, Any],
        manifest: ScenarioManifest,
        topo: TopoObservation,
        alias_entity_ids: dict[str, list[str]],
    ) -> bool:
        selectors = manifest.value["expected_behavior"]["accepted_top_causes"]
        change_by_id = {item.get("event_id"): item for item in topo.change_events}
        event = change_by_id.get(hypothesis.get("root_event_id"), {})
        text = " ".join(
            str(value or "")
            for value in (
                hypothesis.get("root_title"),
                hypothesis.get("root_source"),
                event.get("title"),
                event.get("kind"),
                event.get("change_type"),
                event.get("summary"),
            )
        ).lower()
        analysis = topo.causal_analysis or {}
        node_by_id = {item.get("node_id"): item for item in analysis.get("nodes", [])}
        entity_ids = {str(hypothesis.get("affected_entity_id") or "")}
        for step in hypothesis.get("chain", []):
            node = node_by_id.get(step.get("node_id"), {})
            if node.get("entity_id"):
                entity_ids.add(str(node["entity_id"]))
        for link in event.get("entity_links", []):
            if link.get("entity_id"):
                entity_ids.add(str(link["entity_id"]))
        for selector in selectors:
            tokens = [str(item).lower() for item in selector.get("title_contains_all", [])]
            alias = selector.get("entity_alias")
            token_match = all(token in text for token in tokens)
            entity_match = not alias or bool(entity_ids & set(alias_entity_ids.get(alias, [])))
            if token_match and entity_match:
                return True
        return False

    def _path_metrics(self, manifest: ScenarioManifest, topo: TopoObservation, alias_entity_ids: dict[str, list[str]]) -> dict[str, Any]:
        snapshot = topo.snapshot or {}
        id_alias = {
            entity_id: alias
            for alias, ids in alias_entity_ids.items()
            for entity_id in ids
        }
        analysis = topo.causal_analysis or {}
        top = analysis.get("top_hypothesis") or {}
        relationship_ids: set[str] = set()
        ledger = top.get("evidence_ledger") or {}
        for item in ledger.get("supporting", []):
            if item.get("claim_type") in {"topology_path", "relationship_provenance", "artifact_provenance"}:
                relationship_ids.update(str(value) for value in item.get("relationship_ids", []))
        actual: set[tuple[str, str, str]] = set()
        for relationship in snapshot.get("relationships", []):
            if relationship_ids and relationship.get("id") not in relationship_ids:
                continue
            left = id_alias.get(relationship.get("source_entity_id"))
            right = id_alias.get(relationship.get("target_entity_id"))
            if left and right:
                predicate = str(relationship.get("relationship_type") or "")
                actual.add((left, right, predicate))
                if not relationship.get("directed", True):
                    actual.add((right, left, predicate))

        def present(hop: dict[str, Any]) -> bool:
            expected = (hop["from"], hop["to"], hop.get("predicate", ""))
            if expected in actual:
                return True
            if not expected[2]:
                return any(left == expected[0] and right == expected[1] for left, right, _ in actual)
            return False

        required = manifest.value["expected_path"]["required_hops"]
        forbidden = manifest.value["expected_path"]["forbidden_hops"]
        required_found = sum(1 for hop in required if present(hop))
        optional = manifest.value["expected_path"]["optional_hops"]
        expected_pairs = len(required) + sum(1 for hop in optional if present(hop))
        relevant_actual = sum(
            1 for hop in required + optional if present(hop)
        )
        precision = (relevant_actual / len(actual)) if actual else (1.0 if not expected_pairs else 0.0)
        return {
            "causal_path_required_hops_present": required_found == len(required),
            "causal_path_required_hop_count": len(required),
            "causal_path_required_hop_found_count": required_found,
            "causal_path_forbidden_hops_absent": not any(present(hop) for hop in forbidden),
            "causal_path_edge_precision": precision,
        }

    @staticmethod
    def _blast_metrics(manifest: ScenarioManifest, topo: TopoObservation, alias_entity_ids: dict[str, list[str]]) -> dict[str, Any]:
        blast_ids = {
            str(item.get("entity_id"))
            for item in (topo.blast_radius or {}).get("affected_entities", [])
        }
        required = manifest.value["expected_blast_radius"]["required_affected"]
        unaffected = manifest.value["expected_blast_radius"]["explicitly_unaffected"]
        found_required = sum(1 for alias in required if blast_ids & set(alias_entity_ids.get(alias, [])))
        found_unaffected = sum(1 for alias in unaffected if blast_ids & set(alias_entity_ids.get(alias, [])))
        tp = found_required
        fp = found_unaffected
        fn = len(required) - found_required
        return {
            "blast_radius_true_positive_count": tp,
            "blast_radius_false_positive_count": fp,
            "blast_radius_false_negative_count": fn,
            "blast_radius_precision": tp / (tp + fp) if tp + fp else None,
            "blast_radius_recall": tp / (tp + fn) if tp + fn else None,
        }


def provider_as_dict(provider: ProviderVerification) -> dict[str, Any]:
    return asdict(provider)
