from __future__ import annotations
from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    require_record_owner,
)

import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ActionApprovalEventRecord,
    ActionApprovalRecord,
)
from app.models.action_approval import (
    ActionApprovalAuditEvent,
    ActionApprovalEventType,
    ActionApprovalReadinessSnapshot,
    ActionApprovalStatus,
)
from app.security.api_tokens import (
    AuthPrincipal,
)

ACTIVE_APPROVAL_STATUSES = {
    ActionApprovalStatus.PENDING.value,
    ActionApprovalStatus.APPROVED.value,
}


def load_action_approval_record(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    tenant_id: DomainTenant,
) -> ActionApprovalRecord | None:
    statement = (
        select(ActionApprovalRecord)
        .where(tenant_predicate(ActionApprovalRecord, tenant_id))
        .where(
            ActionApprovalRecord.incident_id == incident_id,
            ActionApprovalRecord.approval_id == approval_id,
        )
        .limit(1)
    )

    return session.scalar(statement)


def list_action_approval_records(
    session: Session,
    *,
    incident_id: str,
    status: ActionApprovalStatus | None = None,
    action_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    tenant_id: DomainTenant,
) -> list[ActionApprovalRecord]:
    statement = (
        select(ActionApprovalRecord)
        .where(tenant_predicate(ActionApprovalRecord, tenant_id))
        .where(ActionApprovalRecord.incident_id == incident_id)
    )

    if status is not None:
        statement = statement.where(
            ActionApprovalRecord.status
            == status.value
        )

    if action_id is not None:
        statement = statement.where(
            ActionApprovalRecord.action_id
            == action_id
        )

    statement = (
        statement
        .order_by(
            ActionApprovalRecord.requested_at.desc(),
            ActionApprovalRecord.approval_id.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 100)))
    )

    return list(
        session.scalars(statement).all()
    )


def list_active_action_approval_records(
    session: Session,
    *,
    incident_id: str,
    action_id: str,
    tenant_id: DomainTenant,
) -> list[ActionApprovalRecord]:
    statement = (
        select(ActionApprovalRecord)
        .where(tenant_predicate(ActionApprovalRecord, tenant_id))
        .where(
            ActionApprovalRecord.incident_id == incident_id,
            ActionApprovalRecord.action_id == action_id,
            ActionApprovalRecord.status.in_(ACTIVE_APPROVAL_STATUSES),
        )
        .order_by(
            ActionApprovalRecord.requested_at.asc(),
            ActionApprovalRecord.approval_id.asc(),
        )
    )

    return list(
        session.scalars(statement).all()
    )


def find_pending_action_approval_record(
    session: Session,
    *,
    pending_key: str,
    tenant_id: DomainTenant,
) -> ActionApprovalRecord | None:
    statement = (
        select(ActionApprovalRecord)
        .where(tenant_predicate(ActionApprovalRecord, tenant_id))
        .where(
            ActionApprovalRecord.pending_key == pending_key,
            ActionApprovalRecord.status == ActionApprovalStatus.PENDING.value,
        )
        .limit(1)
    )

    return session.scalar(statement)


def approval_snapshot(
    record: ActionApprovalRecord,
) -> ActionApprovalReadinessSnapshot:
    return (
        ActionApprovalReadinessSnapshot
        .model_validate_json(
            record.readiness_snapshot_json
        )
    )


def _event_record(
    *,
    record: ActionApprovalRecord,
    sequence: int,
    event_type: ActionApprovalEventType,
    from_status: ActionApprovalStatus | None,
    to_status: ActionApprovalStatus,
    actor: AuthPrincipal,
    reason: str | None,
    occurred_at: datetime,
    tenant_id: DomainTenant,
) -> ActionApprovalEventRecord:
    require_record_owner(record, tenant_id=tenant_id)
    return ActionApprovalEventRecord(
        event_id=("approval-event:" f"{uuid4().hex}"),
        sequence=sequence,
        approval_id=record.approval_id,
        incident_id=record.incident_id,
        action_id=record.action_id,
        event_type=event_type.value,
        from_status=(from_status.value if from_status is not None else None),
        to_status=to_status.value,
        actor_subject=actor.subject,
        actor_display_name=(actor.display_name),
        actor_roles_json=json.dumps(
            list(actor.roles),
            sort_keys=True,
        ),
        authentication_type=(actor.authentication_type),
        reason=reason,
        evidence_fingerprint=(record.evidence_fingerprint),
        occurred_at=occurred_at.isoformat(),
        tenant_id=tenant_value(tenant_id),
    )


def create_action_approval_record(
    session: Session,
    *,
    incident_id: str,
    snapshot: ActionApprovalReadinessSnapshot,
    evidence_fingerprint: str,
    pending_key: str,
    requester: AuthPrincipal,
    request_reason: str | None,
    requested_at: datetime,
    expires_at: datetime,
    tenant_id: DomainTenant,
) -> tuple[ActionApprovalRecord, bool]:
    existing = find_pending_action_approval_record(
        session,
        pending_key=pending_key,
        tenant_id=tenant_id,
    )

    if existing is not None:
        return existing, False

    timestamp = requested_at.isoformat()
    record = ActionApprovalRecord(
        approval_id=("approval:" f"{uuid4().hex}"),
        incident_id=incident_id,
        action_id=snapshot.action_id,
        action_family=(snapshot.action_family.value),
        status=(ActionApprovalStatus.PENDING.value),
        risk=snapshot.risk.value,
        requires_human_approval=(snapshot.requires_human_approval),
        policy_version=(snapshot.policy_version),
        readiness_status_at_request=(snapshot.readiness_status.value),
        evidence_fingerprint=(evidence_fingerprint),
        target_entity_ids_json=json.dumps(
            snapshot.target.entity_ids,
            sort_keys=True,
        ),
        target_change_event_id=(snapshot.target.change_event_id),
        readiness_snapshot_json=(snapshot.model_dump_json()),
        pending_key=pending_key,
        request_reason=request_reason,
        requested_by_subject=(requester.subject),
        requested_by_display_name=(requester.display_name),
        requested_by_roles_json=json.dumps(
            list(requester.roles),
            sort_keys=True,
        ),
        requested_at=timestamp,
        expires_at=expires_at.isoformat(),
        created_at=timestamp,
        updated_at=timestamp,
        tenant_id=tenant_value(tenant_id),
    )
    session.add(record)
    session.add(
        _event_record(
            record=record,
            sequence=1,
            event_type=(ActionApprovalEventType.REQUESTED),
            from_status=None,
            to_status=(ActionApprovalStatus.PENDING),
            actor=requester,
            reason=request_reason,
            occurred_at=requested_at,
            tenant_id=tenant_id,
        )
    )

    try:
        tenant_commit(session, tenant_id=tenant_id)
    except IntegrityError:
        session.rollback()
        existing = find_pending_action_approval_record(
            session,
            pending_key=pending_key,
            tenant_id=tenant_id,
        )

        if existing is not None:
            return existing, False

        raise

    session.refresh(record)

    return record, True


def transition_action_approval_record(
    session: Session,
    *,
    record: ActionApprovalRecord,
    new_status: ActionApprovalStatus,
    event_type: ActionApprovalEventType,
    actor: AuthPrincipal,
    reason: str | None,
    occurred_at: datetime,
    tenant_id: DomainTenant,
) -> ActionApprovalRecord:
    require_record_owner(record, tenant_id=tenant_id)
    old_status = ActionApprovalStatus(
        record.status
    )
    timestamp = occurred_at.isoformat()
    sequence = (
        session.scalar(
            select(func.max(ActionApprovalEventRecord.sequence))
            .where(tenant_predicate(ActionApprovalEventRecord, tenant_id))
            .where(ActionApprovalEventRecord.approval_id == record.approval_id)
        )
        or 0
    ) + 1

    record.status = new_status.value
    record.pending_key = None
    record.updated_at = timestamp

    if new_status in {
        ActionApprovalStatus.APPROVED,
        ActionApprovalStatus.REJECTED,
    }:
        record.decided_by_subject = (
            actor.subject
        )
        record.decided_by_display_name = (
            actor.display_name
        )
        record.decided_by_roles_json = (
            json.dumps(
                list(actor.roles),
                sort_keys=True,
            )
        )
        record.decided_at = timestamp
        record.decision_reason = reason

    elif (
        new_status
        == ActionApprovalStatus.REVOKED
    ):
        record.revoked_by_subject = (
            actor.subject
        )
        record.revoked_by_display_name = (
            actor.display_name
        )
        record.revoked_at = timestamp
        record.revocation_reason = reason

    elif (
        new_status
        == ActionApprovalStatus.INVALIDATED
    ):
        record.invalidated_at = timestamp
        record.invalidation_reason = reason

    session.add(
        _event_record(
            record=record,
            sequence=sequence,
            event_type=event_type,
            from_status=old_status,
            to_status=new_status,
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
            tenant_id=tenant_id,
        )
    )
    tenant_commit(session, tenant_id=tenant_id)
    session.refresh(record)

    return record


def list_action_approval_events(
    session: Session,
    *,
    approval_id: str,
    tenant_id: DomainTenant,
) -> list[ActionApprovalAuditEvent]:
    statement = (
        select(ActionApprovalEventRecord)
        .where(tenant_predicate(ActionApprovalEventRecord, tenant_id))
        .where(ActionApprovalEventRecord.approval_id == approval_id)
        .order_by(
            ActionApprovalEventRecord.sequence.asc(),
        )
    )
    records = list(
        session.scalars(statement).all()
    )

    return [
        ActionApprovalAuditEvent(
            event_id=record.event_id,
            sequence=record.sequence,
            approval_id=record.approval_id,
            incident_id=record.incident_id,
            action_id=record.action_id,
            event_type=(
                ActionApprovalEventType(
                    record.event_type
                )
            ),
            from_status=(
                ActionApprovalStatus(
                    record.from_status
                )
                if record.from_status
                else None
            ),
            to_status=(
                ActionApprovalStatus(
                    record.to_status
                )
            ),
            actor_subject=(
                record.actor_subject
            ),
            actor_display_name=(
                record.actor_display_name
            ),
            actor_roles=json.loads(
                record.actor_roles_json
            ),
            authentication_type=(
                record.authentication_type
            ),
            reason=record.reason,
            evidence_fingerprint=(
                record.evidence_fingerprint
            ),
            occurred_at=(
                datetime.fromisoformat(
                    record.occurred_at
                )
            ),
        )
        for record in records
    ]
