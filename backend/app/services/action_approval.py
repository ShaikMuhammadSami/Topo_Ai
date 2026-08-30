from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    require_record_owner,
)

import hashlib
import json
import os
import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)

from sqlalchemy.orm import Session

from app.db.models import (
    ActionApprovalRecord,
)
from app.models.action_approval import (
    ActionApprovalDetail,
    ActionApprovalEventType,
    ActionApprovalReadinessSnapshot,
    ActionApprovalStatus,
    ActionApprovalView,
    ApprovalPreconditionSnapshot,
    FutureApprovalContract,
)
from app.models.execution_readiness import (
    ActionExecutionReadiness,
    ExecutionReadinessStatus,
    IncidentExecutionReadiness,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.repositories.action_approval_repository import (
    approval_snapshot,
    create_action_approval_record,
    list_action_approval_events,
    list_action_approval_records,
    list_active_action_approval_records,
    load_action_approval_record,
    transition_action_approval_record,
)
from app.security.api_tokens import (
    AuthPrincipal,
)
from app.services.execution_readiness import (
    build_incident_execution_readiness,
)

APPROVAL_TTL_ENV = (
    "TOPO_APPROVAL_TTL_MINUTES"
)
DEFAULT_APPROVAL_TTL_MINUTES = 30
MIN_APPROVAL_TTL_MINUTES = 5
MAX_APPROVAL_TTL_MINUTES = 120

# Approval always uses one server-owned 14F query
# profile. Clients cannot choose a different history
# window when creating or deciding an approval.
APPROVAL_READINESS_HISTORY_LIMIT = 5
APPROVAL_READINESS_MIN_SIMILARITY = 0.5

HIGH_RISK_SELF_APPROVAL_ALLOWED = False

SYSTEM_PRINCIPAL = AuthPrincipal(
    subject="system:approval-control-plane",
    display_name=(
        "Topo Approval Control Plane"
    ),
    roles=(),
    authentication_type="system",
)

AUDIT_SECRET_PATTERN = re.compile(
    r"(?i)(?:"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"
    r"|\b(?:api[_-]?key|token|password|secret)"
    r"\s*[:=]\s*[^\s,;]+"
    r"|\bgithub_pat_[A-Za-z0-9_]+"
    r"|\bgh[pousr]_[A-Za-z0-9_]+"
    r"|\bsk-[A-Za-z0-9_-]{12,}"
    r")"
)


class ActionApprovalError(Exception):
    pass


class ActionApprovalNotFoundError(
    ActionApprovalError
):
    pass


class ActionApprovalConflictError(
    ActionApprovalError
):
    pass


class ActionApprovalAuthorizationError(
    ActionApprovalError
):
    pass


def configured_approval_ttl_minutes() -> int:
    raw_value = os.getenv(
        APPROVAL_TTL_ENV,
        str(DEFAULT_APPROVAL_TTL_MINUTES),
    ).strip()

    try:
        value = int(raw_value)
    except ValueError:
        value = DEFAULT_APPROVAL_TTL_MINUTES

    return max(
        MIN_APPROVAL_TTL_MINUTES,
        min(value, MAX_APPROVAL_TTL_MINUTES),
    )


def _utc_now(
    value: datetime | None = None,
) -> datetime:
    result = value or datetime.now(UTC)

    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)

    return result.astimezone(UTC)


def _sanitize_reason(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = value.strip()

    if not normalized:
        return None

    return AUDIT_SECRET_PATTERN.sub(
        "[REDACTED]",
        normalized,
    )


def _current_readiness(
    session: Session,
    *,
    incident_id: str,
    tenant_id: DomainTenant,
) -> IncidentExecutionReadiness:
    return build_incident_execution_readiness(
        session=session,
        incident_id=incident_id,
        history_limit=(APPROVAL_READINESS_HISTORY_LIMIT),
        min_similarity=(APPROVAL_READINESS_MIN_SIMILARITY),
        include_ai=False,
        tenant_id=tenant_id,
    )


def _action(
    readiness: IncidentExecutionReadiness,
    *,
    action_id: str,
) -> ActionExecutionReadiness | None:
    return next(
        (
            action
            for action in readiness.actions
            if action.action_id == action_id
        ),
        None,
    )


def readiness_snapshot_for_action(
    *,
    readiness: IncidentExecutionReadiness,
    action: ActionExecutionReadiness,
) -> ActionApprovalReadinessSnapshot:
    root = (
        readiness.response_intelligence
        .baseline_response_plan.root_cause
    )
    target = action.target.model_copy(
        update={
            "entity_ids": sorted(
                set(action.target.entity_ids)
            )
        }
    )
    preconditions = sorted(
        [
            ApprovalPreconditionSnapshot(
                code=item.code,
                required=item.required,
                satisfied=item.satisfied,
                evidence_ids=sorted(
                    set(item.evidence_ids)
                ),
            )
            for item in action.preconditions
        ],
        key=lambda item: item.code,
    )

    return ActionApprovalReadinessSnapshot(
        incident_id=readiness.incident_id,
        causal_analysis_id=(
            readiness.causal_analysis_id
        ),
        response_plan_reference=(
            readiness.response_plan_reference
        ),
        policy_version=readiness.policy_version,
        action_id=action.action_id,
        action_title=action.title,
        action_family=action.action_family,
        action_category=action.category,
        action_semantics=(
            action.action_semantics
        ),
        risk=action.risk,
        requires_human_approval=(
            action.requires_human_approval
        ),
        readiness_status=(
            action.readiness_status
        ),
        target=target,
        root_event_id=root.event_id,
        target_event_id=root.target_event_id,
        causal_confidence=(
            root.causal_confidence
        ),
        current_evidence_strength=(
            action.current_evidence_strength
        ),
        historical_support=(
            action.historical_support.level
        ),
        readiness_evidence_ids=sorted(
            set(action.readiness_evidence_ids)
        ),
        preconditions=preconditions,
        owner_team=(
            action.approval_context.owner_team
        ),
        oncall_contact=(
            action.approval_context
            .oncall_contact
        ),
        service_name=(
            action.approval_context.service_name
        ),
        eligible_for_future_execution=(
            action.execution_contract
            .eligible_for_future_execution
        ),
    )


def _fingerprint_payload(
    snapshot: ActionApprovalReadinessSnapshot,
) -> dict[str, object]:
    return {
        "incident_id": snapshot.incident_id,
        "causal_analysis_id": (
            snapshot.causal_analysis_id
        ),
        "response_plan_reference": (
            snapshot.response_plan_reference
        ),
        "policy_version": snapshot.policy_version,
        "action_id": snapshot.action_id,
        "action_family": (
            snapshot.action_family.value
        ),
        "action_category": (
            snapshot.action_category.value
        ),
        "action_semantics": (
            snapshot.action_semantics.value
        ),
        "risk": snapshot.risk.value,
        "requires_human_approval": (
            snapshot.requires_human_approval
        ),
        "readiness_status": (
            snapshot.readiness_status.value
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
        "root_event_id": snapshot.root_event_id,
        "target_event_id": (
            snapshot.target_event_id
        ),
        "causal_confidence": (
            snapshot.causal_confidence
        ),
        "current_evidence_strength": (
            snapshot
            .current_evidence_strength.value
        ),
        "historical_support": (
            snapshot.historical_support.value
        ),
        "readiness_evidence_ids": sorted(
            set(snapshot.readiness_evidence_ids)
        ),
        "preconditions": [
            {
                "code": item.code,
                "required": item.required,
                "satisfied": item.satisfied,
                "evidence_ids": sorted(
                    set(item.evidence_ids)
                ),
            }
            for item in sorted(
                snapshot.preconditions,
                key=lambda value: value.code,
            )
        ],
        "owner_team": snapshot.owner_team,
        "service_name": snapshot.service_name,
        "eligible_for_future_execution": (
            snapshot
            .eligible_for_future_execution
        ),
    }


def approval_evidence_fingerprint(
    snapshot: ActionApprovalReadinessSnapshot,
) -> str:
    canonical = json.dumps(
        _fingerprint_payload(snapshot),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _pending_key(
    *,
    incident_id: str,
    action_id: str,
    evidence_fingerprint: str,
) -> str:
    canonical = "\x00".join(
        [
            incident_id,
            action_id,
            evidence_fingerprint,
        ]
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def _stale_reason(
    *,
    stored: ActionApprovalReadinessSnapshot,
    current: (
        ActionApprovalReadinessSnapshot | None
    ),
) -> str:
    if current is None:
        return (
            "The action no longer exists in current "
            "execution readiness."
        )

    if (
        current.readiness_status
        != ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    ):
        return (
            "Current execution readiness changed to "
            f"'{current.readiness_status.value}'."
        )

    if not current.requires_human_approval:
        return (
            "The current action no longer preserves "
            "the human-approval requirement."
        )

    if current.policy_version != stored.policy_version:
        return (
            "The execution-readiness policy version "
            "changed from "
            f"'{stored.policy_version}' to "
            f"'{current.policy_version}'."
        )

    if current.target != stored.target:
        return (
            "The action target changed after the "
            "approval request was created."
        )

    if (
        current.readiness_evidence_ids
        != stored.readiness_evidence_ids
        or current.preconditions
        != stored.preconditions
    ):
        return (
            "The validation or readiness evidence "
            "changed after the approval request was "
            "created."
        )

    return (
        "Execution-relevant readiness evidence changed "
        "after the approval request was created."
    )


def _terminal_invalid_reason(
    record: ActionApprovalRecord,
) -> str | None:
    status = ActionApprovalStatus(
        record.status
    )

    if status == ActionApprovalStatus.PENDING:
        return (
            "The request is awaiting an authorized "
            "human decision."
        )

    if status == ActionApprovalStatus.REJECTED:
        return "The request was rejected."

    if status == ActionApprovalStatus.EXPIRED:
        return "The approval window expired."

    if status == ActionApprovalStatus.REVOKED:
        return (
            record.revocation_reason
            or "The approval was revoked."
        )

    if status == ActionApprovalStatus.INVALIDATED:
        return (
            record.invalidation_reason
            or "The approval was invalidated."
        )

    return None


def _transition_system(
    session: Session,
    *,
    record: ActionApprovalRecord,
    status: ActionApprovalStatus,
    reason: str,
    now: datetime,
    tenant_id: DomainTenant,
) -> ActionApprovalRecord:
    require_record_owner(record, tenant_id=tenant_id)
    event_type = {
        ActionApprovalStatus.EXPIRED: (
            ActionApprovalEventType.EXPIRED
        ),
        ActionApprovalStatus.INVALIDATED: (
            ActionApprovalEventType.INVALIDATED
        ),
    }[status]

    return transition_action_approval_record(
        session,
        record=record,
        new_status=status,
        event_type=event_type,
        actor=SYSTEM_PRINCIPAL,
        reason=reason,
        occurred_at=now,
        tenant_id=tenant_id,
    )


def _refresh_active_record(
    session: Session,
    *,
    record: ActionApprovalRecord,
    readiness: IncidentExecutionReadiness | None,
    readiness_error: str | None,
    now: datetime,
    tenant_id: DomainTenant,
) -> tuple[ActionApprovalRecord, bool]:
    require_record_owner(record, tenant_id=tenant_id)
    status = ActionApprovalStatus(
        record.status
    )

    if status not in {
        ActionApprovalStatus.PENDING,
        ActionApprovalStatus.APPROVED,
    }:
        return record, False

    expires_at = datetime.fromisoformat(
        record.expires_at
    )

    if now >= _utc_now(expires_at):
        return (
            _transition_system(
                session,
                record=record,
                status=(ActionApprovalStatus.EXPIRED),
                reason=("The server-owned approval TTL " "elapsed."),
                now=now,
                tenant_id=tenant_id,
            ),
            False,
        )

    stored = approval_snapshot(record)

    if readiness is None:
        reason = (
            "Current execution readiness could not be "
            "re-established"
            + (
                f": {readiness_error}"
                if readiness_error
                else "."
            )
        )
        return (
            _transition_system(
                session,
                record=record,
                status=(ActionApprovalStatus.INVALIDATED),
                reason=reason,
                now=now,
                tenant_id=tenant_id,
            ),
            False,
        )

    current_action = _action(
        readiness,
        action_id=record.action_id,
    )
    current_snapshot = (
        readiness_snapshot_for_action(
            readiness=readiness,
            action=current_action,
        )
        if current_action is not None
        else None
    )
    current_fingerprint = (
        approval_evidence_fingerprint(
            current_snapshot
        )
        if current_snapshot is not None
        else None
    )
    current_is_eligible = bool(
        current_snapshot is not None
        and current_snapshot.readiness_status
        == ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
        and current_snapshot
        .requires_human_approval
        and current_snapshot
        .eligible_for_future_execution
    )

    if not current_is_eligible or current_fingerprint != record.evidence_fingerprint:
        return (
            _transition_system(
                session,
                record=record,
                status=(ActionApprovalStatus.INVALIDATED),
                reason=_stale_reason(
                    stored=stored,
                    current=current_snapshot,
                ),
                now=now,
                tenant_id=tenant_id,
            ),
            False,
        )

    return (
        record,
        status == ActionApprovalStatus.APPROVED,
    )


def _readiness_or_error(
    session: Session,
    *,
    incident_id: str,
    tenant_id: DomainTenant,
) -> tuple[
    IncidentExecutionReadiness | None,
    str | None,
]:
    try:
        return (
            _current_readiness(
                session,
                incident_id=incident_id,
                tenant_id=tenant_id,
            ),
            None,
        )
    except ValueError as exc:
        return None, str(exc)


def _record_to_view(
    record: ActionApprovalRecord,
    *,
    currently_valid: bool,
) -> ActionApprovalView:
    snapshot = approval_snapshot(record)
    status = ActionApprovalStatus(
        record.status
    )

    return ActionApprovalView(
        approval_id=record.approval_id,
        incident_id=record.incident_id,
        action_id=record.action_id,
        action_family=snapshot.action_family,
        status=status,
        risk=RecommendationRisk(record.risk),
        requires_human_approval=(
            record.requires_human_approval
        ),
        policy_version=record.policy_version,
        readiness_status_at_request=(
            ExecutionReadinessStatus(
                record
                .readiness_status_at_request
            )
        ),
        evidence_fingerprint=(
            record.evidence_fingerprint
        ),
        target=snapshot.target,
        readiness_snapshot=snapshot,
        request_reason=record.request_reason,
        requested_by=(
            record.requested_by_subject
        ),
        requested_by_display_name=(
            record.requested_by_display_name
        ),
        requested_by_roles=json.loads(
            record.requested_by_roles_json
        ),
        requested_at=datetime.fromisoformat(
            record.requested_at
        ),
        decided_by=record.decided_by_subject,
        decided_by_display_name=(
            record.decided_by_display_name
        ),
        decided_by_roles=json.loads(
            record.decided_by_roles_json
        ),
        decided_at=(
            datetime.fromisoformat(
                record.decided_at
            )
            if record.decided_at
            else None
        ),
        decision_reason=(
            record.decision_reason
        ),
        expires_at=datetime.fromisoformat(
            record.expires_at
        ),
        revoked_by=record.revoked_by_subject,
        revoked_by_display_name=(
            record.revoked_by_display_name
        ),
        revoked_at=(
            datetime.fromisoformat(
                record.revoked_at
            )
            if record.revoked_at
            else None
        ),
        revocation_reason=(
            record.revocation_reason
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
        created_at=datetime.fromisoformat(
            record.created_at
        ),
        updated_at=datetime.fromisoformat(
            record.updated_at
        ),
        currently_valid=currently_valid,
        invalid_reason=(
            None
            if currently_valid
            else _terminal_invalid_reason(
                record
            )
        ),
        future_execution_contract=(
            FutureApprovalContract(
                approval_reference_valid=(
                    currently_valid
                ),
                requires_current_readiness_revalidation=(
                    True
                ),
                execution_performed=False,
                interpretation=(
                    "This evidence-bound approval may be presented to "
                    "a future execution adapter, which must revalidate "
                    "current readiness before any action. Topo AI has "
                    "not executed it."
                    if currently_valid
                    else (
                        "This approval reference cannot be used by a "
                        "future execution adapter. Topo AI has not "
                        "executed it."
                    )
                ),
            )
        ),
    )


def _detail(
    session: Session,
    *,
    record: ActionApprovalRecord,
    currently_valid: bool,
    tenant_id: DomainTenant,
) -> ActionApprovalDetail:
    require_record_owner(record, tenant_id=tenant_id)
    view = _record_to_view(
        record,
        currently_valid=currently_valid,
    )

    return ActionApprovalDetail(
        **view.model_dump(),
        audit_events=(
            list_action_approval_events(
                session,
                approval_id=(record.approval_id),
                tenant_id=tenant_id,
            )
        ),
    )


def create_action_approval(
    session: Session,
    *,
    incident_id: str,
    action_id: str,
    requester: AuthPrincipal,
    reason: str | None = None,
    now: datetime | None = None,
    tenant_id: DomainTenant,
) -> ActionApprovalDetail:
    current_time = _utc_now(now)
    readiness = _current_readiness(
        session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )
    action = _action(
        readiness,
        action_id=action_id,
    )

    if action is None:
        raise ActionApprovalConflictError(
            "The action does not exist in current "
            "execution readiness."
        )

    if (
        not action.mutation
        or action.readiness_status
        != ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
        or not action.requires_human_approval
        or not action.execution_contract
        .eligible_for_future_execution
    ):
        raise ActionApprovalConflictError(
            "An approval request can be created only "
            "for a mutating action that current 14F "
            "readiness marks ready_for_human_approval "
            "with human approval required. Current "
            "status is "
            f"'{action.readiness_status.value}'."
        )

    snapshot = readiness_snapshot_for_action(
        readiness=readiness,
        action=action,
    )
    fingerprint = (
        approval_evidence_fingerprint(
            snapshot
        )
    )

    # Refresh active records using the same current
    # readiness before applying idempotency.
    for active in list_active_action_approval_records(
        session,
        incident_id=incident_id,
        action_id=action_id,
        tenant_id=tenant_id,
    ):
        active, valid = _refresh_active_record(
            session,
            record=active,
            readiness=readiness,
            readiness_error=None,
            now=current_time,
            tenant_id=tenant_id,
        )

        if active.evidence_fingerprint == fingerprint and ActionApprovalStatus(
            active.status
        ) in {
            ActionApprovalStatus.PENDING,
            ActionApprovalStatus.APPROVED,
        }:
            return _detail(
                session,
                record=active,
                currently_valid=valid,
                tenant_id=tenant_id,
            )

    ttl = configured_approval_ttl_minutes()
    record, _ = create_action_approval_record(
        session,
        incident_id=incident_id,
        snapshot=snapshot,
        evidence_fingerprint=fingerprint,
        pending_key=_pending_key(
            incident_id=incident_id,
            action_id=action_id,
            evidence_fingerprint=fingerprint,
        ),
        requester=requester,
        request_reason=_sanitize_reason(reason),
        requested_at=current_time,
        expires_at=(current_time + timedelta(minutes=ttl)),
        tenant_id=tenant_id,
    )

    return _detail(
        session,
        record=record,
        currently_valid=False,
        tenant_id=tenant_id,
    )


def get_action_approval(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    now: datetime | None = None,
    tenant_id: DomainTenant,
) -> ActionApprovalDetail:
    record = load_action_approval_record(
        session,
        incident_id=incident_id,
        approval_id=approval_id,
        tenant_id=tenant_id,
    )

    if record is None:
        raise ActionApprovalNotFoundError(
            "Approval request not found."
        )

    current_time = _utc_now(now)
    readiness: IncidentExecutionReadiness | None = None
    readiness_error: str | None = None

    if ActionApprovalStatus(record.status) in {
        ActionApprovalStatus.PENDING,
        ActionApprovalStatus.APPROVED,
    }:
        readiness, readiness_error = _readiness_or_error(
            session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )

    record, valid = _refresh_active_record(
        session,
        record=record,
        readiness=readiness,
        readiness_error=readiness_error,
        now=current_time,
        tenant_id=tenant_id,
    )

    return _detail(
        session,
        record=record,
        currently_valid=valid,
        tenant_id=tenant_id,
    )


def list_action_approvals(
    session: Session,
    *,
    incident_id: str,
    status: ActionApprovalStatus | None = None,
    action_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    now: datetime | None = None,
    tenant_id: DomainTenant,
) -> list[ActionApprovalView]:
    records = list_action_approval_records(
        session,
        incident_id=incident_id,
        status=status,
        action_id=action_id,
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
    )
    current_time = _utc_now(now)
    has_active = any(
        ActionApprovalStatus(record.status)
        in {
            ActionApprovalStatus.PENDING,
            ActionApprovalStatus.APPROVED,
        }
        for record in records
    )
    readiness: IncidentExecutionReadiness | None = None
    readiness_error: str | None = None

    if has_active:
        readiness, readiness_error = _readiness_or_error(
            session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )

    result: list[ActionApprovalView] = []

    for record in records:
        record, valid = _refresh_active_record(
            session,
            record=record,
            readiness=readiness,
            readiness_error=readiness_error,
            now=current_time,
            tenant_id=tenant_id,
        )

        if (
            status is not None
            and record.status != status.value
        ):
            continue

        result.append(
            _record_to_view(
                record,
                currently_valid=valid,
            )
        )

    return result


def _pending_for_decision(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    now: datetime,
    tenant_id: DomainTenant,
) -> tuple[
    ActionApprovalRecord,
    IncidentExecutionReadiness,
]:
    record = load_action_approval_record(
        session,
        incident_id=incident_id,
        approval_id=approval_id,
        tenant_id=tenant_id,
    )

    if record is None:
        raise ActionApprovalNotFoundError(
            "Approval request not found."
        )

    if (
        ActionApprovalStatus(record.status)
        != ActionApprovalStatus.PENDING
    ):
        raise ActionApprovalConflictError(
            "Only a pending approval request can "
            "receive an approval or rejection "
            "decision. Current status is "
            f"'{record.status}'."
        )

    readiness, readiness_error = _readiness_or_error(
        session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )
    record, _ = _refresh_active_record(
        session,
        record=record,
        readiness=readiness,
        readiness_error=readiness_error,
        now=now,
        tenant_id=tenant_id,
    )

    if (
        ActionApprovalStatus(record.status)
        != ActionApprovalStatus.PENDING
    ):
        raise ActionApprovalConflictError(
            "The approval request became "
            f"'{record.status}' during current "
            "readiness revalidation. Create a new "
            "request if the action becomes eligible."
        )

    assert readiness is not None

    return record, readiness


def decide_action_approval(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    decision: ActionApprovalStatus,
    decider: AuthPrincipal,
    reason: str | None = None,
    now: datetime | None = None,
    tenant_id: DomainTenant,
) -> ActionApprovalDetail:
    if decision not in {
        ActionApprovalStatus.APPROVED,
        ActionApprovalStatus.REJECTED,
    }:
        raise ActionApprovalConflictError(
            "Decision must be approved or rejected."
        )

    current_time = _utc_now(now)
    record, _ = _pending_for_decision(
        session,
        incident_id=incident_id,
        approval_id=approval_id,
        now=current_time,
        tenant_id=tenant_id,
    )

    if (
        decision == ActionApprovalStatus.APPROVED
        and record.risk
        == RecommendationRisk.HIGH.value
        and not HIGH_RISK_SELF_APPROVAL_ALLOWED
        and decider.subject
        == record.requested_by_subject
    ):
        raise ActionApprovalAuthorizationError(
            "High-risk mutation approval requires "
            "an authorized human other than the "
            "requester."
        )

    event_type = (
        ActionApprovalEventType.APPROVED
        if decision
        == ActionApprovalStatus.APPROVED
        else ActionApprovalEventType.REJECTED
    )
    record = transition_action_approval_record(
        session,
        record=record,
        new_status=decision,
        event_type=event_type,
        actor=decider,
        reason=_sanitize_reason(reason),
        occurred_at=current_time,
        tenant_id=tenant_id,
    )

    return _detail(
        session,
        record=record,
        currently_valid=(decision == ActionApprovalStatus.APPROVED),
        tenant_id=tenant_id,
    )


def revoke_action_approval(
    session: Session,
    *,
    incident_id: str,
    approval_id: str,
    revoker: AuthPrincipal,
    reason: str,
    now: datetime | None = None,
    tenant_id: DomainTenant,
) -> ActionApprovalDetail:
    current_time = _utc_now(now)
    record = load_action_approval_record(
        session,
        incident_id=incident_id,
        approval_id=approval_id,
        tenant_id=tenant_id,
    )

    if record is None:
        raise ActionApprovalNotFoundError(
            "Approval request not found."
        )

    if (
        ActionApprovalStatus(record.status)
        != ActionApprovalStatus.APPROVED
    ):
        raise ActionApprovalConflictError(
            "Only an approved request can be "
            "revoked. Current status is "
            f"'{record.status}'."
        )

    readiness, readiness_error = _readiness_or_error(
        session,
        incident_id=incident_id,
        tenant_id=tenant_id,
    )
    record, valid = _refresh_active_record(
        session,
        record=record,
        readiness=readiness,
        readiness_error=readiness_error,
        now=current_time,
        tenant_id=tenant_id,
    )

    if not valid:
        raise ActionApprovalConflictError(
            "The approval is no longer currently "
            "valid and cannot be revoked as an "
            "active approval."
        )

    sanitized_reason = _sanitize_reason(reason)

    if not sanitized_reason:
        raise ActionApprovalConflictError(
            "A non-empty revocation reason is "
            "required."
        )

    record = transition_action_approval_record(
        session,
        record=record,
        new_status=ActionApprovalStatus.REVOKED,
        event_type=(ActionApprovalEventType.REVOKED),
        actor=revoker,
        reason=sanitized_reason,
        occurred_at=current_time,
        tenant_id=tenant_id,
    )

    return _detail(
        session,
        record=record,
        currently_valid=False,
        tenant_id=tenant_id,
    )
