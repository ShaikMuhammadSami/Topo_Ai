from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation.causal_ground_truth import (
    CAUSAL_GROUND_TRUTH_VERSION,
    causal_ground_truth,
    validate_causal_ground_truth,
)
from evaluation.contracts import deterministic_json
from evaluation.source_mutation_truth import (
    FAIL_BYTES,
    FAIL_EXIT_CODE,
    FIXTURE_FILE,
    HEALTHY_BYTES,
    SOURCE_MUTATION_VERSION,
    pending_source_mutation_contract,
    semantic_mode,
    sha256_bytes,
    source_mutation_contract,
    validate_source_mutation_contract,
)
from evaluation.product_diff_guard import (
    assert_text_file_git_blob_id,
    assert_historical_commit_excludes_paths,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_FAILURE_FIXTURE_ACCEPTED_COMMIT = (
    "f9b152133a8075428766dd48b3f752b255ec5270"
)
FIXTURE = ROOT / "evaluation/fixtures/lineage-image"
ATTRIBUTES = FIXTURE / ".gitattributes"
DOCKERFILE = FIXTURE / "Dockerfile"
RUN_SCRIPT = FIXTURE / "run.sh"
MODE_FILE = FIXTURE / "runtime-mode.txt"
DEPLOYMENT = ROOT / "evaluation/fixtures/lineage-causal/deployment.yaml"
SOURCE_SCHEMA = ROOT / "docs/architecture/evaluation/source-mutation.schema.json"
CAUSAL_SCHEMA = ROOT / "docs/architecture/evaluation/causal-ground-truth.schema.json"
WORKFLOW = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"

WORKFLOW_SHA256 = "145a10245d575e02a756be018aaa25c2eabd1d39cde82b43aebd0d605d951903"
PERMANENT_MANIFEST_HASHES = {
    "blast-01.json": "2f292f5ee1c116d2c2c832bc2165a61bc13dedc5",
    "blast-02.json": "695d0feda176f26c7e601a57060f4ad0d29310a9",
    "blast-03.json": "0f9974a4a5f4a08d6b01d2e02be319698175f6c1",
    "sentinel-a.json": "599ba19827d5097fded3f52264cad8dd35abb839",
    "sentinel-b.json": "f404607eaca904baac362edb2365fa53652565fe",
    "sentinel-c.json": "9bb3c201b190708224770a30ec9c23939623f683",
    "sentinel-d.json": "e7e2a8f4e2cde066bee209191ec27304a41193f7",
}


def _shell() -> str:
    discovered = shutil.which("sh")
    if discovered:
        return discovered
    if os.name == "nt":
        for candidate in (
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/sh.exe",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/sh.exe",
        ):
            if candidate.is_file():
                return str(candidate)
    pytest.fail("A POSIX shell is required to verify the POSIX image entrypoint.")


def _run_mode(mode: str, *, replace_healthy_loop: bool = False) -> subprocess.CompletedProcess[str]:
    override = "healthy_loop() { exit 73; }; " if replace_healthy_loop else ""
    return subprocess.run(
        [
            _shell(),
            "-c",
            f'. "$1"; {override}run_mode "$2"',
            "topo-fixture-test",
            RUN_SCRIPT.as_posix(),
            mode,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )


def _documents() -> tuple[dict[str, Any], dict[str, Any]]:
    values = list(yaml.safe_load_all(DEPLOYMENT.read_text(encoding="utf-8")))
    assert len(values) == 2
    namespace, deployment = values
    assert namespace["kind"] == "Namespace"
    assert deployment["kind"] == "Deployment"
    return namespace, deployment


def _completed_source_contract() -> dict[str, Any]:
    return source_mutation_contract(
        repository_id="1278498159",
        repository="example/topo",
        parent_commit_sha="a" * 40,
        commit_sha="b" * 40,
        before=HEALTHY_BYTES,
        after=FAIL_BYTES,
    )


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    if "const" in schema:
        assert value == schema["const"], f"{path}: const mismatch"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: enum mismatch"
    expected_type = schema.get("type")
    if expected_type:
        accepted = expected_type if isinstance(expected_type, list) else [expected_type]
        assert any(_is_type(value, item) for item in accepted), f"{path}: type mismatch"
    if isinstance(value, dict):
        required = set(schema.get("required") or [])
        assert required.issubset(value), f"{path}: missing required fields"
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            assert set(value).issubset(properties), f"{path}: unknown fields"
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], f"{path}.{key}")
        for condition in schema.get("allOf") or []:
            condition_schema = condition.get("if") or {}
            try:
                _validate_schema(value, condition_schema, path)
            except AssertionError:
                continue
            _validate_schema(value, condition["then"], path)
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str) and schema.get("pattern"):
        assert re.fullmatch(schema["pattern"], value), f"{path}: pattern mismatch"


def test_runtime_mode_baseline_is_healthy():
    assert MODE_FILE.read_bytes() == HEALTHY_BYTES


def test_mode_file_has_exactly_one_canonical_semantic_value():
    assert MODE_FILE.read_text(encoding="utf-8").splitlines() == ["healthy"]
    assert semantic_mode(MODE_FILE.read_bytes()) == "healthy"


@pytest.mark.parametrize("name", ["Dockerfile", "run.sh", "runtime-mode.txt"])
def test_fixture_checkout_bytes_are_forced_to_lf(name: str):
    attributes = ATTRIBUTES.read_text(encoding="utf-8").splitlines()
    assert f"{name} text eol=lf" in attributes
    assert b"\r" not in (FIXTURE / name).read_bytes()


def test_healthy_behavior_enters_the_long_running_branch():
    result = _run_mode("healthy", replace_healthy_loop=True)
    assert result.returncode == 73
    assert result.stdout == "topo causal fixture: healthy mode\n"


def test_healthy_branch_has_no_intentional_exit():
    text = RUN_SCRIPT.read_text(encoding="utf-8")
    branch = text.split("healthy)", 1)[1].split(";;", 1)[0]
    assert "healthy_loop" in branch
    assert "exit" not in branch
    assert "while :; do" in text and "sleep 3600" in text


def test_fail_behavior_exits_with_exact_expected_code():
    result = _run_mode("fail")
    assert result.returncode == FAIL_EXIT_CODE
    assert result.stderr == "topo causal fixture: fail mode; exiting 42\n"


@pytest.mark.parametrize("mode", ["unknown", "Healthy", "", "fail "])
def test_unknown_mode_rejects_deterministically(mode: str):
    result = _run_mode(mode)
    assert result.returncode == 64
    assert result.stderr == "topo causal fixture: invalid runtime mode\n"


@pytest.mark.parametrize(
    "forbidden",
    ["curl", "wget", "nc ", "netstat", "/proc/net", "http://", "https://"],
)
def test_run_script_does_not_inspect_network_state(forbidden: str):
    assert forbidden not in RUN_SCRIPT.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    "forbidden",
    ["printenv", " env ", "token", "secret", "password", "credential", "authorization"],
)
def test_run_script_does_not_inspect_environment_secrets(forbidden: str):
    assert forbidden not in RUN_SCRIPT.read_text(encoding="utf-8").lower()


def test_dockerfile_copies_runtime_mode_file():
    assert "COPY --chown=65532:65532 run.sh runtime-mode.txt /opt/topo/" in DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_copies_run_script():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "run.sh" in text and "chmod 0555 /opt/topo/run.sh" in text


def test_dockerfile_invokes_run_script_as_runtime():
    assert 'ENTRYPOINT ["/opt/topo/run.sh"]' in DOCKERFILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("forbidden", ["EXPOSE ", "httpd", "listen", "CMD ["])
def test_dockerfile_exposes_no_port_or_alternate_runtime(forbidden: str):
    assert forbidden.casefold() not in DOCKERFILE.read_text(encoding="utf-8").casefold()


@pytest.mark.parametrize(
    "forbidden", ["token", "password", "credential", "authorization", "private_key"]
)
def test_dockerfile_contains_no_secret(forbidden: str):
    assert forbidden not in DOCKERFILE.read_text(encoding="utf-8").lower()


def test_dockerfile_runtime_is_non_root():
    assert "USER 65532:65532" in DOCKERFILE.read_text(encoding="utf-8")


def test_future_mutation_changes_only_runtime_mode_source_value():
    before = pending_source_mutation_contract()
    assert before["file_path"] == FIXTURE_FILE
    assert before["before_semantic_value"] == "healthy"
    assert before["after_semantic_value"] == "fail"


def test_workflow_logic_needs_no_change_for_future_mode_mutation():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "context: evaluation/fixtures/lineage-image" in text
    assert "runtime-mode" not in text
    assert "docker/build-push-action@v7" in text


def test_source_mutation_contract_validates_healthy_to_fail():
    validate_source_mutation_contract(_completed_source_contract())


def test_source_mutation_contract_supports_pending_commit_sha():
    value = pending_source_mutation_contract()
    validate_source_mutation_contract(value)
    assert value["commit_sha"] is None
    assert value["parent_commit_sha"] is None


def test_before_and_after_sha256_hashes_are_deterministic():
    first = pending_source_mutation_contract()
    second = pending_source_mutation_contract()
    assert first["before_hash"] == second["before_hash"] == sha256_bytes(b"healthy\n")
    assert first["after_hash"] == second["after_hash"] == sha256_bytes(b"fail\n")


def test_semantic_before_is_healthy_and_after_is_fail():
    value = _completed_source_contract()
    assert semantic_mode(HEALTHY_BYTES) == value["before_semantic_value"] == "healthy"
    assert semantic_mode(FAIL_BYTES) == value["after_semantic_value"] == "fail"


def test_expected_failure_exit_code_is_fixed():
    assert pending_source_mutation_contract()["expected_failure_mechanism"] == {
        "type": "container_entrypoint_exit",
        "exit_code": 42,
    }


def test_causal_ground_truth_contains_exactly_four_levels():
    value = causal_ground_truth(pending_source_mutation_contract())
    assert set(value["levels"]) == {
        "initiating_mutation",
        "failure_mechanism",
        "runtime_manifestation",
        "operational_impact",
    }


def test_initiating_mutation_is_not_runtime_manifestation():
    levels = causal_ground_truth(pending_source_mutation_contract())["levels"]
    assert "file_path" in levels["initiating_mutation"]
    assert "last_termination_exit_code" not in levels["initiating_mutation"]
    assert "file_path" not in levels["runtime_manifestation"]


def test_runtime_manifestation_is_not_operational_impact():
    levels = causal_ground_truth(pending_source_mutation_contract())["levels"]
    assert "minimum_restart_count" in levels["runtime_manifestation"]
    assert "ready_replicas" not in levels["runtime_manifestation"]
    assert "minimum_restart_count" not in levels["operational_impact"]


def test_backoff_acceptance_uses_structured_provider_fields():
    runtime = causal_ground_truth(pending_source_mutation_contract())["levels"]["runtime_manifestation"]
    assert runtime["last_termination_exit_code"] == 42
    assert runtime["minimum_restart_count"] == 1
    assert runtime["accepted_waiting_reasons"] == ["BackOff", "CrashLoopBackOff"]
    assert runtime["structured_fields_required"] is True


def test_single_replica_zero_ready_impact_is_represented():
    impact = causal_ground_truth(pending_source_mutation_contract())["levels"]["operational_impact"]
    assert impact == {
        "provider": "kubernetes",
        "resource_kind": "Deployment",
        "desired_replicas": 1,
        "ready_replicas": 0,
        "available_replicas": 0,
    }


def test_deployment_template_uses_immutable_image_placeholder():
    _namespace, deployment = _documents()
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    assert image == "__IMMUTABLE_IMAGE_REF__"


def test_deployment_template_does_not_use_mutable_latest_tag():
    text = DEPLOYMENT.read_text(encoding="utf-8").lower()
    assert ":latest" not in text
    assert "image: __immutable_image_ref__" in text


def test_deployment_template_has_one_replica():
    _namespace, deployment = _documents()
    assert deployment["spec"]["replicas"] == 1


def test_deployment_template_has_no_runtime_cause_override():
    _namespace, deployment = _documents()
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert "command" not in container
    assert "args" not in container
    assert "env" not in container


def test_deployment_template_is_unprivileged():
    _namespace, deployment = _documents()
    pod_spec = deployment["spec"]["template"]["spec"]
    container_security = pod_spec["containers"][0]["securityContext"]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsNonRoot"] is True
    assert container_security["allowPrivilegeEscalation"] is False
    assert container_security["capabilities"]["drop"] == ["ALL"]


@pytest.mark.parametrize("forbidden", ["hostPath", "hostNetwork", "hostPID", "hostIPC", "privileged"])
def test_deployment_template_excludes_host_or_privileged_settings(forbidden: str):
    assert forbidden not in DEPLOYMENT.read_text(encoding="utf-8")


def test_deployment_template_has_no_persistent_volume():
    text = DEPLOYMENT.read_text(encoding="utf-8")
    assert "persistentVolumeClaim" not in text
    assert "volumes:" not in text
    assert "volumeMounts:" not in text


def test_deployment_resource_behavior_is_bounded():
    _namespace, deployment = _documents()
    resources = deployment["spec"]["template"]["spec"]["containers"][0]["resources"]
    assert resources == {
        "requests": {"cpu": "5m", "memory": "8Mi"},
        "limits": {"cpu": "50m", "memory": "32Mi"},
    }
    assert deployment["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 1


def test_namespace_prefix_and_run_label_safety_are_represented():
    namespace, deployment = _documents()
    assert namespace["metadata"]["name"] == "topo-eval-lineage-causal-__RUN_ID__"
    assert namespace["metadata"]["labels"] == {"topo.ai/evaluation-run": "__RUN_ID__"}
    assert deployment["metadata"]["namespace"] == namespace["metadata"]["name"]


def test_source_expected_truth_is_independent_of_topo():
    value = pending_source_mutation_contract()
    assert value["truth_source"] == "git_provider"
    assert value["topo_output_used"] is False
    source = (ROOT / "evaluation/source_mutation_truth.py").read_text(encoding="utf-8")
    assert "from app" not in source and "topo_observation" not in source


def test_provider_build_receipt_remains_independent_of_topo_conclusions():
    workflow = WORKFLOW.read_text(encoding="utf-8").lower()
    receipt_step = workflow.split("create provider receipt", 1)[1]
    for forbidden in ("incident_id", "causal_analysis", "root_cause", "hypothesis"):
        assert forbidden not in receipt_step


@pytest.mark.parametrize("forbidden", ["topo.root_cause", "topo.expected_failure", "exit_code=42"])
def test_no_ground_truth_answer_label_is_embedded_in_image(forbidden: str):
    content = (DOCKERFILE.read_text(encoding="utf-8") + WORKFLOW.read_text(encoding="utf-8")).lower()
    assert forbidden not in content


def test_h3_provider_workflow_remains_manual_only_and_frozen():
    import hashlib

    text = WORKFLOW.read_text(encoding="utf-8")
    assert hashlib.sha256(WORKFLOW.read_bytes()).hexdigest() == WORKFLOW_SHA256
    parsed = yaml.load(text, Loader=yaml.BaseLoader)
    assert set(parsed["on"]) == {"workflow_dispatch"}


def test_source_failure_fixture_commit_changed_no_backend_product_paths():
    assert_historical_commit_excludes_paths(
        ROOT,
        name="LINEAGE-1A source failure fixture backend scope",
        commit=SOURCE_FAILURE_FIXTURE_ACCEPTED_COMMIT,
        prohibited_pathspecs=("backend/app", "backend/tests"),
    )


@pytest.mark.parametrize("name,expected", sorted(PERMANENT_MANIFEST_HASHES.items()))
def test_permanent_manifest_is_unchanged(name: str, expected: str):
    assert_text_file_git_blob_id(ROOT / "evaluation/manifests" / name, expected)


def test_source_failure_fixture_commit_changed_no_product_paths():
    assert_historical_commit_excludes_paths(
        ROOT,
        name="LINEAGE-1A source failure fixture product scope",
        commit=SOURCE_FAILURE_FIXTURE_ACCEPTED_COMMIT,
    )


def test_contract_serialization_is_deterministic():
    value = causal_ground_truth(pending_source_mutation_contract())
    assert deterministic_json(value) == deterministic_json(copy.deepcopy(value))
    assert json.loads(deterministic_json(value)) == value


def test_source_mutation_schema_validates_pending_and_complete_contracts():
    schema = json.loads(SOURCE_SCHEMA.read_text(encoding="utf-8"))
    _validate_schema(pending_source_mutation_contract(), schema)
    _validate_schema(_completed_source_contract(), schema)


def test_causal_ground_truth_schema_validates():
    value = causal_ground_truth(pending_source_mutation_contract())
    validate_causal_ground_truth(value)
    _validate_schema(value, json.loads(CAUSAL_SCHEMA.read_text(encoding="utf-8")))


def test_contract_schemas_are_strict_and_versioned():
    source = json.loads(SOURCE_SCHEMA.read_text(encoding="utf-8"))
    causal = json.loads(CAUSAL_SCHEMA.read_text(encoding="utf-8"))
    assert source["additionalProperties"] is False
    assert source["properties"]["schema_version"]["const"] == SOURCE_MUTATION_VERSION
    assert causal["additionalProperties"] is False
    assert causal["properties"]["schema_version"]["const"] == CAUSAL_GROUND_TRUTH_VERSION


@pytest.mark.parametrize(
    "forbidden",
    ["llm_client", "import openai", "embedding", "fuzzywuzzy", "difflib", "levenshtein"],
)
def test_truth_helpers_use_no_llm_embeddings_or_fuzzy_matching(forbidden: str):
    source = "\n".join(
        (ROOT / name).read_text(encoding="utf-8").lower()
        for name in ("evaluation/source_mutation_truth.py", "evaluation/causal_ground_truth.py")
    )
    assert forbidden not in source


@pytest.mark.parametrize(
    "forbidden", ["gh workflow run", "gh api --method post", "kubectl apply", "docker push", "httpx", "requests.post"]
)
def test_evaluation_tests_and_truth_helpers_have_no_provider_mutation(forbidden: str):
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (
            ROOT / "evaluation/source_mutation_truth.py",
            ROOT / "evaluation/causal_ground_truth.py",
        )
    )
    assert forbidden not in source
