# LINEAGE-2A-R6 Final Clean Distractor Robustness Baseline v1

Date: 2026-08-27

Branch: `evaluation/lineage-2a-final-clean-baseline-v1`

Accepted product commit: `07ff72051ccf6c492336f484ce26614f0eb02b13`

AR-3 merged commit: `07ff720`

Final verdict: **`ROBUST_IN_MEASURED_MATRIX`**

Frozen first-divergence taxonomy result: **`NO_DIVERGENCE`**

First failing count/order: **none**

## 1. Checkpoint purpose

This documentation-only checkpoint freezes the accepted post-AR-3
LINEAGE-2A-R5 measurement. It closes the LINEAGE-2A repair loop for the frozen
controlled matrix without modifying product code, evaluator code, the frozen
harness, existing baselines, or preserved result artifacts.

The policies present at the accepted product commit are:

- `causal-candidate-admission-v2`;
- `causal-evaluation-budget-v1`;
- `causal-relevance-v2`;
- `causal-support-gate-v1`; and
- `causal-hypothesis-projection-v1`.

This checkpoint depends on, but does not modify:

- `lineage-1-final-proven-source-to-runtime-causal-baseline.md`;
- `lineage-2a-distractor-source-robustness-baseline.md`;
- `lineage-2a-post-ar1-distractor-robustness-baseline.md`;
- `lineage-2a-post-ar2-distractor-robustness-baseline.md`;
- `ar-1-evidence-preserving-candidate-evaluation-budget-repair.md`;
- `ar-2-evidence-gated-supported-hypothesis-classification-repair.md`; and
- `ar-3-evidence-preserving-final-hypothesis-projection-repair.md`.

## 2. Frozen experiment

The matrix and temporal-distractor contract were unchanged from the original
accepted LINEAGE-2A experiment.

Distractor counts were:

```text
0
1
5
10
20
50
```

Count 0 used insertion order 0. Every non-zero count used insertion orders 0,
1, and 2. The matrix therefore contained 16 scenarios.

| Matrix property | Accepted result |
|---|---:|
| Total scenarios | `16` |
| Valid scenarios | `16/16` |
| Invalid scenarios | `0` |
| First failing count/order | `NONE` |

The distractors remained deterministic temporal-only noncausal controls. They
had ordinary Path A temporal admission but no immutable lineage, candidate
topology identity, golden source revision, golden CI run, golden image,
affected topology entity, provider-backed golden lineage, or product-visible
expected-answer hint.

## 3. Final golden metrics

| Golden property | Accepted result |
|---|---:|
| Admission | `16/16 = 100%` |
| AR-1 frontier retention | `16/16 = 100%` |
| Causal relevance | `16/16 = 100%` |
| Topology component `0.85` | `16/16 = 100%` |
| Evidence completeness | `16/16 = 100%` |
| Supported Top1 | `16/16 = 100%` |
| Supported Top3 | `16/16 = 100%` |

The golden raw-rank vector by distractor count was:

```text
1
2
6
11
21
51
```

The golden cause does not need to become raw Top1 for the evidence-backed RCA
result to be correct. Raw rank is heuristic suspicion; supported projection is
the evidence-qualified causal surface.

## 4. Final distractor metrics

| Distractor property | Accepted result |
|---|---:|
| False-supported distractors | `0` |
| False-supported scenarios | `0/16` |
| False-supported candidate rate | `0/258 = 0%` |

Every evaluated temporal control retained:

```text
candidate_entity_id = null
relevance = identity_unresolved
topology component = 0

TC-4:
3 supporting
0 contradicting
0 missing
0 unknown
```

Its claim types remained:

- `runtime_failure`;
- `source_change`; and
- `temporal_precedence`.

The controls remain diagnostically visible when highly ranked, but they are
not considered supported causes. Their AR-2 result remains
`insufficient_candidate_specific_evidence` because relevance and
candidate-linkage gates are unsatisfied.

## 5. Final projection metrics

The diagnostic and supported caps both remained `5`. No cap value increased.

| Layer | Vector for counts `0, 1, 5, 10, 20, 50` |
|---|---|
| AR-1 evaluation frontier | `1, 2, 6, 6, 6, 6` |
| Canonical evaluated hypotheses | `1, 2, 6, 6, 6, 6` |
| Diagnostic projection | `1, 2, 5, 5, 5, 5` |
| Supported projection | `1, 1, 1, 1, 1, 1` |

`projection_dropped_supported_count` was `0` in every scenario.

Safe abstentions were `0`. Insertion-order sensitivity was `0/5 = 0%`.

The canonical collection never exceeded the bounded AR-1 frontier. AR-3 did
not reopen the raw candidate set. The sixth canonical hypothesis at counts 5,
10, 20, and 50 was the already-preserved AR-1 frontier member, not a cap
increase or a second candidate search.

## 6. Count-50 final proof

| Dimension | Accepted result |
|---|---|
| Raw candidates | `51` |
| Golden raw rank | `51` |
| Ordinary shortlist | `5` |
| AR-1 frontier | `6` |
| Canonical evaluated hypotheses | `6` |
| Diagnostic projection | five temporal controls |
| Golden diagnostic inclusion | `false` |
| Golden diagnostic reason | `diagnostic_projection_cap_reached` |
| Diagnostic `top_hypothesis` | highest-scoring temporal control |
| Supported projection | golden only |
| Golden supported rank | `1` |
| `projection_dropped_supported_count` | `0` |

All five controls failed the AR-2 support gate. The golden candidate retained:

- supported causal relevance through `exact_immutable_lineage_anchor`;
- topology component `0.85`;
- TC-4 `5 supporting / 0 contradicting / 0 missing / 0 unknown`; and
- an AR-2 support-gate pass.

Unsupported hypotheses consume zero supported-projection capacity.

## 7. Repair progression

The measured first-divergence progression is preserved explicitly:

```text
Original LINEAGE-2A
    first divergence: GOLDEN_CAUSAL_RELEVANCE_LOST

AR-1: causal-evaluation-budget-v1
    golden relevance restored to 16/16
    next divergence: FALSE_SUPPORTED_DISTRACTOR

AR-2: causal-support-gate-v1
    false-supported distractors reduced from 54 to 0
    next divergence: SUPPORTED_TOP1_FLIPPED

AR-3: causal-hypothesis-projection-v1
    Supported Top1 increased from 13/16 to 16/16
    Supported Top3 increased from 13/16 to 16/16
    evidence completeness increased from 13/16 to 16/16

Final taxonomy: NO_DIVERGENCE
```

Each repair targeted the first then-current measured divergence. The final
passing result does not erase or reinterpret that history.

## 8. Final four-layer causal model

The accepted pipeline retains four separate meanings:

1. **Raw candidate ranking** — heuristic suspicion.
2. **AR-1 evaluation frontier** — bounded deep-evaluation opportunity.
3. **Evidence evaluation** — `causal-relevance-v2`, TC-4, and
   `causal-support-gate-v1`.
4. **AR-3 projection** — separate diagnostic and supported projections over
   the canonical bounded evaluated set.

Diagnostic suspicion and evidence-supported causality are intentionally
distinct. The diagnostic projection may contain unsupported high-scoring
candidates. The supported projection contains only hypotheses that pass the
evidence gate.

## 9. Score and ranking freeze

| Candidate | Raw score | Final score | Final support result |
|---|---:|---:|---|
| Golden exact-lineage cause | `9.8` | `30.17` | Supported Top1 |
| Count-50 highest temporal control | `50.65` | `39.45` | Unsupported |

The temporal control retained the higher heuristic scores and diagnostic
`top_hypothesis` position. The golden cause remained Supported Top1. This
proves that the measured repair did not rely on rewriting heuristic scores or
forcing the golden cause to raw or diagnostic Top1.

## 10. Result identities

Final ignored result family:

```text
evaluation/results/lineage/adversarial/lineage-2a-post-ar3/
```

| Artifact | SHA-256 |
|---|---|
| Manifest | `C188951D0FBA220555DFBF18D6680F24176711D5491FE21C8D3EEDAA15D2DAA2` |
| Aggregate | `35DF70D0851C210EA52886AFB5F8BF34B0E9746F26006AAE9014700B864BD19E` |
| Inventory | `2E537DE9D71EB7292F026676D3502C9926BB914234559E9E77C62F8BA3F14563` |
| Result tree | `6EEA3A9715072BC36F361363918A37C3327094BD0ECDCA27FA274DAABA3A7638` |

The result family contains 131 files, including 115 JSON files. All 114/114
inventory entries validated.

## 11. Seed identity and integrity

Seed database:

```text
evaluation/results/lineage/post-sc4/topo-product-32695735269.db
```

Accepted SHA-256:

```text
9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F
```

| Check | Accepted result |
|---|---|
| SQLite `quick_check` | `ok` |
| SQLite `integrity_check` | `ok` |
| Post-run byte identity | exact |

Every scenario used an isolated byte-identical copy. The seed remained
byte-identical.

## 12. Legacy result-tree hash discrepancy

The accepted R5 verification found a historical bookkeeping discrepancy that
must remain visible. The original LINEAGE-2A and post-AR-1 result families
were byte-stable before and after R5, and their inventories and published
component hashes validated. Recomputing a full-tree hash with the current R5
tree-hashing procedure, however, did not reproduce some older
baseline-published full-tree hashes.

Current R5 pre/post values were:

| Result family | Current R5 tree SHA-256 |
|---|---|
| Original LINEAGE-2A | `3066065131691E4D10DF8F7BE075A75D9085648F217930A4282BC2F9256DF665` |
| Post-AR-1 | `E169A63C2CC9ADFE1EAC5E00EB2F8588A7A7431EBAD4ABD2B0FA1CCF9BA88165` |
| Post-AR-2 | `A4A3FA74DA4DDFB46215817BA5CB2597D5B0FE68ABF0F8CAFA5F15B7D789A93D` |

The accepted interpretation is:

- the original and post-AR-1 trees were unchanged during R5;
- published component hashes remain consistent;
- artifact inventories self-validate;
- this is a legacy result-tree hashing/reproduction bookkeeping discrepancy;
- it does not alter the accepted R5 causal result; and
- historical baseline values are not rewritten.

Architect-review question:

> Should one canonical result-tree hashing algorithm and file-scope contract
> be frozen before the next adversarial family?

This checkpoint does not implement or authorize a hashing change.

## 13. Failure revision integrity

The controlled failure revision remains exactly:

```text
4149b194c4c4fdfdcd402a157c5336ad59dfdbbe
```

## 14. Claim boundary

For the frozen controlled Kubernetes source-to-runtime scenario and measured
temporal-distractor counts through 50, this matrix establishes that:

- the golden exact-lineage cause remains admitted;
- the golden cause remains in the bounded evaluation frontier;
- causal relevance remains intact;
- temporal-only distractors are not falsely supported;
- diagnostic ranking may remain distractor-dominated;
- the supported projection retains the evidence-qualified golden cause; and
- the result is deterministic across the measured insertion orders.

It does not establish:

- general statistical robustness;
- correctness for all Kubernetes failures;
- correctness for all source providers;
- broken-lineage robustness;
- multi-file causal attribution;
- multiple-build ambiguity behavior;
- multi-container ambiguity behavior;
- behavior with multiple independently supported causes; or
- production-scale concurrency.

This checkpoint must not be cited as generalized RCA correctness.

## 15. Repair-loop status and next evaluation recommendation

```text
LINEAGE-2A repair loop: CLOSED
```

No AR-4 repair is authorized. The next step is senior architect review of this
clean baseline. Expansion to another adversarial family requires separate
approval after that review.

The recommended next adversarial family is **broken immutable lineage**, with
potential future scenarios such as:

- missing Commit -> Run;
- missing Run -> Image; and
- missing Image -> Workload.

The expected principle is to abstain or reduce specificity and never fabricate
missing provenance. This is a recommendation only; no such scenario is created
or executed by this checkpoint.

## 16. Checkpoint boundary

This checkpoint creates this documentation file only. It does not modify
product code, backend tests, evaluator code, the frozen harness, agent,
frontend, CLI, workflows, existing baselines, result artifacts, repair
policies, or cap values. It does not rerun LINEAGE-2A, start AR-4, or create
LINEAGE-2B.
