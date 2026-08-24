from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from evaluation.lineage_contracts import (
    FIRST_BROKEN_BY_HOP,
    LINEAGE_HOP_VERSION,
    LineageHopResult,
    LineageHopSpec,
    LineageHopStatus,
    LineageStrength,
)


HOP_SPECS = (
    LineageHopSpec(
        "H1",
        "github_repository",
        "github_commit",
        "repository contains commit",
        ("contains",),
        "github_repository",
        "github_commit",
        ("github_repository_id", "git_commit_sha"),
        temporal_order_required=False,
    ),
    LineageHopSpec(
        "H2",
        "github_commit",
        "github_actions_run",
        "commit triggers workflow run with exact head SHA",
        ("triggers",),
        "github_commit",
        "github_actions_run",
        ("git_commit_sha", "github_workflow_run_id"),
    ),
    LineageHopSpec(
        "H3",
        "github_actions_run",
        "container_image",
        "workflow run produces immutable container image",
        ("produces",),
        "github_actions_run",
        "container_image",
        ("github_workflow_run_id", "container_image_digest", "mapping_method"),
        immutable_artifact_required=True,
    ),
    LineageHopSpec(
        "H4",
        "container_image",
        "kubernetes_deployment",
        "deployment uses immutable container image",
        ("uses",),
        "kubernetes_deployment",
        "container_image",
        ("container_image_reference", "container_image_digest"),
        immutable_artifact_required=True,
    ),
    LineageHopSpec(
        "H5",
        "kubernetes_deployment",
        "kubernetes_replicaset",
        "deployment owns ReplicaSet through ownerReference UID",
        ("owns",),
        "kubernetes_deployment",
        "kubernetes_replicaset",
        ("kubernetes_owner_reference_uid",),
    ),
    LineageHopSpec(
        "H6",
        "kubernetes_replicaset",
        "kubernetes_pod",
        "ReplicaSet owns/runs Pod through ownerReference UID",
        ("owns", "runs"),
        "kubernetes_replicaset",
        "kubernetes_pod",
        ("kubernetes_owner_reference_uid",),
    ),
    LineageHopSpec(
        "H7",
        "kubernetes_pod",
        "runtime_failure",
        "structured Kubernetes failure signal involves exact Pod",
        ("involved_entity",),
        "kubernetes_pod",
        "runtime_failure",
        ("kubernetes_event_uid", "kubernetes_object_uid"),
        observation_kind="signal",
    ),
)


# Provider timestamps are authoritative for their own events, but adjacent
# systems can expose slightly different publication/creation semantics. A
# bounded tolerance avoids turning harmless timestamp skew into a lineage
# defect while still rejecting material inversions.
TEMPORAL_SKEW_TOLERANCE = timedelta(minutes=5)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _temporal_consistency(provider_hop: dict[str, Any], required: bool) -> bool | None:
    source = _parse_time(provider_hop.get("source_time"))
    target = _parse_time(provider_hop.get("target_time"))
    if source is None or target is None:
        return None if required else True
    return source <= target + TEMPORAL_SKEW_TOLERANCE


def _entity_by_expected_identity(
    entities: list[dict[str, Any]], identity: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, bool | None, str]:
    if not identity:
        return None, None, "Expected provider identity is unavailable."
    canonical = identity.get("canonical_id")
    native = identity.get("native_id")
    if canonical:
        exact = [item for item in entities if item.get("id") == canonical]
        if len(exact) == 1:
            return exact[0], True, "Exact independently-derived canonical ID matched."
        if len(exact) > 1:
            return None, None, "Duplicate canonical entity IDs are ambiguous."
    native_matches = [
        item
        for item in entities
        if native
        and str(item.get("external_id") or "") == str(native)
        and str(item.get("kind") or "").casefold()
        == str(identity.get("kind") or "").casefold()
    ]
    if len(native_matches) == 1:
        return native_matches[0], False, "Native ID exists under a conflicting canonical ID."
    if len(native_matches) > 1:
        return None, None, "Provider-native identity resolves ambiguously."
    return None, False, "No exact canonical or provider-native entity exists."


def _provenance_projection(relationship: dict[str, Any] | None) -> dict[str, Any]:
    if not relationship:
        return {
            "origin": None,
            "source_component": None,
            "source_references": [],
            "linker_version": None,
            "completeness": None,
        }
    provenance = relationship.get("provenance") or {}
    return {
        "origin": provenance.get("origin"),
        "source_component": provenance.get("source_component"),
        "source_references": list(provenance.get("source_references") or []),
        "linker_version": provenance.get("linker_version"),
        "completeness": provenance.get("completeness"),
    }


def _required_references_present(
    provenance: dict[str, Any], required: tuple[str, ...]
) -> bool:
    observed = {
        str(item.get("reference_type") or "")
        for item in provenance.get("source_references", [])
        if isinstance(item, dict)
    }
    return all(item in observed for item in required)


def _evaluate_signal_hop(
    spec: LineageHopSpec,
    provider_hop: dict[str, Any],
    topo: dict[str, Any],
    source_entity: dict[str, Any] | None,
    source_match: bool | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    expected_signal = (provider_hop.get("target_identity") or {}).get("canonical_id")
    accepted_reasons = set(provider_hop.get("accepted_failure_reasons") or [])
    candidates = [
        item
        for item in topo.get("signals", [])
        if item.get("signal_id") == expected_signal
        or (
            source_entity
            and item.get("involved_entity_id") == source_entity.get("id")
            and item.get("reason") in accepted_reasons
        )
    ]
    signal = candidates[0] if len(candidates) == 1 else None
    target_match = bool(
        signal
        and signal.get("signal_id") == expected_signal
        and signal.get("reason") in accepted_reasons
    )
    edge_present = signal is not None
    source_reference_present = bool(
        signal
        and signal.get("involved_object_uid")
        == (provider_hop.get("source_identity") or {}).get("native_id")
    )
    temporal_consistent = _temporal_consistency(provider_hop, True)
    status = LineageHopStatus.PROVEN
    reason = "Structured provider failure and Topo signal reference the exact Pod."
    if source_match is False or (signal and not target_match):
        status = LineageHopStatus.WRONG
        reason = "Topo signal identity conflicts with provider failure truth."
    elif not edge_present:
        status = LineageHopStatus.MISSING
        reason = "Provider proves a structured runtime failure, but Topo has no matching signal."
    elif source_match is None or temporal_consistent is None:
        status = LineageHopStatus.INCONCLUSIVE
        reason = "Runtime failure structure is insufficient for a safe conclusion."
    elif not source_reference_present or temporal_consistent is False:
        status = LineageHopStatus.PARTIAL
        reason = "Runtime failure is represented, but UID or temporal evidence is incomplete."
    observation = {
        "source_canonical_entity_id": source_entity.get("id") if source_entity else None,
        "target_canonical_entity_id": signal.get("signal_id") if signal else None,
        "relationship_id": signal.get("signal_id") if signal else None,
        "predicate": "involved_entity" if signal else None,
        "stored_direction": "pod_to_failure_signal" if signal else None,
        "provenance": {
            "origin": "observed" if signal else None,
            "source_component": "kubernetes_event_collector" if signal else None,
            "source_references": (
                [
                    {"reference_type": "kubernetes_event_uid", "reference": expected_signal},
                    {
                        "reference_type": "kubernetes_object_uid",
                        "reference": signal.get("involved_object_uid"),
                    },
                ]
                if signal
                else []
            ),
            "linker_version": "normalized-signal-v1" if signal else None,
            "completeness": "complete" if source_reference_present else "partial",
        },
        "temporal": signal.get("temporal") if signal else None,
        "signal": signal,
    }
    evaluation = {
        "identity_source_match": source_match,
        "identity_target_match": target_match if signal else False,
        "edge_present": edge_present,
        "predicate_match": edge_present,
        "direction_match": edge_present,
        "provenance_present": edge_present,
        "source_reference_present": source_reference_present,
        "temporal_consistent": temporal_consistent,
        "immutable_artifact_proven": None,
        "lineage_strength": (
            LineageStrength.STRONG.value
            if status == LineageHopStatus.PROVEN
            else LineageStrength.MEDIUM.value
            if status == LineageHopStatus.PARTIAL
            else LineageStrength.UNKNOWN.value
        ),
        "status": status.value,
        "reason": reason,
    }
    return observation, evaluation


def evaluate_lineage_hop(
    spec: LineageHopSpec,
    provider_hop: dict[str, Any],
    topo: dict[str, Any],
) -> LineageHopResult:
    source_identity = provider_hop.get("source_identity")
    target_identity = provider_hop.get("target_identity")
    base_observation = {
        "snapshot_id": topo.get("snapshot_id"),
        "incident_id": topo.get("incident_id"),
        "pinned_snapshot_id": topo.get("pinned_snapshot_id"),
    }
    if provider_hop.get("status") == LineageHopStatus.PROVIDER_PREREQUISITE_BLOCKED.value:
        evaluation = {
            "identity_source_match": None,
            "identity_target_match": None,
            "edge_present": None,
            "predicate_match": None,
            "direction_match": None,
            "provenance_present": None,
            "source_reference_present": None,
            "temporal_consistent": None,
            "immutable_artifact_proven": None,
            "lineage_strength": LineageStrength.UNKNOWN.value,
            "status": LineageHopStatus.PROVIDER_PREREQUISITE_BLOCKED.value,
            "reason": provider_hop.get("reason") or "Provider prerequisite is unavailable.",
        }
        return LineageHopResult(
            LINEAGE_HOP_VERSION,
            spec.hop_id,
            spec.source_logical_alias,
            spec.target_logical_alias,
            source_identity,
            target_identity,
            spec.expected_relationship_semantic,
            provider_hop,
            base_observation,
            evaluation,
        )

    entities = list(topo.get("entities") or [])
    source_entity, source_match, source_reason = _entity_by_expected_identity(
        entities, source_identity
    )
    if spec.observation_kind == "signal":
        observation, evaluation = _evaluate_signal_hop(
            spec, provider_hop, topo, source_entity, source_match
        )
        observation.update(base_observation)
        return LineageHopResult(
            LINEAGE_HOP_VERSION,
            spec.hop_id,
            spec.source_logical_alias,
            spec.target_logical_alias,
            source_identity,
            target_identity,
            spec.expected_relationship_semantic,
            provider_hop,
            observation,
            evaluation,
        )

    target_entity, target_match, target_reason = _entity_by_expected_identity(
        entities, target_identity
    )
    expected_topo_source = (
        source_entity
        if spec.topo_source_logical_alias == spec.source_logical_alias
        else target_entity
    )
    expected_topo_target = (
        target_entity
        if spec.topo_target_logical_alias == spec.target_logical_alias
        else source_entity
    )
    relationships = list(topo.get("relationships") or [])
    endpoint_matches = [
        item
        for item in relationships
        if expected_topo_source
        and expected_topo_target
        and item.get("source_entity_id") == expected_topo_source.get("id")
        and item.get("target_entity_id") == expected_topo_target.get("id")
    ]
    predicate_matches = [
        item
        for item in endpoint_matches
        if item.get("relationship_type") in spec.expected_predicates
    ]
    relationship = predicate_matches[0] if len(predicate_matches) == 1 else None
    reversed_match = any(
        expected_topo_source
        and expected_topo_target
        and item.get("source_entity_id") == expected_topo_target.get("id")
        and item.get("target_entity_id") == expected_topo_source.get("id")
        and item.get("relationship_type") in spec.expected_predicates
        for item in relationships
    )
    provenance = _provenance_projection(relationship)
    edge_present = bool(relationship)
    predicate_match = bool(relationship)
    direction_match = bool(relationship) and not reversed_match
    provenance_present = bool(
        provenance.get("origin")
        and provenance.get("source_component")
        and provenance.get("linker_version")
    )
    source_reference_present = _required_references_present(
        provenance, spec.required_source_reference_types
    )
    temporal_consistent = _temporal_consistency(
        provider_hop, spec.temporal_order_required
    )
    immutable_proven = provider_hop.get("immutable_artifact_proven")
    if spec.immutable_artifact_required:
        actual_image = (
            target_entity
            if (target_identity or {}).get("kind") == "ContainerImage"
            else source_entity
        )
        actual_digest = (
            (actual_image or {}).get("properties", {}).get("digest")
            or (actual_image or {}).get("external_id")
        )
        expected_digest = (
            (target_identity or {}).get("immutable_digest")
            or (source_identity or {}).get("immutable_digest")
        )
        immutable_proven = bool(
            provider_hop.get("immutable_artifact_proven")
            and expected_digest
            and str(actual_digest or "").casefold() == str(expected_digest).casefold()
        )

    status = LineageHopStatus.PROVEN
    reason = "Provider truth and Topo lineage agree on strong identity and provenance."
    if provider_hop.get("identity_conflict") is True:
        status = LineageHopStatus.WRONG
        reason = "Provider-native identity conflicts with the represented lineage hop."
    elif not provider_hop.get("relationship_established"):
        status = LineageHopStatus.INCONCLUSIVE
        reason = "Independent provider truth does not establish the expected hop."
    elif source_match is None or target_match is None:
        status = LineageHopStatus.INCONCLUSIVE
        reason = "Strong source or target identity is ambiguous or unavailable."
    elif source_match is False or target_match is False:
        status = LineageHopStatus.WRONG if source_entity or target_entity else LineageHopStatus.MISSING
        reason = f"Strong Topo identity mismatch. Source: {source_reason} Target: {target_reason}"
    elif reversed_match or (endpoint_matches and not predicate_matches):
        status = LineageHopStatus.WRONG
        reason = "Topo stores the provider-proven hop with a conflicting predicate or direction."
    elif not edge_present:
        status = LineageHopStatus.MISSING
        reason = "Provider truth proves the hop, but Topo has no matching relationship."
    elif spec.immutable_artifact_required and not immutable_proven:
        status = LineageHopStatus.PARTIAL
        reason = "The hop lacks exact immutable artifact identity."
    elif (
        not provenance_present
        or not source_reference_present
        or provenance.get("completeness") != "complete"
        or temporal_consistent is False
    ):
        status = LineageHopStatus.PARTIAL
        reason = "The hop is represented, but provenance, source references, or time is incomplete."

    strength = (
        LineageStrength.STRONG
        if status == LineageHopStatus.PROVEN
        else LineageStrength.MEDIUM
        if status == LineageHopStatus.PARTIAL
        else LineageStrength.UNKNOWN
    )
    observation = {
        **base_observation,
        "source_canonical_entity_id": source_entity.get("id") if source_entity else None,
        "target_canonical_entity_id": target_entity.get("id") if target_entity else None,
        "relationship_id": relationship.get("id") if relationship else None,
        "predicate": relationship.get("relationship_type") if relationship else None,
        "stored_direction": (
            f"{relationship.get('source_entity_id')} -> {relationship.get('target_entity_id')}"
            if relationship
            else None
        ),
        "provenance": provenance,
        "temporal": relationship.get("temporal") if relationship else None,
        "relationship_observed_at": relationship.get("observed_at") if relationship else None,
    }
    evaluation = {
        "identity_source_match": source_match,
        "identity_target_match": target_match,
        "edge_present": edge_present,
        "predicate_match": predicate_match,
        "direction_match": direction_match,
        "provenance_present": provenance_present,
        "source_reference_present": source_reference_present,
        "temporal_consistent": temporal_consistent,
        "immutable_artifact_proven": immutable_proven,
        "lineage_strength": strength.value,
        "status": status.value,
        "reason": reason,
    }
    return LineageHopResult(
        LINEAGE_HOP_VERSION,
        spec.hop_id,
        spec.source_logical_alias,
        spec.target_logical_alias,
        source_identity,
        target_identity,
        spec.expected_relationship_semantic,
        provider_hop,
        observation,
        evaluation,
    )


def evaluate_lineage_chain(
    provider_hops: dict[str, dict[str, Any]],
    topo_observation: dict[str, Any],
) -> dict[str, Any]:
    incident_id = topo_observation.get("incident_id")
    pinned = topo_observation.get("pinned_snapshot_id")
    if incident_id and (
        not pinned or topo_observation.get("snapshot_id") != pinned
    ):
        raise ValueError(
            "Incident lineage must be evaluated from its exact pinned snapshot; latest fallback is forbidden."
        )
    results = [
        evaluate_lineage_hop(spec, provider_hops.get(spec.hop_id, {}), topo_observation)
        for spec in HOP_SPECS
    ]
    first = next(
        (
            item
            for item in results
            if item.evaluation["status"] != LineageHopStatus.PROVEN.value
        ),
        None,
    )
    if first is None:
        first_broken = "NO_BROKEN_HOP"
        first_hop_id = None
    elif first.evaluation["status"] == LineageHopStatus.PROVIDER_PREREQUISITE_BLOCKED.value:
        first_broken = "PROVIDER_PREREQUISITE_BLOCKED"
        first_hop_id = first.hop_id
    else:
        first_broken = FIRST_BROKEN_BY_HOP[first.hop_id]
        first_hop_id = first.hop_id
    statuses = [item.evaluation["status"] for item in results]
    complete = all(item == LineageHopStatus.PROVEN.value for item in statuses)
    immutable_complete = all(
        next(item for item in results if item.hop_id == hop).evaluation["status"]
        == LineageHopStatus.PROVEN.value
        and next(item for item in results if item.hop_id == hop).evaluation[
            "immutable_artifact_proven"
        ]
        is True
        for hop in ("H3", "H4")
    )
    if complete:
        strength = LineageStrength.STRONG.value
    elif any(
        item
        in {
            LineageHopStatus.MISSING.value,
            LineageHopStatus.WRONG.value,
            LineageHopStatus.INCONCLUSIVE.value,
            LineageHopStatus.PROVIDER_PREREQUISITE_BLOCKED.value,
        }
        for item in statuses
    ):
        strength = LineageStrength.UNKNOWN.value
    else:
        strength = LineageStrength.MEDIUM.value
    by_id = {item.hop_id: item for item in results}
    commercial = {
        "repo_commit_proven": by_id["H1"].evaluation["status"] == "PROVEN",
        "commit_ci_proven": by_id["H2"].evaluation["status"] == "PROVEN",
        "ci_image_digest_proven": by_id["H3"].evaluation["status"] == "PROVEN",
        "image_deployment_proven": by_id["H4"].evaluation["status"] == "PROVEN",
        "deployment_runtime_proven": all(
            by_id[hop].evaluation["status"] == "PROVEN" for hop in ("H5", "H6")
        ),
        "runtime_failure_proven": by_id["H7"].evaluation["status"] == "PROVEN",
        "full_source_to_runtime_lineage_proven": complete,
    }
    return {
        "hop_results": [item.as_dict() for item in results],
        "first_broken_hop": first_broken,
        "first_broken_hop_id": first_hop_id,
        "proven_hop_count": statuses.count(LineageHopStatus.PROVEN.value),
        "partial_hop_count": statuses.count(LineageHopStatus.PARTIAL.value),
        "missing_hop_count": statuses.count(LineageHopStatus.MISSING.value),
        "wrong_hop_count": statuses.count(LineageHopStatus.WRONG.value),
        "inconclusive_hop_count": statuses.count(LineageHopStatus.INCONCLUSIVE.value),
        "provider_blocked_hop_count": statuses.count(
            LineageHopStatus.PROVIDER_PREREQUISITE_BLOCKED.value
        ),
        "lineage_complete": complete,
        "immutable_artifact_chain_complete": immutable_complete,
        "source_to_runtime_strength": strength,
        "commercial_proof_status": commercial,
    }
