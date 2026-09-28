from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import pytest
from test_domain_tenant_enforcement import (  # noqa: F401
    sqlite_tenant_app,
    tenant_app,
    two_tenants,
)
from test_tenant_foundation import _bearer

from app.api import github as github_api
from app.connectors import github_connector
from app.models.topology import GraphSnapshot
from app.repositories.change_source_repository import load_change_source
from app.repositories.snapshot_repository import load_snapshot, save_snapshot
from app.services.github_source_authority import (
    REPOSITORY_AMBIGUOUS,
    REPOSITORY_INVALID,
    REPOSITORY_REQUIRED,
    SOURCE_PROVIDER_INVALID,
    SOURCE_UNAVAILABLE,
    github_settings_from_filters_json,
)
from app.services.sample_topology import build_sample_snapshot
from app.services.secret_consumer_policy import source_binding

FIXTURE_REPOSITORY = "ShaikMuhammadSami/topoai-golden-fixture"
COMMIT_SHA = "78a9669b6977597d2d656c428fd64cde0866ed8c"
RUN_ID = 36470584042


class RecordingGitHubConnector:
    repositories: ClassVar[list[str]] = []

    def __init__(self, settings):
        self.settings = settings
        self.repositories.append(settings.full_name)

    def get_repository(self):
        return {
            "id": 8675309,
            "full_name": self.settings.full_name,
            "default_branch": "main",
            "private": False,
        }

    def list_commits(self, limit=None):
        del limit
        return [
            {
                "sha": COMMIT_SHA,
                "commit": {
                    "message": "Healthy fixture authority",
                    "author": {"date": "2026-09-28T20:00:00Z"},
                    "committer": {"date": "2026-09-28T20:00:00Z"},
                },
            }
        ]

    def list_workflow_runs(self, limit=50):
        del limit
        return [
            {
                "id": RUN_ID,
                "run_attempt": 1,
                "run_number": 1,
                "workflow_id": 101,
                "name": "Build Golden Fixture Image",
                "head_sha": COMMIT_SHA,
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-09-28T20:00:00Z",
                "run_started_at": "2026-09-28T20:00:01Z",
                "updated_at": "2026-09-28T20:01:00Z",
            }
        ]

    def list_workflow_run_artifacts(self, run_id):
        assert str(run_id) == str(RUN_ID)
        return []


def _create_source(
    client,
    *,
    token: str,
    tenant_id: str,
    repositories: list[str],
    source_type: str = "github",
    enabled: bool = True,
) -> str:
    response = client.post(
        "/api/v1/change-sources",
        headers=_bearer(token, tenant_id),
        json={
            "name": f"G1Q-F {source_type} {len(repositories)}",
            "source_type": source_type,
            "credential": "g1q-f-test-webhook-secret",
            "enabled": enabled,
            "config": {},
            "filters": {"repositories": repositories},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["source_id"]


def _snapshot(factory, tenant_id: str) -> GraphSnapshot:
    snapshot = build_sample_snapshot()
    with factory() as session:
        save_snapshot(session, snapshot, tenant_id=tenant_id)
    return snapshot


def test_source_scoped_commit_and_actions_enrichment_ignore_static_repository(
    two_tenants, monkeypatch
):
    client, factory, tokens, tenant_a, _tenant_b = two_tenants
    monkeypatch.setenv("TOPO_GITHUB_OWNER", "wrong-static-owner")
    monkeypatch.setenv("TOPO_GITHUB_REPO", "wrong-static-repository")
    RecordingGitHubConnector.repositories = []
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)

    source_id = _create_source(
        client,
        token=tokens["bootstrap"],
        tenant_id=tenant_a,
        repositories=[FIXTURE_REPOSITORY],
    )
    snapshot = _snapshot(factory, tenant_a)
    headers = _bearer(tokens["bootstrap"], tenant_a)

    commit_response = client.post(
        "/api/v1/github/enrich",
        headers=headers,
        params={
            "snapshot_id": snapshot.snapshot_id,
            "source_id": source_id,
            "repository": "caller/override-is-ignored",
        },
    )
    assert commit_response.status_code == 201, commit_response.text
    assert commit_response.json()["repository"] == FIXTURE_REPOSITORY

    actions_response = client.post(
        "/api/v1/github/actions/enrich",
        headers=headers,
        params={
            "snapshot_id": commit_response.json()["enriched_snapshot_id"],
            "source_id": source_id,
            "repository": "caller/override-is-ignored",
        },
    )
    assert actions_response.status_code == 201, actions_response.text
    assert actions_response.json()["repository"] == FIXTURE_REPOSITORY
    assert RecordingGitHubConnector.repositories == [
        FIXTURE_REPOSITORY,
        FIXTURE_REPOSITORY,
    ]

    with factory() as session:
        enriched = load_snapshot(
            session,
            actions_response.json()["enriched_snapshot_id"],
            tenant_id=tenant_a,
        )
    assert enriched is not None
    assert any(
        entity.kind == "GitRepository" and entity.name == FIXTURE_REPOSITORY
        for entity in enriched.entities
    )
    assert any(
        entity.kind == "GitCommit"
        and str(entity.properties.get("sha") or entity.external_id).lower()
        == COMMIT_SHA
        for entity in enriched.entities
    )
    assert any(
        entity.kind == "GitHubWorkflowRun"
        and str(entity.properties.get("run_id")) == str(RUN_ID)
        and entity.properties.get("head_sha") == COMMIT_SHA
        for entity in enriched.entities
    )


@pytest.mark.parametrize(
    ("repositories", "expected_detail"),
    [
        ([], REPOSITORY_REQUIRED),
        (["acme/one", "acme/two"], REPOSITORY_AMBIGUOUS),
        (["https://github.com/acme/repository"], REPOSITORY_INVALID),
    ],
)
def test_source_repository_cardinality_and_format_are_bounded(
    two_tenants, monkeypatch, repositories, expected_detail
):
    client, factory, tokens, tenant_a, _tenant_b = two_tenants
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)
    source_id = _create_source(
        client,
        token=tokens["bootstrap"],
        tenant_id=tenant_a,
        repositories=repositories,
    )
    snapshot = _snapshot(factory, tenant_a)
    response = client.post(
        "/api/v1/github/enrich",
        headers=_bearer(tokens["bootstrap"], tenant_a),
        params={"snapshot_id": snapshot.snapshot_id, "source_id": source_id},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": expected_detail}


def test_non_github_and_disabled_sources_are_rejected(two_tenants, monkeypatch):
    client, factory, tokens, tenant_a, _tenant_b = two_tenants
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)
    snapshot = _snapshot(factory, tenant_a)
    headers = _bearer(tokens["bootstrap"], tenant_a)

    non_github = _create_source(
        client,
        token=tokens["bootstrap"],
        tenant_id=tenant_a,
        repositories=[FIXTURE_REPOSITORY],
        source_type="gitlab",
    )
    response = client.post(
        "/api/v1/github/enrich",
        headers=headers,
        params={"snapshot_id": snapshot.snapshot_id, "source_id": non_github},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": SOURCE_PROVIDER_INVALID}

    disabled = _create_source(
        client,
        token=tokens["bootstrap"],
        tenant_id=tenant_a,
        repositories=[FIXTURE_REPOSITORY],
        enabled=False,
    )
    response = client.post(
        "/api/v1/github/enrich",
        headers=headers,
        params={"snapshot_id": snapshot.snapshot_id, "source_id": disabled},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": SOURCE_UNAVAILABLE}


def test_revoked_source_credential_is_unavailable(two_tenants, monkeypatch):
    client, factory, tokens, tenant_a, _tenant_b = two_tenants
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)
    source_id = _create_source(
        client,
        token=tokens["bootstrap"],
        tenant_id=tenant_a,
        repositories=[FIXTURE_REPOSITORY],
    )
    snapshot = _snapshot(factory, tenant_a)

    with factory() as session:
        record = load_change_source(
            session,
            tenant_id=tenant_a,
            source_id=source_id,
        )
        assert record is not None and record.secret_ref is not None
        binding = source_binding(
            tenant_id=tenant_a,
            source_id=record.source_id,
            source_type=record.source_type,
            config=json.loads(record.config_json),
        )
        store = client.app.state.secret_store
        descriptor = store.describe(session, binding, record.secret_ref)
        store.revoke(
            session,
            binding,
            record.secret_ref,
            actor="test:g1q-f",
            expected_row_version=descriptor.row_version,
        )
        session.commit()

    response = client.post(
        "/api/v1/github/enrich",
        headers=_bearer(tokens["bootstrap"], tenant_a),
        params={"snapshot_id": snapshot.snapshot_id, "source_id": source_id},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": SOURCE_UNAVAILABLE}


def test_unknown_and_cross_tenant_sources_are_not_found(two_tenants, monkeypatch):
    client, factory, tokens, tenant_a, tenant_b = two_tenants
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)
    snapshot = _snapshot(factory, tenant_a)
    headers = _bearer(tokens["bootstrap"], tenant_a)
    source_b = _create_source(
        client,
        token=tokens["other_admin"],
        tenant_id=tenant_b,
        repositories=[FIXTURE_REPOSITORY],
    )
    for source_id in ("change-source:github:absent", source_b):
        response = client.post(
            "/api/v1/github/enrich",
            headers=headers,
            params={"snapshot_id": snapshot.snapshot_id, "source_id": source_id},
        )
        assert response.status_code == 404
        assert response.json() == {"detail": "GITHUB_CHANGE_SOURCE_NOT_FOUND"}


def test_legacy_static_enrichment_remains_separate(two_tenants, monkeypatch):
    client, factory, tokens, tenant_a, _tenant_b = two_tenants
    monkeypatch.setenv("TOPO_GITHUB_OWNER", "legacy-owner")
    monkeypatch.setenv("TOPO_GITHUB_REPO", "legacy-repository")
    RecordingGitHubConnector.repositories = []
    monkeypatch.setattr(github_api, "GitHubConnector", RecordingGitHubConnector)
    snapshot = _snapshot(factory, tenant_a)
    response = client.post(
        "/api/v1/github/enrich",
        headers=_bearer(tokens["bootstrap"], tenant_a),
        params={"snapshot_id": snapshot.snapshot_id},
    )
    assert response.status_code == 201, response.text
    assert RecordingGitHubConnector.repositories == [
        "legacy-owner/legacy-repository"
    ]


def test_call_local_settings_are_concurrency_isolated(monkeypatch):
    monkeypatch.setenv("TOPO_GITHUB_OWNER", "unrelated-static")
    monkeypatch.setenv("TOPO_GITHUB_REPO", "unrelated-static")
    documents = [
        json.dumps({"repositories": ["tenant-a/repository-a"]}),
        json.dumps({"repositories": ["tenant-b/repository-b"]}),
    ] * 100
    with ThreadPoolExecutor(max_workers=8) as executor:
        settings = list(executor.map(github_settings_from_filters_json, documents))
    assert [item.full_name for item in settings] == [
        "tenant-a/repository-a",
        "tenant-b/repository-b",
    ] * 100
    assert all(item.token is None and item.credential_loader is not None for item in settings)


def test_source_scoped_settings_reuse_installation_github_credential(monkeypatch):
    calls: list[str] = []

    def credential_loader(integration: str) -> str:
        calls.append(integration)
        return "installation-secret-marker"

    monkeypatch.setattr(
        github_connector,
        "installation_secret_text",
        credential_loader,
    )
    settings = github_settings_from_filters_json(
        json.dumps({"repositories": [FIXTURE_REPOSITORY]})
    )
    assert settings.token is None
    assert settings.credential_loader is not None
    assert settings.credential_loader() == "installation-secret-marker"
    assert calls == ["github"]
