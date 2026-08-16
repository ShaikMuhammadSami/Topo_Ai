from __future__ import annotations

import hashlib
from datetime import (
    datetime,
    timezone,
)
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.models.causal_rca import (
    CausalAnalysisResponse,
)
from app.models.change_events import (
    ChangeEventView,
)
from app.models.incident_outcome import (
    ActionEffectiveness,
    IncidentOutcome,
    IncidentOutcomeUpdate,
    IncidentResponseActionObservation,
    OutcomeFactSource,
    OutcomeRootCause,
    RcaVerdict,
    RecommendationFollowThrough,
    ResponseActionObservationInput,
    ResponseActionResult,
    ResponsePlanActionOutcome,
)
from app.models.recommendations import (
    RecommendationStatus,
)
from app.models.response_plan import (
    IncidentResponsePlan,
)
from app.repositories.causal_analysis_repository import (
    latest_causal_analysis,
    load_causal_analysis,
)
from app.repositories.change_event_repository import (
    change_event_view,
    list_change_events,
    load_change_event,
)
from app.repositories.incident_outcome_repository import (
    load_incident_outcome,
    load_incident_outcome_record,
    outcome_source,
    save_incident_outcome,
)
from app.repositories.incident_record_repository import (
    load_incident_record,
)
from app.repositories.recommendation_repository import (
    load_recommendation,
)
from app.repositories.recovery_repository import (
    list_recovery_verifications,
)
from app.repositories.topology_snapshot_repository import (
    load_topology_snapshot,
)
from app.services.response_plan import (
    build_incident_response_plan,
)


RECOVERY_ATTRIBUTION_SECONDS = 1800


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)

    return str(value)


def _as_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(timezone.utc)


def _parse_time(
    value: str | datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return _as_utc(value)

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

    except (TypeError, ValueError):
        return None

    return _as_utc(parsed)


def _deduplicated(
    values: list[str | None],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        if value is None:
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
    raw = "|".join(
        str(part)
        for part in parts
    )
    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]

    return f"{prefix}:{digest}"


def _action_instance_id(
    incident_id: str,
    action: ResponseActionObservationInput,
) -> str:
    if action.action_instance_id:
        return action.action_instance_id

    return _stable_id(
        "response-action-observation",
        incident_id,
        action.response_plan_action_id or "",
        action.change_event_id or "",
        action.action_type.casefold(),
        action.title.casefold(),
        (
            action.completed_at.isoformat()
            if action.completed_at
            else ""
        ),
    )


def _normalize_manual_update(
    incident_id: str,
    update: IncidentOutcomeUpdate,
) -> IncidentOutcomeUpdate:
    actions = [
        item.model_copy(
            update={
                "action_instance_id": (
                    _action_instance_id(
                        incident_id,
                        item,
                    )
                ),
                "target_entity_ids": (
                    _deduplicated(
                        item.target_entity_ids
                    )
                ),
                "evidence_ids": (
                    _deduplicated(
                        item.evidence_ids
                    )
                ),
            }
        )
        for item in update.actions
    ]

    decisions = []
    seen_decisions: set[str] = set()

    for item in reversed(
        update.recommendation_decisions
    ):
        key = (
            item.response_plan_action_id
            .casefold()
        )

        if key in seen_decisions:
            continue

        seen_decisions.add(key)
        decisions.append(item)

    decisions.reverse()

    return update.model_copy(
        update={
            "actions": actions,
            "recommendation_decisions": (
                decisions
            ),
        }
    )


def _merge_manual_update(
    incident_id: str,
    existing: IncidentOutcomeUpdate,
    incoming: IncidentOutcomeUpdate,
) -> IncidentOutcomeUpdate:
    values = existing.model_dump()

    for field in incoming.model_fields_set:
        if field in {
            "actions",
            "recommendation_decisions",
        }:
            continue

        values[field] = getattr(
            incoming,
            field,
        )

    actions = {
        _action_instance_id(
            incident_id,
            item,
        ): item
        for item in existing.actions
    }

    if "actions" in incoming.model_fields_set:
        for item in incoming.actions:
            actions[
                _action_instance_id(
                    incident_id,
                    item,
                )
            ] = item

    decisions = {
        item.response_plan_action_id:
            item
        for item in (
            existing
            .recommendation_decisions
        )
    }

    if (
        "recommendation_decisions"
        in incoming.model_fields_set
    ):
        for item in (
            incoming
            .recommendation_decisions
        ):
            decisions[
                item.response_plan_action_id
            ] = item

    values["actions"] = list(
        actions.values()
    )
    values["recommendation_decisions"] = (
        list(decisions.values())
    )

    return _normalize_manual_update(
        incident_id,
        IncidentOutcomeUpdate.model_validate(
            values
        ),
    )


def _capture_plan(
    plan: IncidentResponsePlan,
) -> dict[str, Any]:
    actions = [
        item.model_dump(mode="json")
        for item in [
            *plan.recommended_actions,
            *plan.validation_checks,
        ]
    ]

    return {
        "reference": (
            "response-plan:"
            f"{plan.causal_analysis_id}"
        ),
        "causal_analysis_id": (
            plan.causal_analysis_id
        ),
        "root_cause": (
            plan.root_cause.model_dump(
                mode="json"
            )
        ),
        "actions": actions,
        "rollback_candidate": (
            plan.rollback_candidate.model_dump(
                mode="json"
            )
        ),
    }


def _analysis_and_plan(
    session: Session,
    *,
    incident_id: str,
    source: dict[str, Any],
    warnings: list[str],
) -> tuple[
    CausalAnalysisResponse | None,
    dict[str, Any] | None,
]:
    stored_analysis_id = source.get(
        "causal_analysis_id"
    )

    analysis = None

    if isinstance(stored_analysis_id, str):
        analysis = load_causal_analysis(
            session,
            analysis_id=stored_analysis_id,
        )

        if analysis is None:
            warnings.append(
                "The causal analysis pinned by "
                "the stored outcome is unavailable: "
                f"{stored_analysis_id}"
            )

    else:
        analysis = latest_causal_analysis(
            session,
            incident_id=incident_id,
        )

    plan_snapshot = source.get(
        "response_plan"
    )

    if not isinstance(plan_snapshot, dict):
        plan_snapshot = None

    if analysis is None:
        warnings.append(
            "No causal analysis available."
        )
        warnings.append(
            "No response plan available."
        )
        return None, plan_snapshot

    source.setdefault(
        "causal_analysis_id",
        analysis.analysis_id,
    )

    if plan_snapshot is None:
        try:
            plan = build_incident_response_plan(
                session=session,
                incident_id=incident_id,
            )

        except ValueError as exc:
            warnings.append(
                "No response plan available: "
                f"{exc}"
            )

        else:
            if (
                plan.causal_analysis_id
                == analysis.analysis_id
            ):
                plan_snapshot = _capture_plan(
                    plan
                )
                source["response_plan"] = (
                    plan_snapshot
                )

            else:
                warnings.append(
                    "The available response plan "
                    "references a different causal "
                    "analysis and was not used."
                )

    return analysis, plan_snapshot


def _original_root_cause(
    analysis: CausalAnalysisResponse | None,
    plan: dict[str, Any] | None,
) -> OutcomeRootCause | None:
    if analysis is None:
        return None

    hypothesis = analysis.top_hypothesis

    if hypothesis is None:
        return None

    root = (
        plan.get("root_cause", {})
        if plan
        else {}
    )

    if not isinstance(root, dict):
        root = {}

    return OutcomeRootCause(
        event_id=hypothesis.root_event_id,
        entity_id=(
            root.get("entity_id")
            or hypothesis.affected_entity_id
        ),
        event_source=hypothesis.root_source,
        title=hypothesis.root_title,
        source=OutcomeFactSource.INFERRED,
        evidence_ids=_deduplicated(
            hypothesis.supporting_evidence_ids
        ),
    )


def _historical_topology_warnings(
    session: Session,
    *,
    analysis: CausalAnalysisResponse | None,
    root_entity_id: str | None,
) -> list[str]:
    if analysis is None:
        return []

    if not analysis.topology_snapshot_id:
        return [
            "Historical topology unavailable: the "
            "causal analysis does not reference a "
            "topology snapshot."
        ]

    snapshot = load_topology_snapshot(
        session=session,
        snapshot_id=(
            analysis.topology_snapshot_id
        ),
    )

    if snapshot is None:
        return [
            "Historical topology unavailable: "
            f"{analysis.topology_snapshot_id}"
        ]

    if root_entity_id and not any(
        entity.id == root_entity_id
        for entity in snapshot.entities
    ):
        return [
            "The original root entity was not "
            "found in the topology snapshot "
            "referenced by the causal analysis: "
            f"{root_entity_id}"
        ]

    return []


def _change_event_for_action(
    session: Session,
    *,
    event_id: str | None,
) -> ChangeEventView | None:
    if not event_id:
        return None

    record = load_change_event(
        session,
        event_id=event_id,
    )

    if record is None:
        return None

    return change_event_view(
        session,
        record=record,
    )


def _base_effectiveness(
    *,
    result: ResponseActionResult,
    recovery_confirmed: bool | None,
) -> tuple[
    ActionEffectiveness,
    str,
]:
    if recovery_confirmed is True:
        return (
            ActionEffectiveness.EFFECTIVE,
            "A responder or durable recovery "
            "record explicitly confirmed recovery.",
        )

    if recovery_confirmed is False:
        return (
            ActionEffectiveness.INEFFECTIVE,
            "A responder or durable recovery "
            "record explicitly reported no recovery.",
        )

    if result in {
        ResponseActionResult.FAILED,
        ResponseActionResult.NO_EFFECT,
    }:
        return (
            ActionEffectiveness.INEFFECTIVE,
            "The recorded action result does not "
            "support incident recovery.",
        )

    return (
        ActionEffectiveness.UNKNOWN,
        "Action completion alone does not prove "
        "that the action resolved the incident.",
    )


def _manual_observation(
    session: Session,
    *,
    incident_id: str,
    item: ResponseActionObservationInput,
    warnings: list[str],
) -> IncidentResponseActionObservation:
    event = _change_event_for_action(
        session,
        event_id=item.change_event_id,
    )

    if item.change_event_id and event is None:
        warnings.append(
            "A recorded response action references "
            "a missing change event: "
            f"{item.change_event_id}"
        )

    targets = list(item.target_entity_ids)
    evidence_ids = list(item.evidence_ids)
    completed_at = item.completed_at
    actor = item.actor

    if event is not None:
        targets.extend(
            link.entity_id
            for link in event.links
        )
        evidence_ids.append(event.event_id)
        completed_at = (
            completed_at
            or _parse_time(event.occurred_at)
        )
        actor = actor or event.actor

    effectiveness, reason = (
        _base_effectiveness(
            result=item.result,
            recovery_confirmed=(
                item.recovery_confirmed
            ),
        )
    )

    return IncidentResponseActionObservation(
        action_instance_id=(
            _action_instance_id(
                incident_id,
                item,
            )
        ),
        response_plan_action_id=(
            item.response_plan_action_id
        ),
        change_event_id=item.change_event_id,
        action_type=item.action_type,
        title=item.title,
        actor=actor,
        source=item.source,
        started_at=(
            _parse_time(item.started_at)
        ),
        completed_at=(
            _parse_time(completed_at)
        ),
        target_entity_ids=_deduplicated(
            targets
        ),
        result=item.result,
        recovery_confirmed=(
            item.recovery_confirmed
        ),
        effectiveness=effectiveness,
        effectiveness_reason=reason,
        notes=item.notes,
        evidence_ids=_deduplicated(
            evidence_ids
        ),
    )


def _metadata_bool(
    value: Any,
) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "confirmed",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "not_confirmed",
        }:
            return False

    return None


def _result_from_value(
    value: Any,
) -> ResponseActionResult:
    try:
        return ResponseActionResult(
            str(value).lower()
        )

    except ValueError:
        return ResponseActionResult.UNKNOWN


def _auto_change_observations(
    session: Session,
    *,
    incident,
    incident_id: str,
    plan: dict[str, Any] | None,
    root_entity_id: str | None,
    end_at: datetime,
) -> list[IncidentResponseActionObservation]:
    plan_action_ids = {
        str(item.get("action_id"))
        for item in (
            plan.get("actions", [])
            if plan
            else []
        )
        if isinstance(item, dict)
        and item.get("action_id")
    }

    events = list_change_events(
        session,
        cluster_name=incident.cluster_name,
        namespace=incident.namespace,
        occurred_after=(
            _as_utc(
                incident.first_observed_at
            ).isoformat()
        ),
        occurred_before=end_at.isoformat(),
        limit=500,
    )

    result: list[
        IncidentResponseActionObservation
    ] = []

    for event in events:
        metadata = event.metadata
        plan_action_id = metadata.get(
            "response_plan_action_id"
        )
        linked_ids = [
            link.entity_id
            for link in event.links
        ]

        explicitly_related = (
            metadata.get("incident_id")
            == incident_id
            or (
                isinstance(
                    plan_action_id,
                    str,
                )
                and plan_action_id
                in plan_action_ids
            )
            or metadata.get(
                "response_action"
            ) is True
            or metadata.get(
                "remediation"
            ) is True
        )

        if not explicitly_related:
            continue

        action_type = str(
            metadata.get("action_type")
            or _enum_value(event.kind)
        )
        action_result = _result_from_value(
            metadata.get("action_result")
            or metadata.get("result")
            or "unknown"
        )
        recovery_confirmed = _metadata_bool(
            metadata.get(
                "recovery_confirmed"
            )
        )
        effectiveness, reason = (
            _base_effectiveness(
                result=action_result,
                recovery_confirmed=(
                    recovery_confirmed
                ),
            )
        )

        targets = _deduplicated(
            [
                *linked_ids,
                (
                    root_entity_id
                    if metadata.get(
                        "target_entity_id"
                    ) == root_entity_id
                    else None
                ),
            ]
        )

        result.append(
            IncidentResponseActionObservation(
                action_instance_id=_stable_id(
                    "response-action-observation",
                    incident_id,
                    event.event_id,
                ),
                response_plan_action_id=(
                    str(plan_action_id)
                    if plan_action_id
                    else None
                ),
                change_event_id=event.event_id,
                action_type=action_type,
                title=event.title,
                actor=event.actor,
                source=(
                    OutcomeFactSource
                    .CHANGE_EVENT.value
                ),
                completed_at=(
                    _parse_time(
                        event.occurred_at
                    )
                ),
                target_entity_ids=targets,
                result=action_result,
                recovery_confirmed=(
                    recovery_confirmed
                ),
                effectiveness=effectiveness,
                effectiveness_reason=reason,
                evidence_ids=[event.event_id],
            )
        )

    return result


def _legacy_observation(
    session: Session,
    *,
    incident,
) -> tuple[
    IncidentResponseActionObservation | None,
    datetime | None,
]:
    recommendation_id = (
        incident.latest_recommendation_id
    )

    if not recommendation_id:
        return None, None

    recommendation = load_recommendation(
        session=session,
        recommendation_id=(
            recommendation_id
        ),
    )

    if (
        recommendation is None
        or recommendation.status
        != RecommendationStatus.APPLIED
        or recommendation.applied_at is None
    ):
        return None, None

    verifications = list_recovery_verifications(
        session=session,
        recommendation_id=(
            recommendation_id
        ),
        limit=100,
    )
    latest = (
        verifications[0]
        if verifications
        else None
    )

    recovery_confirmed = None
    result = ResponseActionResult.UNKNOWN
    evidence_ids = [recommendation_id]
    mitigated_at = None

    if latest is not None:
        evidence_ids.append(
            latest.verification_id
        )

        if latest.status.value == "verified":
            recovery_confirmed = True
            result = (
                ResponseActionResult.SUCCESSFUL
            )
            mitigated_at = _as_utc(
                latest.generated_at
            )

        elif latest.status.value == "failed":
            recovery_confirmed = False
            result = ResponseActionResult.NO_EFFECT

    effectiveness, reason = (
        _base_effectiveness(
            result=result,
            recovery_confirmed=(
                recovery_confirmed
            ),
        )
    )

    return (
        IncidentResponseActionObservation(
            action_instance_id=_stable_id(
                "response-action-observation",
                incident.incident_id,
                recommendation_id,
            ),
            action_type=(
                recommendation
                .action_type.value
            ),
            title=recommendation.title,
            actor=None,
            source=(
                OutcomeFactSource
                .LEGACY_RECOMMENDATION.value
            ),
            started_at=(
                _as_utc(
                    recommendation.applied_at
                )
            ),
            completed_at=(
                _as_utc(
                    recommendation.applied_at
                )
            ),
            target_entity_ids=(
                _deduplicated(
                    [
                        recommendation
                        .target_entity_id
                    ]
                )
            ),
            result=result,
            recovery_confirmed=(
                recovery_confirmed
            ),
            effectiveness=effectiveness,
            effectiveness_reason=reason,
            evidence_ids=evidence_ids,
        ),
        mitigated_at,
    )


def _reversal_target(
    event: ChangeEventView | None,
) -> str | None:
    if event is None:
        return None

    for key in (
        "rollback_of_event_id",
        "reverts_event_id",
        "reverted_event_id",
        "original_event_id",
    ):
        value = event.metadata.get(key)

        if isinstance(value, str) and value:
            return value

    return None


def _is_rollback(
    action: IncidentResponseActionObservation,
) -> bool:
    value = (
        f"{action.action_type} {action.title}"
        .casefold()
    )

    return any(
        token in value
        for token in (
            "rollback",
            "roll back",
            "revert",
            "restore previous",
        )
    )


def _plan_action_map(
    plan: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if plan is None:
        return {}

    return {
        str(item["action_id"]): item
        for item in plan.get("actions", [])
        if isinstance(item, dict)
        and item.get("action_id")
    }


def _match_plan_actions(
    session: Session,
    *,
    actions: list[
        IncidentResponseActionObservation
    ],
    plan: dict[str, Any] | None,
    original: OutcomeRootCause | None,
    warnings: list[str],
) -> list[IncidentResponseActionObservation]:
    action_map = _plan_action_map(plan)
    rollback_ids = [
        action_id
        for action_id, item
        in action_map.items()
        if item.get("category")
        == "rollback_candidate"
    ]

    target_event_id = None

    if plan:
        root = plan.get("root_cause", {})

        if isinstance(root, dict):
            target_event_id = root.get(
                "target_event_id"
            )

    result = []

    for action in actions:
        plan_id = (
            action.response_plan_action_id
        )

        if plan_id and plan_id not in action_map:
            warnings.append(
                "A recorded response action "
                "references an action ID that is "
                "not present in the pinned response "
                f"plan: {plan_id}"
            )
            plan_id = None

        if (
            plan_id is None
            and len(rollback_ids) == 1
            and _is_rollback(action)
        ):
            event = _change_event_for_action(
                session,
                event_id=action.change_event_id,
            )
            reversal = _reversal_target(event)
            entity_overlap = bool(
                original
                and original.entity_id
                and original.entity_id
                in action.target_entity_ids
            )

            if (
                reversal
                and reversal == target_event_id
            ) or entity_overlap:
                plan_id = rollback_ids[0]

        result.append(
            action.model_copy(
                update={
                    "response_plan_action_id": (
                        plan_id
                    )
                }
            )
        )

    return result


def _attribute_recovery(
    session: Session,
    *,
    actions: list[
        IncidentResponseActionObservation
    ],
    mitigated_at: datetime | None,
    original: OutcomeRootCause | None,
    plan: dict[str, Any] | None,
    warnings: list[str],
) -> list[IncidentResponseActionObservation]:
    if mitigated_at is None:
        return actions

    target_event_id = None

    if plan:
        root = plan.get("root_cause", {})

        if isinstance(root, dict):
            target_event_id = root.get(
                "target_event_id"
            )

    candidates = []

    for action in actions:
        if (
            action.effectiveness
            != ActionEffectiveness.UNKNOWN
            or action.result
            != ResponseActionResult.SUCCESSFUL
            or not action.completed_at
            or not _is_rollback(action)
        ):
            continue

        completed_at = _as_utc(
            action.completed_at
        )
        delta = (
            mitigated_at - completed_at
        ).total_seconds()

        if not (
            0 <= delta
            <= RECOVERY_ATTRIBUTION_SECONDS
        ):
            continue

        event = _change_event_for_action(
            session,
            event_id=action.change_event_id,
        )
        reversal = _reversal_target(event)
        entity_overlap = bool(
            original
            and original.entity_id
            and original.entity_id
            in action.target_entity_ids
        )
        plan_match = bool(
            action.response_plan_action_id
            and _plan_action_map(plan).get(
                action.response_plan_action_id,
                {},
            ).get("category")
            == "rollback_candidate"
        )

        if (
            entity_overlap
            and (
                plan_match
                or (
                    reversal
                    and reversal
                    == target_event_id
                )
            )
        ):
            candidates.append(action)

    if len(candidates) > 1:
        warnings.append(
            "Multiple simultaneous mitigation "
            "actions prevent reliable attribution."
        )
        return actions

    if len(candidates) != 1:
        return actions

    selected_id = (
        candidates[0].action_instance_id
    )

    return [
        (
            action.model_copy(
                update={
                    "effectiveness": (
                        ActionEffectiveness
                        .EFFECTIVE
                    ),
                    "effectiveness_reason": (
                        "A single recorded rollback "
                        "targeted the original causal "
                        "entity/change and preceded the "
                        "mitigation milestone. This uses "
                        "target, reversal, and recovery "
                        "evidence rather than timing alone."
                    ),
                }
            )
            if action.action_instance_id
            == selected_id
            else action
        )
        for action in actions
    ]


def _recommendation_outcomes(
    *,
    actions: list[
        IncidentResponseActionObservation
    ],
    plan: dict[str, Any] | None,
    manual: IncidentOutcomeUpdate,
    warnings: list[str],
) -> list[ResponsePlanActionOutcome]:
    action_map = _plan_action_map(plan)
    decisions = {
        item.response_plan_action_id:
            item
        for item in (
            manual.recommendation_decisions
        )
    }
    matched: dict[
        str,
        list[IncidentResponseActionObservation],
    ] = {}

    for action in actions:
        if action.response_plan_action_id:
            matched.setdefault(
                action.response_plan_action_id,
                [],
            ).append(action)

    results = []

    for action_id, plan_action in sorted(
        action_map.items(),
        key=lambda item: (
            int(item[1].get("sequence", 0)),
            item[0],
        ),
    ):
        observations = matched.get(
            action_id,
            [],
        )
        decision = decisions.get(action_id)

        if observations:
            follow_through = (
                RecommendationFollowThrough
                .FOLLOWED
            )

            if (
                decision
                and decision.follow_through
                == RecommendationFollowThrough
                .NOT_FOLLOWED
            ):
                warnings.append(
                    "Conflicting follow-through "
                    "evidence exists for response "
                    f"plan action: {action_id}"
                )

        elif decision is not None:
            follow_through = (
                decision.follow_through
            )

        else:
            follow_through = (
                RecommendationFollowThrough
                .UNKNOWN
            )

        if any(
            item.effectiveness
            == ActionEffectiveness.EFFECTIVE
            for item in observations
        ):
            effectiveness = (
                ActionEffectiveness.EFFECTIVE
            )

        elif (
            observations
            and all(
                item.effectiveness
                == ActionEffectiveness.INEFFECTIVE
                for item in observations
            )
        ):
            effectiveness = (
                ActionEffectiveness.INEFFECTIVE
            )

        else:
            effectiveness = (
                ActionEffectiveness.UNKNOWN
            )

        evidence_ids = _deduplicated(
            [
                *(
                    decision.evidence_ids
                    if decision
                    else []
                ),
                *[
                    value
                    for observation
                    in observations
                    for value in (
                        observation.evidence_ids
                    )
                ],
            ]
        )

        if observations:
            reason = (
                "Durable responder/action evidence "
                "matched this response-plan action."
            )
        elif decision is not None:
            reason = (
                decision.reason
                or "A responder recorded the "
                "follow-through decision."
            )
        else:
            reason = (
                "No durable evidence establishes "
                "whether this recommendation was "
                "followed."
            )

        results.append(
            ResponsePlanActionOutcome(
                response_plan_action_id=(
                    action_id
                ),
                title=str(
                    plan_action.get("title")
                    or action_id
                ),
                category=str(
                    plan_action.get("category")
                    or "unknown"
                ),
                follow_through=(
                    follow_through
                ),
                effectiveness=effectiveness,
                matched_action_instance_ids=[
                    item.action_instance_id
                    for item in observations
                ],
                evidence_ids=evidence_ids,
                reason=reason,
            )
        )

    return results


def _duration(
    *,
    started_at: datetime,
    milestone: datetime | None,
    label: str,
    warnings: list[str],
) -> int | None:
    if milestone is None:
        warnings.append(
            f"{label} timestamp unavailable."
        )
        return None

    seconds = int(
        (
            _as_utc(milestone)
            - _as_utc(started_at)
        ).total_seconds()
    )

    if seconds < 0:
        warnings.append(
            f"Invalid {label.lower()} timestamp "
            "order; a negative duration was not "
            "returned."
        )
        return None

    return seconds


def _verdict(
    session: Session,
    *,
    manual: IncidentOutcomeUpdate,
    original: OutcomeRootCause | None,
    primary: (
        IncidentResponseActionObservation
        | None
    ),
    plan: dict[str, Any] | None,
) -> tuple[
    RcaVerdict,
    float,
    OutcomeRootCause | None,
]:
    reported = manual.final_root_cause

    if reported is not None:
        final = OutcomeRootCause(
            event_id=reported.event_id,
            entity_id=reported.entity_id,
            event_source=(
                reported.event_source
            ),
            title=reported.title,
            source=OutcomeFactSource.RESPONDER,
            evidence_ids=_deduplicated(
                reported.evidence_ids
            ),
        )

        if manual.rca_verdict is not None:
            return (
                manual.rca_verdict,
                manual.rca_confidence
                if manual.rca_confidence
                is not None
                else 0.9,
                final,
            )

        if original is None:
            return (
                RcaVerdict.INCONCLUSIVE,
                manual.rca_confidence or 0.0,
                final,
            )

        same_event = bool(
            reported.event_id
            and original.event_id
            and reported.event_id
            == original.event_id
        )
        same_entity = bool(
            reported.entity_id
            and original.entity_id
            and reported.entity_id
            == original.entity_id
        )

        if same_event and (
            same_entity
            or not reported.entity_id
            or not original.entity_id
        ):
            verdict = RcaVerdict.CONFIRMED
            confidence = 0.95

        elif same_event or same_entity:
            verdict = (
                RcaVerdict
                .PARTIALLY_CONFIRMED
            )
            confidence = 0.75

        else:
            verdict = RcaVerdict.NOT_CONFIRMED
            confidence = 0.9

        return (
            verdict,
            manual.rca_confidence
            if manual.rca_confidence
            is not None
            else confidence,
            final,
        )

    if manual.rca_verdict is not None:
        return (
            manual.rca_verdict,
            manual.rca_confidence
            if manual.rca_confidence
            is not None
            else 0.9,
            original
            if manual.rca_verdict
            in {
                RcaVerdict.CONFIRMED,
                RcaVerdict
                .PARTIALLY_CONFIRMED,
            }
            else None,
        )

    if (
        original is None
        or primary is None
        or primary.effectiveness
        != ActionEffectiveness.EFFECTIVE
        or not _is_rollback(primary)
    ):
        return (
            RcaVerdict.INCONCLUSIVE,
            0.0,
            None,
        )

    event = _change_event_for_action(
        session,
        event_id=primary.change_event_id,
    )
    reversal = _reversal_target(event)
    target_event_id = None

    if plan:
        root = plan.get("root_cause", {})

        if isinstance(root, dict):
            target_event_id = root.get(
                "target_event_id"
            )

    same_entity = bool(
        original.entity_id
        and original.entity_id
        in primary.target_entity_ids
    )

    if (
        same_entity
        and reversal
        and reversal == target_event_id
    ):
        return (
            RcaVerdict.CONFIRMED,
            0.9,
            original.model_copy(
                update={
                    "source": (
                        OutcomeFactSource.INFERRED
                    ),
                    "evidence_ids": (
                        _deduplicated(
                            [
                                *original
                                .evidence_ids,
                                *primary
                                .evidence_ids,
                            ]
                        )
                    ),
                }
            ),
        )

    if same_entity:
        return (
            RcaVerdict.PARTIALLY_CONFIRMED,
            0.65,
            original,
        )

    return (
        RcaVerdict.INCONCLUSIVE,
        0.0,
        None,
    )


def _resolution_summary(
    *,
    manual: IncidentOutcomeUpdate,
    incident_status: str,
    incident_status_note: str | None,
    verdict: RcaVerdict,
    primary: (
        IncidentResponseActionObservation
        | None
    ),
) -> str:
    if manual.resolution_summary:
        return manual.resolution_summary

    if (
        incident_status == "resolved"
        and incident_status_note
    ):
        return incident_status_note

    if primary is not None:
        return (
            f"The recorded primary resolution "
            f"action was '{primary.title}'. Its "
            f"effectiveness is classified as "
            f"'{primary.effectiveness.value}', and "
            f"the original RCA outcome is "
            f"'{verdict.value}'."
        )

    if incident_status == "resolved":
        return (
            "The incident is marked resolved, but "
            "no primary resolution action can be "
            "established from the stored evidence."
        )

    return (
        "Outcome tracking is in progress. The "
        "stored evidence does not yet establish a "
        "primary resolution action."
    )


def _derive_outcome(
    session: Session,
    *,
    incident_id: str,
    manual: IncidentOutcomeUpdate,
    source: dict[str, Any],
) -> IncidentOutcome:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    warnings: list[str] = []
    analysis, plan = _analysis_and_plan(
        session,
        incident_id=incident_id,
        source=source,
        warnings=warnings,
    )
    original = _original_root_cause(
        analysis,
        plan,
    )

    warnings.extend(
        _historical_topology_warnings(
            session,
            analysis=analysis,
            root_entity_id=(
                original.entity_id
                if original
                else None
            ),
        )
    )

    started_at = _as_utc(
        incident.first_observed_at
    )
    end_at = _as_utc(
        manual.resolved_at
        or manual.mitigated_at
        or incident.updated_at
    )

    actions = [
        _manual_observation(
            session,
            incident_id=incident_id,
            item=item,
            warnings=warnings,
        )
        for item in manual.actions
    ]

    actions.extend(
        _auto_change_observations(
            session,
            incident=incident,
            incident_id=incident_id,
            plan=plan,
            root_entity_id=(
                original.entity_id
                if original
                else None
            ),
            end_at=end_at,
        )
    )

    legacy, legacy_mitigated_at = (
        _legacy_observation(
            session,
            incident=incident,
        )
    )

    if legacy is not None:
        actions.append(legacy)

    # Manual observations outrank derived records,
    # while shared change-event references collapse
    # to a single action instance.
    by_key: dict[str, Any] = {}

    for action in reversed(actions):
        key = (
            f"event:{action.change_event_id}"
            if action.change_event_id
            else (
                "action:"
                f"{action.action_instance_id}"
            )
        )
        by_key[key] = action

    actions = sorted(
        by_key.values(),
        key=lambda item: (
            item.completed_at
            or item.started_at
            or started_at,
            item.action_instance_id,
        ),
    )

    if not actions:
        warnings.append(
            "No responder actions recorded."
        )

    mitigated_at = _parse_time(
        manual.mitigated_at
        or legacy_mitigated_at
    )
    resolved_at = _parse_time(
        manual.resolved_at
    )

    actions = _match_plan_actions(
        session,
        actions=actions,
        plan=plan,
        original=original,
        warnings=warnings,
    )
    actions = _attribute_recovery(
        session,
        actions=actions,
        mitigated_at=mitigated_at,
        original=original,
        plan=plan,
        warnings=warnings,
    )

    primary = None

    if manual.primary_resolution_action_id:
        primary = next(
            (
                item
                for item in actions
                if item.action_instance_id
                == manual
                .primary_resolution_action_id
            ),
            None,
        )

        if primary is None:
            warnings.append(
                "The responder-selected primary "
                "resolution action was not found: "
                f"{manual.primary_resolution_action_id}"
            )

    if primary is None:
        effective = [
            item
            for item in actions
            if item.effectiveness
            == ActionEffectiveness.EFFECTIVE
        ]

        if len(effective) == 1:
            primary = effective[0]

        elif len(effective) > 1:
            warnings.append(
                "Multiple actions are confirmed as "
                "effective; no single primary "
                "resolution action was inferred."
            )

    plan_outcomes = _recommendation_outcomes(
        actions=actions,
        plan=plan,
        manual=manual,
        warnings=warnings,
    )
    verdict, verdict_confidence, final = (
        _verdict(
            session,
            manual=manual,
            original=original,
            primary=primary,
            plan=plan,
        )
    )

    mitigation_seconds = _duration(
        started_at=started_at,
        milestone=mitigated_at,
        label="Mitigation",
        warnings=warnings,
    )
    resolution_seconds = _duration(
        started_at=started_at,
        milestone=resolved_at,
        label="Resolution",
        warnings=warnings,
    )

    if (
        mitigated_at
        and resolved_at
        and mitigated_at > resolved_at
    ):
        warnings.append(
            "Mitigation occurs after resolution; "
            "time to mitigation was not returned."
        )
        mitigation_seconds = None

    followed = [
        item.response_plan_action_id
        for item in plan_outcomes
        if item.follow_through
        == RecommendationFollowThrough.FOLLOWED
    ]
    not_followed = [
        item.response_plan_action_id
        for item in plan_outcomes
        if item.follow_through
        == RecommendationFollowThrough
        .NOT_FOLLOWED
    ]
    unknown = [
        item.response_plan_action_id
        for item in plan_outcomes
        if item.follow_through
        == RecommendationFollowThrough.UNKNOWN
    ]

    evidence_event_ids = _deduplicated(
        [
            (
                original.event_id
                if original
                else None
            ),
            (
                final.event_id
                if final
                else None
            ),
            *[
                item.change_event_id
                for item in actions
            ],
        ]
    )
    evidence_ids = _deduplicated(
        [
            *(
                original.evidence_ids
                if original
                else []
            ),
            *(
                final.evidence_ids
                if final
                else []
            ),
            *[
                value
                for item in actions
                for value in item.evidence_ids
            ],
            *[
                value
                for item in plan_outcomes
                for value in item.evidence_ids
            ],
        ]
    )

    return IncidentOutcome(
        outcome_id=_stable_id(
            "incident-outcome",
            incident_id,
        ),
        incident_id=incident_id,
        status=incident.status,
        causal_analysis_id=(
            analysis.analysis_id
            if analysis
            else None
        ),
        response_plan_reference=(
            str(plan.get("reference"))
            if plan
            and plan.get("reference")
            else None
        ),
        historical_topology_snapshot_id=(
            analysis.topology_snapshot_id
            if analysis
            else None
        ),
        started_at=started_at,
        mitigated_at=mitigated_at,
        resolved_at=resolved_at,
        time_to_mitigation_seconds=(
            mitigation_seconds
        ),
        time_to_resolution_seconds=(
            resolution_seconds
        ),
        original_root_cause=original,
        final_root_cause=final,
        rca_verdict=verdict,
        rca_confidence=(
            verdict_confidence
        ),
        resolution_summary=(
            _resolution_summary(
                manual=manual,
                incident_status=(
                    incident.status.value
                ),
                incident_status_note=(
                    getattr(
                        incident,
                        "status_note",
                        None,
                    )
                ),
                verdict=verdict,
                primary=primary,
            )
        ),
        actions_taken=actions,
        primary_resolution_action=primary,
        response_plan_actions=(
            plan_outcomes
        ),
        recommendations_followed=followed,
        recommendations_not_followed=(
            not_followed
        ),
        recommendations_unknown=unknown,
        effective_action_ids=[
            item.action_instance_id
            for item in actions
            if item.effectiveness
            == ActionEffectiveness.EFFECTIVE
        ],
        ineffective_action_ids=[
            item.action_instance_id
            for item in actions
            if item.effectiveness
            == ActionEffectiveness.INEFFECTIVE
        ],
        evidence_event_ids=(
            evidence_event_ids
        ),
        evidence_ids=evidence_ids,
        warnings=_deduplicated(warnings),
    )


def analyze_incident_outcome(
    session: Session,
    *,
    incident_id: str,
) -> IncidentOutcome:
    source: dict[str, Any] = {}
    manual = IncidentOutcomeUpdate()

    return _derive_outcome(
        session,
        incident_id=incident_id,
        manual=manual,
        source=source,
    )


def get_incident_outcome(
    session: Session,
    *,
    incident_id: str,
) -> IncidentOutcome:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    stored = load_incident_outcome(
        session,
        incident_id=incident_id,
    )

    if stored is not None:
        return stored

    return analyze_incident_outcome(
        session,
        incident_id=incident_id,
    )


def record_incident_outcome(
    session: Session,
    *,
    incident_id: str,
    update: IncidentOutcomeUpdate,
) -> IncidentOutcome:
    incident = load_incident_record(
        session=session,
        incident_id=incident_id,
    )

    if incident is None:
        raise ValueError(
            f"Incident not found: {incident_id}"
        )

    record = load_incident_outcome_record(
        session,
        incident_id=incident_id,
    )
    source = (
        outcome_source(record)
        if record is not None
        else {}
    )

    existing_manual = (
        IncidentOutcomeUpdate.model_validate(
            source.get("manual", {})
        )
    )
    merged = _merge_manual_update(
        incident_id,
        existing_manual,
        update,
    )
    merged_json = merged.model_dump(
        mode="json"
    )

    source["manual"] = merged_json
    outcome = _derive_outcome(
        session,
        incident_id=incident_id,
        manual=merged,
        source=source,
    )

    save_incident_outcome(
        session,
        outcome=outcome,
        source=source,
    )

    return outcome
