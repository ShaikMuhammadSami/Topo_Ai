from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    OwnershipMappingRecord,
    utc_now_iso,
)
from app.models.ownership import (
    OwnershipMappingView,
    OwnershipSource,
    ServiceCriticality,
)


def _to_view(
    record: OwnershipMappingRecord,
) -> OwnershipMappingView:
    return OwnershipMappingView(
        ownership_id=record.ownership_id,
        entity_id=record.entity_id,
        service_name=record.service_name,
        cluster_name=record.cluster_name,
        namespace=record.namespace,
        entity_kind=record.entity_kind,
        entity_name=record.entity_name,
        environment=record.environment,
        owner_team=record.owner_team,
        owner_email=record.owner_email,
        oncall_contact=record.oncall_contact,
        repository_url=record.repository_url,
        business_capability=(
            record.business_capability
        ),
        criticality=ServiceCriticality(
            record.criticality
        ),
        source=OwnershipSource(
            record.source
        ),
        active=record.active,
        notes=record.notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def load_ownership_mapping(
    session: Session,
    ownership_id: str,
) -> OwnershipMappingView | None:
    record = session.get(
        OwnershipMappingRecord,
        ownership_id,
    )

    if record is None:
        return None

    return _to_view(record)


def get_ownership_by_fingerprint(
    session: Session,
    fingerprint: str,
) -> OwnershipMappingRecord | None:
    statement = select(
        OwnershipMappingRecord
    ).where(
        OwnershipMappingRecord.fingerprint
        == fingerprint
    )

    return session.scalars(
        statement
    ).first()


def find_active_ownership_mappings(
    session: Session,
    cluster_name: str | None,
    namespace: str | None,
    entity_id: str,
    entity_kind: str,
    entity_name: str,
    service_name: str | None,
    environment: str | None,
) -> list[OwnershipMappingRecord]:
    statement = select(
        OwnershipMappingRecord
    ).where(
        OwnershipMappingRecord.active
        .is_(True)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    matches: list[
        OwnershipMappingRecord
    ] = []

    for record in records:
        if (
            record.cluster_name
            and record.cluster_name
            != cluster_name
        ):
            continue

        if (
            record.namespace
            and record.namespace
            != namespace
        ):
            continue

        if (
            record.environment
            and record.environment
            != environment
        ):
            continue

        exact_match = (
            record.entity_id
            and record.entity_id
            == entity_id
        )

        service_match = (
            record.service_name
            and service_name
            and record.service_name
            == service_name
        )

        object_match = (
            record.entity_kind
            and record.entity_name
            and record.entity_kind
            == entity_kind
            and record.entity_name
            == entity_name
        )

        if (
            exact_match
            or service_match
            or object_match
        ):
            matches.append(record)

    return matches


def list_ownership_mappings(
    session: Session,
    owner_team: str | None = None,
    namespace: str | None = None,
    active: bool | None = True,
    limit: int = 200,
) -> list[OwnershipMappingView]:
    statement = select(
        OwnershipMappingRecord
    )

    if owner_team:
        statement = statement.where(
            OwnershipMappingRecord.owner_team
            == owner_team
        )

    if namespace:
        statement = statement.where(
            OwnershipMappingRecord.namespace
            == namespace
        )

    if active is not None:
        statement = statement.where(
            OwnershipMappingRecord.active
            == active
        )

    statement = (
        statement
        .order_by(
            OwnershipMappingRecord
            .updated_at
            .desc()
        )
        .limit(limit)
    )

    records = list(
        session.scalars(
            statement
        ).all()
    )

    return [
        _to_view(record)
        for record in records
    ]


def save_ownership_mapping(
    session: Session,
    record: OwnershipMappingRecord,
) -> OwnershipMappingView:
    existing = (
        get_ownership_by_fingerprint(
            session=session,
            fingerprint=(
                record.fingerprint
            ),
        )
    )

    if existing is None:
        session.add(record)
        session.commit()
        session.refresh(record)

        return _to_view(record)

    existing.entity_id = record.entity_id
    existing.service_name = (
        record.service_name
    )

    existing.cluster_name = (
        record.cluster_name
    )

    existing.namespace = (
        record.namespace
    )

    existing.entity_kind = (
        record.entity_kind
    )

    existing.entity_name = (
        record.entity_name
    )

    existing.environment = (
        record.environment
    )

    existing.owner_team = (
        record.owner_team
    )

    existing.owner_email = (
        record.owner_email
    )

    existing.oncall_contact = (
        record.oncall_contact
    )

    existing.repository_url = (
        record.repository_url
    )

    existing.business_capability = (
        record.business_capability
    )

    existing.criticality = (
        record.criticality
    )

    existing.source = record.source
    existing.active = record.active
    existing.notes = record.notes

    existing.updated_at = utc_now_iso()

    session.commit()
    session.refresh(existing)

    return _to_view(existing)