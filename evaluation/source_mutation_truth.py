from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_MUTATION_VERSION = "eval-source-mutation-v1"
FIXTURE_FILE = "evaluation/fixtures/lineage-image/runtime-mode.txt"
HEALTHY_BYTES = b"healthy\n"
FAIL_BYTES = b"fail\n"
FAIL_EXIT_CODE = 42

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def semantic_mode(value: bytes) -> str:
    if value == HEALTHY_BYTES:
        return "healthy"
    if value == FAIL_BYTES:
        return "fail"
    raise ValueError("Runtime mode is not one canonical fixture value.")


def pending_source_mutation_contract() -> dict[str, Any]:
    return {
        "schema_version": SOURCE_MUTATION_VERSION,
        "status": "pending",
        "provider": "github",
        "repository_id": None,
        "repository": None,
        "parent_commit_sha": None,
        "commit_sha": None,
        "file_path": FIXTURE_FILE,
        "mutation_family": "file_content_change",
        "before_hash": sha256_bytes(HEALTHY_BYTES),
        "after_hash": sha256_bytes(FAIL_BYTES),
        "before_semantic_value": "healthy",
        "after_semantic_value": "fail",
        "expected_failure_mechanism": {
            "type": "container_entrypoint_exit",
            "exit_code": FAIL_EXIT_CODE,
        },
        "scenario_role": "initiating_mutation",
        "truth_source": "git_provider",
        "topo_output_used": False,
    }


def source_mutation_contract(
    *,
    repository_id: str | int,
    repository: str,
    parent_commit_sha: str,
    commit_sha: str,
    before: bytes,
    after: bytes,
) -> dict[str, Any]:
    value = pending_source_mutation_contract()
    value.update(
        {
            "status": "complete",
            "repository_id": str(repository_id),
            "repository": repository,
            "parent_commit_sha": parent_commit_sha.lower(),
            "commit_sha": commit_sha.lower(),
            "before_hash": sha256_bytes(before),
            "after_hash": sha256_bytes(after),
            "before_semantic_value": semantic_mode(before),
            "after_semantic_value": semantic_mode(after),
        }
    )
    validate_source_mutation_contract(value)
    return value


def validate_source_mutation_contract(value: dict[str, Any]) -> None:
    expected_keys = set(pending_source_mutation_contract())
    if set(value) != expected_keys:
        raise ValueError("Source mutation contract fields do not match v1.")
    if value["schema_version"] != SOURCE_MUTATION_VERSION:
        raise ValueError("Unsupported source mutation contract.")
    if value["status"] not in {"pending", "complete"}:
        raise ValueError("Source mutation status is invalid.")
    if value["provider"] != "github" or value["truth_source"] != "git_provider":
        raise ValueError("Source truth must be GitHub/Git provider truth.")
    if value["topo_output_used"] is not False:
        raise ValueError("Topo output cannot define expected source truth.")
    if value["file_path"] != FIXTURE_FILE:
        raise ValueError("Source mutation targets the wrong fixture file.")
    path = PurePosixPath(value["file_path"])
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Source mutation path is unsafe.")
    if value["mutation_family"] != "file_content_change":
        raise ValueError("Source mutation family is invalid.")
    if value["before_hash"] != sha256_bytes(HEALTHY_BYTES):
        raise ValueError("Healthy source hash does not match canonical bytes.")
    if value["after_hash"] != sha256_bytes(FAIL_BYTES):
        raise ValueError("Fail source hash does not match canonical bytes.")
    if not _HASH.fullmatch(str(value["before_hash"])) or not _HASH.fullmatch(
        str(value["after_hash"])
    ):
        raise ValueError("Source hashes must be SHA-256 values.")
    if (value["before_semantic_value"], value["after_semantic_value"]) != (
        "healthy",
        "fail",
    ):
        raise ValueError("Source semantics must be healthy to fail.")
    if value["expected_failure_mechanism"] != {
        "type": "container_entrypoint_exit",
        "exit_code": FAIL_EXIT_CODE,
    }:
        raise ValueError("Expected failure mechanism is invalid.")
    if value["scenario_role"] != "initiating_mutation":
        raise ValueError("Source mutation must be the initiating mutation.")

    provider_fields = (
        value["repository_id"],
        value["repository"],
        value["parent_commit_sha"],
        value["commit_sha"],
    )
    if value["status"] == "pending":
        if any(item is not None for item in provider_fields):
            raise ValueError("Pending source truth cannot invent provider IDs.")
        return
    if any(item in (None, "") for item in provider_fields):
        raise ValueError("Complete source truth requires provider IDs.")
    if not str(value["repository_id"]).isdigit():
        raise ValueError("Repository ID is invalid.")
    if not _REPOSITORY.fullmatch(str(value["repository"])):
        raise ValueError("Repository name is invalid.")
    if not _COMMIT_SHA.fullmatch(str(value["parent_commit_sha"])):
        raise ValueError("Parent commit SHA is invalid.")
    if not _COMMIT_SHA.fullmatch(str(value["commit_sha"])):
        raise ValueError("Commit SHA is invalid.")
    if value["parent_commit_sha"] == value["commit_sha"]:
        raise ValueError("Parent and child commits must differ.")


def _git(repo_root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError("Local Git provider-truth lookup failed.")
    return completed.stdout


def source_mutation_from_local_git(
    *,
    repo_root: Path,
    repository_id: str | int,
    repository: str,
    parent_commit_sha: str,
    commit_sha: str,
    file_path: str = FIXTURE_FILE,
) -> dict[str, Any]:
    """Derive expected source truth from provider-bound local Git objects."""

    parent = parent_commit_sha.lower()
    child = commit_sha.lower()
    if not _COMMIT_SHA.fullmatch(parent) or not _COMMIT_SHA.fullmatch(child):
        raise ValueError("Full parent and child Git SHAs are required.")
    if file_path != FIXTURE_FILE:
        raise ValueError("LINEAGE-1 v1 permits only the canonical mode file.")

    ancestry = _git(repo_root, "rev-list", "--parents", "-n", "1", child)
    tokens = ancestry.decode("ascii").strip().split()
    if not tokens or tokens[0] != child or parent not in tokens[1:]:
        raise ValueError("Claimed parent is not a direct parent of the child commit.")

    changed_files = _git(
        repo_root,
        "diff",
        "--name-only",
        "--no-renames",
        parent,
        child,
        "--",
    ).decode("utf-8").splitlines()
    if changed_files != [file_path]:
        raise ValueError("Causal source commit must change only runtime-mode.txt.")

    before = _git(repo_root, "show", f"{parent}:{file_path}")
    after = _git(repo_root, "show", f"{child}:{file_path}")
    return source_mutation_contract(
        repository_id=repository_id,
        repository=repository,
        parent_commit_sha=parent,
        commit_sha=child,
        before=before,
        after=after,
    )
