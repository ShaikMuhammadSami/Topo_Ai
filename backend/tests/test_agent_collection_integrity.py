from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.agents import submit_snapshot
from app.db.database import Base
from app.db.models import (
    ChangeEventRecord,
    ChangeRecord,
    SnapshotRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import (
    AgentSnapshotSubmission,
    agent_snapshot_completeness_error,
)
from app.services.agent_snapshot_ingest import (
    SNAPSHOT_OPTIONAL_RESOURCE_UNOBSERVED,
    persist_agent_snapshot,
)
from app.security.authorization_enforcement import (
    authorize_agent_fixed_purpose,
    bind_authorization_context,
)
from authorization_test_support import (
    tenant_admin_authorization,
)
from domain_tenant_fixtures import (
    TEST_TENANT,
    seed_domain_tenant,
)


def _submission(
    *,
    status: str,
    plugin_status: str,
    inventory: dict | None = None,
    submission_id: str = "submission:integrity",
    collected_at: str = "2026-11-13T10:00:00+00:00",
) -> AgentSnapshotSubmission:
    plugin = {
        "name": "kubernetes",
        "status": plugin_status,
        "errors": [],
        "inventory_counts": {},
    }
    if plugin_status not in {
        "success",
        "skipped_optional",
    }:
        plugin["collection_failures"] = [
            {
                "resource": "replicasets",
                "status_code": 403,
                "category": "authorization",
            }
        ]

    return AgentSnapshotSubmission(
        submission_id=submission_id,
        collected_at=collected_at,
        cluster_name="collection-integrity",
        collector_version="1.0",
        inventory=inventory or {},
        metadata={
            "collection_status": status,
            "plugin_count": 1,
            "successful_plugin_count": int(
                plugin_status
                in {"success", "skipped_optional"}
            ),
            "failed_plugin_count": int(
                plugin_status
                not in {"success", "skipped_optional"}
            ),
            "plugins": [plugin],
        },
    )


@pytest.mark.parametrize(
    ("status", "plugin_status"),
    [
        ("partial", "partial"),
        ("failed", "failed"),
        ("success", "partial"),
    ],
)
def test_backend_rejects_declared_incomplete_collection_before_ingest(
    status: str,
    plugin_status: str,
) -> None:
    submission = _submission(
        status=status,
        plugin_status=plugin_status,
    )

    assert agent_snapshot_completeness_error(submission) is not None
    with pytest.raises(
        ValueError,
        match="not accepted",
    ):
        persist_agent_snapshot(
            None,
            agent=SimpleNamespace(),
            submission=submission,
        )

    with pytest.raises(HTTPException) as exc_info:
        submit_snapshot(
            submission,
            request=SimpleNamespace(
                state=SimpleNamespace()
            ),
            agent=SimpleNamespace(
                cluster_name=(
                    submission.cluster_name
                )
            ),
            session=None,
        )

    assert exc_info.value.status_code == 400


def test_backend_accepts_complete_declared_contract() -> None:
    submission = _submission(
        status="success",
        plugin_status="success",
    )

    assert agent_snapshot_completeness_error(submission) is None


def test_backend_rejects_declared_zero_plugin_collection() -> None:
    submission = _submission(
        status="success",
        plugin_status="success",
    )
    submission.metadata.update(
        {
            "plugin_count": 0,
            "successful_plugin_count": 0,
            "failed_plugin_count": 0,
            "plugins": [],
        }
    )

    assert agent_snapshot_completeness_error(submission) == (
        "At least one completed plugin is required."
    )
    with pytest.raises(
        ValueError,
        match="At least one completed plugin",
    ):
        persist_agent_snapshot(
            None,
            agent=SimpleNamespace(),
            submission=submission,
        )

    with pytest.raises(HTTPException) as exc_info:
        submit_snapshot(
            submission,
            request=SimpleNamespace(
                state=SimpleNamespace()
            ),
            agent=SimpleNamespace(
                cluster_name=(
                    submission.cluster_name
                )
            ),
            session=None,
        )

    assert exc_info.value.status_code == 400


def test_optional_skip_is_not_a_required_collection_failure() -> None:
    submission = _submission(
        status="success",
        plugin_status="success",
    )
    submission.metadata["plugins"][0][
        "skipped_optional"
    ] = [
        {
            "resource": "configmaps",
            "status_code": 403,
        }
    ]

    assert agent_snapshot_completeness_error(submission) is None


def test_success_status_cannot_hide_failed_required_resource() -> None:
    submission = _submission(
        status="success",
        plugin_status="success",
    )
    plugin = submission.metadata["plugins"][0]
    plugin["resource_completeness"] = {
        "deployments": "complete",
        "replicasets": "failed",
    }

    assert agent_snapshot_completeness_error(submission) is not None


def test_legacy_submission_without_completeness_contract_remains_supported(
) -> None:
    submission = AgentSnapshotSubmission(
        submission_id="submission:legacy",
        collected_at="2026-11-13T10:00:00+00:00",
        cluster_name="collection-integrity",
        collector_version="0.6.0",
        inventory={},
        metadata={"checkpoint_reason": "manual"},
    )

    assert agent_snapshot_completeness_error(submission) is None


def _session_and_agent() -> tuple[Session, TopoAgentRecord, object]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:"
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    session = Session(engine)
    bind_authorization_context(
        tenant_admin_authorization(
            session,
            TEST_TENANT,
        )
    )
    now = utc_now_iso()
    agent = TopoAgentRecord(
        tenant_id=TEST_TENANT,
        agent_id="agent:collection-integrity",
        name="collection-integrity",
        agent_type="kubernetes",
        cluster_name="collection-integrity",
        environment="test",
        version="1.0",
        token_hash="a" * 64,
        token_hint="test",
        status="online",
        collection_interval_seconds=300,
        heartbeat_interval_seconds=30,
        namespace_scope_json='["payments"]',
        capabilities_json="[]",
        labels_json="{}",
        metadata_json="{}",
        buffered_item_count=0,
        enrolled_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(agent)
    session.commit()
    authorization = authorize_agent_fixed_purpose(
        session,
        agent=agent,
        fixed_purpose=(
            "app.services.agent_snapshot_ingest."
            "persist_agent_snapshot"
        ),
    )
    return session, agent, authorization


def _kubernetes_inventory(
    *,
    include_replica_set: bool,
    include_config_map: bool = False,
) -> dict:
    inventory = {
        "namespaces": [
            {
                "uid": "namespace-payments",
                "name": "payments",
            }
        ],
        "deployments": [
            {
                "uid": "deployment-payment",
                "name": "payment-api",
                "namespace": "payments",
                "images": ["payment:v1"],
                "config_map_refs": ["payment-config"],
            }
        ],
        "replicasets": [],
        "pods": [],
        "services": [],
        "configmaps": [],
    }
    if include_replica_set:
        inventory["replicasets"] = [
            {
                "uid": "replicaset-payment",
                "name": "payment-api-abc",
                "namespace": "payments",
                "owner_uid": "deployment-payment",
                "owner_kind": "Deployment",
            }
        ]
    if include_config_map:
        inventory["configmaps"] = [
            {
                "uid": "configmap-payment",
                "name": "payment-config",
                "namespace": "payments",
                "keys": ["MODE"],
                "data_sha256": "sha256:" + "1" * 64,
            }
        ]
    return inventory


def _declare_config_map_state(
    submission: AgentSnapshotSubmission,
    state: str,
) -> None:
    plugin = submission.metadata["plugins"][0]
    plugin["resource_completeness"] = {
        "configmaps": state,
    }
    if state == "skipped_optional":
        plugin["skipped_optional"] = [
            {
                "resource": "configmaps",
                "status_code": 403,
                "category": "authorization",
            }
        ]


def _api_request(authorization: object) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            authorization_context=authorization
        )
    )


def test_failed_cycle_preserves_snapshot_and_recovery_has_no_false_changes(
) -> None:
    session, agent, authorization = _session_and_agent()
    baseline = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True
        ),
        submission_id="submission:baseline",
        collected_at="2026-11-13T10:00:00+00:00",
    )
    persist_agent_snapshot(
        session,
        agent=agent,
        submission=baseline,
        authorization_context=authorization,
    )

    zero_plugin = _submission(
        status="success",
        plugin_status="success",
        inventory={},
        submission_id="submission:zero-plugin",
        collected_at="2026-11-13T10:00:30+00:00",
    )
    zero_plugin.metadata.update(
        {
            "plugin_count": 0,
            "successful_plugin_count": 0,
            "failed_plugin_count": 0,
            "plugins": [],
        }
    )
    with pytest.raises(ValueError):
        persist_agent_snapshot(
            session,
            agent=agent,
            submission=zero_plugin,
            authorization_context=authorization,
        )

    assert session.scalar(
        select(func.count()).select_from(
            SnapshotRecord
        )
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(
            ChangeRecord
        )
    ) == 0

    incomplete = _submission(
        status="partial",
        plugin_status="partial",
        inventory=_kubernetes_inventory(
            include_replica_set=False
        ),
        submission_id="submission:forbidden",
        collected_at="2026-11-13T10:01:00+00:00",
    )
    with pytest.raises(ValueError):
        persist_agent_snapshot(
            session,
            agent=agent,
            submission=incomplete,
            authorization_context=authorization,
        )

    recovery = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True
        ),
        submission_id="submission:recovery",
        collected_at="2026-11-13T10:02:00+00:00",
    )
    receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=recovery,
        authorization_context=authorization,
    )

    assert receipt.detected_change_count == 0
    assert session.scalar(
        select(func.count()).select_from(
            SnapshotRecord
        )
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(
            ChangeRecord
        )
    ) == 0

    deletion = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=False
        ),
        submission_id="submission:deletion",
        collected_at="2026-11-13T10:03:00+00:00",
    )
    deletion_receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=deletion,
        authorization_context=authorization,
    )

    assert deletion_receipt.detected_change_count > 0
    change_types = set(
        session.scalars(
            select(ChangeRecord.change_type)
        ).all()
    )
    assert "entity_removed" in change_types
    assert "relationship_removed" in change_types
    session.close()


def test_config_map_permission_loss_cannot_create_false_topology_changes(
) -> None:
    session, agent, authorization = _session_and_agent()
    baseline = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True,
            include_config_map=True,
        ),
        submission_id="submission:configmap-baseline",
        collected_at="2026-11-13T11:00:00+00:00",
    )
    _declare_config_map_state(baseline, "complete")
    submit_snapshot(
        baseline,
        request=_api_request(authorization),
        agent=agent,
        session=session,
    )

    denied = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True,
            include_config_map=False,
        ),
        submission_id="submission:configmap-denied",
        collected_at="2026-11-13T11:01:00+00:00",
    )
    _declare_config_map_state(denied, "skipped_optional")
    with pytest.raises(HTTPException) as exc_info:
        submit_snapshot(
            denied,
            request=_api_request(authorization),
            agent=agent,
            session=session,
        )
    assert exc_info.value.status_code == 409
    assert (
        exc_info.value.detail
        == SNAPSHOT_OPTIONAL_RESOURCE_UNOBSERVED
    )

    assert session.scalar(
        select(func.count()).select_from(SnapshotRecord)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(ChangeRecord)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(ChangeEventRecord)
    ) == 0

    restored = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True,
            include_config_map=True,
        ),
        submission_id="submission:configmap-restored",
        collected_at="2026-11-13T11:02:00+00:00",
    )
    _declare_config_map_state(restored, "complete")
    restored_receipt = submit_snapshot(
        restored,
        request=_api_request(authorization),
        agent=agent,
        session=session,
    )

    assert restored_receipt.detected_change_count == 0
    assert session.scalar(
        select(func.count()).select_from(SnapshotRecord)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(ChangeRecord)
    ) == 0
    assert session.scalar(
        select(func.count()).select_from(ChangeEventRecord)
    ) == 0

    deletion = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True,
            include_config_map=False,
        ),
        submission_id="submission:configmap-deleted",
        collected_at="2026-11-13T11:03:00+00:00",
    )
    _declare_config_map_state(deletion, "complete")
    deletion_receipt = submit_snapshot(
        deletion,
        request=_api_request(authorization),
        agent=agent,
        session=session,
    )

    assert deletion_receipt.detected_change_count >= 2
    change_types = set(
        session.scalars(select(ChangeRecord.change_type)).all()
    )
    assert "entity_removed" in change_types
    assert "relationship_removed" in change_types
    assert session.scalar(
        select(func.count()).select_from(ChangeEventRecord)
    ) > 0
    session.close()


def test_initial_optional_config_map_skip_preserves_default_rbac() -> None:
    session, agent, authorization = _session_and_agent()
    submission = _submission(
        status="success",
        plugin_status="success",
        inventory=_kubernetes_inventory(
            include_replica_set=True,
            include_config_map=False,
        ),
        submission_id="submission:configmap-never-observed",
        collected_at="2026-11-13T12:00:00+00:00",
    )
    _declare_config_map_state(submission, "skipped_optional")

    receipt = persist_agent_snapshot(
        session,
        agent=agent,
        submission=submission,
        authorization_context=authorization,
    )

    assert receipt.checkpoint_created is True
    assert receipt.detected_change_count == 0
    assert session.scalar(
        select(func.count()).select_from(SnapshotRecord)
    ) == 1
    session.close()
