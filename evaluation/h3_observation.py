from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from evaluation.lineage_contracts import deterministic_json
from evaluation.lineage_provider_truth import (
    contains_unredacted_secret_like_fields,
    container_image_canonical_id,
    github_commit_canonical_id,
    github_repository_canonical_id,
    github_workflow_run_canonical_id,
    sanitize_provider_receipt,
)


H3_OBSERVATION_VERSION = "eval-h3-observation-v1"
GITHUB_API_URL = "https://api.github.com"

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_IMAGE_REPOSITORY = re.compile(
    r"^ghcr\.io/[a-z0-9][a-z0-9._-]*/"
    r"[a-z0-9][a-z0-9._-]*-topo-lineage-eval$"
)

_RECEIPT_FIELDS = {
    "schema_version",
    "provider",
    "repository",
    "repository_id",
    "commit_sha",
    "workflow_name",
    "workflow_ref",
    "workflow_sha",
    "run_id",
    "run_attempt",
    "run_number",
    "event_name",
    "image_registry",
    "image_repository",
    "image_tag",
    "image_digest",
    "immutable_image_ref",
    "built_at",
    "receipt_created_at",
    "source_ref",
    "provenance",
}


class H3Status(str, Enum):
    PROVEN = "PROVEN"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WRONG = "WRONG"
    INCONCLUSIVE = "INCONCLUSIVE"


class H3FirstDivergence(str, Enum):
    ACTIONS_RUN_ENTITY_MISSING = "ACTIONS_RUN_ENTITY_MISSING"
    ACTIONS_RUN_IDENTITY_WRONG = "ACTIONS_RUN_IDENTITY_WRONG"
    IMAGE_ENTITY_MISSING = "IMAGE_ENTITY_MISSING"
    IMAGE_DIGEST_IDENTITY_WRONG = "IMAGE_DIGEST_IDENTITY_WRONG"
    RUN_IMAGE_RELATIONSHIP_MISSING = "RUN_IMAGE_RELATIONSHIP_MISSING"
    RUN_IMAGE_PREDICATE_WRONG = "RUN_IMAGE_PREDICATE_WRONG"
    RUN_IMAGE_DIRECTION_WRONG = "RUN_IMAGE_DIRECTION_WRONG"
    RUN_IMAGE_PROVENANCE_INCOMPLETE = "RUN_IMAGE_PROVENANCE_INCOMPLETE"
    RUN_IMAGE_SOURCE_REFERENCE_INCOMPLETE = (
        "RUN_IMAGE_SOURCE_REFERENCE_INCOMPLETE"
    )
    RUN_IMAGE_TEMPORAL_INCOMPLETE = "RUN_IMAGE_TEMPORAL_INCOMPLETE"
    TOPO_PROVIDER_ACCESS_UNAVAILABLE = "TOPO_PROVIDER_ACCESS_UNAVAILABLE"
    NO_DIVERGENCE = "NO_DIVERGENCE"


def _utc(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must contain an explicit timezone")
    return parsed.astimezone(timezone.utc)


def validate_provider_receipt(receipt: dict[str, Any]) -> None:
    """Apply the accepted receipt's security and semantic invariants.

    The machine schema is still validated independently. These checks keep the
    evaluator safe when it is called directly and make the expected-truth
    boundary explicit.
    """

    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("provider receipt fields do not match the v1 contract")
    if contains_unredacted_secret_like_fields(receipt):
        raise ValueError("provider receipt contains an unredacted secret-like value")
    if receipt["schema_version"] != "eval-lineage-provider-receipt-v1":
        raise ValueError("unsupported provider receipt schema")
    if receipt["provider"] != "github":
        raise ValueError("H3-P1 requires the accepted GitHub provider receipt")
    if not _REPOSITORY.fullmatch(str(receipt["repository"])):
        raise ValueError("invalid repository identity")
    if not str(receipt["repository_id"]).isdigit():
        raise ValueError("invalid repository native ID")
    if not _COMMIT_SHA.fullmatch(str(receipt["commit_sha"])):
        raise ValueError("invalid commit SHA")
    workflow_sha = receipt["workflow_sha"]
    if workflow_sha is not None and not _COMMIT_SHA.fullmatch(str(workflow_sha)):
        raise ValueError("invalid workflow SHA")
    for key in ("run_id", "run_attempt", "run_number"):
        value = receipt[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"invalid {key}")
    if receipt["event_name"] != "workflow_dispatch":
        raise ValueError("unexpected provider event")
    if receipt["image_registry"] != "ghcr.io":
        raise ValueError("unexpected image registry")
    image_repository = str(receipt["image_repository"])
    if not _IMAGE_REPOSITORY.fullmatch(image_repository):
        raise ValueError("image repository is not evaluation-specific")
    expected_tag = f"run-{receipt['run_id']}-{receipt['run_attempt']}"
    if receipt["image_tag"] != expected_tag:
        raise ValueError("image tag does not match run and attempt")
    digest = str(receipt["image_digest"])
    if not _DIGEST.fullmatch(digest):
        raise ValueError("invalid immutable image digest")
    if receipt["immutable_image_ref"] != f"{image_repository}@{digest}":
        raise ValueError("immutable image reference does not match repository and digest")
    if receipt["built_at"] is not None:
        _utc(str(receipt["built_at"]))
    _utc(str(receipt["receipt_created_at"]))
    if receipt["provenance"] != {
        "commit_source": "github_context",
        "digest_source": "build_push_action_output",
        "run_source": "github_context",
    }:
        raise ValueError("provider receipt provenance is not the accepted contract")


def load_provider_receipt(path: str | Path) -> dict[str, Any]:
    receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_provider_receipt(receipt)
    return receipt


def provider_expected_from_receipt(
    receipt: dict[str, Any],
    *,
    github_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build expected H3 truth exclusively from the accepted provider receipt."""

    validate_provider_receipt(receipt)
    repository_id = github_repository_canonical_id(
        api_url=GITHUB_API_URL,
        repository_native_id=receipt["repository_id"],
    )
    commit_id = github_commit_canonical_id(
        repository_canonical_id=repository_id,
        sha=receipt["commit_sha"],
    )
    run_id = github_workflow_run_canonical_id(
        api_url=GITHUB_API_URL,
        run_id=receipt["run_id"],
    )
    image_id = container_image_canonical_id(receipt["image_digest"])
    run_times = deepcopy((github_verification or {}).get("run_timestamps") or {})
    for key in ("created_at", "run_started_at", "updated_at"):
        if run_times.get(key) is not None:
            _utc(str(run_times[key]))
    return {
        "truth_source": "accepted_provider_receipt",
        "provider": receipt["provider"],
        "repository": receipt["repository"],
        "repository_id": str(receipt["repository_id"]),
        "repository_canonical_entity_id": repository_id,
        "commit_sha": receipt["commit_sha"],
        "commit_canonical_entity_id": commit_id,
        "workflow_name": receipt["workflow_name"],
        "workflow_ref": receipt["workflow_ref"],
        "workflow_sha": receipt["workflow_sha"],
        "run_id": str(receipt["run_id"]),
        "run_attempt": receipt["run_attempt"],
        "run_number": receipt["run_number"],
        "run_canonical_entity_id": run_id,
        "event_name": receipt["event_name"],
        "source_ref": receipt["source_ref"],
        "image_registry": receipt["image_registry"],
        "image_repository": receipt["image_repository"],
        "image_tag": receipt["image_tag"],
        "image_digest": receipt["image_digest"],
        "image_canonical_entity_id": image_id,
        "immutable_image_ref": receipt["immutable_image_ref"],
        "built_at": receipt["built_at"],
        "receipt_created_at": receipt["receipt_created_at"],
        "provider_run_timestamps": run_times,
        "provider_provenance": deepcopy(receipt["provenance"]),
    }


def _relationship_type(item: dict[str, Any]) -> str | None:
    value = item.get("relationship_type")
    if isinstance(value, dict):
        return value.get("value")
    return str(value) if value is not None else None


def _reference_values(provenance: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(provenance, dict):
        return []
    return [
        {
            "reference_type": item.get("reference_type"),
            "reference": item.get("reference"),
            "source_system": item.get("source_system"),
        }
        for item in provenance.get("source_references") or []
        if isinstance(item, dict)
    ]


def _entity_observation(entity: dict[str, Any] | None) -> dict[str, Any]:
    if entity is None:
        return {
            "present": False,
            "canonical_entity_id": None,
            "entity_kind": None,
            "provider_native_id": None,
            "aliases": [],
            "source_system": None,
            "properties": {},
            "observed_at": None,
            "temporal": None,
        }
    properties = entity.get("properties") or {}
    allowed = {
        "run_id",
        "run_attempt",
        "run_number",
        "workflow_id",
        "workflow_name",
        "head_sha",
        "event",
        "status",
        "conclusion",
        "registry",
        "repository",
        "tag",
        "digest",
        "immutable",
        "image",
        "requested_references",
        "discovered_via",
    }
    return {
        "present": True,
        "canonical_entity_id": entity.get("id"),
        "entity_kind": entity.get("kind"),
        "provider_native_id": entity.get("external_id"),
        "aliases": list(entity.get("aliases") or []),
        "source_system": entity.get("source_system"),
        "properties": {key: properties[key] for key in sorted(allowed & set(properties))},
        "observed_at": entity.get("observed_at"),
        "temporal": deepcopy(entity.get("temporal")),
    }


def _relationship_observation(item: dict[str, Any] | None) -> dict[str, Any]:
    if item is None:
        return {
            "present": False,
            "relationship_id": None,
            "predicate": None,
            "stored_source_entity_id": None,
            "stored_target_entity_id": None,
            "directed": None,
            "origin": None,
            "source_system": None,
            "source_component": None,
            "source_references": [],
            "linker_version": None,
            "completeness": None,
            "confidence": None,
            "confidence_semantics": None,
            "observed_at": None,
            "temporal": None,
        }
    provenance = item.get("provenance")
    return {
        "present": True,
        "relationship_id": item.get("id"),
        "predicate": _relationship_type(item),
        "stored_source_entity_id": item.get("source_entity_id"),
        "stored_target_entity_id": item.get("target_entity_id"),
        "directed": item.get("directed"),
        "origin": provenance.get("origin") if isinstance(provenance, dict) else None,
        "source_system": item.get("source_system"),
        "source_component": (
            provenance.get("source_component") if isinstance(provenance, dict) else None
        ),
        "source_references": _reference_values(provenance),
        "linker_version": (
            provenance.get("linker_version") if isinstance(provenance, dict) else None
        ),
        "completeness": (
            provenance.get("completeness") if isinstance(provenance, dict) else None
        ),
        "confidence": item.get("confidence"),
        "confidence_semantics": item.get("confidence_semantics"),
        "observed_at": item.get("observed_at"),
        "temporal": deepcopy(item.get("temporal")),
    }


def observe_topo_snapshot(
    snapshot: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Extract a bounded H3 observation without changing the product graph."""

    entities = list(snapshot.get("entities") or [])
    relationships = list(snapshot.get("relationships") or [])
    by_id = {str(item.get("id")): item for item in entities}
    run_id = expected["run_canonical_entity_id"]
    image_id = expected["image_canonical_entity_id"]
    repository_id = expected["repository_canonical_entity_id"]
    commit_id = expected["commit_canonical_entity_id"]

    exact_run = by_id.get(run_id)
    run_candidate = exact_run or next(
        (
            item
            for item in entities
            if item.get("kind") == "GitHubWorkflowRun"
            and str((item.get("properties") or {}).get("head_sha", "")).lower()
            == expected["commit_sha"]
        ),
        None,
    )
    exact_image = by_id.get(image_id)
    image_candidate = exact_image or next(
        (
            item
            for item in entities
            if item.get("kind") == "ContainerImage"
            and (
                (item.get("properties") or {}).get("repository")
                == expected["image_repository"]
                or (item.get("properties") or {}).get("tag")
                == expected["image_tag"]
            )
        ),
        None,
    )

    repo_scope_relationship = next(
        (
            item
            for item in relationships
            if item.get("source_entity_id") == repository_id
            and item.get("target_entity_id") == (run_candidate or {}).get("id")
            and _relationship_type(item) == "contains"
        ),
        None,
    )
    pair_relationships = [
        item
        for item in relationships
        if {
            item.get("source_entity_id"),
            item.get("target_entity_id"),
        }
        == {run_id, image_id}
    ]
    exact_relationship = next(
        (
            item
            for item in pair_relationships
            if item.get("source_entity_id") == run_id
            and item.get("target_entity_id") == image_id
            and _relationship_type(item) == "produces"
        ),
        None,
    )
    relationship_candidate = exact_relationship or next(iter(pair_relationships), None)

    run_observation = _entity_observation(run_candidate)
    run_observation["repository_scope_match"] = repo_scope_relationship is not None
    run_observation["repository_scope_source_references"] = _reference_values(
        (repo_scope_relationship or {}).get("provenance")
    )
    image_observation = _entity_observation(image_candidate)
    image_observation["immutable_digest"] = (
        (image_candidate or {}).get("properties", {}).get("digest")
        or (image_candidate or {}).get("external_id")
    )
    return {
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_collected_at": snapshot.get("collected_at"),
        "context": {
            "repository_entity_present": repository_id in by_id,
            "commit_entity_present": commit_id in by_id,
            "workflow_name_match": (
                (run_candidate or {}).get("properties", {}).get("workflow_name")
                == expected["workflow_name"]
            ),
            "commit_run_trigger_present": any(
                item.get("source_entity_id") == commit_id
                and item.get("target_entity_id") == run_id
                and _relationship_type(item) == "triggers"
                for item in relationships
            ),
        },
        "topo_run_entity": run_observation,
        "topo_image_entity": image_observation,
        "topo_relationship": _relationship_observation(relationship_candidate),
    }


def _run_identity_match(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    props = observed.get("properties") or {}
    return bool(
        observed.get("present")
        and observed.get("canonical_entity_id")
        == expected["run_canonical_entity_id"]
        and observed.get("entity_kind") == "GitHubWorkflowRun"
        and observed.get("source_system") == "github-actions"
        and str(observed.get("provider_native_id")) == expected["run_id"]
        and str(props.get("run_id")) == expected["run_id"]
        and props.get("run_attempt") == expected["run_attempt"]
        and observed.get("repository_scope_match") is True
    )


def _image_identity_match(expected: dict[str, Any], observed: dict[str, Any]) -> bool:
    props = observed.get("properties") or {}
    digest = expected["image_digest"]
    return bool(
        observed.get("present")
        and observed.get("canonical_entity_id")
        == expected["image_canonical_entity_id"]
        and observed.get("entity_kind") == "ContainerImage"
        and str(observed.get("provider_native_id", "")).lower() == digest
        and str(observed.get("immutable_digest", "")).lower() == digest
        and str(props.get("digest", "")).lower() == digest
        and props.get("immutable") is True
    )


def _provenance_present(relationship: dict[str, Any]) -> bool:
    return bool(
        relationship.get("origin")
        and relationship.get("source_component")
        and relationship.get("linker_version")
        and relationship.get("completeness") == "complete"
    )


def _source_references_present(
    expected: dict[str, Any], relationship: dict[str, Any]
) -> bool:
    refs = relationship.get("source_references") or []
    run_ref = any(
        item.get("reference_type") == "github_workflow_run_id"
        and str(item.get("reference")) == expected["run_id"]
        for item in refs
    )
    digest_ref = any(
        item.get("reference_type") == "container_image_digest"
        and str(item.get("reference", "")).lower() == expected["image_digest"]
        for item in refs
    )
    return run_ref and digest_ref


def _temporal_consistent(
    expected: dict[str, Any], relationship: dict[str, Any]
) -> bool:
    temporal = relationship.get("temporal")
    if not isinstance(temporal, dict) or temporal.get("status") != "complete":
        return False
    observed_at = _utc(relationship.get("observed_at"))
    effective_at = _utc(temporal.get("effective_at"))
    if observed_at is None or effective_at is None:
        return False
    run_updated = _utc(
        (expected.get("provider_run_timestamps") or {}).get("updated_at")
    )
    if run_updated is not None and effective_at < run_updated:
        return False
    return effective_at <= observed_at


def evaluate_h3(
    expected: dict[str, Any],
    observation: dict[str, Any],
    *,
    topo_provider_access_available: bool = True,
) -> dict[str, Any]:
    """Classify the first structural divergence in the required order."""

    run = observation["topo_run_entity"]
    image = observation["topo_image_entity"]
    relationship = observation["topo_relationship"]
    run_match = _run_identity_match(expected, run)
    image_match = _image_identity_match(expected, image)
    edge_present = bool(relationship.get("present"))
    predicate_match = relationship.get("predicate") == "produces"
    direction_match = bool(
        relationship.get("directed") is True
        and relationship.get("stored_source_entity_id")
        == expected["run_canonical_entity_id"]
        and relationship.get("stored_target_entity_id")
        == expected["image_canonical_entity_id"]
    )
    provenance_present = _provenance_present(relationship)
    source_reference_present = _source_references_present(expected, relationship)
    temporal_consistent = _temporal_consistent(expected, relationship) if edge_present else False

    status: H3Status
    divergence: H3FirstDivergence
    reason: str
    if not topo_provider_access_available:
        status = H3Status.INCONCLUSIVE
        divergence = H3FirstDivergence.TOPO_PROVIDER_ACCESS_UNAVAILABLE
        reason = "Current Topo provider ingestion could not be exercised safely."
    elif not run.get("present"):
        status = H3Status.MISSING
        divergence = H3FirstDivergence.ACTIONS_RUN_ENTITY_MISSING
        reason = "The exact provider workflow run is absent from the observed Topo graph."
    elif not run_match:
        status = H3Status.WRONG
        divergence = H3FirstDivergence.ACTIONS_RUN_IDENTITY_WRONG
        reason = "The observed Actions run does not match repository, run ID, and attempt."
    elif not image.get("present"):
        status = H3Status.MISSING
        divergence = H3FirstDivergence.IMAGE_ENTITY_MISSING
        reason = "The exact immutable image artifact is absent from the observed Topo graph."
    elif not image_match:
        status = H3Status.WRONG
        divergence = H3FirstDivergence.IMAGE_DIGEST_IDENTITY_WRONG
        reason = "The image is not represented by the exact authoritative digest identity."
    elif not edge_present:
        status = H3Status.MISSING
        divergence = H3FirstDivergence.RUN_IMAGE_RELATIONSHIP_MISSING
        reason = "Both exact entities exist, but Topo has no run-to-image relationship."
    elif not predicate_match:
        status = H3Status.WRONG
        divergence = H3FirstDivergence.RUN_IMAGE_PREDICATE_WRONG
        reason = "The relationship does not use the accepted produces predicate."
    elif not direction_match:
        status = H3Status.WRONG
        divergence = H3FirstDivergence.RUN_IMAGE_DIRECTION_WRONG
        reason = "The relationship is not stored in producer-to-artifact direction."
    elif not provenance_present:
        status = H3Status.PARTIAL
        divergence = H3FirstDivergence.RUN_IMAGE_PROVENANCE_INCOMPLETE
        reason = "The relationship exists, but TC-2 provenance is incomplete."
    elif not source_reference_present:
        status = H3Status.PARTIAL
        divergence = H3FirstDivergence.RUN_IMAGE_SOURCE_REFERENCE_INCOMPLETE
        reason = "The relationship lacks exact run and immutable-digest source references."
    elif not temporal_consistent:
        status = H3Status.PARTIAL
        divergence = H3FirstDivergence.RUN_IMAGE_TEMPORAL_INCOMPLETE
        reason = "The relationship time is absent, incomplete, or inconsistent with provider time."
    else:
        status = H3Status.PROVEN
        divergence = H3FirstDivergence.NO_DIVERGENCE
        reason = "Topo represents the exact provider-proven Actions run to image lineage."

    return {
        "run_identity_match": run_match,
        "image_identity_match": image_match,
        "edge_present": edge_present,
        "predicate_match": predicate_match,
        "direction_match": direction_match,
        "provenance_present": provenance_present,
        "source_reference_present": source_reference_present,
        "temporal_consistent": temporal_consistent,
        "status": status.value,
        "first_divergence": divergence.value,
        "reason": reason,
    }


def build_h3_result(
    *,
    provider_expected: dict[str, Any],
    provider_verification: dict[str, Any],
    ingestion_exercise: dict[str, Any],
    observation: dict[str, Any],
    evaluation: dict[str, Any],
    observed_at: str,
    product_git_commit: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": H3_OBSERVATION_VERSION,
        "observed_at": observed_at,
        "product_git_commit": product_git_commit,
        "provider_expected": deepcopy(provider_expected),
        "provider_verification": deepcopy(provider_verification),
        "ingestion_exercise": deepcopy(ingestion_exercise),
        "topo_observation": deepcopy(observation),
        "evaluation": deepcopy(evaluation),
        "warnings": sorted(set(warnings or [])),
    }
    safe = sanitize_provider_receipt(result)
    if contains_unredacted_secret_like_fields(safe):
        raise ValueError("H3 result contains an unredacted secret-like value")
    return safe


def serialize_h3_result(result: dict[str, Any]) -> str:
    return deterministic_json(result)

