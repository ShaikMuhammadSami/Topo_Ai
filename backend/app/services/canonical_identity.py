from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from urllib.parse import urlparse

from app.models.canonical_identity import (
    CanonicalEntityIdentity,
    CanonicalIdentityResolution,
    CanonicalIdentityResolutionStatus,
    CanonicalIdentityResolutionStrategy,
)
from app.models.topology import Entity, GraphSnapshot


IDENTITY_VERSION = "v1"
LEGACY_IDENTITY_VERSION = "legacy"


def _digest(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _text(value: object | None) -> str | None:
    if value is None:
        return None

    result = str(value).strip()
    if not result or result.casefold() in {"none", "null"}:
        return None
    return result


def _safe_component(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value).strip())


def _kind_token(kind: str) -> str:
    value = kind.strip()
    if value.casefold().startswith("kubernetes"):
        value = value[len("Kubernetes") :]
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).lower()


def _unique(values: Iterable[str | None], *, excluding: str | None = None) -> list[str]:
    return sorted(
        {
            value
            for value in values
            if value and value != excluding
        }
    )


def canonical_kubernetes_identity(
    *,
    cluster_name: str,
    kind: str,
    name: str,
    namespace: str | None,
    uid: str | None,
) -> CanonicalEntityIdentity:
    """Build the TC-1 Kubernetes identity and safe legacy graph aliases."""

    raw_cluster = str(cluster_name).strip()
    cluster = _safe_component(raw_cluster)
    kind_token = _kind_token(kind)
    object_name = str(name).strip()
    object_namespace = _text(namespace)
    native_uid = _text(uid)

    if native_uid:
        identity = native_uid
        strategy = "kubernetes_uid"
    else:
        identity = _digest(
            "|".join(
                [
                    cluster,
                    kind_token,
                    object_namespace or "",
                    object_name,
                ]
            ),
            24,
        )
        strategy = "kubernetes_scoped_name"

    canonical_id = f"k8s:{cluster}:{kind_token}:{identity}"

    aliases: list[str | None] = []
    if native_uid:
        aliases.append(
            f"k8s:{raw_cluster}:{kind_token}:{native_uid}"
            if raw_cluster != cluster
            else None
        )
    else:
        # Pre-TC-1 direct collector fallback.
        aliases.append(
            f"k8s:{cluster}:{kind_token}:"
            f"{object_namespace or '_cluster'}:{object_name}"
        )

        # Pre-TC-1 agent fallback. This is normally the canonical v1 value,
        # but remains explicit when the raw cluster needed normalization.
        aliases.append(
            f"k8s:{raw_cluster}:{kind_token}:"
            f"{_digest('|'.join([raw_cluster, kind_token, object_namespace or '', object_name]), 24)}"
        )

        # Pre-TC-1 network enricher used namespace and kind in reverse order.
        aliases.append(
            f"k8s:{raw_cluster}:{kind_token}:"
            f"{_digest('|'.join([raw_cluster, object_namespace or '', kind_token, object_name]), 24)}"
        )

        if kind_token == "cluster":
            aliases.append(f"k8s:{cluster}:cluster")

    return CanonicalEntityIdentity(
        canonical_id=canonical_id,
        entity_kind=kind,
        source_system="kubernetes",
        source_native_id=native_uid,
        scope={
            key: value
            for key, value in {
                "cluster": cluster,
                "namespace": object_namespace,
            }.items()
            if value is not None
        },
        aliases=_unique(aliases, excluding=canonical_id),
        identity_version=IDENTITY_VERSION,
        strategy=strategy,
    )


def canonical_aws_identity(
    *,
    account_id: str,
    region: str,
    resource_type: str,
    resource_id: str,
    arn: str | None = None,
) -> CanonicalEntityIdentity:
    native_id = _text(arn) or str(resource_id).strip()
    identity = "|".join(
        ["aws", str(account_id), str(region), str(resource_type), str(resource_id)]
    )
    return CanonicalEntityIdentity(
        canonical_id=f"aws:{_digest(identity, 32)}",
        entity_kind=resource_type,
        source_system="aws",
        source_native_id=native_id,
        scope={"account": str(account_id), "region": str(region)},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="aws_provider_resource_id",
    )


def canonical_azure_identity(
    *,
    subscription_id: str | None,
    resource_type: str,
    resource_id: str,
) -> CanonicalEntityIdentity:
    normalized_id = str(resource_id).strip().rstrip("/").lower()
    return CanonicalEntityIdentity(
        canonical_id=f"azure:{_digest(normalized_id, 32)}",
        entity_kind=resource_type,
        source_system="azure",
        source_native_id=normalized_id,
        scope=(
            {"subscription": str(subscription_id)}
            if subscription_id
            else {}
        ),
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="azure_resource_id",
    )


def canonical_gcp_identity(
    *,
    project_id: str | None,
    resource_type: str,
    resource_id: str,
) -> CanonicalEntityIdentity:
    normalized_id = str(resource_id).strip().rstrip("/").lower()
    return CanonicalEntityIdentity(
        canonical_id=f"gcp:{_digest(normalized_id, 32)}",
        entity_kind=resource_type,
        source_system="gcp",
        source_native_id=normalized_id,
        scope={"project": str(project_id)} if project_id else {},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="gcp_full_resource_id",
    )


def canonical_git_repository_identity(
    *,
    provider: str,
    api_url: str,
    repository_native_id: str | int,
    repository_name: str | None = None,
) -> CanonicalEntityIdentity:
    source = provider.strip().lower()
    host = _safe_component(urlparse(api_url).hostname or source)
    native_id = str(repository_native_id).strip()
    canonical_id = f"{source}:{host}:repository:{native_id}"
    return CanonicalEntityIdentity(
        canonical_id=canonical_id,
        entity_kind="GitRepository",
        source_system=source,
        source_native_id=native_id,
        scope={
            key: value
            for key, value in {
                "host": host,
                "repository": _text(repository_name),
            }.items()
            if value is not None
        },
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="git_provider_repository_id",
    )


def canonical_git_commit_identity(
    *,
    repository_canonical_id: str,
    commit_sha: str,
    source_system: str = "github",
) -> CanonicalEntityIdentity:
    sha = commit_sha.strip().lower()
    return CanonicalEntityIdentity(
        canonical_id=f"{repository_canonical_id}:commit:{sha}",
        entity_kind="GitCommit",
        source_system=source_system,
        source_native_id=sha,
        scope={"repository_id": repository_canonical_id},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="git_repository_scoped_commit",
    )


def canonical_ci_build_identity(
    *,
    provider: str,
    pipeline_scope: str,
    native_build_id: str | int,
) -> CanonicalEntityIdentity:
    source = provider.strip().lower()
    pipeline = pipeline_scope.strip().lower()
    build_id = str(native_build_id).strip()
    canonical_id = (
        f"ci:{_safe_component(source)}:{_digest(pipeline, 20)}:build:{build_id}"
    )
    return CanonicalEntityIdentity(
        canonical_id=canonical_id,
        entity_kind="CICDBuild",
        source_system=source,
        source_native_id=build_id,
        scope={"pipeline": pipeline},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="ci_provider_pipeline_scoped_build",
    )


def canonical_github_workflow_run_identity(
    *, api_url: str, run_id: str | int
) -> CanonicalEntityIdentity:
    host = _safe_component(urlparse(api_url).hostname or "github")
    native_id = str(run_id).strip()
    return CanonicalEntityIdentity(
        canonical_id=f"github:{host}:workflow-run:{native_id}",
        entity_kind="GitHubWorkflowRun",
        source_system="github-actions",
        source_native_id=native_id,
        scope={"host": host},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy="github_provider_workflow_run_id",
    )


def canonical_container_image_identity(
    *, normalized_reference: str, digest: str | None
) -> CanonicalEntityIdentity:
    immutable_digest = _text(digest)
    if immutable_digest:
        immutable_digest = immutable_digest.lower()
        canonical_id = f"artifact:container-image:{immutable_digest}"
        native_id = immutable_digest
        strategy = "container_image_digest"
    else:
        reference = normalized_reference.strip().lower()
        canonical_id = (
            "artifact:container-image:reference:"
            f"{_digest(reference, 24)}"
        )
        native_id = reference
        strategy = "container_image_mutable_reference"

    return CanonicalEntityIdentity(
        canonical_id=canonical_id,
        entity_kind="ContainerImage",
        source_system="container-registry",
        source_native_id=native_id,
        scope={},
        aliases=[],
        identity_version=IDENTITY_VERSION,
        strategy=strategy,
    )


def _snapshot_scope(snapshot: GraphSnapshot, key: str) -> str | None:
    value = snapshot.scope.get(key)
    return _text(value)


def _entity_scope(entity: Entity, snapshot: GraphSnapshot, key: str) -> str | None:
    property_keys = {
        "cluster": ("cluster", "cluster_name"),
        "namespace": ("namespace",),
        "account": ("account_id", "account"),
        "subscription": ("subscription_id", "account_id"),
        "project": ("project_id", "account_id"),
        "region": ("region",),
    }.get(key, (key,))

    for property_key in property_keys:
        value = _text(entity.properties.get(property_key))
        if value:
            return value
    return _snapshot_scope(snapshot, key)


def canonical_identity_for_entity(
    entity: Entity, snapshot: GraphSnapshot
) -> CanonicalEntityIdentity:
    if entity.kind.casefold().startswith("kubernetes"):
        cluster = _entity_scope(entity, snapshot, "cluster")
        if cluster:
            return canonical_kubernetes_identity(
                cluster_name=cluster,
                kind=entity.kind,
                name=entity.name,
                namespace=_entity_scope(entity, snapshot, "namespace"),
                uid=(
                    None
                    if _kind_token(entity.kind) == "cluster"
                    else _text(entity.external_id)
                ),
            )

    if entity.source_system == "aws":
        resource_id = _text(entity.properties.get("resource_id"))
        if resource_id:
            return canonical_aws_identity(
                account_id=_entity_scope(entity, snapshot, "account") or "",
                region=_entity_scope(entity, snapshot, "region") or "global",
                resource_type=_text(entity.properties.get("resource_type")) or entity.kind,
                resource_id=resource_id,
                arn=_text(entity.properties.get("arn")),
            )

    if entity.source_system == "azure":
        resource_id = _text(entity.properties.get("resource_id")) or _text(entity.external_id)
        if resource_id:
            return canonical_azure_identity(
                subscription_id=_entity_scope(entity, snapshot, "subscription"),
                resource_type=_text(entity.properties.get("resource_type")) or entity.kind,
                resource_id=resource_id,
            )

    if entity.source_system == "gcp":
        resource_id = _text(entity.properties.get("resource_id")) or _text(entity.external_id)
        if resource_id:
            return canonical_gcp_identity(
                project_id=_entity_scope(entity, snapshot, "project"),
                resource_type=_text(entity.properties.get("resource_type")) or entity.kind,
                resource_id=resource_id,
            )

    if entity.kind == "ContainerImage":
        return canonical_container_image_identity(
            normalized_reference=(
                _text(entity.properties.get("normalized_reference"))
                or _text(entity.external_id)
                or entity.name
            ),
            digest=_text(entity.properties.get("digest")),
        )

    return CanonicalEntityIdentity(
        canonical_id=entity.id,
        entity_kind=entity.kind,
        source_system=entity.source_system,
        source_native_id=_text(entity.external_id),
        scope={
            key: value
            for key in (
                "cluster",
                "namespace",
                "account",
                "subscription",
                "project",
                "region",
            )
            if (value := _entity_scope(entity, snapshot, key)) is not None
        },
        aliases=sorted(set(entity.aliases)),
        identity_version=entity.identity_version,
        strategy="existing_source_specific_id",
    )


def entity_aliases(entity: Entity, snapshot: GraphSnapshot) -> list[str]:
    identity = canonical_identity_for_entity(entity, snapshot)
    return _unique([*entity.aliases, *identity.aliases, entity.id])


def _kind_matches(entity: Entity, expected_kind: str | None) -> bool:
    if not expected_kind:
        return True
    return _kind_token(entity.kind) == _kind_token(expected_kind)


def _scope_matches(
    entity: Entity,
    snapshot: GraphSnapshot,
    *,
    cluster_name: str | None,
    namespace: str | None,
    account_id: str | None,
    project_id: str | None,
    subscription_id: str | None,
) -> bool:
    expected = {
        "cluster": _text(cluster_name),
        "namespace": _text(namespace),
        "account": _text(account_id),
        "project": _text(project_id),
        "subscription": _text(subscription_id),
    }
    for key, value in expected.items():
        if value is None:
            continue
        actual = _entity_scope(entity, snapshot, key)
        if actual is None or actual.casefold() != value.casefold():
            return False
    return True


def _source_matches(entity: Entity, source_system: str | None) -> bool:
    if not source_system:
        return True
    aliases = {
        "aws_cloudtrail": "aws",
        "azure_activity_log": "azure",
        "gcp_audit_log": "gcp",
        "github_actions": "github-actions",
    }
    expected = aliases.get(source_system.casefold(), source_system.casefold())
    return entity.source_system.casefold() == expected


def _native_values(entity: Entity) -> set[str]:
    values = {
        _text(entity.external_id),
        _text(entity.properties.get("resource_id")),
        _text(entity.properties.get("arn")),
        _text(entity.properties.get("provider_id")),
        _text(entity.properties.get("digest")),
        _text(entity.properties.get("sha")),
        _text(entity.properties.get("run_id")),
    }
    return {value for value in values if value is not None}


def _native_equal(entity: Entity, expected: str, actual: str) -> bool:
    source = entity.source_system.casefold()
    if source in {
        "azure",
        "gcp",
        "github",
        "github-actions",
        "container-registry",
    } or entity.kind in {"GitCommit", "ContainerImage"}:
        return (
            expected.strip().rstrip("/").casefold()
            == actual.strip().rstrip("/").casefold()
        )
    return expected == actual


def _finish_resolution(
    *,
    candidates: list[Entity],
    identities: dict[str, CanonicalEntityIdentity],
    status_strategy: CanonicalIdentityResolutionStrategy,
    input_identifier: str | None,
    matched_value: str | None,
    reason: str,
) -> CanonicalIdentityResolution:
    candidates = sorted(candidates, key=lambda item: item.id)
    if len(candidates) == 1:
        entity = candidates[0]
        identity = identities[entity.id]
        return CanonicalIdentityResolution(
            status=CanonicalIdentityResolutionStatus.RESOLVED,
            strategy=status_strategy,
            input_identifier=input_identifier,
            resolved_entity_id=entity.id,
            resolved_canonical_id=identity.canonical_id,
            matched_value=matched_value,
            identity_version=identity.identity_version,
            candidate_entity_ids=[entity.id],
            reason=reason,
        )
    if len(candidates) > 1:
        return CanonicalIdentityResolution(
            status=CanonicalIdentityResolutionStatus.AMBIGUOUS,
            strategy=status_strategy,
            input_identifier=input_identifier,
            matched_value=matched_value,
            candidate_entity_ids=[item.id for item in candidates],
            reason=(
                f"{reason} More than one scoped entity matched, so no "
                "identity was selected."
            ),
        )
    return CanonicalIdentityResolution(
        status=CanonicalIdentityResolutionStatus.UNRESOLVED,
        strategy=CanonicalIdentityResolutionStrategy.NONE,
        input_identifier=input_identifier,
        reason="No deterministic canonical, native, alias, or scoped match was found.",
    )


def resolve_snapshot_entity_identity(
    snapshot: GraphSnapshot,
    *,
    identifier: str | None = None,
    source_native_id: str | None = None,
    source_system: str | None = None,
    kind: str | None = None,
    name: str | None = None,
    cluster_name: str | None = None,
    namespace: str | None = None,
    account_id: str | None = None,
    project_id: str | None = None,
    subscription_id: str | None = None,
) -> CanonicalIdentityResolution:
    """Resolve an entity without fuzzy matching or first-candidate guessing."""

    input_id = _text(identifier)
    native_id = _text(source_native_id)
    eligible = [
        entity
        for entity in snapshot.entities
        if _source_matches(entity, source_system)
        and _kind_matches(entity, kind)
        and _scope_matches(
            entity,
            snapshot,
            cluster_name=cluster_name,
            namespace=namespace,
            account_id=account_id,
            project_id=project_id,
            subscription_id=subscription_id,
        )
    ]
    identities = {
        entity.id: canonical_identity_for_entity(entity, snapshot)
        for entity in eligible
    }

    if input_id:
        exact = [entity for entity in eligible if entity.id == input_id]
        if exact:
            identity = identities[exact[0].id]
            strategy = (
                CanonicalIdentityResolutionStrategy.CANONICAL_ID
                if exact[0].id == identity.canonical_id
                else CanonicalIdentityResolutionStrategy.SCOPED_ALIAS
            )
            return _finish_resolution(
                candidates=exact,
                identities=identities,
                status_strategy=strategy,
                input_identifier=input_id,
                matched_value=input_id,
                reason="The identifier exactly matched the snapshot entity ID.",
            )

        canonical = [
            entity
            for entity in eligible
            if identities[entity.id].canonical_id == input_id
        ]
        if canonical:
            return _finish_resolution(
                candidates=canonical,
                identities=identities,
                status_strategy=CanonicalIdentityResolutionStrategy.CANONICAL_ID,
                input_identifier=input_id,
                matched_value=input_id,
                reason="The identifier matched the source-specific canonical ID.",
            )

    if native_id:
        native = [
            entity
            for entity in eligible
            if any(
                _native_equal(entity, native_id, value)
                for value in _native_values(entity)
            )
        ]
        if native:
            return _finish_resolution(
                candidates=native,
                identities=identities,
                status_strategy=CanonicalIdentityResolutionStrategy.SOURCE_NATIVE_ID,
                input_identifier=input_id or native_id,
                matched_value=native_id,
                reason="A strong source-native identifier matched.",
            )

    if input_id:
        aliases = [
            entity
            for entity in eligible
            if input_id in entity_aliases(entity, snapshot)
        ]
        if aliases:
            return _finish_resolution(
                candidates=aliases,
                identities=identities,
                status_strategy=CanonicalIdentityResolutionStrategy.SCOPED_ALIAS,
                input_identifier=input_id,
                matched_value=input_id,
                reason="An explicit deterministic legacy alias matched.",
            )

    if name and kind:
        expected_name = name.strip()
        fallback = [
            entity
            for entity in eligible
            if entity.name == expected_name
        ]
        if fallback:
            return _finish_resolution(
                candidates=fallback,
                identities=identities,
                status_strategy=CanonicalIdentityResolutionStrategy.SOURCE_FALLBACK,
                input_identifier=input_id or native_id,
                matched_value=f"{kind}/{expected_name}",
                reason="The exact source-specific scoped kind/name fallback matched.",
            )

    return _finish_resolution(
        candidates=[],
        identities=identities,
        status_strategy=CanonicalIdentityResolutionStrategy.NONE,
        input_identifier=input_id or native_id,
        matched_value=None,
        reason="No deterministic match was found.",
    )


def resolve_equivalent_snapshot_entity(
    source_snapshot: GraphSnapshot,
    target_snapshot: GraphSnapshot,
    source_entity: Entity,
) -> CanonicalIdentityResolution:
    """Resolve one entity across two explicit snapshots.

    This is the identity-version transition primitive used by snapshot
    comparison. It never queries a repository or a latest snapshot. The
    target must be unique at the strongest applicable contract stage.
    """

    source_identity = canonical_identity_for_entity(
        source_entity,
        source_snapshot,
    )
    eligible = [
        entity
        for entity in target_snapshot.entities
        if _source_matches(
            entity,
            source_entity.source_system,
        )
        and _kind_matches(entity, source_entity.kind)
        and _scope_matches(
            entity,
            target_snapshot,
            cluster_name=_entity_scope(
                source_entity,
                source_snapshot,
                "cluster",
            ),
            namespace=_entity_scope(
                source_entity,
                source_snapshot,
                "namespace",
            ),
            account_id=_entity_scope(
                source_entity,
                source_snapshot,
                "account",
            ),
            project_id=_entity_scope(
                source_entity,
                source_snapshot,
                "project",
            ),
            subscription_id=_entity_scope(
                source_entity,
                source_snapshot,
                "subscription",
            ),
        )
    ]
    identities = {
        entity.id: canonical_identity_for_entity(
            entity,
            target_snapshot,
        )
        for entity in eligible
    }

    canonical = [
        entity
        for entity in eligible
        if entity.id == source_entity.id
        or identities[entity.id].canonical_id
        == source_identity.canonical_id
    ]
    if canonical:
        return _finish_resolution(
            candidates=canonical,
            identities=identities,
            status_strategy=(
                CanonicalIdentityResolutionStrategy.CANONICAL_ID
            ),
            input_identifier=source_entity.id,
            matched_value=source_identity.canonical_id,
            reason=(
                "The entities have the same exact or source-specific "
                "canonical identity across the supplied snapshots."
            ),
        )

    source_native_values = {
        *(_native_values(source_entity)),
        source_identity.source_native_id,
    }
    source_native_values.discard(None)
    native = [
        entity
        for entity in eligible
        if any(
            _native_equal(entity, expected, actual)
            for expected in source_native_values
            for actual in _native_values(entity)
        )
    ]
    if native:
        return _finish_resolution(
            candidates=native,
            identities=identities,
            status_strategy=(
                CanonicalIdentityResolutionStrategy.SOURCE_NATIVE_ID
            ),
            input_identifier=source_entity.id,
            matched_value=sorted(source_native_values)[0],
            reason=(
                "A strong source-native identity matched across the "
                "supplied snapshots."
            ),
        )

    source_aliases = {
        source_entity.id,
        *source_entity.aliases,
        *source_identity.aliases,
    }
    alias_matches: list[Entity] = []
    matched_aliases: set[str] = set()
    for entity in eligible:
        target_aliases = {
            entity.id,
            identities[entity.id].canonical_id,
            *entity.aliases,
            *identities[entity.id].aliases,
        }
        overlap = source_aliases.intersection(target_aliases)
        if overlap:
            alias_matches.append(entity)
            matched_aliases.update(overlap)

    if alias_matches:
        return _finish_resolution(
            candidates=alias_matches,
            identities=identities,
            status_strategy=(
                CanonicalIdentityResolutionStrategy.SCOPED_ALIAS
            ),
            input_identifier=source_entity.id,
            matched_value=(
                sorted(matched_aliases)[0]
                if matched_aliases
                else None
            ),
            reason=(
                "An explicit deterministic scoped alias matched across "
                "the supplied snapshots."
            ),
        )

    fallback = [
        entity
        for entity in eligible
        if entity.name == source_entity.name
    ]
    if fallback:
        return _finish_resolution(
            candidates=fallback,
            identities=identities,
            status_strategy=(
                CanonicalIdentityResolutionStrategy.SOURCE_FALLBACK
            ),
            input_identifier=source_entity.id,
            matched_value=(
                f"{source_entity.kind}/{source_entity.name}"
            ),
            reason=(
                "The exact source-specific scoped kind/name fallback "
                "matched across the supplied snapshots."
            ),
        )

    return _finish_resolution(
        candidates=[],
        identities=identities,
        status_strategy=CanonicalIdentityResolutionStrategy.NONE,
        input_identifier=source_entity.id,
        matched_value=None,
        reason=(
            "No deterministic cross-snapshot identity match was found."
        ),
    )


def resolved_snapshot_entity(
    snapshot: GraphSnapshot,
    resolution: CanonicalIdentityResolution,
) -> Entity | None:
    if resolution.status != CanonicalIdentityResolutionStatus.RESOLVED:
        return None
    return next(
        (
            entity
            for entity in snapshot.entities
            if entity.id == resolution.resolved_entity_id
        ),
        None,
    )
