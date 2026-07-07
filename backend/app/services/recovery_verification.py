from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from app.models.incidents import (
    IncidentAnalysis,
)
from app.models.recommendations import (
    RecommendationActionType,
    RemediationRecommendation,
)
from app.models.recovery import (
    RecoveryCheck,
    RecoveryCheckStatus,
    RecoveryStatus,
    RecoveryVerification,
)
from app.models.signals import (
    NormalizedSignal,
    SignalSeverity,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)


ALGORITHM_VERSION = (
    "deterministic-recovery-0.1.0"
)


CHECK_WEIGHTS = {
    "post_snapshot_after_action": 0.10,
    "target_present": 0.15,
    "workload_ready": 0.25,
    "expected_image_restored": 0.25,
    "failure_signal_stopped": 0.25,
}


def _verification_id(
    recommendation_id: str,
    post_snapshot_id: str,
) -> str:
    value = (
        f"{recommendation_id}|"
        f"{post_snapshot_id}|"
        f"{ALGORITHM_VERSION}"
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"recovery:{digest}"


def _as_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _check(
    code: str,
    title: str,
    status: RecoveryCheckStatus,
    summary: str,
    source_type: str,
    source_id: str,
    checked_at: datetime,
    expected: str | None = None,
    observed: str | None = None,
    attributes: (
        dict[str, Any] | None
    ) = None,
) -> RecoveryCheck:
    return RecoveryCheck(
        code=code,
        title=title,
        status=status,
        summary=summary,
        expected=expected,
        observed=observed,
        source_type=source_type,
        source_id=source_id,
        checked_at=checked_at,
        attributes=attributes or {},
    )


def _find_target_entity(
    snapshot: GraphSnapshot,
    recommendation: (
        RemediationRecommendation
    ),
) -> Entity | None:
    entities_by_id = {
        entity.id: entity
        for entity in snapshot.entities
    }

    if recommendation.target_entity_id:
        exact = entities_by_id.get(
            recommendation.target_entity_id
        )

        if exact:
            return exact

    for entity in snapshot.entities:
        if (
            recommendation
            .target_entity_kind
            and entity.kind
            != recommendation
            .target_entity_kind
        ):
            continue

        if (
            recommendation
            .target_entity_name
            and entity.name
            != recommendation
            .target_entity_name
        ):
            continue

        entity_namespace = (
            entity.properties.get(
                "namespace"
            )
        )

        if (
            recommendation.namespace
            and entity_namespace
            != recommendation.namespace
        ):
            continue

        return entity

    return None


def _integer_property(
    entity: Entity,
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = entity.properties.get(
            key
        )

        if (
            isinstance(value, int)
            and not isinstance(value, bool)
        ):
            return value

    return None


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


def _target_related_signal(
    signal: NormalizedSignal,
    original_signal: NormalizedSignal,
    recommendation: (
        RemediationRecommendation
    ),
) -> bool:
    if (
        signal.involved_entity_id
        and signal.involved_entity_id
        == recommendation
        .target_entity_id
    ):
        return True

    target_name = (
        recommendation
        .target_entity_name
        or ""
    )

    object_name = (
        signal.involved_object_name
        or ""
    )

    if (
        target_name
        and target_name in object_name
    ):
        return True

    if (
        signal.reason
        and original_signal.reason
        and signal.reason
        == original_signal.reason
        and signal.category
        == original_signal.category
    ):
        return True

    return False


def _verification_confidence(
    checks: list[RecoveryCheck],
) -> float:
    weighted_pass = 0.0
    total_weight = 0.0

    for check in checks:
        weight = CHECK_WEIGHTS.get(
            check.code,
            0.0,
        )

        total_weight += weight

        if (
            check.status
            == RecoveryCheckStatus.PASS
        ):
            weighted_pass += weight

        elif (
            check.status
            == RecoveryCheckStatus.UNKNOWN
        ):
            weighted_pass += (
                weight * 0.25
            )

    if total_weight == 0:
        return 0.0

    return round(
        weighted_pass / total_weight,
        4,
    )


def verify_recovery(
    recommendation: (
        RemediationRecommendation
    ),
    analysis: IncidentAnalysis,
    original_signal: NormalizedSignal,
    pre_snapshot: GraphSnapshot,
    post_snapshot: GraphSnapshot,
    signals_after_action: list[
        NormalizedSignal
    ],
) -> RecoveryVerification:
    generated_at = datetime.now(
        timezone.utc
    )

    if recommendation.applied_at is None:
        raise ValueError(
            "Recommendation does not contain "
            "an applied_at timestamp."
        )

    applied_at = _as_utc(
        recommendation.applied_at
    )

    checks: list[RecoveryCheck] = []
    warnings: list[str] = []

    post_collected_at = _as_utc(
        post_snapshot.collected_at
    )

    if post_collected_at > applied_at:
        checks.append(
            _check(
                code=(
                    "post_snapshot_after_action"
                ),
                title=(
                    "Post-remediation snapshot"
                ),
                status=(
                    RecoveryCheckStatus.PASS
                ),
                summary=(
                    "The verification snapshot "
                    "was captured after the "
                    "recommendation was applied."
                ),
                expected=(
                    "Snapshot captured after "
                    f"{applied_at.isoformat()}"
                ),
                observed=(
                    post_collected_at
                    .isoformat()
                ),
                source_type="snapshot",
                source_id=(
                    post_snapshot.snapshot_id
                ),
                checked_at=generated_at,
            )
        )

    else:
        checks.append(
            _check(
                code=(
                    "post_snapshot_after_action"
                ),
                title=(
                    "Post-remediation snapshot"
                ),
                status=(
                    RecoveryCheckStatus.FAIL
                ),
                summary=(
                    "The supplied snapshot was "
                    "captured before the action "
                    "was marked as applied."
                ),
                expected=(
                    "A snapshot newer than the "
                    "applied timestamp"
                ),
                observed=(
                    post_collected_at
                    .isoformat()
                ),
                source_type="snapshot",
                source_id=(
                    post_snapshot.snapshot_id
                ),
                checked_at=generated_at,
            )
        )

    target = _find_target_entity(
        snapshot=post_snapshot,
        recommendation=recommendation,
    )

    if target:
        checks.append(
            _check(
                code="target_present",
                title="Target resource exists",
                status=(
                    RecoveryCheckStatus.PASS
                ),
                summary=(
                    f"{target.kind}/{target.name} "
                    "is present in the "
                    "post-remediation topology."
                ),
                expected=(
                    "Target resource remains "
                    "present"
                ),
                observed=(
                    f"{target.kind}/"
                    f"{target.name}"
                ),
                source_type="entity",
                source_id=target.id,
                checked_at=generated_at,
            )
        )

    else:
        checks.append(
            _check(
                code="target_present",
                title="Target resource exists",
                status=(
                    RecoveryCheckStatus.FAIL
                ),
                summary=(
                    "The remediation target could "
                    "not be found in the "
                    "post-remediation snapshot."
                ),
                expected=(
                    f"{recommendation.target_entity_kind}/"
                    f"{recommendation.target_entity_name}"
                ),
                observed="Not found",
                source_type="snapshot",
                source_id=(
                    post_snapshot.snapshot_id
                ),
                checked_at=generated_at,
            )
        )

    if (
        target
        and target.kind
        == "KubernetesDeployment"
    ):
        desired = _integer_property(
            target,
            (
                "desired_replicas",
                "replicas",
                "spec_replicas",
            ),
        )

        available = _integer_property(
            target,
            (
                "available_replicas",
                "ready_replicas",
                "current_replicas",
            ),
        )

        if (
            desired is not None
            and available is not None
        ):
            if (
                desired > 0
                and available >= desired
            ):
                readiness_status = (
                    RecoveryCheckStatus.PASS
                )

                readiness_summary = (
                    "The Deployment has reached "
                    "its desired available replica "
                    "count."
                )

            else:
                readiness_status = (
                    RecoveryCheckStatus.FAIL
                )

                readiness_summary = (
                    "The Deployment has not "
                    "reached its desired available "
                    "replica count."
                )

            checks.append(
                _check(
                    code="workload_ready",
                    title="Workload readiness",
                    status=readiness_status,
                    summary=(
                        readiness_summary
                    ),
                    expected=(
                        f"available >= desired "
                        f"({desired})"
                    ),
                    observed=(
                        f"desired={desired}, "
                        f"available={available}"
                    ),
                    source_type="entity",
                    source_id=target.id,
                    checked_at=generated_at,
                    attributes={
                        "desired_replicas": (
                            desired
                        ),
                        "available_replicas": (
                            available
                        ),
                    },
                )
            )

        else:
            checks.append(
                _check(
                    code="workload_ready",
                    title="Workload readiness",
                    status=(
                        RecoveryCheckStatus
                        .UNKNOWN
                    ),
                    summary=(
                        "Replica readiness values "
                        "were not available in the "
                        "target entity properties."
                    ),
                    source_type="entity",
                    source_id=target.id,
                    checked_at=generated_at,
                )
            )

    else:
        checks.append(
            _check(
                code="workload_ready",
                title="Workload readiness",
                status=(
                    RecoveryCheckStatus.UNKNOWN
                ),
                summary=(
                    "Deployment readiness could "
                    "not be evaluated because the "
                    "target Deployment was not "
                    "available."
                ),
                source_type="snapshot",
                source_id=(
                    post_snapshot.snapshot_id
                ),
                checked_at=generated_at,
            )
        )

    expected_image = (
        recommendation.attributes.get(
            "previous_image"
        )
    )

    expected_image = (
        expected_image
        if isinstance(
            expected_image,
            str,
        )
        else None
    )

    current_images = (
        _extract_images(
            target.properties
        )
        if target
        else set()
    )

    if (
        recommendation.action_type
        == RecommendationActionType
        .ROLLBACK_DEPLOYMENT
    ):
        if not expected_image:
            checks.append(
                _check(
                    code=(
                        "expected_image_restored"
                    ),
                    title="Previous image restored",
                    status=(
                        RecoveryCheckStatus
                        .UNKNOWN
                    ),
                    summary=(
                        "The recommendation did "
                        "not retain a previous image "
                        "reference for comparison."
                    ),
                    source_type=(
                        "recommendation"
                    ),
                    source_id=(
                        recommendation
                        .recommendation_id
                    ),
                    checked_at=generated_at,
                )
            )

        elif expected_image in current_images:
            checks.append(
                _check(
                    code=(
                        "expected_image_restored"
                    ),
                    title="Previous image restored",
                    status=(
                        RecoveryCheckStatus.PASS
                    ),
                    summary=(
                        "The target Deployment is "
                        "using the expected previous "
                        "image."
                    ),
                    expected=expected_image,
                    observed=", ".join(
                        sorted(current_images)
                    ),
                    source_type="entity",
                    source_id=(
                        target.id
                        if target
                        else post_snapshot
                        .snapshot_id
                    ),
                    checked_at=generated_at,
                )
            )

        elif current_images:
            checks.append(
                _check(
                    code=(
                        "expected_image_restored"
                    ),
                    title="Previous image restored",
                    status=(
                        RecoveryCheckStatus.FAIL
                    ),
                    summary=(
                        "The expected previous "
                        "image is not present on the "
                        "target Deployment."
                    ),
                    expected=expected_image,
                    observed=", ".join(
                        sorted(current_images)
                    ),
                    source_type="entity",
                    source_id=(
                        target.id
                        if target
                        else post_snapshot
                        .snapshot_id
                    ),
                    checked_at=generated_at,
                )
            )

        else:
            checks.append(
                _check(
                    code=(
                        "expected_image_restored"
                    ),
                    title="Previous image restored",
                    status=(
                        RecoveryCheckStatus
                        .UNKNOWN
                    ),
                    summary=(
                        "No image references were "
                        "available on the target "
                        "entity."
                    ),
                    expected=expected_image,
                    source_type="snapshot",
                    source_id=(
                        post_snapshot.snapshot_id
                    ),
                    checked_at=generated_at,
                )
            )

    else:
        checks.append(
            _check(
                code=(
                    "expected_image_restored"
                ),
                title="Expected configuration",
                status=(
                    RecoveryCheckStatus.UNKNOWN
                ),
                summary=(
                    "Image restoration is not the "
                    "primary check for this action "
                    "type."
                ),
                source_type="recommendation",
                source_id=(
                    recommendation
                    .recommendation_id
                ),
                checked_at=generated_at,
            )
        )

    recurring_failures = [
        signal
        for signal in signals_after_action
        if (
            signal.last_observed_at
            > applied_at
            and signal.severity
            in {
                SignalSeverity.WARNING,
                SignalSeverity.ERROR,
                SignalSeverity.CRITICAL,
            }
            and _target_related_signal(
                signal=signal,
                original_signal=(
                    original_signal
                ),
                recommendation=(
                    recommendation
                ),
            )
        )
    ]

    if recurring_failures:
        checks.append(
            _check(
                code=(
                    "failure_signal_stopped"
                ),
                title=(
                    "Failure signal stopped"
                ),
                status=(
                    RecoveryCheckStatus.FAIL
                ),
                summary=(
                    f"{len(recurring_failures)} "
                    "related warning or failure "
                    "signals were observed after "
                    "the remediation was applied."
                ),
                expected=(
                    "No related warning, error or "
                    "critical signals after action"
                ),
                observed=", ".join(
                    sorted(
                        {
                            (
                                signal.reason
                                or signal.title
                            )
                            for signal
                            in recurring_failures
                        }
                    )
                ),
                source_type="signal",
                source_id=(
                    recurring_failures[0]
                    .signal_id
                ),
                checked_at=generated_at,
                attributes={
                    "signal_ids": [
                        signal.signal_id
                        for signal
                        in recurring_failures
                    ],
                },
            )
        )

    else:
        checks.append(
            _check(
                code=(
                    "failure_signal_stopped"
                ),
                title=(
                    "Failure signal stopped"
                ),
                status=(
                    RecoveryCheckStatus.PASS
                ),
                summary=(
                    "No related warning, error or "
                    "critical signals were "
                    "observed after the remediation "
                    "was applied."
                ),
                expected=(
                    "No recurring failure signals"
                ),
                observed="None",
                source_type="signal",
                source_id=(
                    original_signal.signal_id
                ),
                checked_at=generated_at,
            )
        )

    passed_count = sum(
        check.status
        == RecoveryCheckStatus.PASS
        for check in checks
    )

    failed_count = sum(
        check.status
        == RecoveryCheckStatus.FAIL
        for check in checks
    )

    unknown_count = sum(
        check.status
        == RecoveryCheckStatus.UNKNOWN
        for check in checks
    )

    confidence = (
        _verification_confidence(
            checks
        )
    )

    if failed_count > 0:
        status = RecoveryStatus.FAILED

        summary = (
            "Recovery was not confirmed because "
            f"{failed_count} verification check"
            f"{'' if failed_count == 1 else 's'} "
            "failed."
        )

    elif unknown_count == 0:
        status = RecoveryStatus.VERIFIED

        summary = (
            "Recovery was verified. The target "
            "workload is healthy, the expected "
            "state is present and the triggering "
            "failure signal has stopped."
        )

    else:
        status = (
            RecoveryStatus.INCONCLUSIVE
        )

        summary = (
            "No verification check failed, but "
            f"{unknown_count} check"
            f"{'' if unknown_count == 1 else 's'} "
            "could not be evaluated."
        )

    return RecoveryVerification(
        verification_id=(
            _verification_id(
                recommendation_id=(
                    recommendation
                    .recommendation_id
                ),
                post_snapshot_id=(
                    post_snapshot.snapshot_id
                ),
            )
        ),
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        recommendation_id=(
            recommendation
            .recommendation_id
        ),
        analysis_id=(
            recommendation.analysis_id
        ),
        signal_id=(
            recommendation.signal_id
        ),
        pre_snapshot_id=(
            pre_snapshot.snapshot_id
        ),
        post_snapshot_id=(
            post_snapshot.snapshot_id
        ),
        generated_at=generated_at,
        applied_at=applied_at,
        status=status,
        confidence=confidence,
        summary=summary,
        cluster_name=(
            recommendation.cluster_name
        ),
        namespace=(
            recommendation.namespace
        ),
        target_entity_id=(
            target.id
            if target
            else recommendation
            .target_entity_id
        ),
        target_entity_kind=(
            target.kind
            if target
            else recommendation
            .target_entity_kind
        ),
        target_entity_name=(
            target.name
            if target
            else recommendation
            .target_entity_name
        ),
        passed_count=passed_count,
        failed_count=failed_count,
        unknown_count=unknown_count,
        checks=checks,
        warnings=warnings,
    )