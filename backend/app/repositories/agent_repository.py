from __future__ import annotations

import hashlib
import json
import secrets
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.repositories.tenant_scope import (
    DomainTenant, tenant_value, tenant_predicate, tenant_get, tenant_commit,
    require_record_owner,
)
from app.security.machine_tenant import machine_tenant_is_active

from app.db.models import (
    AgentEnrollmentTokenRecord,
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
    AgentStatus,
    AgentSummary,
    AgentPluginStatusView,
    AgentPluginsResponse,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def _token_hash(
    token: str,
) -> str:
    return hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()


def _token_hint(
    token: str,
) -> str:
    if len(token) <= 12:
        return token

    return (
        token[:8]
        + "..."
        + token[-4:]
    )


class AgentEnrollmentRejected(ValueError):
    """Credential-safe enrollment rejection with an internal reason."""

    public_message = (
        "The enrollment credential is invalid or unavailable."
    )

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(self.public_message)


def _effective_status(
    record: TopoAgentRecord,
) -> AgentStatus:
    if record.revoked_at:
        return AgentStatus.REVOKED

    heartbeat = _parse_datetime(
        record.last_heartbeat_at
    )

    if heartbeat is None:
        return AgentStatus.ENROLLED

    offline_after = max(
        record.heartbeat_interval_seconds * 3,
        90,
    )

    age_seconds = (
        _now() - heartbeat
    ).total_seconds()

    if age_seconds > offline_after:
        return AgentStatus.OFFLINE

    return AgentStatus.ONLINE


def _config_view(
    record: TopoAgentRecord,
) -> AgentConfigView:
    return AgentConfigView(
        collection_interval_seconds=(
            record.collection_interval_seconds
        ),
        heartbeat_interval_seconds=(
            record.heartbeat_interval_seconds
        ),
        namespace_scope=json.loads(
            record.namespace_scope_json
        ),
    )


def _to_summary(
    record: TopoAgentRecord,
) -> AgentSummary:
    return AgentSummary(
        agent_id=record.agent_id,
        name=record.name,
        agent_type=record.agent_type,
        cluster_name=record.cluster_name,
        environment=record.environment,
        version=record.version,
        status=_effective_status(record),
        collection_interval_seconds=(
            record.collection_interval_seconds
        ),
        heartbeat_interval_seconds=(
            record.heartbeat_interval_seconds
        ),
        namespace_scope=json.loads(
            record.namespace_scope_json
        ),
        buffered_item_count=(
            record.buffered_item_count
        ),
        last_collection_status=(
            record.last_collection_status
        ),
        last_error=record.last_error,
        last_seen_at=record.last_seen_at,
        last_heartbeat_at=(
            record.last_heartbeat_at
        ),
        last_snapshot_at=(
            record.last_snapshot_at
        ),
        enrolled_at=record.enrolled_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_detail(
    record: TopoAgentRecord,
) -> AgentDetail:
    summary = _to_summary(record)

    return AgentDetail(
        **summary.model_dump(),
        capabilities=json.loads(
            record.capabilities_json
        ),
        labels=json.loads(
            record.labels_json
        ),
        metadata=json.loads(
            record.metadata_json
        ),
    )


def create_enrollment_token(
    session: Session,
    *,
    request:
        AgentEnrollmentTokenCreateRequest,
    created_by: str | None,
    tenant_id: DomainTenant,
) -> AgentEnrollmentTokenResponse:
    raw_token = (
        "topo_enroll_"
        + secrets.token_urlsafe(32)
    )

    now = _now()

    record = AgentEnrollmentTokenRecord(
        tenant_id=tenant_value(tenant_id),
        enrollment_token_id=(
            "agent-enrollment:"
            + uuid4().hex
        ),
        token_hash=_token_hash(
            raw_token
        ),
        token_hint=_token_hint(
            raw_token
        ),
        label=request.label,
        max_uses=request.max_uses,
        use_count=0,
        expires_at=(
            now
            + timedelta(
                minutes=(
                    request
                    .expires_in_minutes
                )
            )
        ).isoformat(),
        last_used_at=None,
        revoked_at=None,
        created_by=created_by,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )

    session.add(record)
    tenant_commit(session, tenant_id=tenant_id)

    return AgentEnrollmentTokenResponse(
        enrollment_token_id=(
            record.enrollment_token_id
        ),
        enrollment_token=raw_token,
        token_hint=record.token_hint,
        label=record.label,
        max_uses=record.max_uses,
        expires_at=record.expires_at,
        created_at=record.created_at,
    )


def enroll_agent(
    session: Session,
    *,
    request: AgentEnrollRequest,
) -> AgentEnrollResponse:
    digest = _token_hash(
        request.enrollment_token
    )
    # MACHINE_AUTH_DERIVATION_LOOKUP: exact credential digest only.
    observed = session.execute(
        select(
            AgentEnrollmentTokenRecord.expires_at,
            AgentEnrollmentTokenRecord.revoked_at,
            AgentEnrollmentTokenRecord.use_count,
            AgentEnrollmentTokenRecord.max_uses,
            AgentEnrollmentTokenRecord.tenant_id,
        ).where(
            AgentEnrollmentTokenRecord.token_hash == digest
        )
    ).one_or_none()

    if observed is None:
        session.rollback()
        raise AgentEnrollmentRejected("unknown")

    if not machine_tenant_is_active(session, tenant_id=observed.tenant_id):
        session.rollback()
        raise AgentEnrollmentRejected("tenant_unavailable")

    expires_at = _parse_datetime(observed.expires_at)
    consumption_time = _now()
    consumption_time_iso = consumption_time.isoformat()

    if observed.revoked_at:
        session.rollback()
        raise AgentEnrollmentRejected("revoked")
    if expires_at is None or expires_at <= consumption_time:
        session.rollback()
        raise AgentEnrollmentRejected("expired")
    if observed.use_count >= observed.max_uses:
        session.rollback()
        raise AgentEnrollmentRejected("fully_used")

    try:
        consumption = session.execute(
            update(AgentEnrollmentTokenRecord)
            .where(
                AgentEnrollmentTokenRecord.token_hash == digest,
                tenant_predicate(AgentEnrollmentTokenRecord, observed.tenant_id),
                AgentEnrollmentTokenRecord.revoked_at.is_(None),
                AgentEnrollmentTokenRecord.expires_at > consumption_time_iso,
                AgentEnrollmentTokenRecord.use_count
                < AgentEnrollmentTokenRecord.max_uses,
            )
            .values(
                use_count=AgentEnrollmentTokenRecord.use_count + 1,
                last_used_at=consumption_time_iso,
                updated_at=consumption_time_iso,
            )
            .execution_options(synchronize_session=False)
        )

        if consumption.rowcount != 1:
            raise AgentEnrollmentRejected("concurrent_or_unavailable")

        raw_agent_token = "topo_agent_" + secrets.token_urlsafe(40)
        record = TopoAgentRecord(
            agent_id="agent:" + uuid4().hex,
            tenant_id=observed.tenant_id,
            name=request.name,
            agent_type=request.agent_type,
            cluster_name=request.cluster_name,
            environment=request.environment,
            version=request.version,
            token_hash=_token_hash(raw_agent_token),
            token_hint=_token_hint(raw_agent_token),
            status=AgentStatus.ENROLLED.value,
            collection_interval_seconds=request.collection_interval_seconds,
            heartbeat_interval_seconds=request.heartbeat_interval_seconds,
            namespace_scope_json=json.dumps(request.namespace_scope),
            capabilities_json=json.dumps(request.capabilities),
            labels_json=json.dumps(request.labels),
            metadata_json=json.dumps(request.metadata),
            buffered_item_count=0,
            last_collection_status=None,
            last_error=None,
            last_seen_at=None,
            last_heartbeat_at=None,
            last_snapshot_at=None,
            enrolled_at=consumption_time_iso,
            revoked_at=None,
            created_at=consumption_time_iso,
            updated_at=consumption_time_iso,
        )
        session.add(record)
        tenant_commit(session, tenant_id=observed.tenant_id)
    except Exception:
        session.rollback()
        raise

    return AgentEnrollResponse(
        agent_id=record.agent_id,
        agent_token=raw_agent_token,
        enrolled_at=record.enrolled_at,
        config=_config_view(record),
    )


def authenticate_agent(
    session: Session,
    *,
    token: str,
) -> TopoAgentRecord | None:
    digest = _token_hash(token)

    # MACHINE_AUTH_DERIVATION_LOOKUP: exact credential digest only.
    statement = select(
        TopoAgentRecord
    ).where(
        TopoAgentRecord.token_hash
        == digest
    )

    record = session.scalars(
        statement
    ).first()

    if (
        record is None
        or record.revoked_at
        or not machine_tenant_is_active(session, tenant_id=record.tenant_id)
    ):
        return None

    return record


def list_agents(
    session: Session,
    *,
    limit: int = 100,
    offset: int = 0,
    tenant_id: DomainTenant,
) -> list[AgentSummary]:
    statement = (
        select(TopoAgentRecord)
        .where(tenant_predicate(TopoAgentRecord, tenant_id))
        .order_by(
            TopoAgentRecord
            .created_at
            .desc()
        )
        .offset(offset)
        .limit(limit)
    )

    return [
        _to_summary(record)
        for record in session.scalars(
            statement
        ).all()
    ]


def load_agent(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> AgentDetail | None:
    record = tenant_get(
        session, TopoAgentRecord, agent_id, tenant_id=tenant_id,
    )

    if record is None:
        return None

    return _to_detail(record)


def load_agent_record(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> TopoAgentRecord | None:
    return tenant_get(
        session, TopoAgentRecord, agent_id, tenant_id=tenant_id,
    )


def record_heartbeat(
    session: Session,
    *,
    record: TopoAgentRecord,
    request: AgentHeartbeatRequest,
    tenant_id: DomainTenant,
) -> AgentHeartbeatResponse:
    require_record_owner(record, tenant_id=tenant_id)
    now = utc_now_iso()

    record.status = (
        AgentStatus.ONLINE.value
    )

    record.last_seen_at = now
    record.last_heartbeat_at = now

    record.buffered_item_count = (
        request.buffered_item_count
    )

    record.last_collection_status = (
        request.last_collection_status
    )

    record.last_error = request.last_error

    if request.version:
        record.version = request.version

    if request.capabilities:
        record.capabilities_json = (
            json.dumps(
                request.capabilities
            )
        )

    if request.metadata:
        existing = json.loads(
            record.metadata_json
        )

        existing.update(
            request.metadata
        )

        record.metadata_json = (
            json.dumps(existing)
        )

    record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)

    return AgentHeartbeatResponse(
        agent_id=record.agent_id,
        status=AgentStatus.ONLINE,
        received_at=now,
        config=_config_view(record),
    )


def record_snapshot_success(
    session: Session,
    *,
    record: TopoAgentRecord,
    tenant_id: DomainTenant,
) -> None:
    require_record_owner(record, tenant_id=tenant_id)
    now = utc_now_iso()

    record.status = (
        AgentStatus.ONLINE.value
    )

    record.last_seen_at = now
    record.last_snapshot_at = now
    record.last_collection_status = (
        "success"
    )
    record.last_error = None
    record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)


def revoke_agent(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> AgentDetail | None:
    record = tenant_get(
        session, TopoAgentRecord, agent_id, tenant_id=tenant_id,
    )

    if record is None:
        return None

    now = utc_now_iso()

    record.status = (
        AgentStatus.REVOKED.value
    )
    record.revoked_at = now
    record.updated_at = now

    tenant_commit(session, tenant_id=tenant_id)

    return _to_detail(record)


def agent_health(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> AgentHealthResponse | None:
    record = tenant_get(
        session, TopoAgentRecord, agent_id, tenant_id=tenant_id,
    )

    if record is None:
        return None

    return AgentHealthResponse(
        agent_id=record.agent_id,
        status=_effective_status(record),
        last_heartbeat_at=(
            record.last_heartbeat_at
        ),
        last_snapshot_at=(
            record.last_snapshot_at
        ),
        buffered_item_count=(
            record.buffered_item_count
        ),
        last_collection_status=(
            record.last_collection_status
        ),
        last_error=record.last_error,
        heartbeat_interval_seconds=(
            record.heartbeat_interval_seconds
        ),
    )

def agent_plugins(
    session: Session,
    *,
    agent_id: str,
    tenant_id: DomainTenant,
) -> AgentPluginsResponse | None:
    record = tenant_get(
        session, TopoAgentRecord, agent_id, tenant_id=tenant_id,
    )

    if record is None:
        return None

    metadata = json.loads(
        record.metadata_json
    )

    raw_plugins = metadata.get(
        "plugins",
        [],
    )

    enabled_plugins = metadata.get(
        "enabled_plugins",
        [],
    )

    plugins: list[
        AgentPluginStatusView
    ] = []

    if isinstance(
        raw_plugins,
        list,
    ):
        for item in raw_plugins:
            if not isinstance(
                item,
                dict,
            ):
                continue

            try:
                plugins.append(
                    AgentPluginStatusView
                    .model_validate(
                        item
                    )
                )

            except Exception:
                continue

    return AgentPluginsResponse(
        agent_id=record.agent_id,
        enabled_plugins=[
            str(item)
            for item in (
                enabled_plugins
                if isinstance(
                    enabled_plugins,
                    list,
                )
                else []
            )
        ],
        plugins=plugins,
        updated_at=record.updated_at,
    )
