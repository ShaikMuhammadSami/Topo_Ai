from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EvaluationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    HARNESS_ERROR = "HARNESS_ERROR"


REQUIRED_MANIFEST_KEYS = {
    "scenario_version",
    "scenario_id",
    "family",
    "description",
    "environment_requirements",
    "objects",
    "causal_intent",
    "distractors",
    "non_causes",
    "expected_path",
    "expected_incident",
    "expected_blast_radius",
    "expected_evidence",
    "expected_confidence_semantics",
    "expected_behavior",
}

IMPACT_TRUTH_CLASSES = {
    "direct_failure",
    "ownership_rollup",
    "operationally_impacted",
    "structural_context",
    "unaffected",
}


@dataclass(frozen=True)
class ScenarioManifest:
    value: dict[str, Any]

    @property
    def scenario_id(self) -> str:
        return str(self.value["scenario_id"])

    @property
    def aliases(self) -> frozenset[str]:
        return frozenset(self.value["objects"])

    def ground_truth_copy(self) -> dict[str, Any]:
        return copy.deepcopy(self.value)

    @classmethod
    def load(cls, path: Path) -> "ScenarioManifest":
        value = json.loads(path.read_text(encoding="utf-8"))
        validate_manifest(value)
        return cls(value=copy.deepcopy(value))


def validate_manifest(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("Scenario manifest must be a JSON object.")
    missing = sorted(REQUIRED_MANIFEST_KEYS - set(value))
    if missing:
        raise ValueError("Missing manifest fields: " + ", ".join(missing))
    if value["scenario_version"] != "eval-1.scenario.v1":
        raise ValueError("Unsupported scenario_version.")
    if not isinstance(value["objects"], dict) or not value["objects"]:
        raise ValueError("objects must contain stable logical aliases.")
    aliases = set(value["objects"])
    references: list[str] = []
    intent = value["causal_intent"]
    references.extend(
        str(intent[key])
        for key in ("root_entity", "affected_entity")
        if intent.get(key)
    )
    references.extend(str(item) for item in value["distractors"])
    references.extend(str(item) for item in value["non_causes"])
    blast = value["expected_blast_radius"]
    references.extend(str(item) for item in blast["required_affected"])
    references.extend(str(item) for item in blast["explicitly_unaffected"])
    impact_truth = blast.get("impact_truth")
    if impact_truth is not None:
        if set(impact_truth) != IMPACT_TRUTH_CLASSES:
            raise ValueError(
                "impact_truth must define exactly: "
                + ", ".join(sorted(IMPACT_TRUTH_CLASSES))
            )
        class_members = [
            str(alias)
            for class_name in sorted(IMPACT_TRUTH_CLASSES)
            for alias in impact_truth[class_name]
        ]
        if len(class_members) != len(set(class_members)):
            raise ValueError("impact_truth classes must be disjoint.")
        references.extend(class_members)
        affected_classes = {
            str(alias)
            for class_name in (
                "direct_failure",
                "ownership_rollup",
                "operationally_impacted",
            )
            for alias in impact_truth[class_name]
        }
        unaffected_classes = {
            str(alias)
            for class_name in ("structural_context", "unaffected")
            for alias in impact_truth[class_name]
        }
        if affected_classes != set(blast["required_affected"]):
            raise ValueError(
                "required_affected must equal direct_failure + ownership_rollup + "
                "operationally_impacted."
            )
        if unaffected_classes != set(blast["explicitly_unaffected"]):
            raise ValueError(
                "explicitly_unaffected must equal structural_context + unaffected."
            )
    references.extend(
        str(item)
        for item in value["expected_incident"].get("accepted_affected_aliases", [])
    )
    for hop_group in ("required_hops", "optional_hops", "forbidden_hops"):
        for hop in value["expected_path"][hop_group]:
            references.extend((str(hop["from"]), str(hop["to"])))
    unknown = sorted(set(references) - aliases)
    if unknown:
        raise ValueError("Unknown logical aliases: " + ", ".join(unknown))
    confidence = value["expected_confidence_semantics"]
    if confidence.get("calibrated_probability") is not None:
        raise ValueError("EVAL-1 must expect calibrated_probability=null.")


@dataclass(frozen=True)
class ProviderObject:
    logical_name: str
    provider_kind: str
    namespace: str
    name: str
    uid: str
    observed_at: str
    spec: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    owner_uid: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
    selectors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionAction:
    action_id: str
    action_type: str
    logical_target: str
    provider_uid: str
    executed_at: str
    before: dict[str, Any]
    after: dict[str, Any]
    provider_receipt: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionReceipt:
    receipt_version: str
    scenario_id: str
    run_id: str
    namespace: str
    started_at: str
    completed_at: str | None = None
    actions: list[ExecutionAction] = field(default_factory=list)


@dataclass
class ProviderVerification:
    verification_version: str
    source: str
    observed_at: str
    established: bool
    objects: list[ProviderObject] = field(default_factory=list)
    assertions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TopoObservation:
    observation_version: str
    captured_at: str
    incident: dict[str, Any] | None = None
    incident_candidates: list[dict[str, Any]] = field(default_factory=list)
    incident_signals: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None
    causal_analysis: dict[str, Any] | None = None
    briefing: dict[str, Any] | None = None
    blast_radius: dict[str, Any] | None = None
    change_events: list[dict[str, Any]] = field(default_factory=list)
    incident_change_analysis: dict[str, Any] | None = None
    endpoint_statuses: dict[str, int] = field(default_factory=dict)
    observed_times: dict[str, str] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    result_version: str
    harness_version: str
    run_id: str
    scenario_id: str
    topo_git_commit: str
    started_at: str
    completed_at: str
    environment: dict[str, Any]
    ground_truth: dict[str, Any]
    execution_receipt: dict[str, Any]
    provider_verification: dict[str, Any]
    topo_observation: dict[str, Any]
    metric_results: dict[str, Any]
    assertions: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    warnings: list[str]
    overall_status: EvaluationStatus
    evidence_semantics_version: str | None = None
    cause_fingerprint_version: str | None = None
    cause_match_version: str | None = None
    cause_match_status: str | None = None
    expected_cause_fingerprints: list[dict[str, Any]] = field(default_factory=list)
    top1_actual_cause_fingerprint: dict[str, Any] | None = None
    top1_cause_match: dict[str, Any] | None = None
    top3_cause_matches: list[dict[str, Any]] = field(default_factory=list)
    cause_match_diagnostics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["overall_status"] = self.overall_status.value
        return value

    def to_json(self) -> str:
        return deterministic_json(self.as_dict())


def deterministic_json(value: Any) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"


def contract_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
