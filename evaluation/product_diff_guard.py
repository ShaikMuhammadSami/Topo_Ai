from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PRODUCT_SOURCE_ROOTS = (
    "backend/app",
    "backend/tests",
    "agent/src",
    "frontend",
    "cli/src",
)

H3_R1_ACCEPTED_COMMIT = (
    "38fd5e437b48250c654a96f236ea7d5e20eb5de0"
)

H3_R1_HISTORICAL_PRODUCT_PATHS = frozenset(
    {
        "backend/app/api/github.py",
        "backend/app/connectors/github_connector.py",
        "backend/app/db/models.py",
        "backend/app/models/build_artifacts.py",
        "backend/app/repositories/build_artifact_evidence_repository.py",
        "backend/app/services/github_actions_artifact_lineage.py",
        "backend/app/services/github_actions_build_record.py",
        "backend/app/services/github_actions_graph.py",
        "backend/tests/test_github_actions_build_lineage.py",
        "backend/tests/test_relationship_provenance.py",
    }
)

DEFAULT_SCAN_EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
    }
)


@dataclass(frozen=True)
class HistoricalCommitBaseline:
    name: str
    commit: str
    expected_paths: frozenset[str]
    pathspecs: tuple[str, ...] = PRODUCT_SOURCE_ROOTS


@dataclass(frozen=True)
class HistoricalScopeResult:
    missing_paths: tuple[str, ...]
    unexpected_paths: tuple[str, ...]
    non_authoritative_worktree_paths: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.missing_paths and not self.unexpected_paths


@dataclass(frozen=True, order=True)
class SourceTextMatch:
    path: str
    line_number: int
    pattern: str


H3_R1_PRODUCT_BASELINE = HistoricalCommitBaseline(
    name="H3-R1 product repair",
    commit=H3_R1_ACCEPTED_COMMIT,
    expected_paths=H3_R1_HISTORICAL_PRODUCT_PATHS,
)


def evaluate_historical_scope(
    *,
    expected_paths: Iterable[str],
    observed_historical_paths: Iterable[str],
    current_worktree_paths: Iterable[str] = (),
) -> HistoricalScopeResult:
    """Compare immutable history; dirty worktree paths are diagnostic only."""
    expected = frozenset(path.replace("\\", "/") for path in expected_paths)
    observed = frozenset(
        path.replace("\\", "/") for path in observed_historical_paths
    )
    return HistoricalScopeResult(
        missing_paths=tuple(sorted(expected - observed)),
        unexpected_paths=tuple(sorted(observed - expected)),
        non_authoritative_worktree_paths=tuple(
            sorted(path.replace("\\", "/") for path in current_worktree_paths)
        ),
    )


def assert_historical_path_scope(
    *,
    baseline_name: str,
    expected_paths: Iterable[str],
    observed_historical_paths: Iterable[str],
    current_worktree_paths: Iterable[str] = (),
) -> None:
    result = evaluate_historical_scope(
        expected_paths=expected_paths,
        observed_historical_paths=observed_historical_paths,
        current_worktree_paths=current_worktree_paths,
    )
    if not result.valid:
        raise AssertionError(
            f"{baseline_name} historical path baseline changed; "
            f"missing={list(result.missing_paths)}, "
            f"unexpected={list(result.unexpected_paths)}"
        )


def historical_commit_paths(
    root: Path,
    *,
    commit: str,
    pathspecs: Sequence[str] = PRODUCT_SOURCE_ROOTS,
) -> tuple[str, ...]:
    completed = subprocess.run(
        [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            commit,
            "--",
            *pathspecs,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(
        sorted(
            line.strip().replace("\\", "/")
            for line in completed.stdout.splitlines()
            if line.strip()
        )
    )


def assert_historical_commit_scope(
    root: Path,
    baseline: HistoricalCommitBaseline,
) -> None:
    assert_historical_path_scope(
        baseline_name=baseline.name,
        expected_paths=baseline.expected_paths,
        observed_historical_paths=historical_commit_paths(
            root,
            commit=baseline.commit,
            pathspecs=baseline.pathspecs,
        ),
    )


def assert_historical_commit_excludes_paths(
    root: Path,
    *,
    name: str,
    commit: str,
    prohibited_pathspecs: Sequence[str] = PRODUCT_SOURCE_ROOTS,
) -> None:
    assert_historical_path_scope(
        baseline_name=name,
        expected_paths=(),
        observed_historical_paths=historical_commit_paths(
            root,
            commit=commit,
            pathspecs=prohibited_pathspecs,
        ),
    )


def assert_h3_r1_historical_product_scope(root: Path) -> None:
    assert_historical_commit_scope(root, H3_R1_PRODUCT_BASELINE)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_file_sha256(path: Path, expected: str) -> None:
    actual = file_sha256(path)
    if actual != expected:
        raise AssertionError(
            f"Frozen file hash changed for {path}: expected {expected}, got {actual}"
        )


def git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def git_text_blob_id(content: bytes) -> str:
    """Apply the repository's text line-ending normalization before hashing."""
    return git_blob_id(content.replace(b"\r\n", b"\n"))


def assert_text_file_git_blob_id(path: Path, expected: str) -> None:
    actual = git_text_blob_id(path.read_bytes())
    if actual != expected:
        raise AssertionError(
            f"Frozen Git blob changed for {path}: expected {expected}, got {actual}"
        )


def _candidate_files(
    root: Path,
    source_roots: Sequence[str],
    excluded_directories: frozenset[str],
) -> tuple[Path, ...]:
    files: set[Path] = set()
    for relative_root in source_roots:
        source_root = root / relative_root
        if source_root.is_file():
            files.add(source_root)
            continue
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*"):
            try:
                relative_parts = path.relative_to(root).parts
            except ValueError:
                continue
            if any(part in excluded_directories for part in relative_parts):
                continue
            if path.is_file() and not path.is_symlink():
                files.add(path)
    return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))


def scan_repository_text(
    root: Path,
    *,
    source_roots: Sequence[str],
    patterns: Sequence[str],
    excluded_directories: frozenset[str] = DEFAULT_SCAN_EXCLUDED_DIRECTORIES,
) -> tuple[SourceTextMatch, ...]:
    """Deterministically scan bounded source roots without shell utilities."""
    compiled = tuple((pattern, re.compile(pattern)) for pattern in patterns)
    matches: list[SourceTextMatch] = []
    for path in _candidate_files(root, source_roots, excluded_directories):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern, regex in compiled:
                if regex.search(line):
                    matches.append(
                        SourceTextMatch(
                            path=relative,
                            line_number=line_number,
                            pattern=pattern,
                        )
                    )
    return tuple(sorted(matches))
