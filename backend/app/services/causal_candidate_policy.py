from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from app.models.causal_candidates import (
    CAUSAL_CANDIDATE_POLICY_VERSION,
    CausalCandidateDecision,
    CausalCandidateEligibility,
    CausalCandidateRole,
    CausalCandidateSelectionAudit,
)
from app.models.change_events import (
    ChangeEventKind,
    ChangeEventSource,
    IncidentChangeCandidate,
)
from app.models.changes import ChangeCategory, ChangeType


RELATIONSHIP_CHANGE_TYPES = frozenset(
    {
        ChangeType.RELATIONSHIP_ADDED.value,
        ChangeType.RELATIONSHIP_REMOVED.value,
        ChangeType.RELATIONSHIP_UPDATED.value,
    }
)

ENTITY_CHANGE_TYPES = frozenset(
    {
        ChangeType.ENTITY_ADDED.value,
        ChangeType.ENTITY_REMOVED.value,
        ChangeType.ENTITY_UPDATED.value,
    }
)

# These are stable operator/control resources in the topology model. Their
# material snapshot mutations can be causal even when the upstream provider
# receipt is unavailable.
KUBERNETES_MUTABLE_RESOURCE_KINDS = frozenset(
    {
        "kubernetesconfigmap",
        "kubernetescronjob",
        "kubernetesdaemonset",
        "kubernetesdeployment",
        "kubernetesingress",
        "kubernetesjob",
        "kubernetesnetworkpolicy",
        "kubernetessecret",
        "kubernetesservice",
        "kubernetesstatefulset",
    }
)

# Controller-created or runtime membership objects are consequences by
# default. A future source-native integration can supply a distinct initiating
# control-plane mutation rather than promoting their observed lifecycle churn.
KUBERNETES_GENERATED_RESOURCE_KINDS = frozenset(
    {
        "kubernetescontrollerrevision",
        "kubernetesendpointslice",
        "kubernetespod",
        "kubernetesreplicaset",
    }
)

STRUCTURAL_RESOURCE_KINDS = frozenset(
    {
        "kubernetescluster",
        "kubernetesnamespace",
        "kubernetesnode",
    }
)

ARTIFACT_RESOURCE_KINDS = frozenset({"containerimage"})

MATERIAL_RESOURCE_CATEGORIES = frozenset(
    {
        ChangeCategory.DEPLOYMENT.value,
        ChangeCategory.SCALING.value,
        ChangeCategory.IMAGE.value,
        ChangeCategory.CONFIGURATION.value,
        ChangeCategory.SERVICE.value,
        ChangeCategory.NETWORKING.value,
    }
)

DERIVED_RESOURCE_CATEGORIES = frozenset(
    {
        ChangeCategory.RUNTIME.value,
        ChangeCategory.TOPOLOGY.value,
    }
)

SOURCE_NATIVE_SOURCES = frozenset(
    {
        ChangeEventSource.GIT.value,
        ChangeEventSource.GITHUB.value,
        ChangeEventSource.GITLAB.value,
        ChangeEventSource.CI.value,
        ChangeEventSource.CD.value,
        ChangeEventSource.GITHUB_ACTIONS.value,
        ChangeEventSource.JENKINS.value,
        ChangeEventSource.AZURE_DEVOPS.value,
        ChangeEventSource.TERRAFORM.value,
        ChangeEventSource.KUBERNETES.value,
        ChangeEventSource.AWS_CLOUDTRAIL.value,
        ChangeEventSource.AZURE_ACTIVITY_LOG.value,
        ChangeEventSource.GCP_AUDIT_LOG.value,
        ChangeEventSource.MANUAL.value,
    }
)

RUNTIME_SYMPTOM_REASONS = frozenset(
    {
        "backoff",
        "connectionerror",
        "crashloopbackoff",
        "errimagepull",
        "failed",
        "imagepullbackoff",
        "oomkilled",
        "readinessfailed",
        "resourcepressure",
        "unhealthy",
    }
)

KUBERNETES_DERIVED_EVENT_REASONS = frozenset(
    {
        "killing",
        "scalingreplicaset",
        "successfulcreate",
        "successfuldelete",
    }
)

NON_MUTATION_STATUSES = frozenset(
    {
        "cancelled",
        "canceled",
        "no_change",
        "noop",
        "skipped",
    }
)

# Drift tests compare these registries with the source enums and the machine
# contract. Keeping them explicit prevents an added value from falling through
# to a misleading source-mutation default.
HANDLED_CHANGE_TYPES = frozenset(item.value for item in ChangeType)
HANDLED_CHANGE_CATEGORIES = frozenset(item.value for item in ChangeCategory)


@dataclass(frozen=True)
class CausalCandidateSelection:
    selected_candidates: tuple[IncidentChangeCandidate, ...]
    audit: tuple[CausalCandidateSelectionAudit, ...]


def _value(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _metadata(candidate: IncidentChangeCandidate) -> dict:
    value = candidate.event.metadata
    return value if isinstance(value, dict) else {}


def _structured_entity_kinds(
    candidate: IncidentChangeCandidate,
    entity_kind_by_id: Mapping[str, str] | None,
) -> tuple[str, ...]:
    metadata = _metadata(candidate)
    kinds: set[str] = set()

    for side in ("before", "after"):
        value = metadata.get(side)
        if isinstance(value, dict) and value.get("kind"):
            kinds.add(str(value["kind"]).strip().lower())

    refs = metadata.get("entity_refs", [])
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, dict) and ref.get("kind"):
                kinds.add(str(ref["kind"]).strip().lower())

    if entity_kind_by_id:
        for link in candidate.event.links:
            kind = entity_kind_by_id.get(link.entity_id)
            if kind:
                kinds.add(str(kind).strip().lower())

    return tuple(sorted(kinds))


def _decision(
    role: CausalCandidateRole,
    eligibility: CausalCandidateEligibility,
    reason: str,
    inputs: dict,
) -> CausalCandidateDecision:
    return CausalCandidateDecision(
        role=role,
        eligibility=eligibility,
        reason=reason,
        classification_inputs=inputs,
    )


def classify_causal_candidate(
    candidate: IncidentChangeCandidate,
    *,
    entity_kind_by_id: Mapping[str, str] | None = None,
) -> CausalCandidateDecision:
    """Classify one candidate using durable structured fields only."""

    event = candidate.event
    metadata = _metadata(candidate)
    source = _value(event.source)
    event_kind = _value(event.kind)
    change_type = str(metadata.get("change_type") or "").lower()
    category = str(metadata.get("category") or "").lower()
    relationship_type = str(
        metadata.get("relationship_type") or ""
    ).lower()
    reason = str(metadata.get("reason") or "").lower()
    status = str(event.status or "").lower()
    entity_kinds = _structured_entity_kinds(candidate, entity_kind_by_id)

    inputs = {
        "source": source,
        "event_kind": event_kind,
        "change_type": change_type or None,
        "category": category or None,
        "entity_kinds": list(entity_kinds),
        "relationship_type": relationship_type or None,
        "structured_reason": reason or None,
        "status": status or None,
    }

    if status in NON_MUTATION_STATUSES:
        return _decision(
            CausalCandidateRole.LEGACY_OR_UNKNOWN,
            CausalCandidateEligibility.INELIGIBLE,
            "explicit_non_mutation_status",
            inputs,
        )

    if reason in RUNTIME_SYMPTOM_REASONS:
        return _decision(
            CausalCandidateRole.RUNTIME_SYMPTOM,
            CausalCandidateEligibility.SUPPORTING_ONLY,
            "structured_runtime_failure_reason",
            inputs,
        )

    if (
        source == ChangeEventSource.KUBERNETES.value
        and reason in KUBERNETES_DERIVED_EVENT_REASONS
    ):
        return _decision(
            CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE,
            CausalCandidateEligibility.SUPPORTING_ONLY,
            "kubernetes_controller_lifecycle_event",
            inputs,
        )

    # A topology-diff relationship record is an observed graph consequence,
    # regardless of predicate. Provider-native policy/networking mutation
    # events use their native event source and are classified below.
    if source == ChangeEventSource.TOPOLOGY_DIFF.value and (
        change_type in RELATIONSHIP_CHANGE_TYPES
        or bool(metadata.get("relationship_id"))
        or bool(relationship_type)
    ):
        return _decision(
            CausalCandidateRole.DERIVED_TOPOLOGY_CONSEQUENCE,
            CausalCandidateEligibility.SUPPORTING_ONLY,
            "derived_relationship_change",
            inputs,
        )

    if source == ChangeEventSource.TOPOLOGY_DIFF.value:
        if change_type not in HANDLED_CHANGE_TYPES:
            return _decision(
                CausalCandidateRole.LEGACY_OR_UNKNOWN,
                CausalCandidateEligibility.FALLBACK_ELIGIBLE,
                "legacy_missing_change_type",
                inputs,
            )

        if change_type not in ENTITY_CHANGE_TYPES:
            # All currently known non-entity values were handled as
            # relationship consequences above. This branch is deliberately
            # conservative if the enum registry ever drifts.
            return _decision(
                CausalCandidateRole.LEGACY_OR_UNKNOWN,
                CausalCandidateEligibility.INELIGIBLE,
                "unsupported_structured_change_type",
                inputs,
            )

        kind_set = set(entity_kinds)
        if kind_set & KUBERNETES_GENERATED_RESOURCE_KINDS:
            return _decision(
                CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE,
                CausalCandidateEligibility.SUPPORTING_ONLY,
                "generated_runtime_resource_change",
                inputs,
            )

        if kind_set & ARTIFACT_RESOURCE_KINDS:
            return _decision(
                CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE,
                CausalCandidateEligibility.SUPPORTING_ONLY,
                "observed_runtime_artifact_change",
                inputs,
            )

        if kind_set & STRUCTURAL_RESOURCE_KINDS:
            return _decision(
                CausalCandidateRole.DERIVED_TOPOLOGY_CONSEQUENCE,
                CausalCandidateEligibility.SUPPORTING_ONLY,
                "observed_structural_resource_change",
                inputs,
            )

        if (
            kind_set & KUBERNETES_MUTABLE_RESOURCE_KINDS
            or any(
                kind.startswith(("aws", "azure", "gcp"))
                for kind in kind_set
            )
        ):
            return _decision(
                CausalCandidateRole.OBSERVED_RESOURCE_MUTATION,
                CausalCandidateEligibility.PRIMARY_ELIGIBLE,
                "material_mutable_resource_change",
                inputs,
            )

        if category in MATERIAL_RESOURCE_CATEGORIES:
            return _decision(
                CausalCandidateRole.OBSERVED_RESOURCE_MUTATION,
                CausalCandidateEligibility.PRIMARY_ELIGIBLE,
                "material_structured_resource_category",
                inputs,
            )

        if category in DERIVED_RESOURCE_CATEGORIES:
            role = (
                CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE
                if category == ChangeCategory.RUNTIME.value
                else CausalCandidateRole.DERIVED_TOPOLOGY_CONSEQUENCE
            )
            return _decision(
                role,
                CausalCandidateEligibility.SUPPORTING_ONLY,
                "derived_resource_category",
                inputs,
            )

        # OTHER or missing categories with an unrecognized resource kind do
        # not become mutations merely because they came from a snapshot diff.
        return _decision(
            CausalCandidateRole.LEGACY_OR_UNKNOWN,
            CausalCandidateEligibility.FALLBACK_ELIGIBLE,
            "unclassified_structured_resource_change",
            inputs,
        )

    if source in SOURCE_NATIVE_SOURCES:
        kind_set = set(entity_kinds)
        if (
            source == ChangeEventSource.KUBERNETES.value
            and kind_set & KUBERNETES_GENERATED_RESOURCE_KINDS
        ):
            return _decision(
                CausalCandidateRole.DERIVED_RUNTIME_CONSEQUENCE,
                CausalCandidateEligibility.SUPPORTING_ONLY,
                "source_observed_generated_runtime_resource",
                inputs,
            )

        if event_kind == ChangeEventKind.UNKNOWN.value:
            return _decision(
                CausalCandidateRole.LEGACY_OR_UNKNOWN,
                CausalCandidateEligibility.FALLBACK_ELIGIBLE,
                "source_native_unknown_event_kind",
                inputs,
            )

        return _decision(
            CausalCandidateRole.SOURCE_MUTATION,
            CausalCandidateEligibility.PRIMARY_ELIGIBLE,
            "source_native_mutation_event",
            inputs,
        )

    return _decision(
        CausalCandidateRole.LEGACY_OR_UNKNOWN,
        CausalCandidateEligibility.FALLBACK_ELIGIBLE,
        "legacy_or_unknown_source",
        inputs,
    )


def _candidate_timestamp(candidate: IncidentChangeCandidate) -> float:
    temporal = candidate.event.temporal
    if temporal is not None:
        return temporal.effective_at.timestamp()
    try:
        value = datetime.fromisoformat(
            candidate.event.occurred_at.replace("Z", "+00:00")
        )
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    except ValueError:
        return 0.0


def _selection_key(candidate: IncidentChangeCandidate) -> tuple:
    # Score/risk/time are the existing incident-change ordering dimensions.
    # The stable event ID only resolves exact ties deterministically.
    return (
        -candidate.score,
        -candidate.event.risk_score,
        -_candidate_timestamp(candidate),
        candidate.event.event_id,
    )


def select_causal_candidates(
    candidates: Sequence[IncidentChangeCandidate],
    *,
    limit: int,
    entity_kind_by_id: Mapping[str, str] | None = None,
) -> CausalCandidateSelection:
    """Apply causal semantics before the existing hypothesis Top-N limit."""

    considered = list(candidates)
    decisions = {
        candidate.event.event_id: classify_causal_candidate(
            candidate,
            entity_kind_by_id=entity_kind_by_id,
        )
        for candidate in considered
    }

    primary = sorted(
        (
            candidate
            for candidate in considered
            if decisions[candidate.event.event_id].eligibility
            == CausalCandidateEligibility.PRIMARY_ELIGIBLE
        ),
        key=_selection_key,
    )
    fallback = sorted(
        (
            candidate
            for candidate in considered
            if decisions[candidate.event.event_id].eligibility
            == CausalCandidateEligibility.FALLBACK_ELIGIBLE
        ),
        key=_selection_key,
    )

    eligible = primary if primary else fallback
    selected = eligible[:limit]
    eligible_rank = {
        candidate.event.event_id: rank
        for rank, candidate in enumerate(eligible, start=1)
    }
    selected_ids = {candidate.event.event_id for candidate in selected}

    audit: list[CausalCandidateSelectionAudit] = []
    for raw_rank, candidate in enumerate(considered, start=1):
        event_id = candidate.event.event_id
        decision = decisions[event_id]
        rank = eligible_rank.get(event_id)
        selected_for_hypothesis = event_id in selected_ids

        exclusion_reason: str | None = None
        if not selected_for_hypothesis:
            if decision.eligibility == CausalCandidateEligibility.SUPPORTING_ONLY:
                exclusion_reason = decision.reason
            elif decision.eligibility == CausalCandidateEligibility.INELIGIBLE:
                exclusion_reason = decision.reason
            elif (
                decision.eligibility
                == CausalCandidateEligibility.FALLBACK_ELIGIBLE
                and primary
            ):
                exclusion_reason = "primary_candidates_available"
            elif rank is not None and rank > limit:
                exclusion_reason = "outside_hypothesis_candidate_limit"
            else:
                exclusion_reason = "not_selected"

        audit.append(
            CausalCandidateSelectionAudit(
                event_id=event_id,
                origin_change_id=candidate.event.origin_change_id,
                raw_rank=raw_rank,
                raw_score=candidate.score,
                role=decision.role,
                eligibility=decision.eligibility,
                eligible_rank=rank,
                selected_for_hypothesis=selected_for_hypothesis,
                classification_reason=decision.reason,
                exclusion_reason=exclusion_reason,
                classification_inputs=decision.classification_inputs,
                candidate_admission_policy_version=(
                    candidate.candidate_admission_policy_version
                ),
                admission_basis=candidate.admission_basis,
                admission_evidence_refs=candidate.admission_evidence_refs,
                lineage_paths=candidate.lineage_paths,
                container_scope=candidate.container_scope,
                lineage_admission_state=candidate.lineage_admission_state,
                lineage_admission_reason=candidate.lineage_admission_reason,
                mutation_set=candidate.mutation_set,
                mutation_completeness=candidate.mutation_completeness,
            )
        )

    return CausalCandidateSelection(
        selected_candidates=tuple(selected),
        audit=tuple(audit),
    )
