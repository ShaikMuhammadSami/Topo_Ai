from __future__ import annotations
from domain_tenant_fixtures import TEST_HEADERS, TEST_TENANT, seed_domain_tenant
from domain_tenant_fixtures import seed_domain_parents
from test_tenant_foundation import tenant_app

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.repositories.execution_intent_repository as repository
import app.services.execution_transaction as service
from app.db.database import Base
from app.db.models import (
    ExecutionIntentEventRecord,
    ExecutionIntentRecord,
)
from app.models.action_approval import (
    ActionApprovalDetail,
    ActionApprovalReadinessSnapshot,
    ActionApprovalStatus,
    ApprovalPreconditionSnapshot,
    FutureApprovalContract,
)
from app.models.execution_readiness import (
    ExecutionReadinessStatus,
    ExecutionReadinessTarget,
)
from app.models.execution_transaction import (
    ExecutionIntentCancelRequest,
    ExecutionIntentCreateRequest,
    ExecutionIntentStatus,
)
from app.models.recommendations import RecommendationRisk
from app.models.response_intelligence import (
    CurrentEvidenceStrength,
    HistoricalActionSupportLevel,
    ResponseActionFamily,
    ResponseActionSemantics,
)
from app.models.response_plan import ResponseActionCategory
from app.security.api_tokens import AuthPrincipal
from app.security.approval_authorization import (
    approval_control_principal,
)

NOW = datetime(2026, 8, 16, 13, 0, tzinfo=UTC)


def _principal(
    subject: str,
    *roles: str,
    authentication_type: str = "api_token",
) -> AuthPrincipal:
    return AuthPrincipal(
        subject=subject,
        display_name=subject,
        roles=roles,
        authentication_type=authentication_type,
    )


CREATOR = _principal("operator:creator", "operator")
VIEWER = _principal("viewer:reader", "viewer")
WORKER_A = service.ExecutionWorkerIdentity(
    subject="worker:a",
    display_name="Worker A",
    authentication_type="internal_service",
)
WORKER_B = service.ExecutionWorkerIdentity(
    subject="worker:b",
    display_name="Worker B",
    authentication_type="internal_service",
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    seed_domain_parents(
        engine, ("incidents", "incident:1"), ("action_approvals", "approval:1")
    )
    Session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with Session() as value:
        yield value


def _snapshot(
    *,
    entity_id: str = "entity:payments",
    change_event_id: str = "event:deploy",
    policy_version: str = "14f-v1",
    evidence_ids: list[str] | None = None,
) -> ActionApprovalReadinessSnapshot:
    evidence = evidence_ids or [
        "evidence:causal",
        "action-observation:validation",
    ]
    return ActionApprovalReadinessSnapshot(
        incident_id="incident:1",
        causal_analysis_id="analysis:1",
        response_plan_reference="response-plan:analysis:1",
        policy_version=policy_version,
        action_id="action:rollback",
        action_title="Consider rollback deployment",
        action_family=ResponseActionFamily.ROLLBACK,
        action_category=(
            ResponseActionCategory.ROLLBACK_CANDIDATE
        ),
        action_semantics=(
            ResponseActionSemantics.MITIGATION
        ),
        risk=RecommendationRisk.HIGH,
        requires_human_approval=True,
        readiness_status=(
            ExecutionReadinessStatus
            .READY_FOR_HUMAN_APPROVAL
        ),
        target=ExecutionReadinessTarget(
            entity_ids=[entity_id],
            change_event_id=change_event_id,
            uniquely_identified=True,
        ),
        root_event_id="event:commit",
        target_event_id=change_event_id,
        causal_confidence=0.92,
        current_evidence_strength=(
            CurrentEvidenceStrength.HIGH
        ),
        historical_support=(
            HistoricalActionSupportLevel
            .STRONGLY_SUPPORTED
        ),
        readiness_evidence_ids=evidence,
        preconditions=[
            ApprovalPreconditionSnapshot(
                code="validation:action:validate",
                required=True,
                satisfied=True,
                evidence_ids=evidence,
            )
        ],
        owner_team="payments",
        oncall_contact="pagerduty:payments",
        service_name="payment-api",
        eligible_for_future_execution=True,
    )


def _approval(
    *,
    status: ActionApprovalStatus = (
        ActionApprovalStatus.APPROVED
    ),
    currently_valid: bool = True,
    entity_id: str = "entity:payments",
    change_event_id: str = "event:deploy",
    policy_version: str = "14f-v1",
    evidence_ids: list[str] | None = None,
    fingerprint: str | None = None,
) -> ActionApprovalDetail:
    snapshot = _snapshot(
        entity_id=entity_id,
        change_event_id=change_event_id,
        policy_version=policy_version,
        evidence_ids=evidence_ids,
    )
    evidence_fingerprint = (
        fingerprint
        or service.hashlib.sha256(
            snapshot.model_dump_json().encode("utf-8")
        ).hexdigest()
    )
    return ActionApprovalDetail(
        approval_id="approval:1",
        incident_id="incident:1",
        action_id="action:rollback",
        action_family=ResponseActionFamily.ROLLBACK,
        status=status,
        risk=RecommendationRisk.HIGH,
        requires_human_approval=True,
        policy_version=policy_version,
        readiness_status_at_request=(
            ExecutionReadinessStatus
            .READY_FOR_HUMAN_APPROVAL
        ),
        evidence_fingerprint=evidence_fingerprint,
        target=snapshot.target,
        readiness_snapshot=snapshot,
        request_reason="Prepare rollback.",
        requested_by="operator:requester",
        requested_by_display_name="Requester",
        requested_by_roles=["operator"],
        requested_at=NOW - timedelta(minutes=2),
        decided_by="admin:approver",
        decided_by_display_name="Approver",
        decided_by_roles=["admin"],
        decided_at=NOW - timedelta(minutes=1),
        decision_reason="Approved exact evidence.",
        expires_at=NOW + timedelta(minutes=30),
        created_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=1),
        currently_valid=currently_valid,
        invalid_reason=(
            None
            if currently_valid
            else f"Approval is {status.value}."
        ),
        future_execution_contract=FutureApprovalContract(
            approval_reference_valid=currently_valid,
            requires_current_readiness_revalidation=True,
            execution_performed=False,
            interpretation="No execution.",
        ),
        audit_events=[],
    )


def _wire_approval(
    monkeypatch,
    holder: dict,
) -> None:
    def get_approval(session, *, incident_id, approval_id, now=None, tenant_id=None):
        assert incident_id == "incident:1"
        assert approval_id == "approval:1"
        return holder["approval"]

    monkeypatch.setattr(
        service,
        "get_action_approval",
        get_approval,
    )


def _create(
    session,
    monkeypatch,
    holder: dict | None = None,
):
    state = holder or {"approval": _approval()}
    _wire_approval(monkeypatch, state)
    return service.create_execution_intent(
        session,
        incident_id="incident:1",
        approval_id="approval:1",
        creator=CREATOR,
        now=NOW,
        tenant_id=TEST_TENANT,
    )


def test_valid_approved_action_creates_server_derived_intent(
    session,
    monkeypatch,
) -> None:
    result = _create(session, monkeypatch)

    assert result.status == ExecutionIntentStatus.PENDING
    assert result.incident_id == "incident:1"
    assert result.approval_id == "approval:1"
    assert result.action_id == "action:rollback"
    assert result.action_family == ResponseActionFamily.ROLLBACK
    assert result.target.entity_ids == ["entity:payments"]
    assert result.target.change_event_id == "event:deploy"
    assert result.policy_version == "14f-v1"
    assert result.approval_evidence_fingerprint
    assert len(result.idempotency_key) == 64
    assert result.currently_claimable is True
    assert result.execution_performed is False


@pytest.mark.parametrize(
    "status",
    [
        ActionApprovalStatus.PENDING,
        ActionApprovalStatus.REJECTED,
        ActionApprovalStatus.REVOKED,
        ActionApprovalStatus.EXPIRED,
        ActionApprovalStatus.INVALIDATED,
    ],
)
def test_non_valid_approval_cannot_create_intent(
    session,
    monkeypatch,
    status,
) -> None:
    holder = {
        "approval": _approval(
            status=status,
            currently_valid=False,
        )
    }
    _wire_approval(monkeypatch, holder)

    with pytest.raises(service.ExecutionIntentConflictError):
        service.create_execution_intent(
            session,
            incident_id="incident:1",
            approval_id="approval:1",
            creator=CREATOR,
            now=NOW,
            tenant_id=TEST_TENANT,
        )


def test_stale_approval_fingerprint_blocks_creation(
    session,
    monkeypatch,
) -> None:
    holder = {
        "approval": _approval(
            status=ActionApprovalStatus.INVALIDATED,
            currently_valid=False,
            fingerprint="f" * 64,
        )
    }
    _wire_approval(monkeypatch, holder)

    with pytest.raises(service.ExecutionIntentConflictError):
        service.create_execution_intent(
            session,
            incident_id="incident:1",
            approval_id="approval:1",
            creator=CREATOR,
            now=NOW,
            tenant_id=TEST_TENANT,
        )


def test_creation_schema_rejects_target_action_and_status_spoofing(
) -> None:
    for extra in (
        {"target": {"entity_ids": ["other"]}},
        {"action_id": "action:other"},
        {"status": "succeeded"},
        {"evidence_fingerprint": "a" * 64},
    ):
        with pytest.raises(ValidationError):
            ExecutionIntentCreateRequest.model_validate(
                {
                    "approval_id": "approval:1",
                    **extra,
                }
            )


def test_duplicate_creation_returns_one_logical_intent(
    session,
    monkeypatch,
) -> None:
    first = _create(session, monkeypatch)
    second = service.create_execution_intent(
        session,
        incident_id="incident:1",
        approval_id="approval:1",
        creator=CREATOR,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    third = service.create_execution_intent(
        session,
        incident_id="incident:1",
        approval_id="approval:1",
        creator=CREATOR,
        now=NOW + timedelta(seconds=2),
        tenant_id=TEST_TENANT,
    )
    count = session.scalar(
        select(func.count())
        .select_from(ExecutionIntentRecord)
    )

    assert {
        first.execution_id,
        second.execution_id,
        third.execution_id,
    } == {first.execution_id}
    assert count == 1


def test_cancelled_intent_is_still_the_same_logical_intent(
    session,
    monkeypatch,
) -> None:
    first = _create(session, monkeypatch)
    service.cancel_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=first.execution_id,
        actor=CREATOR,
        reason="Cancel the logical operation.",
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    repeated = service.create_execution_intent(
        session,
        incident_id="incident:1",
        approval_id="approval:1",
        creator=CREATOR,
        now=NOW + timedelta(seconds=2),
        tenant_id=TEST_TENANT,
    )

    assert repeated.execution_id == first.execution_id
    assert repeated.status == ExecutionIntentStatus.CANCELLED
    assert repeated.approval_currently_valid is True


def test_database_idempotency_uniqueness_handles_creation_race(
    tmp_path,
) -> None:
    database_path = tmp_path / "creation-race.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    seed_domain_parents(
        engine, ("incidents", "incident:1"), ("action_approvals", "approval:1")
    )
    Session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    approval = _approval()
    snapshot = service._snapshot_from_approval(
        approval
    )
    key = service.execution_intent_idempotency_key(
        snapshot
    )
    barrier = Barrier(2)

    def create_once():
        with Session() as thread_session:
            barrier.wait(timeout=10)
            record, _ = repository.create_execution_intent_record(
                thread_session,
                snapshot=snapshot,
                idempotency_key=key,
                creator=CREATOR,
                created_at=NOW,
                tenant_id=TEST_TENANT,
            )
            return record.execution_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create_once(), range(2)))

    with Session() as check_session:
        count = check_session.scalar(
            select(func.count())
            .select_from(ExecutionIntentRecord)
        )
        event_count = check_session.scalar(
            select(func.count())
            .select_from(ExecutionIntentEventRecord)
        )

    assert len(set(ids)) == 1
    assert count == 1
    assert event_count == 1


def test_database_rejects_manual_duplicate_idempotency_key(
    session,
    monkeypatch,
) -> None:
    created = _create(session, monkeypatch)
    original = session.get(
        ExecutionIntentRecord,
        created.execution_id,
    )
    assert original is not None
    duplicate = ExecutionIntentRecord(
        **{
            column.name: getattr(original, column.name)
            for column in ExecutionIntentRecord.__table__.columns
            if column.name != "execution_id"
        },
        execution_id="execution-intent:duplicate",
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_two_session_atomic_claim_allows_exactly_one_worker(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "claim-race.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    seed_domain_parents(
        engine, ("incidents", "incident:1"), ("action_approvals", "approval:1")
    )
    Session = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    holder = {"approval": _approval()}
    _wire_approval(monkeypatch, holder)

    with Session() as setup:
        intent = service.create_execution_intent(
            setup,
            incident_id="incident:1",
            approval_id="approval:1",
            creator=CREATOR,
            now=NOW,
            tenant_id=TEST_TENANT,
        )

    barrier = Barrier(2)
    original_atomic_claim = (
        service.atomic_claim_execution_intent_record
    )

    def synchronized_atomic_claim(*args, **kwargs):
        barrier.wait(timeout=10)
        return original_atomic_claim(*args, **kwargs)

    monkeypatch.setattr(
        service,
        "atomic_claim_execution_intent_record",
        synchronized_atomic_claim,
    )

    def compete(worker):
        with Session() as thread_session:
            try:
                receipt = service.claim_execution_intent(
                    thread_session,
                    incident_id="incident:1",
                    execution_id=intent.execution_id,
                    worker=worker,
                    now=NOW + timedelta(seconds=1),
                    tenant_id=TEST_TENANT,
                )
                return ("won", receipt.execution_intent.claimed_by)
            except service.ExecutionIntentConflictError:
                return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(compete, [WORKER_A, WORKER_B])
        )

    assert sorted(value[0] for value in outcomes) == [
        "conflict",
        "won",
    ]

    with Session() as check_session:
        record = check_session.get(
            ExecutionIntentRecord,
            intent.execution_id,
        )
        claimed_events = check_session.scalar(
            select(func.count())
            .select_from(ExecutionIntentEventRecord)
            .where(
                ExecutionIntentEventRecord.event_type
                == "claimed"
            )
        )

    assert record is not None
    assert record.status == "claimed"
    assert record.attempt_count == 1
    assert claimed_events == 1


def test_claim_lease_expiry_reclaims_with_new_generation(
    session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        service.EXECUTION_CLAIM_TTL_ENV,
        "15",
    )
    intent = _create(session, monkeypatch)
    first = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    second = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_B,
        now=NOW + timedelta(seconds=17),
        tenant_id=TEST_TENANT,
    )

    assert first.claim_generation == 1
    assert second.claim_generation == 2
    assert first.claim_token != second.claim_token
    assert second.execution_intent.attempt_count == 2
    assert [
        event.event_type.value
        for event in second.execution_intent.audit_events
    ] == [
        "created",
        "claimed",
        "claim_expired",
        "claimed",
    ]


def test_stale_worker_cannot_release_reclaimed_generation(
    session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        service.EXECUTION_CLAIM_TTL_ENV,
        "15",
    )
    intent = _create(session, monkeypatch)
    first = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    second = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_B,
        now=NOW + timedelta(seconds=17),
        tenant_id=TEST_TENANT,
    )

    with pytest.raises(service.ExecutionIntentConflictError):
        service.release_execution_claim(
            session,
            incident_id="incident:1",
            execution_id=intent.execution_id,
            worker=WORKER_A,
            claim_generation=first.claim_generation,
            claim_token=first.claim_token,
            now=NOW + timedelta(seconds=18),
            tenant_id=TEST_TENANT,
        )

    current = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=18),
        tenant_id=TEST_TENANT,
    )
    assert current.claimed_by == WORKER_B.subject
    assert current.claim_generation == second.claim_generation


def test_attempt_count_increments_only_on_successful_claims(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    first = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    with pytest.raises(service.ExecutionIntentConflictError):
        service.claim_execution_intent(
            session,
            incident_id="incident:1",
            execution_id=intent.execution_id,
            worker=WORKER_B,
            now=NOW + timedelta(seconds=2),
            tenant_id=TEST_TENANT,
        )

    released = service.release_execution_claim(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        claim_generation=first.claim_generation,
        claim_token=first.claim_token,
        now=NOW + timedelta(seconds=3),
        tenant_id=TEST_TENANT,
    )
    viewed = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=4),
        tenant_id=TEST_TENANT,
    )

    assert released.attempt_count == 1
    assert viewed.attempt_count == 1


@pytest.mark.parametrize(
    ("approval", "expected_status"),
    [
        (
            _approval(
                status=ActionApprovalStatus.REVOKED,
                currently_valid=False,
            ),
            ExecutionIntentStatus.INVALIDATED,
        ),
        (
            _approval(
                status=ActionApprovalStatus.EXPIRED,
                currently_valid=False,
            ),
            ExecutionIntentStatus.EXPIRED,
        ),
        (
            _approval(
                status=ActionApprovalStatus.INVALIDATED,
                currently_valid=False,
                evidence_ids=["evidence:new"],
            ),
            ExecutionIntentStatus.INVALIDATED,
        ),
    ],
)
def test_invalid_approval_before_claim_makes_intent_non_claimable(
    session,
    monkeypatch,
    approval,
    expected_status,
) -> None:
    holder = {"approval": _approval()}
    intent = _create(session, monkeypatch, holder)
    holder["approval"] = approval

    with pytest.raises(service.ExecutionIntentConflictError):
        service.claim_execution_intent(
            session,
            incident_id="incident:1",
            execution_id=intent.execution_id,
            worker=WORKER_A,
            now=NOW + timedelta(seconds=1),
            tenant_id=TEST_TENANT,
        )

    record = session.get(
        ExecutionIntentRecord,
        intent.execution_id,
    )
    session.refresh(record)
    assert record.status == expected_status.value
    detail = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=2),
        tenant_id=TEST_TENANT,
    )
    assert detail.audit_events[-1].event_type.value == (
        "expired"
        if expected_status == ExecutionIntentStatus.EXPIRED
        else "invalidated"
    )


@pytest.mark.parametrize(
    "changed_approval",
    [
        _approval(entity_id="entity:other"),
        _approval(change_event_id="event:other"),
        _approval(policy_version="14f-v2"),
        _approval(evidence_ids=["evidence:other"]),
    ],
)
def test_target_policy_or_readiness_evidence_change_invalidates_intent(
    session,
    monkeypatch,
    changed_approval,
) -> None:
    holder = {"approval": _approval()}
    intent = _create(session, monkeypatch, holder)
    holder["approval"] = changed_approval
    result = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert result.status == ExecutionIntentStatus.INVALIDATED
    assert result.currently_claimable is False
    assert result.execution_performed is False


def test_cancel_pending_intent_is_durable_and_non_claimable(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    cancelled = service.cancel_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        actor=CREATOR,
        reason="Operational window closed.",
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    loaded = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=2),
        tenant_id=TEST_TENANT,
    )

    assert cancelled.status == ExecutionIntentStatus.CANCELLED
    assert loaded.status == ExecutionIntentStatus.CANCELLED
    assert loaded.cancellation_reason == "Operational window closed."
    assert loaded.currently_claimable is False

    with pytest.raises(service.ExecutionIntentConflictError):
        service.claim_execution_intent(
            session,
            incident_id="incident:1",
            execution_id=intent.execution_id,
            worker=WORKER_A,
            now=NOW + timedelta(seconds=3),
            tenant_id=TEST_TENANT,
        )


def test_claimed_intent_cannot_be_cancelled(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    with pytest.raises(service.ExecutionIntentConflictError):
        service.cancel_execution_intent(
            session,
            incident_id="incident:1",
            execution_id=intent.execution_id,
            actor=CREATOR,
            reason="Do not pretend an active claim was undone.",
            now=NOW + timedelta(seconds=2),
            tenant_id=TEST_TENANT,
        )


def test_execution_snapshot_is_immutable_across_returned_model_changes(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    intent.execution_snapshot.target.entity_ids = [
        "entity:tampered"
    ]
    reloaded = service.get_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert reloaded.target.entity_ids == ["entity:payments"]
    assert reloaded.execution_snapshot.target.entity_ids == [
        "entity:payments"
    ]


def test_public_api_has_no_claim_execute_or_arbitrary_status_endpoint(
    monkeypatch,
) -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    execution_paths = {
        path
        for path in paths
        if "execution-intents" in path
    }

    assert all("/claim" not in path for path in execution_paths)
    assert all("/execute" not in path for path in execution_paths)
    assert all("/release" not in path for path in execution_paths)
    assert all("/status" not in path for path in execution_paths)


def test_models_and_responses_contain_no_command_or_claim_secret(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    payload = intent.model_dump(mode="json")

    def keys(value):
        if isinstance(value, dict):
            for key, nested in value.items():
                yield key
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)

    all_keys = set(keys(payload))
    assert "command" not in all_keys
    assert "shell" not in all_keys
    assert "claim_token" not in all_keys
    assert "claim_token_hash" not in all_keys


def test_no_recovery_or_infrastructure_execution_is_called(
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
    intent = _create(session, monkeypatch)
    claim = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert claim.execution_intent.execution_performed is False
    assert claim.execution_intent.started_at is None
    assert claim.execution_intent.completed_at is None
    assert claim.execution_intent.result_reference is None
    assert claim.claim_token not in repr(claim)


def test_audit_events_preserve_claim_release_and_cancel(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    claim = service.claim_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )
    service.release_execution_claim(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        worker=WORKER_A,
        claim_generation=claim.claim_generation,
        claim_token=claim.claim_token,
        now=NOW + timedelta(seconds=2),
        tenant_id=TEST_TENANT,
    )
    cancelled = service.cancel_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        actor=CREATOR,
        reason="Stop before adapter processing.",
        now=NOW + timedelta(seconds=3),
        tenant_id=TEST_TENANT,
    )

    assert [
        event.sequence
        for event in cancelled.audit_events
    ] == [1, 2, 3, 4]
    assert [
        event.event_type.value
        for event in cancelled.audit_events
    ] == [
        "created",
        "claimed",
        "released",
        "cancelled",
    ]


def test_listing_is_bounded_and_filterable(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    result = service.list_execution_intents(
        session,
        incident_id="incident:1",
        status=ExecutionIntentStatus.PENDING,
        approval_id="approval:1",
        action_id="action:rollback",
        limit=1000,
        offset=0,
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert [item.execution_id for item in result] == [
        intent.execution_id
    ]


def test_human_and_worker_authorization_boundaries() -> None:
    viewer_request = SimpleNamespace(
        state=SimpleNamespace(principal=VIEWER)
    )

    with pytest.raises(HTTPException) as exc:
        approval_control_principal(viewer_request)

    assert exc.value.status_code == 403

    with pytest.raises(
        service.ExecutionWorkerAuthorizationError
    ):
        service._worker_principal(
            service.ExecutionWorkerIdentity(
                subject="operator:human",
                display_name="Human Operator",
                authentication_type="api_token",
            )
        )


def test_claim_identity_cannot_be_supplied_to_public_schema() -> None:
    with pytest.raises(ValidationError):
        ExecutionIntentCreateRequest.model_validate(
            {
                "approval_id": "approval:1",
                "claimed_by": "worker:spoofed",
            }
        )


def test_claim_ttl_has_safe_default_and_server_bounds(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        service.EXECUTION_CLAIM_TTL_ENV,
        raising=False,
    )
    assert (
        service.configured_execution_claim_ttl_seconds()
        == 60
    )

    monkeypatch.setenv(
        service.EXECUTION_CLAIM_TTL_ENV,
        "1",
    )
    assert (
        service.configured_execution_claim_ttl_seconds()
        == 15
    )

    monkeypatch.setenv(
        service.EXECUTION_CLAIM_TTL_ENV,
        "9999",
    )
    assert (
        service.configured_execution_claim_ttl_seconds()
        == 300
    )


def test_cancellation_reason_is_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        ExecutionIntentCancelRequest(reason=" ")

    with pytest.raises(ValidationError):
        ExecutionIntentCancelRequest(reason="x" * 4001)


def test_secret_shaped_cancellation_reason_is_redacted(
    session,
    monkeypatch,
) -> None:
    intent = _create(session, monkeypatch)
    result = service.cancel_execution_intent(
        session,
        incident_id="incident:1",
        execution_id=intent.execution_id,
        actor=CREATOR,
        reason="Cancel with token=supersecretvalue",
        now=NOW + timedelta(seconds=1),
        tenant_id=TEST_TENANT,
    )

    assert result.cancellation_reason == (
        "Cancel with [REDACTED]"
    )
    assert "supersecretvalue" not in (
        result.audit_events[-1].reason or ""
    )


def test_new_execution_intent_routes_require_authentication(
    required_auth_app,
) -> None:
    client = TestClient(required_auth_app, headers=TEST_HEADERS)
    response = client.post(
        (
            "/api/v1/incidents/incident%3A1/"
            "execution-intents"
        ),
        json={"approval_id": "approval:1"},
    )

    assert response.status_code == 401


def test_execution_intent_list_limit_is_enforced_by_api(
    tenant_app,
) -> None:
    from test_tenant_foundation import _bearer, _create_tenant

    application, _, tokens = tenant_app
    client = TestClient(application)
    tenant = _create_tenant(client, tokens["bootstrap"])
    response = client.get(
        ("/api/v1/incidents/incident%3A1/" "execution-intents?limit=101"),
        headers=_bearer(tokens["bootstrap"], tenant["tenant_id"]),
    )

    assert response.status_code == 422


def test_database_tables_preserve_intent_and_event_history(
    session,
) -> None:
    table_names = set(Base.metadata.tables)

    assert "execution_intents" in table_names
    assert "execution_intent_events" in table_names
    unique_keys = {
        tuple(column.name for column in index.columns)
        for index in ExecutionIntentRecord.__table__.indexes if index.unique
    }
    assert ("tenant_id", "idempotency_key") in unique_keys
    assert ("tenant_id", "approval_id") in unique_keys
