from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.causal_rca import (
    CausalAnalysisResponse,
    CausalHypothesis,
)
from app.models.change_events import (
    ChangeEventView,
)
from app.models.incident_context import (
    IncidentOperationalContext,
)
from app.models.ownership import (
    BusinessImpactLevel,
    IncidentOwnershipImpact,
    ServiceCriticality,
)
from app.models.recommendations import (
    RecommendationRisk,
)
from app.models.response_plan import (
    IncidentResponseAction,
    IncidentResponsePlan,
    ResponseActionCategory,
    ResponsePriority,
    ResponseRootCause,
    RollbackCandidate,
    RunbookReference,
)
from app.models.topology import (
    Entity,
    GraphSnapshot,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
)
from app.repositories.change_event_repository import (
    change_event_view,
    load_change_event,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.incident_context import (
    build_incident_operational_context,
)


STRONG_CAUSAL_CONFIDENCE = 0.75


@dataclass(frozen=True)
class _EventContext:
    event_id: str
    title: str
    source: str
    kind: str | None
    occurred_at: str | None

    repository: str | None
    commit_sha: str | None
    pipeline_name: str | None
    release_version: str | None
    terraform_workspace: str | None

    metadata: dict[str, Any]
    record_found: bool


def _enum_value(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(value, Enum):
        return str(value.value)

    return str(value)


def _deduplicated(
    values: list[str | None],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if not value:
            continue

        normalized = str(value).strip()

        if not normalized:
            continue

        key = normalized.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(normalized)

    return result


def _stable_id(
    prefix: str,
    *parts: object,
) -> str:
    value = "|".join(
        str(part)
        for part in parts
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:32]

    return f"{prefix}:{digest}"


def _analysis_event_node(
    analysis: CausalAnalysisResponse,
    event_id: str,
):
    return next(
        (
            node
            for node in analysis.nodes
            if node.event_id == event_id
            or node.node_id
            == f"event|{event_id}"
        ),
        None,
    )


def _load_event_context(
    session: Session,
    *,
    analysis: CausalAnalysisResponse,
    event_id: str,
    fallback_title: str,
    fallback_source: str | None,
) -> _EventContext:
    record = load_change_event(
        session,
        event_id=event_id,
    )

    view: ChangeEventView | None = None

    if record is not None:
        view = change_event_view(
            session,
            record=record,
        )

    node = _analysis_event_node(
        analysis,
        event_id,
    )

    attributes = (
        node.attributes
        if node is not None
        else {}
    )

    if view is not None:
        return _EventContext(
            event_id=view.event_id,
            title=view.title,
            source=(
                _enum_value(view.source)
                or fallback_source
                or "unknown"
            ),
            kind=_enum_value(view.kind),
            occurred_at=view.occurred_at,
            repository=view.repository,
            commit_sha=view.commit_sha,
            pipeline_name=(
                view.pipeline_name
            ),
            release_version=(
                view.release_version
            ),
            terraform_workspace=(
                view.terraform_workspace
            ),
            metadata=dict(view.metadata),
            record_found=True,
        )

    return _EventContext(
        event_id=event_id,
        title=(
            str(
                node.label
                if node is not None
                else fallback_title
            )
        ),
        source=(
            str(
                attributes.get("source")
                or fallback_source
                or "unknown"
            )
        ),
        kind=(
            str(attributes["kind"])
            if attributes.get("kind")
            is not None
            else None
        ),
        occurred_at=(
            node.occurred_at
            if node is not None
            else None
        ),
        repository=(
            str(attributes["repository"])
            if attributes.get("repository")
            else None
        ),
        commit_sha=(
            str(attributes["commit_sha"])
            if attributes.get("commit_sha")
            else None
        ),
        pipeline_name=(
            str(attributes["pipeline_name"])
            if attributes.get("pipeline_name")
            else None
        ),
        release_version=(
            str(attributes["release_version"])
            if attributes.get("release_version")
            else None
        ),
        terraform_workspace=None,
        metadata={},
        record_found=False,
    )


def _response_priority(
    *,
    incident_severity: object,
    impact: IncidentOwnershipImpact,
) -> tuple[ResponsePriority, str]:
    values: list[
        tuple[ResponsePriority, str]
    ] = []

    severity = (
        _enum_value(incident_severity)
        or ""
    ).lower()

    severity_priority = {
        "critical": ResponsePriority.CRITICAL,
        "error": ResponsePriority.HIGH,
        "warning": ResponsePriority.MEDIUM,
        "info": ResponsePriority.LOW,
    }.get(
        severity,
        ResponsePriority.LOW,
    )

    values.append(
        (
            severity_priority,
            (
                "incident severity is "
                f"'{severity or 'unknown'}'"
            ),
        )
    )

    impact_priority = {
        BusinessImpactLevel.CRITICAL:
            ResponsePriority.CRITICAL,
        BusinessImpactLevel.HIGH:
            ResponsePriority.HIGH,
        BusinessImpactLevel.MEDIUM:
            ResponsePriority.MEDIUM,
        BusinessImpactLevel.LOW:
            ResponsePriority.LOW,
        BusinessImpactLevel.NONE:
            ResponsePriority.LOW,
    }[impact.business_impact_level]

    values.append(
        (
            impact_priority,
            (
                "business impact is "
                f"'{impact.business_impact_level.value}'"
            ),
        )
    )

    if impact.highest_criticality:
        criticality_priority = {
            ServiceCriticality.TIER_1:
                ResponsePriority.CRITICAL,
            ServiceCriticality.TIER_2:
                ResponsePriority.HIGH,
            ServiceCriticality.TIER_3:
                ResponsePriority.MEDIUM,
            ServiceCriticality.TIER_4:
                ResponsePriority.LOW,
        }[impact.highest_criticality]

        values.append(
            (
                criticality_priority,
                (
                    "highest service "
                    "criticality is "
                    f"'{impact.highest_criticality.value}'"
                ),
            )
        )

    if impact.affected_entity_count >= 10:
        values.append(
            (
                ResponsePriority.HIGH,
                (
                    "blast radius contains "
                    f"{impact.affected_entity_count} "
                    "entities"
                ),
            )
        )

    elif impact.affected_entity_count >= 3:
        values.append(
            (
                ResponsePriority.MEDIUM,
                (
                    "blast radius contains "
                    f"{impact.affected_entity_count} "
                    "entities"
                ),
            )
        )

    order = {
        ResponsePriority.LOW: 1,
        ResponsePriority.MEDIUM: 2,
        ResponsePriority.HIGH: 3,
        ResponsePriority.CRITICAL: 4,
    }

    selected = max(
        values,
        key=lambda item: order[item[0]],
    )[0]

    reasons = [
        reason
        for priority, reason in values
        if priority == selected
    ]

    return (
        selected,
        (
            f"Response priority is "
            f"'{selected.value}' because "
            + " and ".join(reasons)
            + "."
        ),
    )


def _action(
    *,
    analysis_id: str,
    category: ResponseActionCategory,
    priority: ResponsePriority,
    title: str,
    description: str,
    reason: str,
    risk: RecommendationRisk = (
        RecommendationRisk.LOW
    ),
    requires_human_approval: bool = False,
    owner_team: str | None = None,
    oncall_contact: str | None = None,
    entity_ids: list[str | None] | None = None,
    event_ids: list[str | None] | None = None,
    evidence_ids: list[str | None] | None = None,
    runbook_url: str | None = None,
) -> IncidentResponseAction:
    normalized_entities = _deduplicated(
        entity_ids or []
    )
    normalized_events = _deduplicated(
        event_ids or []
    )
    normalized_evidence = _deduplicated(
        evidence_ids or []
    )

    action_id = _stable_id(
        "response-action",
        analysis_id,
        category.value,
        title.casefold(),
        ",".join(normalized_entities),
        ",".join(normalized_events),
        runbook_url or "",
    )

    return IncidentResponseAction(
        action_id=action_id,
        sequence=1,
        category=category,
        priority=priority,
        title=title,
        description=description,
        reason=reason,
        risk=risk,
        requires_human_approval=(
            requires_human_approval
        ),
        owner_team=owner_team,
        oncall_contact=oncall_contact,
        entity_ids=normalized_entities,
        evidence_event_ids=(
            normalized_events
        ),
        evidence_ids=normalized_evidence,
        runbook_url=runbook_url,
    )


def _deduplicate_actions(
    actions: list[IncidentResponseAction],
) -> list[IncidentResponseAction]:
    result: list[IncidentResponseAction] = []
    by_key: dict[tuple, int] = {}

    for action in actions:
        key = (
            action.category.value,
            " ".join(
                action.title.casefold().split()
            ),
            tuple(
                value.casefold()
                for value in action.entity_ids
            ),
            tuple(
                value.casefold()
                for value in action
                .evidence_event_ids
            ),
            (
                action.runbook_url.casefold()
                if action.runbook_url
                else None
            ),
        )

        existing_index = by_key.get(key)

        if existing_index is None:
            by_key[key] = len(result)
            result.append(action)
            continue

        existing = result[existing_index]

        result[existing_index] = (
            existing.model_copy(
                update={
                    "evidence_ids": (
                        _deduplicated(
                            [
                                *existing
                                .evidence_ids,
                                *action
                                .evidence_ids,
                            ]
                        )
                    ),
                    "owner_team": (
                        existing.owner_team
                        or action.owner_team
                    ),
                    "oncall_contact": (
                        existing.oncall_contact
                        or action
                        .oncall_contact
                    ),
                    (
                        "requires_human_approval"
                    ): (
                        existing
                        .requires_human_approval
                        or action
                        .requires_human_approval
                    ),
                }
            )
        )

    return result


def _rank_actions(
    actions: list[IncidentResponseAction],
) -> list[IncidentResponseAction]:
    priority_order = {
        ResponsePriority.CRITICAL: 0,
        ResponsePriority.HIGH: 1,
        ResponsePriority.MEDIUM: 2,
        ResponsePriority.LOW: 3,
    }

    category_order = {
        ResponseActionCategory.VALIDATE: 0,
        ResponseActionCategory.INVESTIGATE: 1,
        ResponseActionCategory.ESCALATE: 2,
        ResponseActionCategory.COMMUNICATE: 3,
        ResponseActionCategory.MONITOR: 4,
        ResponseActionCategory.RUNBOOK: 5,
        ResponseActionCategory.MITIGATE: 6,
        ResponseActionCategory
        .ROLLBACK_CANDIDATE: 7,
    }

    risk_order = {
        RecommendationRisk.LOW: 0,
        RecommendationRisk.MEDIUM: 1,
        RecommendationRisk.HIGH: 2,
    }

    deduplicated = _deduplicate_actions(
        actions
    )

    ordered = sorted(
        deduplicated,
        key=lambda action: (
            priority_order[action.priority],
            category_order[action.category],
            risk_order[action.risk],
            action.title.casefold(),
            action.action_id,
        ),
    )

    return [
        action.model_copy(
            update={"sequence": index}
        )
        for index, action in enumerate(
            ordered,
            start=1,
        )
    ]


def _event_detail(
    event: _EventContext,
) -> str:
    details: list[str] = []

    if event.repository:
        details.append(
            f"repository '{event.repository}'"
        )

    if event.commit_sha:
        details.append(
            f"commit '{event.commit_sha}'"
        )

    if event.pipeline_name:
        details.append(
            f"pipeline '{event.pipeline_name}'"
        )

    if event.release_version:
        details.append(
            (
                "release '"
                f"{event.release_version}'"
            )
        )

    if event.terraform_workspace:
        details.append(
            (
                "Terraform workspace '"
                f"{event.terraform_workspace}'"
            )
        )

    if not details:
        return ""

    return (
        " Available change metadata "
        "identifies "
        + ", ".join(details)
        + "."
    )


def _change_review_action(
    *,
    analysis_id: str,
    event: _EventContext,
    hypothesis: CausalHypothesis,
    entity_id: str | None,
    owner_team: str | None,
    oncall_contact: str | None,
    priority: ResponsePriority,
) -> IncidentResponseAction:
    kind = (event.kind or "unknown").lower()
    source = event.source.lower()

    if source in {
        "aws_cloudtrail",
        "azure_activity_log",
        "gcp_audit_log",
    }:
        lead = "Inspect the causal cloud mutation"
        objective = (
            "Review the exact cloud control-plane "
            "mutation and recorded actor metadata for"
        )

    elif kind in {"deployment", "rollout"}:
        lead = "Inspect the causal deployment"
        objective = (
            "Review the exact rollout, artifact, "
            "revision and recorded deployment "
            "metadata associated with"
        )

    elif kind == "configuration":
        lead = "Review the causal configuration change"
        objective = (
            "Compare the exact recorded "
            "configuration delta and its consumers for"
        )

    elif kind == "scaling":
        lead = "Validate the causal scaling change"
        objective = (
            "Review replica, resource and "
            "capacity metadata associated with"
        )

    elif kind == "infrastructure":
        lead = "Review the causal infrastructure change"
        objective = (
            "Inspect the exact infrastructure "
            "resource delta associated with"
        )

    elif kind == "pipeline":
        lead = "Trace the causal pipeline event"
        objective = (
            "Inspect the relevant pipeline job "
            "and its produced artifact for"
        )

    elif kind in {"code", "pull_request"}:
        lead = "Review the causal code change"
        objective = (
            "Inspect the exact repository change "
            "and delivery lineage for"
        )

    else:
        lead = "Inspect the causal change event"
        objective = (
            "Review the stored change metadata and "
            "causal evidence for"
        )

    description = (
        f"{objective} change event "
        f"'{event.event_id}' ({event.title})."
        + _event_detail(event)
    )

    return _action(
        analysis_id=analysis_id,
        category=(
            ResponseActionCategory.INVESTIGATE
        ),
        priority=priority,
        title=f"{lead}: {event.title}",
        description=description,
        reason=(
            "This is the operational change "
            "selected by the leading causal "
            f"hypothesis at confidence "
            f"{hypothesis.confidence:.2f}."
        ),
        owner_team=owner_team,
        oncall_contact=oncall_contact,
        entity_ids=[entity_id],
        event_ids=[
            hypothesis.root_event_id,
            event.event_id,
        ],
        evidence_ids=(
            hypothesis.supporting_evidence_ids
        ),
    )


def _validation_checks(
    *,
    analysis: CausalAnalysisResponse,
    hypothesis: CausalHypothesis,
    event: _EventContext,
    entity_id: str | None,
    impact: IncidentOwnershipImpact,
    priority: ResponsePriority,
) -> list[IncidentResponseAction]:
    checks: list[IncidentResponseAction] = []

    if (
        hypothesis.minutes_before_incident
        is not None
    ):
        minutes = (
            hypothesis.minutes_before_incident
        )

        timing = (
            f"{minutes:.1f} minutes before"
            if minutes >= 0
            else (
                f"{abs(minutes):.1f} minutes "
                "after"
            )
        )

        checks.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                priority=priority,
                title=(
                    "Confirm the causal event "
                    "timeline"
                ),
                description=(
                    f"Verify that change event "
                    f"'{event.event_id}' occurred "
                    f"{timing} incident start and "
                    "that degradation began in the "
                    "same causal window."
                ),
                reason=(
                    "Temporal ordering can support "
                    "or refute the leading causal "
                    "hypothesis."
                ),
                entity_ids=[entity_id],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    if entity_id:
        checks.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                priority=priority,
                title=(
                    "Confirm the change-to-entity "
                    "correlation"
                ),
                description=(
                    f"Verify that causal change "
                    f"event '{event.event_id}' "
                    "actually reached incident-time "
                    f"entity '{entity_id}'."
                ),
                reason=(
                    "The leading hypothesis depends "
                    "on the recorded change/entity "
                    "and topology evidence path."
                ),
                entity_ids=[entity_id],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    artifact = (
        event.release_version
        or event.commit_sha
    )

    if artifact and entity_id:
        artifact_kind = (
            "release"
            if event.release_version
            else "commit"
        )

        checks.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                priority=priority,
                title=(
                    "Confirm the affected runtime "
                    "uses the changed artifact"
                ),
                description=(
                    f"Verify that incident-time "
                    f"entity '{entity_id}' was "
                    f"running the {artifact_kind} "
                    f"'{artifact}' associated with "
                    f"event '{event.event_id}'."
                ),
                reason=(
                    "Artifact identity provides a "
                    "high-information check of the "
                    "causal hypothesis."
                ),
                entity_ids=[entity_id],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    if impact.affected_entity_count > 1:
        checks.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                priority=priority,
                title=(
                    "Confirm downstream failures "
                    "match the blast radius"
                ),
                description=(
                    "Verify that observed downstream "
                    "degradation aligns with the "
                    f"{impact.affected_entity_count} "
                    "entities in the existing "
                    "incident blast-radius result."
                ),
                reason=(
                    "Topology-consistent propagation "
                    "strengthens the hypothesis; a "
                    "different pattern may refute it."
                ),
                entity_ids=[
                    item.entity_id
                    for item in impact
                    .affected_entities
                ],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    before = event.metadata.get("before")
    after = event.metadata.get("after")

    if before is not None and after is not None:
        checks.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.VALIDATE
                ),
                priority=priority,
                title=(
                    "Compare the recorded previous "
                    "and current state"
                ),
                description=(
                    f"Review the stored before/after "
                    f"evidence for change event "
                    f"'{event.event_id}' and confirm "
                    "that the changed values are "
                    "present on the causal entity."
                ),
                reason=(
                    "A rollback or reversion should "
                    "not be considered until the "
                    "specific delta is verified."
                ),
                entity_ids=[entity_id],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    return _rank_actions(checks)


def _rollback_candidate(
    *,
    hypothesis: CausalHypothesis,
    event: _EventContext,
    entity_id: str | None,
) -> RollbackCandidate:
    eligible_kinds = {
        "deployment",
        "rollout",
        "configuration",
    }

    if hypothesis.confidence < (
        STRONG_CAUSAL_CONFIDENCE
    ):
        return RollbackCandidate(
            available=False,
            reason=(
                "Causal confidence is below the "
                f"{STRONG_CAUSAL_CONFIDENCE:.2f} "
                "threshold required to surface a "
                "rollback or reversion candidate."
            ),
        )

    if (event.kind or "").lower() not in (
        eligible_kinds
    ):
        return RollbackCandidate(
            available=False,
            reason=(
                "The leading operational event is "
                f"classified as '{event.kind or 'unknown'}'; "
                "Topo only surfaces conservative "
                "deployment, rollout or configuration "
                "rollback candidates."
            ),
        )

    if not event.record_found:
        return RollbackCandidate(
            available=False,
            reason=(
                "The causal change-event record could "
                "not be loaded, so an exact rollback "
                "candidate cannot be identified."
            ),
        )

    if (
        hypothesis.minutes_before_incident
        is None
        or hypothesis.minutes_before_incident
        < 0
    ):
        return RollbackCandidate(
            available=False,
            reason=(
                "The available evidence does not show "
                "that the candidate change preceded "
                "the incident."
            ),
        )

    if not hypothesis.supporting_evidence_ids:
        return RollbackCandidate(
            available=False,
            reason=(
                "The leading hypothesis has no "
                "referenced causal evidence for a "
                "rollback decision."
            ),
        )

    if not entity_id:
        return RollbackCandidate(
            available=False,
            reason=(
                "No incident-time causal entity was "
                "resolved for the candidate change."
            ),
        )

    return RollbackCandidate(
        available=True,
        change_event_id=event.event_id,
        reason=(
            f"Change event '{event.event_id}' is a "
            f"{event.kind} change that preceded the "
            "incident, is linked to the causal entity, "
            f"and has {hypothesis.confidence:.2f} "
            "causal confidence. Validate the leading "
            "hypothesis and the previous known-good "
            "state before considering reversion."
        ),
        requires_human_approval=True,
    )


RUNBOOK_KEYS = {
    "topo.ai/runbook": "Runbook",
    "topo.ai/runbook-url": "Runbook",
    "runbook": "Runbook",
    "runbook_url": "Runbook",
    "playbook": "Playbook",
    "playbook_url": "Playbook",
    "documentation_url": (
        "Operational documentation"
    ),
    "docs_url": "Operational documentation",
    "service_documentation": (
        "Service documentation"
    ),
}


def _http_url(
    value: object,
) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()

    if normalized.lower().startswith(
        ("https://", "http://")
    ):
        return normalized

    return None


def _runbook_reference(
    *,
    title: str,
    url: str,
    source: str,
    entity_id: str | None,
) -> RunbookReference:
    return RunbookReference(
        runbook_id=_stable_id(
            "runbook",
            url.casefold(),
            source,
            entity_id or "",
        ),
        title=title,
        url=url,
        source=source,
        entity_id=entity_id,
    )


def _runbooks_from_mapping(
    *,
    values: dict[str, Any],
    source_prefix: str,
    default_title: str,
    entity_id: str | None,
) -> list[RunbookReference]:
    result: list[RunbookReference] = []

    for key, label in RUNBOOK_KEYS.items():
        url = _http_url(values.get(key))

        if url:
            result.append(
                _runbook_reference(
                    title=(
                        f"{label}: "
                        f"{default_title}"
                    ),
                    url=url,
                    source=(
                        f"{source_prefix}:{key}"
                    ),
                    entity_id=entity_id,
                )
            )

    for key in ("runbooks", "playbooks"):
        raw_items = values.get(key)

        if not isinstance(raw_items, list):
            continue

        for item in raw_items:
            if isinstance(item, str):
                url = _http_url(item)
                title = default_title

            elif isinstance(item, dict):
                url = _http_url(
                    item.get("url")
                    or item.get("href")
                )
                title = str(
                    item.get("title")
                    or item.get("name")
                    or default_title
                )

            else:
                continue

            if not url:
                continue

            result.append(
                _runbook_reference(
                    title=title,
                    url=url,
                    source=(
                        f"{source_prefix}:{key}"
                    ),
                    entity_id=entity_id,
                )
            )

    return result


def _discover_runbooks(
    *,
    entity: Entity | None,
    event: _EventContext,
) -> list[RunbookReference]:
    values: list[RunbookReference] = []

    if entity is not None:
        values.extend(
            _runbooks_from_mapping(
                values=entity.labels,
                source_prefix="entity.labels",
                default_title=entity.name,
                entity_id=entity.id,
            )
        )
        values.extend(
            _runbooks_from_mapping(
                values=entity.properties,
                source_prefix=(
                    "entity.properties"
                ),
                default_title=entity.name,
                entity_id=entity.id,
            )
        )

    values.extend(
        _runbooks_from_mapping(
            values=event.metadata,
            source_prefix=(
                "change_event.metadata"
            ),
            default_title=event.title,
            entity_id=(
                entity.id
                if entity is not None
                else None
            ),
        )
    )

    result: list[RunbookReference] = []
    seen: set[str] = set()

    for item in values:
        key = item.url.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def _historical_entity(
    session: Session,
    *,
    analysis: CausalAnalysisResponse,
    entity_id: str | None,
) -> tuple[
    GraphSnapshot | None,
    Entity | None,
    list[str],
]:
    warnings: list[str] = []

    if not analysis.topology_snapshot_id:
        warnings.append(
            "The causal analysis does not "
            "reference a topology snapshot; "
            "incident-time runbook metadata "
            "could not be inspected."
        )
        return None, None, warnings

    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=(
            analysis.topology_snapshot_id
        ),
    )

    if snapshot is None:
        warnings.append(
            "The topology snapshot referenced "
            "by the causal analysis was not "
            "found while building the response "
            f"plan: {analysis.topology_snapshot_id}"
        )
        return None, None, warnings

    if not entity_id:
        return snapshot, None, warnings

    entity = next(
        (
            item
            for item in snapshot.entities
            if item.id == entity_id
        ),
        None,
    )

    if entity is None:
        warnings.append(
            "The causal entity was not present "
            "in the topology snapshot referenced "
            f"by the causal analysis: {entity_id}"
        )

    return snapshot, entity, warnings


def _recommended_actions(
    *,
    analysis: CausalAnalysisResponse,
    hypothesis: CausalHypothesis,
    event: _EventContext,
    context: IncidentOperationalContext,
    priority: ResponsePriority,
    rollback: RollbackCandidate,
    runbooks: list[RunbookReference],
) -> list[IncidentResponseAction]:
    ownership = context.root_cause_ownership
    impact = context.overall_business_impact

    owner_team = (
        ownership.owner_team
        if ownership is not None
        and ownership.resolved
        else None
    )
    oncall_contact = (
        ownership.oncall_contact
        if ownership is not None
        and ownership.resolved
        else None
    )

    actions = [
        _change_review_action(
            analysis_id=analysis.analysis_id,
            event=event,
            hypothesis=hypothesis,
            entity_id=context.root_entity_id,
            owner_team=owner_team,
            oncall_contact=oncall_contact,
            priority=priority,
        )
    ]

    entity_label = (
        ownership.service_name
        if ownership is not None
        and ownership.service_name
        else context.root_entity_id
        or "the causal entity"
    )

    causal_time = (
        event.occurred_at
        or analysis.incident_time
    )

    actions.append(
        _action(
            analysis_id=analysis.analysis_id,
            category=(
                ResponseActionCategory.INVESTIGATE
            ),
            priority=priority,
            title=(
                "Inspect runtime evidence for "
                f"{entity_label}"
            ),
            description=(
                "Inspect runtime errors, health "
                "signals and workload events for "
                f"'{entity_label}' around "
                f"'{causal_time}', the recorded "
                "causal window for change event "
                f"'{event.event_id}'."
            ),
            reason=(
                "Runtime evidence closest to the "
                "causal entity can validate or "
                "refute the leading hypothesis "
                "without changing infrastructure."
            ),
            owner_team=owner_team,
            oncall_contact=oncall_contact,
            entity_ids=[context.root_entity_id],
            event_ids=[event.event_id],
            evidence_ids=(
                hypothesis.supporting_evidence_ids
            ),
        )
    )

    if owner_team or oncall_contact:
        target = (
            owner_team
            or oncall_contact
            or "resolved owner"
        )

        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.ESCALATE
                ),
                priority=priority,
                title=f"Escalate to {target}",
                description=(
                    "Send the causal event, causal "
                    "entity, validation checks and "
                    "business-impact context to the "
                    "resolved root-cause owner"
                    + (
                        f" via '{oncall_contact}'."
                        if oncall_contact
                        else "."
                    )
                ),
                reason=(
                    "Block 14A resolved ownership "
                    "for the root causal entity."
                ),
                owner_team=owner_team,
                oncall_contact=oncall_contact,
                entity_ids=[
                    context.root_entity_id
                ],
                event_ids=[
                    event.event_id
                ],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    elif context.escalation_targets:
        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.ESCALATE
                ),
                priority=priority,
                title=(
                    "Escalate through affected-service "
                    "ownership"
                ),
                description=(
                    "Root ownership is unresolved. "
                    "Use the deduplicated affected-"
                    "service escalation targets: "
                    + ", ".join(
                        context
                        .escalation_targets
                    )
                    + "."
                ),
                reason=(
                    "The overall business-impact "
                    "context still provides affected "
                    "team or on-call routing."
                ),
                entity_ids=[
                    context.root_entity_id
                ],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    if (
        impact.business_impact_level
        in {
            BusinessImpactLevel.CRITICAL,
            BusinessImpactLevel.HIGH,
        }
        and (
            impact.owner_teams
            or impact.business_capabilities
        )
    ):
        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.COMMUNICATE
                ),
                priority=priority,
                title=(
                    "Communicate the confirmed "
                    "business impact"
                ),
                description=(
                    "Share validated incident status "
                    f"with {impact.affected_team_count} "
                    "affected team(s) and "
                    f"{impact.affected_capability_count} "
                    "affected business capability "
                    "group(s)"
                    + (
                        ": "
                        + ", ".join(
                            impact
                            .business_capabilities
                        )
                        + "."
                        if impact
                        .business_capabilities
                        else "."
                    )
                ),
                reason=(
                    "Block 14A classified business "
                    "impact as "
                    f"'{impact.business_impact_level.value}'."
                ),
                owner_team=owner_team,
                oncall_contact=oncall_contact,
                entity_ids=[
                    item.entity_id
                    for item in impact
                    .affected_entities
                ],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    if impact.affected_entity_count:
        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.MONITOR
                ),
                priority=(
                    ResponsePriority.MEDIUM
                    if priority
                    in {
                        ResponsePriority.CRITICAL,
                        ResponsePriority.HIGH,
                    }
                    else priority
                ),
                title=(
                    "Monitor the existing incident "
                    "blast radius"
                ),
                description=(
                    "Track health and error signals "
                    "for the "
                    f"{impact.affected_entity_count} "
                    "entities already identified by "
                    "the incident blast-radius and "
                    "ownership-impact calculation."
                ),
                reason=(
                    "Changes in downstream state can "
                    "confirm propagation or show that "
                    "the leading hypothesis is incomplete."
                ),
                owner_team=owner_team,
                oncall_contact=oncall_contact,
                entity_ids=[
                    item.entity_id
                    for item in impact
                    .affected_entities
                ],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    for runbook in runbooks:
        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory.RUNBOOK
                ),
                priority=(
                    ResponsePriority.MEDIUM
                    if priority
                    in {
                        ResponsePriority.CRITICAL,
                        ResponsePriority.HIGH,
                    }
                    else priority
                ),
                title=(
                    f"Follow {runbook.title}"
                ),
                description=(
                    "Review the existing runbook "
                    f"metadata at '{runbook.url}' "
                    "before proposing a change."
                ),
                reason=(
                    "This runbook was discovered from "
                    f"existing {runbook.source} metadata."
                ),
                owner_team=owner_team,
                oncall_contact=oncall_contact,
                entity_ids=[runbook.entity_id],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
                runbook_url=runbook.url,
            )
        )

    if rollback.available:
        actions.append(
            _action(
                analysis_id=analysis.analysis_id,
                category=(
                    ResponseActionCategory
                    .ROLLBACK_CANDIDATE
                ),
                priority=(
                    ResponsePriority.HIGH
                    if priority
                    == ResponsePriority.CRITICAL
                    else priority
                ),
                title=(
                    "Consider reversion only after "
                    "validation confirms the regression"
                ),
                description=(
                    "If the validation checks confirm "
                    "the leading hypothesis and a "
                    "previous known-good state, responders "
                    "may consider reverting change event "
                    f"'{event.event_id}' through its "
                    "authoritative delivery system. Topo "
                    "has not approved or executed this action."
                ),
                reason=rollback.reason,
                risk=RecommendationRisk.HIGH,
                requires_human_approval=True,
                owner_team=owner_team,
                oncall_contact=oncall_contact,
                entity_ids=[
                    context.root_entity_id
                ],
                event_ids=[event.event_id],
                evidence_ids=(
                    hypothesis
                    .supporting_evidence_ids
                ),
            )
        )

    return _rank_actions(actions)


def build_incident_response_plan(
    session: Session,
    incident_id: str,
) -> IncidentResponsePlan:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    analysis = latest_causal_analysis(
        session,
        incident_id=incident_id,
    )

    if analysis is None:
        raise ValueError(
            "No causal analysis exists for "
            "this incident."
        )

    hypothesis = analysis.top_hypothesis

    if hypothesis is None:
        raise ValueError(
            "The latest causal analysis has no "
            "ranked causal hypothesis."
        )

    # Block 14A remains the single owner of
    # root ownership, business impact, blast-radius
    # aggregation and escalation calculation.
    context = build_incident_operational_context(
        session=session,
        incident_id=incident_id,
    )

    root_event = _load_event_context(
        session,
        analysis=analysis,
        event_id=hypothesis.root_event_id,
        fallback_title=hypothesis.root_title,
        fallback_source=(
            hypothesis.root_source
        ),
    )

    target_event = _load_event_context(
        session,
        analysis=analysis,
        event_id=hypothesis.target_event_id,
        fallback_title=hypothesis.target_title,
        fallback_source=None,
    )

    # The target event is the change connected to the
    # causal topology path. The root event remains the
    # displayed causal origin (for example commit ->
    # deployment), while recommendations act on the
    # operationally relevant target change.
    operational_event = target_event

    priority, priority_reason = (
        _response_priority(
            incident_severity=(
                incident.severity
            ),
            impact=(
                context
                .overall_business_impact
            ),
        )
    )

    (
        _,
        historical_entity,
        historical_warnings,
    ) = _historical_entity(
        session,
        analysis=analysis,
        entity_id=context.root_entity_id,
    )

    runbooks = _discover_runbooks(
        entity=historical_entity,
        event=operational_event,
    )

    rollback = _rollback_candidate(
        hypothesis=hypothesis,
        event=operational_event,
        entity_id=context.root_entity_id,
    )

    checks = _validation_checks(
        analysis=analysis,
        hypothesis=hypothesis,
        event=operational_event,
        entity_id=context.root_entity_id,
        impact=(
            context.overall_business_impact
        ),
        priority=priority,
    )

    actions = _recommended_actions(
        analysis=analysis,
        hypothesis=hypothesis,
        event=operational_event,
        context=context,
        priority=priority,
        rollback=rollback,
        runbooks=runbooks,
    )

    warnings = [
        *context.warnings,
        *historical_warnings,
    ]

    if not root_event.record_found:
        warnings.append(
            "The root causal change-event record "
            "was not found; root event details are "
            "limited to the persisted causal analysis."
        )

    if not target_event.record_found:
        warnings.append(
            "The target causal change-event record "
            "was not found; response recommendations "
            "are limited to causal-analysis metadata."
        )

    if hypothesis.confidence < 0.50:
        warnings.append(
            "Causal confidence is low. The plan "
            "prioritizes investigation and validation "
            "and does not surface destructive "
            "mitigation as a candidate."
        )

    ownership = context.root_cause_ownership

    if (
        ownership is None
        or not ownership.resolved
    ):
        warnings.append(
            "Root-cause ownership is unresolved; "
            "no owner was invented."
        )

    root_cause = ResponseRootCause(
        event_id=root_event.event_id,
        event_title=root_event.title,
        event_source=root_event.source,
        event_kind=root_event.kind,
        occurred_at=root_event.occurred_at,
        target_event_id=(
            target_event.event_id
        ),
        target_event_title=(
            target_event.title
        ),
        target_event_source=(
            target_event.source
        ),
        target_event_kind=(
            target_event.kind
        ),
        target_occurred_at=(
            target_event.occurred_at
        ),
        entity_id=context.root_entity_id,
        causal_confidence=(
            hypothesis.confidence
        ),
        confidence_level=(
            hypothesis
            .confidence_level.value
        ),
        evidence_ids=_deduplicated(
            hypothesis
            .supporting_evidence_ids
        ),
    )

    return IncidentResponsePlan(
        incident_id=incident_id,
        causal_analysis_id=(
            analysis.analysis_id
        ),
        response_priority=priority,
        response_priority_reason=(
            priority_reason
        ),
        root_cause=root_cause,
        primary_owner=ownership,
        business_context=(
            context.overall_business_impact
        ),
        recommended_actions=actions,
        validation_checks=checks,
        rollback_candidate=rollback,
        runbooks=runbooks,
        escalation_targets=(
            _deduplicated(
                context
                .escalation_targets
            )
        ),
        warnings=_deduplicated(warnings),
    )
