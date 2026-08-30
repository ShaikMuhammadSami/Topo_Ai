from __future__ import annotations
from app.repositories.tenant_scope import (
    tenant_commit,
    UNOWNED_MACHINE,
)
from app.security.tenant_context import TenantContext, require_tenant_context
from fastapi import Depends

import json

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy.orm import Session

from app.db.database import (
    get_session,
)
from app.db.models import (
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.agents import (
    AgentConfigView,
    AgentDetail,
    AgentEnrollRequest,
    AgentEnrollResponse,
    AgentEnrollmentTokenCreateRequest,
    AgentEnrollmentTokenResponse,
    AgentHealthResponse,
    AgentHeartbeatRequest,
    AgentHeartbeatResponse,
    AgentSnapshotReceipt,
    AgentSnapshotSubmission,
    AgentSummary,
    AgentPluginsResponse,
)
from app.repositories.agent_repository import (
    AgentEnrollmentRejected,
    agent_health,
    create_enrollment_token,
    enroll_agent,
    list_agents,
    load_agent,
    record_heartbeat,
    revoke_agent,
    agent_plugins,
)
from app.security.agent_tokens import (
    require_agent,
)
from app.services.agent_snapshot_ingest import (
    persist_agent_snapshot,
)
from app.models.runtime_observability import (
    RuntimeDependencyView,
    RuntimeEventBatchReceipt,
    RuntimeEventBatchRequest,
    RuntimeSensorHeartbeatRequest,
    RuntimeSensorHeartbeatResponse,
    RuntimeSensorView,
)
from app.repositories.runtime_observability_repository import (
    ingest_runtime_event_batch,
    list_runtime_dependencies,
    list_runtime_sensors,
    record_sensor_heartbeat,
)
from app.models.clouds import (
    AgentCloudStatusResponse,
)
from app.repositories.cloud_repository import (
    agent_cloud_status,
)
from app.models.change_events import (
    AgentChangeEventBatch,
    AgentChangeEventBatchReceipt,
)
from app.repositories.change_event_repository import (
    ingest_change_event,
)
from app.models.lifecycle_automation import (
    FailureSignalBatchRequest,
    FailureSignalBatchResult,
    TopologyCheckpointReason,
)
from app.services.continuous_lifecycle import (
    ingest_failure_signal_batch,
)
from app.services.topology_checkpoint import (
    is_topology_affecting_change_event,
)

admin_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["agents"],
)

agent_router = APIRouter(
    prefix="/api/v1/agent",
    tags=["agent-runtime"],
)


@admin_router.get(
    "/{agent_id}/cloud-status",
    response_model=(
        AgentCloudStatusResponse
    ),
)
def get_agent_cloud_status(
    agent_id: str,
    provider: str = Query(
        default="aws",
        pattern="^(aws|azure|gcp)$",
    ),
    session: Session = Depends(
        get_session
    ),
) -> AgentCloudStatusResponse:
    result = agent_cloud_status(
        session=session,
        agent_id=agent_id,
        provider=provider,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found.",
        )

    return result


def _principal_subject(
    request: Request,
) -> str | None:
    principal = getattr(
        request.state,
        "principal",
        None,
    )

    return getattr(
        principal,
        "subject",
        None,
    )


def _require_admin(
    request: Request,
) -> None:
    principal = getattr(
        request.state,
        "principal",
        None,
    )

    roles = getattr(
        principal,
        "roles",
        (),
    )

    if "admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail=(
                "The admin role is "
                "required."
            ),
        )


@admin_router.post(
    "/enrollment-tokens",
    response_model=(
        AgentEnrollmentTokenResponse
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def create_token(
    request_body:
        AgentEnrollmentTokenCreateRequest,
    request: Request,
    session: Session = Depends(
        get_session
    ),
) -> AgentEnrollmentTokenResponse:
    _require_admin(request)

    return create_enrollment_token(
        session=session,
        request=request_body,
        created_by=(
            _principal_subject(request)
        ),
    )


@admin_router.post(
    "/enroll",
    response_model=AgentEnrollResponse,
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def enroll(
    request:
        AgentEnrollRequest,
    session: Session = Depends(
        get_session
    ),
) -> AgentEnrollResponse:
    try:
        return enroll_agent(
            session=session,
            request=request,
        )

    except AgentEnrollmentRejected as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        ) from exc


@admin_router.get(
    "",
    response_model=list[
        AgentSummary
    ],
)
def get_agents(
    limit: int = Query(
        100,
        ge=1,
        le=1000,
    ),
    offset: int = Query(
        0,
        ge=0,
    ),
    session: Session = Depends(
        get_session
    ),
) -> list[AgentSummary]:
    return list_agents(
        session=session,
        limit=limit,
        offset=offset,
    )


@admin_router.get(
    "/{agent_id}",
    response_model=AgentDetail,
)
def get_agent(
    agent_id: str,
    session: Session = Depends(
        get_session
    ),
) -> AgentDetail:
    result = load_agent(
        session=session,
        agent_id=agent_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found.",
        )

    return result


@admin_router.get(
    "/{agent_id}/health",
    response_model=AgentHealthResponse,
)
def get_agent_health(
    agent_id: str,
    session: Session = Depends(
        get_session
    ),
) -> AgentHealthResponse:
    result = agent_health(
        session=session,
        agent_id=agent_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found.",
        )

    return result


@admin_router.post(
    "/{agent_id}/revoke",
    response_model=AgentDetail,
)
def revoke(
    agent_id: str,
    request: Request,
    session: Session = Depends(
        get_session
    ),
) -> AgentDetail:
    _require_admin(request)

    result = revoke_agent(
        session=session,
        agent_id=agent_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found.",
        )

    return result


@agent_router.get(
    "/config",
    response_model=AgentConfigView,
)
def runtime_config(
    agent: TopoAgentRecord = Depends(
        require_agent
    ),
) -> AgentConfigView:
    import json

    return AgentConfigView(
        collection_interval_seconds=(
            agent
            .collection_interval_seconds
        ),
        heartbeat_interval_seconds=(
            agent
            .heartbeat_interval_seconds
        ),
        namespace_scope=json.loads(
            agent.namespace_scope_json
        ),
    )


@agent_router.post(
    "/heartbeat",
    response_model=(
        AgentHeartbeatResponse
    ),
)
def heartbeat(
    request:
        AgentHeartbeatRequest,
    agent: TopoAgentRecord = Depends(
        require_agent
    ),
    session: Session = Depends(
        get_session
    ),
) -> AgentHeartbeatResponse:
    return record_heartbeat(
        session=session,
        record=agent,
        request=request,
    )


@agent_router.post(
    "/snapshots",
    response_model=(
        AgentSnapshotReceipt
    ),
    status_code=(
        status.HTTP_201_CREATED
    ),
)
def submit_snapshot(
    submission:
        AgentSnapshotSubmission,
    agent: TopoAgentRecord = Depends(
        require_agent
    ),
    session: Session = Depends(
        get_session
    ),
) -> AgentSnapshotReceipt:
    if (
        submission.cluster_name
        != agent.cluster_name
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Snapshot cluster name does "
                "not match the enrolled agent."
            ),
        )

    return persist_agent_snapshot(
        session=session,
        agent=agent,
        submission=submission,
    )


@admin_router.get(
    "/{agent_id}/plugins",
    response_model=(
        AgentPluginsResponse
    ),
)
def get_agent_plugins(
    agent_id: str,
    session: Session = Depends(
        get_session
    ),
) -> AgentPluginsResponse:
    result = agent_plugins(
        session=session,
        agent_id=agent_id,
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Agent not found.",
        )

    return result


@agent_router.post(
    "/runtime/heartbeat",
    response_model=(RuntimeSensorHeartbeatResponse),
)
def runtime_sensor_heartbeat(
    request: RuntimeSensorHeartbeatRequest,
    agent: TopoAgentRecord = Depends(require_agent),
    session: Session = Depends(get_session),
) -> RuntimeSensorHeartbeatResponse:
    return record_sensor_heartbeat(
        session=session,
        agent=agent,
        request=request,
        tenant_id=UNOWNED_MACHINE,
    )


@agent_router.post(
    "/runtime/batches",
    response_model=(RuntimeEventBatchReceipt),
    status_code=status.HTTP_201_CREATED,
)
def runtime_event_batch(
    request: RuntimeEventBatchRequest,
    agent: TopoAgentRecord = Depends(require_agent),
    session: Session = Depends(get_session),
) -> RuntimeEventBatchReceipt:
    try:
        return ingest_runtime_event_batch(
            session=session,
            agent=agent,
            request=request,
            tenant_id=UNOWNED_MACHINE,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@admin_router.get(
    "/{agent_id}/sensors",
    response_model=list[RuntimeSensorView],
)
def get_runtime_sensors(
    agent_id: str,
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[RuntimeSensorView]:
    # Domain evidence is independently owned. Do not disclose the existence
    # of an unbound PH-3E agent while listing this tenant's sensor records.
    return list_runtime_sensors(
        session=session,
        agent_id=agent_id,
        tenant_id=tenant_context.tenant_id,
    )


@admin_router.get(
    "/{agent_id}/runtime-dependencies",
    response_model=list[RuntimeDependencyView],
)
def get_runtime_dependencies(
    agent_id: str,
    window_minutes: int = Query(
        default=15,
        ge=1,
        le=10080,
    ),
    limit: int = Query(
        default=1000,
        ge=1,
        le=5000,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    session: Session = Depends(get_session),
    *,
    tenant_context: TenantContext = Depends(require_tenant_context),
) -> list[RuntimeDependencyView]:
    # Unknown/foreign agent selectors produce the same empty evidence list.
    return list_runtime_dependencies(
        session=session,
        agent_id=agent_id,
        window_minutes=window_minutes,
        limit=limit,
        offset=offset,
        tenant_id=tenant_context.tenant_id,
    )


@agent_router.post(
    "/change-events",
    response_model=(AgentChangeEventBatchReceipt),
    status_code=(status.HTTP_201_CREATED),
)
def submit_change_events(
    request: AgentChangeEventBatch,
    agent: TopoAgentRecord = Depends(require_agent),
    session: Session = Depends(get_session),
) -> AgentChangeEventBatchReceipt:
    event_ids: list[str] = []
    topology_affecting_count = 0

    try:
        for event in request.events:
            # Kubernetes-originated events
            # must not claim to belong to
            # another cluster.
            if (
                event.source.value
                == "kubernetes"
            ):
                if (
                    event.cluster_name
                    and event.cluster_name
                    != agent.cluster_name
                ):
                    raise ValueError(
                        "Kubernetes change "
                        "event cluster does "
                        "not match the "
                        "enrolled agent."
                    )

                if not event.cluster_name:
                    event = event.model_copy(
                        update={
                            "cluster_name":
                                agent.cluster_name
                        }
                    )

            receipt = ingest_change_event(
                session,
                request=event,
                # This is the important
                # project-specific part.
                agent_id=(agent.agent_id),
                auto_correlate=True,
                # Agent identity is authenticated. Source-native time
                # is still accepted only when its producer labeled it
                # available and supplied an aware value.
                source_time_trusted=True,
                observed_at=utc_now_iso(),
                # Commit the complete
                # batch atomically.
                commit=False,
                tenant_id=UNOWNED_MACHINE,
            )

            event_ids.append(
                receipt.event_id
            )

            if (
                receipt.created
                and is_topology_affecting_change_event(
                    event
                )
            ):
                topology_affecting_count += 1

        tenant_commit(session, tenant_id=UNOWNED_MACHINE)

    except ValueError as exc:
        session.rollback()

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception:
        session.rollback()
        raise

    return (
        AgentChangeEventBatchReceipt(
            received_count=len(
                request.events
            ),
            event_ids=event_ids,
            topology_affecting_count=(
                topology_affecting_count
            ),
            checkpoint_requested=(
                topology_affecting_count > 0
            ),
            checkpoint_reason=(
                TopologyCheckpointReason
                .AUTOMATIC_CHANGE.value
                if topology_affecting_count > 0
                else None
            ),
        )
    )


@agent_router.post(
    "/signals",
    response_model=FailureSignalBatchResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_failure_signals(
    request: FailureSignalBatchRequest,
    agent: TopoAgentRecord = Depends(require_agent),
    session: Session = Depends(get_session),
) -> FailureSignalBatchResult:
    namespace_scope = set(
        json.loads(agent.namespace_scope_json)
    )

    for signal in request.signals:
        if signal.cluster_name != agent.cluster_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Signal cluster name does not "
                    "match the enrolled agent."
                ),
            )

        if (
            namespace_scope
            and signal.namespace
            and signal.namespace
            not in namespace_scope
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Signal namespace is outside the "
                    "enrolled agent's discovery scope."
                ),
            )

    return ingest_failure_signal_batch(
        session=session,
        signals=request.signals,
        tenant_id=UNOWNED_MACHINE,
    )
