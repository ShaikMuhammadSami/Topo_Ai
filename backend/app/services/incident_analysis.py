from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from app.models.changes import (
    ChangeCategory,
    ChangeImportance,
    ChangeType,
    NormalizedChange,
)
from app.models.incidents import (
    EvidenceDirection,
    IncidentAnalysis,
    IncidentEvidence,
    RootCauseHypothesis,
)
from app.models.signals import (
    NormalizedSignal,
    SignalCategory,
)
from app.models.topology import GraphSnapshot


ALGORITHM_VERSION = "deterministic-rca-0.1.0"


CATEGORY_COMPATIBILITY: dict[
    SignalCategory,
    dict[ChangeCategory, float],
] = {
    SignalCategory.IMAGE: {
        ChangeCategory.IMAGE: 1.00,
        ChangeCategory.DEPLOYMENT: 0.95,
        ChangeCategory.CONFIGURATION: 0.70,
        ChangeCategory.RUNTIME: 0.55,
        ChangeCategory.TOPOLOGY: 0.30,
    },
    SignalCategory.HEALTH: {
        ChangeCategory.DEPLOYMENT: 0.90,
        ChangeCategory.IMAGE: 0.85,
        ChangeCategory.CONFIGURATION: 0.75,
        ChangeCategory.RUNTIME: 0.70,
        ChangeCategory.SCALING: 0.50,
        ChangeCategory.SERVICE: 0.45,
    },
    SignalCategory.SCHEDULING: {
        ChangeCategory.CONFIGURATION: 0.85,
        ChangeCategory.SCALING: 0.80,
        ChangeCategory.RUNTIME: 0.65,
        ChangeCategory.TOPOLOGY: 0.50,
    },
    SignalCategory.STORAGE: {
        ChangeCategory.CONFIGURATION: 0.85,
        ChangeCategory.RUNTIME: 0.65,
        ChangeCategory.TOPOLOGY: 0.50,
    },
    SignalCategory.AVAILABILITY: {
        ChangeCategory.DEPLOYMENT: 0.90,
        ChangeCategory.SERVICE: 0.85,
        ChangeCategory.NETWORKING: 0.85,
        ChangeCategory.IMAGE: 0.80,
        ChangeCategory.CONFIGURATION: 0.70,
        ChangeCategory.RUNTIME: 0.60,
    },
    SignalCategory.CONFIGURATION: {
        ChangeCategory.CONFIGURATION: 1.00,
        ChangeCategory.DEPLOYMENT: 0.80,
        ChangeCategory.SERVICE: 0.75,
        ChangeCategory.NETWORKING: 0.70,
    },
    SignalCategory.LIFECYCLE: {
        ChangeCategory.DEPLOYMENT: 0.80,
        ChangeCategory.RUNTIME: 0.75,
        ChangeCategory.SCALING: 0.70,
        ChangeCategory.TOPOLOGY: 0.60,
    },
    SignalCategory.SECURITY: {
        ChangeCategory.CONFIGURATION: 0.80,
        ChangeCategory.NETWORKING: 0.75,
        ChangeCategory.SERVICE: 0.50,
    },
    SignalCategory.OTHER: {
        ChangeCategory.DEPLOYMENT: 0.55,
        ChangeCategory.CONFIGURATION: 0.50,
        ChangeCategory.RUNTIME: 0.45,
        ChangeCategory.TOPOLOGY: 0.35,
        ChangeCategory.OTHER: 0.30,
    },
}


IMPORTANCE_SCORE = {
    ChangeImportance.HIGH: 1.00,
    ChangeImportance.MEDIUM: 0.70,
    ChangeImportance.LOW: 0.40,
}


CHANGE_TYPE_SCORE = {
    ChangeType.ENTITY_UPDATED: 1.00,
    ChangeType.ENTITY_ADDED: 0.85,
    ChangeType.ENTITY_REMOVED: 0.80,
    ChangeType.RELATIONSHIP_UPDATED: 0.80,
    ChangeType.RELATIONSHIP_ADDED: 0.70,
    ChangeType.RELATIONSHIP_REMOVED: 0.70,
}


def _analysis_id(
    signal_id: str,
    topology_snapshot_id: str,
    lookback_minutes: int,
    max_graph_hops: int,
) -> str:
    value = "|".join(
        [
            signal_id,
            topology_snapshot_id,
            str(lookback_minutes),
            str(max_graph_hops),
            ALGORITHM_VERSION,
        ]
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"analysis:{digest}"


def _hypothesis_id(
    analysis_id: str,
    change_id: str,
) -> str:
    digest = sha256(
        (
            f"{analysis_id}|"
            f"{change_id}"
        ).encode("utf-8")
    ).hexdigest()[:24]

    return f"hypothesis:{digest}"


def _evidence_id(
    hypothesis_id: str,
    code: str,
) -> str:
    digest = sha256(
        (
            f"{hypothesis_id}|{code}"
        ).encode("utf-8")
    ).hexdigest()[:20]

    return f"incident-evidence:{digest}"


def _graph_adjacency(
    snapshot: GraphSnapshot,
) -> dict[str, set[str]]:
    adjacency: dict[
        str,
        set[str],
    ] = {
        entity.id: set()
        for entity in snapshot.entities
    }

    for relationship in snapshot.relationships:
        source = (
            relationship.source_entity_id
        )

        target = (
            relationship.target_entity_id
        )

        adjacency.setdefault(
            source,
            set(),
        ).add(target)

        adjacency.setdefault(
            target,
            set(),
        ).add(source)

    return adjacency


def _shortest_distance(
    adjacency: dict[str, set[str]],
    start_entity_id: str | None,
    target_entity_ids: set[str],
    max_hops: int,
) -> int | None:
    if (
        not start_entity_id
        or not target_entity_ids
        or start_entity_id
        not in adjacency
    ):
        return None

    if start_entity_id in target_entity_ids:
        return 0

    queue: deque[
        tuple[str, int]
    ] = deque(
        [(start_entity_id, 0)]
    )

    visited = {
        start_entity_id
    }

    while queue:
        current, distance = (
            queue.popleft()
        )

        if distance >= max_hops:
            continue

        for neighbor in adjacency.get(
            current,
            set(),
        ):
            if neighbor in visited:
                continue

            next_distance = (
                distance + 1
            )

            if neighbor in target_entity_ids:
                return next_distance

            visited.add(neighbor)

            queue.append(
                (
                    neighbor,
                    next_distance,
                )
            )

    return None


def _graph_score(
    distance: int | None,
) -> float:
    if distance is None:
        return 0.05

    scores = {
        0: 1.00,
        1: 0.90,
        2: 0.75,
        3: 0.60,
        4: 0.45,
        5: 0.30,
    }

    return scores.get(
        distance,
        0.15,
    )


def _category_score(
    signal_category: SignalCategory,
    change_category: ChangeCategory,
) -> float:
    return (
        CATEGORY_COMPATIBILITY
        .get(
            signal_category,
            {},
        )
        .get(
            change_category,
            0.20,
        )
    )


def _temporal_score(
    change_time: datetime,
    signal_start: datetime,
    lookback_minutes: int,
    grace_minutes: int,
) -> tuple[float, float, bool]:
    delta_seconds = (
        signal_start - change_time
    ).total_seconds()

    minutes_before = (
        delta_seconds / 60
    )

    if delta_seconds >= 0:
        lookback_seconds = max(
            lookback_minutes * 60,
            1,
        )

        score = max(
            0.0,
            1.0
            - (
                delta_seconds
                / lookback_seconds
            ),
        )

        return (
            score,
            minutes_before,
            False,
        )

    grace_seconds = max(
        grace_minutes * 60,
        1,
    )

    seconds_after = abs(
        delta_seconds
    )

    if seconds_after > grace_seconds:
        return (
            0.0,
            minutes_before,
            True,
        )

    score = max(
        0.25,
        0.75
        - (
            seconds_after
            / grace_seconds
        )
        * 0.50,
    )

    return (
        score,
        minutes_before,
        True,
    )


def _candidate_entity_ids(
    change: NormalizedChange,
) -> set[str]:
    result = set(
        change.related_entity_ids
    )

    for value in (
        change.entity_id,
        change.source_entity_id,
        change.target_entity_id,
    ):
        if value:
            result.add(value)

    return result


def _change_label(
    change: NormalizedChange,
) -> str:
    if (
        change.entity_kind
        and change.entity_name
    ):
        return (
            f"{change.entity_kind}/"
            f"{change.entity_name}"
        )

    if change.relationship_type:
        return (
            f"{change.relationship_type} "
            "relationship"
        )

    return change.change_id


def _supporting_evidence(
    hypothesis_id: str,
    change: NormalizedChange,
    signal: NormalizedSignal,
    temporal_score: float,
    graph_score: float,
    category_score: float,
    importance_score: float,
    graph_distance: int | None,
    minutes_before: float,
) -> list[IncidentEvidence]:
    evidence: list[
        IncidentEvidence
    ] = []

    if temporal_score >= 0.50:
        timing = (
            f"{abs(minutes_before):.1f} minutes "
            + (
                "before the first symptom."
                if minutes_before >= 0
                else "after the first symptom, "
                "within the collection grace window."
            )
        )

        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "temporal-proximity",
                ),
                direction=(
                    EvidenceDirection
                    .SUPPORTING
                ),
                code="temporal_proximity",
                summary=(
                    "The change was detected "
                    f"{timing}"
                ),
                weight=round(
                    0.30
                    * temporal_score,
                    4,
                ),
                source_type="change",
                source_id=change.change_id,
                observed_at=(
                    change.detected_at
                ),
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
                attributes={
                    "minutes_before_signal": (
                        round(
                            minutes_before,
                            3,
                        )
                    ),
                },
            )
        )

    if graph_distance is not None:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "graph-proximity",
                ),
                direction=(
                    EvidenceDirection
                    .SUPPORTING
                ),
                code="graph_proximity",
                summary=(
                    "The changed resource is "
                    f"{graph_distance} graph hop"
                    f"{'' if graph_distance == 1 else 's'} "
                    "from the affected resource."
                ),
                weight=round(
                    0.30 * graph_score,
                    4,
                ),
                source_type="topology",
                source_id=(
                    signal
                    .topology_snapshot_id
                    or ""
                ),
                related_entity_ids=[
                    entity_id
                    for entity_id in (
                        [
                            signal
                            .involved_entity_id
                        ]
                        + change
                        .related_entity_ids
                    )
                    if entity_id
                ],
                attributes={
                    "graph_distance": (
                        graph_distance
                    ),
                },
            )
        )

    if category_score >= 0.60:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "category-compatibility",
                ),
                direction=(
                    EvidenceDirection
                    .SUPPORTING
                ),
                code=(
                    "category_compatibility"
                ),
                summary=(
                    f"A {change.category.value} "
                    "change is compatible with a "
                    f"{signal.category.value} "
                    "failure signal."
                ),
                weight=round(
                    0.20
                    * category_score,
                    4,
                ),
                source_type="change",
                source_id=change.change_id,
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
                attributes={
                    "signal_category": (
                        signal.category.value
                    ),
                    "change_category": (
                        change.category.value
                    ),
                },
            )
        )

    if (
        change.importance
        in {
            ChangeImportance.HIGH,
            ChangeImportance.MEDIUM,
        }
    ):
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "change-importance",
                ),
                direction=(
                    EvidenceDirection
                    .SUPPORTING
                ),
                code="change_importance",
                summary=(
                    "The normalized change was "
                    f"classified as "
                    f"{change.importance.value} "
                    "importance."
                ),
                weight=round(
                    0.10
                    * importance_score,
                    4,
                ),
                source_type="change",
                source_id=change.change_id,
                observed_at=(
                    change.detected_at
                ),
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
            )
        )

    if change.changed_fields:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "changed-fields",
                ),
                direction=(
                    EvidenceDirection
                    .SUPPORTING
                ),
                code="changed_fields",
                summary=(
                    "The change contains explicit "
                    "before-and-after field values."
                ),
                weight=0.05,
                source_type="change",
                source_id=change.change_id,
                observed_at=(
                    change.detected_at
                ),
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
                attributes={
                    "fields": sorted(
                        change
                        .changed_fields
                        .keys()
                    ),
                },
            )
        )

    return evidence


def _counter_evidence(
    hypothesis_id: str,
    change: NormalizedChange,
    signal: NormalizedSignal,
    category_score: float,
    graph_distance: int | None,
    minutes_before: float,
    lookback_minutes: int,
    detected_after_signal: bool,
) -> list[IncidentEvidence]:
    evidence: list[
        IncidentEvidence
    ] = []

    if graph_distance is None:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "no-graph-path",
                ),
                direction=(
                    EvidenceDirection.COUNTER
                ),
                code="no_graph_path",
                summary=(
                    "No graph path was found "
                    "between the changed resource "
                    "and the affected resource "
                    "within the configured hop "
                    "limit."
                ),
                weight=-0.20,
                source_type="topology",
                source_id=(
                    signal
                    .topology_snapshot_id
                    or ""
                ),
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
            )
        )

    if category_score <= 0.30:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "category-mismatch",
                ),
                direction=(
                    EvidenceDirection.COUNTER
                ),
                code="category_mismatch",
                summary=(
                    f"The {change.category.value} "
                    "change has weak compatibility "
                    "with the "
                    f"{signal.category.value} "
                    "signal."
                ),
                weight=-0.15,
                source_type="change",
                source_id=change.change_id,
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
            )
        )

    if (
        minutes_before
        > lookback_minutes * 0.75
    ):
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "change-is-old",
                ),
                direction=(
                    EvidenceDirection.COUNTER
                ),
                code="weak_temporal_proximity",
                summary=(
                    "The change occurred near the "
                    "outer edge of the configured "
                    "lookback window."
                ),
                weight=-0.10,
                source_type="change",
                source_id=change.change_id,
                observed_at=(
                    change.detected_at
                ),
            )
        )

    if detected_after_signal:
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "detected-after-symptom",
                ),
                direction=(
                    EvidenceDirection.COUNTER
                ),
                code=(
                    "detected_after_first_symptom"
                ),
                summary=(
                    "The snapshot change was "
                    "recorded after the first "
                    "symptom timestamp. Collection "
                    "timing may explain this, but "
                    "causal ordering is weaker."
                ),
                weight=-0.12,
                source_type="change",
                source_id=change.change_id,
                observed_at=(
                    change.detected_at
                ),
            )
        )

    if (
        change.importance
        == ChangeImportance.LOW
    ):
        evidence.append(
            IncidentEvidence(
                evidence_id=_evidence_id(
                    hypothesis_id,
                    "low-importance",
                ),
                direction=(
                    EvidenceDirection.COUNTER
                ),
                code="low_importance",
                summary=(
                    "This is a low-importance "
                    "runtime or topology change and "
                    "may be a consequence rather "
                    "than the initiating cause."
                ),
                weight=-0.05,
                source_type="change",
                source_id=change.change_id,
                related_entity_ids=(
                    change
                    .related_entity_ids
                ),
            )
        )

    return evidence


def analyze_incident(
    signal: NormalizedSignal,
    snapshot: GraphSnapshot,
    candidate_changes: list[
        NormalizedChange
    ],
    lookback_minutes: int,
    grace_minutes: int,
    max_graph_hops: int,
    max_hypotheses: int,
) -> IncidentAnalysis:
    generated_at = datetime.now(
        timezone.utc
    )

    analysis_id = _analysis_id(
        signal_id=signal.signal_id,
        topology_snapshot_id=(
            snapshot.snapshot_id
        ),
        lookback_minutes=(
            lookback_minutes
        ),
        max_graph_hops=(
            max_graph_hops
        ),
    )

    adjacency = _graph_adjacency(
        snapshot
    )

    warnings: list[str] = []

    if not signal.involved_entity_id:
        warnings.append(
            "The signal is not mapped to a "
            "canonical topology entity. Graph "
            "proximity cannot be calculated."
        )

    elif (
        signal.involved_entity_id
        not in adjacency
    ):
        warnings.append(
            "The signal entity is not present in "
            "the selected topology snapshot."
        )

    hypotheses: list[
        RootCauseHypothesis
    ] = []

    for change in candidate_changes:
        target_ids = (
            _candidate_entity_ids(change)
        )

        distance = _shortest_distance(
            adjacency=adjacency,
            start_entity_id=(
                signal.involved_entity_id
            ),
            target_entity_ids=target_ids,
            max_hops=max_graph_hops,
        )

        graph_component = (
            _graph_score(distance)
        )

        category_component = (
            _category_score(
                signal_category=(
                    signal.category
                ),
                change_category=(
                    change.category
                ),
            )
        )

        importance_component = (
            IMPORTANCE_SCORE[
                change.importance
            ]
        )

        change_type_component = (
            CHANGE_TYPE_SCORE[
                change.change_type
            ]
        )

        (
            temporal_component,
            minutes_before_signal,
            detected_after_signal,
        ) = _temporal_score(
            change_time=(
                change.detected_at
            ),
            signal_start=(
                signal.first_observed_at
            ),
            lookback_minutes=(
                lookback_minutes
            ),
            grace_minutes=(
                grace_minutes
            ),
        )

        raw_score = (
            0.30 * temporal_component
            + 0.30 * graph_component
            + 0.20 * category_component
            + 0.10 * importance_component
            + 0.10 * change_type_component
        )

        hypothesis_id = (
            _hypothesis_id(
                analysis_id=analysis_id,
                change_id=change.change_id,
            )
        )

        supporting = (
            _supporting_evidence(
                hypothesis_id=(
                    hypothesis_id
                ),
                change=change,
                signal=signal,
                temporal_score=(
                    temporal_component
                ),
                graph_score=(
                    graph_component
                ),
                category_score=(
                    category_component
                ),
                importance_score=(
                    importance_component
                ),
                graph_distance=distance,
                minutes_before=(
                    minutes_before_signal
                ),
            )
        )

        counter = _counter_evidence(
            hypothesis_id=hypothesis_id,
            change=change,
            signal=signal,
            category_score=(
                category_component
            ),
            graph_distance=distance,
            minutes_before=(
                minutes_before_signal
            ),
            lookback_minutes=(
                lookback_minutes
            ),
            detected_after_signal=(
                detected_after_signal
            ),
        )

        counter_penalty = sum(
            abs(item.weight)
            for item in counter
        )

        score = max(
            0.0,
            min(
                1.0,
                raw_score
                - counter_penalty,
            ),
        )

        change_label = _change_label(
            change
        )

        explanation = (
            f"{change.title} affected "
            f"{change_label}. It was detected "
            f"{abs(minutes_before_signal):.1f} "
            "minutes "
            + (
                "before"
                if minutes_before_signal >= 0
                else "after"
            )
            + " the first symptom"
            + (
                f" and is {distance} graph hop"
                f"{'' if distance == 1 else 's'} "
                "from the affected entity."
                if distance is not None
                else ", but no nearby graph path "
                "was found."
            )
        )

        hypotheses.append(
            RootCauseHypothesis(
                hypothesis_id=(
                    hypothesis_id
                ),
                rank=1,
                change_id=(
                    change.change_id
                ),
                title=change.title,
                explanation=explanation,
                score=round(
                    score,
                    4,
                ),
                change_type=(
                    change.change_type
                ),
                category=change.category,
                importance=(
                    change.importance
                ),
                change_detected_at=(
                    change.detected_at
                ),
                minutes_before_signal=(
                    round(
                        minutes_before_signal,
                        3,
                    )
                ),
                graph_distance=distance,
                affected_entity_id=(
                    signal
                    .involved_entity_id
                ),
                changed_entity_id=(
                    change.entity_id
                ),
                changed_entity_kind=(
                    change.entity_kind
                ),
                changed_entity_name=(
                    change.entity_name
                ),
                supporting_evidence=(
                    supporting
                ),
                counter_evidence=counter,
                scoring_components={
                    "temporal": round(
                        temporal_component,
                        4,
                    ),
                    "graph": round(
                        graph_component,
                        4,
                    ),
                    "category": round(
                        category_component,
                        4,
                    ),
                    "importance": round(
                        importance_component,
                        4,
                    ),
                    "change_type": round(
                        change_type_component,
                        4,
                    ),
                    "counter_penalty": round(
                        counter_penalty,
                        4,
                    ),
                },
            )
        )

    hypotheses.sort(
        key=lambda item: (
            item.score,
            item.importance.value,
            item.change_detected_at,
        ),
        reverse=True,
    )

    hypotheses = hypotheses[
        :max_hypotheses
    ]

    for rank, hypothesis in enumerate(
        hypotheses,
        start=1,
    ):
        hypothesis.rank = rank

    object_label = "/".join(
        value
        for value in (
            signal.involved_object_kind,
            signal.involved_object_name,
        )
        if value
    )

    incident_title = (
        f"{signal.reason or signal.title}"
        + (
            f" on {object_label}"
            if object_label
            else ""
        )
    )

    if not hypotheses:
        warnings.append(
            "No candidate changes were found "
            "inside the configured analysis "
            "window."
        )

    return IncidentAnalysis(
        analysis_id=analysis_id,
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        signal_id=signal.signal_id,
        topology_snapshot_id=(
            snapshot.snapshot_id
        ),
        generated_at=generated_at,
        incident_title=incident_title,
        cluster_name=(
            signal.cluster_name
        ),
        namespace=signal.namespace,
        symptom_reason=signal.reason,
        symptom_summary=signal.summary,
        symptom_entity_id=(
            signal.involved_entity_id
        ),
        signal_first_observed_at=(
            signal.first_observed_at
        ),
        signal_last_observed_at=(
            signal.last_observed_at
        ),
        lookback_minutes=(
            lookback_minutes
        ),
        grace_minutes=grace_minutes,
        max_graph_hops=(
            max_graph_hops
        ),
        candidate_count=len(
            candidate_changes
        ),
        hypotheses=hypotheses,
        warnings=warnings,
    )