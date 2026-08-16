from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ExecutionIntentEventRecord,
    ExecutionIntentRecord,
)
from app.models.execution_transaction import (
    ExecutionContractSnapshot,
    ExecutionIntentAuditEvent,
    ExecutionIntentEventType,
    ExecutionIntentStatus,
)
from app.security.api_tokens import AuthPrincipal


ACTIVE_EXECUTION_INTENT_STATUSES = {
    ExecutionIntentStatus.PENDING.value,
    ExecutionIntentStatus.CLAIMED.value,
}


def load_execution_intent_record(
    session: Session,
    *,
    incident_id: str,
    execution_id: str,
) -> ExecutionIntentRecord | None:
    statement = (
        select(ExecutionIntentRecord)
        .where(
            ExecutionIntentRecord.incident_id
            == incident_id,
            ExecutionIntentRecord.execution_id
            == execution_id,
        )
        .execution_options(populate_existing=True)
        .limit(1)
    )

    return session.scalar(statement)


def load_execution_intent_by_key(
    session: Session,
    *,
    idempotency_key: str,
) -> ExecutionIntentRecord | None:
    statement = (
        select(ExecutionIntentRecord)
        .where(
            ExecutionIntentRecord.idempotency_key
            == idempotency_key
        )
        .execution_options(populate_existing=True)
        .limit(1)
    )

    return session.scalar(statement)


def load_execution_intent_by_approval(
    session: Session,
    *,
    approval_id: str,
) -> ExecutionIntentRecord | None:
    statement = (
        select(ExecutionIntentRecord)
        .where(
            ExecutionIntentRecord.approval_id
            == approval_id
        )
        .execution_options(populate_existing=True)
        .limit(1)
    )

    return session.scalar(statement)


def list_execution_intent_records(
    session: Session,
    *,
    incident_id: str,
    status: ExecutionIntentStatus | None = None,
    approval_id: str | None = None,
    action_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ExecutionIntentRecord]:
    statement = select(
        ExecutionIntentRecord
    ).where(
        ExecutionIntentRecord.incident_id
        == incident_id
    )

    if status is not None:
        statement = statement.where(
            ExecutionIntentRecord.status
            == status.value
        )

    if approval_id is not None:
        statement = statement.where(
            ExecutionIntentRecord.approval_id
            == approval_id
        )

    if action_id is not None:
        statement = statement.where(
            ExecutionIntentRecord.action_id
            == action_id
        )

    statement = (
        statement
        .order_by(
            ExecutionIntentRecord.created_at.desc(),
            ExecutionIntentRecord.execution_id.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(limit, 100)))
    )

    return list(session.scalars(statement).all())


def execution_snapshot(
    record: ExecutionIntentRecord,
) -> ExecutionContractSnapshot:
    return ExecutionContractSnapshot.model_validate_json(
        record.execution_snapshot_json
    )


def _event_record(
    *,
    record: ExecutionIntentRecord,
    sequence: int,
    event_type: ExecutionIntentEventType,
    from_status: ExecutionIntentStatus | None,
    to_status: ExecutionIntentStatus,
    actor: AuthPrincipal,
    claim_generation: int,
    reason: str | None,
    occurred_at: datetime,
) -> ExecutionIntentEventRecord:
    return ExecutionIntentEventRecord(
        event_id=(
            "execution-event:"
            f"{uuid4().hex}"
        ),
        sequence=sequence,
        execution_id=record.execution_id,
        incident_id=record.incident_id,
        approval_id=record.approval_id,
        action_id=record.action_id,
        event_type=event_type.value,
        from_status=(
            from_status.value
            if from_status is not None
            else None
        ),
        to_status=to_status.value,
        actor_subject=actor.subject,
        actor_display_name=actor.display_name,
        actor_roles_json=json.dumps(
            list(actor.roles),
            sort_keys=True,
        ),
        authentication_type=(
            actor.authentication_type
        ),
        claim_generation=claim_generation,
        reason=reason,
        occurred_at=occurred_at.isoformat(),
    )


def create_execution_intent_record(
    session: Session,
    *,
    snapshot: ExecutionContractSnapshot,
    idempotency_key: str,
    creator: AuthPrincipal,
    created_at: datetime,
) -> tuple[ExecutionIntentRecord, bool]:
    existing = load_execution_intent_by_key(
        session,
        idempotency_key=idempotency_key,
    )

    if existing is not None:
        return existing, False

    timestamp = created_at.isoformat()
    record = ExecutionIntentRecord(
        execution_id=(
            "execution-intent:"
            f"{uuid4().hex}"
        ),
        incident_id=snapshot.incident_id,
        approval_id=snapshot.approval_id,
        action_id=snapshot.action_id,
        action_family=(
            snapshot.action_family.value
        ),
        status=ExecutionIntentStatus.PENDING.value,
        approval_evidence_fingerprint=(
            snapshot.approval_evidence_fingerprint
        ),
        policy_version=snapshot.policy_version,
        risk=snapshot.risk.value,
        target_entity_ids_json=json.dumps(
            snapshot.target.entity_ids,
            sort_keys=True,
        ),
        target_change_event_id=(
            snapshot.target.change_event_id
        ),
        execution_snapshot_json=(
            snapshot.model_dump_json()
        ),
        idempotency_key=idempotency_key,
        created_by_subject=creator.subject,
        created_by_display_name=(
            creator.display_name
        ),
        created_by_roles_json=json.dumps(
            list(creator.roles),
            sort_keys=True,
        ),
        created_by_authentication_type=(
            creator.authentication_type
        ),
        created_at=timestamp,
        claimed_by_subject=None,
        claimed_by_display_name=None,
        claimed_by_authentication_type=None,
        claimed_at=None,
        claim_expires_at=None,
        claim_token_hash=None,
        claim_generation=0,
        attempt_count=0,
        cancelled_by_subject=None,
        cancelled_by_display_name=None,
        cancelled_at=None,
        cancellation_reason=None,
        invalidated_at=None,
        invalidation_reason=None,
        expired_at=None,
        expiration_reason=None,
        started_at=None,
        completed_at=None,
        failed_at=None,
        last_error_code=None,
        last_error_message=None,
        result_reference=None,
        execution_performed=False,
        row_version=1,
        updated_at=timestamp,
    )
    session.add(record)
    session.add(
        _event_record(
            record=record,
            sequence=1,
            event_type=(
                ExecutionIntentEventType.CREATED
            ),
            from_status=None,
            to_status=ExecutionIntentStatus.PENDING,
            actor=creator,
            claim_generation=0,
            reason=(
                "Execution intent created from a "
                "currently valid evidence-bound approval."
            ),
            occurred_at=created_at,
        )
    )

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = load_execution_intent_by_key(
            session,
            idempotency_key=idempotency_key,
        )

        if existing is None:
            existing = (
                load_execution_intent_by_approval(
                    session,
                    approval_id=snapshot.approval_id,
                )
            )

        if existing is not None:
            return existing, False

        raise

    session.refresh(record)
    return record, True


def _atomic_transition(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    expected_status: ExecutionIntentStatus,
    new_status: ExecutionIntentStatus,
    event_type: ExecutionIntentEventType,
    actor: AuthPrincipal,
    reason: str | None,
    occurred_at: datetime,
    values: dict[str, Any] | None = None,
) -> ExecutionIntentRecord | None:
    new_version = record.row_version + 1
    transition_values: dict[str, Any] = {
        "status": new_status.value,
        "row_version": new_version,
        "updated_at": occurred_at.isoformat(),
    }

    if values:
        transition_values.update(values)

    statement = (
        update(ExecutionIntentRecord)
        .where(
            ExecutionIntentRecord.execution_id
            == record.execution_id,
            ExecutionIntentRecord.status
            == expected_status.value,
            ExecutionIntentRecord.row_version
            == record.row_version,
        )
        .values(**transition_values)
        .execution_options(
            synchronize_session=False
        )
    )
    result = session.execute(statement)

    if result.rowcount != 1:
        session.rollback()
        return None

    event_record = _event_record(
        record=record,
        sequence=new_version,
        event_type=event_type,
        from_status=expected_status,
        to_status=new_status,
        actor=actor,
        claim_generation=int(
            transition_values.get(
                "claim_generation",
                record.claim_generation,
            )
        ),
        reason=reason,
        occurred_at=occurred_at,
    )
    session.add(event_record)

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None

    refreshed = load_execution_intent_record(
        session,
        incident_id=record.incident_id,
        execution_id=record.execution_id,
    )
    return refreshed


def atomic_claim_execution_intent_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    worker: AuthPrincipal,
    claim_token_hash: str,
    claimed_at: datetime,
    claim_expires_at: datetime,
) -> ExecutionIntentRecord | None:
    generation = record.claim_generation + 1

    return _atomic_transition(
        session,
        record=record,
        expected_status=ExecutionIntentStatus.PENDING,
        new_status=ExecutionIntentStatus.CLAIMED,
        event_type=ExecutionIntentEventType.CLAIMED,
        actor=worker,
        reason=(
            "Execution intent claimed for bounded "
            f"processing lease generation {generation}."
        ),
        occurred_at=claimed_at,
        values={
            "claimed_by_subject": worker.subject,
            "claimed_by_display_name": (
                worker.display_name
            ),
            "claimed_by_authentication_type": (
                worker.authentication_type
            ),
            "claimed_at": claimed_at.isoformat(),
            "claim_expires_at": (
                claim_expires_at.isoformat()
            ),
            "claim_token_hash": claim_token_hash,
            "claim_generation": generation,
            "attempt_count": (
                record.attempt_count + 1
            ),
        },
    )


def atomic_release_execution_claim_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    worker: AuthPrincipal,
    reason: str,
    released_at: datetime,
) -> ExecutionIntentRecord | None:
    return _atomic_transition(
        session,
        record=record,
        expected_status=ExecutionIntentStatus.CLAIMED,
        new_status=ExecutionIntentStatus.PENDING,
        event_type=ExecutionIntentEventType.RELEASED,
        actor=worker,
        reason=reason,
        occurred_at=released_at,
        values={
            "claimed_by_subject": None,
            "claimed_by_display_name": None,
            "claimed_by_authentication_type": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "claim_token_hash": None,
        },
    )


def atomic_expire_execution_claim_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    system_actor: AuthPrincipal,
    expired_at: datetime,
) -> ExecutionIntentRecord | None:
    return _atomic_transition(
        session,
        record=record,
        expected_status=ExecutionIntentStatus.CLAIMED,
        new_status=ExecutionIntentStatus.PENDING,
        event_type=(
            ExecutionIntentEventType.CLAIM_EXPIRED
        ),
        actor=system_actor,
        reason=(
            "The server-owned claim lease elapsed; "
            "the intent returned to pending."
        ),
        occurred_at=expired_at,
        values={
            "claimed_by_subject": None,
            "claimed_by_display_name": None,
            "claimed_by_authentication_type": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "claim_token_hash": None,
        },
    )


def atomic_cancel_execution_intent_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    actor: AuthPrincipal,
    reason: str,
    cancelled_at: datetime,
) -> ExecutionIntentRecord | None:
    return _atomic_transition(
        session,
        record=record,
        expected_status=ExecutionIntentStatus.PENDING,
        new_status=ExecutionIntentStatus.CANCELLED,
        event_type=ExecutionIntentEventType.CANCELLED,
        actor=actor,
        reason=reason,
        occurred_at=cancelled_at,
        values={
            "cancelled_by_subject": actor.subject,
            "cancelled_by_display_name": (
                actor.display_name
            ),
            "cancelled_at": cancelled_at.isoformat(),
            "cancellation_reason": reason,
        },
    )


def atomic_invalidate_execution_intent_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    expected_status: ExecutionIntentStatus,
    actor: AuthPrincipal,
    reason: str,
    invalidated_at: datetime,
) -> ExecutionIntentRecord | None:
    return _atomic_transition(
        session,
        record=record,
        expected_status=expected_status,
        new_status=ExecutionIntentStatus.INVALIDATED,
        event_type=ExecutionIntentEventType.INVALIDATED,
        actor=actor,
        reason=reason,
        occurred_at=invalidated_at,
        values={
            "claimed_by_subject": None,
            "claimed_by_display_name": None,
            "claimed_by_authentication_type": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "claim_token_hash": None,
            "invalidated_at": (
                invalidated_at.isoformat()
            ),
            "invalidation_reason": reason,
        },
    )


def atomic_expire_execution_intent_record(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    expected_status: ExecutionIntentStatus,
    actor: AuthPrincipal,
    reason: str,
    expired_at: datetime,
) -> ExecutionIntentRecord | None:
    return _atomic_transition(
        session,
        record=record,
        expected_status=expected_status,
        new_status=ExecutionIntentStatus.EXPIRED,
        event_type=ExecutionIntentEventType.EXPIRED,
        actor=actor,
        reason=reason,
        occurred_at=expired_at,
        values={
            "claimed_by_subject": None,
            "claimed_by_display_name": None,
            "claimed_by_authentication_type": None,
            "claimed_at": None,
            "claim_expires_at": None,
            "claim_token_hash": None,
            "expired_at": expired_at.isoformat(),
            "expiration_reason": reason,
        },
    )


def list_execution_intent_events(
    session: Session,
    *,
    execution_id: str,
) -> list[ExecutionIntentAuditEvent]:
    statement = (
        select(ExecutionIntentEventRecord)
        .where(
            ExecutionIntentEventRecord.execution_id
            == execution_id
        )
        .order_by(
            ExecutionIntentEventRecord.sequence.asc()
        )
    )
    records = list(session.scalars(statement).all())

    return [
        ExecutionIntentAuditEvent(
            event_id=record.event_id,
            sequence=record.sequence,
            execution_id=record.execution_id,
            incident_id=record.incident_id,
            approval_id=record.approval_id,
            action_id=record.action_id,
            event_type=ExecutionIntentEventType(
                record.event_type
            ),
            from_status=(
                ExecutionIntentStatus(
                    record.from_status
                )
                if record.from_status
                else None
            ),
            to_status=ExecutionIntentStatus(
                record.to_status
            ),
            actor_subject=record.actor_subject,
            actor_display_name=(
                record.actor_display_name
            ),
            actor_roles=json.loads(
                record.actor_roles_json
            ),
            authentication_type=(
                record.authentication_type
            ),
            claim_generation=(
                record.claim_generation
            ),
            reason=record.reason,
            occurred_at=datetime.fromisoformat(
                record.occurred_at
            ),
        )
        for record in records
    ]
