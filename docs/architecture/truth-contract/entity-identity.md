# TC-1 canonical entity identity

Status: implemented identity contract v1

Scope: graph entity identity and deterministic compatibility resolution only. This document does not define relationship provenance, temporal validity, evidence scoring, entity merge/split history, or a graph database.

## Principles

1. `Entity.id` is the graph identifier used inside one immutable topology snapshot.
2. Canonical identity is source-specific. Kubernetes UID, AWS ARN/resource ID, Azure resource ID, GCP full resource name, repository ID, commit SHA, build ID, and image digest are not forced into one universal template.
3. Stable source-native identity takes precedence over display names.
4. Names are usable only with the minimum deterministic source scope required to avoid collisions.
5. Identity does not collapse ontology. Pod, ReplicaSet, Deployment, Service, image, commit, and repository remain separate entities; graph relationships express ownership and dependency.
6. Ambiguity is a valid result. Topo returns unresolved/ambiguous rather than selecting the first candidate.
7. Historical snapshots are immutable. TC-1 does not rewrite stored payloads or incident references.
8. Identity resolution has no fuzzy matcher, embedding, LLM, or probability model.

## Mapping to the current graph model

| Contract concept | TopoAI representation |
|---|---|
| canonical ID | `Entity.id` for v1-produced entities; derived canonical ID for a legacy entity during resolution |
| entity kind | `Entity.kind` |
| source system | `Entity.source_system` |
| source-native ID | `Entity.external_id`, with selected provider properties as compatibility inputs |
| account/project/subscription/cluster/namespace/environment scope | `GraphSnapshot.scope`, `Entity.environment`, and source properties |
| aliases | `Entity.aliases` |
| identity version | `Entity.identity_version` |
| observation time | `Entity.observed_at` |

TC-1 did not add `first_seen` or `last_seen` fields to immutable snapshot entities. `observed_at` is the actual snapshot observation field; source-oriented cloud/runtime tables retain their existing first/last-seen fields. Formal valid/system-time semantics belong to the later temporal Truth Contract.

Snapshots created before TC-1 load with `identity_version="legacy"` and an empty alias list through backward-compatible Pydantic defaults. They are not persisted again merely to add those defaults.

Runtime contracts are owned by:

- `backend/app/models/canonical_identity.py` — versioned identity and auditable resolution result models;
- `backend/app/services/canonical_identity.py` — canonical builders, safe alias derivation, and deterministic snapshot resolution;
- `backend/app/models/topology.py:Entity` — graph ID, source-native ID, aliases, and identity version stored in new snapshots.

## Kubernetes v1

Kind tokens remove an optional `Kubernetes` prefix and are lower-cased. Cluster text is made ID-safe using the repository's existing direct-collector character policy.

Priority:

1. Kubernetes UID when present:

   ```text
   k8s:{cluster}:{kind}:{uid}
   ```

2. UID-less, exact scoped fallback:

   ```text
   tuple = cluster | kind | namespace-or-empty | name
   k8s:{cluster}:{kind}:{sha256(tuple)[0:24]}
   ```

Cluster, kind, namespace for namespaced resources, and name all participate. Therefore identical namespace/name/kind values in two clusters do not collide, and `Service/foo` cannot collide with `Deployment/foo`.

This v1 fallback preserves the pre-TC-1 agent format for normal ID-safe cluster names. The direct collector and network enricher now call the same builder. The exact watcher → agent-shaped inventory → snapshot → incident entity-resolution path is covered by an integration-style test.

Pod UID remains object-lifetime identity. TC-1 does not rewrite a Pod to its Deployment. Workload stability/correlation remains a separate incident-fingerprint and topology-relationship concern.

### Kubernetes legacy aliases

For a UID-less entity, new snapshots retain deterministic aliases for all formats found by the post-15D audit:

| Producer | Pre-TC-1 fallback |
|---|---|
| direct collector | `k8s:{safe_cluster}:{kind}:{namespace-or-_cluster}:{name}` |
| agent snapshot ingest | `k8s:{cluster}:{kind}:{sha256(cluster|kind|namespace|name)[0:24]}` |
| network enricher | `k8s:{cluster}:{kind}:{sha256(cluster|namespace|kind|name)[0:24]}` |

The agent form is normally canonical v1 and therefore is omitted from `aliases` when identical. The old direct cluster ID `k8s:{safe_cluster}:cluster` is also retained as an alias of the v1 cluster entity.

An old hash cannot be reversed without the original scope/name fields. A legacy snapshot that lacks those fields cannot be safely reconciled and remains unresolved. If multiple legacy nodes derive the same v1 identity or share an alias, resolution is ambiguous and does not merge them.

## Cloud v1

Cloud display names are not canonical identity inputs.

| Source | Native authority | Canonical graph rule | Compatibility |
|---|---|---|---|
| AWS | ARN when supplied; otherwise provider resource ID scoped by account/region/type | existing `aws:{sha256(aws|account|region|resource_type|resource_id)[0:32]}` | existing graph IDs remain canonical |
| Azure | normalized full Azure resource ID | existing `azure:{sha256(lowercase resource ID)[0:32]}` | existing graph IDs remain canonical; source-native comparison is case-insensitive and ignores a trailing slash |
| GCP | normalized full resource ID/self link | existing `gcp:{sha256(lowercase resource ID)[0:32]}` | existing graph IDs remain canonical; source-native comparison is case-insensitive and ignores a trailing slash |

Provider resource IDs stay in `external_id` and source properties for deterministic change-to-entity correlation. Account/project/subscription and region are resolution filters where present. A display name without provider-native ID and adequate provider scope is not promoted to a canonical alias.

## Repository, commit, and CI/CD v1

GitHub repository identity remains host and provider-ID scoped:

```text
github:{host}:repository:{repository_database_id}
```

When the provider database ID is unavailable, the connector's existing host-scoped repository name fallback is retained; rename stability is not proven for that fallback.

Commit identity is repository-scoped:

```text
{repository_canonical_id}:commit:{lowercase_sha}
```

The same SHA in two repositories therefore produces two graph IDs. A SHA-only lookup that matches both is ambiguous. It is not guessed.

GitHub Actions graph entities use the provider workflow **run ID**, not the display run number:

```text
github:{host}:workflow-run:{run_id}
```

The generic v1 CI builder contract for sources whose native build number is only pipeline-local is:

```text
ci:{provider}:{sha256(normalized pipeline scope)[0:20]}:build:{native_build_id}
```

Jenkins change events already include job name with build number. GitLab/Azure DevOps/Terraform currently produce change events rather than a complete graph build/resource entity. TC-1 does not fabricate missing graph entities or pipeline IDs.

## Container image v1

Immutable content and mutable reference are intentionally distinct:

```text
artifact:container-image:sha256:{64 hex characters}
artifact:container-image:reference:{sha256(normalized registry/repository:tag)[0:24]}
```

A tag such as `payment-api:latest` is not treated as identical to a digest. A digest can unify multiple requested references only when runtime/source evidence supplies that digest. TC-1 retains the existing limitation that a tag can move to different content over time.

## Runtime/eBPF v1 boundary

Host, container, Docker network, process, service, listening-port, and endpoint graph entities retain their existing source-specific digest formats. Strong native host/container/network identifiers are preferred; process identity includes PID/create time and endpoint identity includes its observed protocol/address/port tuple. These are lifetime/observation identities, not durable business-service identities.

TC-1 found no cross-producer runtime ID conflict equivalent to Kubernetes and therefore did not rename these entities. New runtime entities load the shared `Entity` alias/version fields but remain `legacy` until a runtime-specific algorithm is deliberately versioned. Address reuse, NAT, PID reuse, and incomplete workload correlation remain known limitations.

## Terraform and business/service identity boundaries

Terraform Cloud supplies durable change/run/workspace evidence. The repository has no Terraform state-resource graph entity, so TC-1 defines no fabricated Terraform entity ID. Configured `provider_resource_id` references resolve only to real cloud/Kubernetes entities when strong native/scoped evidence matches.

The existing logical Kubernetes application identities and ownership `service_name` are grouping/routing concepts. They do not replace graph `Entity.id`, and TC-1 does not create a second business-service catalog.

## Resolution priority and audit result

`resolve_snapshot_entity_identity()` applies these stages in order:

1. exact snapshot/canonical entity ID;
2. strong source-native ID (`external_id` or selected provider-native properties);
3. explicit deterministic scoped alias;
4. exact source-specific kind/name fallback with supplied scope.

Every stage applies available source, kind, cluster, namespace, account, project, and subscription filters. Name fallback requires both exact kind and exact name; substring, suffix stripping, edit distance, and case-insensitive fuzzy resource-name matching are absent.

The structured result records:

- status: resolved, ambiguous, or unresolved;
- input identifier;
- strategy;
- snapshot entity ID;
- derived canonical ID;
- matched value;
- identity version;
- all ambiguous candidate entity IDs;
- deterministic reason.

When more than one candidate survives a stage, resolution stops as ambiguous. It never advances to a weaker stage or chooses the first row.

## Historical compatibility

- No topology snapshot payload is updated in place.
- No incident, signal, change link, ownership mapping, causal analysis, or briefing record is bulk rewritten.
- An incident's historical `affected_entity_id` continues to address the original entity in its pinned snapshot.
- A v1 canonical ID can resolve a legacy entity when its retained source/kind/scope/name/native fields safely derive that v1 identity.
- A legacy direct/network Kubernetes ID can resolve a v1 entity through deterministic aliases.
- Exact ownership mappings created with a safe legacy graph ID match the corresponding v1 entity alias.
- Explicit change references are canonicalized against the selected snapshot before a link is stored when that snapshot exists.
- Blast-radius and incident-change roots resolve aliases inside the already pinned snapshot. This adds no latest-snapshot fallback.

No persisted migration is required for TC-1. A future migration may materialize aliases for query performance, but it must be append-safe and cannot rewrite historical snapshot IDs.

## Identity version transition

An identity-algorithm transition is representation metadata, not customer
infrastructure change. Historical snapshot payloads and raw IDs remain
immutable, while `compare_snapshots()` aligns entities from the two explicitly
supplied snapshots through the TC-1 contract before evaluating topology state.

Alignment applies exact/canonical identity, strong source-native identity,
deterministic scoped aliases, and exact source-specific scoped fallback. A
cross-version entity is paired only when resolution is unique in both
directions. This mutual one-to-one condition prevents duplicate or ambiguous
legacy entities from being silently collapsed.

After alignment, entity comparison excludes identity representation fields:
raw graph ID, source-native ID, aliases, identity version, and observation time.
Material fields such as kind, name, labels, properties, environment, and
confidence retain the existing change semantics. Therefore a legacy-to-v1 ID
change alone emits no entity add/remove/update evidence, while an image,
configuration, spec, label, or other material change still emits the existing
update.

Relationship comparison first aligns its source and target entities. A legacy
edge and v1 edge are equivalent only when both endpoints align, relationship
type matches, and the endpoint/type key is unique on both sides. Endpoint ID
representation is normalized before material relationship comparison, so an
identity-only transition emits no relationship add/remove/update evidence.
Relationship properties and other material fields remain diffable.

This alignment is local to the `before` and `after` snapshots passed to the
diff. It does not query persistence, use a latest topology snapshot, or rewrite
either snapshot. Ambiguous equivalence remains unmatched and is preserved as
uncertain add/remove evidence rather than guessed away. Because normalized
changes and topology change events are derived from this identity-aware diff,
an identity-version-only transition cannot be promoted into false customer
change evidence or causal RCA input.

## Merge/split and unresolved limitations

TC-1 does not implement an entity registry or merge/split event ledger. Future merge/split auditing can use `identity_version`, canonical ID, explicit aliases, source-native ID, and resolution evidence, but needs a separate append-only design.

Unsafe/unreconcilable cases remain unresolved:

- UID-less Kubernetes history missing cluster/kind/namespace/name material;
- duplicate legacy nodes that map to one canonical key;
- unscoped names or aliases;
- commit SHA without repository scope when more than one repository matches;
- CI build number without provider and pipeline scope;
- cloud display name without provider-native ID and source scope;
- mutable image tag without a digest;
- runtime process/endpoint observations after lifetime/address reuse;
- repository-name fallback after rename when provider repository ID was unavailable.

These limitations are preferable to a dangerous false merge.
