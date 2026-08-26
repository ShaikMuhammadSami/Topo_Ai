from __future__ import annotations

import copy
import hashlib
import inspect
import io
import json
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.database import Base
from app.db.models import (
    BuildArtifactEvidenceRecord,
    CausalAnalysisRecord,
    IncidentRecord,
    SnapshotRecord,
)
from app.models.topology import (
    Entity,
    EntityType,
    GraphSnapshot,
    Relationship,
    RelationshipOrigin,
    RelationshipType,
)
from app.repositories.build_artifact_evidence_repository import (
    list_build_artifact_evidence,
)
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.services.canonical_identity import (
    canonical_container_image_identity,
    canonical_github_workflow_run_identity,
)
from app.services.container_image_graph import augment_snapshot_with_container_images
from app.services.github_actions_artifact_lineage import (
    LINKER_VERSION,
    SOURCE_COMPONENT,
    enrich_snapshot_with_github_actions_provider_evidence,
    reconcile_build_artifact_lineage,
)
from app.services.github_actions_build_record import (
    parse_github_actions_docker_build_record,
)
from app.services.github_actions_graph import augment_snapshot_with_github_actions
from app.services.github_graph import augment_snapshot_with_github


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 24, 5, 0, tzinfo=timezone.utc)
REPOSITORY = {"id": 101, "full_name": "acme/payments"}
COMMIT = "a" * 40
RUN = {
    "id": 42001,
    "run_attempt": 1,
    "run_number": 7,
    "workflow_id": 8001,
    "name": "Build container",
    "head_sha": COMMIT,
    "event": "push",
    "status": "completed",
    "conclusion": "success",
    "created_at": "2026-08-24T04:00:00Z",
    "run_started_at": "2026-08-24T04:00:02Z",
    "updated_at": "2026-08-24T04:01:00Z",
}

PROTECTED_PRODUCT_HASHES = {
    "backend/app/services/canonical_identity.py": "5ae8abd4d5706fc975ffa66495d17bdd68784bd3",
    "backend/app/services/relationship_provenance.py": "f7cd1b45a12a53e938ad1eb734fe8d6c93a27492",
    "backend/app/models/temporal.py": "b6c367e631553f08bd6886bc8e22d104f6fd964f",
    "backend/app/services/causal_candidate_policy.py": "38c53385efb9472937aba5834cb24a6d957731a5",
    "backend/app/services/causal_relevance_policy.py": "a43052d476d0127fabbb1c584ef23c04620907ec",
    "backend/app/services/causal_rca.py": "11202fa1535ec695809875e1b0f0bf57931a69f1",
    "backend/app/services/blast_impact_policy.py": "36be80fba0165edfb98a911775e2e925fb672c4e",
}
TRUTH_CONTRACT_HASHES = {
    "causal-evidence-ledger-contract.json": "2336f00ddbed522036745f09826c87b5d15317f5",
    "causal-evidence-ledger.md": "5a94bb115f099708ec7303347e86e4b376e7cf3d",
    "confidence-semantics-contract.json": "1fe87aa209167dd77bf0e3494e1eb2524c21ba2c",
    "confidence-semantics.md": "16c00fb91c399e07a0ddf0c18cd3929e6d7271e9",
    "entity-identity-contract.json": "d67c17ce7fd84b5610173193af4c104114dda731",
    "entity-identity.md": "61d2949668926a8046e5a984aec1d11e312de3dd",
    "relationship-provenance-contract.json": "866c379730b6a57face4ac03543ac6e863abcaa2",
    "relationship-provenance.md": "67336aab3bb48b38185d5976c6eee75de2aea1fa",
    "temporal-semantics-contract.json": "a8984eb2110bd3cb8b3412723565569edbfd4853",
    "temporal-semantics.md": "cc3036a44b9b14486737a651b3a3eebd6f195a42",
    "truth-substrate-v1.md": "8a225cf5c0ad5ad2cbe349f15d8b8c46e2ef0318",
}


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _record_fixture(
    *,
    repository: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    artifact_id: int = 9001,
    image_count: int = 1,
    image_repositories: list[str] | None = None,
    internal_overrides: dict[str, Any] | None = None,
    builder_id: str | None = None,
    include_attestation: bool = True,
    include_result: bool = True,
    malformed_result_digest: bool = False,
    include_build_times: bool = True,
    zip_wrapper: bool = False,
    unsafe_path: bool = False,
) -> tuple[dict[str, Any], bytes, list[str]]:
    repository = copy.deepcopy(repository or REPOSITORY)
    run = copy.deepcopy(run or RUN)
    image_payloads = [
        _json_bytes({"schemaVersion": 2, "image": index})
        for index in range(image_count)
    ]
    image_digests = [_digest(value) for value in image_payloads]
    internal = {
        "github_repository": repository["full_name"],
        "github_repository_id": str(repository["id"]),
        "github_run_id": str(run["id"]),
        "github_run_attempt": str(run["run_attempt"]),
        "github_workflow_ref": (
            f"{repository['full_name']}/.github/workflows/build.yml@refs/heads/main"
        ),
        "github_workflow": run["name"],
    }
    internal.update(internal_overrides or {})
    predicate = {
        "buildDefinition": {"internalParameters": internal},
        "runDetails": {
            "builder": {
                "id": builder_id
                or (
                    f"https://github.com/{repository['full_name']}/actions/"
                    f"runs/{run['id']}/attempts/{run['run_attempt']}"
                )
            },
            "metadata": (
                {
                    "startedOn": "2026-08-24T04:00:10Z",
                    "finishedOn": "2026-08-24T04:00:45Z",
                }
                if include_build_times
                else {}
            ),
        },
    }
    predicate_payload = _json_bytes(predicate)
    predicate_digest = _digest(predicate_payload)
    repositories = image_repositories or ["ghcr.io/acme/payments"]
    exporters = [
        {"Type": "image", "Attrs": {"name": f"{value}:build", "push": "true"}}
        for value in repositories
    ]
    result_descriptors: dict[str, Any] = {}
    if include_result:
        for index, digest in enumerate(image_digests):
            result_descriptors[str(index)] = {
                "media_type": "application/vnd.oci.image.index.v1+json",
                "digest": ("sha256:not-a-digest" if malformed_result_digest else digest),
                "size": len(image_payloads[index]),
            }
    history = {
        "Exporters": exporters,
        "Result": {
            "Results": result_descriptors,
            "Attestations": (
                [
                    {
                        "media_type": "application/vnd.in-toto+json",
                        "digest": predicate_digest,
                        "size": len(predicate_payload),
                        "annotations": {
                            "in-toto.io/predicate-type": "https://slsa.dev/provenance/v1"
                        },
                    }
                ]
                if include_attestation
                else []
            ),
        },
    }
    history_payload = _json_bytes(history)
    history_digest = _digest(history_payload)
    manifest = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {
            "mediaType": "application/vnd.buildkit.historyrecord.v0",
            "digest": history_digest,
            "size": len(history_payload),
        },
        "layers": [],
    }
    manifest_payload = _json_bytes(manifest)
    manifest_digest = _digest(manifest_payload)
    index = {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "digest": manifest_digest,
                "size": len(manifest_payload),
            }
        ],
    }
    files = {
        "oci-layout": _json_bytes({"imageLayoutVersion": "1.0.0"}),
        "index.json": _json_bytes(index),
        f"blobs/sha256/{manifest_digest.split(':')[1]}": manifest_payload,
        f"blobs/sha256/{history_digest.split(':')[1]}": history_payload,
        f"blobs/sha256/{predicate_digest.split(':')[1]}": predicate_payload,
    }
    for digest, payload in zip(image_digests, image_payloads, strict=True):
        files[f"blobs/sha256/{digest.split(':')[1]}"] = payload
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, payload in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if unsafe_path:
            bad = b"unsafe"
            info = tarfile.TarInfo("../unsafe")
            info.size = len(bad)
            archive.addfile(info, io.BytesIO(bad))
    payload = buffer.getvalue()
    if zip_wrapper:
        wrapper = io.BytesIO()
        with zipfile.ZipFile(wrapper, "w") as archive:
            archive.writestr("provider-build.dockerbuild", payload)
        payload = wrapper.getvalue()
    artifact = {
        "id": artifact_id,
        "name": "acme~payments~build.dockerbuild",
        "url": f"https://api.github.com/repos/acme/payments/actions/artifacts/{artifact_id}",
        "size_in_bytes": len(payload),
        "digest": _digest(payload),
        "expired": False,
        "workflow_run": {
            "id": run["id"],
            "repository_id": repository["id"],
            "head_sha": run["head_sha"],
        },
    }
    return artifact, payload, image_digests


class FakeConnector:
    def __init__(
        self,
        artifacts: dict[str, list[dict[str, Any]]],
        payloads: dict[str, bytes],
        *,
        fail_list: bool = False,
    ) -> None:
        self.settings = SimpleNamespace(
            api_url="https://api.github.com",
            full_name=REPOSITORY["full_name"],
        )
        self.artifacts = artifacts
        self.payloads = payloads
        self.fail_list = fail_list

    def list_workflow_run_artifacts(self, run_id: str | int) -> list[dict[str, Any]]:
        if self.fail_list:
            from app.connectors.github_connector import GitHubConnectorError

            raise GitHubConnectorError("unavailable")
        return copy.deepcopy(self.artifacts.get(str(run_id), []))

    def download_actions_artifact(self, artifact_id: str | int) -> bytes:
        return self.payloads[str(artifact_id)]


def _snapshot(image_digests: list[str] | None = None) -> GraphSnapshot:
    workloads = []
    for index, digest in enumerate(image_digests or []):
        workloads.append(
            Entity(
                id=f"k8s:test:deployment:payments-{index}",
                entity_type=EntityType.WORKLOAD,
                kind="KubernetesDeployment",
                name=f"payments-{index}",
                source_system="kubernetes",
                observed_at=NOW,
                properties={
                    "containers": [
                        {
                            "name": "payments",
                            "image": f"ghcr.io/acme/payments@{digest}",
                        }
                    ],
                    "annotations": {
                        "topo.ai/workflow-run-id": str(RUN["id"]),
                        "topo.ai/source-revision": COMMIT,
                    },
                },
            )
        )
    snapshot = GraphSnapshot(
        snapshot_id="snapshot:base",
        collected_at=NOW,
        collector_name="test",
        collector_version="1",
        scope={},
        entities=workloads,
        relationships=[],
        evidence=[],
        metadata={},
    )
    snapshot = augment_snapshot_with_container_images(snapshot)
    snapshot, _ = augment_snapshot_with_github(
        snapshot,
        repository=REPOSITORY,
        commits=[{"sha": COMMIT, "commit": {"message": "release"}}],
        api_url="https://api.github.com",
    )
    return snapshot


def _exercise(
    *,
    image_count: int = 1,
    include_images: bool = True,
    record_kwargs: dict[str, Any] | None = None,
) -> tuple[Session, GraphSnapshot, dict[str, Any], Any, list[str], dict[str, Any], bytes]:
    artifact, payload, digests = _record_fixture(
        image_count=image_count,
        **(record_kwargs or {}),
    )
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]},
        {str(artifact["id"]): payload},
    )
    session = _session()
    result, stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        session,
        snapshot=_snapshot(digests if include_images else []),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    return session, result, stats, lineage, digests, artifact, payload


def _produces(snapshot: GraphSnapshot) -> list[Relationship]:
    return [
        item
        for item in snapshot.relationships
        if item.relationship_type == RelationshipType.PRODUCES
        and ":workflow-run:" in item.source_entity_id
    ]


def test_provider_build_record_extracts_exact_digest_evidence():
    artifact, payload, digests = _record_fixture()
    result = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    assert [item.image_digest for item in result.evidence] == digests
    assert result.warnings == []


def test_exact_provider_evidence_creates_produces():
    _session_value, snapshot, *_rest = _exercise()
    assert len(_produces(snapshot)) == 1


def test_produces_direction_is_run_to_image():
    _session_value, snapshot, *_rest = _exercise()
    relationship = _produces(snapshot)[0]
    assert relationship.source_entity_id.startswith("github:api.github.com:workflow-run:")
    assert relationship.target_entity_id.startswith("artifact:container-image:sha256:")


def test_predicate_is_exactly_produces():
    _session_value, snapshot, *_rest = _exercise()
    assert _produces(snapshot)[0].relationship_type.value == "produces"


def test_existing_run_entity_is_reused():
    _session_value, snapshot, _stats, _lineage, _digests, _artifact, _payload = _exercise()
    run_id = canonical_github_workflow_run_identity(
        api_url="https://api.github.com", run_id=RUN["id"]
    ).canonical_id
    assert [item.id for item in snapshot.entities].count(run_id) == 1


def test_existing_image_entity_is_reused():
    _session_value, snapshot, _stats, _lineage, digests, _artifact, _payload = _exercise()
    image_id = canonical_container_image_identity(
        normalized_reference=f"ghcr.io/acme/payments@{digests[0]}", digest=digests[0]
    ).canonical_id
    assert [item.id for item in snapshot.entities].count(image_id) == 1


def test_no_duplicate_run_entity_is_created():
    _session_value, snapshot, *_rest = _exercise()
    assert len([item for item in snapshot.entities if item.kind == "GitHubWorkflowRun"]) == 1


def test_no_duplicate_image_entity_is_created():
    _session_value, snapshot, *_rest = _exercise()
    assert len([item for item in snapshot.entities if item.kind == "ContainerImage"]) == 1


def test_evidence_replay_is_repository_idempotent():
    session, snapshot, _stats, _lineage, _digests, artifact, payload = _exercise()
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        session,
        snapshot=snapshot,
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert session.scalar(select(func.count()).select_from(BuildArtifactEvidenceRecord)) == 1
    assert lineage.evidence_records_persisted == 0
    assert len(_produces(result)) == 1


def test_multiple_identical_enrichment_calls_create_one_relationship():
    session, snapshot, _stats, _lineage, _digests, artifact, payload = _exercise()
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    for _ in range(2):
        snapshot, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
            session,
            snapshot=snapshot,
            connector=connector,
            repository=REPOSITORY,
            workflow_runs=[RUN],
            observed_at=NOW,
        )
    assert len(_produces(snapshot)) == 1


def test_relationship_id_is_deterministic():
    _session_one, first, *_rest = _exercise()
    _session_two, second, *_rest_two = _exercise()
    assert _produces(first)[0].id == _produces(second)[0].id


def test_tc2_origin_is_observed():
    _session_value, snapshot, *_rest = _exercise()
    assert _produces(snapshot)[0].provenance.origin == RelationshipOrigin.OBSERVED


def test_tc2_source_component_is_stable():
    _session_value, snapshot, *_rest = _exercise()
    assert _produces(snapshot)[0].provenance.source_component == SOURCE_COMPONENT


def test_tc2_linker_version_is_stable():
    _session_value, snapshot, *_rest = _exercise()
    assert _produces(snapshot)[0].provenance.linker_version == LINKER_VERSION


@pytest.mark.parametrize(
    "reference_type",
    [
        "github_repository_id",
        "github_workflow_run_id",
        "github_workflow_run_attempt",
        "github_actions_artifact_id",
        "github_actions_artifact_digest",
        "docker_build_record_digest",
        "provider_builder_id",
        "container_image_digest",
    ],
)
def test_tc2_source_reference_is_present(reference_type: str):
    _session_value, snapshot, *_rest = _exercise()
    assert reference_type in {
        item.reference_type
        for item in _produces(snapshot)[0].provenance.source_references
    }


def test_tc2_completeness_is_complete():
    _session_value, snapshot, *_rest = _exercise()
    assert _produces(snapshot)[0].provenance.completeness.value == "complete"


def test_no_calibrated_probability_is_invented():
    _session_value, snapshot, *_rest = _exercise()
    relationship = _produces(snapshot)[0]
    assert relationship.confidence is None
    assert relationship.confidence_semantics is None


def test_relationship_temporal_metadata_separates_source_and_observation():
    _session_value, snapshot, *_rest = _exercise()
    temporal = _produces(snapshot)[0].temporal
    assert temporal.status.value == "complete"
    assert temporal.source_event_at.isoformat().startswith("2026-08-24T04:01:00")
    assert temporal.observed_at == NOW
    assert temporal.source_field == "github_workflow_run.updated_at"


def test_missing_provider_build_time_is_not_fabricated():
    _session_value, snapshot, *_rest = _exercise(
        record_kwargs={"include_build_times": False}
    )
    props = _produces(snapshot)[0].properties
    assert props["provider_build_started_at"] == []
    assert props["provider_build_finished_at"] == []
    assert "built_at" not in props


def test_workload_tag_or_run_metadata_without_provider_evidence_creates_no_edge():
    snapshot, _stats = augment_snapshot_with_github_actions(
        _snapshot([]),
        workflow_runs=[RUN],
        repository_full_name=REPOSITORY["full_name"],
        api_url="https://api.github.com",
    )
    assert _produces(snapshot) == []


@pytest.mark.parametrize(
    "weak_basis",
    ["commit_sha", "time_proximity", "workflow_name", "mutable_tag"],
)
def test_weak_basis_never_creates_h3(weak_basis: str):
    snapshot = _snapshot([])
    if weak_basis == "mutable_tag":
        workload = Entity(
            id="k8s:test:deployment:tag-only",
            entity_type=EntityType.WORKLOAD,
            kind="KubernetesDeployment",
            name="tag-only",
            source_system="kubernetes",
            observed_at=NOW,
            properties={
                "containers": [{"name": "app", "image": "ghcr.io/acme/payments:latest"}]
            },
        )
        snapshot.entities.append(workload)
        snapshot = augment_snapshot_with_container_images(snapshot)
    snapshot, _stats = augment_snapshot_with_github_actions(
        snapshot,
        workflow_runs=[RUN],
        repository_full_name=REPOSITORY["full_name"],
        api_url="https://api.github.com",
    )
    assert _produces(snapshot) == [], weak_basis


def test_same_commit_but_wrong_run_id_creates_no_edge():
    session, snapshot, _stats, _lineage, _digests, artifact, payload = _exercise()
    wrong = {**RUN, "id": RUN["id"] + 1}
    connector = FakeConnector(
        {str(wrong["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
        session,
        snapshot=_snapshot([]),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[wrong],
        observed_at=NOW,
    )
    assert _produces(result) == []


def test_same_run_id_wrong_attempt_creates_no_edge():
    wrong = {**RUN, "run_attempt": 2}
    artifact, payload, digests = _record_fixture()
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot(digests),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[wrong],
        observed_at=NOW,
    )
    assert _produces(result) == []
    assert any("RUN_ATTEMPT_MISMATCH" in value for value in lineage.warnings)


def test_wrong_digest_does_not_link_expected_image():
    artifact, payload, _record_digests = _record_fixture()
    other_digest = _digest(b"other-image")
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot([other_digest]),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert _produces(result) == []


def test_malformed_digest_is_rejected():
    artifact, payload, _digests = _record_fixture(malformed_result_digest=True)
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    assert parsed.evidence == []
    assert "IMAGE_DIGEST_INVALID" in parsed.warnings[0]


def test_ambiguous_image_identity_creates_no_edge():
    artifact, payload, digests = _record_fixture()
    base = _snapshot(digests)
    image = next(item for item in base.entities if item.kind == "ContainerImage")
    base.entities.append(image.model_copy(deep=True))
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=base,
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert _produces(result) == []
    assert any("IMAGE_ENTITY_AMBIGUOUS" in value for value in lineage.warnings)


def test_missing_run_entity_does_not_fabricate_identity():
    artifact, payload, digests = _record_fixture()
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    snapshot, stats = reconcile_build_artifact_lineage(
        _snapshot(digests),
        evidence=parsed.evidence,
        api_url="https://api.github.com",
    )
    assert _produces(snapshot) == []
    assert stats.unresolved_evidence_count == 1


def test_missing_image_entity_retains_pending_evidence():
    session, snapshot, _stats, lineage, _digests, _artifact, _payload = _exercise(
        include_images=False
    )
    assert _produces(snapshot) == []
    assert lineage.unresolved_evidence_count == 1
    assert len(list_build_artifact_evidence(session, repository_id="101")) == 1


def test_evidence_first_links_when_image_later_becomes_available():
    session, first, _stats, _lineage, digests, _artifact, _payload = _exercise(
        include_images=False
    )
    assert _produces(first) == []
    later = _snapshot(digests)
    reconciled, _stats, lineage = (
        enrich_snapshot_with_github_actions_provider_evidence(
        session,
        snapshot=later,
        connector=FakeConnector({str(RUN["id"]): []}, {}),
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
        )
    )
    assert len(_produces(reconciled)) == 1
    assert lineage.unresolved_evidence_count == 0


def test_image_first_links_when_evidence_arrives():
    _session_value, snapshot, *_rest = _exercise(include_images=True)
    assert len(_produces(snapshot)) == 1


def test_reconciliation_requires_no_background_worker():
    source = inspect.getsource(reconcile_build_artifact_lineage).casefold()
    for forbidden in ("celery", "thread", "scheduler", "backgroundtasks"):
        assert forbidden not in source


def test_multiple_images_from_one_run_are_supported():
    _session_value, snapshot, _stats, lineage, digests, _artifact, _payload = _exercise(
        image_count=2
    )
    assert len(digests) == 2
    assert len(_produces(snapshot)) == 2
    assert lineage.mapped_image_count == 2


def test_same_image_may_be_produced_by_independent_runs():
    first_artifact, first_payload, digests = _record_fixture(artifact_id=9001)
    second_run = {**RUN, "id": 42002, "run_number": 8}
    second_artifact, second_payload, second_digests = _record_fixture(
        run=second_run, artifact_id=9002
    )
    assert second_digests == digests
    connector = FakeConnector(
        {
            str(RUN["id"]): [first_artifact],
            str(second_run["id"]): [second_artifact],
        },
        {"9001": first_payload, "9002": second_payload},
    )
    snapshot, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot(digests),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN, second_run],
        observed_at=NOW,
    )
    assert len(_produces(snapshot)) == 2
    assert len({item.source_entity_id for item in _produces(snapshot)}) == 2


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("artifact_digest", "PROVIDER_ARTIFACT_DIGEST_MISMATCH"),
        ("artifact_repository", "ARTIFACT_RUN_SCOPE_MISMATCH"),
        ("missing_attestation", "BUILD_ATTESTATION_MISSING"),
        ("missing_internal", "BUILD_PROVIDER_IDENTITY_MISMATCH"),
        ("builder_mismatch", "RUN_ATTEMPT_MISMATCH"),
        ("missing_result", "IMAGE_DIGEST_MISSING"),
        ("ambiguous_repository", "IMAGE_REPOSITORY_AMBIGUOUS"),
        ("unsafe_path", "BUILD_RECORD_PATH_UNSAFE"),
    ],
)
def test_malformed_or_conflicting_provider_record_is_rejected(
    mutation: str, code: str
):
    kwargs: dict[str, Any] = {}
    if mutation == "missing_attestation":
        kwargs["include_attestation"] = False
    elif mutation == "missing_internal":
        kwargs["internal_overrides"] = {
            "github_repository": None,
            "github_repository_id": None,
            "github_run_id": None,
            "github_run_attempt": None,
        }
    elif mutation == "builder_mismatch":
        kwargs["builder_id"] = (
            "https://github.com/acme/payments/actions/runs/42001/attempts/2"
        )
    elif mutation == "missing_result":
        kwargs["include_result"] = False
    elif mutation == "ambiguous_repository":
        kwargs["image_repositories"] = [
            "ghcr.io/acme/payments", "ghcr.io/acme/other"
        ]
    elif mutation == "unsafe_path":
        kwargs["unsafe_path"] = True
    artifact, payload, _digests = _record_fixture(**kwargs)
    if mutation == "artifact_digest":
        artifact["digest"] = "sha256:" + "0" * 64
    elif mutation == "artifact_repository":
        artifact["workflow_run"]["repository_id"] = 999
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    assert parsed.evidence == []
    assert code in parsed.warnings[0]


def test_zip_wrapped_provider_build_record_is_supported():
    artifact, payload, digests = _record_fixture(zip_wrapper=True)
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    assert [item.image_digest for item in parsed.evidence] == digests


def test_non_build_artifact_is_not_an_ingestion_shortcut():
    artifact, payload, _digests = _record_fixture()
    artifact["name"] = "custom-receipt.json"
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    assert parsed.evidence == []
    assert "UNSUPPORTED_PROVIDER_ARTIFACT" in parsed.warnings[0]


def test_secret_bearing_provider_fields_are_not_serialized():
    artifact, payload, _digests = _record_fixture(
        internal_overrides={"github_token": "secret-value"}
    )
    parsed = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    encoded = parsed.model_dump_json()
    assert "secret-value" not in encoded
    assert "github_token" not in encoded


def test_provider_record_extraction_is_deterministic():
    artifact, payload, _digests = _record_fixture()
    first = parse_github_actions_docker_build_record(
        artifact=artifact,
        artifact_payload=payload,
        repository=REPOSITORY,
        workflow_run=RUN,
        observed_at=NOW,
    )
    second = parse_github_actions_docker_build_record(
        artifact=copy.deepcopy(artifact),
        artifact_payload=payload,
        repository=copy.deepcopy(REPOSITORY),
        workflow_run=copy.deepcopy(RUN),
        observed_at=NOW,
    )
    assert first == second


def test_provider_parser_uses_no_logs_fuzzy_llm_or_embeddings():
    source = inspect.getsource(parse_github_actions_docker_build_record).casefold()
    for forbidden in ("log prose", "fuzzy", "openai", "embedding", "levenshtein"):
        assert forbidden not in source


def test_expired_build_record_creates_no_edge():
    artifact, payload, digests = _record_fixture()
    artifact["expired"] = True
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    snapshot, _stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot(digests),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert _produces(snapshot) == []
    assert any("PROVIDER_ARTIFACT_EXPIRED" in item for item in lineage.warnings)


def test_connector_failure_with_no_durable_evidence_creates_no_edge():
    artifact, payload, digests = _record_fixture()
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]},
        {str(artifact["id"]): payload},
        fail_list=True,
    )
    snapshot, _stats, lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot(digests),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert _produces(snapshot) == []
    assert any("provider_unavailable" in item for item in lineage.warnings)


def test_no_provider_build_evidence_creates_no_false_edge():
    connector = FakeConnector({str(RUN["id"]): []}, {})
    snapshot, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=_snapshot([_digest(b"image")]),
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert _produces(snapshot) == []


def test_late_evidence_does_not_rewrite_historical_snapshot_analysis_or_pin():
    session = _session()
    pinned = _snapshot([]).model_copy(update={"snapshot_id": "snapshot:pinned"})
    save_snapshot(session, pinned)
    now = NOW.isoformat()
    session.add(
        IncidentRecord(
            incident_id="incident:pinned",
            fingerprint="fingerprint:pinned",
            status="open",
            severity="high",
            title="Pinned incident",
            summary="Pinned",
            cluster_name="test",
            namespace="payments",
            primary_signal_id="signal:pinned",
            topology_snapshot_id="snapshot:pinned",
            first_observed_at=now,
            last_observed_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        CausalAnalysisRecord(
            analysis_id="analysis:pinned",
            incident_id="incident:pinned",
            generated_at=now,
            algorithm_version="13c-causal-v1",
            candidate_count=0,
            hypothesis_count=0,
            payload_json='{"analysis":"immutable"}',
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    before_snapshot = load_snapshot(session, "snapshot:pinned")
    before_payload = session.get(CausalAnalysisRecord, "analysis:pinned").payload_json
    _session_value, _current, *_rest = _exercise()
    assert load_snapshot(session, "snapshot:pinned") == before_snapshot
    assert session.get(IncidentRecord, "incident:pinned").topology_snapshot_id == "snapshot:pinned"
    assert session.get(CausalAnalysisRecord, "analysis:pinned").payload_json == before_payload


@pytest.mark.parametrize(
    "predicate",
    [RelationshipType.USES, RelationshipType.OWNS, RelationshipType.RUNS],
)
def test_existing_non_h3_relationships_remain_unchanged(predicate: RelationshipType):
    artifact, payload, digests = _record_fixture()
    base = _snapshot(digests)
    existing = Relationship(
        id=f"rel:existing:{predicate.value}",
        source_entity_id=base.entities[0].id,
        target_entity_id=base.entities[0].id,
        relationship_type=predicate,
        source_system="test",
        observed_at=NOW,
        provenance=None,
    )
    base.relationships.append(existing)
    connector = FakeConnector(
        {str(RUN["id"]): [artifact]}, {str(artifact["id"]): payload}
    )
    result, _stats, _lineage = enrich_snapshot_with_github_actions_provider_evidence(
        _session(),
        snapshot=base,
        connector=connector,
        repository=REPOSITORY,
        workflow_runs=[RUN],
        observed_at=NOW,
    )
    assert next(item for item in result.relationships if item.id == existing.id) == existing


def test_existing_commit_to_actions_behavior_is_unchanged():
    _session_value, snapshot, *_rest = _exercise()
    assert len(
        [item for item in snapshot.relationships if item.relationship_type == RelationshipType.TRIGGERS]
    ) == 1


def test_github_workflow_run_identity_semantics_are_unchanged():
    identity = canonical_github_workflow_run_identity(
        api_url="https://api.github.com", run_id=RUN["id"]
    )
    assert identity.canonical_id == "github:api.github.com:workflow-run:42001"
    assert "attempt" not in identity.canonical_id


def test_container_image_identity_semantics_are_unchanged():
    digest = _digest(b"identity")
    identity = canonical_container_image_identity(
        normalized_reference=f"ghcr.io/acme/payments@{digest}", digest=digest
    )
    assert identity.canonical_id == f"artifact:container-image:{digest}"


@pytest.mark.parametrize("path,expected", sorted(PROTECTED_PRODUCT_HASHES.items()))
def test_protected_product_contract_implementation_is_unchanged(path: str, expected: str):
    assert hashlib.sha1((ROOT / path).read_bytes()).hexdigest() != ""
    import subprocess

    actual = subprocess.run(
        ["git", "hash-object", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual == expected


@pytest.mark.parametrize("name,expected", sorted(TRUTH_CONTRACT_HASHES.items()))
def test_truth_contract_document_is_unchanged(name: str, expected: str):
    import subprocess

    path = ROOT / "docs/architecture/truth-contract" / name
    actual = subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert actual == expected


def test_product_source_has_no_evaluation_specific_special_case():
    forbidden = (
        "32688747741",
        "ebd9da90",
        "topo-lineage-provider-fixture",
        "eval-lineage-provider-receipt",
        "sentinel-a",
        "sentinel-b",
        "blast-01",
        "blast-03",
    )
    for path in (ROOT / "backend/app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").casefold()
        assert not any(value in text for value in forbidden), path


def test_product_code_does_not_import_evaluation_modules():
    for path in (ROOT / "backend/app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from evaluation" not in text
        assert "import evaluation" not in text


def test_product_code_does_not_import_evaluation_receipt_schema():
    encoded = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend/app").rglob("*.py")
    ).casefold()
    assert "provider-receipt" not in encoded
    assert "eval-lineage" not in encoded
