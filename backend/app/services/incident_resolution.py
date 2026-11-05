from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from app.models.incident_records import (
    IncidentRecordView,
)
from app.models.incident_resolution import (
    IncidentResolutionCheck,
    IncidentResolutionCheckResult,
    IncidentResolutionEvidence,
    IncidentResolutionPlan,
    IncidentResolutionPlannedCheck,
    IncidentResolutionTarget,
)
from app.models.recovery import (
    RecoveryCheckStatus,
    RecoveryStatus,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
    RelationshipType,
)
from app.services.pinned_runtime_health import (
    PINNED_FAILURE_REASONS,
)


ALGORITHM_VERSION = "incident-resolution-check-0.1.0"
DEFAULT_MAX_SNAPSHOT_AGE_SECONDS = 15 * 60
MAX_WORKLOAD_ANCESTRY_HOPS = 3
MAX_WORKLOAD_DESCENDANT_HOPS = 3

OWNERSHIP_RELATIONSHIPS = {
    RelationshipType.OWNS,
    RelationshipType.RUNS,
}

PLANNED_CHECKS = (
    (
        "snapshot_after_incident",
        "Post-incident evidence",
        "The selected topology snapshot must be newer than the incident's latest observed failure.",
    ),
    (
        "snapshot_fresh",
        "Evidence freshness",
        "The selected persisted snapshot must be no more than 15 minutes old.",
    ),
    (
        "target_present",
        "Target workload exists",
        "The exact affected workload identity must still exist in the selected snapshot.",
    ),
    (
        "scope_identity_matches",
        "Evidence scope matches",
        "Tenant, cluster, namespace, workload kind and workload name must match the incident context.",
    ),
    (
        "workload_replicas_ready",
        "Workload replicas recovered",
        "Desired, ready and available replica counts must all indicate recovery.",
    ),
    (
        "affected_pods_healthy",
        "Affected Pods have no failure state",
        "Current Pods owned by the workload must not contain a supported Kubernetes failure reason.",
    ),
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _entity_namespace(entity: Entity) -> str | None:
    value = entity.properties.get("namespace")
    return str(value) if value else None


def _entity_by_id(
    snapshot: GraphSnapshot,
) -> dict[str, Entity]:
    return {
        entity.id: entity
        for entity in snapshot.entities
    }


def _integer_property(
    entity: Entity,
    keys: tuple[str, ...],
) -> int | None:
    for key in keys:
        value = entity.properties.get(key)
        if isinstance(value, int) and not isinstance(
            value,
            bool,
        ):
            return value
    return None


def _related_entities(
    snapshot: GraphSnapshot,
    *,
    start_id: str,
    reverse: bool,
    max_hops: int,
) -> list[Entity]:
    entities = _entity_by_id(snapshot)
    queue: deque[tuple[str, int]] = deque(
        [(start_id, 0)]
    )
    visited = {start_id}
    related: list[Entity] = []

    while queue:
        current_id, distance = queue.popleft()
        if distance >= max_hops:
            continue

        next_ids = {
            (
                relationship.source_entity_id
                if reverse
                else relationship.target_entity_id
            )
            for relationship in snapshot.relationships
            if relationship.relationship_type
            in OWNERSHIP_RELATIONSHIPS
            and (
                relationship.target_entity_id
                if reverse
                else relationship.source_entity_id
            )
            == current_id
        }

        for entity_id in sorted(next_ids):
            if entity_id in visited:
                continue
            visited.add(entity_id)
            entity = entities.get(entity_id)
            if entity is None:
                continue
            related.append(entity)
            queue.append((entity_id, distance + 1))

    return related


def resolve_incident_workload(
    *,
    incident: IncidentRecordView,
    pinned_snapshot: GraphSnapshot | None,
) -> Entity | None:
    if (
        pinned_snapshot is None
        or not incident.affected_entity_id
    ):
        return None

    affected = _entity_by_id(
        pinned_snapshot
    ).get(incident.affected_entity_id)
    if affected is None:
        return None
    if affected.kind == "KubernetesDeployment":
        return affected

    ancestors = _related_entities(
        pinned_snapshot,
        start_id=affected.id,
        reverse=True,
        max_hops=MAX_WORKLOAD_ANCESTRY_HOPS,
    )
    deployments = sorted(
        (
            entity
            for entity in ancestors
            if entity.kind
            == "KubernetesDeployment"
        ),
        key=lambda item: item.id,
    )
    return deployments[0] if deployments else None


def snapshot_covers_namespace(
    snapshot: GraphSnapshot,
    namespace: str | None,
) -> bool:
    if namespace is None:
        return True
    scope_namespace = snapshot.scope.get("namespace")
    if scope_namespace in {None, "", "*", namespace}:
        return True
    namespaces = {
        item.strip()
        for item in snapshot.scope.get(
            "namespaces",
            "",
        ).split(",")
        if item.strip()
    }
    return namespace in namespaces


def select_resolution_snapshot(
    *,
    incident: IncidentRecordView,
    snapshots: list[GraphSnapshot],
) -> GraphSnapshot | None:
    scoped = [
        snapshot
        for snapshot in snapshots
        if snapshot.scope.get("cluster")
        == incident.cluster_name
        and snapshot_covers_namespace(
            snapshot,
            incident.namespace,
        )
    ]
    return max(
        scoped,
        key=lambda item: _as_utc(
            item.collected_at
        ),
        default=None,
    )


def _target(
    incident: IncidentRecordView,
    workload: Entity | None,
    *,
    tenant_id: str,
) -> IncidentResolutionTarget:
    return IncidentResolutionTarget(
        tenant_id=tenant_id,
        cluster_name=incident.cluster_name,
        namespace=incident.namespace,
        workload_entity_id=(
            workload.id if workload else None
        ),
        workload_kind=(
            workload.kind if workload else None
        ),
        workload_name=(
            workload.name if workload else None
        ),
    )


def _evidence(
    snapshot: GraphSnapshot,
    *,
    max_age_seconds: int,
) -> IncidentResolutionEvidence:
    return IncidentResolutionEvidence(
        snapshot_id=snapshot.snapshot_id,
        collected_at=snapshot.collected_at,
        collector_name=snapshot.collector_name,
        collector_version=snapshot.collector_version,
        max_age_seconds=max_age_seconds,
    )


def _kubectl_commands(
    workload: Entity | None,
    namespace: str | None,
) -> list[str]:
    if workload is None or not namespace:
        return []
    name = workload.name
    commands = [
        (
            "kubectl get deployment "
            f"{name} --namespace {namespace} "
            "-o wide"
        ),
        (
            "kubectl get deployment "
            f"{name} --namespace {namespace} "
            "-o jsonpath='{.spec.replicas} "
            "{.status.readyReplicas} "
            "{.status.availableReplicas}'"
        ),
    ]
    selector = workload.properties.get("selector")
    if isinstance(selector, dict) and selector:
        selector_text = ",".join(
            f"{key}={selector[key]}"
            for key in sorted(selector)
        )
        commands.append(
            "kubectl get pods "
            f"--namespace {namespace} "
            f"--selector {selector_text} -o wide"
        )
    return commands


def build_incident_resolution_plan(
    *,
    tenant_id: str,
    incident: IncidentRecordView,
    pinned_snapshot: GraphSnapshot | None,
    candidate_snapshot: GraphSnapshot | None,
    max_age_seconds: int = (
        DEFAULT_MAX_SNAPSHOT_AGE_SECONDS
    ),
) -> IncidentResolutionPlan:
    workload = resolve_incident_workload(
        incident=incident,
        pinned_snapshot=pinned_snapshot,
    )
    limitation = None
    if workload is None:
        limitation = (
            "The affected Kubernetes Deployment could not be "
            "resolved through exact incident-time topology ownership."
        )
    elif candidate_snapshot is None:
        limitation = (
            "No persisted topology snapshot matches this incident's "
            "tenant, cluster and namespace. Wait for the Topo Agent's "
            "next collection and try again."
        )

    return IncidentResolutionPlan(
        incident_id=incident.incident_id,
        incident_status=incident.status.value,
        target=_target(
            incident,
            workload,
            tenant_id=tenant_id,
        ),
        evidence=(
            _evidence(
                candidate_snapshot,
                max_age_seconds=max_age_seconds,
            )
            if candidate_snapshot
            else None
        ),
        checks=[
            IncidentResolutionPlannedCheck(
                code=code,
                title=title,
                description=description,
            )
            for code, title, description
            in PLANNED_CHECKS
        ],
        kubectl_commands=_kubectl_commands(
            workload,
            incident.namespace,
        ),
        can_check=(
            workload is not None
            and candidate_snapshot is not None
            and incident.status.value
            not in {"resolved", "dismissed"}
        ),
        limitation=limitation,
    )


def _check(
    *,
    code: str,
    title: str,
    status: RecoveryCheckStatus,
    summary: str,
    source_type: str,
    source_id: str,
    checked_at: datetime,
    expected: str | None = None,
    observed: str | None = None,
    evidence_references: list[str] | None = None,
) -> IncidentResolutionCheck:
    return IncidentResolutionCheck(
        code=code,
        title=title,
        status=status,
        summary=summary,
        expected=expected,
        observed=observed,
        source_type=source_type,
        source_id=source_id,
        checked_at=checked_at,
        evidence_references=(
            evidence_references or [source_id]
        ),
    )


def _replica_set_ready_count(
    snapshot: GraphSnapshot,
    workload: Entity,
) -> int | None:
    replica_sets = [
        entity
        for entity in _related_entities(
            snapshot,
            start_id=workload.id,
            reverse=False,
            max_hops=1,
        )
        if entity.kind == "KubernetesReplicaSet"
    ]
    values = [
        _integer_property(
            entity,
            ("ready_replicas",),
        )
        for entity in replica_sets
    ]
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _pod_failure_reasons(
    pod: Entity,
) -> set[str]:
    reasons: set[str] = set()
    phase = pod.properties.get("phase")
    if phase in {"Failed", "Unknown"}:
        reasons.add(str(phase))

    for key in ("container_statuses", "containers"):
        containers = pod.properties.get(key)
        if not isinstance(containers, list):
            continue
        for container in containers:
            if not isinstance(container, dict):
                continue
            for reason_key in (
                "waiting_reason",
                "terminated_reason",
                "reason",
            ):
                value = container.get(reason_key)
                if value:
                    reasons.add(str(value))
            state = container.get("state")
            if not isinstance(state, dict):
                continue
            for state_name in ("waiting", "terminated"):
                state_value = state.get(state_name)
                if (
                    isinstance(state_value, dict)
                    and state_value.get("reason")
                ):
                    reasons.add(
                        str(state_value["reason"])
                    )
    return reasons & PINNED_FAILURE_REASONS


def evaluate_incident_resolution(
    *,
    tenant_id: str,
    incident: IncidentRecordView,
    pinned_snapshot: GraphSnapshot | None,
    candidate_snapshot: GraphSnapshot,
    now: datetime | None = None,
    max_age_seconds: int = (
        DEFAULT_MAX_SNAPSHOT_AGE_SECONDS
    ),
) -> IncidentResolutionCheckResult:
    checked_at = _as_utc(
        now or datetime.now(timezone.utc)
    )
    workload = resolve_incident_workload(
        incident=incident,
        pinned_snapshot=pinned_snapshot,
    )
    target = _target(
        incident,
        workload,
        tenant_id=tenant_id,
    )
    evidence = _evidence(
        candidate_snapshot,
        max_age_seconds=max_age_seconds,
    )
    checks: list[IncidentResolutionCheck] = []
    snapshot_time = _as_utc(
        candidate_snapshot.collected_at
    )
    incident_time = _as_utc(
        incident.last_observed_at
    )

    after_incident = snapshot_time > incident_time
    checks.append(
        _check(
            code="snapshot_after_incident",
            title="Post-incident evidence",
            status=(
                RecoveryCheckStatus.PASS
                if after_incident
                else RecoveryCheckStatus.FAIL
            ),
            summary=(
                "The snapshot was collected after the incident's latest failure observation."
                if after_incident
                else "The snapshot is not newer than the incident's latest failure observation."
            ),
            expected=f"collected after {incident_time.isoformat()}",
            observed=snapshot_time.isoformat(),
            source_type="snapshot",
            source_id=candidate_snapshot.snapshot_id,
            checked_at=checked_at,
        )
    )

    age_seconds = (checked_at - snapshot_time).total_seconds()
    fresh = 0 <= age_seconds <= max_age_seconds
    checks.append(
        _check(
            code="snapshot_fresh",
            title="Evidence freshness",
            status=(
                RecoveryCheckStatus.PASS
                if fresh
                else RecoveryCheckStatus.FAIL
            ),
            summary=(
                "The persisted topology snapshot is within the accepted freshness window."
                if fresh
                else "The persisted topology snapshot is stale or timestamped in the future."
            ),
            expected=(
                f"age between 0 and {max_age_seconds} seconds"
            ),
            observed=f"age={round(age_seconds)} seconds",
            source_type="snapshot",
            source_id=candidate_snapshot.snapshot_id,
            checked_at=checked_at,
        )
    )

    current = (
        _entity_by_id(candidate_snapshot).get(
            workload.id
        )
        if workload
        else None
    )
    checks.append(
        _check(
            code="target_present",
            title="Target workload exists",
            status=(
                RecoveryCheckStatus.PASS
                if current
                else RecoveryCheckStatus.FAIL
            ),
            summary=(
                f"{current.kind}/{current.name} exists with the exact incident-time workload identity."
                if current
                else "The exact incident-time workload identity is absent from the selected snapshot."
            ),
            expected=(
                f"{workload.kind}/{workload.name}"
                if workload
                else "Resolvable KubernetesDeployment"
            ),
            observed=(
                f"{current.kind}/{current.name}"
                if current
                else "Not found"
            ),
            source_type=(
                "entity" if current else "snapshot"
            ),
            source_id=(
                current.id
                if current
                else candidate_snapshot.snapshot_id
            ),
            checked_at=checked_at,
        )
    )

    cluster_matches = (
        candidate_snapshot.scope.get("cluster")
        == incident.cluster_name
    )
    identity_matches = bool(
        current
        and workload
        and current.kind == workload.kind
        and current.name == workload.name
        and _entity_namespace(current)
        == incident.namespace
        and current.source_system == "kubernetes"
    )
    scope_matches = cluster_matches and identity_matches
    checks.append(
        _check(
            code="scope_identity_matches",
            title="Evidence scope matches",
            status=(
                RecoveryCheckStatus.PASS
                if scope_matches
                else RecoveryCheckStatus.FAIL
            ),
            summary=(
                "Tenant-scoped evidence matches the incident cluster, namespace and exact workload identity."
                if scope_matches
                else "The evidence scope or workload identity does not match the incident."
            ),
            expected=(
                f"tenant-scoped {incident.cluster_name}/"
                f"{incident.namespace}/{target.workload_name}"
            ),
            observed=(
                f"tenant-scoped {candidate_snapshot.scope.get('cluster')}/"
                f"{_entity_namespace(current) if current else None}/"
                f"{current.name if current else None}"
            ),
            source_type="snapshot",
            source_id=candidate_snapshot.snapshot_id,
            checked_at=checked_at,
            evidence_references=(
                [
                    candidate_snapshot.snapshot_id,
                    current.id,
                ]
                if current
                else [candidate_snapshot.snapshot_id]
            ),
        )
    )

    desired = (
        _integer_property(
            current,
            (
                "desired_replicas",
                "replicas",
                "spec_replicas",
            ),
        )
        if current
        else None
    )
    ready = (
        _integer_property(
            current,
            ("ready_replicas",),
        )
        if current
        else None
    )
    if ready is None and current is not None:
        ready = _replica_set_ready_count(
            candidate_snapshot,
            current,
        )
    available = (
        _integer_property(
            current,
            (
                "available_replicas",
                "current_replicas",
            ),
        )
        if current
        else None
    )
    replica_values_known = all(
        value is not None
        for value in (desired, ready, available)
    )
    replicas_ready = bool(
        replica_values_known
        and desired is not None
        and ready is not None
        and available is not None
        and desired > 0
        and ready >= desired
        and available >= desired
    )
    replica_status = (
        RecoveryCheckStatus.PASS
        if replicas_ready
        else (
            RecoveryCheckStatus.FAIL
            if replica_values_known
            else RecoveryCheckStatus.UNKNOWN
        )
    )
    checks.append(
        _check(
            code="workload_replicas_ready",
            title="Workload replicas recovered",
            status=replica_status,
            summary=(
                "Desired, ready and available replica counts indicate recovery."
                if replicas_ready
                else (
                    "The workload has not reached its desired ready and available replica counts."
                    if replica_values_known
                    else "The snapshot does not contain all required replica counts."
                )
            ),
            expected="desired > 0; ready >= desired; available >= desired",
            observed=(
                f"desired={desired}, ready={ready}, available={available}"
            ),
            source_type=(
                "entity" if current else "snapshot"
            ),
            source_id=(
                current.id
                if current
                else candidate_snapshot.snapshot_id
            ),
            checked_at=checked_at,
        )
    )

    pods = (
        [
            entity
            for entity in _related_entities(
                candidate_snapshot,
                start_id=current.id,
                reverse=False,
                max_hops=(
                    MAX_WORKLOAD_DESCENDANT_HOPS
                ),
            )
            if entity.kind == "KubernetesPod"
        ]
        if current
        else []
    )
    failures = {
        pod.id: sorted(_pod_failure_reasons(pod))
        for pod in pods
        if _pod_failure_reasons(pod)
    }
    pod_status = (
        RecoveryCheckStatus.FAIL
        if failures
        else (
            RecoveryCheckStatus.PASS
            if pods
            else RecoveryCheckStatus.UNKNOWN
        )
    )
    checks.append(
        _check(
            code="affected_pods_healthy",
            title="Affected Pods have no failure state",
            status=pod_status,
            summary=(
                f"{len(pods)} current workload Pod(s) contain no supported failure reason."
                if pods and not failures
                else (
                    f"{len(failures)} current workload Pod(s) remain in a supported failure state."
                    if failures
                    else "No current Pods could be resolved through exact workload ownership edges."
                )
            ),
            expected=(
                "No descendant Pod has a supported Kubernetes failure reason"
            ),
            observed=(
                "; ".join(
                    f"{pod_id}: {','.join(reasons)}"
                    for pod_id, reasons
                    in sorted(failures.items())
                )
                if failures
                else (
                    f"{len(pods)} Pods; no supported failure reasons"
                    if pods
                    else "No owned Pods found"
                )
            ),
            source_type=(
                "entity" if current else "snapshot"
            ),
            source_id=(
                current.id
                if current
                else candidate_snapshot.snapshot_id
            ),
            checked_at=checked_at,
            evidence_references=(
                [candidate_snapshot.snapshot_id]
                + sorted(pod.id for pod in pods)
            ),
        )
    )

    passed_count = sum(
        check.status == RecoveryCheckStatus.PASS
        for check in checks
    )
    failed_count = sum(
        check.status == RecoveryCheckStatus.FAIL
        for check in checks
    )
    unknown_count = sum(
        check.status == RecoveryCheckStatus.UNKNOWN
        for check in checks
    )
    eligible = (
        failed_count == 0
        and unknown_count == 0
        and passed_count == len(checks)
        and incident.status.value
        not in {"resolved", "dismissed"}
    )
    status = (
        RecoveryStatus.VERIFIED
        if eligible
        else (
            RecoveryStatus.FAILED
            if failed_count
            else RecoveryStatus.INCONCLUSIVE
        )
    )
    summary = (
        "All required read-only recovery checks passed. Operator confirmation is still required."
        if eligible
        else (
            "Recovery cannot be confirmed because one or more required checks failed."
            if failed_count
            else "Recovery remains inconclusive because one or more required checks are unknown."
        )
    )
    identity = (
        f"{incident.incident_id}|"
        f"{candidate_snapshot.snapshot_id}|"
        f"{ALGORITHM_VERSION}"
    )
    check_id = (
        "incident-resolution:"
        + sha256(identity.encode("utf-8"))
        .hexdigest()[:32]
    )
    note = (
        "Operator marked resolved after Topo read-only "
        f"resolution check {check_id}. Snapshot "
        f"{candidate_snapshot.snapshot_id} was collected at "
        f"{snapshot_time.isoformat()}; {passed_count}/"
        f"{len(checks)} required checks passed. Topo did not "
        "modify infrastructure."
        if eligible
        else None
    )
    return IncidentResolutionCheckResult(
        check_id=check_id,
        incident_id=incident.incident_id,
        generated_at=checked_at,
        status=status,
        summary=summary,
        target=target,
        evidence=evidence,
        checks=checks,
        passed_count=passed_count,
        failed_count=failed_count,
        unknown_count=unknown_count,
        eligible_to_resolve=eligible,
        resolution_note=note,
    )
