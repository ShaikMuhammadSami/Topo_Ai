from __future__ import annotations
from app.repositories.tenant_scope import UNOWNED_MACHINE
from domain_tenant_fixtures import TEST_TENANT, seed_domain_tenant

import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.connectors.github_connector import (
    GitHubConnector,
    GitHubConnectorError,
    GitHubFileContent,
    GitHubSettings,
)
from app.db.database import Base
from app.db.models import (
    ChangeEventRecord,
    ChangeSourceDeliveryRecord,
    ChangeSourceRecord,
)
from app.repositories.change_event_repository import change_event_view
from app.services.change_source_ingest import ingest_change_source_webhook
from app.services.github_source_file_enrichment import (
    DEFAULT_MAX_BYTES_PER_FILE,
    enrich_github_push_events,
)
from app.services.external_change_normalizers import normalize_github
from app.services.webhook_security import WebhookAuthenticationError

REPOSITORY_ID = "884422"
REPOSITORY = "example/platform"
PARENT_SHA = "1" * 40
CHILD_SHA = "2" * 40
BEFORE_BLOB = "3" * 40
AFTER_BLOB = "4" * 40
WEBHOOK_SECRET = "source-mutation-test-secret"


class FrozenGitHubProvider:
    def __init__(
        self,
        *,
        repository: dict[str, Any] | None = None,
        commits: dict[str, dict[str, Any]] | None = None,
        contents: dict[tuple[str, str], GitHubFileContent | Exception] | None = None,
    ) -> None:
        self.repository = repository or {
            "id": int(REPOSITORY_ID),
            "full_name": REPOSITORY,
        }
        self.commits = commits or {}
        self.contents = contents or {}
        self.content_calls: list[tuple[str, str, int]] = []

    def get_repository(self) -> dict[str, Any]:
        return self.repository

    def get_commit(self, sha: str) -> dict[str, Any]:
        value = self.commits.get(sha)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise GitHubConnectorError("missing", status_code=404)
        return value

    def get_file_content(
        self,
        *,
        path: str,
        ref: str,
        maximum_bytes: int,
    ) -> GitHubFileContent:
        self.content_calls.append((path, ref, maximum_bytes))
        value = self.contents.get((ref, path))
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise GitHubConnectorError("missing", status_code=404)
        return value


def _file_content(blob: str, content: bytes) -> GitHubFileContent:
    return GitHubFileContent(
        provider_blob_oid=blob,
        size_bytes=len(content),
        content=content,
        capture_state="captured",
    )


def _commit(
    *,
    sha: str = CHILD_SHA,
    parents: list[str] | None = None,
    files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "sha": sha,
        "url": f"https://api.github.test/repos/{REPOSITORY}/commits/{sha}",
        "parents": [
            {"sha": parent}
            for parent in (parents if parents is not None else [PARENT_SHA])
        ],
        "files": files
        if files is not None
        else [
            {
                "status": "modified",
                "filename": "config/mode.txt",
                "sha": AFTER_BLOB,
                "blob_url": "https://github.test/blob/after",
            }
        ],
    }


def _provider(
    *,
    before: bytes = b"ready\n",
    after: bytes = b"stopped\n",
    commit: dict[str, Any] | None = None,
) -> FrozenGitHubProvider:
    value = commit or _commit()
    return FrozenGitHubProvider(
        commits={str(value["sha"]): value},
        contents={
            (PARENT_SHA, "config/mode.txt"): _file_content(BEFORE_BLOB, before),
            (CHILD_SHA, "config/mode.txt"): _file_content(AFTER_BLOB, after),
        },
    )


def _payload(
    *,
    after: str = CHILD_SHA,
    commits: list[str] | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    commit_ids = commits if commits is not None else [after]
    return {
        "ref": "refs/heads/main",
        "before": PARENT_SHA,
        "after": after,
        "size": len(commit_ids) if size is None else size,
        "repository": {
            "id": int(REPOSITORY_ID),
            "full_name": REPOSITORY,
        },
        "sender": {"login": "operator"},
        "head_commit": {
            "id": after,
            "message": "Update runtime configuration",
            "timestamp": "2026-08-24T10:00:00Z",
        },
        "commits": [{"id": sha} for sha in commit_ids],
    }


def _events(payload: dict[str, Any] | None = None):
    return normalize_github(
        event_type="push",
        payload=payload or _payload(),
        config={},
    )


def _enriched(
    provider: FrozenGitHubProvider,
    *,
    payload: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
):
    actual_payload = payload or _payload()
    return enrich_github_push_events(
        events=_events(actual_payload),
        payload=actual_payload,
        config=config or {},
        provider_factory=lambda repository, source_config: provider,
    )[0]


def _session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    seed_domain_tenant(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _source(session: Session) -> ChangeSourceRecord:
    source = ChangeSourceRecord(
        source_id="change-source:github:test",
        name="GitHub test",
        source_type="github",
        enabled=True,
        secret_ref="TOPO_SC1_WEBHOOK_SECRET",
        config_json="{}",
        filters_json="{}",
        status="configured",
        delivery_count=0,
        failure_count=0,
        created_at="2026-08-24T09:00:00+00:00",
        updated_at="2026-08-24T09:00:00+00:00",
    )
    session.add(source)
    session.commit()
    return source


def _signed_headers(body: bytes, delivery: str = "delivery-1") -> dict[str, str]:
    signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return {
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": f"sha256={signature}",
    }


def _ingest(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    provider: FrozenGitHubProvider,
    *,
    payload: dict[str, Any] | None = None,
    delivery: str = "delivery-1",
):
    monkeypatch.setenv("TOPO_SC1_WEBHOOK_SECRET", WEBHOOK_SECRET)
    source = session.get(ChangeSourceRecord, "change-source:github:test")
    if source is None:
        source = _source(session)
    body = json.dumps(payload or _payload(), separators=(",", ":")).encode()
    return ingest_change_source_webhook(
        session,
        source=source,
        body=body,
        headers=_signed_headers(body, delivery),
        github_provider_factory=lambda repository, config: provider,
    )


def _mutation(event) -> dict[str, Any]:
    return event.metadata["source_file_mutations"][0]


def test_signed_push_provider_evidence_survives_durable_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _session_factory()
    with sessions() as session:
        receipt = _ingest(session, monkeypatch, _provider())
        assert receipt.status == "accepted"
        event_id = receipt.event_ids[0]

    with sessions() as session:
        record = session.get(ChangeEventRecord, event_id)
        assert record is not None
        event = change_event_view(session, record=record, tenant_id=UNOWNED_MACHINE)
        mutation = _mutation(event)
        assert event.repository == REPOSITORY
        assert event.commit_sha == CHILD_SHA
        assert mutation["repository"] == {
            "provider": "github",
            "provider_repository_id": REPOSITORY_ID,
            "full_name": REPOSITORY,
        }
        assert mutation["commit_sha"] == CHILD_SHA
        assert mutation["parent_context"] == {
            "context_type": "single_parent",
            "parent_shas": [PARENT_SHA],
        }
        assert mutation["current_path"] == "config/mode.txt"
        assert mutation["before"]["provider_blob_oid"] == BEFORE_BLOB
        assert mutation["after"]["provider_blob_oid"] == AFTER_BLOB
        assert mutation["before"]["semantic_value"] == "ready"
        assert mutation["after"]["semantic_value"] == "stopped"
        serialized = event.model_dump(mode="json")
        assert serialized["metadata"]["source_file_mutations"] == [mutation]


def test_frozen_shape_exact_bytes_are_hashed_before_newline_display() -> None:
    before = b"healthy\n"
    after = b"fail\n"
    event = _enriched(_provider(before=before, after=after))
    mutation = _mutation(event)
    assert mutation["before"]["content_sha256"] == (
        "63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d"
    )
    assert mutation["after"]["content_sha256"] == (
        "2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997"
    )
    assert mutation["before"]["semantic_value"] == "healthy"
    assert mutation["after"]["semantic_value"] == "fail"
    assert hashlib.sha256(before).hexdigest() == mutation["before"]["content_sha256"]
    assert hashlib.sha256(after).hexdigest() == mutation["after"]["content_sha256"]


def test_provider_shaped_responses_flow_through_real_connector_and_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_bytes = b"healthy\n"
    after_bytes = b"fail\n"

    class Response:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload
            self.headers: dict[str, str] = {}
            self.text = json.dumps(payload)
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

        def iter_bytes(self):
            yield json.dumps(self.payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    def provider_get(url: str, **kwargs):
        if url.endswith(f"/repos/{REPOSITORY}"):
            return Response({"id": int(REPOSITORY_ID), "full_name": REPOSITORY})
        if url.endswith(f"/commits/{CHILD_SHA}"):
            return Response(_commit())
        raise AssertionError(f"Unexpected provider GET: {url}")

    def provider_stream(method: str, url: str, **kwargs):
        assert method == "GET"
        ref = kwargs["params"]["ref"]
        assert url.endswith("/contents/config/mode.txt")
        if ref == PARENT_SHA:
            content, blob = before_bytes, BEFORE_BLOB
        elif ref == CHILD_SHA:
            content, blob = after_bytes, AFTER_BLOB
        else:
            raise AssertionError(f"Unexpected ref: {ref}")
        return Response(
            {
                "type": "file",
                "sha": blob,
                "size": len(content),
                "encoding": "base64",
                "content": base64.b64encode(content).decode("ascii"),
            }
        )

    monkeypatch.setattr("app.connectors.github_connector.httpx.get", provider_get)
    monkeypatch.setattr("app.connectors.github_connector.httpx.stream", provider_stream)
    settings = GitHubSettings(
        owner="example",
        repository="platform",
        token="test-provider-token",
        api_url="https://api.github.test",
        api_version="test",
        timeout_seconds=1,
        commit_limit=20,
    )
    connector = GitHubConnector(settings)
    sessions = _session_factory()
    with sessions() as session:
        receipt = _ingest(session, monkeypatch, connector)
        record = session.get(ChangeEventRecord, receipt.event_ids[0])
        assert record is not None
        mutation = _mutation(
            change_event_view(session, record=record, tenant_id=UNOWNED_MACHINE)
        )
        assert (
            mutation["before"]["content_sha256"]
            == hashlib.sha256(before_bytes).hexdigest()
        )
        assert (
            mutation["after"]["content_sha256"]
            == hashlib.sha256(after_bytes).hexdigest()
        )
        assert "test-provider-token" not in record.metadata_json


def test_invalid_signature_is_rejected_before_provider_or_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _session_factory()
    provider = _provider()
    monkeypatch.setenv("TOPO_SC1_WEBHOOK_SECRET", WEBHOOK_SECRET)
    with sessions() as session:
        source = _source(session)
        body = json.dumps(_payload()).encode()
        with pytest.raises(WebhookAuthenticationError):
            ingest_change_source_webhook(
                session,
                source=source,
                body=body,
                headers={
                    "X-GitHub-Event": "push",
                    "X-GitHub-Delivery": "invalid",
                    "X-Hub-Signature-256": "sha256=invalid",
                },
                github_provider_factory=lambda repository, config: provider,
            )
        assert provider.content_calls == []
        assert session.scalar(select(func.count()).select_from(ChangeEventRecord)) == 0
        assert (
            session.scalar(select(func.count()).select_from(ChangeSourceDeliveryRecord))
            == 0
        )


def test_provider_failure_preserves_parent_event_with_explicit_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableProvider(FrozenGitHubProvider):
        def get_repository(self):
            raise GitHubConnectorError("denied", status_code=403)

    sessions = _session_factory()
    with sessions() as session:
        receipt = _ingest(session, monkeypatch, UnavailableProvider())
        record = session.get(ChangeEventRecord, receipt.event_ids[0])
        assert record is not None
        event = change_event_view(session, record=record, tenant_id=UNOWNED_MACHINE)
        capture = event.metadata["source_file_mutation_enrichment"]
        assert capture["completeness"] == "unavailable"
        assert capture["reasons"] == ["permission_denied"]
        assert event.metadata["source_file_mutations"] == []


def test_parent_event_identity_is_stable_when_enrichment_later_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableProvider(FrozenGitHubProvider):
        def get_repository(self):
            raise GitHubConnectorError("temporary")

    sessions = _session_factory()
    with sessions() as session:
        first = _ingest(
            session, monkeypatch, UnavailableProvider(), delivery="delivery-a"
        )
        second = _ingest(
            session, monkeypatch, _provider(), delivery="delivery-b"
        )
        assert first.event_ids == second.event_ids
        assert session.scalar(select(func.count()).select_from(ChangeEventRecord)) == 1
        record = session.get(ChangeEventRecord, first.event_ids[0])
        assert record is not None
        assert record.observation_count == 2
        assert len(json.loads(record.metadata_json)["source_file_mutations"]) == 1


def test_later_provider_failure_does_not_erase_richer_durable_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableProvider(FrozenGitHubProvider):
        def get_repository(self):
            raise GitHubConnectorError("temporary")

    sessions = _session_factory()
    with sessions() as session:
        first = _ingest(session, monkeypatch, _provider(), delivery="delivery-a")
        second = _ingest(
            session, monkeypatch, UnavailableProvider(), delivery="delivery-b"
        )
        assert first.event_ids == second.event_ids
        record = session.get(ChangeEventRecord, first.event_ids[0])
        assert record is not None
        metadata = json.loads(record.metadata_json)
        assert metadata["source_file_mutation_enrichment"]["completeness"] == (
            "complete"
        )
        assert len(metadata["source_file_mutations"]) == 1


def test_same_delivery_replay_does_not_duplicate_event_or_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _session_factory()
    provider = _provider()
    with sessions() as session:
        first = _ingest(session, monkeypatch, provider)
        first_record = session.get(ChangeEventRecord, first.event_ids[0])
        first_metadata = first_record.metadata_json
        second = _ingest(session, monkeypatch, provider)
        assert second.duplicate is True
        assert second.event_ids == first.event_ids
        assert first_record.observation_count == 1
        assert first_record.metadata_json == first_metadata


def test_mutation_identity_and_order_are_deterministic() -> None:
    files = [
        {"status": "added", "filename": "z/value.txt", "sha": "a" * 40},
        {"status": "added", "filename": "A/value.txt", "sha": "b" * 40},
    ]
    commit = _commit(files=files)
    contents = {
        (CHILD_SHA, "z/value.txt"): _file_content("a" * 40, b"one\n"),
        (CHILD_SHA, "A/value.txt"): _file_content("b" * 40, b"two\n"),
    }
    first = _enriched(FrozenGitHubProvider(commits={CHILD_SHA: commit}, contents=contents))
    commit["files"] = list(reversed(files))
    second = _enriched(FrozenGitHubProvider(commits={CHILD_SHA: commit}, contents=contents))
    first_mutations = first.metadata["source_file_mutations"]
    second_mutations = second.metadata["source_file_mutations"]
    assert first_mutations == second_mutations
    assert [item["current_path"] for item in first_mutations] == [
        "A/value.txt",
        "z/value.txt",
    ]
    assert len({item["mutation_id"] for item in first_mutations}) == 2


@pytest.mark.parametrize(
    ("status", "previous_path", "before_state", "after_state"),
    [
        ("added", None, "absent", "present"),
        ("removed", None, "present", "absent"),
        ("modified", None, "present", "present"),
        ("renamed", "old/Exact.txt", "present", "present"),
    ],
)
def test_change_type_side_semantics(
    status: str,
    previous_path: str | None,
    before_state: str,
    after_state: str,
) -> None:
    current_path = "New/Exact.txt"
    file = {
        "status": status,
        "filename": current_path,
        "sha": AFTER_BLOB if status != "removed" else BEFORE_BLOB,
    }
    if previous_path:
        file["previous_filename"] = previous_path
    commit = _commit(files=[file])
    before_path = previous_path or current_path
    contents = {
        (PARENT_SHA, before_path): _file_content(BEFORE_BLOB, b"one\n"),
        (CHILD_SHA, current_path): _file_content(AFTER_BLOB, b"two\n"),
    }
    event = _enriched(
        FrozenGitHubProvider(commits={CHILD_SHA: commit}, contents=contents)
    )
    mutation = _mutation(event)
    assert mutation["change_type"] == status
    assert mutation["current_path"] == current_path
    assert mutation["previous_path"] == previous_path
    assert mutation["before"]["identity_state"] == before_state
    assert mutation["after"]["identity_state"] == after_state
    assert "New/Exact.txt" == mutation["current_path"]


def test_modified_lookup_404_is_unavailable_not_absent() -> None:
    provider = _provider()
    provider.contents[(PARENT_SHA, "config/mode.txt")] = GitHubConnectorError(
        "missing", status_code=404
    )
    mutation = _mutation(_enriched(provider))
    assert mutation["before"]["identity_state"] == "unavailable"
    assert mutation["before"]["content_capture_state"] == "not_found"
    assert mutation["before"]["content_capture_reason"] == "not_found"


def test_multi_parent_before_state_is_explicitly_ambiguous() -> None:
    commit = _commit(parents=[PARENT_SHA, "5" * 40])
    provider = _provider(commit=commit)
    mutation = _mutation(_enriched(provider))
    assert mutation["parent_context"]["context_type"] == "multiple_parents"
    assert mutation["before"]["identity_state"] == "ambiguous"
    assert mutation["before"]["provider_blob_oid"] is None
    assert mutation["completeness"] == "partial"
    assert all(call[1] != PARENT_SHA for call in provider.content_calls)


def test_multiple_commits_keep_commit_specific_mutations() -> None:
    first_sha = "6" * 40
    second_sha = CHILD_SHA
    first_path = "config/first.txt"
    second_path = "config/second.txt"
    first_commit = _commit(
        sha=first_sha,
        files=[{"status": "added", "filename": first_path, "sha": "7" * 40}],
    )
    second_commit = _commit(
        sha=second_sha,
        parents=[first_sha],
        files=[{"status": "added", "filename": second_path, "sha": "8" * 40}],
    )
    provider = FrozenGitHubProvider(
        commits={first_sha: first_commit, second_sha: second_commit},
        contents={
            (first_sha, first_path): _file_content("7" * 40, b"one\n"),
            (second_sha, second_path): _file_content("8" * 40, b"two\n"),
        },
    )
    payload = _payload(commits=[first_sha, second_sha])
    mutations = _enriched(provider, payload=payload).metadata["source_file_mutations"]
    assert {(item["commit_sha"], item["current_path"]) for item in mutations} == {
        (first_sha, first_path),
        (second_sha, second_path),
    }


def test_commit_and_file_bounds_are_explicitly_partial() -> None:
    first_sha = "0" * 40
    second_sha = CHILD_SHA
    files = [
        {"status": "added", "filename": f"config/{index}.txt", "sha": f"{index + 1:x}" * 40}
        for index in range(3)
    ]
    first = _commit(sha=first_sha, files=files)
    second = _commit(sha=second_sha, parents=[first_sha], files=[])
    contents = {
        (first_sha, item["filename"]): _file_content(item["sha"], b"x\n")
        for item in files
    }
    provider = FrozenGitHubProvider(
        commits={first_sha: first, second_sha: second}, contents=contents
    )
    event = _enriched(
        provider,
        payload=_payload(commits=[first_sha, second_sha], size=3),
        config={"source_file_capture": {"maximum_commits": 1, "maximum_files": 1}},
    )
    capture = event.metadata["source_file_mutation_enrichment"]
    assert capture["completeness"] == "partial"
    assert "commit_limit_exceeded" in capture["reasons"]
    assert "provider_push_commit_list_truncated" in capture["reasons"]
    assert "file_limit_exceeded" in capture["reasons"]
    assert capture["mutation_count"] == 1


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"\x00\x01\x02", "binary_content"),
        (b"line-one\nline-two\n", "multiline_text"),
        (b"value with spaces\n", "not_bounded_scalar_text"),
        (b"x" * 257, "scalar_byte_limit_exceeded"),
    ],
)
def test_ineligible_content_keeps_exact_hash_but_not_semantic_text(
    content: bytes,
    reason: str,
) -> None:
    mutation = _mutation(_enriched(_provider(after=content)))
    side = mutation["after"]
    assert side["content_sha256"] == hashlib.sha256(content).hexdigest()
    assert side["semantic_value"] is None
    assert side["semantic_capture_state"] == "ineligible"
    assert side["semantic_capture_reason"] == reason


def test_large_provider_content_is_not_downloaded_or_persisted() -> None:
    provider = _provider()
    provider.contents[(CHILD_SHA, "config/mode.txt")] = GitHubFileContent(
        provider_blob_oid=AFTER_BLOB,
        size_bytes=DEFAULT_MAX_BYTES_PER_FILE + 1,
        content=None,
        capture_state="limit_exceeded",
        capture_reason="per_file_byte_limit_exceeded",
    )
    mutation = _mutation(_enriched(provider))
    side = mutation["after"]
    assert side["provider_blob_oid"] == AFTER_BLOB
    assert side["content_sha256"] is None
    assert side["semantic_value"] is None
    assert side["content_capture_state"] == "limit_exceeded"
    encoded = json.dumps(mutation)
    assert "patch" not in encoded
    assert all(call[2] <= DEFAULT_MAX_BYTES_PER_FILE for call in provider.content_calls)


def test_total_content_budget_is_enforced_without_losing_known_blob_identity() -> None:
    provider = _provider(before=b"first\n", after=b"second\n")
    event = _enriched(
        provider,
        config={"source_file_capture": {"maximum_total_bytes": 6}},
    )
    mutation = _mutation(event)
    assert mutation["before"]["content_capture_state"] == "captured"
    assert mutation["after"]["provider_blob_oid"] == AFTER_BLOB
    assert mutation["after"]["content_capture_state"] == "limit_exceeded"
    assert mutation["after"]["content_capture_reason"] == (
        "total_content_byte_limit_exceeded"
    )


def test_provider_repository_identity_mismatch_creates_no_mutations() -> None:
    provider = _provider()
    provider.repository = {"id": 999, "full_name": REPOSITORY}
    event = _enriched(provider)
    capture = event.metadata["source_file_mutation_enrichment"]
    assert capture["completeness"] == "unavailable"
    assert capture["reasons"] == ["provider_repository_identity_mismatch"]
    assert event.metadata["source_file_mutations"] == []


def test_provider_blob_mismatch_rejects_content_identity() -> None:
    provider = _provider()
    provider.contents[(CHILD_SHA, "config/mode.txt")] = _file_content(
        "9" * 40, b"different\n"
    )
    side = _mutation(_enriched(provider))["after"]
    assert side["provider_blob_oid"] == AFTER_BLOB
    assert side["content_sha256"] is None
    assert side["content_capture_reason"] == "provider_blob_identity_mismatch"


def test_existing_source_change_shape_remains_backwards_compatible() -> None:
    event = _events()[0]
    assert event.external_id == f"github:{REPOSITORY}:{CHILD_SHA}"
    assert event.metadata["ref"] == "refs/heads/main"
    assert event.metadata["before"] == PARENT_SHA
    assert event.metadata["after"] == CHILD_SHA
    assert event.metadata["commit_count"] == 1
    assert "source_file_mutations" not in event.metadata


def test_product_implementation_has_no_forbidden_truth_or_reasoning_dependencies() -> None:
    root = Path(__file__).parents[1] / "app"
    files = [
        root / "models" / "source_file_mutations.py",
        root / "services" / "github_source_file_enrichment.py",
    ]
    original_source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    source = original_source.lower()
    for forbidden in (
        "runtime-mode.txt",
        "4149b194c4c4fdfd",
        "f9b152133a807542",
        "evaluation/fixtures",
        "openai",
        "embedding",
        "fuzzy",
    ):
        assert forbidden not in source
    assert "pathlib" not in source
    assert "subprocess" not in source
    assert "from app.models.topology" not in source
    assert "Entity(" not in original_source
    assert "Relationship(" not in original_source
    assert not any("source_file" in table for table in Base.metadata.tables)


def test_sc1_does_not_change_causal_or_lifecycle_product_modules() -> None:
    repository_root = Path(__file__).parents[2]
    causal_model = (
        repository_root / "backend" / "app" / "models" / "causal_rca.py"
    ).read_text(encoding="utf-8")
    causal_service = (
        repository_root / "backend" / "app" / "services" / "causal_rca.py"
    ).read_text(encoding="utf-8")
    assert "default=180" in causal_model
    assert "if gap_minutes > 180:" in causal_service
    changed_product_modules = {
        "connectors/github_connector.py",
        "models/source_file_mutations.py",
        "services/change_source_ingest.py",
        "services/github_source_file_enrichment.py",
    }
    assert not any("incident_lifecycle" in value for value in changed_product_modules)
    assert not any("causal_" in value for value in changed_product_modules)
    assert not any("github_actions" in value for value in changed_product_modules)
    assert not any("topology" in value for value in changed_product_modules)
