# LINEAGE-2B-A0 — Evidence Representability Audit v1

Status: **READ-ONLY ARCHITECTURE / EVIDENCE AUDIT**

Date: 2026-08-27

Audit branch: `evaluation/lineage-2b-representability-audit-v1`

Accepted repository commit at audit start:
`cdb1bcd972871e668dde84ef4009cbe8645234b6`

Accepted repository summary:
`cdb1bcd docs(evaluation): define broken lineage robustness contract (#51)`

## 1. Purpose and boundary

This checkpoint audits whether six proposed broken-lineage counterfactuals are
representable by TopoAI's current truth model and constructible from the
accepted LINEAGE seed. It does not measure causal behavior and does not infer
product robustness from construction feasibility.

This checkpoint does not mutate the seed, construct a scenario, run RCA,
create a result root, generate an EAI manifest, change a product or evaluator,
or authorize B2/B3 measurement.

The accepted LINEAGE-2B.1 finding is frozen:

```text
scenario: LINEAGE-2B.1 Commit -> Run missing
status: EXPERIMENT_CONSTRUCTION_BLOCKED
reason: evidence_model_nonseparable
measurement: NOT EXECUTED
product RCA: NOT MEASURED
```

The old B1 construction proposal in
`lineage-broken-immutable-lineage-v1.md` is not executable: deleting the
atomic build-evidence row and retaining its derived Run -> Image edge would
not preserve independent authority. This audit records that contradiction; it
does not edit the frozen contract.

LINEAGE-2A remains accepted and closed as
`ROBUST_IN_MEASURED_MATRIX / NO_DIVERGENCE`. EAI-1 remains the required
integrity contract for future result families, but it is not invoked here
because this audit creates no result family.

## 2. Permanent counterfactual-validity doctrine

The following doctrine is frozen:

> COUNTERFACTUAL EVALUATION MUST RESPECT THE ATOMICITY OF AUTHORITATIVE
> OBSERVATIONS; A CONCEPTUAL GRAPH EDGE IS NOT AUTOMATICALLY AN INDEPENDENTLY
> MUTABLE EVIDENCE FACT.

Also frozen:

> ADVERSARIAL SCENARIOS MAY REMOVE ONLY INDEPENDENTLY REPRESENTABLE TRUTHS.

And:

> THE EVALUATOR MUST NOT FABRICATE SEPARABILITY THAT THE AUTHORITATIVE SOURCE
> DID NOT PROVIDE.

Deleting an observation deletes every claim for which it is the sole
authority. Retaining a derived claim after deleting its sole authority is not
truth preservation. Relabeling an exact observation as incomplete does not
make its visible exact fields unknown.

## 3. Observation, claim, and causal-use layers

TopoAI must keep three meanings separate:

1. **Authoritative/canonical observation** — what an authenticated provider,
   collector, runtime sensor, or durable source actually reported and Topo
   retained.
2. **Derived provenance claim** — the graph relationship or identity claim
   supported by one or more observations.
3. **Causal use** — whether that claim may participate in SC-2 admission,
   SC-4 relevance, TC-4 evidence, AR-2 support qualification, and AR-3
   presentation.

One observation may support several claims. One claim may eventually have
several independent observations. The current V1 model does not contain a
generalized claim-to-observation binding store, and this audit does not add
one.

## 4. Construction-validity gate

Every future adversarial scenario must pass this stage before construction:

```text
SCENARIO INTENT
    -> EVIDENCE DEPENDENCY ANALYSIS
    -> COUNTERFACTUAL REPRESENTABILITY CHECK
       -> model can express the state without lying?
       -> current seed has independent authority for preserved truths?
    -> if both pass: scenario construction may be contracted
    -> otherwise: CONSTRUCTION_BLOCKED / DEFER / NEEDS_REAL_SEED
```

Useful construction-blocked reasons are:

- `evidence_model_nonseparable`;
- `seed_lacks_required_authoritative_observation`;
- `counterfactual_would_corrupt_preserved_truth`; and
- `counterfactual_requires_synthetic_authority`.

These are documentation taxonomy terms, not a new runtime enum.

### 4.1 Two mandatory questions

**Ontology/model representability** asks whether the current persisted truth
model can hold the intended state without a contradiction or fabricated fact.

**Current-seed constructibility** asks whether this frozen seed contains the
independent authoritative observations needed to make that representable
state through removal only. A model may support a shape that the seed cannot
truthfully instantiate.

## 5. Frozen seed and integrity

The seed was opened only through SQLite URI
`mode=ro&immutable=1`:

```text
evaluation/results/lineage/post-sc4/topo-product-32695735269.db
```

| Check | Result |
|---|---|
| Required SHA-256 | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |
| Observed SHA-256 | `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F` |
| SQLite `quick_check` | `ok` |
| SQLite `integrity_check` | `ok` |
| Mutation | none |

The incident is:

```text
incident:docker-desktop:topo-eval-lineage-causal-32695735269:
workload-lineage-causal-fixture:1afbac4ef76921c7aca2c3d3
```

It pins snapshot
`snapshot:actions-enriched:20260826T051031Z:2d8416d3`, names the affected Pod
`k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168`, and references
the durable Kubernetes BackOff signal. The signal records failure identity and
time but no image identity. This separation is material to B3.

## 6. Evidence dependency graph

### 6.1 GitHub workflow observation

```text
GitHub workflow-run API observation
    -> GitHubWorkflowRun entity
       properties.run_id / run_attempt / head_sha
    -> Commit --triggers--> Run
       evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b
    -> TC-2 observed Commit -> Run claim
```

`backend.app.services.github_actions_graph` owns this projection. Its Evidence
summary explicitly states that provider-native run metadata connects commits
and runs and that immutable artifact lineage requires separate build evidence.

### 6.2 GitHub Actions/BuildKit build observation

```text
BuildArtifactEvidence E1
  commit C + run/attempt R + immutable image I + provider artifact/build IDs
    -> backend.app.services.github_actions_artifact_lineage
    -> Run --produces--> Image
       evidence:github-actions-build:c9b6d53cf66facfb444c8ae0
    -> SC-2 exact-digest provider lookup
    -> exact immutable lineage admission
    -> SC-4 immutable-image relevance bridge
    -> TC-4 / AR-2 / AR-3 / RCA
```

E1 is
`build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb`.
`BuildArtifactEvidence`, its SQL row, its provider parser, and its immutable
repository fact all require the commit, run/attempt, image, artifact digest,
build-record digest, and builder identity together.

### 6.3 Kubernetes workload/image observation

```text
Pinned Kubernetes Deployment/Pod observations
    -> normalize_regular_container_images
    -> requested image + runtime status image + runtime imageID
    -> ContainerImage canonical entity
    -> Deployment --uses--> Image
    -> Pod --uses--> Image
    -> SC-2 runtime path
       Deployment --owns--> ReplicaSet --runs--> Pod
       plus both workload/image uses edges
    -> SC-4 reverse traversal Image -> affected Pod
    -> TC-4 artifact provenance / AR-2 support / RCA
```

`backend.app.services.container_image_identity` owns SC-3 field-role
normalization. `backend.app.services.container_image_graph` derives the image
entity and `uses` claims. The immutable incident pin, not latest topology, is
the only graph input.

### 6.4 Failure observation

```text
Kubernetes BackOff signal
    -> durable signal record
    -> incident + affected Pod + incident boundary + topology pin
    -> TC-4 runtime_failure evidence
```

This signal is independent of the Kubernetes image-use projection. Removing
image-use evidence need not erase the fact that the Pod failed.

## 7. B1–B6 feasibility table

| Scenario | Target fact | Authoritative observation source(s) | Derived claims | Other facts sharing authority | Model independently representable? | Current seed constructible? | Preserved truths endangered | Exact blocker / limitation | Synthetic authority required? | Disposition |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | Commit C -> Run R missing | Atomic `BuildArtifactEvidence` plus workflow-run observation | `triggers`, `produces`, SC-2 path | E1 also solely authorizes Run R -> Image I | **NO** for the current provider-evidence path | **NO** | Run -> Image and provider artifact/build truth | `evidence_model_nonseparable` | **YES** if Run -> Image were retained after E1 removal | **CONSTRUCTION_BLOCKED** |
| B2 | Run R -> Image I missing | E1 is Run/Image authority; independent workflow-run observation authorizes Commit/Run | `produces`, SC-2 provider path | E1 also contains Commit/Run, but that claim has independent workflow-run authority | **YES** | **YES** | Commit -> Run if its independent evidence were accidentally removed; image/workload if image entity were deleted | Must remove E1 and every derived Run/Image surface, not only the edge | **NO** | **EXECUTABLE; selected next contract** |
| B3 | Image I -> affected workload missing | Pinned Deployment/Pod image fields and Kubernetes SC-3 observations | two `uses` edges, image evidence, SC-2 runtime path | Image entity is also the target of preserved Run -> Image | **YES** | **YES** | Pod failure, ownership, incident/pin, and Run -> Image if the image entity were removed | Requires a complete multi-surface cut; edge-only deletion is stale | **NO** | **DEFER; valid fallback after B2** |
| B4 | Commit -> Run ambiguous | Workflow-run `head_sha`; E1 repeats the binding | multiple `triggers` claims would express ambiguity | GitHub V1 supplies one head SHA per run/attempt | **CONDITIONAL** at generic graph-claim layer; not produced by the current provider invariant | **NO** | Provider authenticity | Seed has one commit and one run; a competitor would be fabricated | **YES** for this seed | **DEFER** |
| B5 | Run -> Image ambiguous | Provider build observations | multiple exact `produces` claims | One run may have multiple real outputs; one digest may have multiple real producers | **YES** for real multiplicity; causal ambiguity must be defined separately | **NO** | Provider/build identity | Seed has one build observation and one image; aliases or duplicates are not ambiguity | **YES** for this seed | **NEEDS_REAL_SEED** |
| B6 | Exact identities with degraded/incomplete provenance | TC-2 completeness, SC-3 capture states, BAE completeness label | incomplete claim or rejected admission | BAE still requires exact commit/run/image fields | **CONDITIONAL** | **NO** for a truthful provider-degraded case | Exact fields would continue to prove the supposedly degraded binding | BAE `incomplete` is under-specified and parser persists accepted records only as `complete` | **YES** without a real partial observation | **DEFER** |

## 8. B1 — Commit -> Run missing

### 8.1 Authority and coupling

The current complete E1 observation binds:

```text
repository: 1278498159 / ShaikMuhammadSami/Topo_Ai
commit: 4149b194c4c4fdfdcd402a157c5336ad59dfdbbe
run: 32695735269
attempt: 1
image: sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed
artifact: 9508752475
completeness: complete
```

The build-record parser validates GitHub artifact scope, workflow-run
`head_sha`, repository, run/attempt, BuildKit internal parameters, builder ID,
artifact digest, build-record digest, and image result before emitting E1.
The model requires every one of these identity fields, and persistence treats
them as one immutable fact.

The Run -> Image relationship `rel:63f5cd5dfce59d148ae5` is not independent
authority. It is produced from E1, cites E1, and repeats E1's commit, run,
attempt, image, artifact, builder, and build-record references.

### 8.2 Representability and disposition

Removing the trigger edge, Run `head_sha`, and old analysis while retaining E1
leaves exact Commit -> Run authority. Removing E1 removes the only provider
authority for Run -> Image. Retaining or rewriting its derived edge would
manufacture separability. Nulling the commit is invalid under both Pydantic
and SQL schema; changing the commit invents source truth; changing only the
completeness label leaves the exact binding visible.

Therefore:

```text
ontology/model representability: NO for this V1 provider path
current-seed constructibility: NO
disposition: CONSTRUCTION_BLOCKED
reason: evidence_model_nonseparable
```

Product causal behavior remains unmeasured.

## 9. B2 — Run -> Image missing

### 9.1 Independent Commit -> Run authority

B2 is asymmetrical with B1. The seed contains an independent provider-native
workflow-run observation projected by
`backend.app.services.github_actions_graph`:

- Run entity `github:api.github.com:workflow-run:32695735269` has exact
  `run_id`, `run_attempt=1`, and golden `head_sha`;
- `rel:ebaedc357f11b3e70170` is the complete observed
  `GitCommit --triggers--> GitHubWorkflowRun` claim; and
- `evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b`
  records that provider-native run metadata established the relationship.

These surfaces are constructed from the workflow-run API observation, not
from E1. They can remain authoritative after the build-record observation is
removed.

### 9.2 Run -> Image authority

The Run -> Image authority is E1. Its derived surfaces are:

- `rel:63f5cd5dfce59d148ae5` (`Run --produces--> Image`);
- `evidence:github-actions-build:c9b6d53cf66facfb444c8ae0`; and
- `metadata.github_actions_build_artifact_lineage` counters.

Deleting only `rel:63f5cd5dfce59d148ae5` is invalid because E1 still proves
the claim. A future valid B2 cut must remove E1 and all of those derived
surfaces together. It must retain the Run entity, its `head_sha`, the trigger
edge/evidence, the canonical image entity, both Kubernetes `uses` edges,
workload ownership, failure signal, incident, and pin.

SC-2 would then encounter `IMAGE_TO_RUN_MISSING` after it resolves the intact
runtime image. TC-4 can report missing build/source-to-image proof because the
pinned workload/image relationship remains. Missing is not contradiction.

Therefore:

```text
ontology/model representability: YES
current-seed constructibility: YES
synthetic authority required: NO
disposition: EXECUTABLE, subject to a separate frozen B2 contract
```

## 10. B3 — Image -> affected workload missing

### 10.1 Exact persisted entities

| Role | Canonical entity |
|---|---|
| Deployment | `k8s:docker-desktop:deployment:bd4cfb7a-d32a-43bf-bf82-366e3fd8841a` |
| ReplicaSet | `k8s:docker-desktop:replicaset:200703db-a601-44f0-90ff-63c64cb17162` |
| Affected Pod | `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168` |
| Immutable image | `artifact:container-image:sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |

The ownership path is independently supported by:

```text
Deployment --owns--> ReplicaSet
  rel:57555e411f2db29864c2

ReplicaSet --runs--> Pod
  rel:9c8db862d53bac71327f
```

Both relationships have complete TC-2 provenance from Kubernetes owner UIDs.

### 10.2 Requested-image fields

The golden requested repository-digest reference appears in all of these
workload-specific surfaces:

1. Deployment
   `properties.containers[0].image`;
2. Deployment nested
   `properties.containers[0].image_identity.requested_image`;
3. Deployment nested
   `resolved_artifact_identity` and `identity_evidence_refs`;
4. Deployment annotation
   `kubectl.kubernetes.io/last-applied-configuration`, whose serialized Pod
   template embeds the exact image;
5. Pod `properties.containers[0].image`;
6. Pod nested `image_identity.requested_image`;
7. Pod nested `resolved_artifact_identity` and `identity_evidence_refs`;
8. both `uses` relationships' properties and TC-2 source references.

The source fields retained by SC-3 are
`deployment.spec.template.spec.containers[].image` and
`pod.spec.containers[].image`.

### 10.3 Runtime-image fields

The affected Pod retains:

- `properties.containers[0].image_id` from
  `pod.status.containerStatuses[].imageID`, equal to the golden OCI index
  repository digest;
- `properties.containers[0].runtime_status_image` from
  `pod.status.containerStatuses[].image`, equal to child/runtime digest
  `sha256:a3392fbeae192e861a3df42d25acf050c45a657c8e277a41258332baa9451f53`;
- the same values in nested `image_identity.runtime_image_id` and
  `image_identity.runtime_status_image`; and
- corresponding `identity_evidence_refs`.

SC-3 does not promote the runtime-status child digest into requested artifact
identity. The requested immutable reference resolves the golden OCI index;
the runtime imageID independently reports that same index.

### 10.4 Exact topology relationships

Two complete derived claims establish the workload/image association:

| Relationship | Claim |
|---|---|
| `rel:496906e3e345259910c9` | Deployment `--uses-->` golden ContainerImage |
| `rel:0548ac3e949f44b3569c` | affected Pod `--uses-->` golden ContainerImage |

Both reference
`evidence:container-images:1d88e6b0-6706-44d7-80d4-5aaa4c4d1d56` and are
derived by `backend.app.services.container_image_graph` from the entity fields
above. Deleting the relationships alone would leave the exact source
observations in the Deployment and Pod and would therefore be stale and
internally inconsistent.

### 10.5 Authority coupling and independent absence

The image-use observation is not atomically coupled to the failure signal.
The signal independently stores BackOff, Pod UID/name, failure boundary, and
incident pin and contains no image value. The Pod entity can retain its UID,
name, phase, readiness, restart count, container ID, owner chain, and resource
metadata without an image observation because `Entity.properties` is an open
dictionary. SC-3 also explicitly models captured, missing, and rejected field
states.

A real Kubernetes Pod spec normally requires an image. B3 does not assert
that Kubernetes ran a Pod without one; it represents that Topo's preserved
evidence lacks the image-to-affected-workload observation. That distinction
must be explicit in the future scenario contract.

The canonical ContainerImage entity must remain because it is the target of
the independently preserved Run -> Image claim. Its digest and identity do
not by themselves identify the affected workload.

### 10.6 Minimum complete B3 semantic cut set

A future authorized B3 construction must remove every workload-specific exact
image-use proof surface while preserving the standalone image entity:

1. Deployment requested-image compatibility fields and nested SC-3 identity;
2. the image-bearing Deployment last-applied-configuration annotation;
3. Pod requested image, runtime imageID, runtime-status image, nested SC-3
   identity, and their evidence references;
4. Deployment/Image `uses` relationship `rel:496906e3e345259910c9`;
5. Pod/Image `uses` relationship `rel:0548ac3e949f44b3569c`;
6. their shared container-image Evidence object;
7. only the affected container-image relationship counters and snapshot
   record counts needed for structural consistency; and
8. stale derived causal analysis/projection state before recomputation.

The cut must be proven by a recursive persisted-payload scan, not by checking
only relationship IDs. It must not remove the ContainerImage entity,
Run/Image `produces` edge, build-artifact row, Pod, Deployment, ReplicaSet,
owner edges, signal, incident, or topology pin.

### 10.7 Protected truths

B3 must preserve exactly:

- repository, source revision, source-file mutation, Actions Run, and E1;
- `rel:63f5cd5dfce59d148ae5` Run -> Image and its provider evidence;
- the golden ContainerImage entity and immutable digest;
- Deployment, ReplicaSet, Pod identity and UID ownership;
- Pod `container_id`, `ready=false`, `restart_count=2`,
  `total_restarts=2`, and other non-image runtime fields;
- BackOff signal, incident identity/boundary, affected Pod, and topology pin;
- unrelated topology and temporal evidence; and
- all ranking, support, and truth-contract policies.

### 10.8 Representability, constructibility, and future strategy

The model can represent a workload and failure while image observations are
missing. The seed keeps failure authority separate from image-use authority,
so B3 is constructible through removal without synthetic replacement
evidence.

A future authorized mutation should remove the exact image-bearing fields,
both derived `uses` claims, their Evidence object, and related counters on an
isolated seed copy. It should not manufacture a new partial observation merely
to label the scenario. It should validate the resulting `GraphSnapshot`, prove
that the signal/incident/owner chain remains unchanged, and recursively prove
that no exact workload/golden-image co-reference survives.

The old `CausalAnalysisRecord` must be excluded from both control and B3 fresh
reasoning. Incident-level cached analysis/projection fields must follow the
same reset boundary. No reset or mutation is performed by this audit.

Therefore:

```text
ontology/model representability: YES
current-seed constructibility: YES
synthetic authority required: NO
disposition: DEFER as a valid fallback; B2 is the smaller selected cut
```

## 11. B4 — Commit -> Run ambiguous

The generic topology schema can hold multiple `triggers` relationships, so it
can serialize competing claims. That is not sufficient authority. The current
GitHub V1 observation contract supplies one `head_sha` for one workflow run,
and the build parser requires the artifact and workflow-run SHA to agree. The
BAE provider is fixed to `github_actions`; there is no second persisted
provider-observation family for this claim.

Thus the graph shape is conditionally representable, but this provider path
cannot legitimately originate competing commits for the same run/attempt.
The seed contains exactly one commit/run association. Duplicating a row,
changing a SHA, or adding a second trigger edge would create evaluator-only
authority.

```text
model representability: CONDITIONAL at claim layer
seed constructibility: NO
disposition: DEFER pending a real independently authoritative conflict source
```

## 12. B5 — Run -> Image ambiguous

The current model supports real multiplicity:

- the parser may emit multiple exact image digests from one build record;
- one run may therefore have multiple independently evidenced output edges;
- independently proven runs may produce the same digest; and
- SC-2 can detect multiple source revisions for one runtime digest as
  `AMBIGUOUS_SOURCE_PROVENANCE`.

Multiplicity is not automatically ambiguity. A run producing two exact images
is a one-to-many fact. Two runs producing the same digest are two producer
facts; causal source ambiguity exists only when the surviving authoritative
paths prevent a unique causal source selection. Artifact aliasing, OCI
index/child identity, multiple attempts, and actual competing build receipts
must not be conflated.

The seed contains one complete E1 row, one run/attempt, one golden image, and
one `produces` edge. Any competitor created from this seed would be synthetic.

```text
model representability: YES for real multiplicity; scenario semantics must be frozen
seed constructibility: NO
disposition: NEEDS_REAL_SEED with multiple provider-authentic observations
```

## 13. B6 — degraded/incomplete provenance

The current models expose several distinct incomplete states:

- TC-2 `RelationshipProvenanceCompleteness` supports `complete`, `partial`,
  and legacy-unspecified;
- SC-3 image observations support captured, missing, and rejected source
  values plus missing/ambiguous spec/status joins;
- TC-4 supports defensibly expected `missing` evidence; and
- `BuildArtifactEvidenceCompleteness` contains `complete` and `incomplete`.

These states do not have one shared meaning. In particular, BAE still requires
exact commit, run/attempt, image, provider artifact, artifact digest,
build-record digest, and builder fields even when its label is `incomplete`.
The production GitHub/BuildKit parser persists accepted records only as
`complete`; rejected provider records become warnings rather than durable
partial BAE rows. SC-2 ignores incomplete BAE rows, but the row's exact fields
would remain product-visible authority. Changing only the label would be a
cosmetic degradation, not a truthful missing observation.

TC-2 can truthfully express a partial relationship when the underlying source
references are genuinely partial. SC-3 can truthfully express missing source
fields. The current seed, however, contains only complete provider and
relationship observations for the golden chain. A valid B6 needs a narrowly
defined claim and a real partial observation or a separately approved model
that declares which subclaims remain authoritative.

```text
model representability: CONDITIONAL by evidence family
seed constructibility: NO for provider-degraded BAE
disposition: DEFER until semantics and a real source fixture are available
```

## 14. Provider invariants and seed limitations

The audit found these V1 invariants:

1. `BuildArtifactEvidence` is an atomic GitHub Actions/BuildKit observation,
   not independent Commit/Run and Run/Image claim records.
2. The build parser emits complete evidence only after all provider identities
   agree; invalid or partial artifacts are rejected to warnings.
3. GitHub workflow-run metadata separately supports Commit -> Run.
4. The build-artifact linker creates neither endpoint; it resolves the
   existing Run and Kubernetes-derived immutable image.
5. One run may produce multiple exact images, and multiple exact runs may
   produce the same digest. Those are multiplicity until a causal question is
   actually unresolved.
6. SC-2 starts at the affected entity in the incident-pinned snapshot,
   requires the Pod/owner/workload image path, then performs an exact-digest
   BAE lookup. It does not use latest topology.
7. SC-4 consumes persisted SC-2 lineage context and traverses only the pinned
   snapshot. `produces` is forward and `uses` is reverse for causal traversal.
8. TC-4 treats missing proof as missing, never contradiction, and does not
   invent an artifact producer relationship.
9. AR-2 requires supported relevance and candidate-bound linkage evidence;
   AR-3 presents only support-qualified hypotheses in its supported
   projection. TC-5 keeps ranking separate and uncalibrated.

The current seed has only one repository, commit, run/attempt, complete build
observation, immutable image, Deployment, ReplicaSet, affected Pod, and
incident. It contains no authentic ambiguity and no authentic degraded build
observation.

## 15. Shared-authority findings

| Observation | Claims it supports | Separability consequence |
|---|---|---|
| GitHub workflow-run observation | Run identity; Commit -> Run; repository contains Run | Independent of build evidence, enabling B2 |
| Atomic E1 build observation | Commit -> Run co-reference; Run -> Image; artifact/build identity | Prevents B1 but can be removed for B2 because Commit -> Run has another authority |
| Kubernetes Deployment/Pod image observations | requested/runtime identity; Deployment/Pod -> Image | Must be removed as a complete B3 cut; edge-only deletion is invalid |
| Kubernetes failure signal | BackOff, affected Pod, incident boundary | Independent from image use, enabling B3 |
| Persisted causal analysis | SC-2/SC-4/TC-4/AR-2/AR-3 conclusions | Derived state; must never stand in for mutated authority |

## 16. Selected next executable scenario

The selected next scenario is:

```text
LINEAGE-2B.2 — Missing Actions Run -> Immutable Image Provenance
```

It is selected over B3 because it has the smallest truthful semantic cut:

1. Commit -> Run has independent provider-native workflow-run authority.
2. Run -> Image has one clearly owned atomic observation, E1.
3. The Kubernetes image/workload chain, failure, incident, and pin remain
   untouched.
4. The scenario directly measures whether missing provider build provenance
   reduces source-level causal specificity.
5. No product-model change or synthetic authority is required.

The next block should freeze a B2-specific executable contract covering the
exact authoritative cut, derived-state reset, control symmetry, post-mutation
proof, expected safe degradation, determinism, and EAI-1 finalization. It must
not implement or measure B2 yet.

B3 remains a valid, constructible fallback after B2, but it is deferred
because its proof surface is broader and includes a serialized Deployment
annotation in addition to SC-3 fields and relationships. B1 is blocked. B4 and
B6 are deferred. B5 requires a real provider-authentic multi-path seed.

## 17. Future evidence-model risk register

A future source may independently prove Run -> Image without proving
Commit -> Run, such as a registry/build attestation with stable run identity.
If that operational need becomes real, a future reviewed architecture may
separate raw observations from claims conceptually:

```text
ProviderObservation E1
    -> Claim P1: Commit -> Run
    -> Claim P2: Run -> Image

ProviderObservation E2
    -> Claim P2: Run -> Image
```

That could make P1 removable while P2 remains independently supported. It is
only a risk-register direction. This checkpoint does not create
`ProviderObservation`, claim bindings, tables, migrations, or product code.

## 18. Checkpoint boundary

This audit creates this documentation file only. It modifies no product,
backend test, evaluator, agent, frontend, CLI, workflow, seed, historical
result, or baseline. It creates no result root or EAI manifest and runs no
RCA.

The next authorized action is architect review followed, if approved, by a
documentation-only block freezing the selected B2 executable scenario
contract.

