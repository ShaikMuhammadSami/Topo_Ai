# LINEAGE-2A-R4 Post-AR-2 Distractor Robustness Baseline v1

Date: 2026-08-26

Accepted product commit: `aa866932ba7d0d046f3658022da80f79b963651e`

AR-2 merged commit: `aa86693`

Support policy: `causal-support-gate-v1`

Evaluation-budget policy: `causal-evaluation-budget-v1`

## 1. Checkpoint purpose

This documentation-only checkpoint freezes the accepted LINEAGE-2A-R3
measurement before AR-3. It records the unchanged adversarial matrix result
without modifying product code, evaluator semantics, the frozen LINEAGE-2A
harness, or preserved result artifacts.

Dependencies:

- `lineage-1-final-proven-source-to-runtime-causal-baseline.md`;
- `lineage-2a-distractor-source-robustness-baseline.md`;
- `ar-1-evidence-preserving-candidate-evaluation-budget-repair.md`;
- `lineage-2a-post-ar1-distractor-robustness-baseline.md`; and
- `ar-2-evidence-gated-supported-hypothesis-classification-repair.md`.

No Kubernetes, provider, registry, cloud, LLM, embedding, or other network
service was contacted during the accepted measurement.

## 2. Final result

LINEAGE-2A-R3 overall verdict:

```text
ADVERSARIAL_DIVERGENCE_FOUND
```

Previous first divergence:

```text
FALSE_SUPPORTED_DISTRACTOR
```

Did the previous first divergence disappear? **Yes.**

New first divergence:

```text
SUPPORTED_TOP1_FLIPPED
```

The first failing scenario under the frozen taxonomy is count 50, order 0.

## 3. AR-2 real-matrix result

AR-2 real-matrix gate: **PASS**.

| Metric | Pre-AR-2 | Post-AR-2 |
|---|---:|---:|
| False-supported distractors | `54` | `0` |
| Scenarios with false support | `15/16` | `0/16` |
| False-supported candidate rate | `54/258 = 20.9302%` | `0/258 = 0%` |

All 54 persisted temporal-control hypotheses retained the measured facts:

- `candidate_entity_id = null`;
- relevance `identity_unresolved`;
- topology component `0`;
- TC-4 supporting `3`;
- TC-4 contradicting `0`;
- TC-4 missing `0`;
- TC-4 unknown `0`; and
- claim types limited to `runtime_failure`, `source_change`, and
  `temporal_precedence`.

AR-2 changed only their categorical causal-support result:

```text
support: not supported
reason: insufficient_candidate_specific_evidence
evidence completeness: partial
```

The relevance gate was unsatisfied because identity remained unresolved. The
candidate-linkage gate was unsatisfied because no candidate-specific linkage
claim existed. No contradiction or missing TC-4 claim was invented.

**`FALSE_SUPPORTED_DISTRACTOR` is eliminated in this measured matrix.**

## 4. AR-2 freeze validation

The post-AR-2 measurement confirmed:

- raw candidate scores were unchanged;
- raw candidate ranks were unchanged;
- the AR-1 evaluation frontier was unchanged;
- causal relevance was unchanged;
- TC-4 evidence semantics and evidence IDs were unchanged;
- ranking coefficients were unchanged; and
- diagnostic `top_hypothesis` behavior was unchanged.

Fresh measurement-time `recorded_at` values for newly inserted controls were
expected to differ between runs. After excluding that measurement timestamp,
the TC-4 ledgers were semantically identical to the post-AR-1 ledgers. AR-2 did
not rewrite the evidence ledger.

AR-2 changed categorical causal-support qualification only.

## 5. Golden candidate stability

The exact golden source event remained:

```text
change-event:20a8946c8c445153d85c90ee2166d487
```

Its raw-rank vector remained:

| Distractor count | Golden raw rank |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 5 | 6 |
| 10 | 11 |
| 20 | 21 |
| 50 | 51 |

| Golden property | Result |
|---|---:|
| Raw-rank preservation | `16/16 = 100%` |
| Admission | `16/16 = 100%` |
| Evaluation-frontier retention | `16/16 = 100%` |
| Causal relevance | `16/16 = 100%` |
| Topology component `0.85` | `16/16 = 100%` |

The golden candidate correctly retained `candidate_entity_id = null`. Its
supported causal relevance remained based on
`exact_immutable_lineage_anchor`, candidate-specific topology/provenance
linkage, and the incident-pinned topology.

## 6. Per-count supported results

| Count | Supported result | Interpretation |
|---:|---|---|
| 0 | Golden supported Top1 | `PROVEN`-equivalent control |
| 1 | Control rejected; golden supported Top1 | AR-2 boundary passes |
| 5 | Controls rejected; golden supported Top1 | AR-1 preservation and AR-2 qualification both hold |
| 10 | Controls rejected; golden supported Top1 | AR-1 preservation and AR-2 qualification both hold |
| 20 | Controls rejected; golden supported Top1 | AR-1 preservation and AR-2 qualification both hold |
| 50 | Five controls rejected; supported set empty | Golden absent from final projection; `MISSING` / safe abstention |

## 7. Current first-divergence forensics

At count 50:

- golden raw rank was `51`;
- the ordinary shortlist contained five temporal controls;
- the AR-1 evaluation frontier contained those five temporal controls plus
  the exact-lineage golden candidate;
- frontier size was `6`;
- golden frontier position was `6`;
- golden causal relevance remained supported;
- golden topology component remained `0.85`; and
- all five retained temporal controls failed the AR-2 support gate.

The unchanged final five-hypothesis projection retained only the five
numerically higher controls before the supported subset was consumed. The
golden candidate was therefore excluded from the persisted final hypothesis
surface. Because every retained control was correctly unsupported, supported
Top1 became absent and the system safely abstained despite the presence of a
known, evaluated, relevance-supported candidate upstream.

This is the accepted current first divergence.

The defect is **not** that safe abstention occurred incorrectly in isolation.
Safe abstention is preferable to falsely supporting a temporal control. The
defect is that the pipeline discarded an already-evaluated,
evidence-supported candidate before constructing the supported causal
projection.

This observation does not establish that the repair is simply to increase the
cap.

## 8. Four-layer causal pipeline

The measured layers remain distinct:

1. **Raw candidates** — raw numerical score and ordering.
2. **Evaluation frontier** — bounded AR-1 evaluation membership.
3. **Evaluated hypotheses** — causal relevance, TC-4 evidence, and the AR-2
   support gate.
4. **Final/persisted projection** — the existing bounded hypothesis
   projection.

The current divergence occurs between layers 3 and 4. It does not occur in raw
candidate discovery, AR-1 frontier selection, causal relevance, TC-4 evidence,
or AR-2 support qualification.

## 9. Diagnostic `top_hypothesis`

`top_hypothesis` remained intentionally diagnostic and ranking-oriented:

- count 0: the golden candidate; and
- every non-zero count: a high-scoring temporal control.

AR-2 intentionally did not change this behavior. A high-scoring control may
remain diagnostic while being categorically unsupported. The diagnostic
projection itself is not the current defect; the measured divergence concerns
the supported causal projection.

## 10. Supported and raw results

| Metric | Result |
|---|---:|
| Supported Top1 golden | `13/16` |
| Supported Top1 flip | `3/16 = 18.75%` |
| Supported Top3 retention | `13/16 = 81.25%` |
| Golden supported rank when retained | `1` only |
| Safe abstentions | `3/16` |
| Raw Top1 flip | `15/16 = 93.75%` |
| Raw Top3 retention | `4/16 = 25%` |

All safe abstentions occurred at count 50, orders 0, 1, and 2. Raw behavior
remained unchanged and is not itself the current causal failure.

## 11. Support-gate and TC-4 results

The golden support-gate audit was exposed and passed in all `13/13` persisted
golden hypotheses. Its candidate-linkage claim types remained
`relationship_provenance` and `topology_path`.

At count 50, the golden hypothesis was removed before its support-gate audit
became part of the final persisted hypothesis surface. Absence of that
persisted audit is not a relevance failure. The upstream persisted surfaces
already established that the candidate remained in the evaluation frontier,
retained supported causal relevance, and retained topology component `0.85`.

Golden TC-4 where persisted remained:

```text
5 supporting
0 contradicting
0 missing
0 unknown
```

Temporal-control TC-4 remained:

```text
3 supporting
0 contradicting
0 missing
0 unknown
```

AR-2 did not rewrite either ledger.

## 12. Order determinism

Order sensitivity remained:

```text
0/5 = 0%
```

All insertion-order permutations were deterministic for:

- raw results;
- the AR-1 frontier;
- support-gate results;
- supported results; and
- analysis IDs and normalized analysis hashes.

## 13. Pre/post AR-2 comparison

| Metric | Pre-AR-2 | Post-AR-2 |
|---|---:|---:|
| Golden admission | 100% | 100% |
| Golden frontier retention | 100% | 100% |
| Golden relevance | 100% | 100% |
| Golden evidence completeness | 81.25% | 81.25% |
| False-supported candidates | 54 | 0 |
| False-supported scenarios | 15/16 | 0/16 |
| Supported Top1 flip | 93.75% | 18.75% |
| Supported Top3 retention | 62.5% | 81.25% |
| Raw Top1 flip | 93.75% | 93.75% |
| Raw Top3 retention | 25% | 25% |
| Safe abstentions | 0 | 3 |
| Order sensitivity | 0% | 0% |

## 14. Result identities

Result family:

```text
evaluation/results/lineage/adversarial/lineage-2a-post-ar2/
```

| Artifact | SHA-256 |
|---|---|
| Manifest | `C188951D0FBA220555DFBF18D6680F24176711D5491FE21C8D3EEDAA15D2DAA2` |
| Aggregate | `46232BA4885F394C53AE0D97532929702A0325D4C6BF3065A2DEC1D2061D65F5` |
| Inventory | `5743E6D423C03ADF0C9329B25D3EECF8765AA8A910B3D086FBCF6615052FECAE` |
| Result tree | `A4A3FA74DA4DDFB46215817BA5CB2597D5B0FE68ABF0F8CAFA5F15B7D789A93D` |

The result family contains 131 files. All `114/114` inventory entries were
validated.

## 15. Historical result integrity

The accepted measurement verified that:

- the original LINEAGE-2A result family remained unchanged;
- the post-AR-1 result family remained unchanged;
- the seed database remained
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`;
- all golden post-SC4 artifacts remained unchanged; and
- the failure branch continued to resolve exactly to
  `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`.

## 16. Next approved repair candidate

Name:

```text
AR-3 — Evidence-Preserving Final Hypothesis Projection
```

Target only:

```text
SUPPORTED_TOP1_FLIPPED
```

Measured trigger: count 50, order 0.

AR-3 is not authorized to simultaneously modify:

- raw Top1 or raw Top3;
- the AR-1 evaluation frontier;
- the AR-2 support gate;
- causal relevance;
- TC-4;
- score coefficients;
- Path A;
- SC-2, SC-3, or SC-4; or
- diagnostic `top_hypothesis`.

Architectural question:

> How should bounded final hypothesis projection preserve evidence-qualified
> causal hypotheses without allowing unsupported high-scoring hypotheses to
> consume the entire supported-causal projection budget?

This checkpoint does not prescribe the implementation. AR-3 must not be
implemented as merely increasing the final cap.

## 17. Claim boundary

This matrix proves that:

- AR-1 preserved the golden cause into relevance evaluation under the measured
  distractor pressure;
- AR-2 eliminated the measured false-support defect;
- support gating can reject high-scoring unresolved controls while leaving raw
  ranking unchanged; and
- a deterministic downstream final-projection defect remains at count 50.

It does not prove:

- generalized robustness;
- statistical reliability;
- live concurrent ingestion;
- broken-lineage behavior;
- multi-file attribution;
- all Kubernetes incidents; or
- all providers.

## 18. Checkpoint boundary

This checkpoint creates one documentation file only. It does not modify
product, backend tests, evaluator, agent, frontend, CLI, workflow, harness, or
existing baseline files. It does not rerun the matrix or implement AR-3.
