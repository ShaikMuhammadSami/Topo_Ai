from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Iterable

from evaluation.lineage_contracts import deterministic_json
from evaluation.runtime_causal_observer import (
    provider_index_digest,
    validate_runtime_causal_receipt,
)
from evaluation.source_mutation_truth import validate_source_mutation_contract


SOURCE_CAUSE_MATCH_VERSION = "eval-source-cause-match-v1"
TOPO_OBSERVATION_VERSION = "eval-lineage-1c-topo-observation-v1"


class CausalVerdict(str, Enum):
    PROVEN = "PROVEN"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WRONG = "WRONG"
    INCONCLUSIVE = "INCONCLUSIVE"


class RootCauseLevel(str, Enum):
    INITIATING_MUTATION = "INITIATING_MUTATION"
    FAILURE_MECHANISM = "FAILURE_MECHANISM"
    RUNTIME_MANIFESTATION = "RUNTIME_MANIFESTATION"
    OPERATIONAL_IMPACT = "OPERATIONAL_IMPACT"
    UNRELATED = "UNRELATED"
    ABSTAINED = "ABSTAINED"


class FirstDivergence(str, Enum):
    SOURCE_CHANGE_NOT_INGESTED = "SOURCE_CHANGE_NOT_INGESTED"
    SOURCE_CHANGE_IDENTITY_WRONG = "SOURCE_CHANGE_IDENTITY_WRONG"
    COMMIT_ENTITY_MISSING = "COMMIT_ENTITY_MISSING"
    COMMIT_ACTIONS_LINK_MISSING = "COMMIT_ACTIONS_LINK_MISSING"
    ACTIONS_RUN_ENTITY_MISSING = "ACTIONS_RUN_ENTITY_MISSING"
    RUN_IMAGE_LINK_MISSING = "RUN_IMAGE_LINK_MISSING"
    IMAGE_ENTITY_MISSING = "IMAGE_ENTITY_MISSING"
    IMAGE_DEPLOYMENT_LINK_MISSING = "IMAGE_DEPLOYMENT_LINK_MISSING"
    DEPLOYMENT_RS_LINK_MISSING = "DEPLOYMENT_RS_LINK_MISSING"
    RS_POD_LINK_MISSING = "RS_POD_LINK_MISSING"
    POD_FAILURE_EVIDENCE_MISSING = "POD_FAILURE_EVIDENCE_MISSING"
    INCIDENT_NOT_CREATED = "INCIDENT_NOT_CREATED"
    INCIDENT_AFFECTED_ENTITY_WRONG = "INCIDENT_AFFECTED_ENTITY_WRONG"
    INCIDENT_PIN_INVALID = "INCIDENT_PIN_INVALID"
    CAUSAL_CANDIDATE_MISSING = "CAUSAL_CANDIDATE_MISSING"
    CAUSAL_RELEVANCE_PATH_MISSING = "CAUSAL_RELEVANCE_PATH_MISSING"
    SUPPORTED_HYPOTHESIS_MISSING = "SUPPORTED_HYPOTHESIS_MISSING"
    ROOT_CAUSE_LOWER_SEMANTIC_LEVEL = "ROOT_CAUSE_LOWER_SEMANTIC_LEVEL"
    ROOT_CAUSE_WRONG_MUTATION = "ROOT_CAUSE_WRONG_MUTATION"
    EVIDENCE_CHAIN_INCOMPLETE = "EVIDENCE_CHAIN_INCOMPLETE"
    NO_DIVERGENCE = "NO_DIVERGENCE"


_CAUSE_IDENTITY_FIELDS = (
    "repository",
    "parent_commit_sha",
    "commit_sha",
    "file_path",
    "before_hash",
    "after_hash",
    "before_semantic_value",
    "after_semantic_value",
)


def expected_initiating_mutation(source_truth: dict[str, Any]) -> dict[str, Any]:
    validate_source_mutation_contract(source_truth)
    if source_truth["status"] != "complete":
        raise ValueError("Complete provider-bound source truth is required.")
    return {field: source_truth[field] for field in _CAUSE_IDENTITY_FIELDS}


def blank_topo_observation(*, run_id: str | int) -> dict[str, Any]:
    return {
        "schema_version": TOPO_OBSERVATION_VERSION,
        "run_id": int(run_id),
        "source_change": {
            "present": False,
            "repository": None,
            "parent_commit_sha": None,
            "commit_sha": None,
            "file_path": None,
            "before_hash": None,
            "after_hash": None,
            "before_semantic_value": None,
            "after_semantic_value": None,
        },
        "entities": {
            name: {"present": False, "entity_id": None, "provider_identity": None}
            for name in (
                "repository",
                "commit",
                "actions_run",
                "image",
                "deployment",
                "replicaset",
                "pod",
            )
        },
        "relationships": {
            name: {"present": False, "relationship_id": None, "predicate": None}
            for name in (
                "commit_actions",
                "actions_image",
                "image_deployment",
                "deployment_replicaset",
                "replicaset_pod",
                "pod_failure",
            )
        },
        "runtime": {
            "pod_failure_present": False,
            "exit_code": None,
            "restart_count": None,
            "backoff_reason": None,
            "desired_replicas": None,
            "ready_replicas": None,
            "available_replicas": None,
        },
        "incident": {
            "present": False,
            "incident_id": None,
            "first_failure_signal_id": None,
            "boundary_time": None,
            "pinned_topology_id": None,
            "snapshot_effective_time": None,
            "pin_temporally_valid": None,
            "affected_entity_id": None,
            "affected_entity_kind": None,
            "affected_entity_matches_runtime": False,
            "analysis_state": None,
        },
        "causal": {
            "candidate_present": False,
            "relevance_path_present": False,
            "top1": None,
            "top3": [],
            "evidence_ledger": {
                "supporting": [],
                "contradicting": [],
                "unknown": [],
                "missing": [],
            },
        },
        "topo_output_used_to_construct_expected_truth": False,
    }


def cause_observation(
    *,
    semantic_level: RootCauseLevel | str,
    supported: bool,
    root_event_id: str | None = None,
    confidence: float | None = None,
    repository: str | None = None,
    parent_commit_sha: str | None = None,
    commit_sha: str | None = None,
    file_path: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    before_semantic_value: str | None = None,
    after_semantic_value: str | None = None,
    run_id: int | None = None,
    image_digest: str | None = None,
    evidence_chain_complete: bool = False,
) -> dict[str, Any]:
    level = RootCauseLevel(semantic_level).value
    return {
        "semantic_level": level,
        "supported": supported,
        "root_event_id": root_event_id,
        "confidence": confidence,
        "repository": repository,
        "parent_commit_sha": parent_commit_sha,
        "commit_sha": commit_sha,
        "file_path": file_path,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "before_semantic_value": before_semantic_value,
        "after_semantic_value": after_semantic_value,
        "run_id": run_id,
        "image_digest": image_digest,
        "evidence_chain_complete": evidence_chain_complete,
    }


def validate_topo_observation(value: dict[str, Any]) -> None:
    template = blank_topo_observation(run_id=value.get("run_id") or 1)
    if set(value) != set(template):
        raise ValueError("Topo observation fields do not match LINEAGE-1C v1.")
    if value.get("schema_version") != TOPO_OBSERVATION_VERSION:
        raise ValueError("Unsupported Topo observation version.")
    if not isinstance(value.get("run_id"), int) or value["run_id"] < 1:
        raise ValueError("Topo observation run ID is invalid.")
    if value.get("topo_output_used_to_construct_expected_truth") is not False:
        raise ValueError("Topo output cannot construct independent expected truth.")
    for section in (
        "source_change",
        "entities",
        "relationships",
        "runtime",
        "incident",
        "causal",
    ):
        if not isinstance(value.get(section), dict):
            raise ValueError(f"Topo observation {section} must be an object.")
    if set(value["source_change"]) != set(template["source_change"]):
        raise ValueError("Topo source-change observation fields do not match v1.")
    if set(value["entities"]) != set(template["entities"]):
        raise ValueError("Topo entity observation fields do not match v1.")
    if set(value["relationships"]) != set(template["relationships"]):
        raise ValueError("Topo relationship observation fields do not match v1.")
    for cause in [value["causal"].get("top1"), *value["causal"].get("top3", [])]:
        if cause is not None:
            _validate_cause(cause)
    audit_evidence_ledger(value["causal"].get("evidence_ledger") or {})


def _validate_cause(value: dict[str, Any]) -> None:
    expected_keys = set(cause_observation(
        semantic_level=RootCauseLevel.ABSTAINED, supported=False
    ))
    if set(value) != expected_keys:
        raise ValueError("Source-cause observation fields do not match v1.")
    RootCauseLevel(str(value.get("semantic_level")))
    if not isinstance(value.get("supported"), bool):
        raise ValueError("Source-cause support must be explicit.")
    confidence = value.get("confidence")
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= float(confidence) <= 1
    ):
        raise ValueError("Source-cause confidence is invalid.")


def _source_match(
    expected: dict[str, Any], actual: dict[str, Any] | None
) -> dict[str, Any]:
    actual = actual or {}
    comparisons = {
        field: (
            "matched"
            if actual.get(field) == expected[field]
            else "missing"
            if actual.get(field) is None
            else "mismatched"
        )
        for field in _CAUSE_IDENTITY_FIELDS
    }
    return {
        "exact": all(value == "matched" for value in comparisons.values()),
        "comparisons": comparisons,
        "matched_field_count": sum(
            value == "matched" for value in comparisons.values()
        ),
        "required_field_count": len(comparisons),
    }


def _commit_image_partial(
    actual: dict[str, Any] | None,
    *,
    expected: dict[str, Any],
    expected_image_digest: str,
) -> bool:
    actual = actual or {}
    return (
        actual.get("commit_sha") == expected["commit_sha"]
        and actual.get("image_digest") == expected_image_digest
        and all(
            actual.get(field) in {None, expected[field]}
            for field in _CAUSE_IDENTITY_FIELDS
        )
    )


def audit_evidence_ledger(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"supporting", "contradicting", "unknown", "missing"}
    if set(value) != expected or any(
        not isinstance(value.get(field), list) for field in expected
    ):
        raise ValueError("TC4 evidence observation fields do not match v1.")
    missing_without_basis = [
        item
        for item in value["missing"]
        if not isinstance(item, dict) or not item.get("expectation_basis")
    ]
    if missing_without_basis:
        raise ValueError("Missing evidence requires an expectation basis.")
    explicit_unknown = list(value["unknown"])
    contradictions: list[dict[str, Any]] = []
    for item in value["contradicting"]:
        if isinstance(item, dict) and item.get("truth_status") == "unknown":
            explicit_unknown.append(item)
        else:
            contradictions.append(item)
    return {
        "supporting_count": len(value["supporting"]),
        "contradicting_count": len(contradictions),
        "unknown_count": len(explicit_unknown),
        "missing_count": len(value["missing"]),
        "supporting_evidence_ids": _evidence_ids(value["supporting"]),
        "contradicting_evidence_ids": _evidence_ids(contradictions),
        "unknown_evidence_ids": _evidence_ids(explicit_unknown),
        "missing_evidence_ids": _evidence_ids(value["missing"]),
        "missing_expectation_bases": sorted(
            {
                str(item["expectation_basis"])
                for item in value["missing"]
                if isinstance(item, dict) and item.get("expectation_basis")
            }
        ),
    }


def _evidence_ids(values: Iterable[Any]) -> list[str]:
    return sorted(
        {
            str(item.get("evidence_id"))
            for item in values
            if isinstance(item, dict) and item.get("evidence_id")
        }
    )


def _present(value: dict[str, Any], section: str, name: str) -> bool:
    return bool(value[section][name].get("present"))


def _first_divergence(
    expected: dict[str, Any], observation: dict[str, Any], top1_match: dict[str, Any]
) -> FirstDivergence:
    source = observation["source_change"]
    if not source.get("present"):
        return FirstDivergence.SOURCE_CHANGE_NOT_INGESTED
    if not _source_match(expected, source)["exact"]:
        return FirstDivergence.SOURCE_CHANGE_IDENTITY_WRONG
    if not _present(observation, "entities", "commit"):
        return FirstDivergence.COMMIT_ENTITY_MISSING
    if not _present(observation, "relationships", "commit_actions"):
        return FirstDivergence.COMMIT_ACTIONS_LINK_MISSING
    if not _present(observation, "entities", "actions_run"):
        return FirstDivergence.ACTIONS_RUN_ENTITY_MISSING
    if not _present(observation, "relationships", "actions_image"):
        return FirstDivergence.RUN_IMAGE_LINK_MISSING
    if not _present(observation, "entities", "image"):
        return FirstDivergence.IMAGE_ENTITY_MISSING
    if not _present(observation, "relationships", "image_deployment"):
        return FirstDivergence.IMAGE_DEPLOYMENT_LINK_MISSING
    if not _present(observation, "relationships", "deployment_replicaset"):
        return FirstDivergence.DEPLOYMENT_RS_LINK_MISSING
    if not _present(observation, "relationships", "replicaset_pod"):
        return FirstDivergence.RS_POD_LINK_MISSING
    if not observation["runtime"].get("pod_failure_present") or not _present(
        observation, "relationships", "pod_failure"
    ):
        return FirstDivergence.POD_FAILURE_EVIDENCE_MISSING
    incident = observation["incident"]
    if not incident.get("present"):
        return FirstDivergence.INCIDENT_NOT_CREATED
    if not incident.get("affected_entity_matches_runtime"):
        return FirstDivergence.INCIDENT_AFFECTED_ENTITY_WRONG
    if incident.get("pin_temporally_valid") is not True:
        return FirstDivergence.INCIDENT_PIN_INVALID
    if not observation["causal"].get("candidate_present"):
        return FirstDivergence.CAUSAL_CANDIDATE_MISSING
    if not observation["causal"].get("relevance_path_present"):
        return FirstDivergence.CAUSAL_RELEVANCE_PATH_MISSING
    top1 = observation["causal"].get("top1")
    if not top1 or not top1.get("supported"):
        return FirstDivergence.SUPPORTED_HYPOTHESIS_MISSING
    level = RootCauseLevel(top1["semantic_level"])
    if level in {
        RootCauseLevel.FAILURE_MECHANISM,
        RootCauseLevel.RUNTIME_MANIFESTATION,
        RootCauseLevel.OPERATIONAL_IMPACT,
    }:
        return FirstDivergence.ROOT_CAUSE_LOWER_SEMANTIC_LEVEL
    if level in {RootCauseLevel.UNRELATED, RootCauseLevel.ABSTAINED}:
        return FirstDivergence.ROOT_CAUSE_WRONG_MUTATION
    if not top1_match["exact"]:
        return FirstDivergence.ROOT_CAUSE_WRONG_MUTATION
    if not top1.get("evidence_chain_complete"):
        return FirstDivergence.EVIDENCE_CHAIN_INCOMPLETE
    return FirstDivergence.NO_DIVERGENCE


def _lineage_complete(value: dict[str, Any]) -> bool:
    return all(
        _present(value, "relationships", name)
        for name in (
            "commit_actions",
            "actions_image",
            "image_deployment",
            "deployment_replicaset",
            "replicaset_pod",
            "pod_failure",
        )
    )


def _verdict(
    *,
    observation: dict[str, Any],
    top1_match: dict[str, Any],
    top3_matches: list[dict[str, Any]],
    commit_image_partial: bool,
    first_divergence: FirstDivergence,
) -> CausalVerdict:
    top1 = observation["causal"].get("top1")
    if first_divergence in {
        FirstDivergence.SOURCE_CHANGE_NOT_INGESTED,
        FirstDivergence.COMMIT_ENTITY_MISSING,
        FirstDivergence.COMMIT_ACTIONS_LINK_MISSING,
        FirstDivergence.ACTIONS_RUN_ENTITY_MISSING,
        FirstDivergence.RUN_IMAGE_LINK_MISSING,
        FirstDivergence.IMAGE_ENTITY_MISSING,
        FirstDivergence.IMAGE_DEPLOYMENT_LINK_MISSING,
        FirstDivergence.DEPLOYMENT_RS_LINK_MISSING,
        FirstDivergence.RS_POD_LINK_MISSING,
        FirstDivergence.POD_FAILURE_EVIDENCE_MISSING,
        FirstDivergence.INCIDENT_NOT_CREATED,
        FirstDivergence.INCIDENT_AFFECTED_ENTITY_WRONG,
        FirstDivergence.INCIDENT_PIN_INVALID,
        FirstDivergence.CAUSAL_CANDIDATE_MISSING,
        FirstDivergence.CAUSAL_RELEVANCE_PATH_MISSING,
        FirstDivergence.SUPPORTED_HYPOTHESIS_MISSING,
    }:
        return CausalVerdict.MISSING
    if not top1:
        return CausalVerdict.MISSING
    level = RootCauseLevel(top1["semantic_level"])
    if any(item["exact"] for item in top3_matches[1:]):
        return CausalVerdict.PARTIAL
    if level == RootCauseLevel.UNRELATED:
        return CausalVerdict.WRONG
    if level == RootCauseLevel.ABSTAINED:
        return CausalVerdict.MISSING
    if level in {
        RootCauseLevel.FAILURE_MECHANISM,
        RootCauseLevel.RUNTIME_MANIFESTATION,
        RootCauseLevel.OPERATIONAL_IMPACT,
    }:
        return CausalVerdict.PARTIAL
    if top1_match["exact"]:
        if top1.get("evidence_chain_complete") and _lineage_complete(observation):
            return CausalVerdict.PROVEN
        return CausalVerdict.PARTIAL
    if commit_image_partial:
        return CausalVerdict.PARTIAL
    if any(value == "mismatched" for value in top1_match["comparisons"].values()):
        return CausalVerdict.WRONG
    return CausalVerdict.MISSING


def _matrix(
    *,
    expected: dict[str, Any],
    runtime_receipt: dict[str, Any],
    observation: dict[str, Any],
    top1_match: dict[str, Any],
    evidence_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    source = observation["source_change"]
    runtime = runtime_receipt
    actual_runtime = observation["runtime"]
    incident = observation["incident"]
    rows = [
        ("Repository", expected["repository"], source.get("repository")),
        ("Parent commit", expected["parent_commit_sha"], source.get("parent_commit_sha")),
        ("Failure commit", expected["commit_sha"], source.get("commit_sha")),
        ("Changed file", expected["file_path"], source.get("file_path")),
        ("Before semantic value", expected["before_semantic_value"], source.get("before_semantic_value")),
        ("After semantic value", expected["after_semantic_value"], source.get("after_semantic_value")),
        ("Commit -> Actions", True, _present(observation, "relationships", "commit_actions")),
        ("Actions run", runtime["experiment"]["run_id"], (observation["entities"]["actions_run"].get("provider_identity") or {}).get("run_id")),
        ("Run attempt", 1, (observation["entities"]["actions_run"].get("provider_identity") or {}).get("run_attempt")),
        ("Actions -> Image", True, _present(observation, "relationships", "actions_image")),
        ("Image digest", provider_index_digest(runtime), (observation["entities"]["image"].get("provider_identity") or {}).get("image_digest")),
        ("Image -> Deployment", True, _present(observation, "relationships", "image_deployment")),
        ("Deployment UID", runtime["kubernetes"]["deployment_uid"], (observation["entities"]["deployment"].get("provider_identity") or {}).get("uid")),
        ("Deployment -> ReplicaSet", True, _present(observation, "relationships", "deployment_replicaset")),
        ("ReplicaSet UID", runtime["kubernetes"]["replicaset_uid"], (observation["entities"]["replicaset"].get("provider_identity") or {}).get("uid")),
        ("ReplicaSet -> Pod", True, _present(observation, "relationships", "replicaset_pod")),
        ("Pod UID", runtime["kubernetes"]["pod_uid"], (observation["entities"]["pod"].get("provider_identity") or {}).get("uid")),
        ("Pod failure", True, actual_runtime.get("pod_failure_present")),
        ("Exit code", 42, actual_runtime.get("exit_code")),
        ("Restart/backoff", True, bool((actual_runtime.get("restart_count") or 0) >= 1 and actual_runtime.get("backoff_reason"))),
        ("Operational impact", [1, 0, 0], [actual_runtime.get("desired_replicas"), actual_runtime.get("ready_replicas"), actual_runtime.get("available_replicas")]),
        ("Incident", True, incident.get("present")),
        ("Pinned topology", True, incident.get("pin_temporally_valid")),
        ("Affected entity", True, incident.get("affected_entity_matches_runtime")),
        ("Causal candidate", True, observation["causal"].get("candidate_present")),
        ("Causal relevance path", True, observation["causal"].get("relevance_path_present")),
        ("Top1 root cause", True, top1_match.get("exact")),
        ("Top3 supported causes", True, any(_source_match(expected, item)["exact"] for item in observation["causal"].get("top3", []))),
        ("TC4 evidence ledger", 0, evidence_audit["contradicting_count"]),
        ("Root-cause semantic level", RootCauseLevel.INITIATING_MUTATION.value, (observation["causal"].get("top1") or {}).get("semantic_level")),
    ]
    return [
        {
            "dimension": dimension,
            "independent_truth": truth,
            "current_topo": actual,
            "match": truth == actual,
        }
        for dimension, truth, actual in rows
    ]


def evaluate_source_cause(
    source_truth: dict[str, Any],
    runtime_receipt: dict[str, Any],
    topo_observation: dict[str, Any],
) -> dict[str, Any]:
    validate_source_mutation_contract(source_truth)
    validate_runtime_causal_receipt(runtime_receipt)
    validate_topo_observation(topo_observation)
    if topo_observation["run_id"] != runtime_receipt["experiment"]["run_id"]:
        raise ValueError("Runtime receipt and Topo observation run IDs differ.")
    expected = expected_initiating_mutation(source_truth)
    top1 = topo_observation["causal"].get("top1")
    top3 = topo_observation["causal"].get("top3") or []
    top1_match = _source_match(expected, top1)
    top3_matches = [_source_match(expected, item) for item in top3]
    partial = _commit_image_partial(
        top1,
        expected=expected,
        expected_image_digest=provider_index_digest(runtime_receipt),
    )
    evidence_audit = audit_evidence_ledger(
        topo_observation["causal"]["evidence_ledger"]
    )
    divergence = _first_divergence(expected, topo_observation, top1_match)
    verdict = _verdict(
        observation=topo_observation,
        top1_match=top1_match,
        top3_matches=top3_matches,
        commit_image_partial=partial,
        first_divergence=divergence,
    )
    result = {
        "schema_version": SOURCE_CAUSE_MATCH_VERSION,
        "run_id": runtime_receipt["experiment"]["run_id"],
        "expected_initiating_mutation": deepcopy(expected),
        "actual_top1": deepcopy(top1),
        "actual_top3": deepcopy(top3),
        "top1_source_match": top1_match,
        "top3_source_matches": top3_matches,
        "exact_commit_image_partial": partial,
        "root_cause_semantic_level": (
            top1.get("semantic_level") if top1 else RootCauseLevel.ABSTAINED.value
        ),
        "abstained": bool(
            not top1 or top1.get("semantic_level") == RootCauseLevel.ABSTAINED.value
        ),
        "evidence_audit": evidence_audit,
        "observation_matrix": _matrix(
            expected=expected,
            runtime_receipt=runtime_receipt,
            observation=topo_observation,
            top1_match=top1_match,
            evidence_audit=evidence_audit,
        ),
        "verdict": verdict.value,
        "first_internal_divergence": divergence.value,
        "diagnostics": {
            "structured_fields_only": True,
            "title_token_matching_used": False,
            "fuzzy_matching_used": False,
            "embeddings_used": False,
            "llm_used": False,
            "topo_used_to_construct_expected_truth": False,
        },
    }
    validate_source_cause_result(result)
    return result


def validate_source_cause_result(value: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "run_id",
        "expected_initiating_mutation",
        "actual_top1",
        "actual_top3",
        "top1_source_match",
        "top3_source_matches",
        "exact_commit_image_partial",
        "root_cause_semantic_level",
        "abstained",
        "evidence_audit",
        "observation_matrix",
        "verdict",
        "first_internal_divergence",
        "diagnostics",
    }
    if set(value) != required:
        raise ValueError("Source-cause result fields do not match v1.")
    if value.get("schema_version") != SOURCE_CAUSE_MATCH_VERSION:
        raise ValueError("Unsupported source-cause result version.")
    CausalVerdict(str(value.get("verdict")))
    FirstDivergence(str(value.get("first_internal_divergence")))
    RootCauseLevel(str(value.get("root_cause_semantic_level")))
    diagnostics = value.get("diagnostics") or {}
    if diagnostics != {
        "structured_fields_only": True,
        "title_token_matching_used": False,
        "fuzzy_matching_used": False,
        "embeddings_used": False,
        "llm_used": False,
        "topo_used_to_construct_expected_truth": False,
    }:
        raise ValueError("Source-cause evaluator independence is invalid.")
    if len(value.get("observation_matrix") or []) < 30:
        raise ValueError("The required LINEAGE-1C observation matrix is incomplete.")


def deterministic_result_json(value: dict[str, Any]) -> str:
    validate_source_cause_result(value)
    return deterministic_json(value)
