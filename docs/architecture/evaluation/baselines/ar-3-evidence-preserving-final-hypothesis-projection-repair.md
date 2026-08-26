# AR-3 Evidence-Preserving Final Hypothesis Projection Repair

This document records the product repair target derived from the accepted
post-AR-2 LINEAGE-2A adversarial baseline. It is not a post-repair evaluator
result and does not claim LINEAGE-2A robustness.

## Before AR-3

- Overall: `ADVERSARIAL_DIVERGENCE_FOUND`
- First divergence: `SUPPORTED_TOP1_FLIPPED`
- First failing scenario: distractor count 50, insertion order 0
- Golden raw rank: 51
- Golden AR-1 frontier position: 6
- Golden relevance: supported
- Golden topology component: 0.85
- Five higher-score temporal controls: AR-2 support gate failed
- Golden exact-lineage candidate: AR-2 support gate passed upstream

The AR-1 frontier contained five controls plus the golden source candidate.
All six received relevance, TC-4 ledger, and AR-2 classification. The old final
projection then sorted by existing causal score, truncated to five, and only
afterward allowed consumers to filter for support. The controls occupied every
persisted slot, the golden hypothesis disappeared, and the supported set was
empty.

That result was a safe abstention and was preferable to false attribution, but
it was still a final-projection defect because a support-qualified hypothesis
had already been fully evaluated inside the bounded frontier.

## AR-3 target

AR-3 introduces `causal-hypothesis-projection-v1` and preserves one canonical
bounded evaluated-hypothesis collection with ID-based diagnostic and supported
projections.

For the measured count-50 shape, the target is:

- canonical evaluated collection: five controls plus golden;
- diagnostic projection: five controls, unchanged order;
- golden diagnostic position: 6, outside diagnostic Top-5;
- diagnostic `top_hypothesis`: highest-scoring control, unchanged;
- supported projection: golden;
- supported Top1: golden;
- projection dropped supported count: 0.

Evidence qualification occurs before applying the supported-output limit.
Unsupported controls therefore consume zero supported slots.

## Frozen semantics

The repair leaves unchanged:

- all raw scores and raw ranks;
- the default cap value of 5;
- the `13c-causal-v1` scoring coefficients;
- AR-1 `causal-evaluation-budget-v1` frontier membership and ordering;
- AR-2 `causal-support-gate-v1` classifications;
- `causal-relevance-v2` output and topology component;
- TC-4 ledger claims and evidence references;
- SC-2, SC-3, and SC-4;
- the 180-minute temporal path;
- the frozen LINEAGE-2A harness and accepted baselines.

The cap value is not expanded. It is applied independently after diagnostic
ordering and after supported qualification. No golden slot, score bonus,
evidence multiplier, or raw-candidate reopening is introduced.

## Validation boundary

Focused product tests establish the intended projection contract, persistence,
historical compatibility, deterministic tie-break, safe abstention, multiple
supported hypotheses, and supported-cap overflow. They do not establish that
the full adversarial matrix is now robust.

After architect review and merge, the exact same frozen 16-run LINEAGE-2A
matrix must be rerun on clean main. Only that rerun can determine whether
`SUPPORTED_TOP1_FLIPPED` disappears and whether a later divergence exists.
