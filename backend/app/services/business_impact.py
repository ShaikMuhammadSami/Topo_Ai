from app.repositories.tenant_scope import (
    DomainTenant,
)
from sqlalchemy.orm import Session

from app.models.ownership import (
    AffectedEntityOwnership,
    BusinessImpactLevel,
    IncidentOwnershipImpact,
    ServiceCriticality,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.blast_radius import (
    calculate_blast_radius,
)
from app.services.ownership_resolver import (
    resolve_entity_ownership,
)

CRITICALITY_PRIORITY = {
    ServiceCriticality.TIER_1: 4,
    ServiceCriticality.TIER_2: 3,
    ServiceCriticality.TIER_3: 2,
    ServiceCriticality.TIER_4: 1,
}


from app.services.tenant_world_model import tenant_world

def _highest_criticality(
    values: list[
        ServiceCriticality
    ],
) -> ServiceCriticality | None:
    if not values:
        return None

    return max(
        values,
        key=lambda value:
            CRITICALITY_PRIORITY[
                value
            ],
    )


def _business_impact_level(
    highest: ServiceCriticality | None,
    capability_count: int,
    team_count: int,
) -> BusinessImpactLevel:
    if (
        highest
        == ServiceCriticality.TIER_1
    ):
        return (
            BusinessImpactLevel.CRITICAL
        )

    if (
        highest
        == ServiceCriticality.TIER_2
        or capability_count >= 3
    ):
        return BusinessImpactLevel.HIGH

    if (
        highest
        == ServiceCriticality.TIER_3
        or capability_count >= 1
        or team_count >= 2
    ):
        return BusinessImpactLevel.MEDIUM

    if (
        highest
        == ServiceCriticality.TIER_4
        or team_count == 1
    ):
        return BusinessImpactLevel.LOW

    return BusinessImpactLevel.NONE


def _routing_recommendation(
    teams: list[str],
    oncall_contacts: list[str],
    unresolved_count: int,
) -> str:
    if oncall_contacts:
        return (
            "Route the incident to "
            + ", ".join(oncall_contacts)
            + "."
        )

    if teams:
        return (
            "Route the incident to "
            + ", ".join(teams)
            + "."
        )

    if unresolved_count:
        return (
            "Ownership is unresolved. "
            "Route to the platform or "
            "service-catalog team for triage."
        )

    return (
        "No ownership routing action "
        "is currently required."
    )


@tenant_world(prefetched=())
def calculate_incident_ownership_impact(
    session: Session,
    incident_id: str,
    *,
    tenant_id: DomainTenant,
) -> IncidentOwnershipImpact:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )

    if incident is None:
        raise ValueError(
            "Incident not found: "
            f"{incident_id}"
        )

    if not incident.topology_snapshot_id:
        raise ValueError(
            "Incident does not reference "
            "a topology snapshot."
        )

    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=(incident.topology_snapshot_id),
        tenant_id=tenant_id,
    )

    if snapshot is None:
        raise ValueError(
            "Topology snapshot not found: "
            f"{incident.topology_snapshot_id}"
        )

    blast_radius = calculate_blast_radius(
        session=session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )

    entity_map = {
        entity.id: entity
        for entity in snapshot.entities
    }

    affected: list[
        AffectedEntityOwnership
    ] = []

    owner_teams: set[str] = set()
    capabilities: set[str] = set()
    oncall_contacts: set[str] = set()
    repositories: set[str] = set()

    criticalities: list[
        ServiceCriticality
    ] = []

    resolved_count = 0
    unresolved_count = 0

    warnings: list[str] = []

    for impacted in blast_radius.affected_entities:
        entity = entity_map.get(
            impacted.entity_id
        )

        if entity is None:
            warnings.append(
                "Affected entity was not "
                "found in the snapshot: "
                f"{impacted.entity_id}"
            )
            continue

        ownership = resolve_entity_ownership(
            session=session,
            snapshot=snapshot,
            entity=entity,
            tenant_id=tenant_id,
        )

        if ownership.resolved:
            resolved_count += 1

            if ownership.owner_team:
                owner_teams.add(
                    ownership.owner_team
                )

            if (
                ownership
                .business_capability
            ):
                capabilities.add(
                    ownership
                    .business_capability
                )

            if ownership.oncall_contact:
                oncall_contacts.add(
                    ownership.oncall_contact
                )

            if ownership.repository_url:
                repositories.add(
                    ownership.repository_url
                )

            if ownership.criticality:
                criticalities.append(
                    ownership.criticality
                )
        else:
            unresolved_count += 1

        affected.append(
            AffectedEntityOwnership(
                entity_id=(
                    impacted.entity_id
                ),
                entity_kind=(
                    impacted.entity_kind
                    or entity.kind
                ),
                entity_name=(
                    impacted.entity_name
                ),
                impact=impacted.impact,
                distance=(
                    impacted.distance
                ),
                impact_score=(
                    impacted.impact_score
                ),
                ownership=ownership,
            )
        )

    teams = sorted(owner_teams)
    capability_values = sorted(
        capabilities
    )

    contacts = sorted(
        oncall_contacts
    )

    repository_values = sorted(
        repositories
    )

    highest = _highest_criticality(
        criticalities
    )

    impact_level = (
        _business_impact_level(
            highest=highest,
            capability_count=len(
                capability_values
            ),
            team_count=len(teams),
        )
    )

    if unresolved_count:
        warnings.append(
            f"{unresolved_count} affected "
            "entities have unresolved ownership."
        )

    return IncidentOwnershipImpact(
        incident_id=incident_id,
        business_impact_level=(
            impact_level
        ),
        affected_entity_count=len(
            affected
        ),
        resolved_entity_count=(
            resolved_count
        ),
        unresolved_entity_count=(
            unresolved_count
        ),
        affected_team_count=len(
            teams
        ),
        affected_capability_count=len(
            capability_values
        ),
        highest_criticality=highest,
        owner_teams=teams,
        business_capabilities=(
            capability_values
        ),
        oncall_contacts=contacts,
        repositories=repository_values,
        routing_recommendation=(
            _routing_recommendation(
                teams=teams,
                oncall_contacts=contacts,
                unresolved_count=(
                    unresolved_count
                ),
            )
        ),
        affected_entities=affected,
        warnings=warnings,
    )
