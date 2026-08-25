from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.collectors.kubernetes_collector import KubernetesCollector
from app.db.database import Base
from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION,
)
from app.models.causal_rca import CausalAnalysisRequest
from app.models.causal_relevance import CAUSAL_RELEVANCE_POLICY_VERSION
from app.models.container_image_identity import (
    KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION,
    MAX_CONTAINER_IMAGE_REFERENCE_LENGTH,
    ContainerImageCaptureState,
    ContainerImageJoinState,
    ContainerImageReferenceKind,
    ContainerImageSemanticRole,
    KubernetesContainerImageObservation,
)
from app.models.topology import Entity, EntityType, GraphSnapshot, RelationshipType
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.services.canonical_identity import canonical_container_image_identity
from app.services.container_image_graph import augment_snapshot_with_container_images
from app.services.container_image_identity import (
    normalize_regular_container_images,
    parse_container_image_observation,
)
from app.services.incident_change_analysis import analyze_incident_change_events


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
DIGEST_X = "sha256:" + "1" * 64
DIGEST_Y = "sha256:" + "2" * 64
DIGEST_Z = "sha256:" + "3" * 64
APP_REF = f"ghcr.io/example/app@{DIGEST_X}"


def _observation(
    *,
    requested: str | None = APP_REF,
    status_image: str | None = DIGEST_Y,
    image_id: str | None = f"containerd://{DIGEST_Z}",
    name: str = "app",
) -> dict:
    return normalize_regular_container_images(
        spec_containers=([] if requested is None else [{"name": name, "image": requested}]),
        status_containers=[
            {
                "name": name,
                "image": status_image,
                "image_id": image_id,
                "ready": False,
                "restart_count": 2,
            }
        ],
    )[0]


def _entity(entity_id: str, kind: str, containers: list[dict]) -> Entity:
    return Entity(
        id=entity_id,
        entity_type=(
            EntityType.RUNTIME_INSTANCE
            if kind == "KubernetesPod"
            else EntityType.WORKLOAD
        ),
        kind=kind,
        name=entity_id,
        source_system="kubernetes",
        observed_at=NOW,
        properties={"containers": containers},
    )


def _snapshot(
    *,
    deployment_ref: str = APP_REF,
    pod_ref: str = APP_REF,
    status_image: str = DIGEST_Y,
    image_id: str = f"containerd://{DIGEST_Z}",
) -> GraphSnapshot:
    deployment = normalize_regular_container_images(
        spec_containers=[{"name": "app", "image": deployment_ref}],
        spec_source_field="deployment.spec.template.spec.containers[].image",
    )
    pod = [_observation(requested=pod_ref, status_image=status_image, image_id=image_id)]
    return GraphSnapshot(
        snapshot_id="snapshot:sc3",
        collected_at=NOW,
        collector_name="sc3-test",
        collector_version="1",
        scope={"cluster": "test"},
        entities=[
            _entity("deployment:app", "KubernetesDeployment", deployment),
            _entity("pod:app", "KubernetesPod", pod),
        ],
    )


def _uses(snapshot: GraphSnapshot, source: str):
    return [
        item
        for item in snapshot.relationships
        if item.source_entity_id == source
        and item.relationship_type == RelationshipType.USES
    ]


def _identity(container: dict) -> KubernetesContainerImageObservation:
    return KubernetesContainerImageObservation.model_validate(
        container["image_identity"]
    )


@pytest.mark.parametrize(
    ("value", "role", "kind", "repository", "tag", "digest", "scheme"),
    [
        (
            APP_REF,
            ContainerImageSemanticRole.REQUESTED_IMAGE,
            ContainerImageReferenceKind.REPOSITORY_DIGEST,
            "ghcr.io/example/app",
            None,
            DIGEST_X,
            None,
        ),
        (
            "example/app:stable",
            ContainerImageSemanticRole.REQUESTED_IMAGE,
            ContainerImageReferenceKind.REPOSITORY_TAG,
            "docker.io/example/app",
            "stable",
            None,
            None,
        ),
        (
            DIGEST_X,
            ContainerImageSemanticRole.RUNTIME_STATUS_IMAGE,
            ContainerImageReferenceKind.DIGEST_ONLY,
            None,
            None,
            DIGEST_X,
            None,
        ),
        (
            f"docker-pullable://{APP_REF}",
            ContainerImageSemanticRole.RUNTIME_IMAGE_ID,
            ContainerImageReferenceKind.REPOSITORY_DIGEST,
            "ghcr.io/example/app",
            None,
            DIGEST_X,
            "docker-pullable",
        ),
        (
            f"containerd://{DIGEST_X}",
            ContainerImageSemanticRole.RUNTIME_IMAGE_ID,
            ContainerImageReferenceKind.DIGEST_ONLY,
            None,
            None,
            DIGEST_X,
            "containerd",
        ),
        (
            f"docker://{DIGEST_X}",
            ContainerImageSemanticRole.RUNTIME_IMAGE_ID,
            ContainerImageReferenceKind.DIGEST_ONLY,
            None,
            None,
            DIGEST_X,
            "docker",
        ),
        (
            APP_REF,
            ContainerImageSemanticRole.RUNTIME_IMAGE_ID,
            ContainerImageReferenceKind.REPOSITORY_DIGEST,
            "ghcr.io/example/app",
            None,
            DIGEST_X,
            None,
        ),
    ],
)
def test_structured_reference_parsing(
    value, role, kind, repository, tag, digest, scheme
):
    parsed = parse_container_image_observation(value, semantic_role=role)
    assert parsed.raw_value == value
    assert parsed.reference_kind == kind
    assert parsed.repository == repository
    assert parsed.tag == tag
    assert parsed.digest == digest
    assert parsed.scheme == scheme
    assert parsed.immutable_identity_eligible is (
        role == ContainerImageSemanticRole.REQUESTED_IMAGE
        and kind == ContainerImageReferenceKind.REPOSITORY_DIGEST
    )


@pytest.mark.parametrize(
    "value",
    [
        "repo@sha256:short",
        "repo@md5:" + "1" * 32,
        "repo@sha256:" + "g" * 64,
        "repo name:tag",
        "repo:",
        "@" + DIGEST_X,
    ],
)
@pytest.mark.parametrize(
    "role",
    list(ContainerImageSemanticRole),
)
def test_malformed_values_never_become_immutable(value, role):
    parsed = parse_container_image_observation(value, semantic_role=role)
    assert parsed.immutable_identity_eligible is False
    assert parsed.digest is None
    assert parsed.reference_kind == ContainerImageReferenceKind.MALFORMED


def test_reference_is_bounded_before_storage():
    value = "r" * (MAX_CONTAINER_IMAGE_REFERENCE_LENGTH + 1)
    parsed = parse_container_image_observation(
        value,
        semantic_role=ContainerImageSemanticRole.REQUESTED_IMAGE,
    )
    assert parsed.capture_state == ContainerImageCaptureState.REJECTED
    assert parsed.raw_value is None
    assert parsed.raw_value_length == len(value)
    assert parsed.rejection_reason == "reference_too_long"


def test_requested_runtime_fields_are_independent_and_role_provenanced():
    container = _observation(image_id=f"docker-pullable://{APP_REF}")
    identity = _identity(container)
    assert container["image"] == APP_REF
    assert container["runtime_status_image"] == DIGEST_Y
    assert container["image_id"] == f"docker-pullable://{APP_REF}"
    assert identity.requested_image.source_field == "pod.spec.containers[].image"
    assert identity.runtime_status_image.source_field.endswith("[].image")
    assert identity.runtime_image_id.source_field.endswith("[].imageID")
    assert {item.semantic_role for item in identity.identity_evidence_refs} == set(
        ContainerImageSemanticRole
    )


@pytest.mark.parametrize(
    ("status_image", "image_id"),
    [
        (DIGEST_Y, f"ghcr.io/example/app@{DIGEST_X}"),
        (DIGEST_Y, f"containerd://{DIGEST_Z}"),
        (f"ghcr.io/other/app@{DIGEST_Y}", f"docker://{DIGEST_Z}"),
    ],
)
def test_adversarial_runtime_values_never_replace_requested_artifact(
    status_image, image_id
):
    identity = _identity(_observation(status_image=status_image, image_id=image_id))
    assert identity.resolved_artifact_identity is not None
    assert identity.resolved_artifact_identity.normalized_reference == APP_REF
    assert identity.resolved_artifact_identity.digest == DIGEST_X
    assert identity.runtime_status_image.raw_value == status_image
    assert identity.runtime_image_id.raw_value == image_id


def test_tag_only_request_remains_mutable_even_with_exact_runtime_identity():
    container = _observation(
        requested="ghcr.io/example/app:latest",
        status_image=APP_REF,
        image_id=APP_REF,
    )
    identity = _identity(container)
    assert identity.requested_image.tag == "latest"
    assert identity.requested_image.digest is None
    assert identity.resolved_artifact_identity is None
    graph = augment_snapshot_with_container_images(
        GraphSnapshot(
            snapshot_id="snapshot:tag",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            entities=[_entity("pod:tag", "KubernetesPod", [container])],
        )
    )
    image = next(item for item in graph.entities if item.kind == "ContainerImage")
    assert image.properties["immutable"] is False
    assert image.properties["digest"] is None


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_name_join_is_order_independent(reverse):
    specs = [
        {"name": "app", "image": APP_REF},
        {"name": "envoy", "image": f"ghcr.io/example/envoy@{DIGEST_Y}"},
    ]
    statuses = [
        {"name": "envoy", "image": DIGEST_Z, "image_id": DIGEST_Z},
        {"name": "app", "image": DIGEST_Y, "image_id": DIGEST_X},
    ]
    if reverse:
        statuses.reverse()
    result = normalize_regular_container_images(
        spec_containers=specs,
        status_containers=statuses,
    )
    by_name = {item["name"]: _identity(item) for item in result}
    assert by_name["app"].requested_image.raw_value == APP_REF
    assert by_name["app"].runtime_status_image.raw_value == DIGEST_Y
    assert by_name["envoy"].requested_image.repository == "ghcr.io/example/envoy"
    assert by_name["envoy"].runtime_status_image.raw_value == DIGEST_Z


def test_duplicate_status_name_is_explicitly_ambiguous():
    result = normalize_regular_container_images(
        spec_containers=[{"name": "app", "image": APP_REF}],
        status_containers=[
            {"name": "app", "image": DIGEST_Y, "image_id": DIGEST_Y},
            {"name": "app", "image": DIGEST_Z, "image_id": DIGEST_Z},
        ],
    )
    identity = _identity(result[0])
    assert identity.join_state == ContainerImageJoinState.RUNTIME_STATUS_AMBIGUOUS
    assert identity.status_match_count == 2
    assert identity.runtime_status_image.capture_state == ContainerImageCaptureState.MISSING
    assert [item.raw_value for item in identity.ambiguous_runtime_status_images] == [
        DIGEST_Y,
        DIGEST_Z,
    ]


def test_missing_status_preserves_requested_identity():
    result = normalize_regular_container_images(
        spec_containers=[{"name": "app", "image": APP_REF}],
    )
    identity = _identity(result[0])
    assert identity.join_state == ContainerImageJoinState.RUNTIME_STATUS_MISSING
    assert identity.requested_image.raw_value == APP_REF
    assert identity.resolved_artifact_identity.digest == DIGEST_X


def test_missing_spec_never_invents_requested_identity():
    result = normalize_regular_container_images(
        spec_containers=[],
        status_containers=[
            {"name": "app", "image": APP_REF, "image_id": APP_REF}
        ],
    )
    identity = _identity(result[0])
    assert identity.join_state == ContainerImageJoinState.SPEC_MISSING
    assert identity.requested_image.capture_state == ContainerImageCaptureState.MISSING
    assert identity.resolved_artifact_identity is None
    assert result[0]["image"] is None


def test_duplicate_spec_name_is_explicit_and_does_not_choose_first():
    result = normalize_regular_container_images(
        spec_containers=[
            {"name": "app", "image": APP_REF},
            {"name": "app", "image": f"ghcr.io/example/app@{DIGEST_Y}"},
        ],
    )
    identity = _identity(result[0])
    assert identity.join_state == ContainerImageJoinState.SPEC_AMBIGUOUS
    assert identity.spec_match_count == 2
    assert identity.resolved_artifact_identity is None


def test_deployment_and_pod_exact_requested_identity_share_canonical_artifact():
    graph = augment_snapshot_with_container_images(_snapshot())
    deployment_use = _uses(graph, "deployment:app")[0]
    pod_use = _uses(graph, "pod:app")[0]
    assert deployment_use.target_entity_id == pod_use.target_entity_id
    assert deployment_use.target_entity_id == canonical_container_image_identity(
        normalized_reference=APP_REF,
        digest=DIGEST_X,
    ).canonical_id
    assert pod_use.properties["requested_image"] == APP_REF
    assert pod_use.properties["runtime_status_image"] == DIGEST_Y
    assert pod_use.properties["runtime_image_id"] == f"containerd://{DIGEST_Z}"
    assert pod_use.properties["resolution_method"] == "requested_immutable_reference"


def test_different_requested_digest_stays_distinct_despite_runtime_values():
    graph = augment_snapshot_with_container_images(
        _snapshot(pod_ref=f"ghcr.io/example/app@{DIGEST_Y}")
    )
    assert _uses(graph, "deployment:app")[0].target_entity_id != (
        _uses(graph, "pod:app")[0].target_entity_id
    )


def test_same_digest_different_repository_keeps_relationship_evidence_distinct():
    graph = augment_snapshot_with_container_images(
        _snapshot(pod_ref=f"ghcr.io/other/app@{DIGEST_X}")
    )
    deployment_use = _uses(graph, "deployment:app")[0]
    pod_use = _uses(graph, "pod:app")[0]
    # TC-1's accepted digest identity reuses the artifact entity. Repository
    # semantics remain distinct on each source relationship for SC-2.
    assert deployment_use.target_entity_id == pod_use.target_entity_id
    assert deployment_use.properties["requested_image"] == APP_REF
    assert pod_use.properties["requested_image"].startswith("ghcr.io/other/")


def test_identical_requested_artifact_is_not_duplicated():
    graph = augment_snapshot_with_container_images(_snapshot())
    images = [item for item in graph.entities if item.kind == "ContainerImage"]
    assert len(images) == 1
    assert images[0].external_id == DIGEST_X
    assert images[0].properties["digest"] == DIGEST_X


def test_multi_container_relationships_remain_container_scoped():
    containers = normalize_regular_container_images(
        spec_containers=[
            {"name": "app", "image": APP_REF},
            {"name": "envoy", "image": f"ghcr.io/example/envoy@{DIGEST_Y}"},
        ],
        status_containers=[
            {"name": "app", "image": DIGEST_Y, "image_id": DIGEST_Z},
            {"name": "envoy", "image": DIGEST_Z, "image_id": DIGEST_X},
        ],
    )
    graph = augment_snapshot_with_container_images(
        GraphSnapshot(
            snapshot_id="snapshot:multi",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            entities=[_entity("pod:multi", "KubernetesPod", containers)],
        )
    )
    uses = _uses(graph, "pod:multi")
    assert len(uses) == 2
    assert len({item.id for item in uses}) == 2
    assert {item.properties["container_name"] for item in uses} == {"app", "envoy"}
    assert {item.properties["requested_image"] for item in uses} == {
        APP_REF,
        f"ghcr.io/example/envoy@{DIGEST_Y}",
    }


def test_sc3_relationship_provenance_keeps_all_semantic_sources():
    relationship = _uses(augment_snapshot_with_container_images(_snapshot()), "pod:app")[0]
    assert relationship.provenance is not None
    assert relationship.provenance.linker_version == (
        KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION
    )
    refs = {item.reference_type: item for item in relationship.provenance.source_references}
    assert refs["container_image_reference"].reference == APP_REF
    assert refs["container_image_digest"].reference == DIGEST_X
    assert refs["kubernetes_requested_image_reference"].attributes[
        "source_field"
    ] == "pod.spec.containers[].image"
    assert refs["kubernetes_runtime_status_image"].reference == DIGEST_Y
    assert refs["kubernetes_runtime_image_id"].reference == f"containerd://{DIGEST_Z}"
    assert relationship.confidence is None


def test_snapshot_round_trip_preserves_requested_and_runtime_distinctions():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        save_snapshot(session, augment_snapshot_with_container_images(_snapshot()))
        loaded = load_snapshot(session, "snapshot:sc3")
    assert loaded is not None
    pod = next(item for item in loaded.entities if item.id == "pod:app")
    identity = _identity(pod.properties["containers"][0])
    assert identity.requested_image.raw_value == APP_REF
    assert identity.requested_image.repository == "ghcr.io/example/app"
    assert identity.requested_image.digest == DIGEST_X
    assert identity.runtime_status_image.raw_value == DIGEST_Y
    assert identity.runtime_image_id.raw_value == f"containerd://{DIGEST_Z}"
    pinned_use = _uses(loaded, "pod:app")[0]
    assert pinned_use.properties["image_identity"]["contract_version"] == (
        KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION
    )


def test_legacy_snapshot_loads_without_fabricated_sc3_semantics():
    legacy = GraphSnapshot(
        snapshot_id="snapshot:legacy",
        collected_at=NOW,
        collector_name="legacy",
        collector_version="1",
        entities=[
            _entity(
                "pod:legacy",
                "KubernetesPod",
                [{"name": "app", "image": "example/app:legacy"}],
            )
        ],
    )
    loaded = GraphSnapshot.model_validate_json(legacy.model_dump_json())
    container = loaded.entities[0].properties["containers"][0]
    assert container == {"name": "app", "image": "example/app:legacy"}
    assert "image_identity" not in container


def test_invalid_versioned_observation_does_not_fall_back_to_legacy_claim():
    container = {
        "name": "app",
        "image": APP_REF,
        "image_identity": {"contract_version": "unknown"},
    }
    graph = augment_snapshot_with_container_images(
        GraphSnapshot(
            snapshot_id="snapshot:invalid-contract",
            collected_at=NOW,
            collector_name="test",
            collector_version="1",
            entities=[_entity("pod:invalid", "KubernetesPod", [container])],
        )
    )
    assert not _uses(graph, "pod:invalid")
    assert not any(item.kind == "ContainerImage" for item in graph.entities)


def test_collector_uses_spec_and_status_inputs_instead_of_status_only():
    source = inspect.getsource(KubernetesCollector.collect)
    assert "pod.spec.containers" in source
    assert "pod.status.container_statuses" in source
    assert "normalize_regular_container_images" in source


@pytest.mark.parametrize(
    "forbidden",
    [
        "subprocess",
        "docker.from_env",
        "crictl",
        "kubectl",
        "requests.",
        "httpx",
        "openai",
        "embedding",
        "fuzzy",
        "evaluation.",
        "git ",
    ],
)
def test_identity_normalizer_has_no_external_or_inference_dependency(forbidden):
    source = inspect.getsource(
        __import__("app.services.container_image_identity", fromlist=["*"])
    ).lower()
    assert forbidden not in source


def test_frozen_candidate_and_downstream_contracts_remain_unchanged():
    assert CAUSAL_CANDIDATE_ADMISSION_POLICY_VERSION == (
        "causal-candidate-admission-v2"
    )
    assert CausalAnalysisRequest().lookback_minutes == 180
    assert CAUSAL_RELEVANCE_POLICY_VERSION == "causal-relevance-v1"
    source = inspect.getsource(analyze_incident_change_events)
    assert "score +=" not in source


def test_contract_version_is_explicit_and_no_graph_entity_family_is_added():
    assert KUBERNETES_CONTAINER_IMAGE_IDENTITY_VERSION == (
        "kubernetes-container-image-identity-v1"
    )
    graph = augment_snapshot_with_container_images(_snapshot())
    assert {item.kind for item in graph.entities} == {
        "KubernetesDeployment",
        "KubernetesPod",
        "ContainerImage",
    }
