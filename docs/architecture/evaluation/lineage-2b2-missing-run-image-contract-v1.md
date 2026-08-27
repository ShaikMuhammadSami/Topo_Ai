# LINEAGE-2B.2-0 — Missing Actions Run -> Immutable Image Provenance Contract v1

Status: **DOCUMENTATION / EXECUTABLE SCENARIO CONTRACT ONLY**

Date: 2026-08-27

Contract branch: `evaluation/lineage-2b2-missing-run-image-contract-v1`

Accepted repository commit at contract freeze:
`1d8ee09a7cae48ff4e23e8639dd1c7990ff294e3`

Accepted repository summary:
`1d8ee09 docs(evaluation): audit broken lineage representability (#52)`

Family: **LINEAGE-2B — Broken / Incomplete Immutable Lineage Robustness v1**

Scenario: **LINEAGE-2B.2 — Missing Actions Run -> Immutable Image Provenance**

## 1. Purpose and boundary

This checkpoint freezes the executable scenario contract for measuring whether
TopoAI safely reduces causal specificity when the exact provider-authenticated
Actions Run -> immutable image provenance boundary is absent.

This checkpoint does not construct or measure B2. It does not mutate the
accepted seed, remove evidence, reset analysis, run RCA, create a result root,
generate an EAI manifest, create a baseline, or modify product or evaluator
code.

The only authorized output is this contract. The next block, if separately
approved, may implement the B2 harness and perform offline measurement under
this frozen contract.

## 2. Accepted dependencies

### 2.1 LINEAGE-1

LINEAGE-1 remains the accepted provider-backed source-to-runtime proof for one
controlled Kubernetes scenario. Its accepted result was `PROVEN` with
`NO_DIVERGENCE` at semantic level `INITIATING_MUTATION`.

### 2.2 LINEAGE-2A

LINEAGE-2A remains **ACCEPTED / CLOSED**:

```text
ROBUST_IN_MEASURED_MATRIX
NO_DIVERGENCE
```

This contract does not reopen the 16-scenario distractor matrix or authorize
AR-4.

### 2.3 EAI-1

EAI-1 remains accepted under `evaluation-artifact-integrity-v1`. A future B2
result family must be finalized and independently verified under that
contract before any baseline can be accepted.

### 2.4 LINEAGE-2B.1

LINEAGE-2B.1 remains:

```text
EXPERIMENT_CONSTRUCTION_BLOCKED
reason: evidence_model_nonseparable
measurement: NOT EXECUTED
product RCA: NOT MEASURED
```

The earlier B1 construction proposal cannot preserve Run -> Image after
removing its sole atomic authority. This B2 contract does not reinterpret or
execute B1.

### 2.5 LINEAGE-2B-A0

The accepted representability audit found B2 independently representable and
constructible from the current seed. This contract depends on that finding:

- provider-native workflow-run observation independently proves Commit -> Run;
- atomic `BuildArtifactEvidence` E1 proves Run -> Image;
- Kubernetes snapshot observations independently prove Image -> workload; and
- the runtime failure signal independently proves the affected Pod failure.

## 3. Permanent counterfactual doctrine

The following doctrine is frozen:

> COUNTERFACTUAL EVALUATION MUST RESPECT THE ATOMICITY OF AUTHORITATIVE
> OBSERVATIONS; A CONCEPTUAL GRAPH EDGE IS NOT AUTOMATICALLY AN INDEPENDENTLY
> MUTABLE EVIDENCE FACT.

Also frozen:

> ADVERSARIAL SCENARIOS MAY REMOVE ONLY INDEPENDENTLY REPRESENTABLE TRUTHS.

The evaluator must not fabricate separability, replacement authority, or
provider facts that the accepted evidence model and seed do not contain.

## 4. Governing B2 invariant

The B2 invariant is frozen exactly as:

> EXACT SOURCE-TO-RUNTIME CAUSAL ATTRIBUTION MUST NOT CROSS AN UNPROVEN
> RUN -> IMAGE PROVENANCE BOUNDARY.

Equivalently:

```text
Commit -> Run

and

Image -> affected workload

do not imply

Run -> Image
```

No transitive causal bridge may be invented across missing provider build
provenance. Exact identities on either side of the gap do not prove the
missing relationship.

## 5. Intact and broken chains

### 5.1 Intact golden chain

```text
Repository
    ->
Commit
    ->
Actions Run
    ->
Immutable Image
    ->
Deployment / Pod
    ->
Runtime Failure
```

### 5.2 B2 broken chain

```text
Repository
    ->
Commit
    ->
Actions Run

    X

Immutable Image
    ->
Deployment / Pod
    ->
Runtime Failure
```

The one missing authoritative boundary is:

```text
GitHub Actions run: 32695735269
attempt: 1
    X
immutable image:
sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed
```

## 6. Frozen source and incident identities

| Dimension | Frozen identity |
|---|---|
| Repository | `1278498159 / ShaikMuhammadSami/Topo_Ai` |
| Failure commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Actions Run | `32695735269`, attempt `1` |
| Immutable image | `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Incident | `incident:docker-desktop:topo-eval-lineage-causal-32695735269:workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3` |
| Incident boundary | `2026-08-26T05:09:49Z` |
| Pinned snapshot | `snapshot:actions-enriched:20260826T051031Z:2d8416d3` |
| Affected Pod | `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168` |
| Failure signal | `signal:kubernetes-event:docker-desktop:ad733dcc-a026-424f-8984-6ed30108eec1` |

## 7. Authoritative truth that must remain

### 7.1 Source and commit

B2 must preserve repository identity, commit identity, and the complete
provider-authentic source-file mutation bundle. Removing production provenance
does not erase the historical fact that the source change exists.

### 7.2 Independently authoritative Commit -> Run

B2 must preserve the GitHub workflow-run provider observation and all exact
surfaces it independently supports:

- Run entity `github:api.github.com:workflow-run:32695735269`;
- `run_id=32695735269`;
- `run_attempt=1`;
- `head_sha=4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`;
- `GitCommit --triggers--> GitHubWorkflowRun` relationship
  `rel:ebaedc357f11b3e70170`; and
- provider evidence
  `evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b`.

The future harness must prove that these surfaces remain exact,
provider-authoritative, and semantically unchanged after the B2 cut. E1
repeats Commit -> Run, but E1 is not the only authority for that claim.

### 7.3 Canonical immutable image

B2 must preserve the ContainerImage entity:

```text
artifact:container-image:
sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed
```

The image identity may not be deleted, renamed, weakened, replaced, or
rewritten. B2 removes knowledge of its producer, not knowledge that the image
exists.

### 7.4 Independently authoritative Image -> workload

B2 must preserve the Kubernetes requested/runtime image observations in the
incident-pinned snapshot, including:

- Deployment -> Image `uses` relationship `rel:496906e3e345259910c9`;
- Pod -> Image `uses` relationship `rel:0548ac3e949f44b3569c`;
- their exact requested/runtime SC-3 image identity;
- the Deployment, ReplicaSet, and Pod entities;
- Deployment -> ReplicaSet ownership relationship
  `rel:57555e411f2db29864c2`;
- ReplicaSet -> Pod ownership/runs relationship
  `rel:9c8db862d53bac71327f`; and
- the immutable incident topology pin.

The image still exists and the affected workload still used it. B2 removes
provider build provenance, not runtime artifact identity or use.

### 7.5 Independently authoritative runtime failure

B2 must preserve the BackOff/CrashLoopBackOff signal, affected Pod identity,
incident identity and boundary, primary signal association, topology pin, and
runtime-failure evidence. The failure signal contains no Run -> Image
authority and therefore survives the B2 cut independently.

## 8. Authoritative truth that must be removed

The future B2 mutation must remove complete authoritative proof that GitHub
Actions Run `32695735269`, attempt `1`, produced the golden immutable image.

### 8.1 Atomic E1 observation

The sole provider-authentic Run -> Image authority in the accepted seed is:

```text
build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb
```

E1 atomically contains the commit, run/attempt, image, provider artifact,
artifact digest, build-record digest, and builder identity. A future valid B2
copy must remove E1 as one authoritative observation. It must not null fields,
change identities, relabel the exact record as incomplete, or create a
replacement observation.

Removing E1 is permissible only because Commit -> Run has independent
workflow-run authority. No independent provider observation remains for
Run -> Image.

### 8.2 Derived Run -> Image proof surfaces

Removing E1 alone is insufficient. Every derived or cached surface solely
dependent on E1 must also be removed or reset, including:

- Run `--produces-->` Image relationship `rel:63f5cd5dfce59d148ae5`;
- associated provider evidence
  `evidence:github-actions-build:c9b6d53cf66facfb444c8ae0`;
- `metadata.github_actions_build_artifact_lineage` claim-specific counters;
- persisted build-artifact lineage context that reconstructs the exact run,
  attempt, and image association;
- exact-digest provider lookup results linking this Run to this Image; and
- stale causal-analysis/admission/relevance/projection state asserting the
  intact path.

The future implementation must audit the then-current persisted schema before
mutation. The IDs above identify accepted-seed surfaces, but the semantic
requirement is complete removal of authoritative and stale derived Run ->
Image proof even if storage details later change.

Deleting only the `produces` edge is invalid because E1 would still authorize
the claim. Deleting only E1 is invalid if its derived edge, Evidence record,
metadata, or cached reasoning remains product-visible authority.

## 9. Observation, claim, and causal-use layers

The scenario preserves three separate layers.

### Layer 1 — authoritative observation

```text
GitHub workflow-run observation
    -> proves Commit -> Run

BuildArtifactEvidence E1
    -> proves Run -> Image

Kubernetes snapshot observations
    -> prove Image -> affected workload

Kubernetes failure signal
    -> proves affected runtime failure
```

### Layer 2 — derived provenance claims

```text
Commit --triggers--> Run
Run --produces--> Image
Deployment/Pod --uses--> Image
```

### Layer 3 — causal use

```text
SC-2 admission
SC-4 relevance
TC-4 evidence
AR-2 support
AR-3 projection
```

B2 removes the E1 Layer-1 authority and every Layer-2 claim solely dependent
on it. Layer-3 output must be freshly recomputed and may not resurrect the
removed authority.

## 10. CONTROL and B2 semantics

### 10.1 CONTROL

CONTROL uses an isolated byte-identical copy of the accepted seed, performs
the same derived-state reset as B2, and runs fresh recomputation without any
provenance mutation.

Expected CONTROL behavior is:

- full exact immutable lineage is reproduced;
- the golden source candidate is admitted through exact immutable lineage;
- the exact source mutation is supported at `INITIATING_MUTATION`; and
- downstream evidence remains intact.

If CONTROL cannot reproduce intact golden behavior, the measurement is
`INCONCLUSIVE`.

### 10.2 B2

B2 starts from a separate byte-identical seed copy, performs the identical
derived-state reset, and then applies only the approved authoritative B2 cut.
CONTROL and B2 may differ only by that cut and its necessary internal
consistency cleanup.

The expected B2 world knows Commit -> Run and Image -> affected runtime, but
does not know Run -> Image.

## 11. Derived-analysis reset contract

The accepted seed contains historical causal analysis
`causal-analysis:76c9b683e95e2f2fd599677122f2ebae`. Neither CONTROL nor B2
may reuse it as a fresh result.

Both copies must undergo an identical fresh-analysis boundary covering only
derived reasoning state, including repository-consistent equivalents of:

- `CausalAnalysisRecord`;
- lineage candidate-admission audit;
- candidate selection audit;
- SC-4 relevance audit and lineage bridge;
- TC-4 ledger embedded in prior analysis;
- AR-2 support qualification;
- AR-3 diagnostic and supported projections; and
- incident-level cached analysis references.

The future harness must audit and freeze the exact reset fields during
implementation. It should prefer an existing clean force-recompute path. If
none exists, it may surgically clear only derived analysis state on isolated
copies. It must not delete authoritative evidence merely to force
recomputation and must not modify product code.

Reset symmetry is mandatory: CONTROL and B2 receive the same reset before B2
alone receives the approved provenance cut.

## 12. Construction preconditions

Before RCA is allowed, the future harness must prove the following from
persisted product-visible truth.

### 12.1 Must remain present

1. exact source revision;
2. exact source-file mutation;
3. Actions Run entity;
4. exact workflow-run `head_sha`;
5. exact Commit -> Run relationship;
6. provider evidence for Commit -> Run;
7. canonical immutable ContainerImage entity;
8. Deployment, ReplicaSet, and Pod identities;
9. exact Deployment/Pod -> Image use authority;
10. incident identity;
11. incident boundary;
12. incident-pinned topology;
13. runtime failure signal; and
14. Deployment -> ReplicaSet -> Pod owner chain.

### 12.2 Must be absent

15. BuildArtifactEvidence E1;
16. exact Run -> Image `produces` relationship;
17. Run -> Image provider Evidence record;
18. build-lineage metadata capable of reconstructing exact Run -> Image;
19. exact-digest provider lookup result linking this Run to this Image;
20. stale persisted lineage path/admission/relevance state from prior RCA;
21. stale supported or diagnostic projections from prior RCA; and
22. any alternative authoritative Run -> Image proof.

## 13. Broken-hop validation and construction blocker

The scenario is valid only when all four statements are proven:

```text
Commit -> Run:       PRESENT / exact / provider-authoritative
Run -> Image:        ABSENT
Image -> workload:   PRESENT / exact
Runtime failure:     PRESENT
```

If Run -> Image survives through any authoritative observation, topology
claim, Evidence object, build-lineage metadata, exact-digest lookup, or stale
analysis, the scenario is invalid. RCA must not run and no causal grade may be
assigned.

If implementation discovers that removing E1 and its complete derived cut
truthfully destroys another required preserved fact not identified by the A0
audit, it must stop with:

```text
EXPERIMENT_CONSTRUCTION_BLOCKED
```

The harness must not widen the mutation or synthesize replacement authority.

## 14. Product-hint prohibition

No product input may contain evaluator-only labels or expected answers such
as:

```text
B2
BROKEN_LINEAGE
MISSING_RUN_IMAGE
EXPECTED_ABSTENTION
EXPECTED_UNSUPPORTED_SOURCE
golden marker
```

Ground truth, scenario classification, protected-evidence fingerprints, and
expected semantic outcomes remain evaluator-only. No LLM, embedding, local
Git query, provider query, or external state may supply the missing hop.

## 15. Expected causal behavior

Under a valid B2 world, exact source-to-runtime attribution through:

```text
Commit -> Run -> Image -> runtime
```

is incomplete. The exact source mutation must not remain evidence-supported
as an `INITIATING_MUTATION` through that broken chain.

This contract does not freeze a particular internal failure branch. The A0
audit suggests `IMAGE_TO_RUN_MISSING` may occur, but measurement decides.
Acceptable internal outcomes include:

- no Path B admission for the source candidate;
- admission through another legitimate, independently evidenced basis;
- incomplete lineage context;
- unavailable SC-4 bridge;
- unsupported candidate relevance;
- a diagnostic-only source hypothesis; or
- absence of the source hypothesis from supported projection.

No implementation or grading assumption may force one of those internal
representations when the semantic outcome is correct.

## 16. Temporal and lower-specificity behavior

The golden source event is about `2827.77` minutes before the incident and is
far outside the ordinary 180-minute Path A window. The future harness must not
widen the lookback, rewrite timestamps, create a recent source candidate, or
use temporal fallback.

B2 does not require `supported_projection=[]`. TopoAI may retain an
independently evidenced lower-specificity conclusion at:

- `FAILURE_MECHANISM`;
- `RUNTIME_MANIFESTATION`; or
- `OPERATIONAL_IMPACT`.

Safe complete abstention is also valid. The product must not be modified to
force a lower-level answer.

## 17. Root-cause semantic levels

The four semantic levels remain ordered and distinct:

1. `INITIATING_MUTATION`;
2. `FAILURE_MECHANISM`;
3. `RUNTIME_MANIFESTATION`; and
4. `OPERATIONAL_IMPACT`.

Future results must record `most_specific_supported_semantic_level`. In B2,
the exact source mutation tied to the removed Run -> Image authority is
forbidden from supported `INITIATING_MUTATION` presentation.

## 18. Diagnostic and supported behavior

AR-3 remains authoritative. The exact source mutation may remain visible in
the diagnostic projection. Historical existence, temporal precedence, raw
rank, and diagnostic suspicion do not constitute causal support.

The supported projection must not present the exact source mutation as causal
without candidate-specific evidence sufficient under AR-2. A high diagnostic
score cannot cross the missing provenance boundary.

Equivalent exact source attribution on another persisted or user-facing
causal surface is also forbidden. Safety is not achieved by hiding an unsafe
claim from only one projection.

## 19. Frozen subsystem boundaries

### 19.1 SC-1

SC-1 source identity and source-file mutation evidence remain exact. B2 does
not alter source truth.

### 19.2 SC-2

`causal-candidate-admission-v2` is unchanged. B2 measures existing SC-2
behavior when the affected runtime has an exact immutable image but exact
producer lookup no longer establishes its Run -> Image origin. The contract
does not prescribe an internal status code.

### 19.3 SC-3

`kubernetes-container-image-identity-v1` is unchanged. Requested image,
runtime-status image, runtime image ID, full immutable digest, container name,
and workload/image joins remain exact.

### 19.4 SC-4

`causal-relevance-v2` is unchanged. B2 measures whether the exact immutable
lineage bridge becomes incomplete or unavailable when provider Run -> Image
authority is absent. SC-4 may not consume stale lineage context, re-query a
provider, use latest topology, or infer the missing producer.

### 19.5 AR-1

`causal-evaluation-budget-v1` is unchanged. There is no frontier, budget,
capacity, or preservation-rule change.

### 19.6 AR-2

`causal-support-gate-v1` is unchanged. Incident-level failure evidence and
source/time evidence cannot substitute for missing candidate-specific
Run -> Image linkage.

### 19.7 AR-3

`causal-hypothesis-projection-v1` is unchanged. Diagnostic and supported
projections remain separate, and only support-qualified hypotheses may enter
the supported projection.

### 19.8 TC-3

All effective, source, observed, recorded, and incident-boundary times remain
unchanged. The incident pin remains authoritative. No latest or later topology
fallback is allowed.

### 19.9 TC-4

Missing Run -> Image proof is not contradiction:

```text
unknown != contradiction
missing != contradiction
```

If an existing expectation basis produces a missing evidence item, it should
be recorded truthfully. The evaluator must not inject a fake missing claim,
invent an expectation basis, or alter TC-4 semantics.

### 19.10 TC-5

No score, coefficient, ranking weight, tie-break, confidence interpretation,
or calibration boundary changes. `calibrated_probability` remains null. A
high source diagnostic score cannot authorize a missing provenance hop.

## 20. Historical, image, topology, and policy freezes

B2 changes no timestamp, temporal lookback, image identity, topology pin,
relationship direction, topology traversal policy, candidate score, causal
score, cap, support threshold, or semantic-level definition.

The incident continues to use only
`snapshot:actions-enriched:20260826T051031Z:2d8416d3`. There is no latest
topology, provider, registry, Kubernetes, local Git, LLM, or external-network
fallback.

## 21. Downstream truth preservation

Future CONTROL/B2 comparison must prove these independent truths unchanged:

- repository and commit identity;
- exact provider-authoritative Commit -> Run;
- Run entity and attempt;
- canonical immutable image identity;
- Deployment, ReplicaSet, and Pod identity;
- exact Deployment/Pod -> Image use;
- runtime failure and affected Pod;
- incident boundary and topology pin;
- Deployment -> ReplicaSet -> Pod owner chain;
- source mutation evidence;
- unrelated topology entities, relationships, and evidence; and
- all frozen SC, AR, TC, score, and temporal policies.

Corrupting valid downstream or upstream truth is an adversarial failure, not
an acceptable implementation side effect.

## 22. Protected-evidence fingerprints

The future harness must calculate evaluator-only deterministic fingerprints
before and after the B2 mutation for at least:

- Commit -> Run provider truth;
- Image -> Deployment/Pod truth;
- runtime failure;
- incident and topology pin; and
- Deployment -> ReplicaSet -> Pod owner chain.

Fingerprints must cover semantic material rather than storage ordering. They
are construction/audit evidence only and must never be supplied to product
reasoning.

## 23. Frozen B2 taxonomy

The exact first-divergence taxonomy and priority are:

1. `BROKEN_HOP_STILL_PRESENT`
2. `FABRICATED_RUN_IMAGE_PROVENANCE`
3. `SOURCE_CAUSE_FALSELY_SUPPORTED`
4. `UNSAFE_SOURCE_SPECIFICITY_PRESERVED`
5. `VALID_PRESERVED_EVIDENCE_CORRUPTED`
6. `EVIDENCE_SEMANTICS_DEGRADED`
7. `NONDETERMINISTIC_RESULT`
8. `NO_DIVERGENCE`

No category may be added, removed, renamed, or reordered during measurement
without architect review.

### 23.1 Taxonomy rationale

The harness first validates construction. It next detects fabricated
provenance, direct false source support, and equivalent unsafe source
specificity. Only after the causal boundary is valid does it grade collateral
evidence damage, missing/unknown/contradiction semantics, and determinism.
`NO_DIVERGENCE` is available only after every earlier condition is excluded.

### 23.2 `NO_DIVERGENCE` meaning

For B2, `NO_DIVERGENCE` means:

- exact Run -> Image authority is truly absent;
- no replacement provenance is fabricated;
- exact source `INITIATING_MUTATION` support does not cross the gap;
- Commit -> Run remains exact and provider-authoritative;
- Image -> workload remains exact;
- runtime failure remains exact;
- evidence semantics remain truthful; and
- normalized behavior is deterministic.

It does not mean that TopoAI must return no supported hypotheses.

## 24. Overall verdict rules

Future measurement uses only:

```text
ROBUST_IN_MEASURED_MATRIX
ADVERSARIAL_DIVERGENCE_FOUND
INCONCLUSIVE
```

Rules:

1. If CONTROL cannot reproduce the intact golden behavior, the result is
   `INCONCLUSIVE`.
2. If the B2 mutation does not produce a valid broken-hop world, the result is
   `INCONCLUSIVE`; do not grade product RCA.
3. If valid B2 reaches taxonomy item 2 through 7, the verdict is
   `ADVERSARIAL_DIVERGENCE_FOUND`.
4. If valid B2 reaches `NO_DIVERGENCE`, the verdict is
   `ROBUST_IN_MEASURED_MATRIX`.
5. If construction discovers nonseparability beyond the accepted A0 finding,
   stop as `EXPERIMENT_CONSTRUCTION_BLOCKED`; do not reinterpret it as a
   product causal result.

## 25. Matrix and determinism

The semantic matrix is frozen as:

```text
CONTROL = 1
B2      = 1
```

The future harness must construct B2 from fresh byte-identical seed copies
three times. Those are determinism repetitions, not three distinct
adversarial scenarios. No storage-order permutations or meaningless mutation
orders may inflate the matrix.

Each repetition must produce normalized semantic output and a deterministic
semantic hash. Differences in fresh opaque record IDs must be normalized only
under an explicitly frozen evaluator rule; semantic evidence must never be
discarded to force equality.

## 26. Seed and isolation

The immutable source seed is:

```text
evaluation/results/lineage/post-sc4/topo-product-32695735269.db
```

Accepted SHA-256:

```text
9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F
```

The future harness must:

1. verify SHA-256, SQLite `quick_check`, and `integrity_check`;
2. open the source as immutable/read-only;
3. create a separate byte-identical copy for CONTROL, B2, and each
   determinism repetition;
4. perform writes only on isolated copies;
5. reverify the source seed after execution; and
6. fail closed on any source identity or integrity mismatch.

The seed is not mutated by this contract.

## 27. Future result root and EAI-1

The reserved future result root is:

```text
evaluation/results/lineage/adversarial/lineage-2b-missing-run-image/
```

This contract does not create it.

After a future result family is finalized and quiescent, the harness must:

1. ensure no SQLite `-wal`, `-shm`, `-journal`, or other EAI-forbidden
   transient file remains;
2. generate `artifact-integrity-v1.json` using
   `evaluation-artifact-integrity-v1`;
3. verify it through an independent result-root scan;
4. record contract version, lowercase `tree_sha256`, included-file count, and
   verification result; and
5. perform no result mutation after integrity generation.

EAI-1 finalization occurs only after all ordinary result artifacts exist.

## 28. Required future result audits

The future B2 result must preserve enough evaluator evidence to show:

### CONTROL

- intact proof inventory;
- derived-state reset and fresh recomputation proof; and
- source causal result.

### B2

- exact mutation plan and mutation audit;
- post-mutation proof inventory;
- protected evidence before/after;
- fresh analysis;
- SC-2 and SC-4 audits;
- TC-4 evidence ledger;
- AR-2 support audit;
- AR-3 diagnostic and supported projections;
- most-specific supported semantic level;
- fabrication scan; and
- frozen-taxonomy grade.

### Determinism

- normalized semantic outputs and hashes for all three B2 constructions.

### Integrity

- canonical EAI-1 manifest and independent verification result.

## 29. Fresh-analysis identity requirement

The future result must record:

- original persisted analysis identity;
- new CONTROL analysis identity; and
- new B2 analysis identity for each repetition.

Fresh results must not reuse the original source-supported analysis. If
existing product fingerprints or policies reuse an analysis despite altered
authoritative evidence, the harness must record that as stale-analysis
behavior and grade it under the frozen taxonomy. It must not work around the
behavior by modifying product code.

## 30. Claim boundary

B2 will test exactly one missing Actions Run -> immutable image
provider-provenance boundary in the frozen controlled
GitHub/BuildKit/Kubernetes scenario.

It will not prove:

- B1 or B3 behavior;
- all missing, incomplete, or ambiguous provenance behavior;
- multiple-build or multiple-provider behavior;
- all Kubernetes RCA;
- statistical robustness;
- calibrated causal probability;
- production concurrency; or
- generalized source-to-runtime correctness.

## 31. Next block and stop boundary

The proposed next block is:

```text
LINEAGE-2B.2 harness + offline measurement only
```

It requires separate approval. It may implement only the frozen B2 cut,
CONTROL symmetry, derived-state reset, construction proofs, offline fresh RCA,
taxonomy grading, determinism repetitions, result artifacts, and EAI-1
finalization.

It must not include product repair, B3, ambiguity experiments, AR-4, network
access, provider mutation, Kubernetes execution, or baseline creation.

This contract stops here.
