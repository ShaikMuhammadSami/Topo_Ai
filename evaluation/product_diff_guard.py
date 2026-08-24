from __future__ import annotations

import subprocess
from pathlib import Path


H3_R1_PRODUCT_PATHS = frozenset(
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


def assert_product_diff_scoped_to_h3_r1(root: Path) -> None:
    """Preserve older evaluation guards while an authorized product fix exists."""

    completed = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "backend/app",
            "backend/tests",
            "agent/src",
            "frontend",
            "cli/src",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    changed = {
        line[3:].replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
    }
    unexpected = changed - H3_R1_PRODUCT_PATHS
    assert not unexpected, (
        "Product diff escaped the exact H3-R1 repair scope: "
        + ", ".join(sorted(unexpected))
    )

