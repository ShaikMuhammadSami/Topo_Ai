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
from evaluation.evidence_semantics import interpret_explicit_non_cause_evidence


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _latency(start: str | None, end: str | None) -> float | None:
    left, right = _time(start), _time(end)
    if left is None or right is None:
        return None
    return max(0.0, (right - left).total_seconds())


def blast_false_positive_path_attribution(
    manifest: ScenarioManifest,
    topo: TopoObservation,
    alias_entity_ids: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Attribute declared false positives using only the incident-pinned snapshot."""
    snapshot = topo.snapshot or {}
    blast = topo.blast_radius or {}
    blast_entities = {
        str(item.get("entity_id")): item
        for item in blast.get("affected_entities", [])
        if item.get("entity_id")
    }
    entities = {
        str(item.get("id")): item
        for item in snapshot.get("entities", [])
        if item.get("id")
    }
    paths_by_target: dict[str, list[list[str]]] = {}
    for value in blast.get("dependency_paths", []):
        path = [str(item) for item in value.get("path", [])]
        if path:
            paths_by_target.setdefault(path[-1], []).append(path)
    relationships = sorted(
        snapshot.get("relationships", []),
        key=lambda item: str(item.get("id") or ""),
    )
    attributed: list[dict[str, Any]] = []
    for alias in sorted(manifest.value["expected_blast_radius"]["explicitly_unaffected"]):
        for entity_id in sorted(set(alias_entity_ids.get(alias, [])) & set(blast_entities)):
            candidate_paths = sorted(
                paths_by_target.get(entity_id, []),
                key=lambda path: (len(path), path),
            )
            path = candidate_paths[0] if candidate_paths else []
            terminal_predicate = str(blast_entities[entity_id].get("relationship") or "")
            hops: list[dict[str, Any]] = []
            for index, (left, right) in enumerate(zip(path, path[1:])):
                candidates = [
                    relationship
                    for relationship in relationships
                    if {
                        str(relationship.get("source_entity_id") or ""),
                        str(relationship.get("target_entity_id") or ""),
                    }
                    == {left, right}
                ]
                if index == len(path) - 2 and terminal_predicate:
                    predicate_matches = [
                        relationship
                        for relationship in candidates
                        if str(relationship.get("relationship_type") or "")
                        == terminal_predicate
                    ]
                    if predicate_matches:
                        candidates = predicate_matches
                selected = candidates[0] if candidates else {}
                source = str(selected.get("source_entity_id") or "")
                target = str(selected.get("target_entity_id") or "")
                direction = (
                    "forward"
                    if source == left and target == right
                    else "reverse"
                    if source == right and target == left
                    else "unavailable"
                )
                hops.append(
                    {
                        "from_entity_id": left,
                        "to_entity_id": right,
                        "relationship_id": selected.get("id"),
                        "predicate": selected.get("relationship_type"),
                        "traversal_direction": direction,
                        "declared_directed": selected.get("directed"),
                        "provenance": selected.get("provenance"),
                        "alternative_relationship_ids": [
                            item.get("id") for item in candidates[1:] if item.get("id")
                        ],
                    }
                )
            entity = entities.get(entity_id, {})
            attributed.append(
                {
                    "false_positive_alias": alias,
                    "false_positive_entity_id": entity_id,
                    "false_positive_entity_kind": entity.get("kind"),
                    "false_positive_entity_name": entity.get("name"),
                    "path_entity_ids": path,
                    "hops": hops,
                    "path_source": (
                        "product_dependency_paths_enriched_from_pinned_snapshot"
                        if path
                        else "unavailable"
                    ),
                }
            )
    return attributed


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
        accepted_affected_aliases = manifest.value["expected_incident"].get(
            "accepted_affected_aliases",
            [affected_alias],
        )
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
            and any(
                affected_id in alias_entity_ids.get(alias, [])
                for alias in accepted_affected_aliases
            )
        )
        self._assert(
            assertions,
            failures,
            "affected_identity",
            metrics["identity_correct"],
            "Affected entity must resolve to one of the provider-native accepted aliases: "
            + ", ".join(accepted_affected_aliases)
            + ".",
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
        accepted_affected_ids = {
            entity_id
            for alias in accepted_affected_aliases
            for entity_id in alias_entity_ids.get(alias, [])
        }
        if affected_id:
            accepted_affected_ids.add(str(affected_id))
        noncause_evidence = interpret_explicit_non_cause_evidence(
            analysis=analysis,
            change_events=topo.change_events,
            non_cause_entity_ids=noncause_ids,
            affected_entity_ids=accepted_affected_ids,
        )
        metrics.update(noncause_evidence.metrics())
        false_causal_support = noncause_evidence.false_causal_support_count
        self._assert(
            assertions,
            failures,
            "noncause_support",
            false_causal_support == 0,
            "Explicit non-causes must not receive supporting evidence that "
            "connects the candidate to the incident effect.",
        )
        self._assert(
            assertions,
            failures,
            "unsupported_claims",
            false_causal_support == 0,
            "No supporting causal-connectivity claim may conflict with "
            "independent non-cause truth.",
        )
        if noncause_evidence.ambiguous_support_count:
            detail = (
                "Supporting evidence for an explicit non-cause could not be "
                "classified from structured references."
            )
            assertions.append(
                {
                    "name": "noncause_evidence_classifiable",
                    "passed": False,
                    "detail": detail,
                }
            )
            failures.append(
                self._failure(
                    "noncause_evidence_classifiable",
                    "INCONCLUSIVE",
                    detail,
                )
            )

        path = self._path_metrics(manifest, topo, alias_entity_ids)
        metrics.update(path)
        self._assert(assertions, failures, "required_path", path["causal_path_required_hops_present"], "All required semantic path hops must be present.")
        self._assert(assertions, failures, "forbidden_path", path["causal_path_forbidden_hops_absent"], "Forbidden path hops must be absent.")

        blast = self._blast_metrics(manifest, topo, alias_entity_ids)
        metrics.update(blast)
        false_positive_paths = blast_false_positive_path_attribution(
            manifest,
            topo,
            alias_entity_ids,
        )
        predicate_counts: dict[str, int] = {}
        path_pattern_counts: dict[str, int] = {}
        for item in false_positive_paths:
            patterns: list[str] = []
            for hop in item["hops"]:
                predicate = str(hop.get("predicate") or "unavailable")
                direction = str(hop.get("traversal_direction") or "unavailable")
                predicate_counts[predicate] = predicate_counts.get(predicate, 0) + 1
                patterns.append(f"{predicate}:{direction}")
            pattern = " > ".join(patterns) if patterns else "path-unavailable"
            path_pattern_counts[pattern] = path_pattern_counts.get(pattern, 0) + 1
        metrics["blast_false_positive_paths"] = false_positive_paths
        metrics["blast_false_positive_count_by_predicate"] = dict(
            sorted(predicate_counts.items())
        )
        metrics["blast_false_positive_count_by_path_pattern"] = dict(
            sorted(path_pattern_counts.items())
        )
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

        if any(item.get("category") == "PRODUCT" for item in failures):
            status = EvaluationStatus.FAIL
        elif failures:
            status = EvaluationStatus.INCONCLUSIVE
        else:
            status = EvaluationStatus.PASS
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
            "provider_affected_count": len(required),
            "provider_explicitly_unaffected_count": len(unaffected),
            "topo_blast_count": len(blast_ids),
            "blast_radius_true_positive_count": tp,
            "blast_radius_false_positive_count": fp,
            "blast_radius_false_negative_count": fn,
            "blast_radius_precision": tp / (tp + fp) if tp + fp else None,
            "blast_radius_recall": tp / (tp + fn) if tp + fn else None,
        }


def provider_as_dict(provider: ProviderVerification) -> dict[str, Any]:
    return asdict(provider)
