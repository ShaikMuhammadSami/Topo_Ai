from __future__ import annotations

import argparse
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
from evaluation.lineage_distractor_robustness import (
    copy_seed_database,
    deterministic_json_bytes,
    sha256_file,
    validate_seed_database,
    write_json,
)


SCENARIO_VERSION = "lineage-2b2-missing-run-image-v1"
ACCEPTED_MAIN_COMMIT = "6788ce78f2d4ffdb083b513b09fb8db6e397351c"
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
    / "lineage-2b-missing-run-image"
)

GOLDEN_REPOSITORY_ID = "1278498159"
GOLDEN_REPOSITORY = "ShaikMuhammadSami/Topo_Ai"
GOLDEN_REVISION = "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
GOLDEN_EVENT_ID = "change-event:20a8946c8c445153d85c90ee2166d487"
GOLDEN_MUTATION_ID = (
    "source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633"
)
GOLDEN_RUN_ID = "32695735269"
GOLDEN_RUN_ATTEMPT = 1
GOLDEN_IMAGE_DIGEST = (
    "sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed"
)
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
GOLDEN_AFFECTED_ENTITY_ID = (
    "k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168"
)

E1_ID = "build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb"
OLD_ANALYSIS_ID = "causal-analysis:76c9b683e95e2f2fd599677122f2ebae"
RUN_ENTITY_ID = "github:api.github.com:workflow-run:32695735269"
COMMIT_ENTITY_ID = (
    "github:api.github.com:repository:1278498159:commit:"
    "4149b194c4c4fdfdcd402a157c5336ad59dfdbbe"
)
IMAGE_ENTITY_ID = f"artifact:container-image:{GOLDEN_IMAGE_DIGEST}"
DEPLOYMENT_ENTITY_ID = (
    "k8s:docker-desktop:deployment:bd4cfb7a-d32a-43bf-bf82-366e3fd8841a"
)
REPLICASET_ENTITY_ID = (
    "k8s:docker-desktop:replicaset:200703db-a601-44f0-90ff-63c64cb17162"
)
POD_ENTITY_ID = GOLDEN_AFFECTED_ENTITY_ID

RUN_IMAGE_RELATIONSHIP_ID = "rel:63f5cd5dfce59d148ae5"
RUN_IMAGE_EVIDENCE_ID = "evidence:github-actions-build:c9b6d53cf66facfb444c8ae0"
COMMIT_RUN_RELATIONSHIP_ID = "rel:ebaedc357f11b3e70170"
COMMIT_RUN_EVIDENCE_ID = "evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b"
DEPLOYMENT_IMAGE_RELATIONSHIP_ID = "rel:496906e3e345259910c9"
POD_IMAGE_RELATIONSHIP_ID = "rel:0548ac3e949f44b3569c"
DEPLOYMENT_REPLICASET_RELATIONSHIP_ID = "rel:57555e411f2db29864c2"
REPLICASET_POD_RELATIONSHIP_ID = "rel:9c8db862d53bac71327f"
CONTAINER_IMAGE_EVIDENCE_ID = "evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56"

FIRST_DIVERGENCE_ORDER = (
    "BROKEN_HOP_STILL_PRESENT",
    "FABRICATED_RUN_IMAGE_PROVENANCE",
    "SOURCE_CAUSE_FALSELY_SUPPORTED",
    "UNSAFE_SOURCE_SPECIFICITY_PRESERVED",
    "VALID_PRESERVED_EVIDENCE_CORRUPTED",
    "EVIDENCE_SEMANTICS_DEGRADED",
    "NONDETERMINISTIC_RESULT",
    "NO_DIVERGENCE",
)
VOLATILE_ANALYSIS_FIELDS = ("generated_at",)


class ContractImplementationContradiction(RuntimeError):
    pass


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


def _row(connection: sqlite3.Connection, statement: str, values: tuple[Any, ...]) -> dict[str, Any] | None:
    result = connection.execute(statement, values).fetchone()
    return dict(result) if result is not None else None


def _rows(connection: sqlite3.Connection, statement: str, values: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(item) for item in connection.execute(statement, values).fetchall()]


def _load_snapshot(connection: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any]]:
    record = _row(
        connection,
        "SELECT * FROM topology_snapshots WHERE snapshot_id = ?",
        (GOLDEN_SNAPSHOT_ID,),
    )
    if record is None:
        raise ContractImplementationContradiction("The frozen incident snapshot is absent.")
    payload = json.loads(str(record["payload_json"]))
    if not isinstance(payload, dict):
        raise ContractImplementationContradiction("The snapshot payload is not a JSON object.")
    return record, payload


def _item_by_id(values: Iterable[Mapping[str, Any]], item_id: str) -> dict[str, Any] | None:
    matches = [dict(item) for item in values if str(item.get("id")) == item_id]
    if len(matches) > 1:
        raise ContractImplementationContradiction(f"Duplicate persisted ID: {item_id}")
    return matches[0] if matches else None


def _source_mutation(event: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if event is None:
        return None
    metadata = json.loads(str(event["metadata_json"]))
    mutations = metadata.get("source_file_mutations", [])
    matches = [
        dict(item)
        for item in mutations
        if isinstance(item, dict) and item.get("mutation_id") == GOLDEN_MUTATION_ID
    ]
    return matches[0] if len(matches) == 1 else None


def _semantic_sha256(value: Any) -> str:
    return hashlib.sha256(deterministic_json_bytes(value)).hexdigest()


def _selected_signal_material(signal: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if signal is None:
        return None
    return {
        "signal_id": signal["signal_id"],
        "reason": signal["reason"],
        "first_observed_at": signal["first_observed_at"],
        "last_observed_at": signal["last_observed_at"],
        "involved_entity_id": signal["involved_entity_id"],
        "involved_object_uid": signal["involved_object_uid"],
        "payload": json.loads(str(signal["payload_json"])),
    }


def _selected_incident_material(incident: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if incident is None:
        return None
    return {
        "incident_id": incident["incident_id"],
        "primary_signal_id": incident["primary_signal_id"],
        "topology_snapshot_id": incident["topology_snapshot_id"],
        "affected_entity_id": incident["affected_entity_id"],
        "affected_object_kind": incident["affected_object_kind"],
        "affected_object_name": incident["affected_object_name"],
        "first_observed_at": incident["first_observed_at"],
        "last_observed_at": incident["last_observed_at"],
    }


def inspect_database(database_path: Path, *, read_only: bool = True) -> dict[str, Any]:
    connection = _connect(database_path, read_only=read_only)
    try:
        snapshot_record, payload = _load_snapshot(connection)
        entities = payload.get("entities", [])
        relationships = payload.get("relationships", [])
        evidence = payload.get("evidence", [])
        metadata = payload.get("metadata", {})
        if not all(isinstance(value, list) for value in (entities, relationships, evidence)):
            raise ContractImplementationContradiction("Snapshot graph collections are not lists.")
        if not isinstance(metadata, dict):
            raise ContractImplementationContradiction("Snapshot metadata is not an object.")

        entity_by_id = {
            str(item.get("id")): dict(item)
            for item in entities
            if isinstance(item, dict) and item.get("id")
        }
        relationship_by_id = {
            str(item.get("id")): dict(item)
            for item in relationships
            if isinstance(item, dict) and item.get("id")
        }
        evidence_by_id = {
            str(item.get("id")): dict(item)
            for item in evidence
            if isinstance(item, dict) and item.get("id")
        }
        event = _row(
            connection,
            "SELECT * FROM change_events WHERE event_id = ?",
            (GOLDEN_EVENT_ID,),
        )
        mutation = _source_mutation(event)
        incident = _row(
            connection,
            "SELECT * FROM incidents WHERE incident_id = ?",
            (GOLDEN_INCIDENT_ID,),
        )
        signal = _row(
            connection,
            "SELECT * FROM signals WHERE signal_id = ?",
            (GOLDEN_SIGNAL_ID,),
        )
        e1_rows = _rows(
            connection,
            "SELECT * FROM build_artifact_evidence WHERE evidence_id = ?",
            (E1_ID,),
        )
        exact_provider_rows = _rows(
            connection,
            """
            SELECT evidence_id, workflow_run_id, run_attempt, image_digest
            FROM build_artifact_evidence
            WHERE workflow_run_id = ? AND run_attempt = ? AND image_digest = ?
            ORDER BY evidence_id
            """,
            (GOLDEN_RUN_ID, GOLDEN_RUN_ATTEMPT, GOLDEN_IMAGE_DIGEST),
        )
        analyses = _rows(
            connection,
            "SELECT analysis_id FROM causal_analyses WHERE incident_id = ? ORDER BY analysis_id",
            (GOLDEN_INCIDENT_ID,),
        )
        legacy_analyses = _rows(
            connection,
            """
            SELECT analysis_id FROM incident_analyses
            WHERE signal_id = ? AND topology_snapshot_id = ? ORDER BY analysis_id
            """,
            (GOLDEN_SIGNAL_ID, GOLDEN_SNAPSHOT_ID),
        )
        run_image_relationships = sorted(
            str(item.get("id"))
            for item in relationships
            if isinstance(item, dict)
            and item.get("relationship_type") == "produces"
            and item.get("source_entity_id") == RUN_ENTITY_ID
            and item.get("target_entity_id") == IMAGE_ENTITY_ID
        )
        run_image_evidence = sorted(
            str(item.get("id"))
            for item in evidence
            if isinstance(item, dict)
            and isinstance(item.get("payload"), dict)
            and str(item["payload"].get("run_id")) == GOLDEN_RUN_ID
            and item["payload"].get("image_digest") == GOLDEN_IMAGE_DIGEST
        )
        build_metadata = metadata.get("github_actions_build_artifact_lineage")
        build_metadata_active = bool(
            isinstance(build_metadata, dict)
            and any(
                int(build_metadata.get(key, 0) or 0) > 0
                for key in (
                    "evidence_records_considered",
                    "relationship_count",
                    "unresolved_evidence_count",
                )
            )
        )
        run_entity = entity_by_id.get(RUN_ENTITY_ID)
        commit_run = relationship_by_id.get(COMMIT_RUN_RELATIONSHIP_ID)
        commit_run_evidence = evidence_by_id.get(COMMIT_RUN_EVIDENCE_ID)
        image_entity = entity_by_id.get(IMAGE_ENTITY_ID)
        deployment_image = relationship_by_id.get(DEPLOYMENT_IMAGE_RELATIONSHIP_ID)
        pod_image = relationship_by_id.get(POD_IMAGE_RELATIONSHIP_ID)
        deployment_replicaset = relationship_by_id.get(
            DEPLOYMENT_REPLICASET_RELATIONSHIP_ID
        )
        replicaset_pod = relationship_by_id.get(REPLICASET_POD_RELATIONSHIP_ID)

        present = {
            "source_revision": bool(event and event.get("commit_sha") == GOLDEN_REVISION),
            "source_mutation": mutation is not None,
            "run_entity": run_entity is not None,
            "run_head_sha": bool(
                run_entity
                and isinstance(run_entity.get("properties"), dict)
                and run_entity["properties"].get("head_sha") == GOLDEN_REVISION
            ),
            "commit_run_relationship": bool(
                commit_run
                and commit_run.get("source_entity_id") == COMMIT_ENTITY_ID
                and commit_run.get("target_entity_id") == RUN_ENTITY_ID
                and commit_run.get("relationship_type") == "triggers"
            ),
            "commit_run_evidence": bool(
                commit_run_evidence
                and COMMIT_RUN_RELATIONSHIP_ID
                in commit_run_evidence.get("related_relationship_ids", [])
            ),
            "container_image": image_entity is not None,
            "deployment": DEPLOYMENT_ENTITY_ID in entity_by_id,
            "replicaset": REPLICASET_ENTITY_ID in entity_by_id,
            "pod": POD_ENTITY_ID in entity_by_id,
            "deployment_image": bool(
                deployment_image
                and deployment_image.get("source_entity_id") == DEPLOYMENT_ENTITY_ID
                and deployment_image.get("target_entity_id") == IMAGE_ENTITY_ID
                and deployment_image.get("relationship_type") == "uses"
            ),
            "pod_image": bool(
                pod_image
                and pod_image.get("source_entity_id") == POD_ENTITY_ID
                and pod_image.get("target_entity_id") == IMAGE_ENTITY_ID
                and pod_image.get("relationship_type") == "uses"
            ),
            "deployment_replicaset_owner": bool(
                deployment_replicaset
                and deployment_replicaset.get("source_entity_id") == DEPLOYMENT_ENTITY_ID
                and deployment_replicaset.get("target_entity_id") == REPLICASET_ENTITY_ID
            ),
            "replicaset_pod_owner": bool(
                replicaset_pod
                and replicaset_pod.get("source_entity_id") == REPLICASET_ENTITY_ID
                and replicaset_pod.get("target_entity_id") == POD_ENTITY_ID
            ),
            "runtime_failure": bool(
                signal
                and signal.get("reason") == "BackOff"
                and signal.get("involved_entity_id") == POD_ENTITY_ID
            ),
            "incident": incident is not None,
            "incident_boundary": bool(
                incident and incident.get("first_observed_at") == GOLDEN_INCIDENT_BOUNDARY
            ),
            "topology_pin": bool(
                incident and incident.get("topology_snapshot_id") == GOLDEN_SNAPSHOT_ID
            ),
            "affected_entity": bool(
                incident and incident.get("affected_entity_id") == POD_ENTITY_ID
            ),
        }
        absent = {
            "e1": len(e1_rows) == 0,
            "run_image_relationship": len(run_image_relationships) == 0,
            "run_image_evidence": len(run_image_evidence) == 0,
            "active_build_lineage_metadata": not build_metadata_active,
            "exact_provider_association": len(exact_provider_rows) == 0,
            "stale_causal_analysis": len(analyses) == 0,
            "stale_legacy_analysis": len(legacy_analyses) == 0,
        }
        return {
            "database_sha256": sha256_file(database_path),
            "snapshot_id": snapshot_record["snapshot_id"],
            "snapshot_counts": {
                "record": {
                    "entities": snapshot_record["entity_count"],
                    "relationships": snapshot_record["relationship_count"],
                    "evidence": snapshot_record["evidence_count"],
                },
                "payload": {
                    "entities": len(entities),
                    "relationships": len(relationships),
                    "evidence": len(evidence),
                },
            },
            "present": present,
            "absent": absent,
            "e1_count": len(e1_rows),
            "e1": e1_rows[0] if len(e1_rows) == 1 else None,
            "exact_provider_associations": exact_provider_rows,
            "run_image_relationship_ids": run_image_relationships,
            "run_image_evidence_ids": run_image_evidence,
            "build_lineage_metadata": build_metadata,
            "causal_analysis_ids": [item["analysis_id"] for item in analyses],
            "legacy_analysis_ids": [item["analysis_id"] for item in legacy_analyses],
            "incident_analysis_cache": {
                "latest_analysis_id": incident.get("latest_analysis_id") if incident else None,
                "top_hypothesis_title": incident.get("top_hypothesis_title") if incident else None,
                "top_hypothesis_score": incident.get("top_hypothesis_score") if incident else None,
            },
            "authority_material": {
                "source_event": event,
                "source_mutation": mutation,
                "run_entity": run_entity,
                "commit_run_relationship": commit_run,
                "commit_run_evidence": commit_run_evidence,
                "image_entity": image_entity,
                "deployment_entity": entity_by_id.get(DEPLOYMENT_ENTITY_ID),
                "replicaset_entity": entity_by_id.get(REPLICASET_ENTITY_ID),
                "pod_entity": entity_by_id.get(POD_ENTITY_ID),
                "deployment_image_relationship": deployment_image,
                "pod_image_relationship": pod_image,
                "container_image_evidence": evidence_by_id.get(CONTAINER_IMAGE_EVIDENCE_ID),
                "deployment_replicaset_relationship": deployment_replicaset,
                "replicaset_pod_relationship": replicaset_pod,
                "signal": _selected_signal_material(signal),
                "incident": _selected_incident_material(incident),
            },
        }
    finally:
        connection.close()


def authority_classification(inventory: Mapping[str, Any]) -> dict[str, Any]:
    material = inventory["authority_material"]
    return {
        "authoritative_preserved": {
            "repository_and_source_revision": GOLDEN_REVISION,
            "source_mutation": GOLDEN_MUTATION_ID,
            "workflow_run_entity": RUN_ENTITY_ID,
            "workflow_run_head_sha": GOLDEN_REVISION,
            "commit_run_relationship": COMMIT_RUN_RELATIONSHIP_ID,
            "commit_run_evidence": COMMIT_RUN_EVIDENCE_ID,
            "container_image": IMAGE_ENTITY_ID,
            "deployment": DEPLOYMENT_ENTITY_ID,
            "replicaset": REPLICASET_ENTITY_ID,
            "pod": POD_ENTITY_ID,
            "deployment_image_relationship": DEPLOYMENT_IMAGE_RELATIONSHIP_ID,
            "pod_image_relationship": POD_IMAGE_RELATIONSHIP_ID,
            "owner_relationships": [
                DEPLOYMENT_REPLICASET_RELATIONSHIP_ID,
                REPLICASET_POD_RELATIONSHIP_ID,
            ],
            "runtime_failure_signal": GOLDEN_SIGNAL_ID,
            "incident": GOLDEN_INCIDENT_ID,
            "topology_pin": GOLDEN_SNAPSHOT_ID,
        },
        "authoritative_removed_for_b2": {"build_artifact_evidence": E1_ID},
        "derived_removed_for_b2": {
            "run_image_relationship": RUN_IMAGE_RELATIONSHIP_ID,
            "run_image_evidence": RUN_IMAGE_EVIDENCE_ID,
            "build_lineage_metadata": "metadata.github_actions_build_artifact_lineage",
            "exact_digest_provider_association": "BuildArtifactEvidence exact-digest lookup",
            "causal_analysis_ids": list(inventory["causal_analysis_ids"]),
            "incident_analysis_cache": dict(inventory["incident_analysis_cache"]),
        },
        "classification_source": "persisted seed schema and provider ownership",
        "synthetic_authority": False,
        "material_present": {key: value is not None for key, value in material.items()},
    }


def protected_evidence_fingerprints(inventory: Mapping[str, Any]) -> dict[str, str]:
    material = inventory["authority_material"]
    groups = {
        "commit_run_provider_truth": {
            "run": material["run_entity"],
            "relationship": material["commit_run_relationship"],
            "evidence": material["commit_run_evidence"],
        },
        "image_workload_truth": {
            "image": material["image_entity"],
            "deployment": material["deployment_entity"],
            "pod": material["pod_entity"],
            "deployment_image": material["deployment_image_relationship"],
            "pod_image": material["pod_image_relationship"],
            "evidence": material["container_image_evidence"],
        },
        "runtime_failure": material["signal"],
        "incident_and_topology_pin": material["incident"],
        "owner_chain": {
            "deployment": DEPLOYMENT_ENTITY_ID,
            "replicaset": material["replicaset_entity"],
            "pod": POD_ENTITY_ID,
            "deployment_replicaset": material["deployment_replicaset_relationship"],
            "replicaset_pod": material["replicaset_pod_relationship"],
        },
        "source_mutation_identity": {
            "event": material["source_event"],
            "mutation": material["source_mutation"],
        },
        "container_image_identity": material["image_entity"],
    }
    return {name: _semantic_sha256(value) for name, value in sorted(groups.items())}


def verify_contract_schema(seed_db: Path) -> dict[str, Any]:
    inventory = inspect_database(seed_db, read_only=True)
    required_present = inventory["present"]
    expected_pre_cut = {
        "e1": inventory["e1_count"] == 1,
        "run_image_relationship": inventory["run_image_relationship_ids"]
        == [RUN_IMAGE_RELATIONSHIP_ID],
        "run_image_evidence": inventory["run_image_evidence_ids"]
        == [RUN_IMAGE_EVIDENCE_ID],
        "build_lineage_metadata": inventory["build_lineage_metadata"]
        == {
            "evidence_records_considered": 1,
            "relationship_count": 1,
            "unresolved_evidence_count": 0,
        },
        "old_analysis": OLD_ANALYSIS_ID in inventory["causal_analysis_ids"],
        "snapshot_counts_match": inventory["snapshot_counts"]["record"]
        == inventory["snapshot_counts"]["payload"],
    }
    failures = sorted(
        key
        for key, value in {**required_present, **expected_pre_cut}.items()
        if not value
    )
    if failures:
        raise ContractImplementationContradiction(
            "Current schema contradicts the frozen B2 contract: " + ", ".join(failures)
        )
    return {
        "status": "compatible",
        "required_present": required_present,
        "expected_pre_cut": expected_pre_cut,
        "inventory": inventory,
    }


def reset_derived_analysis(database_path: Path) -> dict[str, Any]:
    connection = _connect(database_path)
    try:
        incident = _row(
            connection,
            "SELECT * FROM incidents WHERE incident_id = ?",
            (GOLDEN_INCIDENT_ID,),
        )
        if incident is None:
            raise ContractImplementationContradiction("Incident is absent before reset.")
        causal_ids = [
            item["analysis_id"]
            for item in _rows(
                connection,
                "SELECT analysis_id FROM causal_analyses WHERE incident_id = ? ORDER BY analysis_id",
                (GOLDEN_INCIDENT_ID,),
            )
        ]
        legacy_ids = [
            item["analysis_id"]
            for item in _rows(
                connection,
                """
                SELECT analysis_id FROM incident_analyses
                WHERE signal_id = ? AND topology_snapshot_id = ? ORDER BY analysis_id
                """,
                (GOLDEN_SIGNAL_ID, GOLDEN_SNAPSHOT_ID),
            )
        ]
        before_cache = {
            "latest_analysis_id": incident["latest_analysis_id"],
            "top_hypothesis_title": incident["top_hypothesis_title"],
            "top_hypothesis_score": incident["top_hypothesis_score"],
        }
        with connection:
            deleted_causal = connection.execute(
                "DELETE FROM causal_analyses WHERE incident_id = ?",
                (GOLDEN_INCIDENT_ID,),
            ).rowcount
            deleted_legacy = connection.execute(
                """
                DELETE FROM incident_analyses
                WHERE signal_id = ? AND topology_snapshot_id = ?
                """,
                (GOLDEN_SIGNAL_ID, GOLDEN_SNAPSHOT_ID),
            ).rowcount
            connection.execute(
                """
                UPDATE incidents
                SET latest_analysis_id = NULL,
                    top_hypothesis_title = NULL,
                    top_hypothesis_score = NULL
                WHERE incident_id = ?
                """,
                (GOLDEN_INCIDENT_ID,),
            )
        after = _row(
            connection,
            """
            SELECT latest_analysis_id, top_hypothesis_title, top_hypothesis_score
            FROM incidents WHERE incident_id = ?
            """,
            (GOLDEN_INCIDENT_ID,),
        )
        remaining = int(
            connection.execute(
                "SELECT COUNT(*) FROM causal_analyses WHERE incident_id = ?",
                (GOLDEN_INCIDENT_ID,),
            ).fetchone()[0]
        )
        return {
            "mechanism": "evaluation-only isolated-copy SQL reset",
            "product_force_recompute_available": False,
            "original_causal_analysis_ids": causal_ids,
            "original_legacy_analysis_ids": legacy_ids,
            "deleted_causal_analysis_count": deleted_causal,
            "deleted_legacy_analysis_count": deleted_legacy,
            "incident_cache_before": before_cache,
            "incident_cache_after": after,
            "remaining_causal_analysis_count": remaining,
            "authoritative_evidence_deleted": False,
            "fresh_analysis_eligible": bool(
                remaining == 0
                and after
                and all(value is None for value in after.values())
            ),
        }
    finally:
        connection.close()


def apply_b2_mutation(database_path: Path) -> dict[str, Any]:
    before = inspect_database(database_path, read_only=False)
    fingerprints_before = protected_evidence_fingerprints(before)
    connection = _connect(database_path)
    try:
        snapshot_record, payload = _load_snapshot(connection)
        relationships = list(payload.get("relationships", []))
        evidence = list(payload.get("evidence", []))
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ContractImplementationContradiction("Snapshot metadata is not mutable JSON.")
        build_metadata = metadata.get("github_actions_build_artifact_lineage")
        if build_metadata != {
            "evidence_records_considered": 1,
            "relationship_count": 1,
            "unresolved_evidence_count": 0,
        }:
            raise ContractImplementationContradiction(
                "Build-lineage metadata no longer matches the frozen B2 schema."
            )
        relationship_matches = [
            item for item in relationships if item.get("id") == RUN_IMAGE_RELATIONSHIP_ID
        ]
        evidence_matches = [
            item for item in evidence if item.get("id") == RUN_IMAGE_EVIDENCE_ID
        ]
        if len(relationship_matches) != 1 or len(evidence_matches) != 1:
            raise ContractImplementationContradiction(
                "The exact Run -> Image derived surfaces are not singleton records."
            )
        payload["relationships"] = [
            item for item in relationships if item.get("id") != RUN_IMAGE_RELATIONSHIP_ID
        ]
        payload["evidence"] = [
            item for item in evidence if item.get("id") != RUN_IMAGE_EVIDENCE_ID
        ]
        metadata["github_actions_build_artifact_lineage"] = {
            "evidence_records_considered": 0,
            "relationship_count": 0,
            "unresolved_evidence_count": 0,
        }

        from evaluation.lineage_distractor_robustness import _ensure_backend_import_path

        _ensure_backend_import_path()
        from app.models.topology import GraphSnapshot

        validated = GraphSnapshot.model_validate(payload)
        validated_payload = validated.model_dump(mode="json")
        serialized = json.dumps(
            validated_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        with connection:
            deleted_e1 = connection.execute(
                "DELETE FROM build_artifact_evidence WHERE evidence_id = ?",
                (E1_ID,),
            ).rowcount
            if deleted_e1 != 1:
                raise ContractImplementationContradiction(
                    "E1 was not exactly one authoritative row at mutation time."
                )
            connection.execute(
                """
                UPDATE topology_snapshots
                SET relationship_count = ?, evidence_count = ?, payload_json = ?
                WHERE snapshot_id = ?
                """,
                (
                    len(validated.relationships),
                    len(validated.evidence),
                    serialized,
                    GOLDEN_SNAPSHOT_ID,
                ),
            )
    finally:
        connection.close()

    after = inspect_database(database_path, read_only=False)
    fingerprints_after = protected_evidence_fingerprints(after)
    changed = sorted(
        name
        for name in fingerprints_before
        if fingerprints_before[name] != fingerprints_after.get(name)
    )
    if changed:
        raise ExperimentConstructionBlocked(
            "counterfactual_would_corrupt_preserved_truth: " + ", ".join(changed)
        )
    return {
        "authoritative_cut": {"deleted_build_artifact_evidence": [E1_ID]},
        "derived_cut": {
            "deleted_relationships": [RUN_IMAGE_RELATIONSHIP_ID],
            "deleted_evidence": [RUN_IMAGE_EVIDENCE_ID],
            "build_lineage_metadata_before": before["build_lineage_metadata"],
            "build_lineage_metadata_after": after["build_lineage_metadata"],
            "exact_provider_associations_before": before["exact_provider_associations"],
            "exact_provider_associations_after": after["exact_provider_associations"],
        },
        "protected_fingerprints": {
            "before": fingerprints_before,
            "after": fingerprints_after,
            "changed": changed,
            "unchanged": not changed,
        },
        "before": {
            "e1_count": before["e1_count"],
            "run_image_relationship_ids": before["run_image_relationship_ids"],
            "run_image_evidence_ids": before["run_image_evidence_ids"],
            "build_lineage_metadata": before["build_lineage_metadata"],
        },
        "after": {
            "e1_count": after["e1_count"],
            "run_image_relationship_ids": after["run_image_relationship_ids"],
            "run_image_evidence_ids": after["run_image_evidence_ids"],
            "build_lineage_metadata": after["build_lineage_metadata"],
        },
    }


def validate_control_precondition(inventory: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        **dict(inventory["present"]),
        "e1": inventory["e1_count"] == 1,
        "run_image_relationship": inventory["run_image_relationship_ids"]
        == [RUN_IMAGE_RELATIONSHIP_ID],
        "run_image_evidence": inventory["run_image_evidence_ids"]
        == [RUN_IMAGE_EVIDENCE_ID],
        "exact_provider_association": len(inventory["exact_provider_associations"]) == 1,
        "analysis_reset": not inventory["causal_analysis_ids"],
    }
    return {"valid": all(checks.values()), "checks": checks}


def validate_b2_construction(inventory: Mapping[str, Any]) -> dict[str, Any]:
    required_present = dict(inventory["present"])
    required_absent = dict(inventory["absent"])
    broken_hop_present = not all(
        required_absent[key]
        for key in (
            "e1",
            "run_image_relationship",
            "run_image_evidence",
            "active_build_lineage_metadata",
            "exact_provider_association",
            "stale_causal_analysis",
            "stale_legacy_analysis",
        )
    )
    protected_present = all(required_present.values())
    return {
        "valid": protected_present and not broken_hop_present,
        "required_present": required_present,
        "required_absent": required_absent,
        "broken_hop_present": broken_hop_present,
        "protected_present": protected_present,
        "alternative_authority": {
            "exact_provider_associations": inventory["exact_provider_associations"],
            "run_image_relationship_ids": inventory["run_image_relationship_ids"],
            "run_image_evidence_ids": inventory["run_image_evidence_ids"],
        },
    }


def _scenario_engine(database_path: Path):
    from evaluation.lineage_distractor_robustness import _scenario_engine as engine

    return engine(database_path)


def _ledger_summary(hypothesis: Mapping[str, Any] | None) -> dict[str, Any]:
    ledger = hypothesis.get("evidence_ledger") if hypothesis else None
    if not isinstance(ledger, dict):
        return {
            "present": False,
            "supporting": 0,
            "contradicting": 0,
            "missing": 0,
            "unknown": 0,
            "claim_types": [],
        }
    supporting = list(ledger.get("supporting", []))
    contradicting = list(ledger.get("contradicting", []))
    missing = list(ledger.get("missing", []))
    items = [*supporting, *contradicting, *missing]
    return {
        "present": True,
        "supporting": len(supporting),
        "contradicting": len(contradicting),
        "missing": len(missing),
        "unknown": sum(item.get("quality") == "unknown" for item in items),
        "claim_types": sorted({str(item.get("claim_type")) for item in items}),
        "missing_expectation_bases": sorted(
            str(item.get("expectation_basis"))
            for item in missing
            if item.get("expectation_basis")
        ),
    }


def _supported_hypothesis(analysis: Mapping[str, Any], event_id: str) -> dict[str, Any] | None:
    supported = set(analysis.get("supported_hypothesis_ids", []))
    return next(
        (
            dict(item)
            for item in analysis.get("hypotheses", [])
            if item.get("root_event_id") == event_id
            and (
                item.get("hypothesis_id") in supported
                or (
                    isinstance(item.get("confidence_semantics"), dict)
                    and item["confidence_semantics"].get("evidence_state")
                    == "supported_under_current_model"
                )
            )
        ),
        None,
    )


def analysis_diagnostics(database_path: Path, analysis: Mapping[str, Any]) -> dict[str, Any]:
    selections = list(analysis.get("candidate_selection_audit", []))
    lineage = list(analysis.get("lineage_admission_audit", []))
    relevance = list(analysis.get("candidate_relevance_audit", []))
    hypotheses = list(analysis.get("hypotheses", []))
    selection = next((item for item in selections if item.get("event_id") == GOLDEN_EVENT_ID), None)
    source_lineage = next(
        (item for item in lineage if item.get("canonical_change_id") == GOLDEN_EVENT_ID),
        None,
    )
    incomplete_lineage = next(
        (item for item in lineage if item.get("admission_state") == "incomplete"),
        None,
    )
    source_relevance = next(
        (item for item in relevance if item.get("candidate_event_id") == GOLDEN_EVENT_ID),
        None,
    )
    source_hypothesis = next(
        (item for item in hypotheses if item.get("root_event_id") == GOLDEN_EVENT_ID),
        None,
    )
    supported_source = _supported_hypothesis(analysis, GOLDEN_EVENT_ID)
    hypothesis_by_id = {
        str(item.get("hypothesis_id")): item for item in hypotheses if item.get("hypothesis_id")
    }
    supported_ids = list(analysis.get("supported_hypothesis_ids", []))
    diagnostic_ids = list(analysis.get("diagnostic_hypothesis_ids", []))
    supported_top = hypothesis_by_id.get(supported_ids[0]) if supported_ids else None
    top = analysis.get("top_hypothesis")
    confidence = supported_top.get("confidence_semantics") if supported_top else None
    source_event_present = False
    connection = _connect(database_path, read_only=True)
    try:
        source_event_present = bool(
            connection.execute(
                "SELECT COUNT(*) FROM change_events WHERE event_id = ?",
                (GOLDEN_EVENT_ID,),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    bases = set(selection.get("admission_basis", [])) if selection else set()
    if supported_top is None:
        semantic_level = "NONE"
    elif supported_top.get("root_event_id") == GOLDEN_EVENT_ID:
        semantic_level = "INITIATING_MUTATION"
    else:
        semantic_level = "UNCLASSIFIED_PRODUCT_HYPOTHESIS"
    return {
        "analysis_id": analysis.get("analysis_id"),
        "candidate_count": analysis.get("candidate_count"),
        "hypothesis_count": analysis.get("hypothesis_count"),
        "durable_source_event_present": source_event_present,
        "golden_raw_candidate_discovered": selection is not None,
        "golden_raw_score": selection.get("raw_score") if selection else None,
        "ordinary_path_a_admitted": "temporal" in bases,
        "exact_path_b_admitted": "exact_immutable_lineage" in bases,
        "golden_admission_basis": sorted(bases),
        "sc2": {
            "source_audit": source_lineage,
            "incomplete_audit": incomplete_lineage,
            "all_audits": lineage,
            "status": (
                source_lineage.get("admission_state")
                if source_lineage
                else incomplete_lineage.get("admission_state")
                if incomplete_lineage
                else "not_recorded"
            ),
            "reason": (
                source_lineage.get("admission_reason")
                if source_lineage
                else incomplete_lineage.get("admission_reason")
                if incomplete_lineage
                else None
            ),
        },
        "sc4": {
            "source_relevance": source_relevance,
            "mode": source_relevance.get("resolution_basis") if source_relevance else "not_evaluated",
            "bridge_state": source_relevance.get("bridge_state") if source_relevance else "not_evaluated",
            "anchor": source_relevance.get("relevance_anchor_entity_id") if source_relevance else None,
        },
        "source_hypothesis": source_hypothesis,
        "source_support_gate": source_hypothesis.get("support_gate") if source_hypothesis else None,
        "source_supported": supported_source is not None,
        "source_ledger": _ledger_summary(source_hypothesis),
        "diagnostic_projection": diagnostic_ids,
        "supported_projection": supported_ids,
        "top_hypothesis": top,
        "supported_top1": supported_top,
        "most_specific_supported_semantic_level": semantic_level,
        "final_score": supported_top.get("score") if supported_top else None,
        "confidence": supported_top.get("confidence") if supported_top else None,
        "confidence_semantics": confidence,
        "calibration": confidence.get("calibration_status") if confidence else None,
    }


def run_fresh_analysis(database_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    engine = _scenario_engine(database_path)
    try:
        from sqlalchemy.orm import Session
        from app.models.causal_rca import CausalAnalysisRequest
        from app.services.causal_rca import analyze_causal_rca

        with Session(engine) as session:
            existing_before = bool(
                session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT COUNT(*) FROM causal_analyses WHERE incident_id = :incident_id"
                    ),
                    {"incident_id": GOLDEN_INCIDENT_ID},
                ).scalar_one()
            )
            analysis = analyze_causal_rca(
                session,
                incident_id=GOLDEN_INCIDENT_ID,
                request=CausalAnalysisRequest(),
                persist=True,
            )
            payload = analysis.model_dump(mode="json")
            record_count = int(
                session.execute(
                    __import__("sqlalchemy").text(
                        "SELECT COUNT(*) FROM causal_analyses WHERE analysis_id = :analysis_id"
                    ),
                    {"analysis_id": analysis.analysis_id},
                ).scalar_one()
            )
    finally:
        engine.dispose()
    return payload, {
        "entrypoint": "backend.app.services.causal_rca.analyze_causal_rca",
        "request": {},
        "persist": True,
        "record_existed_before_call": existing_before,
        "original_persisted_record_reused": existing_before,
        "persisted_record_count": record_count,
    }


def fabrication_scan(database_path: Path, analysis: Mapping[str, Any]) -> dict[str, Any]:
    inventory = inspect_database(database_path, read_only=True)
    surfaces: list[str] = []
    if inventory["exact_provider_associations"]:
        surfaces.append("build_artifact_evidence.exact_run_image")
    surfaces.extend(
        f"topology.relationship:{item}" for item in inventory["run_image_relationship_ids"]
    )
    surfaces.extend(f"topology.evidence:{item}" for item in inventory["run_image_evidence_ids"])
    if inventory["build_lineage_metadata"] and not inventory["absent"][
        "active_build_lineage_metadata"
    ]:
        surfaces.append("topology.metadata.github_actions_build_artifact_lineage")
    for index, audit in enumerate(analysis.get("lineage_admission_audit", [])):
        for path in audit.get("lineage_paths", []):
            if (
                str(path.get("run_id")) == GOLDEN_RUN_ID
                and path.get("image_digest") == GOLDEN_IMAGE_DIGEST
            ):
                surfaces.append(f"analysis.lineage_admission_audit[{index}].lineage_paths")
    for index, audit in enumerate(analysis.get("candidate_relevance_audit", [])):
        if (
            GOLDEN_RUN_ID in [str(value) for value in audit.get("bridge_run_ids", [])]
            and audit.get("bridge_image_digest") == GOLDEN_IMAGE_DIGEST
        ):
            surfaces.append(f"analysis.candidate_relevance_audit[{index}].bridge")
    encoded = json.dumps(analysis, sort_keys=True, default=str)
    for value, label in (
        (E1_ID, "analysis.build_artifact_evidence_id"),
        (RUN_IMAGE_RELATIONSHIP_ID, "analysis.run_image_relationship_id"),
        (RUN_IMAGE_EVIDENCE_ID, "analysis.run_image_evidence_id"),
    ):
        if value in encoded:
            surfaces.append(label)
    surfaces = sorted(set(surfaces))
    return {"count": len(surfaces), "surfaces": surfaces}


def unsafe_specificity_scan(analysis: Mapping[str, Any]) -> dict[str, Any]:
    surfaces: list[str] = []
    supported_ids = set(analysis.get("supported_hypothesis_ids", []))
    for index, hypothesis in enumerate(analysis.get("hypotheses", [])):
        if hypothesis.get("root_event_id") != GOLDEN_EVENT_ID:
            continue
        semantics = hypothesis.get("confidence_semantics") or {}
        if hypothesis.get("hypothesis_id") in supported_ids:
            surfaces.append(f"analysis.supported_hypothesis_ids[{hypothesis.get('hypothesis_id')}]")
        if semantics.get("evidence_state") == "supported_under_current_model":
            surfaces.append(f"analysis.hypotheses[{index}].confidence_semantics")
        gate = hypothesis.get("support_gate") or {}
        if gate.get("support_state") == "supported_under_current_model":
            surfaces.append(f"analysis.hypotheses[{index}].support_gate")
    surfaces = sorted(set(surfaces))
    return {"count": len(surfaces), "surfaces": surfaces}


def evidence_semantics_audit(analysis: Mapping[str, Any]) -> dict[str, Any]:
    violations: list[str] = []
    ledger_count = 0
    for hypothesis_index, hypothesis in enumerate(analysis.get("hypotheses", [])):
        ledger = hypothesis.get("evidence_ledger")
        if not isinstance(ledger, dict):
            continue
        ledger_count += 1
        for index, item in enumerate(ledger.get("missing", [])):
            if not item.get("expectation_basis"):
                violations.append(
                    f"hypotheses[{hypothesis_index}].evidence_ledger.missing[{index}]"
                )
        for bucket in ("supporting", "contradicting"):
            for index, item in enumerate(ledger.get(bucket, [])):
                if item.get("expectation_basis") is not None:
                    violations.append(
                        f"hypotheses[{hypothesis_index}].evidence_ledger.{bucket}[{index}]"
                    )
    return {
        "degraded": bool(violations),
        "violations": violations,
        "ledger_count": ledger_count,
        "no_candidate_specific_ledger": ledger_count == 0,
        "missing_is_not_contradiction": not violations,
    }


def normalized_semantic_output(
    *,
    construction: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    fabrication: Mapping[str, Any],
    unsafe: Mapping[str, Any],
    evidence_semantics: Mapping[str, Any],
    protected_fingerprints: Mapping[str, Any],
) -> dict[str, Any]:
    analysis_semantics = {
        key: value
        for key, value in diagnostics.items()
        if key not in VOLATILE_ANALYSIS_FIELDS
    }
    return {
        "construction": construction,
        "analysis": analysis_semantics,
        "fabrication": fabrication,
        "unsafe_specificity": unsafe,
        "evidence_semantics": evidence_semantics,
        "protected_fingerprints": protected_fingerprints,
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
        "FABRICATED_RUN_IMAGE_PROVENANCE": int(fabrication.get("count", 0)) > 0,
        "SOURCE_CAUSE_FALSELY_SUPPORTED": source_supported,
        "UNSAFE_SOURCE_SPECIFICITY_PRESERVED": int(unsafe.get("count", 0)) > 0,
        "VALID_PRESERVED_EVIDENCE_CORRUPTED": protected_corrupted,
        "EVIDENCE_SEMANTICS_DEGRADED": evidence_degraded,
        "NONDETERMINISTIC_RESULT": not deterministic,
        "NO_DIVERGENCE": True,
    }
    return next(item for item in FIRST_DIVERGENCE_ORDER if conditions[item])


def _artifact_hashes(output_root: Path) -> dict[str, str]:
    return {
        path.relative_to(output_root).as_posix(): sha256_file(path)
        for path in sorted(output_root.rglob("*"))
        if path.is_file()
        and path.name not in {"artifact-hashes.json", "artifact-integrity-v1.json"}
    }


def _assert_no_sqlite_transients(root: Path) -> list[str]:
    suffixes = ("-wal", "-shm", "-journal")
    values = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name.lower().endswith(suffixes)
    )
    if values:
        raise RuntimeError("SQLite transient files remain: " + ", ".join(values))
    return values


def run_measurement(
    *,
    seed_db: Path = DEFAULT_SEED_DB,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    seed_db = seed_db.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise FileExistsError(f"Refusing to overwrite existing B2 result root: {output_root}")

    seed_receipt = validate_seed_database(
        seed_db,
        expected_sha256=EXPECTED_SEED_SHA256,
    )
    schema_audit = verify_contract_schema(seed_db)
    seed_inventory = schema_audit["inventory"]
    classification = authority_classification(seed_inventory)
    output_root.mkdir(parents=True, exist_ok=False)

    manifest = {
        "scenario_version": SCENARIO_VERSION,
        "scenario": "LINEAGE-2B.2 — Missing Actions Run -> Immutable Image Provenance",
        "accepted_main_commit": ACCEPTED_MAIN_COMMIT,
        "seed": seed_receipt,
        "matrix": {"control": 1, "b2_semantic_scenarios": 1, "b2_repetitions": 3},
        "product_entrypoint": "backend.app.services.causal_rca.analyze_causal_rca",
        "offline": True,
        "provider_calls": False,
        "kubernetes_execution": False,
        "registry_calls": False,
        "llm_or_embeddings": False,
        "product_code_modified": False,
        "volatile_fields_normalized": list(VOLATILE_ANALYSIS_FIELDS),
        "eai_contract": EVALUATION_ARTIFACT_INTEGRITY_VERSION,
    }
    write_json(output_root / "manifest.json", manifest)
    write_json(output_root / "authority-classification.json", classification)

    with tempfile.TemporaryDirectory(prefix="topo-lineage-2b2-") as temporary:
        temporary_root = Path(temporary)
        copy_paths = {
            "control": temporary_root / "control.db",
            "repeat-1": temporary_root / "b2-repeat-1.db",
            "repeat-2": temporary_root / "b2-repeat-2.db",
            "repeat-3": temporary_root / "b2-repeat-3.db",
        }
        copy_receipts = {
            name: copy_seed_database(seed_db, path) for name, path in copy_paths.items()
        }
        reset_audits = {
            name: reset_derived_analysis(path) for name, path in copy_paths.items()
        }
        reset_signatures = {
            name: _semantic_sha256(audit) for name, audit in reset_audits.items()
        }
        reset_symmetry = len(set(reset_signatures.values())) == 1

        control_inventory = inspect_database(copy_paths["control"], read_only=False)
        control_precondition = validate_control_precondition(control_inventory)
        write_json(
            output_root / "control/scenario-input.json",
            {
                "copy": copy_receipts["control"],
                "provenance_mutation": None,
                "product_hints": False,
            },
        )
        write_json(output_root / "control/reset-audit.json", reset_audits["control"])
        write_json(output_root / "control/precondition-audit.json", control_precondition)

        control_analysis: dict[str, Any] | None = None
        control_diagnostics: dict[str, Any] | None = None
        control_execution: dict[str, Any] | None = None
        control_reproduced = False
        if control_precondition["valid"] and reset_symmetry:
            control_analysis, control_execution = run_fresh_analysis(copy_paths["control"])
            control_diagnostics = analysis_diagnostics(copy_paths["control"], control_analysis)
            control_reproduced = bool(
                control_diagnostics["exact_path_b_admitted"]
                and control_diagnostics["source_supported"]
                and control_diagnostics["most_specific_supported_semantic_level"]
                == "INITIATING_MUTATION"
            )
            write_json(output_root / "control/analysis.json", control_analysis)
            write_json(output_root / "control/diagnostics.json", control_diagnostics)
        control_grade = {
            "precondition_valid": control_precondition["valid"],
            "reset_symmetry": reset_symmetry,
            "fresh_execution": control_execution,
            "golden_reproduction": control_reproduced,
            "result": "PASS" if control_reproduced else "FAIL",
        }
        write_json(output_root / "control/grade.json", control_grade)

        repeat_results: list[dict[str, Any]] = []
        for repeat_number in range(1, 4):
            name = f"repeat-{repeat_number}"
            database_path = copy_paths[name]
            pre_mutation = inspect_database(database_path, read_only=False)
            mutation = apply_b2_mutation(database_path)
            post_mutation = inspect_database(database_path, read_only=False)
            construction = validate_b2_construction(post_mutation)
            protected_corrupted = bool(
                mutation["protected_fingerprints"]["changed"]
            )
            if construction["valid"]:
                analysis, execution = run_fresh_analysis(database_path)
                diagnostics = analysis_diagnostics(database_path, analysis)
                fabrication = fabrication_scan(database_path, analysis)
                unsafe = unsafe_specificity_scan(analysis)
                semantics = evidence_semantics_audit(analysis)
            else:
                analysis = None
                execution = None
                diagnostics = {
                    "analysis_id": None,
                    "source_supported": False,
                    "most_specific_supported_semantic_level": None,
                }
                fabrication = {"count": 0, "surfaces": []}
                unsafe = {"count": 0, "surfaces": []}
                semantics = {
                    "degraded": False,
                    "violations": [],
                    "ledger_count": 0,
                    "no_candidate_specific_ledger": True,
                    "missing_is_not_contradiction": True,
                }
            normalized = normalized_semantic_output(
                construction=construction,
                diagnostics=diagnostics,
                fabrication=fabrication,
                unsafe=unsafe,
                evidence_semantics=semantics,
                protected_fingerprints=mutation["protected_fingerprints"],
            )
            repeat_results.append(
                {
                    "repeat": repeat_number,
                    "copy": copy_receipts[name],
                    "reset": reset_audits[name],
                    "pre_mutation": {
                        "e1_count": pre_mutation["e1_count"],
                        "run_image_relationship_ids": pre_mutation[
                            "run_image_relationship_ids"
                        ],
                        "run_image_evidence_ids": pre_mutation["run_image_evidence_ids"],
                        "build_lineage_metadata": pre_mutation["build_lineage_metadata"],
                    },
                    "mutation": mutation,
                    "construction": construction,
                    "analysis": analysis,
                    "execution": execution,
                    "diagnostics": diagnostics,
                    "fabrication": fabrication,
                    "unsafe_specificity": unsafe,
                    "evidence_semantics": semantics,
                    "protected_corrupted": protected_corrupted,
                    "normalized_semantic_output": normalized,
                    "semantic_sha256": _semantic_sha256(normalized),
                }
            )

    semantic_hashes = [item["semantic_sha256"] for item in repeat_results]
    deterministic = len(set(semantic_hashes)) == 1
    for item in repeat_results:
        item["taxonomy_result"] = grade_taxonomy(
            construction=item["construction"],
            fabrication=item["fabrication"],
            source_supported=bool(item["diagnostics"].get("source_supported")),
            unsafe=item["unsafe_specificity"],
            protected_corrupted=bool(item["protected_corrupted"]),
            evidence_degraded=bool(item["evidence_semantics"].get("degraded")),
            deterministic=deterministic,
        )

    first = repeat_results[0]
    taxonomy_result = first["taxonomy_result"]
    all_constructed = all(item["construction"]["valid"] for item in repeat_results)
    if not control_reproduced or not reset_symmetry or not all_constructed:
        verdict = "INCONCLUSIVE"
    elif taxonomy_result == "NO_DIVERGENCE":
        verdict = "ROBUST_IN_MEASURED_MATRIX"
    else:
        verdict = "ADVERSARIAL_DIVERGENCE_FOUND"

    write_json(
        output_root / "b2/mutation-plan.json",
        {
            "authoritative_removed": [E1_ID],
            "derived_removed": [
                RUN_IMAGE_RELATIONSHIP_ID,
                RUN_IMAGE_EVIDENCE_ID,
                "metadata.github_actions_build_artifact_lineage",
                "stale causal-analysis and incident cache state",
            ],
            "protected": classification["authoritative_preserved"],
            "synthetic_repair_allowed": False,
        },
    )
    write_json(output_root / "b2/mutation-audit.json", first["mutation"])
    write_json(output_root / "b2/precondition-audit.json", first["construction"])
    write_json(
        output_root / "b2/protected-evidence.json",
        first["mutation"]["protected_fingerprints"],
    )
    if first["analysis"] is not None:
        write_json(output_root / "b2/analysis.json", first["analysis"])
    write_json(output_root / "b2/diagnostics.json", first["diagnostics"])
    write_json(
        output_root / "b2/grade.json",
        {
            "scenario_valid": first["construction"]["valid"],
            "taxonomy_result": taxonomy_result,
            "overall_verdict": verdict,
            "fabrication": first["fabrication"],
            "unsafe_specificity": first["unsafe_specificity"],
            "protected_corrupted": first["protected_corrupted"],
            "evidence_semantics": first["evidence_semantics"],
        },
    )
    for item in repeat_results:
        compact = {
            key: value
            for key, value in item.items()
            if key not in {"analysis", "normalized_semantic_output"}
        }
        write_json(output_root / f"determinism/repeat-{item['repeat']}.json", compact)
    write_json(
        output_root / "determinism/normalized-hashes.json",
        {
            "volatile_fields_normalized": list(VOLATILE_ANALYSIS_FIELDS),
            "hashes": semantic_hashes,
            "identical": deterministic,
            "repetitions": 3,
        },
    )

    aggregate = {
        "scenario_version": SCENARIO_VERSION,
        "control_reproduction": control_reproduced,
        "reset_symmetry": reset_symmetry,
        "construction_valid_repetitions": sum(
            item["construction"]["valid"] for item in repeat_results
        ),
        "determinism": {"identical": deterministic, "hashes": semantic_hashes},
        "taxonomy_result": taxonomy_result,
        "first_divergence": taxonomy_result,
        "overall_verdict": verdict,
        "source_specificity_reduced_safely": bool(
            taxonomy_result == "NO_DIVERGENCE"
            and not first["diagnostics"].get("source_supported")
        ),
        "preserved_truth": {
            "commit_run": first["construction"]["required_present"][
                "commit_run_relationship"
            ]
            and first["construction"]["required_present"]["commit_run_evidence"],
            "image_workload": first["construction"]["required_present"][
                "deployment_image"
            ]
            and first["construction"]["required_present"]["pod_image"],
            "runtime_failure": first["construction"]["required_present"][
                "runtime_failure"
            ],
        },
        "fabricated_run_image_count": first["fabrication"]["count"],
        "unsafe_source_specificity_count": first["unsafe_specificity"]["count"],
        "product_policy_changes": [],
        "seed_post_run": validate_seed_database(
            seed_db,
            expected_sha256=EXPECTED_SEED_SHA256,
        ),
    }
    write_json(output_root / "aggregate.json", aggregate)
    hashes = _artifact_hashes(output_root)
    write_json(output_root / "artifact-hashes.json", hashes)
    transient_files = _assert_no_sqlite_transients(output_root)
    integrity_manifest = write_integrity_manifest(output_root)
    verification = verify_integrity_manifest(output_root)
    return {
        "manifest": manifest,
        "aggregate": aggregate,
        "control": {
            "copy": copy_receipts["control"],
            "reset": reset_audits["control"],
            "analysis": control_analysis,
            "diagnostics": control_diagnostics,
            "grade": control_grade,
        },
        "b2_repeats": repeat_results,
        "artifact_hashes": hashes,
        "sqlite_transient_files": transient_files,
        "eai": {
            "contract": integrity_manifest["contract"],
            "tree_sha256": integrity_manifest["tree_sha256"],
            "included_file_count": len(integrity_manifest["entries"]),
            "verification": {
                "contract": verification.contract,
                "tree_sha256": verification.tree_sha256,
                "included_file_count": verification.included_file_count,
                "status": "verified",
            },
            "generated_after_ordinary_artifacts": True,
        },
        "output_root": output_root.as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline LINEAGE-2B.2 missing Run -> Image experiment."
    )
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
