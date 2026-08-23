from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


BLAST_POLICY_VERSION = "blast-impact-v1"


class BlastImpactSemantic(str, Enum):
    DIRECT_FAILURE = "direct_failure"
    OWNERSHIP_ROLLUP = "ownership_rollup"
    OBSERVED_CO_FAILURE = "observed_co_failure"
    OPERATIONAL_IMPACT = "operational_impact"
    AGGREGATE_IMPACT = "aggregate_impact"
    STRUCTURAL_CONTEXT = "structural_context"
    UNKNOWN_UNPROVEN = "unknown_unproven"


class BlastTraversal(str, Enum):
    FORWARD = "forward"
    REVERSE = "reverse"
    CONDITIONAL_REVERSE = "conditional_reverse"
    NONE = "none"


class BlastPolicyMaturity(str, Enum):
    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    NON_PROPAGATING = "non_propagating"
    UNSUPPORTED_FOR_IMPACT_V1 = (
        "unsupported_for_impact_v1"
    )


@dataclass(frozen=True)
class BlastPredicatePolicy:
    predicate: str
    relationship_direction: str
    impact_semantic: BlastImpactSemantic
    allowed_traversal: BlastTraversal
    conditional: bool
    aggregate_evaluator: str | None
    can_expand_from_states: tuple[BlastImpactSemantic, ...]
    maturity: BlastPolicyMaturity
    known_limitations: str
    policy_version: str = BLAST_POLICY_VERSION

    def machine_record(self) -> dict[str, object]:
        record = asdict(self)
        record["impact_semantic"] = self.impact_semantic.value
        record["allowed_traversal"] = self.allowed_traversal.value
        record["can_expand_from_states"] = [
            state.value
            for state in self.can_expand_from_states
        ]
        record["maturity"] = self.maturity.value
        return record


_FAILURE_STATES = (
    BlastImpactSemantic.DIRECT_FAILURE,
    BlastImpactSemantic.OBSERVED_CO_FAILURE,
    BlastImpactSemantic.OPERATIONAL_IMPACT,
    BlastImpactSemantic.AGGREGATE_IMPACT,
)


ACTIVE_BLAST_PREDICATES = frozenset(
    {
        "attached_to",
        "calls",
        "contains",
        "depends_on",
        "exposes",
        "owns",
        "produces",
        "protects",
        "resolves_to",
        "routes_to",
        "runs",
        "selects",
        "triggers",
        "uses",
    }
)


BLAST_IMPACT_POLICIES: dict[str, BlastPredicatePolicy] = {
    "attached_to": BlastPredicatePolicy(
        predicate="attached_to",
        relationship_direction="attached object -> target",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations=(
            "Only target failure propagates to the attached object; "
            "an attached-object failure does not implicate its target."
        ),
    ),
    "calls": BlastPredicatePolicy(
        predicate="calls",
        relationship_direction="caller -> destination",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations="The call graph does not prove request-level impact.",
    ),
    "contains": BlastPredicatePolicy(
        predicate="contains",
        relationship_direction="scope -> member",
        impact_semantic=BlastImpactSemantic.STRUCTURAL_CONTEXT,
        allowed_traversal=BlastTraversal.NONE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(),
        maturity=BlastPolicyMaturity.NON_PROPAGATING,
        known_limitations=(
            "Containment remains topology context and never enters the "
            "operational impacted set."
        ),
    ),
    "depends_on": BlastPredicatePolicy(
        predicate="depends_on",
        relationship_direction="dependent -> dependency",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations="Dependency presence does not establish symptom severity.",
    ),
    "exposes": BlastPredicatePolicy(
        predicate="exposes",
        relationship_direction="resource -> endpoint",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.FORWARD,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations="Only failure of the exposing resource propagates.",
    ),
    "owns": BlastPredicatePolicy(
        predicate="owns",
        relationship_direction="owner -> owned",
        impact_semantic=BlastImpactSemantic.OWNERSHIP_ROLLUP,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(
            BlastImpactSemantic.DIRECT_FAILURE,
            BlastImpactSemantic.OBSERVED_CO_FAILURE,
            BlastImpactSemantic.OWNERSHIP_ROLLUP,
        ),
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations=(
            "This is attribution roll-up only. Owners never fan out to "
            "healthy owned entities."
        ),
    ),
    "produces": BlastPredicatePolicy(
        predicate="produces",
        relationship_direction="producer -> artifact",
        impact_semantic=BlastImpactSemantic.UNKNOWN_UNPROVEN,
        allowed_traversal=BlastTraversal.NONE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(),
        maturity=BlastPolicyMaturity.UNSUPPORTED_FOR_IMPACT_V1,
        known_limitations="Production lineage alone does not prove runtime impact.",
    ),
    "protects": BlastPredicatePolicy(
        predicate="protects",
        relationship_direction="control -> protected resource",
        impact_semantic=BlastImpactSemantic.UNKNOWN_UNPROVEN,
        allowed_traversal=BlastTraversal.NONE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(),
        maturity=BlastPolicyMaturity.UNSUPPORTED_FOR_IMPACT_V1,
        known_limitations="Loss of protection is not equivalent to service failure.",
    ),
    "resolves_to": BlastPredicatePolicy(
        predicate="resolves_to",
        relationship_direction="name/service -> target",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations="Only target impact propagates to its resolver source.",
    ),
    "routes_to": BlastPredicatePolicy(
        predicate="routes_to",
        relationship_direction="routing source -> destination",
        impact_semantic=BlastImpactSemantic.AGGREGATE_IMPACT,
        allowed_traversal=BlastTraversal.CONDITIONAL_REVERSE,
        conditional=True,
        aggregate_evaluator="kubernetes_service_backend_availability_v1",
        can_expand_from_states=(
            BlastImpactSemantic.DIRECT_FAILURE,
            BlastImpactSemantic.OBSERVED_CO_FAILURE,
        ),
        maturity=BlastPolicyMaturity.CONDITIONAL,
        known_limitations=(
            "BR-1 supports only Kubernetes Service-to-Pod aggregate "
            "evaluation with a known selected target universe."
        ),
    ),
    "runs": BlastPredicatePolicy(
        predicate="runs",
        relationship_direction="host/workload/owner -> running object",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.FORWARD,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(
            BlastImpactSemantic.DIRECT_FAILURE,
            BlastImpactSemantic.OBSERVED_CO_FAILURE,
            BlastImpactSemantic.OPERATIONAL_IMPACT,
            BlastImpactSemantic.AGGREGATE_IMPACT,
        ),
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations=(
            "Ownership-rollup state is deliberately excluded so a rolled-up "
            "controller cannot fan out to healthy runtime objects."
        ),
    ),
    "selects": BlastPredicatePolicy(
        predicate="selects",
        relationship_direction="Service -> Pod",
        impact_semantic=BlastImpactSemantic.AGGREGATE_IMPACT,
        allowed_traversal=BlastTraversal.CONDITIONAL_REVERSE,
        conditional=True,
        aggregate_evaluator="kubernetes_service_backend_availability_v1",
        can_expand_from_states=(
            BlastImpactSemantic.DIRECT_FAILURE,
            BlastImpactSemantic.OBSERVED_CO_FAILURE,
        ),
        maturity=BlastPolicyMaturity.CONDITIONAL,
        known_limitations=(
            "A selected Pod failure affects the Service only when the pinned "
            "target set proves zero serving capacity."
        ),
    ),
    "triggers": BlastPredicatePolicy(
        predicate="triggers",
        relationship_direction="trigger source -> triggered execution",
        impact_semantic=BlastImpactSemantic.UNKNOWN_UNPROVEN,
        allowed_traversal=BlastTraversal.NONE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=(),
        maturity=BlastPolicyMaturity.UNSUPPORTED_FOR_IMPACT_V1,
        known_limitations="Execution lineage does not prove operational impact.",
    ),
    "uses": BlastPredicatePolicy(
        predicate="uses",
        relationship_direction="consumer -> dependency/artifact",
        impact_semantic=BlastImpactSemantic.OPERATIONAL_IMPACT,
        allowed_traversal=BlastTraversal.REVERSE,
        conditional=False,
        aggregate_evaluator=None,
        can_expand_from_states=_FAILURE_STATES,
        maturity=BlastPolicyMaturity.SUPPORTED,
        known_limitations="Only dependency impact propagates to the consumer.",
    ),
}


def blast_policy_for(predicate: str) -> BlastPredicatePolicy | None:
    """Return an explicit policy; unknown predicates never propagate."""

    return BLAST_IMPACT_POLICIES.get(predicate)


def blast_policy_machine_contract() -> list[dict[str, object]]:
    return [
        BLAST_IMPACT_POLICIES[predicate].machine_record()
        for predicate in sorted(BLAST_IMPACT_POLICIES)
    ]
