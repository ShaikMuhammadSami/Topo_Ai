from __future__ import annotations
from app.repositories.tenant_scope import (
    DomainTenant,
    require_record_owner,
    TenantResourceNotFound,
)

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models import IncidentOutcomeRecord
from app.models.causal_rca import (
    CausalAnalysisResponse,
)
from app.models.incident_memory import (
    HistoricalIncidentFeatureProfile,
    HistoricalResolutionAction,
    HistoricalResolutionSummary,
)
from app.models.incident_outcome import (
    IncidentOutcome,
)
from app.models.incident_records import (
    IncidentRecordView,
    IncidentStatus,
)
from app.models.ownership import (
    IncidentOwnershipImpact,
)
from app.models.topology import GraphSnapshot
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
    load_causal_analysis,
)
from app.repositories.incident_outcome_repository import (
    outcome_source,
    load_incident_outcome_record,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.topology_neighborhood import (
    traverse_topology_neighborhood,
)
from app.services.business_impact import (
    calculate_incident_ownership_impact,
)
from app.services.incident_context import (
    root_entity_id_for_analysis,
)
from app.services.ownership_resolver import (
    resolve_entity_ownership,
    stable_service_name,
)

FEATURE_SCHEMA_VERSION = (
    "14d-structured-v1"
)
NEIGHBORHOOD_HOPS = 2
FALLBACK_AFFECTED_HOPS = 5


from app.services.tenant_world_model import bind_world_value, tenant_world

def _value(value: Any) -> str | None:
    if value is None:
        return None

    raw = getattr(value, "value", value)
    text = str(raw).strip()
    return text or None


def _deduplicated(
    values: list[str | None],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = _value(value)

        if text is None:
            continue

        key = text.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(text)

    return result


def _sorted_values(
    values: list[str | None],
) -> list[str]:
    return sorted(
        _deduplicated(values),
        key=lambda item: item.casefold(),
    )


def _analysis_event(
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


def _causal_change_details(
    analysis: CausalAnalysisResponse | None,
) -> tuple[str | None, str | None]:
    if (
        analysis is None
        or analysis.top_hypothesis is None
    ):
        return None, None

    hypothesis = analysis.top_hypothesis

    # The target event is the operational change
    # connected to the causal topology path. This is
    # the same interpretation used by Block 14B.
    target = _analysis_event(
        analysis,
        hypothesis.target_event_id,
    )
    root = _analysis_event(
        analysis,
        hypothesis.root_event_id,
    )

    target_attributes = (
        target.attributes
        if target is not None
        else {}
    )
    root_attributes = (
        root.attributes
        if root is not None
        else {}
    )

    kind = _value(
        target_attributes.get("kind")
        or root_attributes.get("kind")
    )
    source = _value(
        target_attributes.get("source")
        or root_attributes.get("source")
        or hypothesis.root_source
    )

    return kind, source


def _feature_fingerprint(
    values: dict[str, Any],
) -> str:
    def normalized(value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().casefold()

        if isinstance(value, list):
            return sorted(
                {
                    str(item).strip().casefold()
                    for item in value
                    if str(item).strip()
                }
            )

        return value

    canonical = {
        key: normalized(value)
        for key, value in values.items()
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _snapshot_for_profile(
    session: Session,
    *,
    incident: IncidentRecordView,
    analysis: CausalAnalysisResponse | None,
    historical_snapshot_id: str | None,
    warnings: list[str],
    tenant_id: DomainTenant,
) -> tuple[str | None, GraphSnapshot | None]:
    snapshot_id = (
        historical_snapshot_id
        or (
            analysis.topology_snapshot_id
            if analysis is not None
            else None
        )
        or (
            incident.topology_snapshot_id
            if historical_snapshot_id is None
            and analysis is None
            else None
        )
    )

    if snapshot_id is None:
        warnings.append(
            "Incident-time topology is unavailable; "
            "topology similarity was omitted."
        )
        return None, None

    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=snapshot_id,
        tenant_id=tenant_id,
    )

    if snapshot is None:
        warnings.append(
            "Incident-time topology snapshot was "
            f"not found: {snapshot_id}"
        )

    return snapshot_id, snapshot


def _runbook_url(
    source: dict[str, Any],
    response_plan_action_id: str | None,
) -> str | None:
    if response_plan_action_id is None:
        return None

    plan = source.get("response_plan")

    if not isinstance(plan, dict):
        return None

    actions = plan.get("actions")

    if not isinstance(actions, list):
        return None

    for item in actions:
        if not isinstance(item, dict):
            continue

        if (
            _value(item.get("action_id"))
            != response_plan_action_id
        ):
            continue

        return _value(item.get("runbook_url"))

    return None


def resolution_summary_for_outcome(
    outcome: IncidentOutcome,
    *,
    source: dict[str, Any] | None = None,
) -> HistoricalResolutionSummary:
    source_value = source or {}
    primary = outcome.primary_resolution_action
    action = None

    if primary is not None:
        action = HistoricalResolutionAction(
            action_instance_id=(
                primary.action_instance_id
            ),
            action_type=primary.action_type,
            title=primary.title,
            effectiveness=(
                primary.effectiveness
            ),
            response_plan_action_id=(
                primary.response_plan_action_id
            ),
            runbook_url=_runbook_url(
                source_value,
                primary.response_plan_action_id,
            ),
        )

    return HistoricalResolutionSummary(
        rca_verdict=outcome.rca_verdict,
        rca_confidence=outcome.rca_confidence,
        root_cause=(
            outcome.final_root_cause
            or outcome.original_root_cause
        ),
        primary_resolution_action=action,
        time_to_mitigation_seconds=(
            outcome.time_to_mitigation_seconds
        ),
        time_to_resolution_seconds=(
            outcome.time_to_resolution_seconds
        ),
        resolution_summary=(
            outcome.resolution_summary
        ),
        warnings=_deduplicated(
            list(outcome.warnings)
        ),
    )


def completed_historical_outcome(
    record: IncidentOutcomeRecord,
) -> tuple[IncidentOutcome, dict[str, Any]] | None:
    try:
        outcome = (
            IncidentOutcome.model_validate_json(
                record.payload_json
            )
        )

    except (ValidationError, ValueError, TypeError):
        return None

    if (
        outcome.resolved_at is None
        and outcome.status
        not in {
            IncidentStatus.RESOLVED,
            IncidentStatus.DISMISSED,
        }
    ):
        return None

    return outcome, outcome_source(record)


def _historical_analysis(
    session: Session,
    *,
    outcome: IncidentOutcome,
    warnings: list[str],
    tenant_id: DomainTenant,
) -> CausalAnalysisResponse | None:
    if outcome.causal_analysis_id is None:
        warnings.append(
            "Causal analysis unavailable; "
            "similarity is based on reduced context."
        )
        return None

    analysis = load_causal_analysis(
        session,
        analysis_id=outcome.causal_analysis_id,
        tenant_id=tenant_id,
    )

    if analysis is None:
        warnings.append(
            "The causal analysis pinned by the "
            "historical outcome was not found: "
            f"{outcome.causal_analysis_id}"
        )
        warnings.append(
            "Causal analysis unavailable; "
            "similarity is based on reduced context."
        )

    return analysis


@tenant_world(prefetched=('incident', 'analysis', 'operational_impact', 'outcome'))
def build_incident_feature_profile(
    session: Session,
    *,
    incident: IncidentRecordView,
    analysis: CausalAnalysisResponse | None,
    outcome: IncidentOutcome | None = None,
    outcome_source_data: dict[str, Any] | None = None,
    historical: bool = False,
    operational_impact: IncidentOwnershipImpact | None = None,
    tenant_id: DomainTenant,
) -> HistoricalIncidentFeatureProfile:
    if outcome_source_data is not None:
        # A plain source dictionary has no ownership attestation. Validate it
        # against the owned durable outcome before it supplies historical URLs
        # or response context. Matching public IDs alone are not authority.
        record = load_incident_outcome_record(
            session, incident_id=incident.incident_id, tenant_id=tenant_id,
        )
        if (outcome is None or record is None
                or record.outcome_id != outcome.outcome_id
                or outcome_source_data != outcome_source(record)):
            raise TenantResourceNotFound()
    warnings: list[str] = []

    if analysis is None:
        warnings.append(
            "Causal analysis unavailable; "
            "similarity is based on reduced context."
        )

    historical_snapshot_id = (
        outcome.historical_topology_snapshot_id
        if historical and outcome is not None
        else None
    )
    snapshot_id, snapshot = _snapshot_for_profile(
        session,
        incident=incident,
        analysis=analysis,
        historical_snapshot_id=(historical_snapshot_id),
        warnings=warnings,
        tenant_id=tenant_id,
    )

    if (
        historical
        and outcome is not None
        and outcome.historical_topology_snapshot_id
        and analysis is not None
        and analysis.topology_snapshot_id
        and outcome.historical_topology_snapshot_id
        != analysis.topology_snapshot_id
    ):
        warnings.append(
            "The outcome and causal analysis "
            "reference different topology snapshots; "
            "the outcome-pinned historical snapshot "
            "was used."
        )

    hypothesis = (
        analysis.top_hypothesis
        if analysis is not None
        else None
    )
    root_entity_id = (
        root_entity_id_for_analysis(analysis)
        if analysis is not None
        else None
    )
    root_entity = None
    entity_map = {}

    if snapshot is not None:
        entity_map = {
            entity.id: entity
            for entity in snapshot.entities
        }
        root_entity = entity_map.get(
            root_entity_id
        )

    if root_entity_id and root_entity is None:
        warnings.append(
            "The root causal entity was not found "
            "in the incident-time topology snapshot: "
            f"{root_entity_id}"
        )

    root_service_name = (
        stable_service_name(root_entity)
        if root_entity is not None
        else None
    )
    root_owner_team = None
    business_capability = None
    criticality = None

    if snapshot is not None and root_entity is not None:
        try:
            ownership = resolve_entity_ownership(
                session=session,
                snapshot=snapshot,
                entity=root_entity,
                tenant_id=tenant_id,
            )

        except ValueError as exc:
            warnings.append("Root ownership resolution was " f"unavailable: {exc}")

        else:
            if ownership.resolved:
                root_owner_team = ownership.owner_team
                business_capability = (
                    ownership.business_capability
                )
                criticality = _value(
                    ownership.criticality
                )
            else:
                warnings.append(
                    "Root ownership is unresolved; "
                    "owner-derived similarity factors "
                    "were omitted."
                )

    affected_entity_ids: list[str] = []
    affected_entity_kinds: list[str] = []

    # Reuse Block 14A when its incident snapshot is
    # the exact snapshot selected above. Never ask it
    # to evaluate a different historical graph.
    if snapshot_id is not None and incident.topology_snapshot_id == snapshot_id:
        impact = operational_impact

        if impact is None:
            try:
                impact = calculate_incident_ownership_impact(
                    session=session,
                    incident_id=(incident.incident_id),
                    tenant_id=tenant_id,
                )

            except ValueError as exc:
                warnings.append(
                    "Operational context unavailable; "
                    "technical similarity will continue: "
                    f"{exc}"
                )

        if impact is not None:
            affected_entity_ids = [
                item.entity_id
                for item in impact.affected_entities
            ]
            affected_entity_kinds = [
                item.entity_kind
                for item in impact.affected_entities
            ]

            if root_owner_team is None and (
                len(impact.owner_teams) == 1
            ):
                root_owner_team = (
                    impact.owner_teams[0]
                )

            if business_capability is None and (
                len(
                    impact.business_capabilities
                )
                == 1
            ):
                business_capability = (
                    impact.business_capabilities[0]
                )

            if (
                criticality is None
                and impact.highest_criticality
                is not None
            ):
                criticality = _value(
                    impact.highest_criticality
                )

            warnings.extend(impact.warnings)

    else:
        warnings.append(
            "Operational context unavailable for "
            "the selected incident-time snapshot; "
            "technical similarity will continue."
        )

    topology_seed = (
        root_entity_id
        or incident.affected_entity_id
    )
    topology_neighbor_ids: list[str] = []

    if snapshot is not None and topology_seed:
        topology_neighbor_ids = [
            entity_id
            for entity_id in traverse_topology_neighborhood(
                topology_seed,
                snapshot.relationships,
                NEIGHBORHOOD_HOPS,
            )
            if entity_id != topology_seed
        ]

        if not affected_entity_ids:
            affected_entity_ids = (
                traverse_topology_neighborhood(
                    topology_seed,
                    snapshot.relationships,
                    FALLBACK_AFFECTED_HOPS,
                )
            )

    if (
        not affected_entity_ids
        and incident.affected_entity_id
    ):
        affected_entity_ids = [
            incident.affected_entity_id
        ]

    if entity_map:
        affected_entity_kinds.extend(
            entity_map[entity_id].kind
            for entity_id in affected_entity_ids
            if entity_id in entity_map
        )

    topology_neighbor_kinds = [
        entity_map[entity_id].kind
        for entity_id in topology_neighbor_ids
        if entity_id in entity_map
    ]

    change_kind, change_source = (
        _causal_change_details(analysis)
    )
    environment = (
        _value(root_entity.environment)
        if root_entity is not None
        else None
    ) or (
        _value(snapshot.scope.get("environment"))
        if snapshot is not None
        else None
    )

    severity = _value(incident.severity) or "unknown"
    fingerprint_values = {
        "severity": severity,
        "environment": environment,
        "root_entity_id": root_entity_id,
        "root_entity_kind": (
            root_entity.kind
            if root_entity is not None
            else None
        ),
        "root_service_name": root_service_name,
        "causal_change_kind": change_kind,
        "causal_change_source": change_source,
        "owner_team": root_owner_team,
        "business_capability": business_capability,
        "affected_entity_ids": (
            _sorted_values(affected_entity_ids)
        ),
        "affected_entity_kinds": (
            _sorted_values(affected_entity_kinds)
        ),
        "topology_neighbor_ids": (
            _sorted_values(topology_neighbor_ids)
        ),
        "topology_neighbor_kinds": (
            _sorted_values(
                topology_neighbor_kinds
            )
        ),
    }

    return HistoricalIncidentFeatureProfile(
        schema_version=FEATURE_SCHEMA_VERSION,
        feature_fingerprint=(
            _feature_fingerprint(
                fingerprint_values
            )
        ),
        incident_id=incident.incident_id,
        incident_title=incident.title,
        incident_time=(
            analysis.incident_time
            if analysis is not None
            else incident.first_observed_at.isoformat()
        ),
        resolved_at=(
            outcome.resolved_at.isoformat()
            if outcome is not None
            and outcome.resolved_at is not None
            else None
        ),
        severity=severity,
        environment=environment,
        causal_analysis_id=(
            analysis.analysis_id
            if analysis is not None
            else None
        ),
        topology_snapshot_id=snapshot_id,
        root_event_id=(
            hypothesis.root_event_id
            if hypothesis is not None
            else None
        ),
        root_event_title=(
            hypothesis.root_title
            if hypothesis is not None
            else None
        ),
        root_event_source=(
            hypothesis.root_source
            if hypothesis is not None
            else None
        ),
        root_entity_id=root_entity_id,
        root_entity_kind=(
            root_entity.kind
            if root_entity is not None
            else None
        ),
        root_service_name=root_service_name,
        causal_change_kind=change_kind,
        causal_change_source=change_source,
        owner_team=root_owner_team,
        business_capability=business_capability,
        criticality=criticality,
        affected_entity_ids=(
            _sorted_values(affected_entity_ids)
        ),
        affected_entity_kinds=(
            _sorted_values(affected_entity_kinds)
        ),
        topology_neighbor_ids=(
            _sorted_values(topology_neighbor_ids)
        ),
        topology_neighbor_kinds=(
            _sorted_values(
                topology_neighbor_kinds
            )
        ),
        blast_radius_size=len(
            _deduplicated(
                affected_entity_ids
            )
        ),
        resolution=(
            resolution_summary_for_outcome(
                outcome,
                source=(
                    outcome_source_data
                    or {}
                ),
            )
            if outcome is not None
            else None
        ),
        warnings=_deduplicated(warnings),
    )


@tenant_world(prefetched=('incident_record', 'causal_analysis', 'operational_impact'))
def build_current_incident_profile(
    session: Session,
    *,
    incident_id: str,
    incident_record: IncidentRecordView | None = None,
    causal_analysis: CausalAnalysisResponse | None = None,
    operational_impact: IncidentOwnershipImpact | None = None,
    tenant_id: DomainTenant,
) -> HistoricalIncidentFeatureProfile:
    incident = incident_record or (
        load_incident_record(
            session=session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    analysis = causal_analysis or (
        latest_causal_analysis(
            session,
            incident_id=incident_id,
            tenant_id=tenant_id,
        )
    )

    return build_incident_feature_profile(
        session,
        incident=incident,
        analysis=analysis,
        operational_impact=operational_impact,
        tenant_id=tenant_id,
    )


@tenant_world(prefetched=())
def build_historical_incident_profile(
    session: Session,
    *,
    record: IncidentOutcomeRecord,
    tenant_id: DomainTenant,
) -> HistoricalIncidentFeatureProfile | None:
    require_record_owner(record, tenant_id=tenant_id)
    completed = completed_historical_outcome(
        record
    )

    if completed is None:
        return None

    outcome, source = completed
    # The record owner was checked before decoding this historical payload.
    bind_world_value(outcome, tenant_id=tenant_id)
    incident = load_incident_record(
        session=session,
        incident_id=outcome.incident_id,
        tenant_id=tenant_id,
    )

    if incident is None:
        return None

    warnings: list[str] = []
    analysis = _historical_analysis(
        session,
        outcome=outcome,
        warnings=warnings,
        tenant_id=tenant_id,
    )
    profile = build_incident_feature_profile(
        session,
        incident=incident,
        analysis=analysis,
        outcome=outcome,
        outcome_source_data=source,
        historical=True,
        tenant_id=tenant_id,
    )

    return profile.model_copy(
        update={
            "warnings": _deduplicated(
                [
                    *warnings,
                    *profile.warnings,
                ]
            )
        }
    )
