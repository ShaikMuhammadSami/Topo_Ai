# Lineage-Aware Causal Candidate Admission v1

Status: SC-2 product contract  
Admission policy: `causal-candidate-admission-v2`  
Downstream candidate classification policy: `causal-candidate-v1` (unchanged)

## Measured divergence

SC-1 established provider-authentic source revision and file-mutation identity,
but the preserved LINEAGE-1 source event was 789.95 minutes before the incident.
The ordinary 180-minute discovery window correctly returned no candidate. SC-2
repairs only `CAUSAL_CANDIDATE_MISSING`: it defines when an old canonical source
change may enter the existing causal evaluation pipeline.

Lineage is admission support, not causal support. Exact lineage permits a source
change to be considered. It does not assert that the source change caused the
incident, does not add a score, and does not force a hypothesis.

## One candidate set, two admission paths

### Path A — temporal

Path A is the existing incident-change query and score:

1. Determine the incident operational boundary.
2. Query the existing bounded change records.
3. Retain events whose TC-3 effective time is within the configured lookback and
   after-window.
4. Apply the existing time, entity, scope, and risk inputs.
5. Sort by the existing score/risk/source-time key.

The default RCA lookback remains exactly 180 minutes. Path A's time filtering,
event identity, scoring formula, ordering, and recent-event behavior are not
redefined by SC-2.

### Path B — exact immutable lineage

Path B starts from incident reality and traverses in the opposite direction of
artifact production:

```text
incident
  -> explicitly pinned topology snapshot
  -> exact affected Pod (or already-exact workload)
  -> exact ReplicaSet owner
  -> exact Deployment owner
  -> exact failing container, or the only container
  -> immutable image digest used by both Pod and workload
  -> bounded provider build evidence for that exact digest
  -> exact GitHub Actions run and attempt
  -> exact repository ID and commit SHA
  -> canonical SC-1 GitHub source-change event
```

The runtime half is read only from `IncidentRecord.topology_snapshot_id`. The
lineage service does not use the incident-change service's legacy at-or-before
snapshot fallback and never queries the latest topology. The provider half is a
bounded indexed lookup by the exact immutable image digest; it is not a scan of
historical source changes.

## Atomic candidate and mutation bundle

The atomic candidate remains the existing canonical `ChangeEventRecord` for the
source revision. Its `event_id` is the deduplication key. SC-1
`source_file_mutations` are attached as `mutation_set[]` to that one candidate.
A revision with twenty mutations is one candidate, not twenty candidates.

The SC-1 capture completeness is retained. A partial or empty mutation bundle
does not prevent revision-level admission when the repository, revision, image,
run, and canonical source-change identities are exact. Partial evidence does not
earn file-level specificity and SC-2 does not identify any individual file as a
cause.

## Identity and provenance gates

The affected entity ID must exactly identify an entity in the pinned snapshot.
No kind/name, alias, fuzzy, or current-state resolution is performed by Path B.
Pod ownership edges must retain their existing directions:

- `Deployment --owns--> ReplicaSet`
- `ReplicaSet --runs--> Pod`

Kubernetes owner-reference edges may be declared, observed, or deterministically
derived when TC-2 provenance is complete, the collector component is the trusted
Kubernetes graph source, and an authoritative owner UID reference is present.

Container-image use edges must retain:

- `Pod --uses--> ContainerImage`
- `Deployment --uses--> ContainerImage`

They must be observed or deterministically derived by the existing container
image linker, have complete TC-2 provenance, carry both image-reference and
digest references, and agree on the exact container and artifact. Inferred,
partial, unknown, or declared tag-only image edges do not qualify.

The image entity must have a canonical `sha256` digest as both external identity
and immutable artifact property. Mutable tags, pull time, repository similarity,
or array position cannot establish artifact identity.

H3-R1 durable build evidence must be complete, source-time authoritative, and
match the runtime image's exact digest and repository. The provider record
already binds repository ID, run ID, run attempt, commit SHA, immutable image,
build record digest, and provider artifact identity. The canonical SC-1 event
must match the repository full name, commit SHA, canonical external source ID,
and authoritative source time. When SC-1 captured a repository identity in the
mutation envelope, its provider repository ID must also match. An unavailable
mutation envelope may still retain revision-level admission because the exact
provider artifact record supplies the stable repository ID and the canonical
authenticated event supplies the same repository/revision identity; it supplies
no file-level evidence.

## Multi-container rule

If the primary incident signal carries an exact container name, including a
Kubernetes `spec.containers{name}` field path, only that container is traversed.
Healthy sidecars cannot contribute Path B candidates.

If no container is named and the affected Pod/workload has exactly one relevant
container, Path B may proceed. If multiple containers exist and the failing
container is unknown, admission fails closed with
`affected_container_ambiguous`. Container array order is never used.

## Provider history and TC-3

Provider `observed_at` and `recorded_at` may be later than the incident. Those
timestamps describe when Topo learned the provider fact, not when the immutable
relationship became true. Path B gates on provider `temporal.effective_at` and
requires it to be at or before the incident boundary. The canonical source event
must be effective no later than both the provider build fact and the incident.

Provider evidence whose effective time is after the incident is rejected with
`provider_effective_time_incompatible`. SC-2 does not rewrite source time to
incident or deployment time.

There is no Path B source-age cutoff. Exact immutable provenance, rather than a
broad historical time range, bounds the lookup. Activation time may be carried
later when authoritative evidence exists, but it is not a v1 admission gate.

## Ambiguity, deduplication, and budgets

All provider records for the exact artifact are considered within a deterministic
cap of 32. More records produce `lineage_budget_exceeded`; Path B never selects an
arbitrary first record. Source lookup is an exact indexed commit-SHA query capped
at eight records.

Multiple exact runs or paths resolving to the same repository and canonical
revision produce one candidate. Their paths and evidence references are sorted,
deduplicated audit context. If equally authoritative paths for the same digest
resolve to distinct repository/revision identities, Path B rejects the artifact
with `ambiguous_source_provenance`.

If Path A and Path B resolve to the same event ID, one candidate records both
`temporal` and `exact_immutable_lineage`. The original score is retained. Path B
never adds a lineage score or changes the downstream ordering key.

## Admission audit and persistence

`IncidentChangeAnalysisResponse` reports:

- `candidate_admission_policy_version`
- `lineage_admission_audit[]`

An admitted candidate and the durable selection audit carry:

- canonical change ID and revision
- admission bases
- exact evidence references
- deterministic lineage paths
- container and immutable-image scope
- SC-1 mutation bundle and completeness
- admission state and bounded reason
- admission-policy version

Incomplete Path B attempts remain visible in the lineage admission audit even
when no candidate is added. Existing causal-analysis JSON persistence stores
both the lineage-attempt audit and the candidate selection audit. Historical
payloads load with null/empty additive fields and are not rewritten.

The candidate role/eligibility policy remains `causal-candidate-v1` because SC-2
does not alter classification. The separate
`causal-candidate-admission-v2` version means:

```text
unchanged temporal admission
+ exact immutable-lineage admission
```

## Fail-closed behavior

Bounded reason codes distinguish missing pin/entity/owner/container/image,
incomplete relationship provenance, workload-image mismatch, missing provider or
source change, historically incompatible provider time, distinct-revision
ambiguity, and budget overflow. Missing evidence reduces knowledge. No fallback
uses tags, names, branches, messages, PR text, timestamps alone, logs, local Git,
embeddings, LLMs, or evaluation truth.

## Safe abstention and non-goals

After admission, the existing candidate classification, causal relevance,
ranking, TC-4 evidence ledger, and root-cause representation operate unchanged.
A lineage-admitted event can be ineligible, fail relevance, rank below another
candidate, or yield no supported hypothesis. SC-2 does not:

- globally widen the 180-minute window;
- add a lineage ranking component or forced Top1;
- change `causal-relevance-v1` or graph directions;
- add TC-4 claim types;
- create reverse edges, `SourceFile`, or `LineageCandidate` topology entities;
- modify incident lifecycle, topology pinning, or runtime exit-code evidence;
- query providers or local Git during causal analysis;
- implement activation history or analysis lifecycle redesign.
