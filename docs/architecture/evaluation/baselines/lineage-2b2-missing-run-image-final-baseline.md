# LINEAGE-2B.2 — Final Missing Run -> Image Provenance Baseline

**Status: ACCEPTED MEASUREMENT CANDIDATE**

This document is a documentation-only checkpoint of the completed and merged
LINEAGE-2B.2 measurement. It records the finalized result tree exactly as
measured. It is not a design contract, product repair, generalized product
claim, new measurement, B3 experiment, AR-4 change, or final architecture
acceptance.

## Accepted source state

- Repository: `C:\Topo-ai`
- Expected branch: `evaluation/lineage-2b2-final-baseline-v1`
- Current accepted commit: `66494030266844e12e063545520862d8d55097d5`
- Current accepted commit summary:
  `6649403 test(evaluation): add missing run image lineage scenario (#54)`
- Working tree before this documentation checkpoint: no reported paths

## Frozen status

| Field | Result |
|---|---|
| Scenario | LINEAGE-2B.2 — Missing Actions Run -> Immutable Image Provenance |
| Construction validity | PASS |
| CONTROL reproduction | PASS |
| Determinism | PASS — 3/3 |
| EAI-1 | PASS |
| Taxonomy | `NO_DIVERGENCE` |
| Overall verdict | `ROBUST_IN_MEASURED_MATRIX` |

## Governing result

When the sole authoritative Actions Run -> immutable Image provenance
observation was removed, while independently authoritative Commit -> Run,
Image -> affected workload, runtime failure, and incident/pin evidence remained
intact, TopoAI did not cross the missing Run -> Image boundary to support exact
source-level causal attribution.

The measured counterfactual was:

```text
CONTROL

Commit -> Run -> Image -> Affected workload -> Failure

B2

Commit -> Run
             X
             Image -> Affected workload -> Failure
```

The post-mutation authoritative state was:

| Boundary or fact | State |
|---|---|
| Commit -> Run | PRESENT / exact / provider-authoritative |
| Run -> Image | ABSENT |
| Image -> workload | PRESENT / exact |
| Runtime failure | PRESENT |

## Frozen seed

- Seed:
  `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`
- SHA-256:
  `9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f`
- `quick_check`: `ok`
- `integrity_check`: `ok`
- Access: immutable/read-only using `mode=ro&immutable=1` and
  `PRAGMA query_only=ON`
- Post-measurement seed SHA: unchanged

## Golden identities

| Identity | Frozen value |
|---|---|
| Commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| Actions run | `32695735269` |
| Run attempt | `1` |
| Immutable image | `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed` |
| Source event | `change-event:20a8946c8c445153d85c90ee2166d487` |
| Source mutation | `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633` |
| Original BuildArtifactEvidence E1 | `build-artifact-evidence:cf96a026fe2560c5f385d342436a8cb23de767bb` |
| Run -> Image relationship | `rel:63f5cd5dfce59d148ae5` |
| Run -> Image Evidence | `evidence:github-actions-build:c9b6d53cf66facfb444c8ae0` |
| Preserved Commit -> Run relationship | `rel:ebaedc357f11b3e70170` |
| Preserved Commit -> Run Evidence | `evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b` |

## Exact B2 mutation

The evaluator removed only the authority and derived state needed to sever the
Run -> Image boundary:

- BuildArtifactEvidence E1;
- the Run -> Image `produces` relationship;
- Run -> Image Evidence;
- claim-specific build-lineage metadata and counters; and
- stale derived causal-analysis state.

Build-lineage metadata changed from:

```json
{
  "evidence_records_considered": 1,
  "relationship_count": 1,
  "unresolved_evidence_count": 0
}
```

to:

```json
{
  "evidence_records_considered": 0,
  "relationship_count": 0,
  "unresolved_evidence_count": 0
}
```

No synthetic replacement authority was created.

### Evaluation-only fresh-analysis reset

CONTROL and every B2 repetition underwent the same evaluation-only reset
before the B2-specific mutation.

- Removed old analysis:
  `causal-analysis:76c9b683e95e2f2fd599677122f2ebae`
- Deleted incident causal-analysis records.
- Cleared three incident cached analysis fields.
- Deleted no authoritative evidence.
- Used the same reset for CONTROL and all three B2 repetitions.

No suitable explicit product force-recompute mechanism existed. This was an
evaluator-side isolated-copy procedure, not a product semantic change.

## CONTROL result

The intact CONTROL reproduced the accepted source-to-runtime causal result:

| Field | CONTROL result |
|---|---|
| Fresh analysis | `causal-analysis:9da0b88a484768cc36d93e28a3756989` |
| Original analysis reused | NO |
| Golden source candidate | discovered |
| Ordinary Path A | not used |
| Exact Path B | admitted |
| SC-2 | admitted / `exact_immutable_lineage` |
| SC-4 | `exact_immutable_lineage_anchor` |
| Provider bridge | valid |
| Relevance anchor | immutable image entity |
| TC-4 supporting | 5 |
| TC-4 contradicting | 0 |
| TC-4 missing | 0 |
| AR-2 | `supported_under_current_model` |
| AR-2 reason | `candidate_specific_causal_linkage_supported` |
| Diagnostic projection | `causal-hypothesis:2ac8304fd400995d86bff0b3750fd436` |
| Supported projection | same hypothesis |
| Supported Top1 | same hypothesis, rooted at the golden source event |
| Semantic level | `INITIATING_MUTATION` |
| Raw score | `9.8` |
| Final score | `30.17` |
| Legacy confidence | `0.3017` |
| Calibration | not calibrated |
| CONTROL reproduction | PASS |

## B2 result

All three repetitions produced the same fresh analysis identity:
`causal-analysis:85fdb84639362caecb97bcdbde926eee`. The original analysis
was not reused.

| Field | B2 result |
|---|---|
| Durable source event | still present |
| Raw source candidate discovery | false |
| Ordinary Path A | false |
| Exact Path B | false |
| SC-2 | incomplete / `image_to_run_missing` |
| Persisted lineage context | incomplete audit; empty lineage paths; empty mutation set |
| SC-4 | `not_evaluated` |
| Provider bridge | `not_evaluated` |
| Relevance anchor | null |
| TC-4 candidate-specific ledger | absent |
| TC-4 supporting | 0 |
| TC-4 contradicting | 0 |
| TC-4 missing | 0 |
| AR-2 | `not_evaluated` |
| AR-2 reason | no source hypothesis existed to support-gate |
| Diagnostic projection | empty |
| `top_hypothesis` | null |
| Supported projection | empty |
| Supported Top1 | null |
| Most-specific supported semantic level | `NONE` |
| Golden source `INITIATING_MUTATION` supported | NO |
| Raw score | null |
| Final score | null |
| Confidence | null |
| Calibration | null |

Missing provider provenance was not converted into contradiction. The evidence
semantics remained intact.

## Fabrication and unsafe specificity

- Fabricated Run -> Image provenance count: `0`
- Fabrication surfaces: none
- Unsafe exact-source specificity count: `0`
- Unsafe surfaces: none

The missing boundary was not reconstructed from timestamps, scores, Run
`head_sha`, image identity, topology, latest state, provider fallback, an LLM,
embeddings, fuzzy matching, or stale analysis.

## Protected truth preservation

All protected semantic fingerprints were unchanged before and after B2:

| Protected truth | SHA-256 | Result |
|---|---|---|
| Commit -> Run | `99a3c39456cea355e25d20d4be3630718c08b53c6a64b37e7423033775d96b9d` | unchanged |
| Image/workload | `bd1d6a6f265513541b6f389d83d959541e673544112058e527450985cb64489a` | unchanged |
| Runtime failure | `69546dea3a7b7b92c5d7e8fe4b24d4317f3082541f0daf2714ba6e2f4793eb83` | unchanged |
| Incident/pin | `a73234cd683c6c4b22ebf482131eac34992943379c2d40b3a42c789b1c419a28` | unchanged |
| Deployment -> ReplicaSet -> Pod owner chain | `759c821f25285746e5416d44e7b931ac887a4c9cc83d107dbef3dd142143106a` | unchanged |
| Source mutation | `bb46414a05c379eef07a35507243d970eb1984b0b4ef398f7d4ea214a3ae836b` | unchanged |
| ContainerImage identity | `8d912d191959d894b043a83fb606371b149d72559459f272f8e4f6f951e0de5e` | unchanged |

Protected truth preservation: **PASS**.

## Exact surviving authorities

| Authority or fact | Identity/value | State |
|---|---|---|
| Commit -> Run relationship | `rel:ebaedc357f11b3e70170` | PRESENT |
| Commit -> Run Evidence | `evidence:github-actions:88bfa781-66aa-4e29-85d1-abd03b53ce5b` | PRESENT |
| Run `head_sha` | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` | PRESENT |
| ContainerImage | immutable image identity above | PRESENT |
| Deployment -> Image | `rel:496906e3e345259910c9` | PRESENT |
| Pod -> Image | `rel:0548ac3e949f44b3569c` | PRESENT |
| Deployment -> ReplicaSet | `rel:57555e411f2db29864c2` | PRESENT |
| ReplicaSet -> Pod | `rel:9c8db862d53bac71327f` | PRESENT |
| Runtime failure signal | `signal:kubernetes-event:docker-desktop:ad733dcc-a026-424f-8984-6ed30108eec1` | PRESENT |
| Incident boundary | `2026-08-26T05:09:49+00:00` | PRESENT |
| Pinned topology | `snapshot:actions-enriched:20260826T051031Z:2d8416d3` | PRESENT |

## Broken-hop validity

| Check | Result |
|---|---|
| BuildArtifactEvidence E1 | ABSENT |
| Run -> Image relationship | ABSENT |
| Run -> Image Evidence | ABSENT |
| Alternative exact Run -> Image authority | NONE |
| Broken-hop proof | PASS |
| Construction blocker | NO |

## Determinism

- Repetitions: `3`
- Fresh byte-identical seed copies: YES
- Volatile fields normalized: `generated_at` only
- Deterministic analysis identity remained included in semantic comparison.
- Normalized semantic hash for repetition 1:
  `0f85e67dbe7b3121b4e849c528aa177a60b4f017468c7ca05ad70f52edeeeb5d`
- Normalized semantic hash for repetition 2:
  `0f85e67dbe7b3121b4e849c528aa177a60b4f017468c7ca05ad70f52edeeeb5d`
- Normalized semantic hash for repetition 3:
  `0f85e67dbe7b3121b4e849c528aa177a60b4f017468c7ca05ad70f52edeeeb5d`
- Result: **PASS — 3/3**

## EAI-1 artifact integrity

| Field | Frozen value |
|---|---|
| Contract | `evaluation-artifact-integrity-v1` |
| Result root | `evaluation/results/lineage/adversarial/lineage-2b-missing-run-image/` |
| Total files | 22 |
| EAI-covered ordinary files | 21 |
| Exclusion | `artifact-integrity-v1.json` self-excluded |
| Covered `artifact-hashes.json` SHA-256 | `8662f96f1756db232321465f436e717dd601bb2b8f1b6fdb13a1b4c72a041d1a` |
| EAI `tree_sha256` | `e782aa1eb797218ca420ca7bd49ed4733416976971d33ae0ff4ac5d8c74f7114` |
| Verification | VALID / PASS |
| SQLite transient files | none |

EAI was generated only after all ordinary artifacts were finalized and was
then independently reverified. This baseline does not regenerate it.

## Frozen test and regression results

These are the results from the completed measurement; they were not rerun for
this documentation-only checkpoint.

| Check | Frozen result |
|---|---|
| Focused B2 | 38 passed |
| Evaluation | 818 passed, 3 skipped |
| Evaluation skip reason | accepted Windows EAI symlink-permission cases |
| Backend | 976 passed, 1 warning |
| Agent | 15 passed |
| Compile checks | passed |
| `git diff --check` during measurement | passed |

## Product and policy freeze

B2 passed against the already accepted product behavior. No repair was
required.

| Scope | Diff |
|---|---|
| `backend/app` | none |
| `backend/tests` | none |
| SC-1 | none |
| SC-2 | none |
| SC-3 | none |
| SC-4 | none |
| AR-1 | none |
| AR-2 | none |
| AR-3 | none |
| TC-1 through TC-5 | none |
| Ranking | none |
| Agent | none |
| Frontend | none |
| CLI | none |
| Workflow | none |

## Frozen taxonomy and verdict

The contract taxonomy, in order, is:

1. `BROKEN_HOP_STILL_PRESENT`
2. `FABRICATED_RUN_IMAGE_PROVENANCE`
3. `SOURCE_CAUSE_FALSELY_SUPPORTED`
4. `UNSAFE_SOURCE_SPECIFICITY_PRESERVED`
5. `VALID_PRESERVED_EVIDENCE_CORRUPTED`
6. `EVIDENCE_SEMANTICS_DEGRADED`
7. `NONDETERMINISTIC_RESULT`
8. `NO_DIVERGENCE`

- Measured result: `NO_DIVERGENCE`
- First divergence: `NO_DIVERGENCE`
- Final verdict: `ROBUST_IN_MEASURED_MATRIX`

This verdict does not mean that TopoAI is generally correct, has 100% RCA
accuracy, handles all broken lineage, or handles all providers.

## Forensic explanation

The accepted seed originally proved Commit -> Run -> Image -> affected
runtime. B2 removed the only authoritative provider observation establishing
Run -> Image. Independent workflow evidence continued to prove Commit -> Run,
independent Kubernetes evidence continued to prove Image -> affected workload,
and runtime evidence continued to prove that the affected workload failed.

SC-2 could no longer construct exact immutable source lineage and reported
`incomplete / image_to_run_missing`. The source candidate was not admitted.
SC-4 therefore did not evaluate an immutable-lineage bridge. No source
hypothesis reached AR-2 or AR-3 support. TopoAI did not fabricate the missing
producer relationship. It preserved every independently proven truth and
safely reduced the most-specific supported causal conclusion from
`INITIATING_MUTATION` to `NONE`.

This was safe abstention, not loss of unrelated operational truth.

## Claim boundary

Approved narrow claim:

> In one controlled offline GitHub Actions/BuildKit/Kubernetes lineage
> scenario, TopoAI withheld exact source-level causal attribution when the
> authoritative Actions Run -> immutable-image provenance observation was
> removed, while preserving independently authoritative Commit -> Run,
> image-to-workload, runtime-failure, and incident-time topology evidence.

This baseline does **not** claim:

- correctness for all broken provenance cases;
- correctness for all CI providers;
- correctness for all Kubernetes incidents;
- B1 robustness;
- B3 robustness;
- ambiguous provenance correctness;
- degraded provenance correctness;
- multi-build correctness;
- statistical accuracy;
- calibrated probability; or
- production behavior.

## Broken-lineage family state

| Scenario | State |
|---|---|
| B1 / LINEAGE-2B.1 | `EXPERIMENT_CONSTRUCTION_BLOCKED`; reason `evidence_model_nonseparable`; measurement `NOT EXECUTED` |
| B2 / LINEAGE-2B.2 | `ROBUST_IN_MEASURED_MATRIX` / `NO_DIVERGENCE` |
| B3 | representable and seed-constructible; deferred |
| B4 | deferred |
| B5 | needs real seed |
| B6 | deferred |

B1 remains construction-blocked and unmeasured; it is not converted into a
PASS or FAIL.

## Result immutability

The finalized B2 result family was not rewritten. EAI was not regenerated.
No ordinary result artifact, evaluator, product implementation, frozen
contract, workflow, or other experiment was changed. This baseline records the
finalized tree exactly as measured and awaits architect review.
