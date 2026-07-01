from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


from app.models.changes import (
    ChangeCategory,
    NormalizedChange,
)
from app.models.incidents import (
    IncidentAnalysis,
    RootCauseHypothesis,
)
from app.models.recommendations import (
    RecommendationActionType,
    RecommendationRisk,
    RecommendationStatus,
    RecommendationStep,
    RemediationRecommendation,
)
from app.models.signals import (
    NormalizedSignal,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    RelationshipType,
)


ALGORITHM_VERSION = (
    "deterministic-remediation-0.1.0"
)


def _recommendation_id(
    analysis_id: str,
    hypothesis_id: str,
) -> str:
    value = (
        f"{analysis_id}|"
        f"{hypothesis_id}|"
        f"{ALGORITHM_VERSION}"
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"recommendation:{digest}"


def _extract_images(
    value: Any,
) -> set[str]:
    images: set[str] = set()

    if isinstance(value, dict):
        for key, item in value.items():
            if (
                key == "image"
                and isinstance(item, str)
            ):
                images.add(item)

            images.update(
                _extract_images(item)
            )

    elif isinstance(value, list):
        for item in value:
            images.update(
                _extract_images(item)
            )

    return images


def _previous_image(
    change: NormalizedChange,
) -> str | None:
    before_images = _extract_images(
        change.before
    )

    after_images = _extract_images(
        change.after
    )

    removed_images = sorted(
        before_images - after_images
    )

    if removed_images:
        return removed_images[0]

    if before_images:
        return sorted(before_images)[0]

    return None


def _new_image(
    change: NormalizedChange,
) -> str | None:
    before_images = _extract_images(
        change.before
    )

    after_images = _extract_images(
        change.after
    )

    added_images = sorted(
        after_images - before_images
    )

    if added_images:
        return added_images[0]

    if after_images:
        return sorted(after_images)[0]

    return None


def _previous_replicas(
    change: NormalizedChange,
) -> int | None:
    for field, values in (
        change.changed_fields.items()
    ):
        if "replicas" not in field.lower():
            continue

        before = values.get("before")

        if isinstance(before, int):
            return before

    return None


def _parent_deployment(
    snapshot: GraphSnapshot,
    entity_id: str | None,
) -> Entity | None:
    if not entity_id:
        return None

    entities = {
        entity.id: entity
        for entity in snapshot.entities
    }

    entity = entities.get(entity_id)

    if (
        entity
        and entity.kind
        == "KubernetesDeployment"
    ):
        return entity

    current_ids = {entity_id}

    for _ in range(3):
        next_ids: set[str] = set()

        for relationship in (
            snapshot.relationships
        ):
            if (
                relationship
                .target_entity_id
                not in current_ids
            ):
                continue

            if (
                relationship
                .relationship_type
                not in {
                    RelationshipType.RUNS,
                    RelationshipType.OWNS,
                }
            ):
                continue

            parent = entities.get(
                relationship
                .source_entity_id
            )

            if parent is None:
                continue

            if (
                parent.kind
                == "KubernetesDeployment"
            ):
                return parent

            next_ids.add(parent.id)

        if not next_ids:
            break

        current_ids = next_ids

    return None


def _deployment_using_image(
    snapshot: GraphSnapshot,
    image_entity_id: str | None,
) -> Entity | None:
    if not image_entity_id:
        return None

    entities = {
        entity.id: entity
        for entity in snapshot.entities
    }

    for relationship in (
        snapshot.relationships
    ):
        if (
            relationship
            .relationship_type
            != RelationshipType.USES
        ):
            continue

        if (
            relationship
            .target_entity_id
            != image_entity_id
        ):
            continue

        source = entities.get(
            relationship
            .source_entity_id
        )

        if (
            source
            and source.kind
            == "KubernetesDeployment"
        ):
            return source

    return None


def _target_deployment(
    hypothesis: RootCauseHypothesis,
    analysis: IncidentAnalysis,
    snapshot: GraphSnapshot,
) -> Entity | None:
    entities = {
        entity.id: entity
        for entity in snapshot.entities
    }

    if hypothesis.changed_entity_id:
        changed = entities.get(
            hypothesis.changed_entity_id
        )

        if (
            changed
            and changed.kind
            == "KubernetesDeployment"
        ):
            return changed

    if (
        hypothesis.changed_entity_kind
        == "ContainerImage"
    ):
        deployment = (
            _deployment_using_image(
                snapshot=snapshot,
                image_entity_id=(
                    hypothesis
                    .changed_entity_id
                ),
            )
        )

        if deployment:
            return deployment

    return _parent_deployment(
        snapshot=snapshot,
        entity_id=(
            analysis.symptom_entity_id
        ),
    )


def _namespace(
    deployment: Entity | None,
    fallback: str | None,
) -> str | None:
    if deployment:
        value = deployment.properties.get(
            "namespace"
        )

        if isinstance(value, str):
            return value

    return fallback


def _evidence_ids(
    hypothesis: RootCauseHypothesis,
) -> list[str]:
    return [
        evidence.evidence_id
        for evidence in (
            hypothesis
            .supporting_evidence
            + hypothesis
            .counter_evidence
        )
    ]


def _image_recommendation(
    analysis: IncidentAnalysis,
    hypothesis: RootCauseHypothesis,
    change: NormalizedChange,
    deployment: Entity | None,
) -> RemediationRecommendation:
    namespace = _namespace(
        deployment,
        analysis.namespace,
    )

    deployment_name = (
        deployment.name
        if deployment
        else (
            hypothesis
            .changed_entity_name
            or "unknown-deployment"
        )
    )

    previous_image = (
        _previous_image(change)
    )

    new_image = _new_image(change)

    target = (
        f"Deployment/{deployment_name}"
    )

    rationale = (
        f"{hypothesis.title} is ranked "
        f"#{hypothesis.rank} with "
        f"{hypothesis.score:.0%} confidence. "
        f"The affected workload is connected "
        f"to {target}"
    )

    if new_image:
        rationale += (
            f", which introduced image "
            f"{new_image}"
        )

    rationale += "."

    namespace_argument = (
        f" -n {namespace}"
        if namespace
        else ""
    )

    steps = [
        RecommendationStep(
            order=1,
            title="Inspect rollout history",
            description=(
                "Confirm the previous stable "
                "Deployment revision before "
                "making a change."
            ),
            command=(
                "kubectl rollout history "
                f"deployment/{deployment_name}"
                f"{namespace_argument}"
            ),
            expected_result=(
                "A previous known-good revision "
                "is available."
            ),
        ),
        RecommendationStep(
            order=2,
            title="Roll back the Deployment",
            description=(
                "Restore the previous Deployment "
                "revision after operator approval."
            ),
            command=(
                "kubectl rollout undo "
                f"deployment/{deployment_name}"
                f"{namespace_argument}"
            ),
            requires_approval=True,
            expected_result=(
                "The Deployment begins a new "
                "rollout using the previous "
                "revision."
            ),
        ),
        RecommendationStep(
            order=3,
            title="Wait for rollout completion",
            description=(
                "Confirm that the rollback "
                "successfully reaches Ready state."
            ),
            command=(
                "kubectl rollout status "
                f"deployment/{deployment_name}"
                f"{namespace_argument} "
                "--timeout=5m"
            ),
            expected_result=(
                "The rollout completes "
                "successfully."
            ),
        ),
        RecommendationStep(
            order=4,
            title="Check runtime health",
            description=(
                "Confirm that Pods are running "
                "and image-pull failures stop."
            ),
            command=(
                "kubectl get pods"
                f"{namespace_argument} "
                "-o wide"
            ),
            expected_result=(
                "Replacement Pods are Ready and "
                "no new ImagePullBackOff events "
                "are occurring."
            ),
        ),
    ]

    return RemediationRecommendation(
        recommendation_id=(
            _recommendation_id(
                analysis.analysis_id,
                hypothesis.hypothesis_id,
            )
        ),
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        analysis_id=(
            analysis.analysis_id
        ),
        hypothesis_id=(
            hypothesis.hypothesis_id
        ),
        signal_id=analysis.signal_id,
        change_id=hypothesis.change_id,
        generated_at=datetime.now(
            timezone.utc
        ),
        title=(
            f"Roll back {target}"
        ),
        rationale=rationale,
        action_type=(
            RecommendationActionType
            .ROLLBACK_DEPLOYMENT
        ),
        status=(
            RecommendationStatus.PROPOSED
        ),
        confidence=hypothesis.score,
        risk=RecommendationRisk.MEDIUM,
        cluster_name=(
            analysis.cluster_name
        ),
        namespace=namespace,
        target_entity_id=(
            deployment.id
            if deployment
            else hypothesis
            .changed_entity_id
        ),
        target_entity_kind=(
            "KubernetesDeployment"
        ),
        target_entity_name=(
            deployment_name
        ),
        requires_approval=True,
        steps=steps,
        expected_outcome=(
            "The previous known-good Deployment "
            "revision becomes active, affected "
            "Pods reach Ready state and image "
            "pull failures stop."
        ),
        verification_checks=[
            (
                "Deployment rollout completes "
                "successfully."
            ),
            (
                "Desired and available replica "
                "counts match."
            ),
            (
                "Affected Pods reach Ready state."
            ),
            (
                "No new ErrImagePull or "
                "ImagePullBackOff events appear."
            ),
        ],
        safety_notes=[
            (
                "Review the rollout history "
                "before running the rollback."
            ),
            (
                "Confirm that the previous "
                "revision is compatible with "
                "current configuration and data."
            ),
            (
                "Update the Git or GitOps source "
                "of truth so reconciliation does "
                "not restore the broken image."
            ),
            (
                "Topo AI is providing a command "
                "preview only; it has not executed "
                "the rollback."
            ),
        ],
        evidence_ids=(
            _evidence_ids(hypothesis)
        ),
        attributes={
            "previous_image": (
                previous_image
            ),
            "introduced_image": (
                new_image
            ),
            "graph_distance": (
                hypothesis.graph_distance
            ),
            "minutes_before_signal": (
                hypothesis
                .minutes_before_signal
            ),
        },
    )


def _scaling_recommendation(
    analysis: IncidentAnalysis,
    hypothesis: RootCauseHypothesis,
    change: NormalizedChange,
    deployment: Entity | None,
) -> RemediationRecommendation:
    namespace = _namespace(
        deployment,
        analysis.namespace,
    )

    deployment_name = (
        deployment.name
        if deployment
        else (
            hypothesis
            .changed_entity_name
            or "unknown-deployment"
        )
    )

    previous_replicas = (
        _previous_replicas(change)
    )

    namespace_argument = (
        f" -n {namespace}"
        if namespace
        else ""
    )

    scale_command = None

    if previous_replicas is not None:
        scale_command = (
            "kubectl scale "
            f"deployment/{deployment_name} "
            f"--replicas={previous_replicas}"
            f"{namespace_argument}"
        )

    steps = [
        RecommendationStep(
            order=1,
            title="Inspect current replica state",
            description=(
                "Confirm desired, current and "
                "available replica counts."
            ),
            command=(
                "kubectl get deployment "
                f"{deployment_name}"
                f"{namespace_argument}"
            ),
        ),
        RecommendationStep(
            order=2,
            title="Restore the prior replica count",
            description=(
                "Restore the known previous "
                "replica count after approval."
            ),
            command=scale_command,
            requires_approval=True,
            expected_result=(
                "The Deployment returns to the "
                "previous desired replica count."
            ),
        ),
        RecommendationStep(
            order=3,
            title="Verify availability",
            description=(
                "Wait for the Deployment to "
                "reach the restored state."
            ),
            command=(
                "kubectl rollout status "
                f"deployment/{deployment_name}"
                f"{namespace_argument} "
                "--timeout=5m"
            ),
        ),
    ]

    return RemediationRecommendation(
        recommendation_id=(
            _recommendation_id(
                analysis.analysis_id,
                hypothesis.hypothesis_id,
            )
        ),
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        analysis_id=analysis.analysis_id,
        hypothesis_id=(
            hypothesis.hypothesis_id
        ),
        signal_id=analysis.signal_id,
        change_id=hypothesis.change_id,
        generated_at=datetime.now(
            timezone.utc
        ),
        title=(
            "Restore the previous replica count"
        ),
        rationale=(
            f"The scaling change is ranked "
            f"#{hypothesis.rank} with "
            f"{hypothesis.score:.0%} confidence."
        ),
        action_type=(
            RecommendationActionType
            .RESTORE_REPLICA_COUNT
        ),
        status=(
            RecommendationStatus.PROPOSED
        ),
        confidence=hypothesis.score,
        risk=RecommendationRisk.MEDIUM,
        cluster_name=(
            analysis.cluster_name
        ),
        namespace=namespace,
        target_entity_id=(
            deployment.id
            if deployment
            else hypothesis
            .changed_entity_id
        ),
        target_entity_kind=(
            "KubernetesDeployment"
        ),
        target_entity_name=(
            deployment_name
        ),
        requires_approval=True,
        steps=steps,
        expected_outcome=(
            "The workload returns to its prior "
            "capacity and availability state."
        ),
        verification_checks=[
            (
                "Desired replicas match the "
                "previous value."
            ),
            (
                "Available replicas equal desired "
                "replicas."
            ),
            (
                "The triggering failure signal "
                "stops recurring."
            ),
        ],
        safety_notes=[
            (
                "Confirm that reducing capacity "
                "will not create additional load "
                "or availability risk."
            ),
            (
                "Update the source-of-truth "
                "configuration after applying "
                "the change."
            ),
        ],
        evidence_ids=(
            _evidence_ids(hypothesis)
        ),
        attributes={
            "previous_replicas": (
                previous_replicas
            ),
        },
    )


def _generic_recommendation(
    analysis: IncidentAnalysis,
    hypothesis: RootCauseHypothesis,
    change: NormalizedChange,
    deployment: Entity | None,
) -> RemediationRecommendation:
    namespace = _namespace(
        deployment,
        analysis.namespace,
    )

    target_name = (
        deployment.name
        if deployment
        else (
            hypothesis
            .changed_entity_name
            or "changed-resource"
        )
    )

    target_kind = (
        deployment.kind
        if deployment
        else (
            hypothesis
            .changed_entity_kind
            or "Unknown"
        )
    )

    return RemediationRecommendation(
        recommendation_id=(
            _recommendation_id(
                analysis.analysis_id,
                hypothesis.hypothesis_id,
            )
        ),
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        analysis_id=analysis.analysis_id,
        hypothesis_id=(
            hypothesis.hypothesis_id
        ),
        signal_id=analysis.signal_id,
        change_id=hypothesis.change_id,
        generated_at=datetime.now(
            timezone.utc
        ),
        title=(
            f"Review and revert "
            f"{target_kind}/{target_name}"
        ),
        rationale=(
            f"{hypothesis.title} is ranked "
            f"#{hypothesis.rank} with "
            f"{hypothesis.score:.0%} confidence. "
            "The before-and-after change evidence "
            "should be reviewed before restoring "
            "the previous configuration."
        ),
        action_type=(
            RecommendationActionType
            .RESTORE_CONFIGURATION
        ),
        status=(
            RecommendationStatus.PROPOSED
        ),
        confidence=hypothesis.score,
        risk=RecommendationRisk.MEDIUM,
        cluster_name=(
            analysis.cluster_name
        ),
        namespace=namespace,
        target_entity_id=(
            deployment.id
            if deployment
            else hypothesis
            .changed_entity_id
        ),
        target_entity_kind=target_kind,
        target_entity_name=target_name,
        requires_approval=True,
        steps=[
            RecommendationStep(
                order=1,
                title="Review the field-level diff",
                description=(
                    "Inspect the stored before and "
                    "after values for the candidate "
                    "change."
                ),
            ),
            RecommendationStep(
                order=2,
                title="Restore through source of truth",
                description=(
                    "Revert the configuration in "
                    "Git, Helm, Argo CD or the "
                    "authoritative deployment "
                    "mechanism."
                ),
                requires_approval=True,
            ),
            RecommendationStep(
                order=3,
                title="Verify the affected workload",
                description=(
                    "Confirm that the workload "
                    "returns to Ready state and the "
                    "failure signal stops."
                ),
            ),
        ],
        expected_outcome=(
            "The changed resource returns to its "
            "previous known-good configuration "
            "and the affected workload recovers."
        ),
        verification_checks=[
            (
                "The expected configuration is "
                "visible in a fresh snapshot."
            ),
            (
                "The affected entity is healthy."
            ),
            (
                "The triggering signal no longer "
                "recurs."
            ),
        ],
        safety_notes=[
            (
                "Do not directly patch a resource "
                "managed by GitOps without also "
                "updating its source of truth."
            ),
            (
                "Review dependencies and blast "
                "radius before reverting."
            ),
        ],
        evidence_ids=(
            _evidence_ids(hypothesis)
        ),
        attributes={
            "changed_fields": sorted(
                change.changed_fields.keys()
            ),
        },
    )


def generate_recommendations(
    analysis: IncidentAnalysis,
    signal: NormalizedSignal,
    snapshot: GraphSnapshot,
    changes_by_id: dict[
        str,
        NormalizedChange,
    ],
    minimum_score: float = 0.50,
    max_recommendations: int = 3,
) -> list[
    RemediationRecommendation
]:
    recommendations: list[
        RemediationRecommendation
    ] = []

    for hypothesis in (
        analysis.hypotheses
    ):
        if (
            hypothesis.score
            < minimum_score
        ):
            continue

        change = changes_by_id.get(
            hypothesis.change_id
        )

        if change is None:
            continue

        deployment = _target_deployment(
            hypothesis=hypothesis,
            analysis=analysis,
            snapshot=snapshot,
        )

        if (
            hypothesis.category
            in {
                ChangeCategory.IMAGE,
                ChangeCategory.DEPLOYMENT,
            }
            and (
                signal.category.value
                in {
                    "image",
                    "health",
                    "availability",
                }
            )
        ):
            recommendation = (
                _image_recommendation(
                    analysis=analysis,
                    hypothesis=hypothesis,
                    change=change,
                    deployment=deployment,
                )
            )

        elif (
            hypothesis.category
            == ChangeCategory.SCALING
        ):
            recommendation = (
                _scaling_recommendation(
                    analysis=analysis,
                    hypothesis=hypothesis,
                    change=change,
                    deployment=deployment,
                )
            )

        else:
            recommendation = (
                _generic_recommendation(
                    analysis=analysis,
                    hypothesis=hypothesis,
                    change=change,
                    deployment=deployment,
                )
            )

        recommendations.append(
            recommendation
        )

        if (
            len(recommendations)
            >= max_recommendations
        ):
            break

    return recommendations