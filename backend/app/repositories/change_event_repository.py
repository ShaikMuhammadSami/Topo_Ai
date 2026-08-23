from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChangeEntityLinkRecord,
    ChangeEventRecord,
    SnapshotRecord,
    utc_now_iso,
)
from app.models.change_events import (
    ChangeCorrelationResponse,
    ChangeEntityLinkType,
    ChangeEntityLinkView,
    ChangeEventCreate,
    ChangeEventKind,
    ChangeEventReceipt,
    ChangeEventRiskLevel,
    ChangeEventView,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)
from app.models.temporal import TimeOrigin, TimeQuality
from app.models.canonical_identity import (
    CanonicalIdentityResolutionStatus,
    CanonicalIdentityResolutionStrategy,
)
from app.services.canonical_identity import (
    resolve_snapshot_entity_identity,
)
from app.services.temporal_semantics import (
    build_temporal_metadata,
    change_event_temporal,
    safe_snapshot_record_at_or_before,
)


def _digest(
    value: str,
    length: int = 40,
) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:length]


def _json_dict(
    value: str | None,
) -> dict[str, Any]:
    if not value:
        return {}

    try:
        parsed = json.loads(value)

    except json.JSONDecodeError:
        return {}

    return (
        parsed
        if isinstance(parsed, dict)
        else {}
    )


def risk_level(
    score: int,
) -> ChangeEventRiskLevel:
    if score >= 85:
        return (
            ChangeEventRiskLevel.CRITICAL
        )

    if score >= 65:
        return ChangeEventRiskLevel.HIGH

    if score >= 35:
        return ChangeEventRiskLevel.MEDIUM

    return ChangeEventRiskLevel.LOW


def score_change_event_risk(
    request: ChangeEventCreate,
) -> int:
    if request.risk_score is not None:
        return request.risk_score

    base_scores = {
        ChangeEventKind.CODE: 20,
        ChangeEventKind.PULL_REQUEST: 15,
        ChangeEventKind.PIPELINE: 20,
        ChangeEventKind.DEPLOYMENT: 50,
        ChangeEventKind.ROLLOUT: 55,
        ChangeEventKind.CONFIGURATION: 40,
        ChangeEventKind.INFRASTRUCTURE: 55,
        ChangeEventKind.SCALING: 30,
        ChangeEventKind.SECURITY: 70,
        ChangeEventKind.DATABASE: 70,
        ChangeEventKind.TOPOLOGY: 35,
        ChangeEventKind.UNKNOWN: 15,
    }

    score = base_scores.get(
        request.kind,
        15,
    )

    metadata = request.metadata

    if str(
        request.environment or ""
    ).lower() in {
        "prod",
        "production",
    }:
        score += 15

    if metadata.get("production"):
        score += 10

    if metadata.get("destructive"):
        score += 20

    if metadata.get(
        "database_migration"
    ):
        score += 15

    if metadata.get(
        "security_impact"
    ):
        score += 15

    changed_count = metadata.get(
        "changed_resource_count"
    )

    if isinstance(
        changed_count,
        int,
    ):
        score += min(
            changed_count,
            15,
        )

    return max(
        0,
        min(score, 100),
    )


def _event_fingerprint(
    request: ChangeEventCreate,
) -> str:
    # Provider/platform external IDs
    # should be the strongest
    # idempotency signal.
    if request.external_id:
        value = {
            "source":
                request.source.value,
            "external_id":
                request.external_id,
        }

    else:
        value = {
            "source":
                request.source.value,
            "kind":
                request.kind.value,
            "occurred_at":
                request.occurred_at,
            "title":
                request.title,
            "repository":
                request.repository,
            "commit_sha":
                request.commit_sha,
            "pipeline_name":
                request.pipeline_name,
            "release_version":
                request.release_version,
        }

    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _event_id(
    fingerprint: str,
) -> str:
    return (
        "change-event:"
        + _digest(
            fingerprint,
            32,
        )
    )


def _link_id(
    *,
    event_id: str,
    entity_id: str,
    link_type: str,
) -> str:
    return (
        "change-link:"
        + _digest(
            (
                f"{event_id}|"
                f"{entity_id}|"
                f"{link_type}"
            ),
            32,
        )
    )


def _upsert_link(
    session: Session,
    *,
    event_id: str,
    entity_id: str,
    link_type: ChangeEntityLinkType,
    confidence: float,
    reason: str,
    snapshot_id: str | None,
) -> ChangeEntityLinkRecord:
    link_id = _link_id(
        event_id=event_id,
        entity_id=entity_id,
        link_type=link_type.value,
    )

    # First check pending objects already
    # added during this transaction.
    #
    # session.get() alone is not enough
    # here because another identical link
    # may still be pending and not flushed.
    record = None

    for pending in session.new:
        if not isinstance(
            pending,
            ChangeEntityLinkRecord,
        ):
            continue

        if (
            pending.event_id == event_id
            and pending.entity_id == entity_id
            and pending.link_type
            == link_type.value
        ):
            record = pending
            break

    # If it is not pending, check the
    # persisted database row using the
    # actual composite uniqueness fields.
    if record is None:
        statement = (
            select(
                ChangeEntityLinkRecord
            )
            .where(
                ChangeEntityLinkRecord
                .event_id
                == event_id,

                ChangeEntityLinkRecord
                .entity_id
                == entity_id,

                ChangeEntityLinkRecord
                .link_type
                == link_type.value,
            )
            .limit(1)
        )

        # Do not flush other pending
        # objects just to perform this
        # duplicate check.
        with session.no_autoflush:
            record = session.scalar(
                statement
            )

    now = utc_now_iso()

    if record is None:
        record = ChangeEntityLinkRecord(
            link_id=link_id,
            event_id=event_id,
            entity_id=entity_id,
            link_type=(
                link_type.value
            ),
            confidence=confidence,
            reason=reason,
            snapshot_id=snapshot_id,
            created_at=now,
            updated_at=now,
        )

        session.add(record)

        return record

    # Existing/pending link:
    # keep the strongest confidence.
    if confidence > record.confidence:
        record.confidence = confidence
        record.reason = reason

    # A newer/more specific snapshot ID
    # can enrich the existing link.
    if (
        snapshot_id
        and not record.snapshot_id
    ):
        record.snapshot_id = snapshot_id

    record.updated_at = now

    return record

def _links(
    session: Session,
    *,
    event_id: str,
) -> list[
    ChangeEntityLinkRecord
]:
    statement = (
        select(
            ChangeEntityLinkRecord
        )
        .where(
            ChangeEntityLinkRecord
            .event_id
            == event_id
        )
        .order_by(
            ChangeEntityLinkRecord
            .confidence
            .desc()
        )
    )

    return list(
        session.scalars(
            statement
        ).all()
    )


def _link_view(
    record: ChangeEntityLinkRecord,
) -> ChangeEntityLinkView:
    return ChangeEntityLinkView(
        link_id=record.link_id,
        event_id=record.event_id,
        entity_id=record.entity_id,
        link_type=(
            ChangeEntityLinkType(
                record.link_type
            )
        ),
        confidence=record.confidence,
        reason=record.reason,
        snapshot_id=record.snapshot_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def change_event_view(
    session: Session,
    *,
    record: ChangeEventRecord,
) -> ChangeEventView:
    return ChangeEventView(
        event_id=record.event_id,
        event_fingerprint=(
            record.event_fingerprint
        ),
        source=record.source,
        kind=record.kind,
        external_id=record.external_id,
        origin_change_id=(
            record.origin_change_id
        ),
        title=record.title,
        summary=record.summary,
        actor=record.actor,
        occurred_at=record.occurred_at,
        received_at=record.received_at,
        temporal=change_event_temporal(record),
        environment=record.environment,
        provider=record.provider,
        account_id=record.account_id,
        region=record.region,
        cluster_name=(
            record.cluster_name
        ),
        namespace=record.namespace,
        repository=record.repository,
        commit_sha=record.commit_sha,
        pipeline_name=(
            record.pipeline_name
        ),
        release_version=(
            record.release_version
        ),
        terraform_workspace=(
            record.terraform_workspace
        ),
        risk_score=record.risk_score,
        risk_level=record.risk_level,
        status=record.status,
        observation_count=(
            record.observation_count
        ),
        metadata=_json_dict(
            record.metadata_json
        ),
        raw_payload=_json_dict(
            record.raw_payload_json
        ),
        agent_id=record.agent_id,
        links=[
            _link_view(link)
            for link in _links(
                session,
                event_id=record.event_id,
            )
        ],
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def load_change_event(
    session: Session,
    *,
    event_id: str,
) -> ChangeEventRecord | None:
    return session.get(
        ChangeEventRecord,
        event_id,
    )


def _entity_tokens(
    entity: Entity,
) -> set[str]:
    result = {
        entity.id.lower(),
        entity.name.lower(),
        entity.kind.lower(),
    }

    if entity.external_id:
        result.add(
            entity.external_id.lower()
        )

    for value in (
        entity.labels.values()
    ):
        text = str(
            value
        ).strip().lower()

        if text:
            result.add(text)

    interesting_keys = {
        "resource_id",
        "arn",
        "provider_id",
        "repository",
        "repo",
        "commit_sha",
        "image",
        "service",
        "application",
        "app",
        "namespace",
        "cluster_name",
    }

    for key, value in (
        entity.properties.items()
    ):
        if (
            key.lower()
            not in interesting_keys
        ):
            continue

        values = (
            value
            if isinstance(
                value,
                list,
            )
            else [value]
        )

        for item in values:
            text = str(
                item
            ).strip().lower()

            if text:
                result.add(text)

    return result


def correlate_change_event(
    session: Session,
    *,
    event_id: str,
    snapshot_id: str | None = None,
    commit: bool = True,
) -> ChangeCorrelationResponse:
    record = load_change_event(
        session,
        event_id=event_id,
    )

    if record is None:
        raise ValueError(
            "Change event not found."
        )

    metadata = _json_dict(
        record.metadata_json
    )

    snapshot_record = None

    # 1. Caller explicitly requested
    # a snapshot.
    if snapshot_id:
        snapshot_record = session.get(
            SnapshotRecord,
            snapshot_id,
        )

        if snapshot_record is None:
            raise ValueError(
                "Requested topology "
                "snapshot was not found."
            )

    # 2. Snapshot-derived events must
    # correlate against the snapshot
    # where the original change was
    # observed, never a future snapshot.
    elif (
        record.source
        == "topology_diff"
    ):
        origin_snapshot_id = (
            metadata.get(
                "to_snapshot_id"
            )
        )

        if origin_snapshot_id:
            snapshot_record = session.get(
                SnapshotRecord,
                str(
                    origin_snapshot_id
                ),
            )

    # 3. External operational events may use only a scope-compatible
    # checkpoint observed at or before their effective event time. A late
    # delivery must never link itself against an arbitrary future/latest
    # topology.
    else:
        if record.cluster_name:
            snapshot_record = safe_snapshot_record_at_or_before(
                session,
                cluster_name=record.cluster_name,
                namespace=record.namespace,
                boundary_at=(
                    change_event_temporal(record).effective_at
                ),
            )
    # Explicit links can exist even
    # without any snapshot.
    if snapshot_record is None:
        links = _links(
            session,
            event_id=event_id,
        )

        return ChangeCorrelationResponse(
            event_id=event_id,
            snapshot_id=None,
            linked_entity_count=(
                len(links)
            ),
            links=[
                _link_view(link)
                for link in links
            ],
        )

    snapshot = (
        GraphSnapshot
        .model_validate_json(
            snapshot_record.payload_json
        )
    )

    token_index: dict[
        str,
        list[Entity],
    ] = {}

    for entity in snapshot.entities:
        for token in _entity_tokens(
            entity
        ):
            token_index.setdefault(
                token,
                [],
            ).append(entity)

    # metadata = _json_dict(
    #     record.metadata_json
    # )

    refs = metadata.get(
        "entity_refs",
        [],
    )

    if not isinstance(refs, list):
        refs = []

    for ref in refs:
        if not isinstance(
            ref,
            dict,
        ):
            continue

        entity_id = ref.get("entity_id")
        native_id = (
            ref.get("external_id")
            or ref.get("provider_resource_id")
        )
        resolution = resolve_snapshot_entity_identity(
            snapshot,
            identifier=(
                str(entity_id)
                if entity_id
                else None
            ),
            source_native_id=(
                str(native_id)
                if native_id
                else None
            ),
            kind=(
                str(ref["kind"])
                if ref.get("kind")
                else None
            ),
            name=(
                str(ref["name"])
                if ref.get("name")
                else None
            ),
            cluster_name=(
                str(ref["cluster_name"])
                if ref.get("cluster_name")
                else record.cluster_name
            ),
            namespace=(
                str(ref["namespace"])
                if ref.get("namespace")
                else record.namespace
            ),
            account_id=record.account_id,
            project_id=(
                record.account_id
                if record.source == "gcp_audit_log"
                else None
            ),
            subscription_id=(
                record.account_id
                if record.source == "azure_activity_log"
                else None
            ),
        )

        if (
            resolution.status
            != CanonicalIdentityResolutionStatus.RESOLVED
            or not resolution.resolved_entity_id
        ):
            continue

        explicit = bool(entity_id)
        confidence_by_strategy = {
            CanonicalIdentityResolutionStrategy.CANONICAL_ID: 1.0,
            CanonicalIdentityResolutionStrategy.SOURCE_NATIVE_ID: 0.98,
            CanonicalIdentityResolutionStrategy.SCOPED_ALIAS: 0.97,
            CanonicalIdentityResolutionStrategy.SOURCE_FALLBACK: 0.95,
        }
        _upsert_link(
            session,
            event_id=event_id,
            entity_id=resolution.resolved_entity_id,
            link_type=(
                ChangeEntityLinkType.EXPLICIT
                if explicit
                else ChangeEntityLinkType.AUTOMATIC
            ),
            confidence=confidence_by_strategy.get(
                resolution.strategy,
                0.90,
            ),
            reason=(
                "Canonical identity resolution matched the event "
                f"reference by {resolution.strategy.value}."
            ),
            snapshot_id=snapshot.snapshot_id,
        )

    event_tokens = {
        str(value).strip().lower()
        for value in (
            record.repository,
            record.commit_sha,
            record.pipeline_name,
            record.release_version,
            metadata.get("service"),
            metadata.get(
                "application"
            ),
            metadata.get(
                "resource_id"
            ),
            metadata.get("image"),
        )
        if value
    }

    for token in event_tokens:
        for entity in (
            token_index.get(
                token,
                [],
            )
        ):
            _upsert_link(
                session,
                event_id=event_id,
                entity_id=entity.id,
                link_type=(
                    ChangeEntityLinkType
                    .DERIVED
                ),
                confidence=0.75,
                reason=(
                    "Event metadata matched "
                    "an entity property "
                    "or label."
                ),
                snapshot_id=(
                    snapshot.snapshot_id
                ),
            )

    if commit:
        session.commit()

    links = _links(
        session,
        event_id=event_id,
    )

    return ChangeCorrelationResponse(
        event_id=event_id,
        snapshot_id=snapshot.snapshot_id,
        linked_entity_count=len(
            links
        ),
        links=[
            _link_view(link)
            for link in links
        ],
    )


def ingest_change_event(
    session: Session,
    *,
    request: ChangeEventCreate,
    agent_id: str | None = None,
    auto_correlate: bool = True,
    correlation_snapshot_id:
        str | None = None,
    source_time_trusted: bool = False,
    observed_at: str | None = None,
    source_field: str | None = None,
    source_time_origin: TimeOrigin = TimeOrigin.SOURCE_REPORTED,
    source_time_quality: TimeQuality = TimeQuality.EXACT,
    commit: bool = True,
) -> ChangeEventReceipt:
    fingerprint = _event_fingerprint(
        request
    )

    existing = session.scalar(
        select(
            ChangeEventRecord
        ).where(
            ChangeEventRecord
            .event_fingerprint
            == fingerprint
        )
    )

    now = utc_now_iso()

    risk_score = (
        score_change_event_risk(
            request
        )
    )

    level = risk_level(
        risk_score
    )

    temporal_hint = request.metadata.get("_temporal", {})
    if not isinstance(temporal_hint, dict):
        temporal_hint = {}
    source_available = temporal_hint.get(
        "source_time_available",
        True,
    )
    trusted = bool(source_time_trusted and source_available)
    temporal = build_temporal_metadata(
        source_event_at=request.occurred_at,
        observed_at=observed_at or now,
        recorded_at=now,
        source_time_trusted=trusted,
        source_field=(
            source_field
            or temporal_hint.get("source_field")
            or "ChangeEventCreate.occurred_at"
        ),
        source_origin=source_time_origin,
        source_quality=source_time_quality,
    )
    metadata = {
        **{
            key: value
            for key, value in request.metadata.items()
            if key != "_temporal"
        },
        "entity_refs": [
            item.model_dump(
                mode="json"
            )
            for item in (
                request.entity_refs
            )
        ],
        "temporal": temporal.model_dump(mode="json"),
    }

    created = existing is None

    if existing is None:
        record = ChangeEventRecord(
            event_id=_event_id(
                fingerprint
            ),
            event_fingerprint=(
                fingerprint
            ),
            source=request.source.value,
            kind=request.kind.value,
            external_id=(
                request.external_id
            ),
            origin_change_id=(
                request.origin_change_id
            ),
            title=request.title,
            summary=request.summary,
            actor=request.actor,
            occurred_at=(
                temporal.effective_at.isoformat()
            ),
            received_at=(
                temporal.observed_at
                or temporal.recorded_at
                or temporal.effective_at
            ).isoformat(),
            environment=(
                request.environment
            ),
            provider=request.provider,
            account_id=(
                request.account_id
            ),
            region=request.region,
            cluster_name=(
                request.cluster_name
            ),
            namespace=(
                request.namespace
            ),
            repository=(
                request.repository
            ),
            commit_sha=(
                request.commit_sha
            ),
            pipeline_name=(
                request.pipeline_name
            ),
            release_version=(
                request.release_version
            ),
            terraform_workspace=(
                request
                .terraform_workspace
            ),
            risk_score=risk_score,
            risk_level=level.value,
            status=request.status,
            observation_count=1,
            metadata_json=json.dumps(
                metadata,
                default=str,
            ),
            raw_payload_json=(
                json.dumps(
                    request.raw_payload,
                    default=str,
                )
            ),
            agent_id=agent_id,
            created_at=now,
            updated_at=now,
        )

        session.add(record)
        session.flush()

    else:
        record = existing
        record.source = (
         request.source.value
        )

        record.kind = (
         request.kind.value
        )

        record.origin_change_id = (
          request.origin_change_id
          or record.origin_change_id
        )

        record.observation_count += 1

        record.updated_at = now

        if request.summary:
            record.summary = (
                request.summary
            )

        if (
            risk_score
            > record.risk_score
        ):
            record.risk_score = (
                risk_score
            )

            record.risk_level = (
                level.value
            )

        old_metadata = _json_dict(
            record.metadata_json
        )

        # A redelivery can add non-temporal context, but it must not replace
        # the original effective/observation/recorded interpretation with a
        # later backend receipt time.
        if "temporal" in old_metadata:
            metadata["temporal"] = old_metadata["temporal"]

        old_metadata.update(
            metadata
        )

        record.metadata_json = (
            json.dumps(
                old_metadata,
                default=str,
            )
        )

    # When a topology is available, defer explicit references to the
    # canonical resolver below. Without a topology, retain the historical
    # behavior of preserving the supplied reference as an explicit link.
    has_correlation_snapshot = bool(correlation_snapshot_id)
    if not has_correlation_snapshot and record.cluster_name:
        has_correlation_snapshot = bool(
            safe_snapshot_record_at_or_before(
                session,
                cluster_name=record.cluster_name,
                namespace=record.namespace,
                boundary_at=change_event_temporal(record).effective_at,
            )
        )

    for ref in request.entity_refs:
        if not ref.entity_id:
            continue

        if auto_correlate and has_correlation_snapshot:
            continue

        _upsert_link(
            session,
            event_id=record.event_id,
            entity_id=ref.entity_id,
            link_type=(
                ChangeEntityLinkType
                .EXPLICIT
            ),
            confidence=1.0,
            reason=(
                "Event explicitly "
                "referenced entity."
            ),
            snapshot_id=(
                correlation_snapshot_id
            ),
        )

    if auto_correlate:
        correlation = (
            correlate_change_event(
                session,
                event_id=record.event_id,
                snapshot_id=(
                    correlation_snapshot_id
                ),
                commit=False,
            )
        )

        linked_count = (
            correlation
            .linked_entity_count
        )

    else:
        linked_count = len(
            _links(
                session,
                event_id=record.event_id,
            )
        )

    if commit:
        session.commit()

    return ChangeEventReceipt(
        event_id=record.event_id,
        created=created,
        duplicate=not created,
        risk_score=(
            record.risk_score
        ),
        risk_level=(
            ChangeEventRiskLevel(
                record.risk_level
            )
        ),
        linked_entity_count=(
            linked_count
        ),
    )


def list_change_events(
    session: Session,
    *,
    source: str | None = None,
    kind: str | None = None,
    environment: str | None = None,
    cluster_name: str | None = None,
    namespace: str | None = None,
    minimum_risk_score: int = 0,
    occurred_after: str | None = None,
    occurred_before: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ChangeEventView]:
    statement = select(
        ChangeEventRecord
    )

    if source:
        statement = statement.where(
            ChangeEventRecord.source
            == source
        )

    if kind:
        statement = statement.where(
            ChangeEventRecord.kind
            == kind
        )

    if environment:
        statement = statement.where(
            ChangeEventRecord.environment
            == environment
        )

    if cluster_name:
        statement = statement.where(
            ChangeEventRecord.cluster_name
            == cluster_name
        )

    if namespace:
        statement = statement.where(
            ChangeEventRecord.namespace
            == namespace
        )

    statement = statement.where(
        ChangeEventRecord.risk_score
        >= minimum_risk_score
    )

    if occurred_after:
        statement = statement.where(
            ChangeEventRecord.occurred_at
            >= occurred_after
        )

    if occurred_before:
        statement = statement.where(
            ChangeEventRecord.occurred_at
            <= occurred_before
        )

    statement = (
        statement
        .order_by(
            ChangeEventRecord
            .occurred_at
            .desc()
        )
        .offset(offset)
        .limit(limit)
    )

    return [
        change_event_view(
            session,
            record=record,
        )
        for record in session.scalars(
            statement
        ).all()
    ]
