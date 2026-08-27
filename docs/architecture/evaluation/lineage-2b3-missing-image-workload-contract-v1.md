# LINEAGE-2B.3-0 — Missing Immutable Image -> Affected Workload Provenance Contract v1

Status: **DOCUMENTATION / EXECUTABLE SCENARIO CONTRACT ONLY**

Date: 2026-08-27

Contract branch:
`evaluation/lineage-2b3-missing-image-workload-contract-v1`

Accepted repository commit at contract freeze:
`eeee7ac7f49adc1a948dfb8e8ca49ef09e7374bf`

Accepted repository summary:
`eeee7ac docs(evaluation): freeze missing run image baseline (#55)`

Family: **LINEAGE-2B — Broken / Incomplete Immutable Lineage Robustness v1**

Scenario: **LINEAGE-2B.3 — Missing Immutable Image -> Affected Workload Provenance**

## 1. Purpose and boundary

This checkpoint freezes an executable scenario contract for measuring whether
TopoAI safely reduces causal specificity when build provenance identifies an
exact immutable image but preserved evidence cannot prove that the affected
workload used that image.

This is a contract, not a measurement. It does not construct B3, mutate the
accepted seed, remove image observations or graph relationships, reset or run
RCA, create a result root, generate EAI, create a baseline, modify product or
evaluator code, start B4 through B6, or authorize AR-4.

The only authorized output is this document. A separately approved next block
may implement the B3 harness and perform the offline measurement under this
frozen contract.

## 2. Accepted program and family state

The following dependencies remain accepted and unchanged:

| Program item | Accepted state |
|---|---|
| LINEAGE-1 | Provider-backed source-to-runtime golden proof: `PROVEN` |
| LINEAGE-2A | `ACCEPTED / CLOSED`; `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE` |
| EAI-1 | Accepted contract `evaluation-artifact-integrity-v1` |
| LINEAGE-2B.1 | `EXPERIMENT_CONSTRUCTION_BLOCKED`; `evidence_model_nonseparable`; `NOT EXECUTED` |
| LINEAGE-2B.2 | `ACCEPTED / CLOSED`; `ROBUST_IN_MEASURED_MATRIX`; `NO_DIVERGENCE` |
| LINEAGE-2B-A0 | Accepted representability audit |
| LINEAGE-2B.3 | Model-representable and seed-constructible; not yet measured |

B1 is not converted into PASS or FAIL. B2's accepted result is not reopened or
generalized to B3. The A0 audit is the construction authority for B3 unless a
future implementation audit discovers a material contradiction in the current
schema.

## 3. Permanent counterfactual doctrine

The following doctrine is frozen:

> COUNTERFACTUAL EVALUATION MUST RESPECT THE ATOMICITY OF AUTHORITATIVE
> OBSERVATIONS; A CONCEPTUAL GRAPH EDGE IS NOT AUTOMATICALLY AN INDEPENDENTLY
> MUTABLE EVIDENCE FACT.

Also frozen:

> ADVERSARIAL SCENARIOS MAY REMOVE ONLY INDEPENDENTLY REPRESENTABLE TRUTHS.

The evaluator must not fabricate separability, provider facts, Kubernetes
observations, partial observations, or replacement authority that the accepted
model and seed do not contain.

## 4. Governing B3 invariant

The B3 invariant is frozen exactly as:

> EXACT SOURCE-TO-RUNTIME CAUSAL ATTRIBUTION MUST NOT CROSS AN UNPROVEN
> IMAGE -> AFFECTED-WORKLOAD BOUNDARY.

Equivalently:

```text
Commit -> Run -> Image

and

affected workload -> failure

do not imply

this Image was used by this affected workload
```

Artifact production provenance is not deployment/runtime provenance. Exact
identity on either side of the gap does not prove the missing relationship.

## 5. Semantic interpretation of the counterfactual

B3 does **not** assert that Kubernetes ran a Pod with no container image.
Kubernetes workload semantics are not rewritten.

B3 asserts that TopoAI's preserved evidence no longer contains authoritative
workload-specific image observations sufficient to prove that the exact golden
immutable image was requested or used by the affected Deployment or Pod.

The workload, failure, image, and image's source/build provenance remain known.
Only their affected-workload association becomes unavailable in the preserved
evidence world. Unknown or missing is valid; a synthetic alternative image or
partial observation is not.

## 6. Intact and broken chains

### 6.1 Intact golden chain

```text
Repository
    ->
Commit
    ->
Actions Run
    ->
Immutable Image
    ->
Deployment / ReplicaSet / Pod
    ->
Runtime Failure
```

### 6.2 B3 broken chain

```text
Repository
    ->
Commit
    ->
Actions Run
    ->
Immutable Image

    X

Deployment / ReplicaSet / Pod
    ->
Runtime Failure
```

The missing authoritative boundary is the golden immutable image to the
affected workload/runtime.

## 7. Frozen identities

| Dimension | Frozen identity |
|---|---|
| Repository | `1278498159 / ShaikMuhammadSami/Topo_Ai` |
| Commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Actions Run | `32695735269` |
| Run attempt | `1` |
| BuildArtifactEvidence E1 | `build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb` |
| Run -> Image relationship | `rel:63f5cd5dfce59d148ae5` |
| Golden digest | `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Golden image entity | `artifact:container-image:sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Deployment | `k8s:docker-desktop:deployment:bd4cfb7a-d32a-43bf-bf82-366e3fd8841a` |
| ReplicaSet | `k8s:docker-desktop:replicaset:200703db-a601-44f0-90ff-63c64cb17162` |
| Affected Pod | `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168` |
| Deployment -> Image | `rel:496906e3e345259910c9` |
| Pod -> Image | `rel:0548ac3e949f44b3569c` |
| Deployment -> ReplicaSet | `rel:57555e411f2db29864c2` |
| ReplicaSet -> Pod | `rel:9c8db862d53bac71327f` |
| Shared container-image Evidence | `evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56` |
| Incident | `incident:docker-desktop:topo-eval-lineage-causal-32695735269:workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3` |
| Incident boundary | `2026-08-26T05:09:49Z` |
| Pinned snapshot | `snapshot:actions-enriched:20260826T051031Z:2d8416d3` |
| Failure signal | `signal:kubernetes-event:docker-desktop:ad733dcc-a026-424f-8984-6ed30108eec1` |

## 8. Authoritative source/build truth that must remain

B3 does not break source or build provenance. It must preserve:

- repository and source revision identity;
- provider-authentic source-file mutation evidence;
- workflow Run and attempt;
- independently authoritative Commit -> Run relationship and Evidence;
- BuildArtifactEvidence E1;
- Run -> Image `produces` relationship and provider Evidence; and
- the golden immutable ContainerImage entity.

After B3 construction the system must still know exactly:

```text
Commit -> Run -> Image
```

The preserved exact Commit -> Run authority is relationship
`rel:ebaedc357f11b3e70170` with Evidence
`evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b`.

BuildArtifactEvidence E1 and Run -> Image relationship
`rel:63f5cd5dfce59d148ae5`, including its provider Evidence, must remain
semantically unchanged.

## 9. Workload, ownership, and failure truth that must remain

B3 must preserve the Deployment, ReplicaSet, and affected Pod entities,
including their stable Kubernetes UIDs, cluster/namespace scope, labels,
non-image properties, and independently persisted runtime properties.

The UID-backed owner path must remain exact:

```text
Deployment --owns--> ReplicaSet --runs--> Pod
```

The owner relationships use complete TC-2 provenance derived from Kubernetes
owner-reference UIDs. They are independent of image-use observations.

B3 must also preserve:

- BackOff / CrashLoopBackOff failure evidence;
- affected Pod identity;
- restart and termination/error state where independently persisted;
- incident identity and boundary;
- primary failure signal; and
- incident-pinned historical topology identity.

The accepted Kubernetes failure signal contains affected object identity and
time but no image identity. It therefore survives the image/workload cut
unchanged unless a future schema audit materially contradicts that accepted
fact, in which case construction must stop.

## 10. Current SC-3 observation semantics

Contract `kubernetes-container-image-identity-v1` keeps three semantic roles
separate:

1. `requested_image`, captured from workload spec;
2. `runtime_status_image`, captured from
   `pod.status.containerStatuses[].image`; and
3. `runtime_image_id`, captured from
   `pod.status.containerStatuses[].imageID`.

Each role records captured, missing, or rejected state. Requested repository-
digest observations may resolve an immutable artifact identity. Runtime-status
diagnostic values are not promoted into requested-artifact identity. The
runtime image ID remains a distinct execution observation.

The graph linker derives canonical ContainerImage entities and Deployment/Pod
`uses` relationships from these persisted observations. Therefore deleting
only graph edges would leave their Layer-1 authorities intact and would be an
invalid B3 construction.

## 11. Deployment requested-image proof surfaces

A future B3 implementation must re-audit and remove the affected Deployment's
golden image co-reference from every applicable current-schema equivalent of:

- `properties.containers[].image` compatibility field;
- `properties.containers[].image_identity.requested_image`;
- nested `resolved_artifact_identity`;
- `resolved_artifact_basis` where it would assert the removed resolution;
- `identity_evidence_refs` for affected-container image identity;
- other nested SC-3 requested-image identity fields; and
- relationship properties/provenance that repeat the requested image or
  golden digest.

Fields must be removed or converted only to a truthful existing missing state.
The evaluator must not write another image, digest, repository, tag, or
synthetic Evidence object.

## 12. Deployment image-bearing annotation

The accepted Deployment includes
`kubectl.kubernetes.io/last-applied-configuration` in
`properties.annotations`. Its serialized Pod template embeds the exact golden
image reference and therefore preserves a workload-specific co-reference even
if normalized SC-3 fields are removed.

The future B3 cut must truthfully and deterministically remove or sanitize only
the image-bearing workload-specific portion of that annotation. It must retain
unrelated Deployment configuration and annotations. If a complete truthful cut
cannot be made without corrupting unrelated authoritative configuration, B3 is
`EXPERIMENT_CONSTRUCTION_BLOCKED`.

## 13. Pod requested-image proof surfaces

The future mutation must re-audit and remove the affected Pod's golden image
co-reference from current-schema equivalents of:

- `properties.containers[].image`;
- nested `image_identity.requested_image`;
- `resolved_artifact_identity`;
- `resolved_artifact_basis` where it asserts the removed resolution;
- `identity_evidence_refs`; and
- relationship properties/provenance repeating requested image or digest.

Container identity, container name, readiness, restart count, container ID,
and other independently persisted non-image fields must remain unchanged.

## 14. Pod runtime-image proof surfaces

The future mutation must also remove workload-specific runtime image fields
capable of independently reconnecting the affected Pod to the golden artifact:

- `properties.containers[].image_id` from
  `pod.status.containerStatuses[].imageID`;
- nested `image_identity.runtime_image_id`;
- `properties.containers[].runtime_status_image` from
  `pod.status.containerStatuses[].image`;
- nested `image_identity.runtime_status_image`;
- corresponding `identity_evidence_refs`; and
- relationship properties and TC-2 source references derived from those
  observations.

In the accepted seed, runtime `imageID` resolves to the golden OCI index while
the runtime-status image is the separately recorded child/runtime digest
`sha256:a3392fbeae192e861a3df42d25acf050c45a657c8e277a41258332baa9451f53`.
Their distinct semantics must not be conflated, but both workload-specific
observations belong to the complete B3 cut because leaving an applicable exact
association or identity join could reconstruct victim-artifact linkage.

## 15. Derived image-use relationships

The following derived claims must be absent after a valid B3 cut:

- Deployment `--uses-->` golden Image:
  `rel:496906e3e345259910c9`; and
- affected Pod `--uses-->` golden Image:
  `rel:0548ac3e949f44b3569c`.

Both relationships contain image identity in their properties and TC-2 source
references. Their complete semantic surfaces—not merely their relationship
IDs—must be removed from the isolated snapshot copy.

## 16. Shared container-image Evidence

Both image-use relationships reference:

```text
evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56
```

The future harness must inventory that Evidence object's related entities,
relationships, payload, and any other protected claims before mutation. It may
remove or minimally rewrite the Evidence only if doing so is necessary to
remove the exact affected-workload/golden-image association and does not erase
unrelated authoritative image claims.

If the shared Evidence cannot be separated without corrupting a protected
independent truth, construction must stop as
`EXPERIMENT_CONSTRUCTION_BLOCKED`. No replacement Evidence may be fabricated.

## 17. Snapshot structural consistency

The accepted incident-pinned `GraphSnapshot` persists entities,
relationships, Evidence, scope, metadata, and collection time in one immutable
payload. Its SQL `SnapshotRecord` separately persists entity, relationship,
and evidence counts. The container-image linker also records
`metadata.container_image_artifacts` and Evidence payload counters.

A future isolated-copy mutation must audit and update only counters or metadata
whose stored meaning becomes false because of the B3 cut, including as
applicable:

- SQL `entity_count`, `relationship_count`, and `evidence_count`;
- payload entity, relationship, and Evidence collection sizes;
- `metadata.container_image_artifacts.count` and `.relationships`;
- shared container-image Evidence `artifact_count`, `relationship_count`, and
  `digest_resolved_count`; and
- any current-schema normalization or image-lineage counter that would
  otherwise make a false claim.

The golden ContainerImage entity remains, so image/entity counters must not be
blindly decremented. The exact current schema must be inventoried before any
future write.

The mutation must not change unrelated snapshot content, snapshot ID,
collection timestamp, scope, validity, incident boundary, topology pin,
owner-chain counts, or historical semantics. If changing the payload
necessarily invalidates the snapshot identity contract, construction must stop
and report the contradiction. It must never mint or attach a replacement
latest snapshot.

## 18. Complete B3 semantic cut

Subject to a fresh schema and authority audit, a valid B3 mutation must remove
every product-visible exact workload/golden-image co-reference, including
where present:

1. Deployment requested-image compatibility field;
2. Deployment nested SC-3 requested-image identity;
3. Deployment resolved artifact identity and basis;
4. Deployment image identity Evidence references;
5. image-bearing Deployment last-applied annotation content;
6. Pod requested-image compatibility field;
7. Pod nested SC-3 requested-image identity;
8. Pod resolved artifact identity and basis;
9. Pod runtime image ID;
10. Pod runtime-status image;
11. nested Pod runtime-image identity fields;
12. Pod image identity Evidence references;
13. Deployment -> golden Image `uses` relationship and dependent fields;
14. Pod -> golden Image `uses` relationship and dependent fields;
15. shared or claim-specific container-image Evidence that preserves the
    affected-workload association;
16. image-use counters or metadata made false by the cut; and
17. stale causal admission, relevance, evidence, support, and projection state.

This is a semantic checklist, not permission to blindly delete matching keys.
The future implementation must re-audit the current schema and make the
smallest truthful complete cut.

## 19. Required truth after the B3 cut

### 19.1 Must remain present and semantically unchanged

1. repository and Commit truth;
2. exact source-file mutation;
3. exact Commit -> Run authority;
4. Actions Run and attempt;
5. BuildArtifactEvidence E1;
6. exact Run -> Image relationship and provider Evidence;
7. golden ContainerImage entity and immutable digest;
8. Deployment, ReplicaSet, and affected Pod identity;
9. Deployment -> ReplicaSet and ReplicaSet -> Pod owner relationships;
10. independently persisted non-image workload/runtime properties;
11. runtime failure signal and failure evidence;
12. incident identity, primary signal, and boundary; and
13. incident-pinned snapshot identity.

### 19.2 Must be absent or unknown

1. any authoritative or co-referential proof that the golden Image belongs to
   or was used by the affected Deployment;
2. any authoritative or co-referential proof that the golden Image belongs to
   or was used by the affected Pod;
3. requested-image association in affected workload payloads;
4. runtime-image-ID association in the affected Pod;
5. runtime-status-image association capable of preserving the affected
   workload image join;
6. Deployment/Pod -> golden Image `uses` relationships;
7. authoritative Evidence reconstructing those claims;
8. stale SC-2 lineage context;
9. stale SC-4 topology paths or relevance anchors; and
10. reusable old supported source-level analysis or projection state.

## 20. Recursive broken-hop proof

Before RCA, the future harness must recursively inspect persisted JSON and
prove that no exact golden digest or repository-digest association survives in
workload-specific affected Deployment or Pod authority surfaces.

The scan must cover nested dictionaries, arrays, serialized annotation JSON,
SC-3 identity structures, runtime image fields, Evidence references,
relationship properties, relationship provenance references, snapshot
metadata, and cached analysis state. It must separately prove that no exact
Deployment/Pod -> golden Image edge or authoritative Evidence survives.

An edge-only query is insufficient. A database-wide rejection of the golden
digest is also invalid: the digest must remain in protected BuildArtifactEvidence,
Run -> Image authority, and the standalone ContainerImage entity.

The correct assertion is:

> Golden image identity MUST NOT survive in affected workload-specific
> authority surfaces.

It is not:

> Golden image identity must disappear globally.

The scan must be scoped to the incident-pinned snapshot, affected workload
entities and their dependent image claims; it must not reject legitimate
protected build/image facts elsewhere in the database.

## 21. Construction validity and blocker rule

Construction is valid only if the intended Image -> affected-workload proof is
completely absent while every explicitly protected independent truth remains
semantically unchanged.

If implementation discovers that a complete truthful cut necessarily destroys
Run -> Image authority, the golden image entity, workload identity, owner
chain, runtime failure, incident/pin, or another protected authoritative fact,
it must stop before RCA as:

```text
EXPERIMENT_CONSTRUCTION_BLOCKED
```

The reason must identify the exact shared-authority or nonseparability problem.
The harness must not widen the cut, invent a different image, invent a partial
Pod observation, fabricate Evidence, or change product models.

## 22. CONTROL and B3 symmetry

### 22.1 CONTROL

CONTROL uses one isolated byte-identical seed copy. It receives the same
derived-analysis reset as B3 and no image/workload mutation. It must freshly
reproduce the exact golden source mutation at semantic level
`INITIATING_MUTATION` through the complete immutable lineage.

If CONTROL fails, the overall measurement is `INCONCLUSIVE`.

### 22.2 B3

B3 starts from a separate byte-identical copy of the same seed. It receives
the identical derived-state reset and then only the approved Image -> workload
semantic cut plus necessary structural-consistency cleanup.

CONTROL and B3 may differ only by that cut and its necessary truthful
consistency metadata changes.

## 23. Derived-analysis reset

The accepted seed contains old source-supported causal analysis
`causal-analysis:76c9b683e95e2f2fd599677122f2ebae`. Neither CONTROL nor B3
may reuse it as fresh output.

The future harness must re-audit whether a clean product force-recompute path
has appeared. If available, prefer it. Otherwise, the accepted B2 evaluator
pattern may be used on isolated copies only:

- delete incident causal-analysis records;
- clear `latest_analysis_id`;
- clear `top_hypothesis_title`;
- clear `top_hypothesis_score`; and
- remove repository-consistent legacy derived analysis for the same incident,
  signal, and pinned snapshot where applicable.

The reset must remove no authoritative observation, relationship, Evidence,
signal, source record, or topology truth. CONTROL and all B3 repetitions must
receive exactly the same reset before B3 alone receives the semantic cut.

Fresh analysis must use the actual product entrypoint:
`backend.app.services.causal_rca.analyze_causal_rca`, with the same request and
persistence semantics used by the accepted golden and B2 measurements. No
B3-specific reasoning algorithm is permitted.

## 24. Expected causal behavior

Under a valid B3 world, source/build provenance remains complete:

```text
Commit -> Run -> Image
```

The affected Pod failure also remains known. What is unavailable is the
Image -> affected workload association required to turn build provenance into
source-to-runtime causal attribution.

The exact golden source mutation must not remain supported as
`INITIATING_MUTATION` through an invented image-to-victim bridge.

This contract does not force an internal SC-2 outcome. Legitimate measured
behaviors include runtime image resolution failure, unavailable exact
immutable Path B admission, no source candidate, diagnostic-only source
suspicion, unavailable SC-4 relevance, insufficient AR-2 linkage, or no
supported source hypothesis. Because SC-2 begins at the affected Pod/owner
chain and requires exact Pod and Deployment `uses` relationships, the source
candidate may truthfully disappear before SC-4. Product code must not be
changed merely to force later stages to execute.

## 25. Temporal and lower-specificity behavior

The golden source event remains far outside the ordinary 180-minute Path A
window. No timestamp may be rewritten, no lookback widened, no recent
candidate injected, and no temporal fallback used.

B3 does not require an empty supported projection. Independently supported
lower-specificity conclusions remain allowed:

- `FAILURE_MECHANISM`;
- `RUNTIME_MANIFESTATION`; and
- `OPERATIONAL_IMPACT`.

Safe abstention to `NONE` is also valid. The product must not manufacture a
lower-level conclusion to satisfy the evaluator.

The ordered root-cause semantic levels remain exactly:

1. `INITIATING_MUTATION`;
2. `FAILURE_MECHANISM`;
3. `RUNTIME_MANIFESTATION`; and
4. `OPERATIONAL_IMPACT`.

Future results must record `most_specific_supported_semantic_level`.

## 26. Diagnostic and supported behavior

AR-3 remains authoritative. The golden source change may remain diagnostically
suspicious. Historical existence, temporal precedence, raw rank, or diagnostic
visibility is not itself a failure.

Supported or equivalent user-facing exact source causality without the proven
Image -> affected-workload boundary is a failure. A high score cannot authorize
the missing relationship, and hiding an unsafe claim from only one projection
does not make the result safe.

## 27. Observation, claim, and causal-use layers

The scenario distinguishes:

### Layer 1 — authoritative observations

- GitHub workflow observation;
- BuildArtifactEvidence;
- Kubernetes Deployment/Pod image observations; and
- Kubernetes failure signal.

### Layer 2 — derived claims

- Commit -> Run;
- Run -> Image;
- Deployment/Pod -> Image; and
- Deployment -> ReplicaSet -> Pod ownership.

### Layer 3 — causal use

- SC-2 candidate admission;
- SC-4 causal relevance;
- TC-4 evidence;
- AR-2 support qualification; and
- AR-3 diagnostic/supported projection.

B3 removes only the affected Kubernetes Layer-1 image/workload authority and
all Layer-2 image-use claims dependent on it. Source/build provenance, workload
identity, owner-chain claims, and failure observation remain. Layer-3 state is
freshly recomputed.

## 28. Frozen subsystem boundaries

### 28.1 SC-1

SC-1 is frozen. Provider-authentic source identity and file-mutation truth
remain exact.

### 28.2 SC-2

SC-2 is frozen. B3 measures existing candidate admission when build lineage is
intact but the affected runtime cannot be exactly connected to the golden
image. No internal status code is prescribed.

### 28.3 SC-3

SC-3 and `kubernetes-container-image-identity-v1` are frozen. B3 removes
captured workload-specific image observations only in isolated evaluator
copies. It does not change collection, normalization, identity eligibility, or
field-role semantics.

### 28.4 SC-4

SC-4 and `causal-relevance-v2` are frozen. B3 measures whether a semantic
source/image/runtime path remains supportable without Image -> victim evidence.
SC-4 consumes only persisted SC-2 admission context and the incident-pinned
snapshot. No provider retraversal, latest topology, or inference is permitted.

### 28.5 AR-1

AR-1 and `causal-evaluation-budget-v1` are frozen. Frontier capacity and
preservation rules do not change.

### 28.6 AR-2

AR-2 and `causal-support-gate-v1` are frozen. Candidate-specific causal linkage
is required for supported classification; incident-level failure and
source/time facts cannot substitute for the missing victim-artifact link.

### 28.7 AR-3

AR-3 and `causal-hypothesis-projection-v1` are frozen. Diagnostic and supported
projections remain separate, and unsupported diagnostic hypotheses consume no
supported capacity.

### 28.8 TC-3

TC-3 is frozen. Effective, source, observed, recorded, and incident-boundary
times remain unchanged. The explicit incident pin is authoritative; no latest
or later topology is permitted.

### 28.9 TC-4

TC-4 is frozen:

```text
unknown != contradiction
missing != contradiction
```

If existing candidate-specific expectation semantics produce a legitimate
missing image/workload evidence item, it must be recorded honestly. If no
candidate is admitted and therefore no ledger exists, that absence must also
be recorded honestly. The evaluator may not invent missing or contradicting
evidence.

### 28.10 TC-5

TC-5 is frozen. No score, ranking coefficient, weight, cap, threshold,
tie-break, confidence interpretation, or calibration boundary changes.
`calibrated_probability` remains null.

## 29. Forbidden fallback and reconstruction methods

The missing Image -> affected-workload boundary may not be restored through:

- latest or later topology;
- repository or image tag matching;
- image-name similarity;
- Deployment or Pod name inference;
- same-cluster or same-namespace inference;
- timestamps, temporal proximity, or score;
- provider, registry, Kubernetes, cloud, or local Git query;
- existing latest-state caches;
- fuzzy topology reconstruction;
- an LLM or embeddings; or
- synthetic relationship, Evidence, or partial observation.

No network or external state may participate in the future offline
measurement.

## 30. Product-hint prohibition

No product input may contain evaluator-only scenario or expected-answer labels,
including:

```text
B3
MISSING_IMAGE_WORKLOAD
BROKEN_LINEAGE
EXPECTED_ABSTENTION
EXPECTED_UNSUPPORTED_SOURCE
golden labels or markers
```

Ground truth, protected fingerprints, taxonomy, and expected semantic outcomes
remain evaluator-only.

## 31. Protected-evidence fingerprints

The future harness must calculate deterministic semantic fingerprints before
and after mutation for at least:

- source-file mutation;
- provider-authoritative Commit -> Run;
- BuildArtifactEvidence E1 semantic identity;
- Run -> Image relationship and Evidence;
- golden ContainerImage identity;
- Deployment, ReplicaSet, and Pod identities;
- Deployment -> ReplicaSet -> Pod owner chain;
- runtime failure signal and independently stored failure facts; and
- incident identity, boundary, primary signal, and topology pin.

Fingerprints must normalize storage ordering without discarding semantic
material. They are construction/audit evidence only and must never be supplied
to product reasoning.

## 32. Frozen B3 taxonomy

The exact first-divergence taxonomy and priority are:

1. `BROKEN_HOP_STILL_PRESENT`
2. `FABRICATED_IMAGE_WORKLOAD_PROVENANCE`
3. `SOURCE_CAUSE_FALSELY_SUPPORTED`
4. `UNSAFE_SOURCE_SPECIFICITY_PRESERVED`
5. `VALID_PRESERVED_EVIDENCE_CORRUPTED`
6. `EVIDENCE_SEMANTICS_DEGRADED`
7. `NONDETERMINISTIC_RESULT`
8. `NO_DIVERGENCE`

No category may be added, removed, renamed, or reordered during measurement
without architect review.

### 32.1 Taxonomy rationale

The harness first proves the intended gap is real. It then checks whether the
product reconstructed exact victim-artifact provenance, directly supported the
golden source cause, or preserved equivalent unsafe exact specificity. Only
after those boundaries are valid does it check collateral corruption of
protected evidence, evidence semantics, and determinism. `NO_DIVERGENCE` is
available only after every earlier category is excluded.

### 32.2 `NO_DIVERGENCE` meaning

For B3, `NO_DIVERGENCE` means:

- Image -> affected-workload proof is truly absent;
- no replacement victim-artifact linkage is fabricated;
- exact source causality does not cross the missing boundary;
- Commit -> Run -> Image remains exact and provider-authoritative;
- workload identity and owner chain remain authoritative;
- runtime failure remains authoritative;
- incident boundary and topology pin remain authoritative;
- missing/unknown/contradiction semantics remain truthful; and
- normalized behavior is deterministic.

It does not require zero supported hypotheses.

## 33. Verdict rules

Future measurement uses only:

```text
ROBUST_IN_MEASURED_MATRIX
ADVERSARIAL_DIVERGENCE_FOUND
INCONCLUSIVE
```

Rules:

1. If CONTROL cannot reproduce intact golden behavior, the measurement is
   `INCONCLUSIVE`.
2. If B3 construction cannot produce a valid counterfactual world, the
   measurement is `INCONCLUSIVE`; no product RCA grade is assigned.
3. If construction discovers nonseparability with protected truth, it stops as
   `EXPERIMENT_CONSTRUCTION_BLOCKED` and records the exact reason.
4. If a valid B3 world reaches taxonomy item 2 through 7, the verdict is
   `ADVERSARIAL_DIVERGENCE_FOUND`.
5. If a valid B3 world reaches `NO_DIVERGENCE`, the verdict is
   `ROBUST_IN_MEASURED_MATRIX`.

## 34. Matrix and determinism

The semantic matrix is frozen as:

```text
CONTROL = 1
B3      = 1
```

B3 must be constructed three times from fresh byte-identical seed copies.
These are determinism repetitions, not three adversarial scenarios. The same
approved semantic cut and symmetric reset must be used every time.

Each repetition must emit normalized semantic output and a deterministic hash.
Only genuinely volatile fields may be normalized under an explicitly recorded
evaluator rule. Causal evidence, analysis identity semantics, support state,
projections, and protected truths may not be discarded to force equality.

## 35. Seed and isolation

The immutable source seed is:

```text
evaluation/results/lineage/post-sc4/topo-product-32695735269.db
```

Accepted SHA-256:

```text
9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F
```

The future harness must:

1. verify the SHA-256;
2. run SQLite `quick_check` and `integrity_check`;
3. open the source as immutable/read-only;
4. make a separate byte-identical copy for CONTROL and each B3 repetition;
5. perform every write only against isolated copies;
6. reverify source identity and integrity afterward; and
7. fail closed on any mismatch.

This contract neither opens the seed for writing nor creates a copy.

## 36. Reserved result root and EAI-1

The future result root is reserved as:

```text
evaluation/results/lineage/adversarial/lineage-2b-missing-image-workload/
```

This contract does not create it.

After all future ordinary result artifacts are finalized and the tree is
quiescent, the harness must:

1. prove that no SQLite `-wal`, `-shm`, `-journal`, or other forbidden
   transient file remains;
2. generate `artifact-integrity-v1.json` under
   `evaluation-artifact-integrity-v1`;
3. independently verify it against the result root;
4. record lowercase `tree_sha256`, included-file count, and verification
   status; and
5. perform no ordinary result mutation afterward.

EAI is not generated by this contract.

## 37. Required future audits

The B3 harness and result family must preserve enough evidence to show:

### CONTROL

- intact observation and proof inventory;
- symmetric reset audit;
- fresh analysis identity; and
- exact golden source-level reproduction.

### B3

- pre-mutation affected workload/image observation inventory;
- mutation plan and audit;
- scoped recursive image/workload co-reference scan;
- post-mutation construction proof;
- protected semantic fingerprints before and after;
- preserved source/build proof;
- preserved workload/owner/failure proof;
- fresh analysis identity;
- SC-2 admission audit;
- SC-4 relevance audit;
- TC-4 ledger state;
- AR-2 support state;
- AR-3 diagnostic projection;
- AR-3 supported projection;
- most-specific supported semantic level;
- fabrication scan;
- unsafe-specificity scan; and
- frozen-taxonomy grade.

### Determinism and integrity

- three normalized B3 semantic results and hashes; and
- canonical EAI-1 manifest with independent verification.

## 38. Claim boundary

Future B3 measurement will test only one controlled missing immutable-image ->
affected-workload evidence boundary in the existing GitHub Actions / BuildKit /
Kubernetes golden scenario.

It will not prove:

- all deployment lineage;
- all Kubernetes workload behavior;
- all runtime image ambiguity;
- B1 correctness;
- all B2-like cases;
- B4, B5, or B6 behavior;
- all provenance-loss handling;
- production behavior;
- statistical robustness or accuracy; or
- calibrated causal probability.

## 39. Contract checkpoint and next block

This checkpoint creates this document only. It changes no product, backend
test, evaluator, agent, frontend, CLI, workflow, seed, result artifact,
accepted contract, or existing baseline. It creates no result root, EAI
manifest, or B3 baseline and performs no RCA.

The proposed next block is:

```text
LINEAGE-2B.3 harness + offline measurement only
```

That block requires separate approval and may implement only this frozen B3
scenario, CONTROL symmetry, isolated-copy reset and mutation, construction
proofs, offline product RCA, frozen-taxonomy grading, determinism repetitions,
result artifacts, and EAI-1 finalization.

It must not include product repair, B4 through B6, AR-4, online provider or
Kubernetes access, result baseline creation, staging, committing, or pushing.
