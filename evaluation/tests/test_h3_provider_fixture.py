from __future__ import annotations

import copy
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from evaluation.lineage_provider_truth import (
    contains_unredacted_secret_like_fields,
    sanitize_provider_receipt,
)
from evaluation.product_diff_guard import assert_product_diff_scoped_to_h3_r1


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"
DOCKERFILE = ROOT / "evaluation/fixtures/lineage-image/Dockerfile"
RUN_SCRIPT = ROOT / "evaluation/fixtures/lineage-image/run.sh"
RUNTIME_MODE = ROOT / "evaluation/fixtures/lineage-image/runtime-mode.txt"
SCHEMA = ROOT / "docs/architecture/evaluation/lineage-provider-receipt.schema.json"
EXAMPLE = ROOT / "evaluation/fixtures/lineage-provider-receipt.example.json"
DOC = ROOT / "docs/architecture/evaluation/lineage-provider-receipt-v1.md"

PERMANENT_MANIFEST_HASHES = {
    "blast-01.json": "2f292f5ee1c116d2c2c832bc2165a61bc13dedc5",
    "blast-02.json": "695d0feda176f26c7e601a57060f4ad0d29310a9",
    "blast-03.json": "0f9974a4a5f4a08d6b01d2e02be319698175f6c1",
    "sentinel-a.json": "599ba19827d5097fded3f52264cad8dd35abb839",
    "sentinel-b.json": "f404607eaca904baac362edb2365fa53652565fe",
    "sentinel-c.json": "9bb3c201b190708224770a30ec9c23939623f683",
    "sentinel-d.json": "e7e2a8f4e2cde066bee209191ec27304a41193f7",
}


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def workflow() -> dict[str, Any]:
    # BaseLoader intentionally keeps the GitHub Actions key `on` as a string;
    # YAML 1.1 SafeLoader otherwise coerces it to boolean True.
    return yaml.load(workflow_text(), Loader=yaml.BaseLoader)


def job() -> dict[str, Any]:
    return workflow()["jobs"]["publish-evaluation-image"]


def step(name: str) -> dict[str, Any]:
    return next(item for item in job()["steps"] if item["name"] == name)


def _is_type(value: Any, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def validate_schema_subset(value: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Validate the JSON Schema features used by the receipt contract."""

    if "oneOf" in schema:
        matches = 0
        for candidate in schema["oneOf"]:
            try:
                validate_schema_subset(value, candidate, path)
            except AssertionError:
                continue
            matches += 1
        assert matches == 1, f"{path}: expected exactly one oneOf match"
        return
    if "const" in schema:
        assert value == schema["const"], f"{path}: const mismatch"
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
                validate_schema_subset(item, properties[key], f"{path}.{key}")
    if isinstance(value, str):
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{path}: too short"
        if "pattern" in schema:
            assert re.fullmatch(schema["pattern"], value), f"{path}: pattern mismatch"
        if schema.get("format") == "date-time":
            datetime.fromisoformat(value.replace("Z", "+00:00"))
    if isinstance(value, int) and not isinstance(value, bool) and "minimum" in schema:
        assert value >= schema["minimum"], f"{path}: below minimum"


def test_workflow_exists_at_dedicated_fixture_path():
    assert WORKFLOW.is_file()


def test_only_workflow_dispatch_trigger_exists():
    assert set(workflow()["on"]) == {"workflow_dispatch"}


@pytest.mark.parametrize(
    "forbidden_trigger",
    ["push", "pull_request", "schedule", "workflow_run", "release", "deployment", "repository_dispatch"],
)
def test_automatic_or_external_trigger_is_absent(forbidden_trigger):
    assert forbidden_trigger not in workflow()["on"]


def test_manual_confirmation_input_is_required():
    confirm = workflow()["on"]["workflow_dispatch"]["inputs"]["confirm"]
    assert confirm["required"] == "true"
    assert confirm["type"] == "string"
    assert "EVALUATION_ONLY" in confirm["description"]


def test_publish_job_requires_exact_confirmation():
    guard = job()["if"]
    assert "inputs.confirm" in guard
    assert "EVALUATION_ONLY" in guard
    assert "==" in guard


def test_permissions_are_exactly_least_privilege():
    assert workflow()["permissions"] == {"contents": "read", "packages": "write"}


def test_no_write_all_permission():
    assert "write-all" not in workflow_text().lower()


@pytest.mark.parametrize(
    "forbidden_permission",
    ["actions", "deployments", "issues", "pull-requests", "security-events", "id-token"],
)
def test_no_unnecessary_permission(forbidden_permission):
    assert forbidden_permission not in workflow()["permissions"]


def test_no_github_environment_is_targeted():
    assert "environment" not in job()


@pytest.mark.parametrize(
    "forbidden",
    ["kubectl", "helm ", "terraform", "aws-actions", "azure/", "google-github-actions", "action-gh-release", "create-release", "deployment-action"],
)
def test_no_deployment_cloud_or_release_tooling(forbidden):
    assert forbidden not in workflow_text().lower()


def test_only_github_token_is_used_for_registry_authentication():
    text = workflow_text()
    assert text.count("${{ secrets.GITHUB_TOKEN }}") == 1
    assert re.findall(r"secrets\.([A-Za-z0-9_]+)", text) == ["GITHUB_TOKEN"]


@pytest.mark.parametrize("forbidden", ["PAT", "DOCKERHUB_TOKEN", "REGISTRY_PASSWORD", "GHCR_TOKEN"])
def test_no_custom_registry_secret_is_required(forbidden):
    assert f"secrets.{forbidden}" not in workflow_text()


def test_registry_is_ghcr():
    login = step("Log in to GitHub Container Registry")
    assert login["with"]["registry"] == "ghcr.io"


def test_package_name_is_explicitly_evaluation_specific():
    assert "-topo-lineage-eval" in workflow_text()


def test_package_name_is_derived_with_lowercase_validation():
    metadata = step("Prepare evaluation image metadata")["run"]
    assert "tr '[:upper:]' '[:lower:]'" in metadata
    assert "^[a-z0-9][a-z0-9._-]*$" in metadata


def test_no_authoritative_latest_tag_is_used():
    text = workflow_text().lower()
    assert ":latest" not in text
    assert "value=latest" not in text


def test_run_specific_tag_contains_run_and_attempt():
    assert 'image_tag="run-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"' in workflow_text()


def test_build_pushes_the_image():
    assert step("Build and push evaluation image")["with"]["push"] == "true"


def test_build_targets_linux_amd64():
    assert step("Build and push evaluation image")["with"]["platforms"] == "linux/amd64"


def test_build_uses_only_dedicated_fixture_context():
    build = step("Build and push evaluation image")["with"]
    assert build["context"] == "evaluation/fixtures/lineage-image"
    assert build["file"] == "evaluation/fixtures/lineage-image/Dockerfile"


def test_digest_comes_from_structured_build_output():
    text = workflow_text()
    assert "RECEIPT_IMAGE_DIGEST: ${{ steps.build.outputs.digest }}" in text
    assert '"digest_source": "build_push_action_output"' in text


@pytest.mark.parametrize(
    "receipt_field",
    [
        "commit_sha",
        "workflow_name",
        "workflow_ref",
        "workflow_sha",
        "run_id",
        "run_attempt",
        "run_number",
        "image_repository",
        "image_tag",
        "image_digest",
        "immutable_image_ref",
    ],
)
def test_receipt_records_required_provider_field(receipt_field):
    assert f'"{receipt_field}"' in step("Create provider receipt and safe job summary")["run"]


def test_receipt_distinguishes_tag_from_digest():
    receipt_step = step("Create provider receipt and safe job summary")["run"]
    assert '"image_tag": image_tag' in receipt_step
    assert '"image_digest": digest' in receipt_step
    assert 'f"{image_repository}@{digest}"' in receipt_step


def test_receipt_artifact_is_uploaded():
    upload = step("Upload provider receipt")
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert "topo-lineage-receipt-${{ github.run_id }}-${{ github.run_attempt }}" == upload["with"]["name"]


def test_receipt_artifact_retention_is_bounded():
    assert step("Upload provider receipt")["with"]["retention-days"] == "30"


def test_oci_source_label_is_present():
    assert "org.opencontainers.image.source=${{ github.server_url }}/${{ github.repository }}" in workflow_text()


def test_oci_revision_label_is_present():
    assert "org.opencontainers.image.revision=${{ github.sha }}" in workflow_text()


@pytest.mark.parametrize(
    "label",
    ["topo.eval.github.run_id", "topo.eval.github.run_attempt", "topo.eval.github.workflow_ref"],
)
def test_evaluation_run_metadata_label_is_present(label):
    assert label in workflow_text()


def test_dockerfile_contains_no_secret_material():
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    for forbidden in ("token", "password", "credential", "authorization", "private_key"):
        assert forbidden not in text


def test_dockerfile_is_harmless_and_not_intentionally_failing():
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    assert "exit 1" not in text
    assert "exit 17" not in text
    assert "rm -rf" not in text


def test_dockerfile_exposes_no_service():
    text = DOCKERFILE.read_text(encoding="utf-8").lower()
    assert "expose " not in text
    assert "listen" not in text
    assert "httpd" not in text


def test_image_runtime_is_long_running_and_non_root():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER 65532:65532" in text
    assert 'ENTRYPOINT ["/opt/topo/run.sh"]' in text
    assert "while :; do" in RUN_SCRIPT.read_text(encoding="utf-8")
    assert RUNTIME_MODE.read_bytes() == b"healthy\n"


def test_schema_validates_representative_receipt():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    validate_schema_subset(receipt, schema)


def test_schema_rejects_secret_shaped_unknown_field():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    receipt["token"] = "unsafe"
    with pytest.raises(AssertionError, match="unknown fields"):
        validate_schema_subset(receipt, schema)


def test_secret_filter_redacts_secret_shaped_receipt_values():
    receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    receipt["authorization"] = "Bearer unsafe"
    safe = sanitize_provider_receipt(receipt)
    assert safe["authorization"] == "[REDACTED]"
    assert contains_unredacted_secret_like_fields(safe) is False


def test_workflow_does_not_print_raw_secrets():
    lowered = workflow_text().lower()
    assert 'echo "${{ secrets.' not in lowered
    assert "print(os.environ" not in lowered
    assert "github_token" not in step("Create provider receipt and safe job summary")["run"].lower()


@pytest.mark.parametrize("forbidden", ["printenv", "env |", "tojson(github)", "github.event_path", "github.event }}"])
def test_workflow_does_not_dump_context_or_environment(forbidden):
    assert forbidden not in workflow_text().lower()


def test_fixture_contains_no_sentinel_or_blast_special_case():
    content = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in (WORKFLOW, DOCKERFILE, SCHEMA, EXAMPLE, DOC)
    )
    assert "sentinel-" not in content
    assert "blast-" not in content


def test_product_diff_is_scoped_to_h3_r1_after_provider_fixture():
    assert_product_diff_scoped_to_h3_r1(ROOT)


@pytest.mark.parametrize("filename,expected_hash", PERMANENT_MANIFEST_HASHES.items())
def test_permanent_manifest_hash_is_unchanged(filename, expected_hash):
    completed = subprocess.run(
        ["git", "hash-object", f"evaluation/manifests/{filename}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout.strip() == expected_hash


def test_no_package_cleanup_job_exists():
    lowered = workflow_text().lower()
    assert "delete-package" not in lowered
    assert "package delete" not in lowered
    assert "gh api --method delete" not in lowered


def test_receipt_schema_is_strict_and_versioned():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema_version"]["const"] == "eval-lineage-provider-receipt-v1"


def test_workflow_uses_repository_action_major_convention():
    text = workflow_text()
    assert "actions/checkout@v6" in text
    assert "actions/upload-artifact@v7" in text
    assert "docker/setup-buildx-action@v4" in text
    assert "docker/login-action@v4" in text
    assert "docker/build-push-action@v7" in text


def test_merging_workflow_has_no_execution_side_effect():
    assert set(workflow()["on"]) == {"workflow_dispatch"}
    assert "workflow_dispatch" not in (workflow()["on"]["workflow_dispatch"] or {}).get("branches", {})


def test_receipt_document_separates_provenance_from_causality():
    text = DOC.read_text(encoding="utf-8").lower()
    assert "does not prove that a commit caused a runtime failure" in text
    assert "mutable diagnostic locator" in text


def test_example_receipt_has_no_unredacted_secret_like_fields():
    receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert contains_unredacted_secret_like_fields(receipt) is False


def test_schema_requires_immutable_digest_and_ref():
    required = set(json.loads(SCHEMA.read_text(encoding="utf-8"))["required"])
    assert {"image_digest", "immutable_image_ref"}.issubset(required)


def test_built_at_is_null_instead_of_invented():
    receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert receipt["built_at"] is None


def test_receipt_generation_is_structured_python_json():
    run = step("Create provider receipt and safe job summary")["run"]
    assert "json.dumps(receipt, indent=2, sort_keys=True)" in run
    assert "python - <<'PY'" in run


def test_job_summary_uses_allowlisted_safe_receipt_fields():
    run = step("Create provider receipt and safe job summary")["run"]
    for forbidden in ("authorization", "password", "token", "email", "event_payload"):
        assert f"receipt['{forbidden}']" not in run.lower()
