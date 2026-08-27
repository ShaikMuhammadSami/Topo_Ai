from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from evaluation.artifact_integrity import (
    EVALUATION_ARTIFACT_INTEGRITY_VERSION,
    verify_integrity_manifest,
    write_integrity_manifest,
)
from evaluation.lineage_broken_run_image import (
    ContractImplementationContradiction,
    analysis_diagnostics,
    evidence_semantics_audit,
    reset_derived_analysis,
    run_fresh_analysis,
    unsafe_specificity_scan,
)
from evaluation.lineage_distractor_robustness import (
    copy_seed_database,
    deterministic_json_bytes,
    sha256_file,
    validate_seed_database,
    write_json,
)


SCENARIO_VERSION = "lineage-2b3-missing-image-workload-v1"
ACCEPTED_MAIN_COMMIT = "5cb571caaca5248d1f117c310d542e64b6b12610"
EXPECTED_SEED_SHA256 = (
    "9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f"
)

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
DEFAULT_SEED_DB = (
    ROOT
    / "evaluation/results/lineage/post-sc4"
    / "topo-product-32695735269.db"
)
DEFAULT_OUTPUT_ROOT = (
    ROOT
    / "evaluation/results/lineage/adversarial"
    / "lineage-2b-missing-image-workload"
)

GOLDEN_REVISION = "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
GOLDEN_EVENT_ID = "change-event:20a8946c8c445153d85c90ee2166d487"
GOLDEN_MUTATION_ID = (
    "source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633"
)
GOLDEN_RUN_ID = "32695735269"
GOLDEN_IMAGE_DIGEST = (
    "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"
)
GOLDEN_IMAGE_REFERENCE = (
    "ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@" + GOLDEN_IMAGE_DIGEST
)
RUNTIME_STATUS_DIGEST = (
    "sha256:a3392fbeae192e861a3df42d25acf050c45a657c8e277a41258332baa9451f53"
)
IMAGE_ENTITY_ID = f"artifact:container-image:{GOLDEN_IMAGE_DIGEST}"
RUN_ENTITY_ID = "github:api.github.com:workflow-run:32695735269"
COMMIT_ENTITY_ID = (
    "github:api.github.com:repository:1278498159:commit:" + GOLDEN_REVISION
)
DEPLOYMENT_ENTITY_ID = (
    "k8s:docker-desktop:deployment:bd4cfb7a-d32a-43bf-bf82-366e3fd8841a"
)
REPLICASET_ENTITY_ID = (
    "k8s:docker-desktop:replicaset:200703db-a601-44f0-90ff-63c64cb17162"
)
POD_ENTITY_ID = "k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168"
GOLDEN_INCIDENT_ID = (
    "incident:docker-desktop:topo-eval-lineage-causal-32695735269:"
    "workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3"
)
GOLDEN_INCIDENT_BOUNDARY = "2026-08-26T05:09:49+00:00"
GOLDEN_SNAPSHOT_ID = "snapshot:actions-enriched:20260826T051031Z:2d8416d3"
GOLDEN_SIGNAL_ID = (
    "signal:kubernetes-event:docker-desktop:"
    "ad733dcc-a026-424f-8984-6ed30108eec1"
)

E1_ID = "build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb"
RUN_IMAGE_RELATIONSHIP_ID = "rel:63f5cd5dfce59d148ae5"
RUN_IMAGE_EVIDENCE_ID = "evidence:github-actions-build:c9b6d53cf66facfb444c8ae0"
COMMIT_RUN_RELATIONSHIP_ID = "rel:ebaedc357f11b3e70170"
COMMIT_RUN_EVIDENCE_ID = "evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b"
DEPLOYMENT_IMAGE_RELATIONSHIP_ID = "rel:496906e3e345259910c9"
POD_IMAGE_RELATIONSHIP_ID = "rel:0548ac3e949f44b3569c"
DEPLOYMENT_REPLICASET_RELATIONSHIP_ID = "rel:57555e411f2db29864c2"
REPLICASET_POD_RELATIONSHIP_ID = "rel:9c8db862d53bac71327f"
CONTAINER_IMAGE_EVIDENCE_ID = (
    "evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56"
)
LAST_APPLIED_ANNOTATION = "kubectl.kubernetes.io/last-applied-configuration"
CONTAINER_NAME = "fixture"

VOLATILE_FIELDS_NORMALIZED = ("generated_at", "temporary_copy_path")
FIRST_DIVERGENCE_ORDER = (
    "BROKEN_HOP_STILL_PRESENT",
    "FABRICATED_IMAGE_WORKLOAD_PROVENANCE",
    "SOURCE_CAUSE_FALSELY_SUPPORTED",
    "UNSAFE_SOURCE_SPECIFICITY_PRESERVED",
    "VALID_PRESERVED_EVIDENCE_CORRUPTED",
    "EVIDENCE_SEMANTICS_DEGRADED",
    "NONDETERMINISTIC_RESULT",
    "NO_DIVERGENCE",
)


class ExperimentConstructionBlocked(RuntimeError):
    pass


def _connect(database_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    path = database_path.resolve()
    if read_only:
        connection = sqlite3.connect(
            f"file:{path.as_posix()}?mode=ro&immutable=1",
            uri=True,
        )
        connection.execute("PRAGMA query_only=ON")
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _row(
    connection: sqlite3.Connection,
    statement: str,
    values: tuple[Any, ...],
) -> dict[str, Any] | None:
    result = connection.execute(statement, values).fetchone()
    return dict(result) if result is not None else None


def _rows(
    connection: sqlite3.Connection,
    statement: str,
    values: tuple[Any, ...],
) -> list[dict[str, Any]]:
    return [dict(item) for item in connection.execute(statement, values).fetchall()]


def _semantic_sha256(value: Any) -> str:
    return hashlib.sha256(deterministic_json_bytes(value)).hexdigest()


def _by_id(values: Iterable[Mapping[str, Any]], item_id: str) -> dict[str, Any] | None:
    matches = [dict(item) for item in values if item.get("id") == item_id]
    if len(matches) > 1:
        raise ContractImplementationContradiction(f"Duplicate persisted ID: {item_id}")
    return matches[0] if matches else None


def _load_snapshot(
    connection: sqlite3.Connection,
) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _row(
        connection,
        "SELECT * FROM topology_snapshots WHERE snapshot_id = ?",
        (GOLDEN_SNAPSHOT_ID,),
    )
    if record is None:
        raise ContractImplementationContradiction("The pinned snapshot is absent.")
    payload = json.loads(str(record["payload_json"]))
    if not isinstance(payload, dict):
        raise ContractImplementationContradiction("Snapshot payload is not an object.")
    return record, payload


def _source_mutation(event: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    metadata = json.loads(str(event["metadata_json"]))
    matches = [
        dict(value)
        for value in metadata.get("source_file_mutations", [])
        if isinstance(value, dict) and value.get("mutation_id") == GOLDEN_MUTATION_ID
    ]
    return matches[0] if len(matches) == 1 else None


def _container(entity: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if entity is None:
        return None
    properties = entity.get("properties")
    containers = properties.get("containers", []) if isinstance(properties, dict) else []
    matches = [
        dict(value)
        for value in containers
        if isinstance(value, dict) and value.get("name") == CONTAINER_NAME
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _annotation_document(entity: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if entity is None:
        return None
    properties = entity.get("properties")
    annotations = properties.get("annotations", {}) if isinstance(properties, dict) else {}
    raw = annotations.get(LAST_APPLIED_ANNOTATION) if isinstance(annotations, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ExperimentConstructionBlocked("annotation_authority_nonseparable") from error
    if not isinstance(value, dict):
        raise ExperimentConstructionBlocked("annotation_authority_nonseparable")
    return value


def _annotation_container(document: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        containers = document["spec"]["template"]["spec"]["containers"]
    except (KeyError, TypeError):
        return None
    matches = [
        value
        for value in containers
        if isinstance(value, dict) and value.get("name") == CONTAINER_NAME
    ]
    return matches[0] if len(matches) == 1 else None


def _missing_observation(observation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semantic_role": observation["semantic_role"],
        "source_field": observation["source_field"],
        "capture_state": "missing",
        "raw_value": None,
        "raw_value_length": 0,
        "scheme": None,
        "registry": None,
        "repository": None,
        "tag": None,
        "digest": None,
        "normalized_reference": None,
        "reference_kind": "unknown",
        "immutable_identity_eligible": False,
        "rejection_reason": None,
    }


def _without_workload_image_authority(entity: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(entity))
    properties = value.get("properties", {})
    for container in properties.get("containers", []):
        if isinstance(container, dict) and container.get("name") == CONTAINER_NAME:
            for key in ("image", "image_id", "runtime_status_image", "image_identity"):
                container.pop(key, None)
    annotations = properties.get("annotations")
    if isinstance(annotations, dict) and LAST_APPLIED_ANNOTATION in annotations:
        try:
            document = json.loads(str(annotations[LAST_APPLIED_ANNOTATION]))
        except json.JSONDecodeError:
            document = None
        if isinstance(document, dict):
            target = _annotation_container(document)
            if target is not None:
                target.pop("image", None)
            annotations[LAST_APPLIED_ANNOTATION] = document
    return value


def _selected_signal(signal: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "signal_id": signal["signal_id"],
        "reason": signal["reason"],
        "involved_entity_id": signal["involved_entity_id"],
        "first_observed_at": signal["first_observed_at"],
        "last_observed_at": signal["last_observed_at"],
        "payload": json.loads(str(signal["payload_json"])),
    }


def _selected_incident(incident: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if incident is None:
        return None
    return {
        "incident_id": incident["incident_id"],
        "primary_signal_id": incident["primary_signal_id"],
        "topology_snapshot_id": incident["topology_snapshot_id"],
        "affected_entity_id": incident["affected_entity_id"],
        "first_observed_at": incident["first_observed_at"],
        "last_observed_at": incident["last_observed_at"],
    }


def inspect_database(database_path: Path, *, read_only: bool = True) -> dict[str, Any]:
    connection = _connect(database_path, read_only=read_only)
    try:
        record, payload = _load_snapshot(connection)
        entities = payload.get("entities", [])
        relationships = payload.get("relationships", [])
        evidence = payload.get("evidence", [])
        metadata = payload.get("metadata", {})
        if not all(isinstance(value, list) for value in (entities, relationships, evidence)):
            raise ContractImplementationContradiction("Graph collections are not lists.")
        entity_by_id = {str(value.get("id")): value for value in entities if isinstance(value, dict)}
        relationship_by_id = {
            str(value.get("id")): value for value in relationships if isinstance(value, dict)
        }
        evidence_by_id = {str(value.get("id")): value for value in evidence if isinstance(value, dict)}
        event = _row(connection, "SELECT * FROM change_events WHERE event_id = ?", (GOLDEN_EVENT_ID,))
        incident = _row(connection, "SELECT * FROM incidents WHERE incident_id = ?", (GOLDEN_INCIDENT_ID,))
        signal = _row(connection, "SELECT * FROM signals WHERE signal_id = ?", (GOLDEN_SIGNAL_ID,))
        e1 = _row(connection, "SELECT * FROM build_artifact_evidence WHERE evidence_id = ?", (E1_ID,))
        analyses = _rows(
            connection,
            "SELECT analysis_id FROM causal_analyses WHERE incident_id = ? ORDER BY analysis_id",
            (GOLDEN_INCIDENT_ID,),
        )
        legacy = _rows(
            connection,
            "SELECT analysis_id FROM incident_analyses WHERE signal_id = ? AND topology_snapshot_id = ? ORDER BY analysis_id",
            (GOLDEN_SIGNAL_ID, GOLDEN_SNAPSHOT_ID),
        )
        deployment = entity_by_id.get(DEPLOYMENT_ENTITY_ID)
        pod = entity_by_id.get(POD_ENTITY_ID)
        deployment_container = _container(deployment)
        pod_container = _container(pod)
        annotation = _annotation_document(deployment)
        annotation_container = _annotation_container(annotation) if annotation else None
        return {
            "database_sha256": sha256_file(database_path),
            "snapshot_id": record["snapshot_id"],
            "snapshot_counts": {
                "record": {
                    "entities": record["entity_count"],
                    "relationships": record["relationship_count"],
                    "evidence": record["evidence_count"],
                },
                "payload": {
                    "entities": len(entities),
                    "relationships": len(relationships),
                    "evidence": len(evidence),
                },
                "container_image_artifacts": metadata.get("container_image_artifacts"),
            },
            "deployment_container": deployment_container,
            "pod_container": pod_container,
            "annotation": {
                "valid_json": annotation is not None,
                "path": "spec.template.spec.containers[name=fixture].image",
                "image": annotation_container.get("image") if annotation_container else None,
                "document": annotation,
            },
            "relationships": {
                key: relationship_by_id.get(value)
                for key, value in {
                    "commit_run": COMMIT_RUN_RELATIONSHIP_ID,
                    "run_image": RUN_IMAGE_RELATIONSHIP_ID,
                    "deployment_image": DEPLOYMENT_IMAGE_RELATIONSHIP_ID,
                    "pod_image": POD_IMAGE_RELATIONSHIP_ID,
                    "deployment_replicaset": DEPLOYMENT_REPLICASET_RELATIONSHIP_ID,
                    "replicaset_pod": REPLICASET_POD_RELATIONSHIP_ID,
                }.items()
            },
            "evidence": {
                "commit_run": evidence_by_id.get(COMMIT_RUN_EVIDENCE_ID),
                "run_image": evidence_by_id.get(RUN_IMAGE_EVIDENCE_ID),
                "container_images": evidence_by_id.get(CONTAINER_IMAGE_EVIDENCE_ID),
            },
            "entities": {
                "run": entity_by_id.get(RUN_ENTITY_ID),
                "image": entity_by_id.get(IMAGE_ENTITY_ID),
                "deployment": deployment,
                "replicaset": entity_by_id.get(REPLICASET_ENTITY_ID),
                "pod": pod,
            },
            "source_event": event,
            "source_mutation": _source_mutation(event),
            "e1": e1,
            "signal": _selected_signal(signal),
            "incident": _selected_incident(incident),
            "causal_analysis_ids": [value["analysis_id"] for value in analyses],
            "legacy_analysis_ids": [value["analysis_id"] for value in legacy],
            "incident_analysis_cache": {
                "latest_analysis_id": incident.get("latest_analysis_id") if incident else None,
                "top_hypothesis_title": incident.get("top_hypothesis_title") if incident else None,
                "top_hypothesis_score": incident.get("top_hypothesis_score") if incident else None,
            },
        }
    finally:
        connection.close()


def snapshot_identity_audit() -> dict[str, Any]:
    service = ROOT / "backend/app/services/github_actions_graph.py"
    repository = ROOT / "backend/app/repositories/topology_snapshot_repository.py"
    service_text = service.read_text(encoding="utf-8")
    repository_text = repository.read_text(encoding="utf-8")
    observation_id = "snapshot:actions-enriched:" in service_text and "uuid4" in service_text
    content_hash_required = "sha256" in service_text[service_text.find("snapshot:actions-enriched:") - 500 : service_text.find("snapshot:actions-enriched:") + 500]
    supplied_id_persisted = "snapshot.snapshot_id" in repository_text
    return {
        "model": "observation-record identifier: timestamp plus random suffix",
        "content_addressed": bool(content_hash_required),
        "constructor_observed": observation_id,
        "repository_persists_supplied_id": supplied_id_persisted,
        "same_historical_observation_with_incomplete_retained_evidence_is_valid": bool(
            observation_id and supplied_id_persisted and not content_hash_required
        ),
        "construction_blocked": not (
            observation_id and supplied_id_persisted and not content_hash_required
        ),
        "blocker_reason": None
        if observation_id and supplied_id_persisted and not content_hash_required
        else "snapshot_identity_nonseparable",
    }


def verify_contract_schema(seed_db: Path) -> dict[str, Any]:
    identity = snapshot_identity_audit()
    if identity["construction_blocked"]:
        raise ExperimentConstructionBlocked("snapshot_identity_nonseparable")
    inventory = inspect_database(seed_db, read_only=True)
    container_evidence = inventory["evidence"]["container_images"]
    expected = {
        "snapshot_id": inventory["snapshot_id"] == GOLDEN_SNAPSHOT_ID,
        "counts_match": inventory["snapshot_counts"]["record"] == {
            key: inventory["snapshot_counts"]["payload"][key]
            for key in ("entities", "relationships", "evidence")
        },
        "source_mutation": inventory["source_mutation"] is not None,
        "e1": inventory["e1"] is not None,
        "run_image": inventory["relationships"]["run_image"] is not None,
        "run_image_evidence": inventory["evidence"]["run_image"] is not None,
        "container_image": inventory["entities"]["image"] is not None,
        "deployment": inventory["entities"]["deployment"] is not None,
        "replicaset": inventory["entities"]["replicaset"] is not None,
        "pod": inventory["entities"]["pod"] is not None,
        "deployment_image": inventory["relationships"]["deployment_image"] is not None,
        "pod_image": inventory["relationships"]["pod_image"] is not None,
        "owner_chain": all(
            inventory["relationships"][key] is not None
            for key in ("deployment_replicaset", "replicaset_pod")
        ),
        "shared_evidence_separable": bool(
            container_evidence
            and sorted(container_evidence.get("related_relationship_ids", []))
            == sorted([DEPLOYMENT_IMAGE_RELATIONSHIP_ID, POD_IMAGE_RELATIONSHIP_ID])
        ),
        "deployment_requested": bool(
            inventory["deployment_container"]
            and inventory["deployment_container"].get("image") == GOLDEN_IMAGE_REFERENCE
        ),
        "pod_requested": bool(
            inventory["pod_container"]
            and inventory["pod_container"].get("image") == GOLDEN_IMAGE_REFERENCE
        ),
        "pod_runtime_image_id": bool(
            inventory["pod_container"]
            and inventory["pod_container"].get("image_id") == GOLDEN_IMAGE_REFERENCE
        ),
        "pod_runtime_status": bool(
            inventory["pod_container"]
            and inventory["pod_container"].get("runtime_status_image") == RUNTIME_STATUS_DIGEST
        ),
        "annotation": inventory["annotation"]["image"] == GOLDEN_IMAGE_REFERENCE,
        "failure": bool(
            inventory["signal"]
            and inventory["signal"]["reason"] == "BackOff"
            and inventory["signal"]["involved_entity_id"] == POD_ENTITY_ID
        ),
        "incident_pin": bool(
            inventory["incident"]
            and inventory["incident"]["topology_snapshot_id"] == GOLDEN_SNAPSHOT_ID
            and inventory["incident"]["first_observed_at"] == GOLDEN_INCIDENT_BOUNDARY
        ),
    }
    failures = sorted(key for key, value in expected.items() if not value)
    if failures:
        raise ContractImplementationContradiction(
            "Current schema contradicts frozen B3 contract: " + ", ".join(failures)
        )
    return {"status": "compatible", "snapshot_identity": identity, "checks": expected, "inventory": inventory}


def authority_classification(inventory: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "protected_source_build_authority": [
            GOLDEN_MUTATION_ID,
            COMMIT_RUN_RELATIONSHIP_ID,
            E1_ID,
            RUN_IMAGE_RELATIONSHIP_ID,
            RUN_IMAGE_EVIDENCE_ID,
            IMAGE_ENTITY_ID,
        ],
        "protected_runtime_authority": [
            DEPLOYMENT_ENTITY_ID,
            REPLICASET_ENTITY_ID,
            POD_ENTITY_ID,
            DEPLOYMENT_REPLICASET_RELATIONSHIP_ID,
            REPLICASET_POD_RELATIONSHIP_ID,
            GOLDEN_SIGNAL_ID,
            GOLDEN_INCIDENT_ID,
            GOLDEN_SNAPSHOT_ID,
        ],
        "removed_authoritative_observations": [
            "affected Deployment requested image",
            "affected Pod requested image",
            "affected Pod runtime imageID",
            "affected Pod runtime-status image",
        ],
        "removed_derived_claims": [
            DEPLOYMENT_IMAGE_RELATIONSHIP_ID,
            POD_IMAGE_RELATIONSHIP_ID,
            CONTAINER_IMAGE_EVIDENCE_ID,
            "metadata.container_image_artifacts.relationships",
        ],
        "derived_reset": {
            "causal_analysis_ids": list(inventory["causal_analysis_ids"]),
            "legacy_analysis_ids": list(inventory["legacy_analysis_ids"]),
            "incident_cache": dict(inventory["incident_analysis_cache"]),
        },
        "synthetic_authority": False,
    }


def _workload_protected_projection(entity: Mapping[str, Any] | None) -> Any:
    return _without_workload_image_authority(entity) if entity else None


def protected_fingerprints(inventory: Mapping[str, Any]) -> dict[str, str]:
    groups = {
        "source_mutation": inventory["source_mutation"],
        "commit_run": {
            "relationship": inventory["relationships"]["commit_run"],
            "evidence": inventory["evidence"]["commit_run"],
        },
        "e1": inventory["e1"],
        "run_image": inventory["relationships"]["run_image"],
        "run_image_provider_evidence": inventory["evidence"]["run_image"],
        "container_image": inventory["entities"]["image"],
        "deployment_non_image": _workload_protected_projection(inventory["entities"]["deployment"]),
        "replicaset": inventory["entities"]["replicaset"],
        "pod_non_image": _workload_protected_projection(inventory["entities"]["pod"]),
        "owner_chain": {
            "deployment_replicaset": inventory["relationships"]["deployment_replicaset"],
            "replicaset_pod": inventory["relationships"]["replicaset_pod"],
        },
        "runtime_failure": inventory["signal"],
        "incident_pin": inventory["incident"],
        "annotation_unrelated_semantics": (
            _without_workload_image_authority(inventory["entities"]["deployment"])
            .get("properties", {})
            .get("annotations", {})
            .get(LAST_APPLIED_ANNOTATION)
        ),
    }
    return {key: _semantic_sha256(value) for key, value in sorted(groups.items())}


def pre_mutation_image_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    deployment = inventory["deployment_container"] or {}
    pod = inventory["pod_container"] or {}
    return {
        "deployment": {
            "requested_image": deployment.get("image"),
            "image_identity": deployment.get("image_identity"),
        },
        "annotation": inventory["annotation"],
        "pod": {
            "requested_image": pod.get("image"),
            "runtime_image_id": pod.get("image_id"),
            "runtime_status_image": pod.get("runtime_status_image"),
            "image_identity": pod.get("image_identity"),
        },
        "relationships": {
            "deployment_image": inventory["relationships"]["deployment_image"],
            "pod_image": inventory["relationships"]["pod_image"],
        },
        "shared_evidence": inventory["evidence"]["container_images"],
        "snapshot_counts": inventory["snapshot_counts"],
    }


def _scan_value(value: Any, *, path: str = "$") -> list[dict[str, str]]:
    needles = {
        "golden_image_reference": GOLDEN_IMAGE_REFERENCE,
        "golden_digest": GOLDEN_IMAGE_DIGEST,
        "runtime_status_digest": RUNTIME_STATUS_DIGEST,
        "image_entity_id": IMAGE_ENTITY_ID,
        "deployment_image_relationship_id": DEPLOYMENT_IMAGE_RELATIONSHIP_ID,
        "pod_image_relationship_id": POD_IMAGE_RELATIONSHIP_ID,
        "shared_image_evidence_id": CONTAINER_IMAGE_EVIDENCE_ID,
    }
    matches: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            matches.extend(_scan_value(value[key], path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            matches.extend(_scan_value(item, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        parsed: Any = None
        if value.startswith("{") or value.startswith("["):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, (dict, list)):
            matches.extend(_scan_value(parsed, path=f"{path}<json>"))
        for label, needle in needles.items():
            if needle in value:
                matches.append({"path": path, "match_type": label, "value": value})
    return matches


def recursive_coreference_scan(inventory: Mapping[str, Any]) -> dict[str, Any]:
    scope = {
        "deployment": inventory["entities"]["deployment"],
        "pod": inventory["entities"]["pod"],
        "deployment_image_relationship": inventory["relationships"]["deployment_image"],
        "pod_image_relationship": inventory["relationships"]["pod_image"],
        "container_image_evidence": inventory["evidence"]["container_images"],
        "container_image_metadata": inventory["snapshot_counts"]["container_image_artifacts"],
        "cached_analysis": {
            "ids": inventory["causal_analysis_ids"],
            "legacy_ids": inventory["legacy_analysis_ids"],
            "incident_cache": inventory["incident_analysis_cache"],
        },
    }
    matches = _scan_value(scope)
    return {
        "scope": sorted(scope),
        "matches": matches,
        "count": len(matches),
        "authoritative_workload_image_association_remaining": len(matches),
    }


def alternative_authority_scan(inventory: Mapping[str, Any]) -> dict[str, Any]:
    relationships = [
        value
        for value in inventory["relationships"].values()
        if isinstance(value, dict)
        and value.get("relationship_type") == "uses"
        and value.get("source_entity_id") in {DEPLOYMENT_ENTITY_ID, POD_ENTITY_ID}
        and value.get("target_entity_id") == IMAGE_ENTITY_ID
    ]
    return {"count": len(relationships), "relationship_ids": sorted(value["id"] for value in relationships)}


def _redact_container(container: dict[str, Any]) -> dict[str, Any]:
    before = copy.deepcopy(container)
    identity = container.get("image_identity")
    if not isinstance(identity, dict):
        raise ExperimentConstructionBlocked("workload_image_authority_nonseparable")
    for key in ("requested_image", "runtime_status_image", "runtime_image_id"):
        observation = identity.get(key)
        if not isinstance(observation, dict):
            raise ExperimentConstructionBlocked("workload_image_authority_nonseparable")
        identity[key] = _missing_observation(observation)
    identity["resolved_artifact_identity"] = None
    identity["resolved_artifact_basis"] = None
    identity["identity_evidence_refs"] = []
    identity["ambiguous_runtime_status_images"] = []
    identity["ambiguous_runtime_image_ids"] = []
    container["image"] = None
    container["image_id"] = None
    container["runtime_status_image"] = None
    return {"before": before, "after": copy.deepcopy(container)}


def apply_b3_mutation(database_path: Path) -> dict[str, Any]:
    before = inspect_database(database_path, read_only=False)
    before_fingerprints = protected_fingerprints(before)
    annotation_before = before["annotation"]["document"]
    if not isinstance(annotation_before, dict):
        raise ExperimentConstructionBlocked("annotation_authority_nonseparable")
    annotation_unrelated_before = copy.deepcopy(annotation_before)
    annotation_target_before = _annotation_container(annotation_unrelated_before)
    if annotation_target_before is None or annotation_target_before.get("image") != GOLDEN_IMAGE_REFERENCE:
        raise ExperimentConstructionBlocked("annotation_authority_nonseparable")
    annotation_target_before.pop("image")
    annotation_fingerprint_before = _semantic_sha256(annotation_unrelated_before)

    connection = _connect(database_path)
    try:
        record, payload = _load_snapshot(connection)
        entities = payload["entities"]
        relationships = payload["relationships"]
        evidence = payload["evidence"]
        deployment = _by_id(entities, DEPLOYMENT_ENTITY_ID)
        pod = _by_id(entities, POD_ENTITY_ID)
        if deployment is None or pod is None:
            raise ExperimentConstructionBlocked("workload_identity_missing")
        deployment_container = next(
            (value for value in deployment["properties"]["containers"] if value.get("name") == CONTAINER_NAME),
            None,
        )
        pod_container = next(
            (value for value in pod["properties"]["containers"] if value.get("name") == CONTAINER_NAME),
            None,
        )
        if not isinstance(deployment_container, dict) or not isinstance(pod_container, dict):
            raise ExperimentConstructionBlocked("workload_image_authority_nonseparable")
        deployment_changes = _redact_container(deployment_container)
        pod_changes = _redact_container(pod_container)

        annotations = deployment["properties"].get("annotations", {})
        raw_annotation = annotations.get(LAST_APPLIED_ANNOTATION)
        try:
            annotation = json.loads(str(raw_annotation))
        except json.JSONDecodeError as error:
            raise ExperimentConstructionBlocked("annotation_authority_nonseparable") from error
        annotation_target = _annotation_container(annotation)
        if annotation_target is None or annotation_target.get("image") != GOLDEN_IMAGE_REFERENCE:
            raise ExperimentConstructionBlocked("annotation_authority_nonseparable")
        annotation_target.pop("image")
        annotations[LAST_APPLIED_ANNOTATION] = json.dumps(
            annotation, sort_keys=True, separators=(",", ":")
        )
        annotation_fingerprint_after = _semantic_sha256(annotation)
        if annotation_fingerprint_after != annotation_fingerprint_before:
            raise ExperimentConstructionBlocked("annotation_authority_nonseparable")

        relationship_ids_before = [value["id"] for value in relationships]
        payload["relationships"] = [
            value
            for value in relationships
            if value.get("id") not in {DEPLOYMENT_IMAGE_RELATIONSHIP_ID, POD_IMAGE_RELATIONSHIP_ID}
        ]
        shared_evidence = _by_id(evidence, CONTAINER_IMAGE_EVIDENCE_ID)
        if shared_evidence is None or sorted(shared_evidence.get("related_relationship_ids", [])) != sorted(
            [DEPLOYMENT_IMAGE_RELATIONSHIP_ID, POD_IMAGE_RELATIONSHIP_ID]
        ):
            raise ExperimentConstructionBlocked("container_image_evidence_nonseparable")
        payload["evidence"] = [
            value for value in evidence if value.get("id") != CONTAINER_IMAGE_EVIDENCE_ID
        ]
        image_metadata = payload.get("metadata", {}).get("container_image_artifacts")
        if not isinstance(image_metadata, dict) or image_metadata.get("count") != 1 or image_metadata.get("relationships") != 2:
            raise ExperimentConstructionBlocked("container_image_metadata_nonseparable")
        image_metadata["relationships"] = 0

        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        if str(record["snapshot_id"]) != GOLDEN_SNAPSHOT_ID:
            raise ExperimentConstructionBlocked("snapshot_identity_nonseparable")
        with connection:
            connection.execute(
                """
                UPDATE topology_snapshots
                SET relationship_count = ?, evidence_count = ?, payload_json = ?
                WHERE snapshot_id = ?
                """,
                (len(payload["relationships"]), len(payload["evidence"]), payload_json, GOLDEN_SNAPSHOT_ID),
            )
    finally:
        connection.close()

    if str(BACKEND_ROOT) not in __import__("sys").path:
        __import__("sys").path.insert(0, str(BACKEND_ROOT))
    from app.models.topology import GraphSnapshot

    GraphSnapshot.model_validate(payload)
    after = inspect_database(database_path, read_only=False)
    after_fingerprints = protected_fingerprints(after)
    changed = sorted(key for key in before_fingerprints if before_fingerprints[key] != after_fingerprints[key])
    return {
        "mutation": "complete affected workload/golden-image retained-evidence cut",
        "snapshot_id_before": before["snapshot_id"],
        "snapshot_id_after": after["snapshot_id"],
        "deployment_container": deployment_changes,
        "pod_container": pod_changes,
        "annotation": {
            "path": "spec.template.spec.containers[name=fixture].image",
            "operation": "member removed",
            "replacement_value": None,
            "canonical_serialization": True,
            "unrelated_semantic_sha256_before": annotation_fingerprint_before,
            "unrelated_semantic_sha256_after": annotation_fingerprint_after,
            "preserved": annotation_fingerprint_before == annotation_fingerprint_after,
        },
        "relationships_removed": sorted(
            set(relationship_ids_before)
            - {value["id"] for value in payload["relationships"]}
        ),
        "evidence_removed": [CONTAINER_IMAGE_EVIDENCE_ID],
        "counter_changes": {
            "before": before["snapshot_counts"],
            "after": after["snapshot_counts"],
        },
        "protected_fingerprints": {
            "before": before_fingerprints,
            "after": after_fingerprints,
            "changed": changed,
            "preserved": not changed,
        },
        "graph_snapshot_validation": "passed",
        "synthetic_authority_added": False,
        "post_inventory": after,
    }


def validate_control_precondition(inventory: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "source_mutation": inventory["source_mutation"] is not None,
        "commit_run": inventory["relationships"]["commit_run"] is not None,
        "e1": inventory["e1"] is not None,
        "run_image": inventory["relationships"]["run_image"] is not None,
        "run_image_evidence": inventory["evidence"]["run_image"] is not None,
        "container_image": inventory["entities"]["image"] is not None,
        "deployment_image": inventory["relationships"]["deployment_image"] is not None,
        "pod_image": inventory["relationships"]["pod_image"] is not None,
        "deployment_replicaset": inventory["relationships"]["deployment_replicaset"] is not None,
        "replicaset_pod": inventory["relationships"]["replicaset_pod"] is not None,
        "failure": inventory["signal"] is not None,
        "incident_pin": inventory["incident"] is not None,
    }
    return {"valid": all(required.values()), "required_present": required}


def validate_b3_construction(inventory: Mapping[str, Any]) -> dict[str, Any]:
    deployment = inventory["deployment_container"] or {}
    pod = inventory["pod_container"] or {}
    deployment_identity = deployment.get("image_identity") or {}
    pod_identity = pod.get("image_identity") or {}
    required_present = {
        "source_mutation": inventory["source_mutation"] is not None,
        "commit_run": inventory["relationships"]["commit_run"] is not None,
        "e1": inventory["e1"] is not None,
        "run_image": inventory["relationships"]["run_image"] is not None,
        "run_image_evidence": inventory["evidence"]["run_image"] is not None,
        "container_image": inventory["entities"]["image"] is not None,
        "deployment": inventory["entities"]["deployment"] is not None,
        "replicaset": inventory["entities"]["replicaset"] is not None,
        "pod": inventory["entities"]["pod"] is not None,
        "deployment_replicaset": inventory["relationships"]["deployment_replicaset"] is not None,
        "replicaset_pod": inventory["relationships"]["replicaset_pod"] is not None,
        "runtime_failure": inventory["signal"] is not None,
        "incident_pin": bool(
            inventory["incident"]
            and inventory["incident"]["topology_snapshot_id"] == GOLDEN_SNAPSHOT_ID
            and inventory["incident"]["first_observed_at"] == GOLDEN_INCIDENT_BOUNDARY
        ),
    }
    required_absent = {
        "deployment_requested_image": deployment.get("image") is None,
        "deployment_resolved_identity": deployment_identity.get("resolved_artifact_identity") is None,
        "deployment_identity_refs": not deployment_identity.get("identity_evidence_refs"),
        "annotation_image": inventory["annotation"]["image"] is None,
        "pod_requested_image": pod.get("image") is None,
        "pod_runtime_image_id": pod.get("image_id") is None,
        "pod_runtime_status_image": pod.get("runtime_status_image") is None,
        "pod_resolved_identity": pod_identity.get("resolved_artifact_identity") is None,
        "pod_identity_refs": not pod_identity.get("identity_evidence_refs"),
        "deployment_image_relationship": inventory["relationships"]["deployment_image"] is None,
        "pod_image_relationship": inventory["relationships"]["pod_image"] is None,
        "container_image_evidence": inventory["evidence"]["container_images"] is None,
        "stale_causal_analysis": not inventory["causal_analysis_ids"],
        "stale_legacy_analysis": not inventory["legacy_analysis_ids"],
        "stale_cache": all(value is None for value in inventory["incident_analysis_cache"].values()),
    }
    scan = recursive_coreference_scan(inventory)
    alternative = alternative_authority_scan(inventory)
    counts_consistent = inventory["snapshot_counts"]["record"] == {
        key: inventory["snapshot_counts"]["payload"][key]
        for key in ("entities", "relationships", "evidence")
    }
    broken_hop_present = not all(required_absent.values()) or scan["count"] > 0 or alternative["count"] > 0
    return {
        "valid": all(required_present.values()) and not broken_hop_present and counts_consistent,
        "required_present": required_present,
        "required_absent": required_absent,
        "broken_hop_present": broken_hop_present,
        "recursive_coreference": scan,
        "alternative_authority": alternative,
        "snapshot_counts_consistent": counts_consistent,
    }


def fabrication_scan(analysis: Mapping[str, Any]) -> dict[str, Any]:
    surfaces: list[str] = []
    for index, audit in enumerate(analysis.get("candidate_relevance_audit", [])):
        if audit.get("candidate_event_id") != GOLDEN_EVENT_ID:
            continue
        path = audit.get("topology_path") or []
        path_values = json.dumps(path, sort_keys=True)
        if IMAGE_ENTITY_ID in path_values and (
            POD_ENTITY_ID in path_values or DEPLOYMENT_ENTITY_ID in path_values
        ):
            surfaces.append(f"candidate_relevance_audit[{index}].topology_path")
    for index, hypothesis in enumerate(analysis.get("hypotheses", [])):
        if hypothesis.get("root_event_id") != GOLDEN_EVENT_ID:
            continue
        chain = json.dumps(hypothesis.get("causal_chain", []), sort_keys=True)
        if IMAGE_ENTITY_ID in chain and (POD_ENTITY_ID in chain or DEPLOYMENT_ENTITY_ID in chain):
            surfaces.append(f"hypotheses[{index}].causal_chain")
    return {"count": len(sorted(set(surfaces))), "surfaces": sorted(set(surfaces))}


def normalized_semantic_output(
    *,
    construction: Mapping[str, Any],
    mutation: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    fabrication: Mapping[str, Any],
    unsafe: Mapping[str, Any],
    evidence_semantics: Mapping[str, Any],
) -> dict[str, Any]:
    mutation_semantics = {
        key: value
        for key, value in mutation.items()
        if key not in {"post_inventory"}
    }
    return {
        "construction": construction,
        "mutation": mutation_semantics,
        "diagnostics": diagnostics,
        "fabrication": fabrication,
        "unsafe_specificity": unsafe,
        "evidence_semantics": evidence_semantics,
    }


def grade_taxonomy(
    *,
    construction: Mapping[str, Any],
    fabrication: Mapping[str, Any],
    source_supported: bool,
    unsafe: Mapping[str, Any],
    protected_corrupted: bool,
    evidence_degraded: bool,
    deterministic: bool,
) -> str:
    conditions = {
        "BROKEN_HOP_STILL_PRESENT": bool(construction.get("broken_hop_present")),
        "FABRICATED_IMAGE_WORKLOAD_PROVENANCE": int(fabrication.get("count", 0)) > 0,
        "SOURCE_CAUSE_FALSELY_SUPPORTED": source_supported,
        "UNSAFE_SOURCE_SPECIFICITY_PRESERVED": int(unsafe.get("count", 0)) > 0,
        "VALID_PRESERVED_EVIDENCE_CORRUPTED": protected_corrupted,
        "EVIDENCE_SEMANTICS_DEGRADED": evidence_degraded,
        "NONDETERMINISTIC_RESULT": not deterministic,
        "NO_DIVERGENCE": True,
    }
    return next(value for value in FIRST_DIVERGENCE_ORDER if conditions[value])


def _artifact_hashes(output_root: Path) -> dict[str, str]:
    return {
        path.relative_to(output_root).as_posix(): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file() and path.name not in {"artifact-hashes.json", "artifact-integrity-v1.json"}
    }


def _assert_no_sqlite_transients(root: Path) -> list[str]:
    values = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(("-wal", "-shm", "-journal"))
    )
    if values:
        raise RuntimeError("SQLite transient files remain: " + ", ".join(values))
    return values


def _assert_result_root_available(output_root: Path) -> None:
    if not output_root.exists():
        return
    eai = output_root / "artifact-integrity-v1.json"
    aggregate = output_root / "aggregate.json"
    if eai.exists() and aggregate.exists():
        raise FileExistsError(f"Refusing to overwrite finalized B3 result root: {output_root}")
    raise FileExistsError(f"Refusing to overwrite existing B3 result root: {output_root}")


def run_measurement(
    *,
    seed_db: Path = DEFAULT_SEED_DB,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    seed_db = seed_db.resolve()
    output_root = output_root.resolve()
    _assert_result_root_available(output_root)
    seed_receipt = validate_seed_database(seed_db, expected_sha256=EXPECTED_SEED_SHA256)
    schema = verify_contract_schema(seed_db)
    seed_inventory = schema["inventory"]
    classification = authority_classification(seed_inventory)
    output_root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "scenario_version": SCENARIO_VERSION,
        "scenario": "LINEAGE-2B.3 — Missing Immutable Image -> Affected Workload Provenance",
        "accepted_main_commit": ACCEPTED_MAIN_COMMIT,
        "seed": seed_receipt,
        "matrix": {"control": 1, "b3_repetitions": 3},
        "offline": True,
        "product_entrypoint": "backend.app.services.causal_rca.analyze_causal_rca",
        "product_code_modified": False,
        "product_hints": False,
        "volatile_fields_normalized": list(VOLATILE_FIELDS_NORMALIZED),
        "snapshot_identity": schema["snapshot_identity"],
        "eai_contract": EVALUATION_ARTIFACT_INTEGRITY_VERSION,
    }
    write_json(output_root / "manifest.json", manifest)
    write_json(output_root / "authority-classification.json", classification)

    with tempfile.TemporaryDirectory(prefix="topo-lineage-2b3-") as temporary:
        temporary_root = Path(temporary)
        copies = {
            "control": temporary_root / "control.db",
            "repeat-1": temporary_root / "b3-repeat-1.db",
            "repeat-2": temporary_root / "b3-repeat-2.db",
            "repeat-3": temporary_root / "b3-repeat-3.db",
        }
        copy_receipts = {name: copy_seed_database(seed_db, path) for name, path in copies.items()}
        resets = {name: reset_derived_analysis(path) for name, path in copies.items()}
        reset_hashes = {name: _semantic_sha256(value) for name, value in resets.items()}
        reset_symmetry = len(set(reset_hashes.values())) == 1

        control_inventory = inspect_database(copies["control"], read_only=False)
        control_precondition = validate_control_precondition(control_inventory)
        write_json(output_root / "control/scenario-input.json", {"copy": copy_receipts["control"], "mutation": None, "product_hints": False})
        write_json(output_root / "control/precondition-audit.json", control_precondition)
        write_json(output_root / "control/reset-audit.json", resets["control"])
        control_analysis = None
        control_diagnostics = None
        control_execution = None
        control_reproduced = False
        if control_precondition["valid"] and reset_symmetry:
            control_analysis, control_execution = run_fresh_analysis(copies["control"])
            control_diagnostics = analysis_diagnostics(copies["control"], control_analysis)
            control_reproduced = bool(
                control_diagnostics["exact_path_b_admitted"]
                and control_diagnostics["source_supported"]
                and control_diagnostics["most_specific_supported_semantic_level"] == "INITIATING_MUTATION"
            )
            write_json(output_root / "control/analysis.json", control_analysis)
            write_json(output_root / "control/diagnostics.json", control_diagnostics)
        control_grade = {
            "precondition_valid": control_precondition["valid"],
            "reset_symmetry": reset_symmetry,
            "fresh_execution": control_execution,
            "golden_reproduction": control_reproduced,
            "old_analysis_reused": bool(control_execution and control_execution["original_persisted_record_reused"]),
            "result": "PASS" if control_reproduced else "FAIL",
        }
        write_json(output_root / "control/grade.json", control_grade)

        repeats: list[dict[str, Any]] = []
        for number in range(1, 4):
            name = f"repeat-{number}"
            database_path = copies[name]
            before = inspect_database(database_path, read_only=False)
            pre_inventory = pre_mutation_image_inventory(before)
            pre_scan = recursive_coreference_scan(before)
            mutation = apply_b3_mutation(database_path)
            after = inspect_database(database_path, read_only=False)
            construction = validate_b3_construction(after)
            if construction["valid"]:
                analysis, execution = run_fresh_analysis(database_path)
                diagnostics = analysis_diagnostics(database_path, analysis)
                fabrication = fabrication_scan(analysis)
                unsafe = unsafe_specificity_scan(analysis)
                semantics = evidence_semantics_audit(analysis)
            else:
                analysis = None
                execution = None
                diagnostics = {"analysis_id": None, "source_supported": False, "most_specific_supported_semantic_level": None}
                fabrication = {"count": 0, "surfaces": []}
                unsafe = {"count": 0, "surfaces": []}
                semantics = {"degraded": False, "violations": [], "ledger_count": 0, "no_candidate_specific_ledger": True, "missing_is_not_contradiction": True}
            normalized = normalized_semantic_output(
                construction=construction,
                mutation=mutation,
                diagnostics=diagnostics,
                fabrication=fabrication,
                unsafe=unsafe,
                evidence_semantics=semantics,
            )
            repeats.append({
                "repeat": number,
                "copy": copy_receipts[name],
                "reset": resets[name],
                "pre_inventory": pre_inventory,
                "pre_scan": pre_scan,
                "mutation": mutation,
                "construction": construction,
                "analysis": analysis,
                "execution": execution,
                "diagnostics": diagnostics,
                "fabrication": fabrication,
                "unsafe_specificity": unsafe,
                "evidence_semantics": semantics,
                "protected_corrupted": bool(mutation["protected_fingerprints"]["changed"]),
                "normalized": normalized,
                "semantic_sha256": _semantic_sha256(normalized),
            })

    hashes = [value["semantic_sha256"] for value in repeats]
    deterministic = len(set(hashes)) == 1
    for value in repeats:
        value["taxonomy_result"] = grade_taxonomy(
            construction=value["construction"],
            fabrication=value["fabrication"],
            source_supported=bool(value["diagnostics"].get("source_supported")),
            unsafe=value["unsafe_specificity"],
            protected_corrupted=value["protected_corrupted"],
            evidence_degraded=bool(value["evidence_semantics"].get("degraded")),
            deterministic=deterministic,
        )
    first = repeats[0]
    taxonomy = first["taxonomy_result"]
    all_constructed = all(value["construction"]["valid"] for value in repeats)
    if not control_reproduced or not reset_symmetry or not all_constructed:
        verdict = "INCONCLUSIVE"
    elif taxonomy == "NO_DIVERGENCE":
        verdict = "ROBUST_IN_MEASURED_MATRIX"
    else:
        verdict = "ADVERSARIAL_DIVERGENCE_FOUND"

    write_json(output_root / "b3/pre-mutation-image-inventory.json", first["pre_inventory"])
    write_json(output_root / "b3/mutation-plan.json", {
        "remove_observations": classification["removed_authoritative_observations"],
        "remove_derived_claims": classification["removed_derived_claims"],
        "preserve_source_build": classification["protected_source_build_authority"],
        "preserve_runtime": classification["protected_runtime_authority"],
        "replacement_authority": False,
    })
    write_json(output_root / "b3/mutation-audit.json", {key: value for key, value in first["mutation"].items() if key != "post_inventory"})
    write_json(output_root / "b3/recursive-coreference-audit.json", {
        "before": first["pre_scan"],
        "after": first["construction"]["recursive_coreference"],
        "alternative_authority": first["construction"]["alternative_authority"],
    })
    write_json(output_root / "b3/snapshot-consistency-audit.json", {
        "snapshot_identity": schema["snapshot_identity"],
        "counter_changes": first["mutation"]["counter_changes"],
        "counts_consistent": first["construction"]["snapshot_counts_consistent"],
        "pinned_snapshot_unchanged": first["mutation"]["snapshot_id_before"] == first["mutation"]["snapshot_id_after"] == GOLDEN_SNAPSHOT_ID,
    })
    write_json(output_root / "b3/protected-evidence.json", first["mutation"]["protected_fingerprints"])
    write_json(output_root / "b3/construction-proof.json", first["construction"])
    if first["analysis"] is not None:
        write_json(output_root / "b3/analysis.json", first["analysis"])
    write_json(output_root / "b3/diagnostics.json", first["diagnostics"])
    write_json(output_root / "b3/grade.json", {
        "scenario_valid": first["construction"]["valid"],
        "taxonomy_result": taxonomy,
        "overall_verdict": verdict,
        "fabrication": first["fabrication"],
        "unsafe_specificity": first["unsafe_specificity"],
        "protected_corrupted": first["protected_corrupted"],
        "evidence_semantics": first["evidence_semantics"],
    })
    for value in repeats:
        write_json(output_root / f"determinism/repeat-{value['repeat']}.json", {
            key: item for key, item in value.items() if key not in {"analysis", "normalized", "mutation", "pre_inventory", "pre_scan"}
        })
    write_json(output_root / "determinism/normalized-hashes.json", {
        "volatile_fields_normalized": list(VOLATILE_FIELDS_NORMALIZED),
        "hashes": hashes,
        "identical": deterministic,
        "repetitions": 3,
    })
    seed_after = validate_seed_database(seed_db, expected_sha256=EXPECTED_SEED_SHA256)
    aggregate = {
        "scenario_version": SCENARIO_VERSION,
        "control_reproduction": control_reproduced,
        "reset_symmetry": reset_symmetry,
        "construction_valid_repetitions": sum(value["construction"]["valid"] for value in repeats),
        "determinism": {"identical": deterministic, "hashes": hashes},
        "taxonomy_result": taxonomy,
        "first_divergence": taxonomy,
        "overall_verdict": verdict,
        "source_specificity_reduced_safely": bool(taxonomy == "NO_DIVERGENCE" and not first["diagnostics"].get("source_supported")),
        "preserved_truth": first["construction"]["required_present"],
        "fabricated_image_workload_count": first["fabrication"]["count"],
        "unsafe_source_specificity_count": first["unsafe_specificity"]["count"],
        "product_policy_changes": [],
        "seed_post_run": seed_after,
    }
    write_json(output_root / "aggregate.json", aggregate)
    artifact_hashes = _artifact_hashes(output_root)
    write_json(output_root / "artifact-hashes.json", artifact_hashes)
    transient_files = _assert_no_sqlite_transients(output_root)
    integrity_manifest = write_integrity_manifest(output_root)
    verification = verify_integrity_manifest(output_root)
    return {
        "manifest": manifest,
        "aggregate": aggregate,
        "control": {"copy": copy_receipts["control"], "reset": resets["control"], "analysis": control_analysis, "diagnostics": control_diagnostics, "grade": control_grade},
        "b3_repeats": repeats,
        "artifact_hashes": artifact_hashes,
        "sqlite_transient_files": transient_files,
        "eai": {
            "contract": integrity_manifest["contract"],
            "tree_sha256": integrity_manifest["tree_sha256"],
            "included_file_count": len(integrity_manifest["entries"]),
            "verification": {"status": "verified", "contract": verification.contract, "tree_sha256": verification.tree_sha256, "included_file_count": verification.included_file_count},
            "generated_after_ordinary_artifacts": True,
        },
        "output_root": output_root.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run offline LINEAGE-2B.3 missing Image -> workload experiment.")
    parser.add_argument("--seed-db", type=Path, default=DEFAULT_SEED_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    arguments = parser.parse_args()
    result = run_measurement(seed_db=arguments.seed_db, output_root=arguments.output_root)
    aggregate = result["aggregate"]
    print(f"verdict={aggregate['overall_verdict']}")
    print(f"taxonomy={aggregate['taxonomy_result']}")
    print(f"result_root={result['output_root']}")
    print(f"eai_tree_sha256={result['eai']['tree_sha256']}")
    print(f"eai_included_files={result['eai']['included_file_count']}")
    return 0 if aggregate["overall_verdict"] != "INCONCLUSIVE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
