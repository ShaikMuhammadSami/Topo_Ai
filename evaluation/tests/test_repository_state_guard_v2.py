from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from evaluation.product_diff_guard import (
    H3_R1_HISTORICAL_PRODUCT_PATHS,
    H3_R1_PRODUCT_BASELINE,
    PRODUCT_SOURCE_ROOTS,
    assert_text_file_git_blob_id,
    assert_file_sha256,
    assert_h3_r1_historical_product_scope,
    assert_historical_path_scope,
    evaluate_historical_scope,
    git_text_blob_id,
    historical_commit_paths,
    scan_repository_text,
)


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/topo-lineage-provider-fixture.yml"
WORKFLOW_SHA256 = (
    "145a10245d575e02a756be018aaa25c2eabd1d39cde82b43aebd0d605d951903"
)
SENTINEL_A = ROOT / "evaluation/manifests/sentinel-a.json"
SENTINEL_A_GIT_BLOB = "599ba19827d5097fded3f52264cad8dd35abb839"


def test_future_product_diff_is_not_an_immutable_baseline_violation() -> None:
    future_path = "backend/app/services/example_future_repair.py"
    result = evaluate_historical_scope(
        expected_paths={"backend/app/services/accepted_repair.py"},
        observed_historical_paths={"backend/app/services/accepted_repair.py"},
        current_worktree_paths={future_path},
    )
    assert result.valid is True
    assert result.non_authoritative_worktree_paths == (future_path,)


def test_actual_historical_scope_violation_still_fails() -> None:
    with pytest.raises(AssertionError, match="unexpected"):
        assert_historical_path_scope(
            baseline_name="synthetic accepted repair",
            expected_paths={"backend/app/services/accepted_repair.py"},
            observed_historical_paths={
                "backend/app/services/accepted_repair.py",
                "backend/app/services/unaccepted_change.py",
            },
        )


def test_accepted_h3_r1_historical_scope_is_exact() -> None:
    assert_h3_r1_historical_product_scope(ROOT)
    actual = historical_commit_paths(
        ROOT,
        commit=H3_R1_PRODUCT_BASELINE.commit,
        pathspecs=PRODUCT_SOURCE_ROOTS,
    )
    assert frozenset(actual) == H3_R1_HISTORICAL_PRODUCT_PATHS


def test_frozen_workflow_mutation_still_fails(tmp_path: Path) -> None:
    candidate = tmp_path / "workflow.yml"
    candidate.write_bytes(WORKFLOW.read_bytes())
    assert_file_sha256(candidate, WORKFLOW_SHA256)
    candidate.write_bytes(candidate.read_bytes() + b"\n# mutation\n")
    with pytest.raises(AssertionError, match="Frozen file hash changed"):
        assert_file_sha256(candidate, WORKFLOW_SHA256)


def test_permanent_manifest_mutation_still_fails(tmp_path: Path) -> None:
    candidate = tmp_path / "manifest.json"
    candidate.write_bytes(SENTINEL_A.read_bytes())
    assert_text_file_git_blob_id(candidate, SENTINEL_A_GIT_BLOB)
    candidate.write_bytes(candidate.read_bytes() + b"\n")
    with pytest.raises(AssertionError, match="Frozen Git blob changed"):
        assert_text_file_git_blob_id(candidate, SENTINEL_A_GIT_BLOB)


def test_git_blob_id_matches_accepted_manifest_identity() -> None:
    assert git_text_blob_id(SENTINEL_A.read_bytes()) == SENTINEL_A_GIT_BLOB


def test_forbidden_product_literal_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        'SCENARIO = "lineage-source-to-runtime-v1"\n',
        encoding="utf-8",
    )
    matches = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("lineage-source-to-runtime-v1|topo-eval-lineage",),
    )
    assert [(match.path, match.line_number) for match in matches] == [
        ("backend/app/service.py", 1)
    ]


def test_source_scan_does_not_depend_on_ripgrep_or_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    (source / "service.py").write_text("topo-eval-lineage\n", encoding="utf-8")
    monkeypatch.setenv("PATH", "")
    matches = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("topo-eval-lineage",),
    )
    assert len(matches) == 1


def test_binary_and_invalid_utf8_files_are_skipped(tmp_path: Path) -> None:
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    (source / "binary.bin").write_bytes(b"topo-eval-lineage\x00binary")
    (source / "invalid.txt").write_bytes(b"\xff\xfe\xfd")
    assert scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("topo-eval-lineage",),
    ) == ()


def test_unreadable_file_handling_is_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    unreadable = source / "unreadable.py"
    unreadable.write_text("topo-eval-lineage\n", encoding="utf-8")
    original = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == unreadable:
            raise OSError("synthetic unreadable file")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    first = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("topo-eval-lineage",),
    )
    second = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("topo-eval-lineage",),
    )
    assert first == second == ()


def test_scan_result_order_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "backend/app"
    source.mkdir(parents=True)
    (source / "z.py").write_text("second\nneedle\n", encoding="utf-8")
    (source / "a.py").write_text("needle\n", encoding="utf-8")
    first = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("needle",),
    )
    second = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("needle",),
    )
    assert first == second
    assert [(item.path, item.line_number) for item in first] == [
        ("backend/app/a.py", 1),
        ("backend/app/z.py", 2),
    ]


def test_scanner_respects_source_roots_and_exclusions(tmp_path: Path) -> None:
    included = tmp_path / "backend/app/service.py"
    included.parent.mkdir(parents=True)
    included.write_text("needle\n", encoding="utf-8")
    excluded = tmp_path / "backend/app/node_modules/package.js"
    excluded.parent.mkdir(parents=True)
    excluded.write_text("needle\n", encoding="utf-8")
    outside = tmp_path / "evaluation/answer.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("needle\n", encoding="utf-8")
    matches = scan_repository_text(
        tmp_path,
        source_roots=("backend/app",),
        patterns=("needle",),
    )
    assert [item.path for item in matches] == ["backend/app/service.py"]


def test_guard_implementation_has_no_branch_or_current_repair_special_case() -> None:
    source = (ROOT / "evaluation/product_diff_guard.py").read_text(
        encoding="utf-8"
    ).lower()
    for forbidden in (
        "branch --show-current",
        "git status",
        "--porcelain",
        "feature/",
        "sc-1",
        "source_file_mutations",
        "example_future_repair",
        "allowlist",
    ):
        assert forbidden not in source


def test_guard_imports_no_product_implementation() -> None:
    source = (ROOT / "evaluation/product_diff_guard.py").read_text(
        encoding="utf-8"
    )
    assert "from app." not in source
    assert "import app." not in source
    assert "backend.app" not in source


def test_workflow_hash_uses_exact_bytes() -> None:
    assert hashlib.sha256(WORKFLOW.read_bytes()).hexdigest() == WORKFLOW_SHA256
