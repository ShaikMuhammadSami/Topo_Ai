from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


LINEAGE_HOP_VERSION = "eval-lineage-hop-v1"
LINEAGE_RESULT_VERSION = "eval-lineage-result-v1"
LINEAGE_SCENARIO_ID = "lineage-source-to-runtime-v1"


class LineageHopStatus(str, Enum):
    PROVEN = "PROVEN"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    WRONG = "WRONG"
    INCONCLUSIVE = "INCONCLUSIVE"
    PROVIDER_PREREQUISITE_BLOCKED = "PROVIDER_PREREQUISITE_BLOCKED"


class LineageStrength(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


FIRST_BROKEN_BY_HOP = {
    "H1": "H1_REPO_COMMIT",
    "H2": "H2_COMMIT_ACTIONS",
    "H3": "H3_ACTIONS_IMAGE",
    "H4": "H4_IMAGE_DEPLOYMENT",
    "H5": "H5_DEPLOYMENT_RS",
    "H6": "H6_RS_POD",
    "H7": "H7_POD_FAILURE",
}


@dataclass(frozen=True)
class LineageHopSpec:
    hop_id: str
    source_logical_alias: str
    target_logical_alias: str
    expected_relationship_semantic: str
    expected_predicates: tuple[str, ...]
    topo_source_logical_alias: str
    topo_target_logical_alias: str
    required_source_reference_types: tuple[str, ...] = ()
    immutable_artifact_required: bool = False
    temporal_order_required: bool = True
    observation_kind: str = "relationship"


@dataclass
class LineageHopResult:
    hop_version: str
    hop_id: str
    source_logical_alias: str
    target_logical_alias: str
    expected_source_provider_identity: dict[str, Any] | None
    expected_target_provider_identity: dict[str, Any] | None
    expected_relationship_semantic: str
    provider_truth: dict[str, Any]
    topo_observation: dict[str, Any]
    evaluation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LineageResult:
    result_version: str
    hop_contract_version: str
    run_id: str
    scenario_id: str
    started_at: str
    completed_at: str
    product_git_commit: str
    execution_mode: str
    prerequisites: dict[str, Any]
    provider_truth: dict[str, Any]
    topo_observation: dict[str, Any]
    hop_results: list[dict[str, Any]]
    first_broken_hop: str
    first_broken_hop_id: str | None
    proven_hop_count: int
    partial_hop_count: int
    missing_hop_count: int
    wrong_hop_count: int
    inconclusive_hop_count: int
    provider_blocked_hop_count: int
    lineage_complete: bool
    immutable_artifact_chain_complete: bool
    source_to_runtime_strength: str
    source_change_causally_proven: str
    commercial_proof_status: dict[str, bool]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return deterministic_json(self.as_dict())


def deterministic_json(value: Any) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ) + "\n"
