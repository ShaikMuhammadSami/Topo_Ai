from __future__ import annotations
from app.repositories.tenant_scope import require_record_owner
from app.repositories.tenant_scope import (
    tenant_commit,
    DomainTenant,
    tenant_value,
    tenant_predicate,
    tenant_get,
)

import hashlib
import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from sqlalchemy import select
from sqlalchemy.orm import Session
from app.security.authorization_enforcement import authorize_service_operation

from app.db.models import (
    RuntimeDependencyRecord,
    RuntimeProcessRecord,
    RuntimeSensorRecord,
    TopoAgentRecord,
    utc_now_iso,
)
from app.models.runtime_observability import (
    RuntimeDependencyObservation,
    RuntimeDependencyView,
    RuntimeEventBatchReceipt,
    RuntimeEventBatchRequest,
    RuntimeProcessObservation,
    RuntimeSensorHeartbeatRequest,
    RuntimeSensorHeartbeatResponse,
    RuntimeSensorStatus,
    RuntimeSensorView,
)
from app.models.temporal import TimeOrigin
from app.services.temporal_semantics import build_temporal_metadata


def _digest(
    value: str,
    length: int = 32,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    try:
        result = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result


def _sensor_status(
    record: RuntimeSensorRecord,
) -> RuntimeSensorStatus:
    heartbeat = _parse_datetime(
        record.last_heartbeat_at
    )

    if heartbeat is None:
        return RuntimeSensorStatus.ENROLLED

    maximum_age = max(
        record.heartbeat_interval_seconds
        * 3,
        90,
    )

    age = (
        datetime.now(timezone.utc)
        - heartbeat
    ).total_seconds()

    if age > maximum_age:
        return RuntimeSensorStatus.OFFLINE

    if record.last_error:
        return RuntimeSensorStatus.ERROR

    return RuntimeSensorStatus.ONLINE


def _sensor_view(
    record: RuntimeSensorRecord,
) -> RuntimeSensorView:
    return RuntimeSensorView(
        sensor_id=record.sensor_id,
        agent_id=record.agent_id,
        node_name=record.node_name,
        cluster_name=record.cluster_name,
        source=record.source,
        version=record.version,
        status=_sensor_status(record),
        heartbeat_interval_seconds=(
            record.heartbeat_interval_seconds
        ),
        processed_event_count=(
            record.processed_event_count
        ),
        dropped_event_count=(
            record.dropped_event_count
        ),
        parser_error_count=(
            record.parser_error_count
        ),
        buffered_batch_count=(
            record.buffered_batch_count
        ),
        submitted_batch_count=(
            record.submitted_batch_count
        ),
        source_file=record.source_file,
        source_file_offset=(
            record.source_file_offset
        ),
        last_error=record.last_error,
        capabilities=json.loads(
            record.capabilities_json
        ),
        metadata=json.loads(
            record.metadata_json
        ),
        last_seen_at=record.last_seen_at,
        last_heartbeat_at=(
            record.last_heartbeat_at
        ),
        last_batch_at=record.last_batch_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _dependency_id(
    *,
    agent_id: str,
    node_name: str,
    observation:
        RuntimeDependencyObservation,
) -> str:
    source = observation.source
    destination = observation.destination

    identity = "|".join(
        [
            agent_id,
            node_name,
            source.namespace or "",
            source.pod_uid or "",
            source.pod_name or "",
            source.container_id or "",
            source.binary or "",
            destination.name or "",
            destination.address,
            str(destination.port),
            observation.protocol.lower(),
            observation.direction.lower(),
        ]
    )

    return (
        "runtime-dependency:"
        + _digest(identity)
    )


def _process_id(
    *,
    agent_id: str,
    node_name: str,
    observation:
        RuntimeProcessObservation,
) -> str:
    identity = "|".join(
        [
            agent_id,
            node_name,
            observation.exec_id or "",
            observation.container_id or "",
            str(observation.pid or ""),
            observation.binary,
            observation.first_seen_at,
        ]
    )

    return (
        "runtime-process:"
        + _digest(identity)
    )


def _touch_sensor(
    session: Session,
    *,
    agent: TopoAgentRecord,
    sensor_id: str,
    node_name: str,
    cluster_name: str,
    source: str,
    version: str,
    heartbeat_interval_seconds: int,
    processed_event_count: int,
    dropped_event_count: int,
    parser_error_count: int,
    buffered_batch_count: int,
    source_file: str | None,
    source_file_offset: int,
    last_error: str | None,
    capabilities: list[str],
    metadata: dict,
    heartbeat: bool,
    batch: bool,
    tenant_id: DomainTenant,
) -> RuntimeSensorRecord:
    require_record_owner(agent, tenant_id=tenant_id)
    now = utc_now_iso()

    record = tenant_get(
        session,
        RuntimeSensorRecord,
        sensor_id,
        tenant_id=tenant_id,
    )

    if record is None:
        record = RuntimeSensorRecord(
            sensor_id=sensor_id,
            agent_id=agent.agent_id,
            node_name=node_name,
            cluster_name=cluster_name,
            source=source,
            version=version,
            status=(RuntimeSensorStatus.ONLINE.value),
            heartbeat_interval_seconds=(heartbeat_interval_seconds),
            processed_event_count=(processed_event_count),
            dropped_event_count=(dropped_event_count),
            parser_error_count=(parser_error_count),
            buffered_batch_count=(buffered_batch_count),
            submitted_batch_count=(1 if batch else 0),
            source_file=source_file,
            source_file_offset=(source_file_offset),
            last_error=last_error,
            capabilities_json=json.dumps(capabilities),
            metadata_json=json.dumps(metadata),
            last_seen_at=now,
            last_heartbeat_at=(now if heartbeat else None),
            last_batch_at=(now if batch else None),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)

        return record

    if record.agent_id != agent.agent_id:
        raise ValueError(
            "Sensor ID belongs to another "
            "Topo Agent."
        )

    record.node_name = node_name
    record.cluster_name = cluster_name
    record.source = source
    record.version = version
    record.status = (
        RuntimeSensorStatus.ONLINE.value
    )

    record.heartbeat_interval_seconds = (
        heartbeat_interval_seconds
    )

    record.processed_event_count = (
        processed_event_count
    )
    record.dropped_event_count = (
        dropped_event_count
    )
    record.parser_error_count = (
        parser_error_count
    )
    record.buffered_batch_count = (
        buffered_batch_count
    )

    if batch:
        record.submitted_batch_count += 1
        record.last_batch_at = now

    if heartbeat:
        record.last_heartbeat_at = now

    record.source_file = source_file
    record.source_file_offset = (
        source_file_offset
    )
    record.last_error = last_error

    if capabilities:
        record.capabilities_json = (
            json.dumps(capabilities)
        )

    if metadata:
        existing = json.loads(
            record.metadata_json
        )
        existing.update(metadata)
        record.metadata_json = (
            json.dumps(existing)
        )

    record.last_seen_at = now
    record.updated_at = now

    return record


def record_sensor_heartbeat(
    session: Session,
    *,
    agent: TopoAgentRecord,
    request: RuntimeSensorHeartbeatRequest,
    tenant_id: DomainTenant,
    authorization_context=None,
) -> RuntimeSensorHeartbeatResponse:
    authorize_service_operation(
        "app.repositories.runtime_observability_repository.record_sensor_heartbeat",
        authorization_context=authorization_context,
    )
    _touch_sensor(
        session=session,
        agent=agent,
        sensor_id=request.sensor_id,
        node_name=request.node_name,
        cluster_name=request.cluster_name,
        source=request.source,
        version=request.version,
        heartbeat_interval_seconds=(request.heartbeat_interval_seconds),
        processed_event_count=(request.processed_event_count),
        dropped_event_count=(request.dropped_event_count),
        parser_error_count=(request.parser_error_count),
        buffered_batch_count=(request.buffered_batch_count),
        source_file=request.source_file,
        source_file_offset=(request.source_file_offset),
        last_error=request.last_error,
        capabilities=(request.capabilities),
        metadata=request.metadata,
        heartbeat=True,
        batch=False,
        tenant_id=tenant_id,
    )

    tenant_commit(session, tenant_id=tenant_id)

    return RuntimeSensorHeartbeatResponse(
        sensor_id=request.sensor_id,
        agent_id=agent.agent_id,
        status=RuntimeSensorStatus.ONLINE,
        received_at=utc_now_iso(),
    )


def _upsert_dependency(
    session: Session,
    *,
    agent: TopoAgentRecord,
    sensor_id: str,
    node_name: str,
    cluster_name: str,
    observation: RuntimeDependencyObservation,
    tenant_id: DomainTenant,
) -> None:
    dependency_id = _dependency_id(
        agent_id=agent.agent_id,
        node_name=node_name,
        observation=observation,
    )

    record = tenant_get(
        session,
        RuntimeDependencyRecord,
        dependency_id,
        tenant_id=tenant_id,
    )

    now = utc_now_iso()

    if record is None:
        metadata = dict(observation.metadata)
        metadata["temporal"] = build_temporal_metadata(
            source_event_at=observation.first_seen_at,
            observed_at=observation.first_seen_at,
            recorded_at=now,
            source_time_trusted=True,
            source_field="RuntimeDependencyObservation.first_seen_at",
            source_origin=TimeOrigin.RUNTIME_OBSERVED,
        ).model_dump(mode="json")
        record = RuntimeDependencyRecord(
            runtime_dependency_id=(dependency_id),
            agent_id=agent.agent_id,
            sensor_id=sensor_id,
            cluster_name=cluster_name,
            node_name=node_name,
            source_namespace=(observation.source.namespace),
            source_pod_name=(observation.source.pod_name),
            source_pod_uid=(observation.source.pod_uid),
            source_workload_name=(observation.source.workload_name),
            source_container_id=(observation.source.container_id),
            source_binary=(observation.source.binary),
            source_pid=(observation.source.pid),
            destination_name=(observation.destination.name),
            destination_address=(observation.destination.address),
            destination_port=(observation.destination.port),
            protocol=(observation.protocol.lower()),
            direction=(observation.direction.lower()),
            observation_count=(observation.observation_count),
            success_count=(observation.success_count),
            failure_count=(observation.failure_count),
            first_seen_at=(observation.first_seen_at),
            last_seen_at=(observation.last_seen_at),
            metadata_json=json.dumps(metadata),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)
        return

    record.sensor_id = sensor_id

    record.observation_count += (
        observation.observation_count
    )
    record.success_count += (
        observation.success_count
    )
    record.failure_count += (
        observation.failure_count
    )

    if (
        observation.first_seen_at
        < record.first_seen_at
    ):
        record.first_seen_at = (
            observation.first_seen_at
        )

    if (
        observation.last_seen_at
        > record.last_seen_at
    ):
        record.last_seen_at = (
            observation.last_seen_at
        )

    metadata = json.loads(
        record.metadata_json
    )
    metadata.update(
        observation.metadata
    )
    record.metadata_json = (
        json.dumps(metadata)
    )

    record.updated_at = now


def _upsert_process(
    session: Session,
    *,
    agent: TopoAgentRecord,
    sensor_id: str,
    node_name: str,
    cluster_name: str,
    observation: RuntimeProcessObservation,
    tenant_id: DomainTenant,
) -> None:
    process_id = _process_id(
        agent_id=agent.agent_id,
        node_name=node_name,
        observation=observation,
    )

    record = tenant_get(
        session,
        RuntimeProcessRecord,
        process_id,
        tenant_id=tenant_id,
    )

    now = utc_now_iso()

    if record is None:
        metadata = dict(observation.metadata)
        metadata["temporal"] = build_temporal_metadata(
            source_event_at=observation.first_seen_at,
            observed_at=observation.first_seen_at,
            recorded_at=now,
            source_time_trusted=True,
            source_field="RuntimeProcessObservation.first_seen_at",
            source_origin=TimeOrigin.RUNTIME_OBSERVED,
        ).model_dump(mode="json")
        record = RuntimeProcessRecord(
            runtime_process_id=process_id,
            agent_id=agent.agent_id,
            sensor_id=sensor_id,
            cluster_name=cluster_name,
            node_name=node_name,
            exec_id=observation.exec_id,
            pid=observation.pid,
            binary=observation.binary,
            namespace=(observation.namespace),
            pod_name=(observation.pod_name),
            pod_uid=(observation.pod_uid),
            container_id=(observation.container_id),
            parent_exec_id=(observation.parent_exec_id),
            exec_count=(observation.exec_count),
            exit_count=(observation.exit_count),
            last_exit_code=(observation.last_exit_code),
            last_signal=(observation.last_signal),
            first_seen_at=(observation.first_seen_at),
            last_seen_at=(observation.last_seen_at),
            metadata_json=json.dumps(metadata),
            created_at=now,
            updated_at=now,
            tenant_id=tenant_value(tenant_id),
        )

        session.add(record)
        return

    record.exec_count += (
        observation.exec_count
    )
    record.exit_count += (
        observation.exit_count
    )

    record.last_exit_code = (
        observation.last_exit_code
        if observation.last_exit_code
        is not None
        else record.last_exit_code
    )

    record.last_signal = (
        observation.last_signal
        or record.last_signal
    )

    if (
        observation.last_seen_at
        > record.last_seen_at
    ):
        record.last_seen_at = (
            observation.last_seen_at
        )

    record.updated_at = now


def ingest_runtime_event_batch(
    session: Session,
    *,
    agent: TopoAgentRecord,
    request: RuntimeEventBatchRequest,
    tenant_id: DomainTenant,
    authorization_context=None,
) -> RuntimeEventBatchReceipt:
    authorize_service_operation(
        "app.repositories.runtime_observability_repository.ingest_runtime_event_batch",
        authorization_context=authorization_context,
    )
    if (
        request.cluster_name
        != agent.cluster_name
    ):
        raise ValueError(
            "Runtime batch cluster does not "
            "match the enrolled agent."
        )

    _touch_sensor(
        session=session,
        agent=agent,
        sensor_id=request.sensor_id,
        node_name=request.node_name,
        cluster_name=request.cluster_name,
        source=request.source,
        version=request.version,
        heartbeat_interval_seconds=(
            int(
                request.metadata.get(
                    "heartbeat_interval_seconds",
                    30,
                )
            )
        ),
        processed_event_count=(request.processed_event_count),
        dropped_event_count=(request.dropped_event_count),
        parser_error_count=(request.parser_error_count),
        buffered_batch_count=(request.buffered_batch_count),
        source_file=request.source_file,
        source_file_offset=(request.source_file_offset),
        last_error=None,
        capabilities=[
            "ebpf.process.lifecycle",
            "ebpf.network.connect",
            "ebpf.network.accept",
            "ebpf.dns.resolver",
        ],
        metadata=request.metadata,
        heartbeat=False,
        batch=True,
        tenant_id=tenant_id,
    )

    for observation in request.dependencies:
        _upsert_dependency(
            session=session,
            agent=agent,
            sensor_id=request.sensor_id,
            node_name=request.node_name,
            cluster_name=(request.cluster_name),
            observation=observation,
            tenant_id=tenant_id,
        )

    for observation in request.processes:
        _upsert_process(
            session=session,
            agent=agent,
            sensor_id=request.sensor_id,
            node_name=request.node_name,
            cluster_name=(request.cluster_name),
            observation=observation,
            tenant_id=tenant_id,
        )

    tenant_commit(session, tenant_id=tenant_id)

    return RuntimeEventBatchReceipt(
        batch_id=request.batch_id,
        sensor_id=request.sensor_id,
        agent_id=agent.agent_id,
        accepted_at=utc_now_iso(),
        dependency_count=len(
            request.dependencies
        ),
        process_count=len(
            request.processes
        ),
    )


def list_runtime_sensors(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> list[RuntimeSensorView]:
    statement = (
        select(RuntimeSensorRecord)
        .where(tenant_predicate(RuntimeSensorRecord, tenant_id))
        .where(RuntimeSensorRecord.agent_id == agent_id)
        .order_by(RuntimeSensorRecord.node_name.asc())
    )

    return [
        _sensor_view(record)
        for record in session.scalars(
            statement
        ).all()
    ]


def _dependency_view(
    record: RuntimeDependencyRecord,
) -> RuntimeDependencyView:
    return RuntimeDependencyView(
        runtime_dependency_id=(
            record.runtime_dependency_id
        ),
        agent_id=record.agent_id,
        sensor_id=record.sensor_id,
        cluster_name=(
            record.cluster_name
        ),
        node_name=record.node_name,
        source_namespace=(
            record.source_namespace
        ),
        source_pod_name=(
            record.source_pod_name
        ),
        source_pod_uid=(
            record.source_pod_uid
        ),
        source_workload_name=(
            record.source_workload_name
        ),
        source_container_id=(
            record.source_container_id
        ),
        source_binary=(
            record.source_binary
        ),
        source_pid=record.source_pid,
        destination_name=(
            record.destination_name
        ),
        destination_address=(
            record.destination_address
        ),
        destination_port=(
            record.destination_port
        ),
        protocol=record.protocol,
        direction=record.direction,
        observation_count=(
            record.observation_count
        ),
        success_count=(
            record.success_count
        ),
        failure_count=(
            record.failure_count
        ),
        first_seen_at=(
            record.first_seen_at
        ),
        last_seen_at=record.last_seen_at,
        metadata=json.loads(
            record.metadata_json
        ),
    )


def list_runtime_dependencies(
    session: Session,
    *,
    agent_id: str,
    window_minutes: int = 15,
    limit: int = 1000,
    offset: int = 0,
    tenant_id: DomainTenant,
) -> list[RuntimeDependencyView]:
    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            minutes=window_minutes
        )
    ).isoformat()

    statement = (
        select(RuntimeDependencyRecord)
        .where(tenant_predicate(RuntimeDependencyRecord, tenant_id))
        .where(
            RuntimeDependencyRecord.agent_id == agent_id,
            RuntimeDependencyRecord.last_seen_at >= cutoff,
        )
        .order_by(RuntimeDependencyRecord.last_seen_at.desc())
        .offset(offset)
        .limit(limit)
    )

    return [
        _dependency_view(record)
        for record in session.scalars(
            statement
        ).all()
    ]
