from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IdentityOverrideRecord,
    IdentityResolutionRecord,
    utc_now_iso,
)
from app.models.identity import (
    IdentityOverrideAction,
    IdentityOverrideCreate,
    IdentityOverrideView,
    IdentityResolutionResult,
    IdentityResolutionSummary,
)


def save_identity_resolution(
    session: Session,
    result: IdentityResolutionResult,
    *,
    tenant_id: DomainTenant,
) -> IdentityResolutionRecord:
    record = tenant_get(
        session,
        IdentityResolutionRecord,
        result.snapshot_id,
        tenant_id=tenant_id,
    )

    now = utc_now_iso()

    if record is None:
        record = IdentityResolutionRecord(
            snapshot_id=result.snapshot_id,
            generated_at=(result.generated_at.isoformat()),
            identity_count=len(result.identities),
            unresolved_count=len(result.unresolved_entity_ids),
            excluded_count=len(result.excluded_entity_ids),
            payload_json=(result.model_dump_json()),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)

    else:
        record.generated_at = (
            result.generated_at.isoformat()
        )

        record.identity_count = len(
            result.identities
        )

        record.unresolved_count = len(
            result.unresolved_entity_ids
        )

        record.excluded_count = len(
            result.excluded_entity_ids
        )

        record.payload_json = (
            result.model_dump_json()
        )

        record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record


def load_identity_resolution(
    session: Session,
    snapshot_id: str,
    *,
    tenant_id: DomainTenant,
) -> IdentityResolutionResult | None:
    record = tenant_get(
        session,
        IdentityResolutionRecord,
        snapshot_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return None

    return (
        IdentityResolutionResult
        .model_validate_json(
            record.payload_json
        )
    )


def identity_resolution_summary(
    record: IdentityResolutionRecord,
) -> IdentityResolutionSummary:
    return IdentityResolutionSummary(
        snapshot_id=record.snapshot_id,
        generated_at=datetime.fromisoformat(
            record.generated_at
        ),
        identity_count=record.identity_count,
        unresolved_count=(
            record.unresolved_count
        ),
        excluded_count=record.excluded_count,
    )


def record_to_override_view(
    record: IdentityOverrideRecord,
) -> IdentityOverrideView:
    return IdentityOverrideView(
        override_id=record.override_id,
        cluster_name=record.cluster_name,
        namespace=record.namespace,
        entity_kind=record.entity_kind,
        entity_name=record.entity_name,
        action=IdentityOverrideAction(
            record.action
        ),
        canonical_name=record.canonical_name,
        reason=record.reason,
        active=record.active,
        created_at=datetime.fromisoformat(
            record.created_at
        ),
        updated_at=datetime.fromisoformat(
            record.updated_at
        ),
    )


def upsert_identity_override(
    session: Session,
    request: IdentityOverrideCreate,
    *,
    tenant_id: DomainTenant,
) -> IdentityOverrideView:
    statement = (
        select(IdentityOverrideRecord)
        .where(tenant_predicate(IdentityOverrideRecord, tenant_id))
        .where(
            IdentityOverrideRecord.cluster_name == request.cluster_name,
            IdentityOverrideRecord.namespace == request.namespace,
            IdentityOverrideRecord.entity_kind == request.entity_kind,
            IdentityOverrideRecord.entity_name == request.entity_name,
        )
    )

    record = session.scalar(statement)

    now = utc_now_iso()

    canonical_name = (
        request.canonical_name
        if request.action
        == IdentityOverrideAction.ASSIGN
        else None
    )

    if record is None:
        record = IdentityOverrideRecord(
            override_id=(f"override:{uuid4()}"),
            cluster_name=request.cluster_name,
            namespace=request.namespace,
            entity_kind=request.entity_kind,
            entity_name=request.entity_name,
            action=request.action.value,
            canonical_name=canonical_name,
            reason=request.reason,
            active=True,
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)

    else:
        record.action = request.action.value
        record.canonical_name = canonical_name
        record.reason = request.reason
        record.active = True
        record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record_to_override_view(record)


def list_identity_overrides(
    session: Session,
    cluster_name: str | None = None,
    namespace: str | None = None,
    active_only: bool = True,
    *,
    tenant_id: DomainTenant,
) -> list[IdentityOverrideView]:
    statement = select(IdentityOverrideRecord).where(
        tenant_predicate(IdentityOverrideRecord, tenant_id)
    )

    if cluster_name:
        statement = statement.where(
            IdentityOverrideRecord.cluster_name
            == cluster_name
        )

    if namespace:
        statement = statement.where(
            IdentityOverrideRecord.namespace
            == namespace
        )

    if active_only:
        statement = statement.where(
            IdentityOverrideRecord.active
            .is_(True)
        )

    statement = statement.order_by(
        IdentityOverrideRecord.namespace,
        IdentityOverrideRecord.entity_kind,
        IdentityOverrideRecord.entity_name,
    )

    records = list(
        session.scalars(statement).all()
    )

    return [
        record_to_override_view(record)
        for record in records
    ]


def deactivate_identity_override(
    session: Session,
    override_id: str,
    *,
    tenant_id: DomainTenant,
) -> bool:
    record = tenant_get(
        session,
        IdentityOverrideRecord,
        override_id,
        tenant_id=tenant_id,
    )

    if record is None:
        return False

    record.active = False
    record.updated_at = utc_now_iso()

    tenant_commit(session, tenant_id=tenant_id)

    return True
