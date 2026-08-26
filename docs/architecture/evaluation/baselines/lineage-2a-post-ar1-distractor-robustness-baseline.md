# LINEAGE-2A-R2 Post-AR-1 Distractor Robustness Baseline v1

Date: 2026-08-26

Accepted product commit: `49f5c7df5c72bc7f6d62c4185223bdcd92d056c5`

AR-1 merged commit: `49f5c7d`

Evaluation policy: `causal-evaluation-budget-v1`

## 1. Checkpoint purpose

This documentation-only checkpoint freezes the accepted LINEAGE-2A-R1
measurement before AR-2. It records the unchanged adversarial matrix results
without modifying product code, evaluator semantics, the frozen harness, or
the preserved result artifacts.

Dependencies:

- `lineage-1-final-proven-source-to-runtime-causal-baseline.md`;
- `lineage-2a-distractor-source-robustness-baseline.md`; and
- `ar-1-evidence-preserving-candidate-evaluation-budget-repair.md`.

## 2. Final result

LINEAGE-2A-R1 overall verdict:

```text
ADVERSARIAL_DIVERGENCE_FOUND
```

Previous first divergence:

```text
GOLDEN_CAUSAL_RELEVANCE_LOST
```

Did the previous first divergence disappear? **Yes.**

New first divergence:

```text
FALSE_SUPPORTED_DISTRACTOR
```

The first failing scenario under the frozen taxonomy is count 1, order 0.

## 3. AR-1 real-path result

AR-1 repaired its measured evaluation-frontier defect in the real adversarial
matrix.

| Golden property | Result |
|---|---:|
| Admission | `16/16 = 100%` |
| Evaluation-frontier retention | `16/16 = 100%` |
| Causal relevance | `16/16 = 100%` |
| Topology component `0.85` | `16/16 = 100%` |

The golden raw ranks remained exactly:

| Distractor count | Golden raw rank |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 5 | 6 |
| 10 | 11 |
| 20 | 21 |
| 50 | 51 |

Raw-rank preservation was 100%. Ordinary shortlist behavior was unchanged.

The evaluation-frontier sizes were:

| Distractor count | Frontier size |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 5 | 6 |
| 10 | 6 |
| 20 | 6 |
| 50 | 6 |

`GOLDEN_CAUSAL_RELEVANCE_LOST` is eliminated in this measured matrix.

## 4. Strict AR-1 gate nuance

The strict AR-1 real-matrix gate is **FAIL**.

Golden evidence completeness was retained in `13/16 = 81.25%`, not 16/16.
All three failures were count-50 runs.

At count 50, the golden candidate:

- remained admitted;
- remained in the AR-1 evaluation frontier;
- reached `causal-relevance-v2`;
- remained relevance-supported; and
- retained topology component `0.85`.

It was then dropped behind the unchanged final five-hypothesis cap. This does
not mean AR-1 failed to repair `GOLDEN_CAUSAL_RELEVANCE_LOST`; it is a downstream
hypothesis-projection/cap observation.

That observation does not authorize repair yet. The frozen taxonomy has an
earlier divergence at count 1: `FALSE_SUPPORTED_DISTRACTOR`.

## 5. New first divergence

The first falsely supported distractor was:

```text
change-event:05a3d2361472923f5d545eaca1981f35
```

Scenario: count 1, order 0.

| Dimension | Observation |
|---|---|
| Raw rank | `1` |
| Raw score | `50.65` |
| Evaluation basis | ordinary only |
| `candidate_entity_id` | `null` |
| Causal relevance | `identity_unresolved` |
| Topology component | `0.0` |
| TC-4 supporting | `3` |
| TC-4 contradicting | `0` |
| TC-4 missing | `0` |
| TC-4 unknown | `0` |
| Support classification | `supported_under_current_model` |
| Evidence completeness | `complete_for_current_model` |
| Final score | `39.45` |
| Supported rank | `1` |

The TC-4 claim types were only:

- `runtime_failure`;
- `source_change`; and
- `temporal_precedence`.

There was no accepted `topology_path` or `relationship_provenance` claim.

## 6. Forensic interpretation

The candidate has temporal, source, and runtime context but no resolved causal
relevance to the affected runtime topology. The product nevertheless treats
the absence of contradicting or missing ledger entries as sufficient for
support. This allows an identity-unresolved, topology-unconnected candidate to
become a supported causal hypothesis.

Temporal precedence is not equivalent to causal relevance. A generic runtime
failure claim is incident evidence, not candidate-specific proof that a source
change caused the failure.

This baseline records the observation; it does not prescribe the final repair
implementation.

## 7. False-support matrix

| Metric | Result |
|---|---:|
| False-supported distractor hypotheses | `54` |
| Scenarios with false support | `15/16` |
| False-supported candidate rate | `54/258 = 20.9302%` |
| Safe abstention | `0/16` |

All 54 falsely supported candidates shared this pattern:

- ordinary-only candidate;
- `candidate_entity_id = null`;
- relevance `identity_unresolved`;
- topology component `0`;
- TC-4 `3 supporting / 0 contradicting / 0 missing / 0 unknown`;
- claim types limited to `runtime_failure`, `source_change`, and
  `temporal_precedence`; and
- classified supported.

## 8. Supported and raw results

| Metric | Result |
|---|---:|
| Supported Top1 flip | `15/16 = 93.75%` |
| Supported Top3 retention | `10/16 = 62.5%` |
| Golden supported rank when present | `1` through `5` |
| Golden absent | three count-50 runs |
| Raw Top1 flip | `15/16 = 93.75%` |
| Raw Top3 retention | `4/16 = 25%` |

Raw-ranking changes are not themselves the new causal failure. The defect is
false support despite unresolved causal relevance.

## 9. Golden evidence distinction

When retained, golden TC-4 remained:

```text
5 supporting
0 contradicting
0 missing
0 unknown
```

Golden evidence completeness was `13/16 = 81.25%`, while golden relevance was
`16/16 = 100%`. These are separate properties and must not be conflated.

## 10. Order determinism

Order sensitivity was `0/5 = 0%`.

All nonzero counts produced deterministic:

- raw results;
- evaluation frontiers;
- supported results; and
- analysis IDs and normalized hashes.

The observed failure is deterministic under the measured matrix.

## 11. Pre/post AR-1 comparison

| Metric | Pre-AR-1 | Post-AR-1 |
|---|---:|---:|
| Golden admission | 100% | 100% |
| Golden frontier retention | 25% | 100% |
| Golden relevance | 25% | 100% |
| Golden evidence completeness | 25% | 81.25% |
| Supported Top1 flip | 93.75% | 93.75% |
| Supported Top3 retention | 25% | 62.5% |
| Raw Top1 flip | 93.75% | 93.75% |
| Raw Top3 retention | 25% | 25% |
| False-supported candidates | 63 | 54 |
| False-supported scenarios | 15/16 | 15/16 |
| Order sensitivity | 0% | 0% |

## 12. Result identities and integrity

Result family:

```text
evaluation/results/lineage/adversarial/lineage-2a-post-ar1/
```

| Artifact | SHA-256 |
|---|---|
| Manifest | `C188951D0FBA220555DFBF18D6680F24176711D5491FE21C8D3EEDAA15D2DAA2` |
| Aggregate | `C4137A31A872EACB431399701D27FADD592506912FF780458D73C74F678F0426` |
| Inventory | `DDA6C94F12C2F41BBCA04D0266A870FEBA1BC3C99120352B8AA5F5B5F87AEF35` |
| Result tree | `4F601DDEA2C0FA25C2A96601D8D7B1E1365B012C2AECFEEA99A33D627EBA1F21` |

The result family contains 114 JSON inventory entries and 131 total files,
with zero inventory mismatches.

The original LINEAGE-2A result tree remained:

```text
44FF3FB6B43C52C6EA181A639FD2F2D45418602D95184B6CCDFE35311A408144
```

The seed database remained:

```text
9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F
```

The golden post-SC4 database remained byte-identical and SQLite-valid.

## 13. Next approved repair boundary

The next repair candidate is:

```text
AR-2 — Evidence-Gated Supported-Hypothesis Classification
```

AR-2 targets only `FALSE_SUPPORTED_DISTRACTOR`. It must not simultaneously
repair:

- the final five-hypothesis cap;
- raw Top1 or raw Top3;
- the AR-1 evaluation budget;
- causal relevance semantics;
- ranking coefficients;
- Path A;
- SC-2;
- SC-3; or
- SC-4.

The count-50 final hypothesis-cap observation remains queued behind the earlier
false-support divergence.

Architectural question for AR-2:

> What minimum candidate-specific evidence/relevance state must be required
> before a causal hypothesis may be labeled "supported"?

The repair must preserve safe abstention and must not simply add a score
threshold.

## 14. Claim boundary

This adversarial matrix proves that:

- AR-1 preserves exact-lineage evaluation opportunity under up to 50 measured
  temporal distractors;
- the current support classifier falsely supports topology-unresolved temporal
  distractors; and
- the behavior is deterministic in the measured matrix.

It does not prove:

- general statistical robustness;
- live concurrent ingestion;
- broken-lineage behavior;
- multi-file attribution;
- all Kubernetes incidents; or
- all source/provider systems.

## 15. Checkpoint boundary

This checkpoint changes documentation only. It does not modify product code,
evaluator code, the LINEAGE-2A harness, existing baselines, result artifacts,
support classification, TC-4, causal relevance, or ranking. It does not start
AR-2.
