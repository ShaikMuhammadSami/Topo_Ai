from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    tenant_value,
)

from hashlib import sha256

from sqlalchemy.orm import Session

from app.db.models import (
    OwnershipMappingRecord,
    utc_now_iso,
)
from app.models.ownership import (
    EntityOwnershipResolution,
    OwnershipMappingCreate,
    OwnershipSource,
    ServiceCriticality,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)
from app.repositories.ownership_repository import (
    find_active_ownership_mappings,
    save_ownership_mapping,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.canonical_identity import (
    canonical_identity_for_entity,
    entity_aliases,
    resolve_snapshot_entity_identity,
    resolved_snapshot_entity,
)

OWNER_KEYS = (
    "topo.ai/owner-team",
    "app.kubernetes.io/owner",
    "owner_team",
    "owner",
    "team",
)

OWNER_EMAIL_KEYS = (
    "topo.ai/owner-email",
    "owner_email",
)

ONCALL_KEYS = (
    "topo.ai/oncall",
    "oncall",
    "on_call",
)

REPOSITORY_KEYS = (
    "topo.ai/repository",
    "repository",
    "repository_url",
    "repo",
)

CAPABILITY_KEYS = (
    "topo.ai/business-capability",
    "business_capability",
    "capability",
)

CRITICALITY_KEYS = (
    "topo.ai/criticality",
    "criticality",
    "service_tier",
)


def stable_service_name(
    entity: Entity,
) -> str:
    explicit = (
        entity.properties.get(
            "service_name"
        )
        or entity.labels.get(
            "topo.ai/service-name"
        )
        or entity.labels.get(
            "app.kubernetes.io/name"
        )
        or entity.labels.get("app")
    )

    if explicit:
        return str(explicit)

    name = entity.name
    kind = entity.kind.lower()

    parts = name.split("-")

    if (
        "pod" in kind
        and len(parts) >= 3
    ):
        return "-".join(
            parts[:-2]
        )

    if (
        "replicaset" in kind
        and len(parts) >= 2
    ):
        return "-".join(
            parts[:-1]
        )

    return name


def _metadata_value(
    entity: Entity,
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        label_value = entity.labels.get(
            key
        )

        if label_value:
            return str(label_value)

        property_value = (
            entity.properties.get(key)
        )

        if property_value:
            return str(property_value)

    return None


def _criticality_from_value(
    value: str | None,
) -> ServiceCriticality:
    if not value:
        return ServiceCriticality.TIER_3

    normalized = (
        value.lower()
        .replace("-", "_")
        .replace(" ", "_")
    )

    aliases = {
        "1": "tier_1",
        "critical": "tier_1",
        "tier1": "tier_1",
        "2": "tier_2",
        "high": "tier_2",
        "tier2": "tier_2",
        "3": "tier_3",
        "medium": "tier_3",
        "tier3": "tier_3",
        "4": "tier_4",
        "low": "tier_4",
        "tier4": "tier_4",
    }

    normalized = aliases.get(
        normalized,
        normalized,
    )

    try:
        return ServiceCriticality(
            normalized
        )
    except ValueError:
        return ServiceCriticality.TIER_3


def _mapping_priority(
    record: OwnershipMappingRecord,
    entity: Entity,
    service_name: str,
    entity_ids: set[str] | None = None,
) -> tuple[int, int]:
    if (
        record.entity_id
        in (entity_ids or {entity.id})
    ):
        return (3, 100)

    if (
        record.service_name
        == service_name
    ):
        specificity = sum(
            value is not None
            for value in (
                record.cluster_name,
                record.namespace,
                record.environment,
            )
        )

        return (2, specificity)

    return (1, 0)


def _mapping_confidence(
    record: OwnershipMappingRecord,
    entity: Entity,
    service_name: str,
    entity_ids: set[str] | None = None,
) -> float:
    priority, specificity = (
        _mapping_priority(
            record=record,
            entity=entity,
            service_name=service_name,
            entity_ids=entity_ids,
        )
    )

    if priority == 3:
        return 1.0

    if priority == 2:
        return min(
            0.99,
            0.90
            + specificity * 0.02,
        )

    return 0.85


def create_ownership_mapping(
    session: Session,
    request: OwnershipMappingCreate,
    *,
    tenant_id: DomainTenant,
):
    value = "|".join(
        [
            request.entity_id or "",
            request.service_name or "",
            request.cluster_name or "",
            request.namespace or "",
            request.entity_kind or "",
            request.entity_name or "",
            request.environment or "",
        ]
    )

    fingerprint = sha256(
        value.encode("utf-8")
    ).hexdigest()

    ownership_id = (
        "ownership:"
        f"{fingerprint[:32]}"
    )

    record = OwnershipMappingRecord(
        ownership_id=ownership_id,
        fingerprint=fingerprint,
        entity_id=request.entity_id,
        service_name=(request.service_name),
        cluster_name=(request.cluster_name),
        namespace=request.namespace,
        entity_kind=(request.entity_kind),
        entity_name=(request.entity_name),
        environment=(request.environment),
        owner_team=request.owner_team,
        owner_email=(request.owner_email),
        oncall_contact=(request.oncall_contact),
        repository_url=(request.repository_url),
        business_capability=(request.business_capability),
        criticality=(request.criticality.value),
        source=request.source.value,
        active=True,
        notes=request.notes,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
        tenant_id=tenant_value(tenant_id),
    )

    return save_ownership_mapping(
        session=session,
        record=record,
        tenant_id=tenant_id,
    )


def resolve_entity_ownership(
    session: Session,
    snapshot: GraphSnapshot,
    entity: Entity,
    *,
    tenant_id: DomainTenant,
) -> EntityOwnershipResolution:
    from app.services.tenant_world_model import bind_world_value

    bind_world_value(snapshot, tenant_id=tenant_id)
    bind_world_value(entity, tenant_id=tenant_id)
    service_name = stable_service_name(
        entity
    )
    canonical_identity = canonical_identity_for_entity(
        entity,
        snapshot,
    )
    accepted_entity_ids = {
        entity.id,
        canonical_identity.canonical_id,
        *entity_aliases(entity, snapshot),
    }

    cluster_name = (
        entity.properties.get(
            "cluster"
        )
        or snapshot.scope.get(
            "cluster"
        )
    )

    namespace = entity.properties.get(
        "namespace"
    )

    environment = (
        entity.environment
        or snapshot.scope.get(
            "environment"
        )
    )

    mappings = find_active_ownership_mappings(
        session=session,
        cluster_name=(str(cluster_name) if cluster_name else None),
        namespace=(str(namespace) if namespace else None),
        entity_id=entity.id,
        entity_kind=entity.kind,
        entity_name=entity.name,
        service_name=service_name,
        environment=environment,
        entity_ids=sorted(accepted_entity_ids),
        tenant_id=tenant_id,
    )

    if mappings:
        selected = sorted(
            mappings,
            key=lambda record:
                _mapping_priority(
                    record=record,
                    entity=entity,
                    service_name=(
                        service_name
                    ),
                    entity_ids=(
                        accepted_entity_ids
                    ),
                ),
            reverse=True,
        )[0]

        confidence = (
            _mapping_confidence(
                record=selected,
                entity=entity,
                service_name=(
                    service_name
                ),
                entity_ids=(
                    accepted_entity_ids
                ),
            )
        )

        return EntityOwnershipResolution(
            resolved=True,
            entity_id=entity.id,
            entity_kind=entity.kind,
            entity_name=entity.name,
            service_name=service_name,
            cluster_name=(
                str(cluster_name)
                if cluster_name
                else None
            ),
            namespace=(
                str(namespace)
                if namespace
                else None
            ),
            owner_team=(
                selected.owner_team
            ),
            owner_email=(
                selected.owner_email
            ),
            oncall_contact=(
                selected.oncall_contact
            ),
            repository_url=(
                selected.repository_url
            ),
            business_capability=(
                selected.business_capability
            ),
            criticality=(
                ServiceCriticality(
                    selected.criticality
                )
            ),
            source=OwnershipSource(
                selected.source
            ),
            confidence=confidence,
            matched_ownership_id=(
                selected.ownership_id
            ),
            resolution_reason=(
                "Resolved from a stored "
                "ownership mapping."
            ),
        )

    owner_team = _metadata_value(
        entity,
        OWNER_KEYS,
    )

    if owner_team:
        criticality = (
            _criticality_from_value(
                _metadata_value(
                    entity,
                    CRITICALITY_KEYS,
                )
            )
        )

        return EntityOwnershipResolution(
            resolved=True,
            entity_id=entity.id,
            entity_kind=entity.kind,
            entity_name=entity.name,
            service_name=service_name,
            cluster_name=(
                str(cluster_name)
                if cluster_name
                else None
            ),
            namespace=(
                str(namespace)
                if namespace
                else None
            ),
            owner_team=owner_team,
            owner_email=_metadata_value(
                entity,
                OWNER_EMAIL_KEYS,
            ),
            oncall_contact=(
                _metadata_value(
                    entity,
                    ONCALL_KEYS,
                )
            ),
            repository_url=(
                _metadata_value(
                    entity,
                    REPOSITORY_KEYS,
                )
            ),
            business_capability=(
                _metadata_value(
                    entity,
                    CAPABILITY_KEYS,
                )
            ),
            criticality=criticality,
            source=(
                OwnershipSource
                .ENTITY_METADATA
            ),
            confidence=0.75,
            matched_ownership_id=None,
            resolution_reason=(
                "Resolved from entity labels "
                "or properties."
            ),
        )

    return EntityOwnershipResolution(
        resolved=False,
        entity_id=entity.id,
        entity_kind=entity.kind,
        entity_name=entity.name,
        service_name=service_name,
        cluster_name=(
            str(cluster_name)
            if cluster_name
            else None
        ),
        namespace=(
            str(namespace)
            if namespace
            else None
        ),
        owner_team=None,
        owner_email=None,
        oncall_contact=None,
        repository_url=None,
        business_capability=None,
        criticality=None,
        source=OwnershipSource.UNRESOLVED,
        confidence=0.0,
        matched_ownership_id=None,
        resolution_reason=(
            "No matching ownership mapping "
            "or ownership metadata was found."
        ),
    )


def resolve_ownership_by_ids(
    session: Session,
    snapshot_id: str,
    entity_id: str,
    *,
    tenant_id: DomainTenant,
) -> EntityOwnershipResolution:
    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_id,
    )

    if snapshot is None:
        raise ValueError(
            "Topology snapshot not found: "
            f"{snapshot_id}"
        )

    resolution = resolve_snapshot_entity_identity(
        snapshot,
        identifier=entity_id,
    )
    entity = resolved_snapshot_entity(
        snapshot,
        resolution,
    )

    if entity is None:
        raise ValueError(
            "Entity was not found in the "
            "selected snapshot: "
            f"{entity_id}"
        )

    return resolve_entity_ownership(
        session=session,
        snapshot=snapshot,
        entity=entity,
        tenant_id=tenant_id,
    )
