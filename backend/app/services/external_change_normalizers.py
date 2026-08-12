from __future__ import annotations

from datetime import (
    datetime,
    timezone,
)
from typing import Any

from app.models.change_events import (
    ChangeEventCreate,
    ChangeEventEntityReference,
    ChangeEventKind,
    ChangeEventSource,
)


def _now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _nested(
    value: Any,
    *keys: str,
) -> Any:
    current = value

    for key in keys:
        if not isinstance(
            current,
            dict,
        ):
            return None

        current = current.get(key)

    return current


def _configured_refs(
    config: dict[str, Any],
) -> list[
    ChangeEventEntityReference
]:
    raw = config.get(
        "entity_refs",
        [],
    )

    if not isinstance(raw, list):
        return []

    result = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        try:
            result.append(
                ChangeEventEntityReference
                .model_validate(item)
            )

        except Exception:
            continue

    return result


def normalize_github(
    *,
    event_type: str,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> list[ChangeEventCreate]:
    repository = (
        _nested(
            payload,
            "repository",
            "full_name",
        )
        or _nested(
            payload,
            "repository",
            "name",
        )
    )

    actor = (
        _nested(
            payload,
            "sender",
            "login",
        )
        or _nested(
            payload,
            "pusher",
            "name",
        )
    )

    refs = _configured_refs(
        config
    )

    base = {
        "environment":
            config.get(
                "environment"
            ),
        "cluster_name":
            config.get(
                "cluster_name"
            ),
        "namespace":
            config.get(
                "namespace"
            ),
    }

    if event_type == "push":
        head = (
            payload.get(
                "head_commit"
            )
            or {}
        )

        commit_sha = (
            payload.get("after")
            or head.get("id")
        )

        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITHUB
                ),
                kind=(
                    ChangeEventKind.CODE
                ),
                external_id=(
                    f"github:{repository}:"
                    f"{commit_sha}"
                ),
                title=(
                    head.get("message")
                    or (
                        "GitHub push "
                        f"{payload.get('ref')}"
                    )
                ),
                summary=head.get(
                    "message"
                ),
                actor=actor,
                occurred_at=(
                    head.get(
                        "timestamp"
                    )
                    or _now()
                ),
                repository=repository,
                commit_sha=commit_sha,
                entity_refs=refs,
                metadata={
                    "ref":
                        payload.get("ref"),
                    "before":
                        payload.get(
                            "before"
                        ),
                    "after":
                        payload.get(
                            "after"
                        ),
                    "commit_count":
                        len(
                            payload.get(
                                "commits",
                                [],
                            )
                        ),
                },
                **base,
            )
        ]

    if event_type in {
        "workflow_run",
        "workflow_job",
    }:
        value = (
            payload.get(
                "workflow_run"
            )
            or payload.get(
                "workflow_job"
            )
            or {}
        )

        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITHUB_ACTIONS
                ),
                kind=(
                    ChangeEventKind
                    .PIPELINE
                ),
                external_id=(
                    "github-actions:"
                    f"{value.get('id')}:"
                    f"{value.get('status')}:"
                    f"{value.get('conclusion')}"
                ),
                title=(
                    value.get("name")
                    or "GitHub Actions run"
                ),
                actor=actor,
                occurred_at=(
                    value.get(
                        "updated_at"
                    )
                    or value.get(
                        "started_at"
                    )
                    or _now()
                ),
                repository=repository,
                commit_sha=(
                    value.get(
                        "head_sha"
                    )
                ),
                pipeline_name=(
                    value.get("name")
                ),
                status=str(
                    value.get(
                        "conclusion"
                    )
                    or value.get(
                        "status"
                    )
                    or "observed"
                ),
                entity_refs=refs,
                metadata={
                    "run_number":
                        value.get(
                            "run_number"
                        ),
                    "html_url":
                        value.get(
                            "html_url"
                        ),
                },
                **base,
            )
        ]

    if event_type in {
        "deployment",
        "deployment_status",
    }:
        deployment = (
            payload.get(
                "deployment"
            )
            or {}
        )

        deployment_status = (
            payload.get(
                "deployment_status"
            )
            or {}
        )

        deployment_id = (
            deployment.get("id")
        )

        status_id = (
            deployment_status.get(
                "id"
            )
        )

        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITHUB_ACTIONS
                ),
                kind=(
                    ChangeEventKind
                    .DEPLOYMENT
                ),
                external_id=(
                    "github-deployment:"
                    f"{deployment_id}:"
                    f"{status_id or ''}:"
                    f"{deployment_status.get('state') or ''}"
                ),
                title=(
                    "GitHub deployment "
                    f"{deployment.get('ref')}"
                ),
                actor=actor,
                occurred_at=(
                    deployment_status.get(
                        "updated_at"
                    )
                    or deployment.get(
                        "updated_at"
                    )
                    or _now()
                ),
                environment=(
                    deployment.get(
                        "environment"
                    )
                    or base[
                        "environment"
                    ]
                ),
                cluster_name=(
                    base[
                        "cluster_name"
                    ]
                ),
                namespace=(
                    base[
                        "namespace"
                    ]
                ),
                repository=repository,
                commit_sha=(
                    deployment.get(
                        "sha"
                    )
                ),
                release_version=(
                    deployment.get(
                        "ref"
                    )
                ),
                status=str(
                    deployment_status.get(
                        "state"
                    )
                    or "observed"
                ),
                entity_refs=refs,
            )
        ]

    return []


def normalize_gitlab(
    *,
    event_type: str,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> list[ChangeEventCreate]:
    object_kind = str(
        payload.get(
            "object_kind"
        )
        or event_type
        or ""
    ).lower()

    repository = _nested(
        payload,
        "project",
        "path_with_namespace",
    )

    actor = (
        payload.get(
            "user_username"
        )
        or _nested(
            payload,
            "user",
            "username",
        )
    )

    refs = _configured_refs(
        config
    )

    base = {
        "environment":
            config.get(
                "environment"
            ),
        "cluster_name":
            config.get(
                "cluster_name"
            ),
        "namespace":
            config.get(
                "namespace"
            ),
    }

    if "push" in object_kind:
        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITLAB
                ),
                kind=(
                    ChangeEventKind.CODE
                ),
                external_id=(
                    f"gitlab:{repository}:"
                    f"{payload.get('after')}"
                ),
                title=(
                    "GitLab push "
                    f"{payload.get('ref')}"
                ),
                actor=actor,
                occurred_at=_now(),
                repository=repository,
                commit_sha=(
                    payload.get("after")
                ),
                entity_refs=refs,
                metadata={
                    "ref":
                        payload.get("ref"),
                    "before":
                        payload.get(
                            "before"
                        ),
                },
                **base,
            )
        ]

    if "pipeline" in object_kind:
        attrs = (
            payload.get(
                "object_attributes"
            )
            or {}
        )

        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITLAB
                ),
                kind=(
                    ChangeEventKind
                    .PIPELINE
                ),
                external_id=(
                    "gitlab-pipeline:"
                    f"{attrs.get('id')}:"
                    f"{attrs.get('status')}"
                ),
                title=(
                    "GitLab pipeline "
                    f"{attrs.get('id')}"
                ),
                actor=actor,
                occurred_at=(
                    attrs.get(
                        "finished_at"
                    )
                    or attrs.get(
                        "created_at"
                    )
                    or _now()
                ),
                repository=repository,
                commit_sha=(
                    attrs.get("sha")
                ),
                status=str(
                    attrs.get(
                        "status"
                    )
                    or "observed"
                ),
                entity_refs=refs,
                **base,
            )
        ]

    if (
        "deployment"
        in object_kind
    ):
        status = (
            payload.get("status")
            or _nested(
                payload,
                "deployment",
                "status",
            )
            or "observed"
        )

        deployment_id = (
            _nested(
                payload,
                "deployment",
                "id",
            )
            or payload.get("id")
        )

        environment = (
            _nested(
                payload,
                "environment",
                "name",
            )
            or base[
                "environment"
            ]
        )

        return [
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .GITLAB
                ),
                kind=(
                    ChangeEventKind
                    .DEPLOYMENT
                ),
                external_id=(
                    "gitlab-deployment:"
                    f"{deployment_id}:"
                    f"{status}"
                ),
                title=(
                    "GitLab deployment "
                    f"{environment}"
                ),
                actor=actor,
                occurred_at=_now(),
                environment=environment,
                cluster_name=(
                    base[
                        "cluster_name"
                    ]
                ),
                namespace=(
                    base[
                        "namespace"
                    ]
                ),
                repository=repository,
                status=str(status),
                entity_refs=refs,
            )
        ]

    return []


def normalize_jenkins(
    *,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> list[ChangeEventCreate]:
    event_type = str(
        payload.get(
            "event_type",
            "build",
        )
    ).lower()

    kind = (
        ChangeEventKind.DEPLOYMENT
        if event_type in {
            "deployment",
            "release",
        }
        else ChangeEventKind.PIPELINE
    )

    job_name = str(
        payload.get(
            "job_name",
            "jenkins-job",
        )
    )

    build_number = payload.get(
        "build_number"
    )

    refs = []

    for item in payload.get(
        "entity_refs",
        [],
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        refs.append(
            ChangeEventEntityReference
            .model_validate(item)
        )

    return [
        ChangeEventCreate(
            source=(
                ChangeEventSource.JENKINS
            ),
            kind=kind,
            external_id=(
                "jenkins:"
                f"{job_name}:"
                f"{build_number}:"
                f"{payload.get('status')}"
            ),
            title=(
                payload.get("title")
                or (
                    f"Jenkins {job_name} "
                    f"#{build_number}"
                )
            ),
            actor=payload.get("actor"),
            occurred_at=(
                payload.get(
                    "occurred_at"
                )
                or _now()
            ),
            environment=(
                payload.get(
                    "environment"
                )
                or config.get(
                    "environment"
                )
            ),
            cluster_name=(
                payload.get(
                    "cluster_name"
                )
                or config.get(
                    "cluster_name"
                )
            ),
            namespace=(
                payload.get(
                    "namespace"
                )
                or config.get(
                    "namespace"
                )
            ),
            repository=(
                payload.get(
                    "repository"
                )
            ),
            commit_sha=(
                payload.get(
                    "commit_sha"
                )
            ),
            pipeline_name=job_name,
            release_version=(
                payload.get(
                    "release_version"
                )
            ),
            status=str(
                payload.get(
                    "status",
                    "observed",
                )
            ),
            entity_refs=refs,
            metadata={
                "build_number":
                    build_number,
                "build_url":
                    payload.get(
                        "build_url"
                    ),
            },
        )
    ]


def normalize_azure_devops(
    *,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> list[ChangeEventCreate]:
    event_type = str(
        payload.get(
            "eventType",
            "unknown",
        )
    )

    resource = (
        payload.get("resource")
        or {}
    )

    lower = event_type.lower()

    if event_type == "git.push":
        kind = ChangeEventKind.CODE

    elif "build" in lower:
        kind = (
            ChangeEventKind.PIPELINE
        )

    elif (
        "release" in lower
        or "deployment" in lower
    ):
        kind = (
            ChangeEventKind.DEPLOYMENT
        )

    elif "pullrequest" in lower:
        kind = (
            ChangeEventKind
            .PULL_REQUEST
        )

    else:
        kind = (
            ChangeEventKind
            .CONFIGURATION
        )

    repository = (
        _nested(
            resource,
            "repository",
            "name",
        )
        or _nested(
            resource,
            "repository",
            "id",
        )
    )

    commit_sha = (
        resource.get(
            "sourceVersion"
        )
        or _nested(
            resource,
            "commits",
            "0",
        )
    )

    return [
        ChangeEventCreate(
            source=(
                ChangeEventSource
                .AZURE_DEVOPS
            ),
            kind=kind,
            external_id=(
                "azure-devops:"
                f"{payload.get('id')}:"
                f"{event_type}"
            ),
            title=(
                _nested(
                    payload,
                    "message",
                    "text",
                )
                or (
                    "Azure DevOps "
                    f"{event_type}"
                )
            ),
            actor=(
                _nested(
                    resource,
                    "requestedFor",
                    "displayName",
                )
            ),
            occurred_at=(
                payload.get(
                    "createdDate"
                )
                or resource.get(
                    "finishTime"
                )
                or _now()
            ),
            environment=(
                config.get(
                    "environment"
                )
            ),
            cluster_name=(
                config.get(
                    "cluster_name"
                )
            ),
            namespace=(
                config.get(
                    "namespace"
                )
            ),
            repository=repository,
            commit_sha=commit_sha,
            pipeline_name=(
                _nested(
                    resource,
                    "definition",
                    "name",
                )
            ),
            status=str(
                resource.get(
                    "result"
                )
                or resource.get(
                    "status"
                )
                or "observed"
            ),
            entity_refs=(
                _configured_refs(
                    config
                )
            ),
            metadata={
                "event_type":
                    event_type,
                "resource_id":
                    resource.get("id"),
            },
        )
    ]


def normalize_terraform_cloud(
    *,
    payload: dict[str, Any],
    config: dict[str, Any],
) -> list[ChangeEventCreate]:
    run_id = payload.get(
        "run_id"
    )

    workspace = payload.get(
        "workspace_name"
    )

    organization = payload.get(
        "organization_name"
    )

    notifications = payload.get(
        "notifications"
    )

    if not isinstance(
        notifications,
        list,
    ):
        notifications = []

    # HCP Terraform verification request.
    if not notifications:
        return []

    result = []

    for index, notification in enumerate(
        notifications
    ):
        if not isinstance(
            notification,
            dict,
        ):
            continue

        trigger = str(
            notification.get(
                "trigger",
                "unknown",
            )
        )

        status = str(
            notification.get(
                "run_status"
            )
            or trigger
        )

        # Applying/completed represent
        # actual infrastructure change.
        kind = (
            ChangeEventKind
            .INFRASTRUCTURE
        )

        result.append(
            ChangeEventCreate(
                source=(
                    ChangeEventSource
                    .TERRAFORM
                ),
                kind=kind,
                external_id=(
                    "terraform:"
                    f"{workspace}:"
                    f"{run_id}:"
                    f"{trigger}:"
                    f"{index}"
                ),
                title=(
                    notification.get(
                        "message"
                    )
                    or (
                        "Terraform "
                        f"{trigger}"
                    )
                ),
                actor=(
                    notification.get(
                        "run_updated_by"
                    )
                    or payload.get(
                        "run_created_by"
                    )
                ),
                occurred_at=(
                    notification.get(
                        "run_updated_at"
                    )
                    or payload.get(
                        "run_created_at"
                    )
                    or _now()
                ),
                environment=(
                    config.get(
                        "environment"
                    )
                ),
                provider=(
                    config.get(
                        "provider"
                    )
                ),
                terraform_workspace=(
                    workspace
                ),
                status=status,
                entity_refs=(
                    _configured_refs(
                        config
                    )
                ),
                metadata={
                    "run_id":
                        run_id,
                    "run_url":
                        payload.get(
                            "run_url"
                        ),
                    "workspace_id":
                        payload.get(
                            "workspace_id"
                        ),
                    "workspace_name":
                        workspace,
                    "organization":
                        organization,
                    "trigger":
                        trigger,
                },
            )
        )

    return result