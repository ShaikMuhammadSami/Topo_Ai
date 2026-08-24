from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from app.models.build_artifacts import (
    BuildArtifactEvidence,
    BuildArtifactEvidenceCompleteness,
    BuildArtifactEvidenceParseResult,
    BuildArtifactEvidenceType,
    BuildArtifactType,
)
from app.models.temporal import TimeOrigin, TimeQuality
from app.services.temporal_semantics import (
    build_temporal_metadata,
    parse_utc,
    try_parse_utc,
)


MAX_BUILD_RECORD_BYTES = 32 * 1024 * 1024
MAX_BUILD_RECORD_MEMBER_BYTES = 16 * 1024 * 1024
MAX_BUILD_RECORD_TOTAL_BYTES = 64 * 1024 * 1024
MAX_BUILD_RECORD_MEMBERS = 1000

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_BUILDER = re.compile(
    r"^https://github\.com/([^/]+/[^/]+)/actions/runs/([1-9][0-9]*)/"
    r"attempts/([1-9][0-9]*)$",
    re.IGNORECASE,
)


class BuildRecordRejected(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def _reject(code: str, detail: str) -> BuildRecordRejected:
    return BuildRecordRejected(code, detail)


def _safe_path(value: str) -> bool:
    path = PurePosixPath(value.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts


def _unwrap_artifact(payload: bytes) -> bytes:
    if len(payload) > MAX_BUILD_RECORD_BYTES:
        raise _reject("BUILD_RECORD_TOO_LARGE", "Provider artifact is too large.")
    if not payload.startswith(b"PK\x03\x04"):
        return payload
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            candidates = [
                item for item in files if item.filename.casefold().endswith(".dockerbuild")
            ]
            selected = candidates if candidates else files
            if len(selected) != 1 or not _safe_path(selected[0].filename):
                raise _reject(
                    "BUILD_RECORD_ARCHIVE_AMBIGUOUS",
                    "Provider artifact does not contain one safe Docker build record.",
                )
            if selected[0].file_size > MAX_BUILD_RECORD_BYTES:
                raise _reject("BUILD_RECORD_TOO_LARGE", "Docker build record is too large.")
            return archive.read(selected[0])
    except zipfile.BadZipFile as exc:
        raise _reject("BUILD_RECORD_ARCHIVE_INVALID", "Provider artifact ZIP is invalid.") from exc


def _read_oci_layout(payload: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as archive:
            members = archive.getmembers()
            if len(members) > MAX_BUILD_RECORD_MEMBERS:
                raise _reject("BUILD_RECORD_TOO_MANY_MEMBERS", "Build record has too many members.")
            total = 0
            for member in members:
                if not _safe_path(member.name):
                    raise _reject("BUILD_RECORD_PATH_UNSAFE", "Build record contains an unsafe path.")
                if not member.isfile():
                    continue
                if member.size > MAX_BUILD_RECORD_MEMBER_BYTES:
                    raise _reject("BUILD_RECORD_MEMBER_TOO_LARGE", "Build record member is too large.")
                total += member.size
                if total > MAX_BUILD_RECORD_TOTAL_BYTES:
                    raise _reject("BUILD_RECORD_EXPANSION_TOO_LARGE", "Build record expands too large.")
                stream = archive.extractfile(member)
                if stream is None:
                    raise _reject("BUILD_RECORD_MEMBER_UNREADABLE", "Build record member cannot be read.")
                normalized_name = member.name.replace("\\", "/")
                if normalized_name in result:
                    raise _reject(
                        "BUILD_RECORD_MEMBER_DUPLICATE",
                        "Build record contains a duplicate member path.",
                    )
                result[normalized_name] = stream.read()
    except (tarfile.TarError, OSError) as exc:
        raise _reject("BUILD_RECORD_ARCHIVE_INVALID", "Provider build record is not a valid OCI archive.") from exc
    return result


def _json(value: bytes, *, code: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _reject(code, "Provider build record JSON is invalid.") from exc
    if not isinstance(parsed, dict):
        raise _reject(code, "Provider build record JSON must be an object.")
    return parsed


def _blob(files: dict[str, bytes], digest: str) -> bytes:
    if not _DIGEST.fullmatch(digest):
        raise _reject("BUILD_RECORD_DIGEST_INVALID", "Build record descriptor digest is invalid.")
    algorithm, value = digest.split(":", 1)
    path = f"blobs/{algorithm}/{value}"
    payload = files.get(path)
    if payload is None:
        raise _reject("BUILD_RECORD_BLOB_MISSING", "Build record descriptor blob is missing.")
    if hashlib.sha256(payload).hexdigest() != value:
        raise _reject("BUILD_RECORD_BLOB_MISMATCH", "Build record blob digest does not match content.")
    return payload


def _artifact_digest(artifact: dict[str, Any], payload: bytes) -> str:
    expected = str(artifact.get("digest") or "").lower()
    if not _DIGEST.fullmatch(expected):
        raise _reject("PROVIDER_ARTIFACT_DIGEST_MISSING", "GitHub artifact digest is unavailable.")
    actual = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if actual != expected:
        raise _reject("PROVIDER_ARTIFACT_DIGEST_MISMATCH", "GitHub artifact digest does not match content.")
    return actual


def _normalized_image_repository(reference: str) -> str | None:
    value = reference.strip().lower()
    if not value:
        return None
    value = value.split("@", 1)[0]
    slash = value.rfind("/")
    colon = value.rfind(":")
    if colon > slash:
        value = value[:colon]
    return value if "/" in value else None


def _exported_image(history: dict[str, Any]) -> tuple[str, str | None]:
    repositories: set[str] = set()
    references: set[str] = set()
    for exporter in history.get("Exporters") or []:
        if not isinstance(exporter, dict) or exporter.get("Type") != "image":
            continue
        attrs = exporter.get("Attrs") or {}
        if not isinstance(attrs, dict) or str(attrs.get("push", "")).casefold() != "true":
            continue
        for raw in str(attrs.get("name") or "").split(","):
            reference = raw.strip()
            repository = _normalized_image_repository(reference)
            if repository:
                references.add(reference)
                repositories.add(repository)
    if len(repositories) != 1:
        raise _reject(
            "IMAGE_REPOSITORY_AMBIGUOUS",
            "Build record does not identify exactly one pushed image repository.",
        )
    reference = sorted(references)[0] if len(references) == 1 else None
    return next(iter(repositories)), reference


def _result_digests(history: dict[str, Any], files: dict[str, bytes]) -> list[str]:
    result = history.get("Result")
    if not isinstance(result, dict):
        raise _reject("BUILD_RESULT_MISSING", "Build record has no structured result.")
    descriptors: list[dict[str, Any]] = []
    deprecated = result.get("ResultDeprecated")
    if isinstance(deprecated, dict):
        descriptors.append(deprecated)
    values = result.get("Results")
    if isinstance(values, dict):
        descriptors.extend(item for item in values.values() if isinstance(item, dict))
    digests: set[str] = set()
    for descriptor in descriptors:
        digest = str(descriptor.get("digest") or "").lower()
        if not _DIGEST.fullmatch(digest):
            raise _reject("IMAGE_DIGEST_INVALID", "Build result has a malformed image digest.")
        _blob(files, digest)
        digests.add(digest)
    if not digests:
        raise _reject("IMAGE_DIGEST_MISSING", "Build result has no immutable image digest.")
    return sorted(digests)


def _provider_attestation(
    history: dict[str, Any],
    files: dict[str, bytes],
) -> tuple[dict[str, Any], str]:
    result = history.get("Result") or {}
    for descriptor in result.get("Attestations") or []:
        if not isinstance(descriptor, dict):
            continue
        annotations = descriptor.get("annotations") or {}
        if (
            descriptor.get("media_type") != "application/vnd.in-toto+json"
            or annotations.get("in-toto.io/predicate-type")
            != "https://slsa.dev/provenance/v1"
        ):
            continue
        digest = str(descriptor.get("digest") or "").lower()
        predicate = _json(_blob(files, digest), code="BUILD_ATTESTATION_INVALID")
        return predicate, digest
    raise _reject(
        "BUILD_ATTESTATION_MISSING",
        "Build record has no structured SLSA provenance predicate.",
    )


def _validate_provider_identity(
    *,
    artifact: dict[str, Any],
    repository: dict[str, Any],
    workflow_run: dict[str, Any],
    predicate: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    repository_id = str(repository.get("id") or "")
    repository_name = str(repository.get("full_name") or "")
    run_id = str(workflow_run.get("id") or "")
    run_attempt = workflow_run.get("run_attempt")
    commit_sha = str(workflow_run.get("head_sha") or "").lower()
    if not repository_id or not repository_name or not run_id:
        raise _reject("PROVIDER_IDENTITY_MISSING", "GitHub provider identity is incomplete.")
    if not isinstance(run_attempt, int) or run_attempt < 1:
        raise _reject("RUN_ATTEMPT_MISSING", "GitHub workflow run attempt is unavailable.")
    if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
        raise _reject("COMMIT_SHA_INVALID", "GitHub workflow run commit SHA is invalid.")
    if workflow_run.get("conclusion") != "success":
        raise _reject("RUN_NOT_SUCCESSFUL", "GitHub workflow run did not complete successfully.")

    artifact_run = artifact.get("workflow_run") or {}
    if (
        str(artifact_run.get("id") or "") != run_id
        or str(artifact_run.get("repository_id") or "") != repository_id
        or str(artifact_run.get("head_sha") or "").lower() != commit_sha
    ):
        raise _reject("ARTIFACT_RUN_SCOPE_MISMATCH", "GitHub artifact scope does not match the run.")

    internal = (predicate.get("buildDefinition") or {}).get("internalParameters")
    if not isinstance(internal, dict):
        raise _reject("BUILD_PROVIDER_METADATA_MISSING", "Build provider metadata is missing.")
    expected = {
        "github_repository_id": repository_id,
        "github_repository": repository_name,
        "github_run_id": run_id,
        "github_run_attempt": str(run_attempt),
    }
    for key, value in expected.items():
        actual = str(internal.get(key) or "")
        matches = actual.casefold() == value.casefold() if key == "github_repository" else actual == value
        if not matches:
            code = "RUN_ATTEMPT_MISMATCH" if key == "github_run_attempt" else "BUILD_PROVIDER_IDENTITY_MISMATCH"
            raise _reject(code, f"Structured build provider field {key} does not match GitHub.")

    builder_id = str(
        (((predicate.get("runDetails") or {}).get("builder") or {}).get("id"))
        or ""
    )
    match = _BUILDER.fullmatch(builder_id)
    if not match:
        raise _reject("PROVIDER_BUILDER_ID_INVALID", "Build provider builder ID is invalid.")
    if (
        match.group(1).casefold() != repository_name.casefold()
        or match.group(2) != run_id
        or int(match.group(3)) != run_attempt
    ):
        raise _reject("RUN_ATTEMPT_MISMATCH", "Build provider builder ID does not match run attempt.")
    return internal, builder_id


def _evidence_id(
    *, repository_id: str, run_id: str, run_attempt: int, image_digest: str, artifact_id: str
) -> str:
    payload = "|".join(
        ("github_actions", repository_id, run_id, str(run_attempt), image_digest, artifact_id)
    )
    return "build-artifact-evidence:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]


def parse_github_actions_docker_build_record(
    *,
    artifact: dict[str, Any],
    artifact_payload: bytes,
    repository: dict[str, Any],
    workflow_run: dict[str, Any],
    observed_at: datetime,
) -> BuildArtifactEvidenceParseResult:
    artifact_id = str(artifact.get("id") or "unknown")
    try:
        if not str(artifact.get("name") or "").casefold().endswith(".dockerbuild"):
            raise _reject("UNSUPPORTED_PROVIDER_ARTIFACT", "Artifact is not a Docker build record.")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise _reject("OBSERVED_TIME_INVALID", "Observation time requires a timezone.")
        evidence_digest = _artifact_digest(artifact, artifact_payload)
        files = _read_oci_layout(_unwrap_artifact(artifact_payload))
        layout = _json(files.get("oci-layout", b""), code="OCI_LAYOUT_INVALID")
        if layout.get("imageLayoutVersion") != "1.0.0":
            raise _reject("OCI_LAYOUT_UNSUPPORTED", "Build record OCI layout is unsupported.")
        index = _json(files.get("index.json", b""), code="OCI_INDEX_INVALID")
        if index.get("schemaVersion") != 2:
            raise _reject("OCI_INDEX_UNSUPPORTED", "Build record OCI index is unsupported.")

        accepted: list[BuildArtifactEvidence] = []
        for manifest_descriptor in index.get("manifests") or []:
            if not isinstance(manifest_descriptor, dict):
                continue
            manifest_digest = str(manifest_descriptor.get("digest") or "").lower()
            manifest = _json(_blob(files, manifest_digest), code="BUILD_RECORD_MANIFEST_INVALID")
            config = manifest.get("config") or {}
            if config.get("mediaType") != "application/vnd.buildkit.historyrecord.v0":
                continue
            history_digest = str(config.get("digest") or "").lower()
            history = _json(_blob(files, history_digest), code="BUILD_HISTORY_INVALID")
            predicate, _attestation_digest = _provider_attestation(history, files)
            internal, builder_id = _validate_provider_identity(
                artifact=artifact,
                repository=repository,
                workflow_run=workflow_run,
                predicate=predicate,
            )
            image_repository, image_reference = _exported_image(history)
            image_digests = _result_digests(history, files)
            run_metadata = (predicate.get("runDetails") or {}).get("metadata") or {}
            build_started = try_parse_utc(run_metadata.get("startedOn"))
            build_finished = try_parse_utc(run_metadata.get("finishedOn"))
            run_updated = try_parse_utc(workflow_run.get("updated_at"))
            if run_updated is None:
                raise _reject("RUN_UPDATED_TIME_MISSING", "GitHub run update time is unavailable.")
            source_event_at = build_finished or run_updated
            temporal = build_temporal_metadata(
                source_event_at=source_event_at,
                observed_at=observed_at,
                recorded_at=observed_at,
                source_time_trusted=True,
                source_field=(
                    "docker_build_record.slsa.runDetails.metadata.finishedOn"
                    if build_finished
                    else "github_workflow_run.updated_at"
                ),
                source_origin=TimeOrigin.SOURCE_REPORTED,
                source_quality=TimeQuality.EXACT,
            )
            artifact_reference = str(artifact.get("url") or "")
            parsed_url = urlparse(artifact_reference)
            if parsed_url.scheme != "https" or parsed_url.netloc.casefold() != "api.github.com":
                raise _reject("PROVIDER_EVIDENCE_REFERENCE_INVALID", "GitHub artifact reference is invalid.")
            for image_digest in image_digests:
                accepted.append(
                    BuildArtifactEvidence(
                        evidence_id=_evidence_id(
                            repository_id=str(repository["id"]),
                            run_id=str(workflow_run["id"]),
                            run_attempt=int(workflow_run["run_attempt"]),
                            image_digest=image_digest,
                            artifact_id=artifact_id,
                        ),
                        provider="github_actions",
                        repository_id=str(repository["id"]),
                        repository=str(repository["full_name"]),
                        workflow_id=(
                            str(workflow_run["workflow_id"])
                            if workflow_run.get("workflow_id") is not None
                            else None
                        ),
                        workflow_ref=(
                            str(internal["github_workflow_ref"])
                            if internal.get("github_workflow_ref")
                            else None
                        ),
                        run_id=str(workflow_run["id"]),
                        run_attempt=int(workflow_run["run_attempt"]),
                        commit_sha=str(workflow_run["head_sha"]).lower(),
                        artifact_type=BuildArtifactType.CONTAINER_IMAGE,
                        image_repository=image_repository,
                        image_reference=image_reference,
                        image_digest=image_digest,
                        immutable_image_ref=f"{image_repository}@{image_digest}",
                        provider_evidence_type=(
                            BuildArtifactEvidenceType.GITHUB_ACTIONS_DOCKER_BUILD_RECORD
                        ),
                        provider_evidence_id=artifact_id,
                        provider_evidence_reference=artifact_reference,
                        provider_evidence_digest=evidence_digest,
                        provider_build_record_digest=history_digest,
                        provider_builder_id=builder_id,
                        provider_build_started_at=build_started,
                        provider_build_finished_at=build_finished,
                        provider_run_updated_at=parse_utc(run_updated),
                        observed_at=parse_utc(observed_at),
                        temporal=temporal,
                        completeness=BuildArtifactEvidenceCompleteness.COMPLETE,
                    )
                )
        if not accepted:
            raise _reject("BUILD_HISTORY_MISSING", "No Docker build history record was found.")
        unique = {item.evidence_id: item for item in accepted}
        return BuildArtifactEvidenceParseResult(
            evidence=[unique[key] for key in sorted(unique)]
        )
    except BuildRecordRejected as exc:
        return BuildArtifactEvidenceParseResult(
            warnings=[f"build_artifact_rejected:{exc.code}:artifact={artifact_id}"]
        )
