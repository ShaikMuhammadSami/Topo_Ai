from __future__ import annotations

from typing import Any

from evaluation.source_mutation_truth import (
    FAIL_EXIT_CODE,
    SOURCE_MUTATION_VERSION,
    validate_source_mutation_contract,
)


CAUSAL_GROUND_TRUTH_VERSION = "eval-causal-ground-truth-v1"


def causal_ground_truth(source_mutation: dict[str, Any]) -> dict[str, Any]:
    validate_source_mutation_contract(source_mutation)
    value = {
        "schema_version": CAUSAL_GROUND_TRUTH_VERSION,
        "status": (
            "pending_provider_run"
            if source_mutation["status"] == "pending"
            else "source_truth_complete"
        ),
        "scenario_id": "lineage-source-failure-causal-v1",
        "expected_truth_source": "git_and_provider_runtime",
        "topo_role": "system_under_test",
        "levels": {
            "initiating_mutation": {
                "contract_version": SOURCE_MUTATION_VERSION,
                "file_path": source_mutation["file_path"],
                "mutation_family": source_mutation["mutation_family"],
                "before_semantic_value": source_mutation["before_semantic_value"],
                "after_semantic_value": source_mutation["after_semantic_value"],
                "scenario_role": "initiating_mutation",
            },
            "failure_mechanism": {
                "type": "container_entrypoint_exit",
                "exit_code": FAIL_EXIT_CODE,
                "deterministic": True,
            },
            "runtime_manifestation": {
                "provider": "kubernetes",
                "last_termination_exit_code": FAIL_EXIT_CODE,
                "minimum_restart_count": 1,
                "accepted_waiting_reasons": ["BackOff", "CrashLoopBackOff"],
                "accepted_termination_reasons": ["Error"],
                "structured_fields_required": True,
            },
            "operational_impact": {
                "provider": "kubernetes",
                "resource_kind": "Deployment",
                "desired_replicas": 1,
                "ready_replicas": 0,
                "available_replicas": 0,
            },
        },
    }
    validate_causal_ground_truth(value)
    return value


def validate_causal_ground_truth(value: dict[str, Any]) -> None:
    if value.get("schema_version") != CAUSAL_GROUND_TRUTH_VERSION:
        raise ValueError("Unsupported causal ground-truth contract.")
    if value.get("expected_truth_source") != "git_and_provider_runtime":
        raise ValueError("Causal truth must come from Git and provider runtime.")
    if value.get("topo_role") != "system_under_test":
        raise ValueError("Topo cannot define expected causal truth.")
    levels = value.get("levels")
    required = {
        "initiating_mutation",
        "failure_mechanism",
        "runtime_manifestation",
        "operational_impact",
    }
    if not isinstance(levels, dict) or set(levels) != required:
        raise ValueError("Causal truth requires exactly four semantic levels.")
    if levels["initiating_mutation"].get("scenario_role") != "initiating_mutation":
        raise ValueError("Initiating mutation semantics are invalid.")
    if levels["failure_mechanism"] != {
        "type": "container_entrypoint_exit",
        "exit_code": FAIL_EXIT_CODE,
        "deterministic": True,
    }:
        raise ValueError("Failure mechanism semantics are invalid.")
    runtime = levels["runtime_manifestation"]
    if runtime.get("last_termination_exit_code") != FAIL_EXIT_CODE:
        raise ValueError("Runtime exit evidence is invalid.")
    if runtime.get("minimum_restart_count") != 1:
        raise ValueError("Runtime restart evidence is invalid.")
    if runtime.get("accepted_waiting_reasons") != [
        "BackOff",
        "CrashLoopBackOff",
    ]:
        raise ValueError("Runtime waiting reasons are invalid.")
    if levels["operational_impact"] != {
        "provider": "kubernetes",
        "resource_kind": "Deployment",
        "desired_replicas": 1,
        "ready_replicas": 0,
        "available_replicas": 0,
    }:
        raise ValueError("Operational impact semantics are invalid.")
