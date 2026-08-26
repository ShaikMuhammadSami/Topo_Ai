# LINEAGE-2B — Broken / Incomplete Immutable Lineage Robustness v1

Status: **LINEAGE-2B-0 contract/design checkpoint only**

Date: 2026-08-27

Contract branch: `evaluation/lineage-2b-broken-lineage-contract-v1`

Accepted repository commit at contract freeze:
`28c27e3e784f927ce0d808efefea51133c6ab0b1`

Accepted repository summary:
`28c27e3 test(evaluation): add artifact integrity contract (#50)`

First approved measurement scenario:
**`LINEAGE-2B.1 — Commit -> Actions Run Missing`**

## 1. Purpose and boundary

LINEAGE-2B measures whether TopoAI degrades causal specificity safely when a
required immutable-lineage hop is unavailable or incomplete. LINEAGE-2A
established robustness against temporal source distractors while the golden
immutable lineage was complete. LINEAGE-2B asks a different question: what
happens when the evidence chain itself has a controlled gap?

This is not a distractor-ranking experiment and it does not authorize product
repair. This checkpoint freezes the family and B1 semantics before a harness
exists or any measurement is made.

This checkpoint does not:

- create or run a scenario;
- mutate the accepted seed or any result database;
- create a result root or integrity manifest;
- modify product, evaluator, agent, frontend, CLI, or workflow code;
- change SC-1 through SC-4, AR-1 through AR-3, or TC-1 through TC-5;
- start B2 through B6, an ambiguity experiment, or AR-4; or
- create a result baseline.

## 2. Accepted dependencies

### 2.1 LINEAGE-1

LINEAGE-1 remains the accepted provider-backed source-to-runtime golden proof
for one controlled Kubernetes scenario. Its accepted source-level conclusion
was `PROVEN`, with `NO_DIVERGENCE`, at semantic level
`INITIATING_MUTATION`.

### 2.2 LINEAGE-2A

LINEAGE-2A is **ACCEPTED / CLOSED** with final verdict
`ROBUST_IN_MEASURED_MATRIX` and taxonomy result `NO_DIVERGENCE`. This family
does not reopen LINEAGE-2A or reinterpret its 16-scenario distractor matrix.

The accepted AR policies remain:

- `causal-evaluation-budget-v1`;
- `causal-support-gate-v1`; and
- `causal-hypothesis-projection-v1`.

### 2.3 EAI-1

EAI-1 is accepted. Every new result family created after EAI-1 must generate
and successfully verify `artifact-integrity-v1.json` under
`evaluation-artifact-integrity-v1` before its baseline can be accepted.
Historical result families remain legacy/pre-contract identities and are not
backfilled or rewritten.

## 3. Governing invariant

The invariant is frozen exactly as:

> MISSING PROVENANCE REDUCES CAUSAL SPECIFICITY;
>
> IT NEVER GRANTS PERMISSION TO FABRICATE THE MISSING RELATIONSHIP.

Equivalently, TopoAI may make a source-level causal claim only when the
evidence required for that specificity exists. Absence of evidence cannot be
converted into an inferred exact lineage hop.

## 4. Golden and broken chains

The intact controlled chain is:

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

B1 freezes this single missing hop:

```text
Repository
    ->
Commit
    X
Actions Run
    ->
Immutable Image
    ->
Deployment / Pod
    ->
Runtime Failure
```

The exact B1 provenance boundary is:

```text
source revision 4149b194c4c4fdfdcd402a157c5336ad59dfdbbe
    X
GitHub Actions run 32695735269, attempt 1
```

The source revision and its exact file mutation remain known historical source
facts. B1 removes only the ability to prove that this revision produced the
Actions Run associated with the failing artifact.

## 5. Missing and ambiguous are distinct

`missing` means no accepted authoritative exact hop exists.

`ambiguous` means multiple authoritative-looking alternatives exist and no
unique exact resolution is justified.

B1 tests missing only. It must not introduce a competing commit, run, image,
or provider path. Future ambiguity scenarios must preserve all alternatives
and must not select an arbitrary source.

## 6. Current Commit -> Actions Run evidence audit

The accepted seed was inspected read-only. The following product-visible
surfaces currently establish or retain the golden Commit -> Actions Run
association.

### 6.1 Primary provider evidence record

The `build_artifact_evidence` table contains one complete
`BuildArtifactEvidenceRecord`:

| Field | Accepted value |
|---|---|
| Evidence ID | `build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb` |
| Provider | `github_actions` |
| Repository ID | `1278498159` |
| Repository | `ShaikMuhammadSami/Topo_Ai` |
| Workflow run | `32695735269` |
| Run attempt | `1` |
| Commit SHA | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Image digest | `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Provider artifact | `9508752475` |
| Completeness | `complete` |

`github_actions_build_record.py` authenticates the repository, run, attempt,
run `head_sha`, provider artifact scope, SLSA builder identity, and immutable
image result before constructing this record. The row therefore combines two
semantically distinct joins in one durable provider fact:

```text
Commit -> Actions Run
Actions Run -> Immutable Image
```

`lineage_candidate_admission.py` performs its bounded exact-digest lookup on
this table. It groups accepted rows by
`repository_id + repository + commit_sha`, then binds the selected source
event to `run_id + run_attempt + image_digest`. This complete row is the live
SC-2 Path B authority used to admit the old source revision.

### 6.2 Incident-pinned topology

The incident remains pinned to:

```text
snapshot:actions-enriched:20260826T051031Z:2d8416d3
```

That snapshot contains these additional product-visible proof surfaces:

1. The `GitHubWorkflowRun` entity
   `github:api.github.com:workflow-run:32695735269` has
   `properties.head_sha` equal to the golden commit SHA.
2. Relationship `rel:ebaedc357f11b3e70170` is the exact directed
   `GitCommit --triggers--> GitHubWorkflowRun` edge. Its complete observed
   provenance contains both `git_commit_sha` and
   `github_workflow_run_id` references.
3. Evidence `evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b`
   references the trigger edge and reports one commit/run relationship.
4. The independently meaningful Run -> Image relationship
   `rel:63f5cd5dfce59d148ae5` includes a `git_commit_sha` source reference in
   its otherwise downstream Run/Image provenance. If retained unchanged, that
   co-reference still exposes the supposedly missing upstream binding.

Repository -> Commit and Repository -> Run relationships are separate facts.
Neither proves Commit -> Run by itself and both must remain.

### 6.3 Persisted derived analysis

The accepted seed contains causal analysis
`causal-analysis:76c9b683e95e2f2fd599677122f2ebae`. Its immutable JSON
payload retains the previously valid conclusion through:

- `lineage_admission_audit`;
- `candidate_selection_audit`;
- `admission_evidence_refs` containing the commit, run, and provider evidence;
- `lineage_paths` containing the revision, run, attempt, image, and canonical
  change ID; and
- the supported source-level top hypothesis.

This record is a derived cache/result, not the primary provider authority. A
future B1 measurement must not reuse it as if it had been generated from the
mutated evidence state.

### 6.4 Surfaces that do not independently prove the hop

The canonical Git commit entity, canonical Actions Run entity, source change
event, repository membership edges, aggregate enrichment counters, branch
name, workflow reference, timestamps, and shared repository scope do not
independently establish the missing exact hop. They remain diagnostically
useful but cannot substitute for exact provenance.

## 7. Future B1 surgical mutation contract

The accepted seed is immutable. B1 may operate only on an isolated,
byte-identical copy whose pre-mutation SHA-256 is verified first.

The future harness must remove the complete Commit -> Run proof as one
**semantic cut set**, not merely delete the decorative trigger edge. At
minimum, the isolated copy must no longer expose:

1. the complete `build_artifact_evidence` record that jointly binds the
   golden commit to run `32695735269`;
2. the `GitCommit --triggers--> GitHubWorkflowRun` relationship and its exact
   commit/run provenance;
3. the Run entity's `head_sha` binding to the golden commit;
4. the `git_commit_sha` co-reference on the preserved Run -> Image
   relationship; and
5. a reusable causal-analysis payload that already asserts the old exact
   lineage.

The current build-evidence schema requires a non-null, syntactically valid
commit SHA. The future harness must therefore not create an empty, fake, or
replacement commit value and must not merely relabel the complete record as
incomplete while leaving the exact binding readable. The compatible surgical
approach is to remove the combined provider row from the isolated copy while
preserving the already-persisted Run -> Image topology relationship and its
downstream provider/artifact evidence, minus only the upstream
`git_commit_sha` co-reference.

The shared GitHub Actions evidence object and enrichment counters must be made
internally consistent with the missing trigger relationship. This consistency
cleanup is part of removing the exact hop, not permission to alter unrelated
entities or relationships.

The prior causal analysis for the incident must be excluded from B1 execution
and grading so that the product performs a fresh deterministic analysis from
the mutated persisted truth. A new B1 result may be persisted in the isolated
copy; the accepted seed and its historical analysis remain untouched.

The future implementation must assert a pre/post inventory so this semantic
cut set cannot silently expand.

## 8. Evidence that must remain untouched

B1 must preserve exact identity and content for:

- repository `ShaikMuhammadSami/Topo_Ai` and provider repository ID
  `1278498159`;
- failure commit `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`;
- parent commit `f9b152133a8075428766dd48b3f752b255ec5270`;
- source event `change-event:20a8946c8c445153d85c90ee2166d487`;
- source mutation
  `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633`;
- changed path `evaluation/fixtures/lineage-image/runtime-mode.txt`;
- before value/hash `healthy` /
  `63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d`;
- after value/hash `fail` /
  `2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997`;
- Actions Run entity `32695735269`, attempt `1`;
- Run -> Image relationship and its run, attempt, provider artifact, build
  record, builder, immutable image, and time evidence except the intentionally
  removed upstream commit co-reference;
- immutable OCI index
  `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed`;
- Deployment/Pod requested-image and runtime-image identity;
- Deployment -> ReplicaSet -> Pod UID ownership;
- runtime BackOff/CrashLoopBackOff failure evidence;
- incident identity, affected Pod, primary signal, and incident-time snapshot
  pin;
- all unrelated graph relationships and durable records; and
- all timestamps, scores, weights, caps, and policies.

The B1 mutation must not alter source truth merely to make source attribution
unavailable. It removes proof of production, not the source change itself.

## 9. Broken-hop assertion

The future harness must derive the post-mutation assertion from
product-visible persisted truth. An evaluator-side label is insufficient.

Before RCA runs, B1 must verify all of the following:

- no complete provider evidence record binds the golden revision to the
  golden run/attempt;
- no exact directed `triggers` edge binds the golden Commit entity to the
  golden Run entity;
- no surviving accepted relationship provenance co-references the golden
  commit and run as one exact production path;
- the Run entity does not retain the golden revision as `head_sha`;
- no persisted lineage-admission/path or cached causal-analysis result from
  the intact control is eligible for reuse;
- the source event and mutation remain exact;
- the Run -> Image hop remains independently observable;
- the image-to-workload/runtime chain remains exact; and
- the incident still names the same affected entity and pinned topology.

After RCA runs, the harness must also prove that no newly generated admission
audit, relevance bridge, topology edge, TC-4 item, diagnostic projection, or
supported projection reconstructs the missing exact hop without authoritative
evidence.

No field named `B1`, `BROKEN_LINEAGE`, `EXPECTED_ABSTENTION`, `NONCAUSAL`, or
`GOLDEN_MISSING_EDGE` may be present in product input.

## 10. Expected causal specificity

The existing root-cause semantic levels remain separate:

1. `INITIATING_MUTATION`;
2. `FAILURE_MECHANISM`;
3. `RUNTIME_MANIFESTATION`; and
4. `OPERATIONAL_IMPACT`.

In B1, the exact golden source mutation must not be support-qualified as
`INITIATING_MUTATION` through the broken chain. This restriction applies even
if the source event remains recent-looking, diagnostically high-ranked, or
otherwise suspicious.

TopoAI may retain lower-specificity conclusions that are independently backed
by surviving evidence. Examples include:

- the runtime failure occurred;
- the affected Pod or Deployment identity;
- the failing immutable artifact identity;
- the artifact's exact use by the affected runtime;
- the known Actions Run's production of that immutable artifact; and
- a lower `FAILURE_MECHANISM`, `RUNTIME_MANIFESTATION`, or
  `OPERATIONAL_IMPACT` conclusion when the current product and evaluator can
  support it without the missing hop.

Source attribution unavailable does not mean nothing is known. Conversely,
truth at a downstream semantic level cannot be relabeled as exact source-level
causality.

## 11. Diagnostic and supported projections

AR-3 remains authoritative.

The diagnostic projection may continue to show the known source change as
suspicious. Diagnostic rank, temporal precedence, and a high heuristic score
are not proof.

The supported projection may contain only hypotheses that satisfy the frozen
AR-2 candidate-specific evidence gate. The exact source mutation must be
absent from the supported projection when its required Commit -> Run proof is
missing. If no independently supported lower-level hypothesis exists, safe
abstention is the correct result.

## 12. TC-4 missing and unknown semantics

TC-4 is unchanged:

- missing or unavailable provenance is not contradiction;
- unknown is not contradiction;
- silence, absence, or ambiguity cannot be promoted to negative proof;
- a `missing` evidence item is legal only when the existing TC-4 contract has
  a defensible `expectation_basis`; and
- the harness may grade the absence of a required hop without injecting a new
  TC-4 claim type or rewriting the evidence ledger.

If the current product emits no hypothesis because SC-2 does not admit the
old source event, it need not fabricate a per-hypothesis missing item. The
evaluation-side broken-hop assertion remains separate from product evidence.

## 13. Forbidden recovery

The missing hop must remain missing. The product and harness may not recover
it through:

- timestamp closeness or temporal precedence;
- repository, branch, tag, workflow, or image-name similarity;
- a nearby, latest, or latest-successful CI run;
- latest deployment, latest topology, local Git history, or provider lookup;
- fuzzy matching, embeddings, an LLM, or generated prose;
- ranking score, normalized confidence, topology weight, kind prior, or
  lineage weight; or
- an evaluator label, expected answer, scenario ID, or golden identity hint.

No score or confidence value can manufacture Commit -> Run provenance.

## 14. Frozen subsystem boundaries

### 14.1 SC-1

SC-1 source identity and file-mutation evidence remain exact and unchanged.
B1 deliberately distinguishes “this source change exists” from “this source
change produced the failing artifact.”

### 14.2 SC-2

`causal-candidate-admission-v2` is unchanged. B1 measures whether removing the
complete Commit -> Run provider binding prevents the broken Path B from
qualifying. The contract does not force an admission outcome: a legitimate
independent path may still be recorded and evaluated, but the missing hop may
not be reconstructed from weak substitutes.

### 14.3 SC-3

`kubernetes-container-image-identity-v1` is unchanged. Requested image,
runtime status image, runtime image ID, full immutable digest, container name,
and workload/image joins remain frozen.

### 14.4 SC-4

`causal-relevance-v2` is unchanged. B1 measures whether exact immutable-lineage
anchor resolution correctly becomes unavailable or incomplete when the
provider bridge lacks the source-to-run join. SC-4 may not consume stale
intact lineage metadata or resolve an anchor from latest topology.

### 14.5 AR-1

`causal-evaluation-budget-v1` remains the bounded union of the ordinary
shortlist and already-admitted exact-lineage evidence. B1 does not change
frontier capacity, selection bases, or preservation rules.

### 14.6 AR-2

`causal-support-gate-v1` remains the candidate-specific evidence qualifier.
Incident-level runtime evidence and candidate-context source/time evidence
cannot substitute for the missing candidate linkage.

### 14.7 AR-3

`causal-hypothesis-projection-v1` retains separate diagnostic and supported
projections. Unsupported diagnostic hypotheses consume no supported capacity,
and no supported hypothesis may be dropped except by the legitimate supported
cap.

### 14.8 TC-1 through TC-5

- **TC-1:** exact source-native/canonical identity; ambiguity remains
  unresolved; no fuzzy identity.
- **TC-2:** relationship predicate, direction, provenance origin, source
  references, linker version, and completeness retain their exact meanings.
- **TC-3:** effective, source, observed, recorded, and incident-boundary times
  remain unchanged; no latest/later-topology fallback.
- **TC-4:** supporting, contradicting, missing, and unknown semantics remain
  separate; no new claim type or contradiction from absence.
- **TC-5:** heuristic ranking and evidence state remain separate;
  `calibrated_probability` remains null.

## 15. Ranking, time, image, and topology freezes

B1 changes no raw score, `13c-causal-v1` coefficient, temporal weight,
topology weight, kind prior, lineage weight, tie-break, Top-N limit, confidence
semantics, or calibration boundary.

It rewrites no effective/source/observed/recorded timestamp and does not widen
the 180-minute Path A lookback.

It changes no requested/runtime image identity and introduces no alternate
digest, tag, repository, or container.

The incident continues to use its explicit historical topology pin. Apart
from the exact proof-surface removal and consistency cleanup specified in
Section 7, all pinned topology entities, relationships, evidence, properties,
and metadata remain byte-equivalent. There is no topology expansion or latest
snapshot fallback.

## 16. Control and minimal first matrix

The future control is one intact isolated copy of the accepted seed. It must
reproduce:

- complete golden lineage;
- the golden source candidate admitted through exact immutable lineage;
- supported source-level `INITIATING_MUTATION`; and
- the accepted downstream evidence chain.

The proposed minimal first matrix is:

```text
CONTROL = 1
B1      = 1
```

Three storage-order variants add no meaningful B1 dimension. There is one
provider record and one exact Commit -> Run relationship in the accepted seed;
the B1 mutation removes the entire exact semantic hop, and the relevant
repository/admission paths already use explicit deterministic sorting. A
permutation of an absent singleton hop would manufacture a scenario-count
claim without changing semantics.

Determinism must instead be proven by repeating the same control and B1
construction from byte-identical isolated seed copies and comparing their
structured conclusions and finalized artifact identities. These repetitions
are verification runs, not distinct matrix variants.

## 17. Frozen B1 success condition

B1 succeeds only when all of the following hold:

1. exact Commit -> Run proof is genuinely absent;
2. no fabricated replacement edge or path appears;
3. the exact source-level `INITIATING_MUTATION` is not support-qualified through
   the broken chain;
4. no fuzzy, timing, score, confidence, LLM, or latest-state fallback restores
   source attribution;
5. surviving downstream evidence remains truthful;
6. Topo safely abstains from source attribution or reduces specificity to an
   independently supported lower causal level;
7. diagnostic suspicion does not become supported causality without evidence;
8. TC-4 missing/unknown semantics remain correct;
9. the result is deterministic; and
10. EAI-1 generation and verification succeed.

## 18. Frozen first-divergence taxonomy

The taxonomy and priority are frozen exactly as:

1. `BROKEN_HOP_STILL_PRESENT`
2. `FABRICATED_PROVENANCE_HOP`
3. `SOURCE_CAUSE_FALSELY_SUPPORTED`
4. `UNSAFE_SPECIFICITY_PRESERVED`
5. `VALID_DOWNSTREAM_EVIDENCE_CORRUPTED`
6. `EVIDENCE_SEMANTICS_DEGRADED`
7. `ORDER_DEPENDENT_RESULT`
8. `NO_DIVERGENCE`

Priority follows the earliest trustworthy boundary. The harness first proves
that the experiment actually removed the hop. It next checks whether the
product recreated it. Only after those provenance checks are valid does it
grade source support and presentation specificity. Downstream integrity and
evidence semantics follow, then determinism. This prevents a bad fixture from
being mislabeled as a product-causality failure and prevents a correct
abstention from hiding collateral evidence corruption.

For B1, `NO_DIVERGENCE` does **not** mean the source cause remains supported.
It means the gap was honored safely and the observed abstention or reduced
specificity matched this contract.

No taxonomy category may be added, removed, renamed, or reordered during
measurement without architect review.

## 19. Seed and isolation

Recommended seed:

```text
evaluation/results/lineage/post-sc4/topo-product-32695735269.db
```

Accepted seed SHA-256:

```text
9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F
```

The future harness must:

1. verify this identity before copying;
2. create a separate copy per control, B1, and verification repetition;
3. mutate only the B1 copy;
4. prove the seed remains byte-identical after every run; and
5. perform all SQLite writes only against isolated copies.

The accepted seed, closed baselines, historical results, and historical
analyses are immutable evidence.

## 20. Offline rule

All future B1 construction, execution, observation, and grading must be
offline. It may not access GitHub, Kubernetes, a registry, a cloud provider,
an LLM, embeddings, or local Git as causal input. Frozen persisted evidence is
the only product input.

## 21. Result root and EAI-1 gate

The reserved future result root is:

```text
evaluation/results/lineage/adversarial/lineage-2b-broken-commit-run/
```

This root is not created by LINEAGE-2B-0.

After the future result tree is finalized and quiescent, the B1 harness must:

1. generate `artifact-integrity-v1.json` using
   `evaluation-artifact-integrity-v1`;
2. verify the manifest against an independent scan of the result root; and
3. fail baseline acceptance if verification fails.

The future B1 baseline must record:

- integrity contract version;
- lowercase `tree_sha256`;
- included-file count; and
- verification success.

Legacy ad hoc full-tree hashes are not the authoritative LINEAGE-2B identity.
Existing evaluator inventories may remain and are included as ordinary EAI-1
artifacts.

## 22. Future B2-B6 risk register

These scenarios are recorded only; none is authorized for implementation by
this checkpoint.

| Scenario | Future adversarial condition | Required distinction |
|---|---|---|
| B2 | Run -> Image missing | Preserve source/run and image/workload truth while removing exact production proof. |
| B3 | Image -> affected workload missing | Preserve upstream lineage and runtime failure while removing exact artifact/use proof. |
| B4 | Commit -> Run ambiguous | Preserve multiple authoritative-looking run alternatives; never select arbitrarily. |
| B5 | Run -> Image ambiguous | Preserve multiple authoritative-looking artifact alternatives; never select arbitrarily. |
| B6 | Exact chain exists but one provenance record is degraded/incomplete | Distinguish an extant relationship from insufficient provenance completeness. |

Each future scenario requires its own reviewed contract or contract amendment
before implementation and measurement.

## 23. Claim boundary

LINEAGE-2B.1 will test one controlled missing exact Commit -> Actions Run
boundary using the accepted golden source-to-runtime seed. It may establish
that current TopoAI safely abstains or reduces causal specificity under that
single measured condition.

It will not prove:

- all missing-lineage behavior;
- ambiguous-lineage behavior;
- Run -> Image or Image -> Workload missing behavior;
- multiple-build, multiple-provider, or multiple-source behavior;
- generalized Kubernetes RCA correctness;
- statistical robustness or calibrated causal probability; or
- production-scale behavior.

## 24. Next block and stop boundary

The proposed next block is:

```text
LINEAGE-2B.1 harness + offline measurement only
```

It requires explicit approval. It must implement only the frozen B1 scenario,
control, evaluator assertions, offline measurement, and EAI-1 result finalization.
It must not include product repair, B2 through B6, ambiguity tests, or AR-4.

LINEAGE-2B-0 stops at this contract.
