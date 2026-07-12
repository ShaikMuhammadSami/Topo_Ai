from __future__ import annotations

from collections import (
    defaultdict,
    deque,
)
from datetime import (
    datetime,
    timezone,
)
from hashlib import sha256

from sqlalchemy.orm import Session

from app.models.predeployment import (
    ChangeRiskLevel,
    DeploymentDecision,
    PlannedChangeType,
    PreDeploymentAffectedEntity,
    PreDeploymentDependencyPath,
    PreDeploymentImpactRequest,
    PreDeploymentImpactResponse,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)


ALGORITHM_VERSION = (
    "predeployment-impact-0.1.0"
)


class PreDeploymentNotFoundError(
    Exception
):
    pass


class PreDeploymentValidationError(
    Exception
):
    pass


CHANGE_BASE_RISK = {
    PlannedChangeType
    .CONTAINER_IMAGE_UPDATE: 0.55,

    PlannedChangeType
    .CONFIGURATION_CHANGE: 0.60,

    PlannedChangeType
    .RESOURCE_LIMIT_CHANGE: 0.65,

    PlannedChangeType
    .REPLICA_CHANGE: 0.35,

    PlannedChangeType
    .NETWORK_POLICY_CHANGE: 0.75,

    PlannedChangeType
    .SERVICE_ROUTING_CHANGE: 0.70,

    PlannedChangeType
    .SECRET_OR_CERTIFICATE_CHANGE: 0.80,

    PlannedChangeType
    .DATABASE_SCHEMA_CHANGE: 0.85,

    PlannedChangeType.OTHER: 0.50,
}


FORWARD_RELATIONSHIPS = {
    "contains",
    "owns",
    "produces",
    "triggers",
    "deploys",
    "runs",
    "selects",
    "exposes",
    "routes_to",
    "calls",
    "depends_on",
    "uses",
    "protects",
    "resolves_to",
    "attached_to",
    "affects",
    "derived_from",
}


# Reverse traversal finds consumers and
# owning runtime resources. "contains" is
# intentionally excluded to avoid treating
# every namespace sibling as affected.
REVERSE_RELATIONSHIPS = {
    "owns",
    "deploys",
    "runs",
    "selects",
    "exposes",
    "routes_to",
    "calls",
    "depends_on",
    "uses",
    "protects",
    "resolves_to",
    "attached_to",
    "affects",
    "derived_from",
}


RELATIONSHIP_RISK = {
    "calls": 0.90,
    "depends_on": 0.90,
    "routes_to": 0.85,
    "uses": 0.80,
    "selects": 0.75,
    "exposes": 0.75,
    "protects": 0.85,
    "resolves_to": 0.80,
    "attached_to": 0.70,
    "runs": 0.65,
    "deploys": 0.65,
    "contains": 0.45,
    "owns": 0.45,
    "derived_from": 0.55,
}


def _analysis_id(
    request: PreDeploymentImpactRequest,
) -> str:
    value = "|".join(
        [
            request.snapshot_id,
            request.entity_id,
            request.change_type.value,
            request.change_summary.strip(),
            str(request.max_depth),
            ALGORITHM_VERSION,
        ]
    )

    digest = sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return (
        f"predeployment-analysis:"
        f"{digest}"
    )


def _impact_label(
    distance: int,
) -> str:
    if distance == 0:
        return "direct"

    if distance == 1:
        return "dependent"

    if distance == 2:
        return "indirect"

    return "potential"


def _impact_score(
    distance: int,
) -> float:
    if distance == 0:
        return 1.0

    if distance == 1:
        return 0.85

    if distance == 2:
        return 0.65

    if distance == 3:
        return 0.45

    return 0.25


def _namespace(
    entity: Entity,
) -> str | None:
    value = entity.properties.get(
        "namespace"
    )

    if value is None:
        return None

    return str(value)


def _kind_risk(
    entity: Entity,
) -> float:
    value = entity.kind.lower()

    if any(
        token in value
        for token in (
            "database",
            "datastore",
            "postgres",
            "mysql",
            "redis",
        )
    ):
        return 0.90

    if any(
        token in value
        for token in (
            "certificate",
            "secret",
            "security",
        )
    ):
        return 0.88

    if any(
        token in value
        for token in (
            "ingress",
            "gateway",
            "loadbalancer",
            "networkpolicy",
        )
    ):
        return 0.82

    if "service" in value:
        return 0.72

    if "deployment" in value:
        return 0.68

    if "statefulset" in value:
        return 0.78

    if "pod" in value:
        return 0.55

    if "containerimage" in value:
        return 0.58

    return 0.50


def _entity_risk(
    entity: Entity,
    distance: int,
    relationship: str | None,
    change_type: PlannedChangeType,
) -> tuple[float, list[str]]:
    change_score = CHANGE_BASE_RISK[
        change_type
    ]

    impact_score = _impact_score(
        distance
    )

    kind_score = _kind_risk(entity)

    relationship_score = (
        RELATIONSHIP_RISK.get(
            relationship,
            0.50,
        )
        if relationship
        else 0.50
    )

    score = (
        change_score * 0.40
        + impact_score * 0.30
        + kind_score * 0.20
        + relationship_score * 0.10
    )

    score = round(
        max(
            0.0,
            min(score, 1.0),
        ),
        4,
    )

    reasons = [
        (
            "Change type contributes "
            f"{change_score:.2f} base risk."
        ),
        (
            f"{entity.kind} contributes "
            f"{kind_score:.2f} entity risk."
        ),
        (
            f"Graph distance {distance} "
            f"contributes "
            f"{impact_score:.2f} impact."
        ),
    ]

    if relationship:
        reasons.append(
            f"Relationship '{relationship}' "
            f"contributes "
            f"{relationship_score:.2f} risk."
        )

    return score, reasons


def _build_adjacency(
    snapshot: GraphSnapshot,
) -> dict[
    str,
    list[
        tuple[str, str]
    ],
]:
    adjacency: dict[
        str,
        list[
            tuple[str, str]
        ],
    ] = defaultdict(list)

    seen: set[
        tuple[str, str, str]
    ] = set()

    for relationship in (
        snapshot.relationships
    ):
        relation = (
            relationship
            .relationship_type
            .value
        )

        if (
            relation
            in FORWARD_RELATIONSHIPS
        ):
            edge = (
                relationship
                .source_entity_id,
                relationship
                .target_entity_id,
                relation,
            )

            if edge not in seen:
                adjacency[
                    edge[0]
                ].append(
                    (
                        edge[1],
                        edge[2],
                    )
                )

                seen.add(edge)

        if (
            relation
            in REVERSE_RELATIONSHIPS
        ):
            reverse_edge = (
                relationship
                .target_entity_id,
                relationship
                .source_entity_id,
                relation,
            )

            if reverse_edge not in seen:
                adjacency[
                    reverse_edge[0]
                ].append(
                    (
                        reverse_edge[1],
                        reverse_edge[2],
                    )
                )

                seen.add(
                    reverse_edge
                )

    return dict(adjacency)


def _risk_level(
    score: float,
) -> ChangeRiskLevel:
    if score >= 0.80:
        return ChangeRiskLevel.CRITICAL

    if score >= 0.65:
        return ChangeRiskLevel.HIGH

    if score >= 0.40:
        return ChangeRiskLevel.MEDIUM

    return ChangeRiskLevel.LOW


def _decision(
    level: ChangeRiskLevel,
) -> DeploymentDecision:
    if level == ChangeRiskLevel.CRITICAL:
        return (
            DeploymentDecision
            .BLOCK_UNTIL_MITIGATED
        )

    if level == ChangeRiskLevel.HIGH:
        return (
            DeploymentDecision
            .APPROVAL_REQUIRED
        )

    if level == ChangeRiskLevel.MEDIUM:
        return (
            DeploymentDecision
            .REVIEW_REQUIRED
        )

    return DeploymentDecision.ALLOW


def _recommendation(
    decision: DeploymentDecision,
) -> str:
    if (
        decision
        == DeploymentDecision
        .BLOCK_UNTIL_MITIGATED
    ):
        return (
            "Do not deploy until the highest-risk "
            "dependencies have mitigation, rollback "
            "and validation plans."
        )

    if (
        decision
        == DeploymentDecision
        .APPROVAL_REQUIRED
    ):
        return (
            "Require an operator or change-approval "
            "review before deployment."
        )

    if (
        decision
        == DeploymentDecision
        .REVIEW_REQUIRED
    ):
        return (
            "Review the affected entities and confirm "
            "monitoring and rollback readiness."
        )

    return (
        "The predicted topology risk is low. "
        "Proceed using the normal deployment controls."
    )


def analyze_predeployment_impact(
    session: Session,
    request: PreDeploymentImpactRequest,
) -> PreDeploymentImpactResponse:
    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=request.snapshot_id,
    )

    if snapshot is None:
        raise PreDeploymentNotFoundError(
            "Topology snapshot not found: "
            f"{request.snapshot_id}"
        )

    entity_map = {
        entity.id: entity
        for entity in snapshot.entities
    }

    root = entity_map.get(
        request.entity_id
    )

    if root is None:
        raise PreDeploymentNotFoundError(
            "Entity was not found in the "
            "selected topology snapshot: "
            f"{request.entity_id}"
        )

    adjacency = _build_adjacency(
        snapshot
    )

    queue = deque(
        [
            (
                root.id,
                0,
                [root.id],
                None,
            )
        ]
    )

    best_distance: dict[
        str,
        int,
    ] = {}

    affected: list[
        PreDeploymentAffectedEntity
    ] = []

    paths: list[
        PreDeploymentDependencyPath
    ] = []

    while queue:
        (
            entity_id,
            distance,
            path,
            relationship,
        ) = queue.popleft()

        previous_distance = (
            best_distance.get(
                entity_id
            )
        )

        if (
            previous_distance is not None
            and previous_distance
            <= distance
        ):
            continue

        best_distance[
            entity_id
        ] = distance

        entity = entity_map.get(
            entity_id
        )

        if entity is None:
            continue

        risk_score, risk_reasons = (
            _entity_risk(
                entity=entity,
                distance=distance,
                relationship=relationship,
                change_type=(
                    request.change_type
                ),
            )
        )

        affected.append(
            PreDeploymentAffectedEntity(
                entity_id=entity.id,
                entity_kind=entity.kind,
                entity_name=entity.name,
                namespace=_namespace(
                    entity
                ),
                distance=distance,
                impact=_impact_label(
                    distance
                ),
                impact_score=_impact_score(
                    distance
                ),
                relationship=relationship,
                risk_score=risk_score,
                risk_reasons=(
                    risk_reasons
                ),
            )
        )

        if distance > 0:
            paths.append(
                PreDeploymentDependencyPath(
                    path=path
                )
            )

        if (
            distance
            >= request.max_depth
        ):
            continue

        for (
            neighbour_id,
            relation,
        ) in adjacency.get(
            entity_id,
            [],
        ):
            neighbour_distance = (
                best_distance.get(
                    neighbour_id
                )
            )

            if (
                neighbour_distance
                is not None
                and neighbour_distance
                <= distance + 1
            ):
                continue

            queue.append(
                (
                    neighbour_id,
                    distance + 1,
                    [
                        *path,
                        neighbour_id,
                    ],
                    relation,
                )
            )

    affected.sort(
        key=lambda item: (
            item.distance,
            -item.risk_score,
            item.entity_name,
        )
    )

    downstream = [
        item
        for item in affected
        if item.distance > 0
    ]

    maximum_entity_risk = max(
        (
            item.risk_score
            for item in affected
        ),
        default=0.0,
    )

    scope_score = min(
        1.0,
        len(downstream) / 10.0,
    )

    maximum_distance = max(
        (
            item.distance
            for item in affected
        ),
        default=0,
    )

    depth_score = min(
        1.0,
        maximum_distance
        / max(
            request.max_depth,
            1,
        ),
    )

    base_change_risk = (
        CHANGE_BASE_RISK[
            request.change_type
        ]
    )

    overall_risk = round(
        max(
            0.0,
            min(
                (
                    base_change_risk
                    * 0.40
                    + maximum_entity_risk
                    * 0.30
                    + scope_score
                    * 0.20
                    + depth_score
                    * 0.10
                ),
                1.0,
            ),
        ),
        4,
    )

    level = _risk_level(
        overall_risk
    )

    decision = _decision(level)

    high_risk_count = len(
        [
            item
            for item in affected
            if item.risk_score >= 0.70
        ]
    )

    risk_factors = [
        (
            "Planned change base risk: "
            f"{base_change_risk:.2f}"
        ),
        (
            "Reachable downstream entities: "
            f"{len(downstream)}"
        ),
        (
            "Highest entity risk: "
            f"{maximum_entity_risk:.2f}"
        ),
        (
            "High-risk entities: "
            f"{high_risk_count}"
        ),
        (
            "Maximum dependency distance: "
            f"{maximum_distance}"
        ),
    ]

    warnings = [
        (
            "This result is a deterministic "
            "topology prediction. It does not "
            "execute or validate the planned change."
        )
    ]

    if not downstream:
        warnings.append(
            "No downstream entities were reachable "
            "from the selected entity."
        )

    return PreDeploymentImpactResponse(
        analysis_id=_analysis_id(
            request
        ),
        algorithm_version=(
            ALGORITHM_VERSION
        ),
        generated_at=datetime.now(
            timezone.utc
        ),
        snapshot_id=(
            request.snapshot_id
        ),
        root_entity_id=root.id,
        root_entity_kind=root.kind,
        root_entity_name=root.name,
        change_type=(
            request.change_type
        ),
        change_summary=(
            request.change_summary
        ),
        risk_score=overall_risk,
        risk_level=level,
        deployment_decision=(
            decision
        ),
        recommendation=(
            _recommendation(
                decision
            )
        ),
        affected_entity_count=len(
            affected
        ),
        downstream_entity_count=len(
            downstream
        ),
        direct_impact_count=len(
            [
                item
                for item in affected
                if item.distance == 0
            ]
        ),
        dependent_impact_count=len(
            [
                item
                for item in affected
                if item.distance == 1
            ]
        ),
        indirect_impact_count=len(
            [
                item
                for item in affected
                if item.distance == 2
            ]
        ),
        potential_impact_count=len(
            [
                item
                for item in affected
                if item.distance >= 3
            ]
        ),
        high_risk_entity_count=(
            high_risk_count
        ),
        affected_entities=affected,
        dependency_paths=paths,
        risk_factors=risk_factors,
        warnings=warnings,
    )