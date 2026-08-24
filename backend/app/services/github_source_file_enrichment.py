from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from app.connectors.github_connector import (
    GitHubConnector,
    GitHubConnectorError,
    GitHubFileContent,
    GitHubResponseLimitError,
    GitHubSettings,
)
from app.models.change_events import ChangeEventCreate
from app.models.source_file_mutations import (
    SourceFileCaptureState,
    SourceFileChangeType,
    SourceFileEvidenceCompleteness,
    SourceFileEvidenceReference,
    SourceFileIdentityState,
    SourceFileMutationEnrichment,
    SourceFileMutationEvidence,
    SourceFileMutationSide,
    SourceFileParentContext,
    SourceFileParentContextType,
    SourceRepositoryIdentity,
)


DEFAULT_MAX_COMMITS = 20
DEFAULT_MAX_FILES = 100
DEFAULT_MAX_BYTES_PER_FILE = 64 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024
DEFAULT_MAX_SCALAR_BYTES = 256
DEFAULT_MAX_SCALAR_CHARACTERS = 128

_SAFE_SCALAR = re.compile(r"^[A-Za-z0-9_.:/@+\-]+$")


class GitHubSourceEvidenceProvider(Protocol):
    def get_repository(self) -> dict[str, Any]: ...

    def get_commit(self, sha: str) -> dict[str, Any]: ...

    def get_file_content(
        self,
        *,
        path: str,
        ref: str,
        maximum_bytes: int,
    ) -> GitHubFileContent: ...


GitHubSourceEvidenceProviderFactory = Callable[
    [str, dict[str, Any]], GitHubSourceEvidenceProvider
]


@dataclass(frozen=True)
class SourceFileCaptureLimits:
    maximum_commits: int = DEFAULT_MAX_COMMITS
    maximum_files: int = DEFAULT_MAX_FILES
    maximum_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE
    maximum_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES
    maximum_scalar_bytes: int = DEFAULT_MAX_SCALAR_BYTES
    maximum_scalar_characters: int = DEFAULT_MAX_SCALAR_CHARACTERS

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SourceFileCaptureLimits":
        raw = config.get("source_file_capture", {})
        if not isinstance(raw, dict):
            raw = {}

        def bounded(name: str, default: int, ceiling: int) -> int:
            value = raw.get(name, default)
            if not isinstance(value, int):
                value = default
            return max(1, min(value, ceiling))

        return cls(
            maximum_commits=bounded(
                "maximum_commits", DEFAULT_MAX_COMMITS, DEFAULT_MAX_COMMITS
            ),
            maximum_files=bounded(
                "maximum_files", DEFAULT_MAX_FILES, DEFAULT_MAX_FILES
            ),
            maximum_bytes_per_file=bounded(
                "maximum_bytes_per_file",
                DEFAULT_MAX_BYTES_PER_FILE,
                DEFAULT_MAX_BYTES_PER_FILE,
            ),
            maximum_total_bytes=bounded(
                "maximum_total_bytes",
                DEFAULT_MAX_TOTAL_BYTES,
                DEFAULT_MAX_TOTAL_BYTES,
            ),
            maximum_scalar_bytes=bounded(
                "maximum_scalar_bytes",
                DEFAULT_MAX_SCALAR_BYTES,
                DEFAULT_MAX_SCALAR_BYTES,
            ),
            maximum_scalar_characters=bounded(
                "maximum_scalar_characters",
                DEFAULT_MAX_SCALAR_CHARACTERS,
                DEFAULT_MAX_SCALAR_CHARACTERS,
            ),
        )

    def model_dict(self) -> dict[str, int]:
        return {
            "maximum_commits": self.maximum_commits,
            "maximum_files": self.maximum_files,
            "maximum_bytes_per_file": self.maximum_bytes_per_file,
            "maximum_total_bytes": self.maximum_total_bytes,
            "maximum_scalar_bytes": self.maximum_scalar_bytes,
            "maximum_scalar_characters": self.maximum_scalar_characters,
        }


@dataclass
class _ByteBudget:
    remaining: int


def github_source_evidence_provider(
    repository_full_name: str,
    config: dict[str, Any],
) -> GitHubSourceEvidenceProvider:
    del config
    parts = repository_full_name.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError("GitHub repository full name must be owner/repository.")
    return GitHubConnector(
        GitHubSettings.for_repository(
            owner=parts[0],
            repository=parts[1],
        )
    )


def _reason_for_error(exc: GitHubConnectorError) -> str:
    if exc.status_code in {401, 403}:
        return "permission_denied"
    if exc.status_code == 404:
        return "not_found"
    return "provider_error"


def _scalar_value(
    content: bytes,
    *,
    limits: SourceFileCaptureLimits,
) -> tuple[str | None, SourceFileCaptureState, str | None]:
    if len(content) > limits.maximum_scalar_bytes:
        return None, SourceFileCaptureState.INELIGIBLE, "scalar_byte_limit_exceeded"
    if b"\x00" in content:
        return None, SourceFileCaptureState.INELIGIBLE, "binary_content"
    try:
        value = content.decode("utf-8")
    except UnicodeDecodeError:
        return None, SourceFileCaptureState.INELIGIBLE, "invalid_utf8"

    # Remove at most one provider-returned terminal newline for display only.
    # Exact byte identity was already computed before this transformation.
    if value.endswith("\n"):
        value = value[:-1]
        if value.endswith("\r"):
            value = value[:-1]
    if "\n" in value or "\r" in value:
        return None, SourceFileCaptureState.INELIGIBLE, "multiline_text"
    if len(value) > limits.maximum_scalar_characters:
        return None, SourceFileCaptureState.INELIGIBLE, "scalar_character_limit_exceeded"
    if not value or not _SAFE_SCALAR.fullmatch(value):
        return None, SourceFileCaptureState.INELIGIBLE, "not_bounded_scalar_text"
    return value, SourceFileCaptureState.CAPTURED, None


def _absent_side(path: str) -> SourceFileMutationSide:
    return SourceFileMutationSide(
        identity_state=SourceFileIdentityState.ABSENT,
        path=path,
        content_capture_state=SourceFileCaptureState.NOT_APPLICABLE,
        content_capture_reason="provider_change_semantics_prove_absence",
        semantic_capture_state=SourceFileCaptureState.NOT_APPLICABLE,
        semantic_capture_reason="provider_change_semantics_prove_absence",
    )


def _ambiguous_side(path: str) -> SourceFileMutationSide:
    return SourceFileMutationSide(
        identity_state=SourceFileIdentityState.AMBIGUOUS,
        path=path,
        content_capture_state=SourceFileCaptureState.AMBIGUOUS,
        content_capture_reason="multiple_parent_commits",
        semantic_capture_state=SourceFileCaptureState.AMBIGUOUS,
        semantic_capture_reason="multiple_parent_commits",
    )


def _unavailable_side(
    path: str,
    *,
    reason: str,
    provider_blob_oid: str | None = None,
    provider_blob_source: str | None = None,
    state: SourceFileCaptureState = SourceFileCaptureState.UNAVAILABLE,
) -> SourceFileMutationSide:
    return SourceFileMutationSide(
        identity_state=(
            SourceFileIdentityState.PRESENT
            if provider_blob_oid
            else SourceFileIdentityState.UNAVAILABLE
        ),
        path=path,
        provider_blob_oid=provider_blob_oid,
        provider_blob_source=provider_blob_source,
        content_capture_state=state,
        content_capture_reason=reason,
        semantic_capture_state=SourceFileCaptureState.UNAVAILABLE,
        semantic_capture_reason=reason,
    )


def _capture_side(
    provider: GitHubSourceEvidenceProvider,
    *,
    path: str,
    ref: str,
    limits: SourceFileCaptureLimits,
    budget: _ByteBudget,
    known_blob_oid: str | None = None,
    known_blob_source: str | None = None,
) -> SourceFileMutationSide:
    if budget.remaining <= 0:
        return _unavailable_side(
            path,
            reason="total_content_byte_limit_exceeded",
            provider_blob_oid=known_blob_oid,
            provider_blob_source=known_blob_source,
            state=SourceFileCaptureState.LIMIT_EXCEEDED,
        )
    request_limit = min(limits.maximum_bytes_per_file, budget.remaining)
    try:
        result = provider.get_file_content(
            path=path,
            ref=ref,
            maximum_bytes=request_limit,
        )
    except GitHubResponseLimitError:
        return _unavailable_side(
            path,
            reason="provider_response_byte_limit_exceeded",
            provider_blob_oid=known_blob_oid,
            provider_blob_source=known_blob_source,
            state=SourceFileCaptureState.LIMIT_EXCEEDED,
        )
    except GitHubConnectorError as exc:
        reason = _reason_for_error(exc)
        state = {
            "permission_denied": SourceFileCaptureState.PERMISSION_DENIED,
            "not_found": SourceFileCaptureState.NOT_FOUND,
        }.get(reason, SourceFileCaptureState.PROVIDER_ERROR)
        return _unavailable_side(
            path,
            reason=reason,
            provider_blob_oid=known_blob_oid,
            provider_blob_source=known_blob_source,
            state=state,
        )
    except Exception:
        return _unavailable_side(
            path,
            reason="provider_error",
            provider_blob_oid=known_blob_oid,
            provider_blob_source=known_blob_source,
            state=SourceFileCaptureState.PROVIDER_ERROR,
        )

    blob_oid = result.provider_blob_oid or known_blob_oid
    blob_source = (
        "github_contents_api"
        if result.provider_blob_oid
        else known_blob_source
    )
    if (
        known_blob_oid
        and result.provider_blob_oid
        and known_blob_oid != result.provider_blob_oid
    ):
        return _unavailable_side(
            path,
            reason="provider_blob_identity_mismatch",
            provider_blob_oid=known_blob_oid,
            provider_blob_source=known_blob_source,
            state=SourceFileCaptureState.PROVIDER_ERROR,
        )
    if result.content is None:
        state = (
            SourceFileCaptureState.LIMIT_EXCEEDED
            if result.capture_state == "limit_exceeded"
            else SourceFileCaptureState.UNAVAILABLE
        )
        return _unavailable_side(
            path,
            reason=result.capture_reason or "provider_content_unavailable",
            provider_blob_oid=blob_oid,
            provider_blob_source=blob_source,
            state=state,
        )
    if len(result.content) > request_limit:
        return _unavailable_side(
            path,
            reason="provider_returned_content_over_limit",
            provider_blob_oid=blob_oid,
            provider_blob_source=blob_source,
            state=SourceFileCaptureState.LIMIT_EXCEEDED,
        )

    budget.remaining -= len(result.content)
    content_sha256 = hashlib.sha256(result.content).hexdigest()
    semantic_value, semantic_state, semantic_reason = _scalar_value(
        result.content,
        limits=limits,
    )
    return SourceFileMutationSide(
        identity_state=(
            SourceFileIdentityState.PRESENT
            if blob_oid
            else SourceFileIdentityState.UNAVAILABLE
        ),
        path=path,
        provider_blob_oid=blob_oid,
        provider_blob_source=blob_source,
        content_sha256=content_sha256,
        size_bytes=(
            result.size_bytes
            if result.size_bytes is not None
            else len(result.content)
        ),
        content_capture_state=SourceFileCaptureState.CAPTURED,
        semantic_value=semantic_value,
        semantic_capture_state=semantic_state,
        semantic_capture_reason=semantic_reason,
    )


def _mutation_id(
    *,
    repository_id: str,
    commit_sha: str,
    parent_shas: list[str],
    change_type: SourceFileChangeType,
    previous_path: str | None,
    current_path: str,
    before: SourceFileMutationSide,
    after: SourceFileMutationSide,
) -> str:
    identity = {
        "provider": "github",
        "repository_id": repository_id,
        "commit_sha": commit_sha,
        "parent_shas": parent_shas,
        "change_type": change_type.value,
        "previous_path": previous_path,
        "current_path": current_path,
        "before_identity_state": before.identity_state.value,
        "before_blob_oid": before.provider_blob_oid,
        "after_identity_state": after.identity_state.value,
        "after_blob_oid": after.provider_blob_oid,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()[:40]
    return f"source-file-mutation:{digest}"


def _required_sides_complete(
    change_type: SourceFileChangeType,
    before: SourceFileMutationSide,
    after: SourceFileMutationSide,
) -> bool:
    expected = {
        SourceFileChangeType.ADDED: (
            SourceFileIdentityState.ABSENT,
            SourceFileIdentityState.PRESENT,
        ),
        SourceFileChangeType.REMOVED: (
            SourceFileIdentityState.PRESENT,
            SourceFileIdentityState.ABSENT,
        ),
        SourceFileChangeType.MODIFIED: (
            SourceFileIdentityState.PRESENT,
            SourceFileIdentityState.PRESENT,
        ),
        SourceFileChangeType.RENAMED: (
            SourceFileIdentityState.PRESENT,
            SourceFileIdentityState.PRESENT,
        ),
    }[change_type]
    return (before.identity_state, after.identity_state) == expected


def _one_mutation(
    provider: GitHubSourceEvidenceProvider,
    *,
    repository: SourceRepositoryIdentity,
    commit: dict[str, Any],
    file: dict[str, Any],
    limits: SourceFileCaptureLimits,
    budget: _ByteBudget,
) -> SourceFileMutationEvidence | None:
    status = str(file.get("status") or "").lower()
    try:
        change_type = SourceFileChangeType(status)
    except ValueError:
        return None
    current_path_value = file.get("filename")
    if not isinstance(current_path_value, str) or not current_path_value:
        return None
    current_path = current_path_value
    previous_path = (
        file.get("previous_filename")
        if isinstance(file.get("previous_filename"), str)
        else None
    )
    commit_sha = str(commit.get("sha") or "")
    raw_parents = commit.get("parents", [])
    if not isinstance(raw_parents, list):
        raw_parents = []
    parent_shas = sorted(
        str(parent.get("sha"))
        for parent in raw_parents
        if isinstance(parent, dict) and parent.get("sha")
    )
    if not parent_shas:
        parent_context_type = SourceFileParentContextType.ROOT
    elif len(parent_shas) == 1:
        parent_context_type = SourceFileParentContextType.SINGLE_PARENT
    else:
        parent_context_type = SourceFileParentContextType.MULTIPLE_PARENTS
    parent_context = SourceFileParentContext(
        context_type=parent_context_type,
        parent_shas=parent_shas,
    )
    provider_blob_oid = (
        str(file.get("sha")) if file.get("sha") else None
    )
    before_path = previous_path or current_path

    if change_type == SourceFileChangeType.ADDED:
        before = _absent_side(before_path)
    elif parent_context_type == SourceFileParentContextType.MULTIPLE_PARENTS:
        before = _ambiguous_side(before_path)
    elif parent_context_type == SourceFileParentContextType.ROOT:
        before = _unavailable_side(before_path, reason="root_commit_has_no_parent")
    else:
        before = _capture_side(
            provider,
            path=before_path,
            ref=parent_shas[0],
            limits=limits,
            budget=budget,
            known_blob_oid=(
                provider_blob_oid
                if change_type == SourceFileChangeType.REMOVED
                else None
            ),
            known_blob_source=(
                "github_commit_files_api"
                if change_type == SourceFileChangeType.REMOVED
                else None
            ),
        )

    if change_type == SourceFileChangeType.REMOVED:
        after = _absent_side(current_path)
    else:
        after = _capture_side(
            provider,
            path=current_path,
            ref=commit_sha,
            limits=limits,
            budget=budget,
            known_blob_oid=provider_blob_oid,
            known_blob_source="github_commit_files_api",
        )

    completeness_reasons: list[str] = []
    if not _required_sides_complete(change_type, before, after):
        completeness_reasons.append("required_provider_identity_unavailable")
    for label, side in (("before", before), ("after", after)):
        if side.identity_state in {
            SourceFileIdentityState.PRESENT,
            SourceFileIdentityState.UNAVAILABLE,
        } and side.content_capture_state != SourceFileCaptureState.CAPTURED:
            completeness_reasons.append(
                f"{label}_content_{side.content_capture_state.value}"
            )
    completeness = (
        SourceFileEvidenceCompleteness.COMPLETE
        if not completeness_reasons
        else SourceFileEvidenceCompleteness.PARTIAL
    )
    references = [
        SourceFileEvidenceReference(
            reference_type="github_repository",
            reference=repository.provider_repository_id,
            source_system="github_rest_api",
        ),
        SourceFileEvidenceReference(
            reference_type="github_commit",
            reference=str(commit.get("url") or commit_sha),
            source_system="github_rest_api",
        ),
    ]
    if isinstance(file.get("blob_url"), str):
        references.append(
            SourceFileEvidenceReference(
                reference_type="github_blob",
                reference=file["blob_url"],
                source_system="github_rest_api",
            )
        )
    mutation_id = _mutation_id(
        repository_id=repository.provider_repository_id,
        commit_sha=commit_sha,
        parent_shas=parent_shas,
        change_type=change_type,
        previous_path=previous_path,
        current_path=current_path,
        before=before,
        after=after,
    )
    return SourceFileMutationEvidence(
        mutation_id=mutation_id,
        provider="github",
        repository=repository,
        commit_sha=commit_sha,
        parent_context=parent_context,
        change_type=change_type,
        provider_status=status,
        current_path=current_path,
        previous_path=previous_path,
        before=before,
        after=after,
        completeness=completeness,
        completeness_reasons=sorted(set(completeness_reasons)),
        source_references=references,
    )


def _push_commit_shas(payload: dict[str, Any]) -> tuple[list[str], int]:
    raw_commits = payload.get("commits", [])
    if not isinstance(raw_commits, list):
        raw_commits = []
    shas = {
        str(commit.get("id"))
        for commit in raw_commits
        if isinstance(commit, dict) and commit.get("id")
    }
    after = payload.get("after")
    if isinstance(after, str) and after and set(after) != {"0"}:
        shas.add(after)
    requested = payload.get("size")
    requested_count = requested if isinstance(requested, int) else len(shas)
    return sorted(shas), max(requested_count, len(shas))


def _push_file_counts(payload: dict[str, Any]) -> dict[str, int]:
    raw_commits = payload.get("commits", [])
    if not isinstance(raw_commits, list):
        return {}
    result: dict[str, int] = {}
    for commit in raw_commits:
        if not isinstance(commit, dict) or not commit.get("id"):
            continue
        paths: set[str] = set()
        has_file_lists = False
        for key in ("added", "modified", "removed"):
            values = commit.get(key)
            if not isinstance(values, list):
                continue
            has_file_lists = True
            paths.update(str(value) for value in values if isinstance(value, str))
        if has_file_lists:
            result[str(commit["id"])] = len(paths)
    return result


def _attach(
    events: list[ChangeEventCreate],
    *,
    capture: SourceFileMutationEnrichment,
    mutations: list[SourceFileMutationEvidence],
) -> list[ChangeEventCreate]:
    mutation_payload = [
        mutation.model_dump(mode="json")
        for mutation in sorted(
            mutations,
            key=lambda value: (
                value.commit_sha,
                value.current_path,
                value.previous_path or "",
                value.change_type.value,
                value.mutation_id,
            ),
        )
    ]
    result: list[ChangeEventCreate] = []
    for event in events:
        metadata = {
            **event.metadata,
            "source_file_mutation_enrichment": capture.model_dump(mode="json"),
            "source_file_mutations": mutation_payload,
        }
        result.append(event.model_copy(update={"metadata": metadata}))
    return result


def unavailable_github_push_events(
    *,
    events: list[ChangeEventCreate],
    payload: dict[str, Any],
    config: dict[str, Any],
    reason: str,
) -> list[ChangeEventCreate]:
    limits = SourceFileCaptureLimits.from_config(config)
    _, requested_count = _push_commit_shas(payload)
    capture = SourceFileMutationEnrichment(
        provider="github",
        completeness=SourceFileEvidenceCompleteness.UNAVAILABLE,
        reasons=[reason],
        requested_commit_count=requested_count,
        limits=limits.model_dict(),
    )
    return _attach(events, capture=capture, mutations=[])


def enrich_github_push_events(
    *,
    events: list[ChangeEventCreate],
    payload: dict[str, Any],
    config: dict[str, Any],
    provider_factory: GitHubSourceEvidenceProviderFactory = (
        github_source_evidence_provider
    ),
) -> list[ChangeEventCreate]:
    """Attach bounded provider-authentic file evidence to a signed push."""
    limits = SourceFileCaptureLimits.from_config(config)
    repository_payload = payload.get("repository")
    repository_payload = (
        repository_payload if isinstance(repository_payload, dict) else {}
    )
    full_name_value = repository_payload.get("full_name")
    repository_id_value = repository_payload.get("id")
    full_name = str(full_name_value) if full_name_value else ""
    provider_repository_id = (
        str(repository_id_value) if repository_id_value is not None else ""
    )
    commit_shas, requested_count = _push_commit_shas(payload)

    def unavailable(reason: str) -> list[ChangeEventCreate]:
        return unavailable_github_push_events(
            events=events,
            payload=payload,
            config=config,
            reason=reason,
        )

    if not full_name:
        return unavailable("missing_repository_full_name")
    if not provider_repository_id:
        return unavailable("missing_repository_stable_id")
    if not commit_shas:
        return unavailable("missing_commit_identity")

    try:
        provider = provider_factory(full_name, config)
        provider_repository = provider.get_repository()
    except GitHubConnectorError as exc:
        return unavailable(_reason_for_error(exc))
    except Exception:
        return unavailable("provider_error")

    if not isinstance(provider_repository, dict):
        return unavailable("provider_repository_response_invalid")
    actual_id = provider_repository.get("id")
    actual_full_name = provider_repository.get("full_name")
    if str(actual_id) != provider_repository_id or actual_full_name != full_name:
        return unavailable("provider_repository_identity_mismatch")

    repository = SourceRepositoryIdentity(
        provider="github",
        provider_repository_id=provider_repository_id,
        full_name=full_name,
    )
    reasons: list[str] = []
    raw_push_commits = payload.get("commits", [])
    if not isinstance(raw_push_commits, list):
        raw_push_commits = []
    listed_commit_count = len(
        [item for item in raw_push_commits if isinstance(item, dict)]
    )
    if requested_count > listed_commit_count and requested_count > 1:
        reasons.append("provider_push_commit_list_truncated")
    if len(commit_shas) > limits.maximum_commits:
        reasons.append("commit_limit_exceeded")
        commit_shas = commit_shas[: limits.maximum_commits]

    budget = _ByteBudget(remaining=limits.maximum_total_bytes)
    push_file_counts = _push_file_counts(payload)
    mutations: list[SourceFileMutationEvidence] = []
    enriched_commits = 0
    remaining_files = limits.maximum_files
    commit_references: list[SourceFileEvidenceReference] = []
    for requested_sha in commit_shas:
        try:
            commit = provider.get_commit(requested_sha)
        except GitHubConnectorError as exc:
            reasons.append(f"commit_{_reason_for_error(exc)}")
            continue
        except Exception:
            reasons.append("commit_provider_error")
            continue
        if not isinstance(commit, dict):
            reasons.append("provider_commit_response_invalid")
            continue
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str) or commit_sha != requested_sha:
            reasons.append("provider_commit_identity_mismatch")
            continue
        enriched_commits += 1
        commit_references.append(
            SourceFileEvidenceReference(
                reference_type="github_commit",
                reference=str(commit.get("url") or commit_sha),
                source_system="github_rest_api",
            )
        )
        files = commit.get("files")
        if not isinstance(files, list):
            reasons.append("commit_file_list_unavailable")
            continue
        expected_file_count = push_file_counts.get(commit_sha)
        if expected_file_count is not None and expected_file_count > len(files):
            reasons.append("provider_commit_file_list_incomplete")
        provider_files = sorted(
            (item for item in files if isinstance(item, dict)),
            key=lambda item: (
                str(item.get("filename") or ""),
                str(item.get("previous_filename") or ""),
                str(item.get("status") or ""),
                str(item.get("sha") or ""),
            ),
        )
        if len(provider_files) >= remaining_files:
            reasons.append("file_limit_exceeded")
        if len(provider_files) > remaining_files:
            provider_files = provider_files[:remaining_files]
        for file in provider_files:
            mutation = _one_mutation(
                provider,
                repository=repository,
                commit=commit,
                file=file,
                limits=limits,
                budget=budget,
            )
            if mutation is None:
                reasons.append("unsupported_or_invalid_file_mutation")
                continue
            mutations.append(mutation)
        remaining_files -= len(provider_files)
        if remaining_files <= 0:
            if requested_sha != commit_shas[-1]:
                reasons.append("file_limit_exceeded")
            break

    reasons = sorted(set(reasons))
    if not mutations and enriched_commits == 0:
        completeness = SourceFileEvidenceCompleteness.UNAVAILABLE
    elif reasons or any(
        mutation.completeness != SourceFileEvidenceCompleteness.COMPLETE
        for mutation in mutations
    ):
        completeness = SourceFileEvidenceCompleteness.PARTIAL
    else:
        completeness = SourceFileEvidenceCompleteness.COMPLETE
    capture = SourceFileMutationEnrichment(
        provider="github",
        repository=repository,
        completeness=completeness,
        reasons=reasons,
        requested_commit_count=requested_count,
        enriched_commit_count=enriched_commits,
        mutation_count=len(mutations),
        limits=limits.model_dict(),
        source_references=[
            SourceFileEvidenceReference(
                reference_type="github_repository",
                reference=provider_repository_id,
                source_system="github_rest_api",
            ),
            *sorted(commit_references, key=lambda item: item.reference),
        ],
    )
    return _attach(events, capture=capture, mutations=mutations)
