from __future__ import annotations
from domain_tenant_fixtures import TEST_HEADERS, TEST_TENANT, seed_domain_tenant
from domain_tenant_fixtures import seed_domain_parents
from test_tenant_foundation import tenant_app

from datetime import (
    UTC,
    datetime,
    timedelta,
)
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import (
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import sessionmaker

import app.services.action_approval as service
from app.db.database import Base
from app.db.models import (
    ActionApprovalEventRecord,
    ActionApprovalRecord,
)
from app.models.action_approval import (
    ActionApprovalDecisionRequest,
    ActionApprovalRequest,
    ActionApprovalRevocationRequest,
    ActionApprovalStatus,
)
from app.models.execution_readiness import (
    ActionApprovalContext,
    ActionPrecondition,
    ExecutionReadinessStatus,
    ExecutionReadinessTarget,
    FutureExecutionContract,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_intelligence import (
    CurrentEvidenceStrength,
    HistoricalActionSupportLevel,
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import (
    ResponseActionCategory,
)
from app.repositories.action_approval_repository import (
    load_action_approval_record,
)
from app.security.api_tokens import (
    AuthPrincipal,
)
from app.security.approval_authorization import (
    approval_control_principal,
)

NOW = datetime(
    2026,
    8,
    16,
    12,
    0,
    tzinfo=UTC,
)


@pytest.fixture(autouse=True)
def preserved_dormant_approval_foundation(monkeypatch):
    """Exercise preserved 14G mechanics below the PH-5C V1 deny boundary."""
    monkeypatch.setattr(
        service,
        "authorize_service_operation",
        lambda *_args, **_kwargs: None,
    )


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    seed_domain_parents(engine, ("incidents", "incident:1"))
    Session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with Session() as value:
        yield value


def _principal(
    subject: str,
    *roles: str,
) -> AuthPrincipal:
    return AuthPrincipal(
        subject=subject,
        display_name=subject.replace(
            "-",
            " ",
        ).title(),
        roles=roles,
        authentication_type="api_token",
    )


REQUESTER = _principal(
    "requester-user",
    "operator",
)
APPROVER = _principal(
    "approver-user",
    "admin",
)
VIEWER = _principal(
    "viewer-user",
    "viewer",
)


def _readiness(
    *,
    status: ExecutionReadinessStatus = (
        ExecutionReadinessStatus
        .READY_FOR_HUMAN_APPROVAL
    ),
    action_id: str = "action:rollback",
    entity_id: str = "entity:payments",
    change_event_id: str = "event:deploy",
    policy_version: str = "14f-v1",
    evidence_ids: list[str] | None = None,
    risk: RecommendationRisk = (
        RecommendationRisk.HIGH
    ),
    mutation: bool = True,
    requires_approval: bool = True,
):
    evidence = (
        evidence_ids
        if evidence_ids is not None
        else [
            "evidence:causal",
            "action-observation:validation",
        ]
    )
    action = SimpleNamespace(
        action_id=action_id,
        title="Consider rollback deployment",
        action_family=(
            ResponseActionFamily.ROLLBACK
        ),
        category=(
            ResponseActionCategory
            .ROLLBACK_CANDIDATE
        ),
        action_semantics=(
            ResponseActionSemantics.MITIGATION
        ),
        risk=risk,
        requires_human_approval=(
            requires_approval
        ),
        mutation=mutation,
        readiness_status=status,
        target=ExecutionReadinessTarget(
            entity_ids=[entity_id],
            change_event_id=change_event_id,
            uniquely_identified=True,
        ),
        current_evidence_strength=(
            CurrentEvidenceStrength.HIGH
        ),
        historical_support=SimpleNamespace(
            level=(
                HistoricalActionSupportLevel
                .STRONGLY_SUPPORTED
            )
        ),
        readiness_evidence_ids=evidence,
        preconditions=[
            ActionPrecondition(
                code="validation:action:validate",
                title="Validate runtime revision",
                required=True,
                satisfied=(
                    status
                    == ExecutionReadinessStatus
                    .READY_FOR_HUMAN_APPROVAL
                ),
                reason="Durable responder evidence.",
                evidence_ids=evidence,
            )
        ],
        approval_context=(
            ActionApprovalContext(
                required=requires_approval,
                reason="Human approval required.",
                owner_team="payments",
                oncall_contact=(
                    "pagerduty:payments"
                ),
                service_name="payment-api",
            )
        ),
        execution_contract=(
            FutureExecutionContract(
                eligible_for_future_execution=(
                    status
                    == ExecutionReadinessStatus
                    .READY_FOR_HUMAN_APPROVAL
                ),
                interpretation=(
                    "May be presented for approval."
                ),
            )
        ),
    )
    root = SimpleNamespace(
        event_id="event:commit",
        target_event_id=change_event_id,
        causal_confidence=0.92,
    )

    return SimpleNamespace(
        incident_id="incident:1",
        causal_analysis_id="analysis:1",
        response_plan_reference=(
            "response-plan:analysis:1"
        ),
        policy_version=policy_version,
        actions=[action],
        response_intelligence=(
            SimpleNamespace(
                baseline_response_plan=(
                    SimpleNamespace(
                        root_cause=root
                    )
                )
            )
        ),
    )


def _wire(
    monkeypatch,
    holder: dict,
    calls: list | None = None,
) -> None:
    def build(**kwargs):
        if calls is not None:
            calls.append(kwargs)

        return holder["readiness"]

    monkeypatch.setattr(
        service,
        "build_incident_execution_readiness",
        build,
    )


def _create(
    session,
    monkeypatch,
    holder: dict | None = None,
    *,
    requester: AuthPrincipal = REQUESTER,
    reason: str | None = None,
):
    state = holder or {
        "readiness": _readiness()
    }
    _wire(monkeypatch, state)

    return service.create_action_approval(
        session,
        incident_id="incident:1",
        action_id="action:rollback",
        requester=requester,
        reason=reason,
        now=NOW,
        tenant_id=TEST_TENANT,
    )


def test_create_request_derives_safety_fields_from_14f(
    session,
    monkeypatch,
) -> None:
    result = _create(
        session,
        monkeypatch,
    )

    assert result.status == (
        ActionApprovalStatus.PENDING
    )
    assert result.action_family == (
        ResponseActionFamily.ROLLBACK
    )
    assert result.target.entity_ids == [
        "entity:payments"
    ]
    assert result.target.change_event_id == (
        "event:deploy"
    )
    assert result.policy_version == "14f-v1"
    assert result.risk == RecommendationRisk.HIGH
    assert len(result.evidence_fingerprint) == 64
    assert result.requested_by == (
        REQUESTER.subject
    )


@pytest.mark.parametrize(
    "status",
    [
        ExecutionReadinessStatus.NEEDS_VALIDATION,
        ExecutionReadinessStatus.BLOCKED,
        ExecutionReadinessStatus.NEEDS_MORE_EVIDENCE,
    ],
)
def test_non_ready_action_cannot_create_request(
    session,
    monkeypatch,
    status,
) -> None:
    holder = {
        "readiness": _readiness(
            status=status
        )
    }
    _wire(monkeypatch, holder)

    with pytest.raises(service.ActionApprovalConflictError):
        service.create_action_approval(
            session,
            incident_id="incident:1",
            action_id="action:rollback",
            requester=REQUESTER,
            now=NOW,
            tenant_id=TEST_TENANT,
        )


def test_read_only_action_does_not_create_approval_noise(
    session,
    monkeypatch,
) -> None:
    holder = {
        "readiness": _readiness(
            mutation=False,
            requires_approval=False,
            status=(
                ExecutionReadinessStatus
                .READ_ONLY_SAFE
            ),
        )
    }
    _wire(monkeypatch, holder)

    with pytest.raises(service.ActionApprovalConflictError):
        service.create_action_approval(
            session,
            incident_id="incident:1",
            action_id="action:rollback",
            requester=REQUESTER,
            now=NOW,
            tenant_id=TEST_TENANT,
        )


def test_request_schema_rejects_target_spoofing(
) -> None:
    with pytest.raises(ValidationError):
        ActionApprovalRequest.model_validate(
            {
                "action_id": "action:rollback",
                "target_entity_id": (
                    "entity:other-production"
                ),
            }
        )


def test_request_schema_rejects_approver_spoofing(
) -> None:
    with pytest.raises(ValidationError):
        ActionApprovalRequest.model_validate(
            {
                "action_id": "action:rollback",
                "approved_by": "alice",
            }
        )

    with pytest.raises(ValidationError):
        ActionApprovalDecisionRequest.model_validate(
            {
                "reason": "Approve.",
                "decided_by": "alice",
            }
        )


def test_viewer_role_cannot_change_approval_state(
) -> None:
    request = SimpleNamespace(
        state=SimpleNamespace(
            principal=VIEWER
        )
    )

    with pytest.raises(HTTPException) as exc:
        approval_control_principal(request)

    assert exc.value.status_code == 403


def test_unknown_subject_is_default_denied(
) -> None:
    request = SimpleNamespace(
        state=SimpleNamespace(
            principal=AuthPrincipal(
                subject="unknown",
                display_name="Unknown",
                roles=("admin",),
                authentication_type="api_token",
            )
        )
    )

    with pytest.raises(HTTPException) as exc:
        approval_control_principal(request)

    assert exc.value.status_code == 403


def test_authorized_distinct_principal_can_approve(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        reason="Validated with the service owner.",
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert approved.status == (
        ActionApprovalStatus.APPROVED
    )
    assert approved.decided_by == APPROVER.subject
    assert approved.currently_valid is True


def test_high_risk_self_approval_is_denied(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )

    with pytest.raises(service.ActionApprovalAuthorizationError):
        service.decide_action_approval(
            session,
            incident_id="incident:1",
            approval_id=pending.approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=REQUESTER,
            now=NOW + timedelta(minutes=1),
            tenant_id=TEST_TENANT,
        )


def test_evidence_change_before_approval_invalidates(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        evidence_ids=["evidence:new"]
    )

    with pytest.raises(service.ActionApprovalConflictError):
        service.decide_action_approval(
            session,
            incident_id="incident:1",
            approval_id=pending.approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=APPROVER,
            now=NOW + timedelta(minutes=1),
            tenant_id=TEST_TENANT,
        )

    record = load_action_approval_record(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        tenant_id=TEST_TENANT,
    )
    assert record is not None
    assert record.status == (
        ActionApprovalStatus.INVALIDATED.value
    )


def test_target_change_before_approval_invalidates(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        entity_id="entity:worker",
        change_event_id="event:deploy-new",
    )

    with pytest.raises(service.ActionApprovalConflictError):
        service.decide_action_approval(
            session,
            incident_id="incident:1",
            approval_id=pending.approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=APPROVER,
            now=NOW + timedelta(minutes=1),
            tenant_id=TEST_TENANT,
        )

    record = load_action_approval_record(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        tenant_id=TEST_TENANT,
    )
    assert record is not None
    assert "target changed" in (
        record.invalidation_reason or ""
    )


def test_policy_version_change_invalidates(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        policy_version="14f-v2"
    )
    result = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert result.status == (
        ActionApprovalStatus.INVALIDATED
    )
    assert "policy version" in (
        result.invalidation_reason or ""
    )


def test_validation_evidence_change_invalidates(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        evidence_ids=[
            "action-observation:new-validation"
        ]
    )
    result = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert result.status == (
        ActionApprovalStatus.INVALIDATED
    )
    assert "validation or readiness" in (
        result.invalidation_reason or ""
    )


def test_readiness_drop_before_approval_invalidates(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        status=(
            ExecutionReadinessStatus
            .NEEDS_VALIDATION
        )
    )

    with pytest.raises(service.ActionApprovalConflictError):
        service.decide_action_approval(
            session,
            incident_id="incident:1",
            approval_id=pending.approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=APPROVER,
            now=NOW + timedelta(minutes=1),
            tenant_id=TEST_TENANT,
        )


def test_expiration_uses_injected_time_without_sleep(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    result = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=31),
        tenant_id=TEST_TENANT,
    )

    assert result.status == (
        ActionApprovalStatus.EXPIRED
    )
    assert result.currently_valid is False


def test_approved_record_also_expires(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    expired = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=approved.approval_id,
        now=NOW + timedelta(minutes=31),
        tenant_id=TEST_TENANT,
    )

    assert expired.status == (
        ActionApprovalStatus.EXPIRED
    )
    assert expired.currently_valid is False


def test_approved_status_never_means_execution(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert (
        approved.future_execution_contract
        .approval_reference_valid
    )
    assert (
        approved.future_execution_contract
        .requires_current_readiness_revalidation
    )
    assert not (
        approved.future_execution_contract
        .execution_performed
    )


def test_rejection_is_durable_and_retrievable(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    rejected = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.REJECTED,
        decider=APPROVER,
        reason="Risk is not acceptable.",
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    loaded = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )

    assert rejected.status == (
        ActionApprovalStatus.REJECTED
    )
    assert loaded.status == (
        ActionApprovalStatus.REJECTED
    )
    assert loaded.decision_reason == (
        "Risk is not acceptable."
    )


def test_rejected_record_cannot_be_silently_approved(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.REJECTED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    with pytest.raises(service.ActionApprovalConflictError):
        service.decide_action_approval(
            session,
            incident_id="incident:1",
            approval_id=pending.approval_id,
            decision=(ActionApprovalStatus.APPROVED),
            decider=APPROVER,
            now=NOW + timedelta(minutes=2),
            tenant_id=TEST_TENANT,
        )


def test_new_request_after_rejection_preserves_old_history(
    session,
    monkeypatch,
) -> None:
    first = _create(
        session,
        monkeypatch,
    )
    service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=first.approval_id,
        decision=ActionApprovalStatus.REJECTED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    second = service.create_action_approval(
        session,
        incident_id="incident:1",
        action_id="action:rollback",
        requester=REQUESTER,
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )
    count = session.scalar(
        select(func.count())
        .select_from(ActionApprovalRecord)
    )

    assert second.status == (
        ActionApprovalStatus.PENDING
    )
    assert second.approval_id != first.approval_id
    assert count == 2


def test_approved_request_can_be_revoked(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    revoked = service.revoke_action_approval(
        session,
        incident_id="incident:1",
        approval_id=approved.approval_id,
        revoker=REQUESTER,
        reason="Incident conditions changed.",
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )

    assert revoked.status == (
        ActionApprovalStatus.REVOKED
    )
    assert revoked.currently_valid is False
    assert revoked.revoked_by == REQUESTER.subject


def test_duplicate_pending_request_is_idempotent(
    session,
    monkeypatch,
) -> None:
    first = _create(
        session,
        monkeypatch,
    )
    second = service.create_action_approval(
        session,
        incident_id="incident:1",
        action_id="action:rollback",
        requester=REQUESTER,
        now=NOW + timedelta(seconds=5),
        tenant_id=TEST_TENANT,
    )
    count = session.scalar(
        select(func.count())
        .select_from(ActionApprovalRecord)
    )

    assert first.approval_id == second.approval_id
    assert count == 1


def test_changed_evidence_creates_new_request_and_invalidates_old(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    first = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"] = _readiness(
        evidence_ids=["evidence:new-state"]
    )
    second = service.create_action_approval(
        session,
        incident_id="incident:1",
        action_id="action:rollback",
        requester=REQUESTER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    first_record = load_action_approval_record(
        session,
        incident_id="incident:1",
        approval_id=first.approval_id,
        tenant_id=TEST_TENANT,
    )

    assert second.approval_id != first.approval_id
    assert first_record is not None
    assert first_record.status == (
        ActionApprovalStatus.INVALIDATED.value
    )


def test_get_recalculates_current_validity(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    assert approved.currently_valid is True

    holder["readiness"] = _readiness(
        change_event_id="event:replacement"
    )
    refreshed = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )

    assert refreshed.status == (
        ActionApprovalStatus.INVALIDATED
    )
    assert refreshed.currently_valid is False


def test_display_wording_change_does_not_invalidate(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    holder["readiness"].actions[0].title = (
        "Updated display wording only"
    )
    refreshed = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=approved.approval_id,
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )

    assert refreshed.status == (
        ActionApprovalStatus.APPROVED
    )
    assert refreshed.currently_valid is True


def test_fingerprint_is_canonical_for_evidence_order(
) -> None:
    first_readiness = _readiness(
        evidence_ids=["evidence:b", "evidence:a"]
    )
    second_readiness = _readiness(
        evidence_ids=["evidence:a", "evidence:b"]
    )
    first_snapshot = (
        service.readiness_snapshot_for_action(
            readiness=first_readiness,
            action=first_readiness.actions[0],
        )
    )
    second_snapshot = (
        service.readiness_snapshot_for_action(
            readiness=second_readiness,
            action=second_readiness.actions[0],
        )
    )

    assert service.approval_evidence_fingerprint(
        first_snapshot
    ) == service.approval_evidence_fingerprint(
        second_snapshot
    )


def test_action_disappearance_invalidates_approval(
    session,
    monkeypatch,
) -> None:
    holder = {"readiness": _readiness()}
    pending = _create(
        session,
        monkeypatch,
        holder,
    )
    holder["readiness"].actions = []
    refreshed = service.get_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert refreshed.status == (
        ActionApprovalStatus.INVALIDATED
    )


def test_14f_is_called_without_ai_and_openai_is_not_required(
    session,
    monkeypatch,
) -> None:
    calls = []
    holder = {"readiness": _readiness()}
    _wire(monkeypatch, holder, calls)
    service.create_action_approval(
        session,
        incident_id="incident:1",
        action_id="action:rollback",
        requester=REQUESTER,
        now=NOW,
        tenant_id=TEST_TENANT,
    )

    assert len(calls) == 1
    assert calls[0]["include_ai"] is False
    assert "openai" not in service.__dict__


def test_requester_and_decider_are_in_immutable_audit_events(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    result = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )

    assert [
        event.actor_subject
        for event in result.audit_events
    ] == [
        REQUESTER.subject,
        APPROVER.subject,
    ]
    assert [
        event.event_type.value
        for event in result.audit_events
    ] == ["requested", "approved"]


def test_reason_length_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ActionApprovalRequest(
            action_id="action:rollback",
            reason="x" * 4001,
        )

    with pytest.raises(ValidationError):
        ActionApprovalRevocationRequest(
            reason=" "
        )


def test_secret_shaped_reason_is_redacted(
    session,
    monkeypatch,
) -> None:
    result = _create(
        session,
        monkeypatch,
        reason=(
            "Investigated with token=supersecretvalue"
        ),
    )

    assert result.request_reason == (
        "Investigated with [REDACTED]"
    )
    assert "supersecretvalue" not in (
        result.audit_events[0].reason or ""
    )


def test_listing_is_bounded_and_filterable(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    results = service.list_action_approvals(
        session,
        incident_id="incident:1",
        status=ActionApprovalStatus.PENDING,
        action_id="action:rollback",
        limit=1000,
        offset=0,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert [
        item.approval_id
        for item in results
    ] == [pending.approval_id]


def test_ttl_configuration_has_safe_default_and_bounds(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        service.APPROVAL_TTL_ENV,
        raising=False,
    )
    assert (
        service.configured_approval_ttl_minutes()
        == 30
    )

    monkeypatch.setenv(
        service.APPROVAL_TTL_ENV,
        "9999",
    )
    assert (
        service.configured_approval_ttl_minutes()
        == 120
    )

    monkeypatch.setenv(
        service.APPROVAL_TTL_ENV,
        "1",
    )
    assert (
        service.configured_approval_ttl_minutes()
        == 5
    )


def test_no_recovery_or_execution_service_is_called(
    session,
    monkeypatch,
) -> None:
    import app.repositories.recovery_repository as recovery

    monkeypatch.setattr(
        recovery,
        "save_recovery_verification",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("recovery must not run")
        ),
    )
    result = _create(
        session,
        monkeypatch,
    )

    assert result.status == (
        ActionApprovalStatus.PENDING
    )


def test_audit_events_are_append_only_across_transitions(
    session,
    monkeypatch,
) -> None:
    pending = _create(
        session,
        monkeypatch,
    )
    approved = service.decide_action_approval(
        session,
        incident_id="incident:1",
        approval_id=pending.approval_id,
        decision=ActionApprovalStatus.APPROVED,
        decider=APPROVER,
        now=NOW + timedelta(minutes=1),
        tenant_id=TEST_TENANT,
    )
    revoked = service.revoke_action_approval(
        session,
        incident_id="incident:1",
        approval_id=approved.approval_id,
        revoker=REQUESTER,
        reason="Stop the approval.",
        now=NOW + timedelta(minutes=2),
        tenant_id=TEST_TENANT,
    )
    count = session.scalar(
        select(func.count())
        .select_from(
            ActionApprovalEventRecord
        )
    )

    assert count == 3
    assert [
        event.event_type.value
        for event in revoked.audit_events
    ] == [
        "requested",
        "approved",
        "revoked",
    ]


def test_new_approval_routes_are_authenticated(
    required_auth_app,
) -> None:
    client = TestClient(required_auth_app, headers=TEST_HEADERS)
    response = client.post(
        "/api/v1/incidents/incident%3A1/approvals",
        json={"action_id": "action:rollback"},
    )

    assert response.status_code == 401


def test_approval_list_limit_is_enforced_by_api(
    tenant_app,
) -> None:
    from test_tenant_foundation import _bearer, _create_tenant

    application, _, tokens = tenant_app
    client = TestClient(application)
    tenant = _create_tenant(client, tokens["bootstrap"])
    response = client.get(
        "/api/v1/incidents/incident%3A1/approvals?limit=101",
        headers=_bearer(tokens["bootstrap"], tenant["tenant_id"]),
    )

    # PH-5C denies the dormant V1 execution surface before request validation.
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "V1_EXECUTION_DISABLED"


def test_database_tables_preserve_current_and_event_history(
    session,
) -> None:
    table_names = set(
        Base.metadata.tables
    )

    assert "action_approvals" in table_names
    assert "action_approval_events" in table_names
