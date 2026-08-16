from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import ExecutionIntentRecord
from app.models.action_approval import (
    ActionApprovalDetail,
    ActionApprovalStatus,
)
from app.models.execution_readiness import (
    ExecutionReadinessStatus,
)
from app.models.execution_transaction import (
    ExecutionContractSnapshot,
    ExecutionIntentDetail,
    ExecutionIntentStatus,
    ExecutionIntentView,
    FutureExecutionTransactionContract,
)
from app.repositories.execution_intent_repository import (
    atomic_cancel_execution_intent_record,
    atomic_claim_execution_intent_record,
    atomic_expire_execution_claim_record,
    atomic_expire_execution_intent_record,
    atomic_invalidate_execution_intent_record,
    atomic_release_execution_claim_record,
    create_execution_intent_record,
    execution_snapshot,
    list_execution_intent_events,
    list_execution_intent_records,
    load_execution_intent_record,
)
from app.security.api_tokens import AuthPrincipal
from app.services.action_approval import (
    ActionApprovalNotFoundError,
    _sanitize_reason,
    get_action_approval,
)


EXECUTION_CLAIM_TTL_ENV = (
    "TOPO_EXECUTION_CLAIM_TTL_SECONDS"
)
DEFAULT_EXECUTION_CLAIM_TTL_SECONDS = 60
MIN_EXECUTION_CLAIM_TTL_SECONDS = 15
MAX_EXECUTION_CLAIM_TTL_SECONDS = 300

SYSTEM_PRINCIPAL = AuthPrincipal(
    subject="system:execution-transaction",
    display_name="Topo Execution Transaction",
    roles=(),
    authentication_type="system",
)


class ExecutionTransactionError(Exception):
    pass


class ExecutionIntentNotFoundError(
    ExecutionTransactionError
):
    pass


class ExecutionIntentConflictError(
    ExecutionTransactionError
):
    pass


class ExecutionWorkerAuthorizationError(
    ExecutionTransactionError
):
    pass


@dataclass(frozen=True)
class ExecutionWorkerIdentity:
    """
    Trusted internal identity for a future adapter.

    No HTTP request model or human CLI command can
    construct a claim through Block 14H.
    """

    subject: str
    display_name: str
    authentication_type: str


@dataclass(frozen=True)
class ExecutionClaimReceipt:
    execution_intent: ExecutionIntentDetail
    claim_generation: int
    claim_expires_at: datetime
    claim_token: str = field(repr=False)


def configured_execution_claim_ttl_seconds() -> int:
    raw_value = os.getenv(
        EXECUTION_CLAIM_TTL_ENV,
        str(DEFAULT_EXECUTION_CLAIM_TTL_SECONDS),
    ).strip()

    try:
        value = int(raw_value)
    except ValueError:
        value = (
            DEFAULT_EXECUTION_CLAIM_TTL_SECONDS
        )

    return max(
        MIN_EXECUTION_CLAIM_TTL_SECONDS,
        min(
            value,
            MAX_EXECUTION_CLAIM_TTL_SECONDS,
        ),
    )


def _utc_now(
    value: datetime | None = None,
) -> datetime:
    result = value or datetime.now(UTC)

    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)

    return result.astimezone(UTC)


def _worker_principal(
    worker: ExecutionWorkerIdentity,
) -> AuthPrincipal:
    subject = worker.subject.strip()
    display_name = worker.display_name.strip()
    authentication_type = (
        worker.authentication_type.strip()
    )

    if (
        not subject
        or subject.lower() == "unknown"
        or not display_name
        or not authentication_type
    ):
        raise ExecutionWorkerAuthorizationError(
            "A stable server-derived execution-worker "
            "identity is required."
        )

    if authentication_type in {
        "development",
        "api_token",
        "human_api_token",
    }:
        raise ExecutionWorkerAuthorizationError(
            "Human API-token identities cannot claim "
            "execution intents."
        )

    return AuthPrincipal(
        subject=subject,
        display_name=display_name,
        roles=(),
        authentication_type=authentication_type,
    )


def _snapshot_from_approval(
    approval: ActionApprovalDetail,
) -> ExecutionContractSnapshot:
    readiness = approval.readiness_snapshot

    return ExecutionContractSnapshot(
        approval_id=approval.approval_id,
        incident_id=approval.incident_id,
        action_id=approval.action_id,
        action_family=approval.action_family,
        action_category=(
            readiness.action_category
        ),
        action_semantics=(
            readiness.action_semantics
        ),
        policy_version=approval.policy_version,
        approval_evidence_fingerprint=(
            approval.evidence_fingerprint
        ),
        target=approval.target.model_copy(
            update={
                "entity_ids": sorted(
                    set(
                        approval.target.entity_ids
                    )
                )
            }
        ),
        risk=approval.risk,
        requires_human_approval=(
            approval.requires_human_approval
        ),
        created_from_readiness_status=(
            readiness.readiness_status
        ),
        causal_analysis_id=(
            readiness.causal_analysis_id
        ),
        response_plan_reference=(
            readiness.response_plan_reference
        ),
        root_event_id=readiness.root_event_id,
        target_event_id=readiness.target_event_id,
        readiness_evidence_ids=sorted(
            set(readiness.readiness_evidence_ids)
        ),
        preconditions=readiness.preconditions,
        requires_pre_execution_revalidation=True,
        execution_performed=False,
    )


def execution_intent_idempotency_key(
    snapshot: ExecutionContractSnapshot,
) -> str:
    payload = {
        "approval_id": snapshot.approval_id,
        "incident_id": snapshot.incident_id,
        "action_id": snapshot.action_id,
        "approval_evidence_fingerprint": (
            snapshot.approval_evidence_fingerprint
        ),
        "target": {
            "entity_ids": sorted(
                set(snapshot.target.entity_ids)
            ),
            "change_event_id": (
                snapshot.target.change_event_id
            ),
            "uniquely_identified": (
                snapshot.target.uniquely_identified
            ),
        },
        "policy_version": snapshot.policy_version,
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _approval_for_intent(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    now: datetime,
) -> ActionApprovalDetail | None:
    try:
        return get_action_approval(
            session,
            incident_id=record.incident_id,
            approval_id=record.approval_id,
            now=now,
        )
    except ActionApprovalNotFoundError:
        return None


def _approval_invalid_reason(
    *,
    record: ExecutionIntentRecord,
    approval: ActionApprovalDetail | None,
) -> str | None:
    if approval is None:
        return (
            "The source approval no longer exists."
        )

    if (
        approval.status
        != ActionApprovalStatus.APPROVED
        or not approval.currently_valid
    ):
        return (
            "The source approval is no longer "
            f"currently valid (status "
            f"'{approval.status.value}'): "
            f"{approval.invalid_reason or 'revalidation failed.'}"
        )

    stored = execution_snapshot(record)
    current = _snapshot_from_approval(approval)

    comparisons = (
        (
            stored.incident_id == current.incident_id,
            "incident binding",
        ),
        (
            stored.approval_id == current.approval_id,
            "approval binding",
        ),
        (
            stored.action_id == current.action_id,
            "action binding",
        ),
        (
            stored.action_family
            == current.action_family,
            "action family",
        ),
        (
            stored.policy_version
            == current.policy_version,
            "policy version",
        ),
        (
            stored.approval_evidence_fingerprint
            == current.approval_evidence_fingerprint,
            "approval evidence fingerprint",
        ),
        (
            stored.target == current.target,
            "execution target",
        ),
        (
            stored.risk == current.risk,
            "risk",
        ),
        (
            stored.requires_human_approval
            == current.requires_human_approval,
            "human-approval requirement",
        ),
        (
            current.created_from_readiness_status
            == ExecutionReadinessStatus
            .READY_FOR_HUMAN_APPROVAL,
            "execution readiness",
        ),
    )

    for matches, name in comparisons:
        if not matches:
            return (
                "The current approval no longer "
                f"matches the immutable {name}."
            )

    return None


def _terminal_reason(
    record: ExecutionIntentRecord,
) -> str | None:
    status = ExecutionIntentStatus(record.status)

    if status == ExecutionIntentStatus.CANCELLED:
        return (
            record.cancellation_reason
            or "The execution intent was cancelled."
        )

    if status == ExecutionIntentStatus.EXPIRED:
        return (
            record.expiration_reason
            or "The source approval expired."
        )

    if status == ExecutionIntentStatus.INVALIDATED:
        return (
            record.invalidation_reason
            or "The execution intent was invalidated."
        )

    if status == ExecutionIntentStatus.CLAIMED:
        return (
            "The execution intent currently has a "
            "live bounded claim."
        )

    return None


def _reload(
    session: Session,
    record: ExecutionIntentRecord,
) -> ExecutionIntentRecord:
    refreshed = load_execution_intent_record(
        session,
        incident_id=record.incident_id,
        execution_id=record.execution_id,
    )

    if refreshed is None:
        raise ExecutionIntentNotFoundError(
            "Execution intent not found."
        )

    return refreshed


def _refresh_active_intent(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    now: datetime,
) -> tuple[ExecutionIntentRecord, bool]:
    status = ExecutionIntentStatus(record.status)

    if status not in {
        ExecutionIntentStatus.PENDING,
        ExecutionIntentStatus.CLAIMED,
    }:
        approval = _approval_for_intent(
            session,
            record=record,
            now=now,
        )
        return (
            record,
            _approval_invalid_reason(
                record=record,
                approval=approval,
            )
            is None,
        )

    approval = _approval_for_intent(
        session,
        record=record,
        now=now,
    )
    invalid_reason = _approval_invalid_reason(
        record=record,
        approval=approval,
    )

    if invalid_reason is not None:
        if (
            approval is not None
            and approval.status
            == ActionApprovalStatus.EXPIRED
        ):
            transitioned = (
                atomic_expire_execution_intent_record(
                    session,
                    record=record,
                    expected_status=status,
                    actor=SYSTEM_PRINCIPAL,
                    reason=invalid_reason,
                    expired_at=now,
                )
            )
        else:
            transitioned = (
                atomic_invalidate_execution_intent_record(
                    session,
                    record=record,
                    expected_status=status,
                    actor=SYSTEM_PRINCIPAL,
                    reason=invalid_reason,
                    invalidated_at=now,
                )
            )

        return (
            transitioned or _reload(session, record),
            False,
        )

    if status == ExecutionIntentStatus.CLAIMED:
        claim_expires_at = (
            datetime.fromisoformat(
                record.claim_expires_at
            )
            if record.claim_expires_at
            else now
        )

        if now >= _utc_now(claim_expires_at):
            transitioned = (
                atomic_expire_execution_claim_record(
                    session,
                    record=record,
                    system_actor=SYSTEM_PRINCIPAL,
                    expired_at=now,
                )
            )
            return (
                transitioned or _reload(session, record),
                True,
            )

    return record, True


def _record_to_view(
    record: ExecutionIntentRecord,
    *,
    approval_valid: bool,
) -> ExecutionIntentView:
    snapshot = execution_snapshot(record)
    status = ExecutionIntentStatus(record.status)
    active = (
        approval_valid
        and status
        in {
            ExecutionIntentStatus.PENDING,
            ExecutionIntentStatus.CLAIMED,
        }
    )
    claimable = (
        approval_valid
        and status == ExecutionIntentStatus.PENDING
    )

    return ExecutionIntentView(
        execution_id=record.execution_id,
        incident_id=record.incident_id,
        approval_id=record.approval_id,
        action_id=record.action_id,
        action_family=snapshot.action_family,
        status=status,
        approval_evidence_fingerprint=(
            record.approval_evidence_fingerprint
        ),
        policy_version=record.policy_version,
        target=snapshot.target,
        risk=snapshot.risk,
        idempotency_key=record.idempotency_key,
        execution_snapshot=snapshot,
        created_by=record.created_by_subject,
        created_by_display_name=(
            record.created_by_display_name
        ),
        created_by_roles=json.loads(
            record.created_by_roles_json
        ),
        created_at=datetime.fromisoformat(
            record.created_at
        ),
        claimed_by=record.claimed_by_subject,
        claimed_by_display_name=(
            record.claimed_by_display_name
        ),
        claimed_at=(
            datetime.fromisoformat(record.claimed_at)
            if record.claimed_at
            else None
        ),
        claim_expires_at=(
            datetime.fromisoformat(
                record.claim_expires_at
            )
            if record.claim_expires_at
            else None
        ),
        claim_generation=record.claim_generation,
        attempt_count=record.attempt_count,
        cancelled_by=(
            record.cancelled_by_subject
        ),
        cancelled_by_display_name=(
            record.cancelled_by_display_name
        ),
        cancelled_at=(
            datetime.fromisoformat(
                record.cancelled_at
            )
            if record.cancelled_at
            else None
        ),
        cancellation_reason=(
            record.cancellation_reason
        ),
        invalidated_at=(
            datetime.fromisoformat(
                record.invalidated_at
            )
            if record.invalidated_at
            else None
        ),
        invalidation_reason=(
            record.invalidation_reason
        ),
        expired_at=(
            datetime.fromisoformat(record.expired_at)
            if record.expired_at
            else None
        ),
        expiration_reason=(
            record.expiration_reason
        ),
        started_at=(
            datetime.fromisoformat(record.started_at)
            if record.started_at
            else None
        ),
        completed_at=(
            datetime.fromisoformat(
                record.completed_at
            )
            if record.completed_at
            else None
        ),
        failed_at=(
            datetime.fromisoformat(record.failed_at)
            if record.failed_at
            else None
        ),
        last_error_code=record.last_error_code,
        last_error_message=(
            record.last_error_message
        ),
        result_reference=record.result_reference,
        row_version=record.row_version,
        updated_at=datetime.fromisoformat(
            record.updated_at
        ),
        approval_currently_valid=approval_valid,
        currently_claimable=claimable,
        retryable=claimable,
        invalid_reason=(
            None if claimable else _terminal_reason(record)
        ),
        execution_performed=False,
        future_execution_contract=(
            FutureExecutionTransactionContract(
                intent_reference_valid=active,
                requires_approval_revalidation=True,
                requires_readiness_revalidation=True,
                requires_pre_execution_revalidation=True,
                execution_performed=False,
                interpretation=(
                    "This immutable intent may be claimed by a "
                    "future authorized internal adapter. That adapter "
                    "must revalidate approval and readiness immediately "
                    "before mutation. Topo AI has not executed it."
                    if active
                    else (
                        "This intent cannot be used for future mutation. "
                        "Topo AI has not executed it."
                    )
                ),
            )
        ),
    )


def _detail(
    session: Session,
    *,
    record: ExecutionIntentRecord,
    approval_valid: bool,
) -> ExecutionIntentDetail:
    view = _record_to_view(
        record,
        approval_valid=approval_valid,
    )
    return ExecutionIntentDetail(
        **view.model_dump(),
        audit_events=list_execution_intent_events(
            session,
            execution_id=record.execution_id,
        ),
    )


def create_execution_intent(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    creator: AuthPrincipal,
    now: datetime | None = None,
) -> ExecutionIntentDetail:
    current_time = _utc_now(now)

    try:
        approval = get_action_approval(
            session,
            incident_id=incident_id,
            approval_id=approval_id,
            now=current_time,
        )
    except ActionApprovalNotFoundError as exc:
        raise ExecutionIntentNotFoundError(
            "Source approval not found."
        ) from exc

    if (
        approval.status
        != ActionApprovalStatus.APPROVED
        or not approval.currently_valid
        or not approval.future_execution_contract
        .approval_reference_valid
    ):
        raise ExecutionIntentConflictError(
            "Execution intent creation requires a "
            "currently valid approved 14G request. "
            f"Current status is '{approval.status.value}'."
        )

    snapshot = _snapshot_from_approval(approval)

    if (
        snapshot.created_from_readiness_status
        != ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
        or not snapshot.requires_human_approval
    ):
        raise ExecutionIntentConflictError(
            "The approved action no longer satisfies "
            "the authoritative 14F creation gate."
        )

    idempotency_key = (
        execution_intent_idempotency_key(snapshot)
    )
    record, _ = create_execution_intent_record(
        session,
        snapshot=snapshot,
        idempotency_key=idempotency_key,
        creator=creator,
        created_at=current_time,
    )

    return _detail(
        session,
        record=record,
        approval_valid=approval.currently_valid,
    )


def get_execution_intent(
    session: Session,
    *,
    incident_id: str,
    execution_id: str,
    now: datetime | None = None,
) -> ExecutionIntentDetail:
    record = load_execution_intent_record(
        session,
        incident_id=incident_id,
        execution_id=execution_id,
    )

    if record is None:
        raise ExecutionIntentNotFoundError(
            "Execution intent not found."
        )

    record, approval_valid = (
        _refresh_active_intent(
            session,
            record=record,
            now=_utc_now(now),
        )
    )
    return _detail(
        session,
        record=record,
        approval_valid=approval_valid,
    )


def list_execution_intents(
    session: Session,
    *,
    incident_id: str,
    status: ExecutionIntentStatus | None = None,
    approval_id: str | None = None,
    action_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
) -> list[ExecutionIntentView]:
    records = list_execution_intent_records(
        session,
        incident_id=incident_id,
        status=status,
        approval_id=approval_id,
        action_id=action_id,
        limit=limit,
        offset=offset,
    )
    current_time = _utc_now(now)
    result: list[ExecutionIntentView] = []

    for record in records:
        record, approval_valid = (
            _refresh_active_intent(
                session,
                record=record,
                now=current_time,
            )
        )

        if (
            status is not None
            and record.status != status.value
        ):
            continue

        result.append(
            _record_to_view(
                record,
                approval_valid=approval_valid,
            )
        )

    return result


def cancel_execution_intent(
    session: Session,
    *,
    incident_id: str,
    execution_id: str,
    actor: AuthPrincipal,
    reason: str,
    now: datetime | None = None,
) -> ExecutionIntentDetail:
    current_time = _utc_now(now)
    record = load_execution_intent_record(
        session,
        incident_id=incident_id,
        execution_id=execution_id,
    )

    if record is None:
        raise ExecutionIntentNotFoundError(
            "Execution intent not found."
        )

    record, approval_valid = (
        _refresh_active_intent(
            session,
            record=record,
            now=current_time,
        )
    )

    if (
        ExecutionIntentStatus(record.status)
        != ExecutionIntentStatus.PENDING
    ):
        raise ExecutionIntentConflictError(
            "Only a pending execution intent can be "
            "cancelled. Current status is "
            f"'{record.status}'."
        )

    sanitized = _sanitize_reason(reason)

    if not sanitized:
        raise ExecutionIntentConflictError(
            "A non-empty cancellation reason is required."
        )

    transitioned = atomic_cancel_execution_intent_record(
        session,
        record=record,
        actor=actor,
        reason=sanitized,
        cancelled_at=current_time,
    )

    if transitioned is None:
        raise ExecutionIntentConflictError(
            "The execution intent changed concurrently; "
            "cancellation did not occur."
        )

    return _detail(
        session,
        record=transitioned,
        approval_valid=approval_valid,
    )


def claim_execution_intent(
    session: Session,
    *,
    incident_id: str,
    execution_id: str,
    worker: ExecutionWorkerIdentity,
    now: datetime | None = None,
) -> ExecutionClaimReceipt:
    worker_principal = _worker_principal(worker)
    current_time = _utc_now(now)
    record = load_execution_intent_record(
        session,
        incident_id=incident_id,
        execution_id=execution_id,
    )

    if record is None:
        raise ExecutionIntentNotFoundError(
            "Execution intent not found."
        )

    record, approval_valid = (
        _refresh_active_intent(
            session,
            record=record,
            now=current_time,
        )
    )

    if (
        not approval_valid
        or ExecutionIntentStatus(record.status)
        != ExecutionIntentStatus.PENDING
    ):
        raise ExecutionIntentConflictError(
            "Execution intent is not currently "
            "claimable. Current status is "
            f"'{record.status}'."
        )

    claim_token = secrets.token_urlsafe(32)
    claim_token_hash = hashlib.sha256(
        claim_token.encode("utf-8")
    ).hexdigest()
    claim_expires_at = (
        current_time
        + timedelta(
            seconds=(
                configured_execution_claim_ttl_seconds()
            )
        )
    )
    transitioned = (
        atomic_claim_execution_intent_record(
            session,
            record=record,
            worker=worker_principal,
            claim_token_hash=claim_token_hash,
            claimed_at=current_time,
            claim_expires_at=claim_expires_at,
        )
    )

    if transitioned is None:
        raise ExecutionIntentConflictError(
            "Execution intent was claimed or changed "
            "concurrently; this worker did not acquire it."
        )

    detail = _detail(
        session,
        record=transitioned,
        approval_valid=True,
    )
    return ExecutionClaimReceipt(
        execution_intent=detail,
        claim_generation=(
            transitioned.claim_generation
        ),
        claim_expires_at=claim_expires_at,
        claim_token=claim_token,
    )


def release_execution_claim(
    session: Session,
    *,
    incident_id: str,
    execution_id: str,
    worker: ExecutionWorkerIdentity,
    claim_generation: int,
    claim_token: str,
    reason: str = "Internal worker released the claim.",
    now: datetime | None = None,
) -> ExecutionIntentDetail:
    worker_principal = _worker_principal(worker)
    current_time = _utc_now(now)
    record = load_execution_intent_record(
        session,
        incident_id=incident_id,
        execution_id=execution_id,
    )

    if record is None:
        raise ExecutionIntentNotFoundError(
            "Execution intent not found."
        )

    record, approval_valid = (
        _refresh_active_intent(
            session,
            record=record,
            now=current_time,
        )
    )

    supplied_hash = hashlib.sha256(
        claim_token.encode("utf-8")
    ).hexdigest()
    token_matches = bool(
        record.claim_token_hash
        and hmac.compare_digest(
            supplied_hash,
            record.claim_token_hash,
        )
    )

    if (
        not approval_valid
        or ExecutionIntentStatus(record.status)
        != ExecutionIntentStatus.CLAIMED
        or record.claim_generation
        != claim_generation
        or record.claimed_by_subject
        != worker_principal.subject
        or not token_matches
    ):
        raise ExecutionIntentConflictError(
            "The claim capability is stale, invalid, or "
            "does not belong to the current worker."
        )

    sanitized = _sanitize_reason(reason)

    if not sanitized:
        raise ExecutionIntentConflictError(
            "A non-empty release reason is required."
        )

    transitioned = (
        atomic_release_execution_claim_record(
            session,
            record=record,
            worker=worker_principal,
            reason=sanitized,
            released_at=current_time,
        )
    )

    if transitioned is None:
        raise ExecutionIntentConflictError(
            "The claim changed concurrently and was not released."
        )

    return _detail(
        session,
        record=transitioned,
        approval_valid=True,
    )
