"""The real artifact writer is GitHub discovery, not webhook normalization."""

from sqlalchemy import select

from app.db.models import BuildArtifactEvidenceRecord
from app.repositories.build_artifact_evidence_repository import list_build_artifact_evidence
from test_github_actions_build_lineage import _exercise, TEST_TENANT


def test_provider_artifact_discovery_persists_and_scopes_authoritative_tenant():
    session, *_ = _exercise()
    try:
        rows = session.scalars(select(BuildArtifactEvidenceRecord)).all()
        assert rows and all(row.tenant_id == TEST_TENANT for row in rows)
        assert list_build_artifact_evidence(
            session, repository_id=rows[0].repository_id, tenant_id=TEST_TENANT
        )
        assert list_build_artifact_evidence(
            session, repository_id=rows[0].repository_id,
            tenant_id="tenant:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        ) == []
    finally:
        session.close()
