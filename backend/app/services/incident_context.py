from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalEdgeType,
    CausalNodeType,
)
from app.models.incident_context import (
    IncidentOperationalContext,
)
from app.models.ownership import (
    EntityOwnershipResolution,
    IncidentOwnershipImpact,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.business_impact import (
    calculate_incident_ownership_impact,
)
from app.services.ownership_resolver import (
    resolve_entity_ownership,
)


def _deduplicated(
    values: list[str | None],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue

        normalized = value.strip()

        if not normalized:
            continue

        key = normalized.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(normalized)

    return result


def _entity_id_for_node(
    analysis: CausalAnalysisResponse,
    node_id: str,
) -> str | None:
    node = next(
        (
            item
            for item in analysis.nodes
            if item.node_id == node_id
        ),
        None,
    )

    if node and node.entity_id:
        return node.entity_id

    if node_id.startswith("entity|"):
        value = node_id.removeprefix(
            "entity|"
        )

        return value or None

    return None


def root_entity_id_for_analysis(
    analysis: CausalAnalysisResponse,
) -> str | None:
    hypothesis = analysis.top_hypothesis

    if hypothesis is None:
        return None

    chain = sorted(
        hypothesis.chain,
        key=lambda step: step.order,
    )

    target_node_id = (
        f"event|{hypothesis.target_event_id}"
    )

    target_index = next(
        (
            index
            for index, step in enumerate(
                chain
            )
            if step.node_id
            == target_node_id
        ),
        None,
    )

    relevant_steps = (
        chain[target_index + 1 :]
        if target_index is not None
        else chain
    )

    for step in relevant_steps:
        if (
            step.node_type
            == CausalNodeType.ENTITY
            and step.relation_from_previous
            == CausalEdgeType.TOUCHES_ENTITY
        ):
            entity_id = _entity_id_for_node(
                analysis,
                step.node_id,
            )

            if entity_id:
                return entity_id

    for step in relevant_steps:
        if (
            step.node_type
            != CausalNodeType.ENTITY
        ):
            continue

        entity_id = _entity_id_for_node(
            analysis,
            step.node_id,
        )

        if entity_id:
            return entity_id

    return hypothesis.affected_entity_id


def _root_entity_id(
    analysis: CausalAnalysisResponse,
) -> str | None:
    """Backward-compatible private alias."""
    return root_entity_id_for_analysis(
        analysis
    )


def _escalation_targets(
    ownership: (
        EntityOwnershipResolution | None
    ),
    impact: IncidentOwnershipImpact,
) -> list[str]:
    values: list[str | None] = []

    if ownership is not None:
        values.extend(
            [
                ownership.oncall_contact,
                ownership.owner_email,
                ownership.owner_team,
            ]
        )

    values.extend(
        impact.oncall_contacts
    )
    values.extend(
        impact.owner_teams
    )

    return _deduplicated(values)


def build_incident_operational_context(
    session: Session,
    incident_id: str,
    *,
    causal_analysis: (
        CausalAnalysisResponse | None
    ) = None,
    ownership_impact: (
        IncidentOwnershipImpact | None
    ) = None,
) -> IncidentOperationalContext:
    analysis = causal_analysis or (
        latest_causal_analysis(
            session,
            incident_id=incident_id,
        )
    )

    if analysis is None:
        raise ValueError(
            "No causal analysis exists for "
            "this incident."
        )

    impact = ownership_impact or (
        calculate_incident_ownership_impact(
            session=session,
            incident_id=incident_id,
        )
    )

    hypothesis = analysis.top_hypothesis
    root_entity_id = root_entity_id_for_analysis(
        analysis
    )

    ownership = None
    warnings = list(impact.warnings)

    if hypothesis is None:
        warnings.append(
            "The causal analysis has no "
            "ranked causal hypothesis."
        )

    elif root_entity_id is None:
        warnings.append(
            "A root causal entity could not "
            "be determined from the top "
            "causal hypothesis."
        )

    elif not analysis.topology_snapshot_id:
        warnings.append(
            "The causal analysis does not "
            "reference a topology snapshot; "
            "root-cause ownership could not "
            "be resolved."
        )

    else:
        snapshot = load_topology_snapshot(
            session=session,
            snapshot_id=(
                analysis.topology_snapshot_id
            ),
        )

        if snapshot is None:
            warnings.append(
                "The topology snapshot "
                "referenced by the causal "
                "analysis was not found: "
                f"{analysis.topology_snapshot_id}"
            )

        else:
            entity = next(
                (
                    item
                    for item in snapshot.entities
                    if item.id == root_entity_id
                ),
                None,
            )

            if entity is None:
                warnings.append(
                    "The root causal entity "
                    "was not found in the "
                    "causal analysis topology "
                    "snapshot: "
                    f"{root_entity_id}"
                )

            else:
                try:
                    ownership = (
                        resolve_entity_ownership(
                            session=session,
                            snapshot=snapshot,
                            entity=entity,
                        )
                    )

                except ValueError as exc:
                    warnings.append(
                        "Root-cause ownership "
                        "could not be resolved: "
                        f"{exc}"
                    )

                if (
                    ownership is not None
                    and not ownership.resolved
                ):
                    warnings.append(
                        "Root-cause ownership is "
                        "unresolved for entity: "
                        f"{root_entity_id}"
                    )

    warnings = _deduplicated(warnings)

    return IncidentOperationalContext(
        incident_id=incident_id,
        causal_analysis_id=(
            analysis.analysis_id
        ),
        root_event_id=(
            hypothesis.root_event_id
            if hypothesis
            else None
        ),
        root_event_title=(
            hypothesis.root_title
            if hypothesis
            else None
        ),
        root_event_source=(
            hypothesis.root_source
            if hypothesis
            else None
        ),
        root_entity_id=root_entity_id,
        causal_confidence=(
            hypothesis.confidence
            if hypothesis
            else None
        ),
        causal_confidence_semantics=(
            analysis.confidence_semantics
        ),
        root_cause_ownership=ownership,
        overall_business_impact=impact,
        escalation_targets=(
            _escalation_targets(
                ownership,
                impact,
            )
        ),
        warnings=warnings,
    )
