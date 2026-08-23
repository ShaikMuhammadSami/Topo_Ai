# TopoAI Causal Candidate Policy v1

Status: active product policy

Policy version: `causal-candidate-v1`

Downstream scoring version: `13c-causal-v1`

## Purpose

This policy decides which durable incident change candidates may seed a root-cause hypothesis. It does not alter the raw incident-change score, raw candidate ordering, 13C coefficients, TC-4 evidence ledger, TC-5 confidence semantics, or blast-impact policy.

EVAL-1 motivated the policy: in Sentinels A and C, rollout-derived `selects`, `routes_to`, and `owns` changes occupied the leading hypotheses while the independently observed Deployment image mutation remained outside Top-3. Sentinel C recorded that mutation at raw rank 11 with raw score 55.2. The defect was semantic eligibility before hypothesis truncation, not a missing numeric bonus.

The executable owner is `app.services.causal_candidate_policy`. The synchronized machine contract is [causal-candidate-policy-v1.json](./causal-candidate-policy-v1.json).

## Roles and eligibility

| Role | Meaning | Eligibility |
|---|---|---|
| `source_mutation` | A source/provider-native mutation or action such as Git, CI/CD, Terraform, Kubernetes control-plane, or cloud audit change | `primary_eligible` |
| `observed_resource_mutation` | A material snapshot-observed mutation to a mutable control/configuration resource | `primary_eligible` |
| `derived_topology_consequence` | Graph structure produced by another mutation, including snapshot relationship churn | `supporting_only` |
| `derived_runtime_consequence` | Controller/runtime object or membership churn such as ReplicaSet, Pod, EndpointSlice, or runtime artifact appearance | `supporting_only` |
| `runtime_symptom` | Structured failure/health evidence such as ImagePullBackOff, CrashLoopBackOff, or OOMKilled | `supporting_only` |
| `legacy_or_unknown` | Insufficient structured data for a defensible current classification | bounded `fallback_eligible`, or `ineligible` for explicit non-mutation states |

Supporting-only facts remain in the persisted selection audit. They do not independently seed a hypothesis and are never rebranded as legacy fallback.

## Structured inputs

Classification uses only structured event data:

- `ChangeEvent.source`, `kind`, and `status`;
- normalized `change_type` and `category` metadata;
- entity kinds from normalized before/after data, durable entity references, or links resolved on the incident-pinned snapshot;
- relationship ID and predicate;
- structured provider/runtime reason.

Human-readable titles are not parsed. There are no Sentinel IDs, evaluation namespaces, embeddings, LLMs, or numeric candidate bonuses.

## Kubernetes resource semantics

Material additions, removals, or updates to known mutable control resources—Deployment, StatefulSet, DaemonSet, Service, ConfigMap, Secret, Ingress, NetworkPolicy, Job, and CronJob—are observed resource mutations. The same is true for structured material cloud resource changes recognized from AWS, Azure, or GCP entity kinds.

ReplicaSet, Pod, EndpointSlice, and ControllerRevision lifecycle changes are generated runtime consequences by default. Container image graph-entity appearance is also consequence/context; the causal control mutation remains the workload/source change. Cluster, Namespace, and Node inventory churn is structural topology context under v1.

A native Kubernetes event is not broadly demoted. A native event with a known mutation kind remains a source mutation, except when its linked structured identity shows a generated runtime resource, its structured reason is a runtime symptom, or its provider reason identifies controller lifecycle behavior (`ScalingReplicaSet`, `SuccessfulCreate`, `SuccessfulDelete`, or `Killing`). Those lifecycle observations remain supporting-only even when Kubernetes attaches them to a mutable controller object.

## Relationship-diff semantics

Snapshot-derived `relationship_added`, `relationship_removed`, and `relationship_updated` events are derived topology consequences for every current predicate, including `selects`, `routes_to`, and `owns`. This is a v1 root-candidate rule, not a universal claim that relationships can never be causal. A provider-native networking or security mutation is classified from its native mutation record; the later derived graph edge remains supporting context.

## Source-native semantics

Known mutation/action events from Git, GitHub, GitLab, CI, CD, GitHub Actions, Jenkins, Azure DevOps, Terraform, Kubernetes, AWS CloudTrail, Azure Activity Log, GCP Audit Logs, and manual authenticated submission are primary eligible. An explicit unknown event kind does not silently become a source mutation and follows bounded legacy fallback semantics.

## Runtime symptoms

Structured runtime failure reasons are supporting-only. Failure signals continue to drive incident identity, temporal evidence, runtime-failure ledger claims, and affected-entity validation through the existing services. Candidate selection does not delete or reinterpret those facts and does not modify TC-4.

## Selection before Top-N

The deterministic pipeline is:

```text
all raw IncidentChangeCandidates (up to the existing bounded analysis fetch)
        ↓
classify every candidate
        ↓
primary-eligible population
        ↓ if empty only
genuine legacy fallback population
        ↓
existing score/risk/time order, stable ID for exact ties
        ↓
existing max_hypotheses candidate limit
        ↓
unchanged 13c-causal-v1 hypothesis generation and scoring
```

Supporting-only candidates never consume primary slots. If no primary or defensible fallback exists, 13C returns the existing no-hypothesis/insufficient-evidence result.

## Raw ranking and scoring preservation

The raw `IncidentChangeCandidate.score` and list rank are not modified. The audit separately records `raw_rank` and `eligible_rank`. Thus a derived event may remain raw rank 1 while a Deployment mutation at raw rank 11 becomes eligible rank 1.

The 13C formula and version remain unchanged:

```text
candidate.score * 0.40
+ topology_component * 25
+ temporal_component * 15
+ change_kind_prior * 10
+ lineage_component * 10
```

The result is still clipped to 0–100 and interpreted by TC-5 as a heuristic ranking, not a calibrated probability.

## Persistence and versioning

New immutable `CausalAnalysisResponse` payloads store `candidate_policy_version=causal-candidate-v1` and one audit row per raw candidate: event/change ID, raw rank/score, role, eligibility, eligible rank, selection flag, reason, structured classification inputs, and exclusion reason.

The policy version participates in the analysis input fingerprint, so a new-policy generation cannot silently overwrite an older generation. Repository idempotency remains unchanged. Historical payloads deserialize with a null policy version and empty audit; loading them does not rewrite their stored JSON or claim they used v1.

## Compatibility boundaries

- TC-1 through TC-5 contracts are unchanged.
- `13c-causal-v1` coefficients and version are unchanged.
- `blast-impact-v1` is unchanged.
- Incident correlation, ownership, connectors, UI, and LLM behavior are unchanged.
- TC-4 ledgers are built only for selected hypotheses exactly as before; exclusion metadata is an analysis-level audit, not fabricated supporting evidence.

## Limitations

- V1 uses explicit resource-kind registries plus structured category delegation; it is not an exhaustive ontology of every provider resource.
- Multiple genuinely primary mutations still compete under existing incident-change and 13C scoring. This policy deliberately does not repair a separate relevance-ranking defect.
- A source-native event with an unknown kind remains fallback rather than being assumed causal.
- Supporting-only consequences are auditable but are not injected into a selected hypothesis ledger merely because they were nearby.
- Three Sentinel reruns are engineering evidence, not a statistically meaningful accuracy measurement.
