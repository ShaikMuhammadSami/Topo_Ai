# AR-1 Evidence-Preserving Candidate Evaluation Budget Repair

Status: product repair implemented; frozen LINEAGE-2A experiment not rerun.

Branch: `feature/ar-1-evidence-preserving-candidate-evaluation-budget-v1`

## Repair target

AR-1 repairs exactly the first LINEAGE-2A divergence:

```text
GOLDEN_CAUSAL_RELEVANCE_LOST
```

The accepted frozen result showed that the golden source mutation remained
admitted through exact immutable lineage but was excluded from relevance when
its raw ranks were 6, 11, 21, and 51 behind 5, 10, 20, and 50 distractors.

The separate temporal-distractor false-support observation remains frozen and
unrepaired. AR-1 provides evaluation opportunity; it does not change relevance,
evidence, support, or ranking outcomes.

## Before

```text
LINEAGE-1: PROVEN
LINEAGE-2A: ADVERSARIAL_DIVERGENCE_FOUND
golden admission: 100%
golden relevance: 25%
first divergence: GOLDEN_CAUSAL_RELEVANCE_LOST
```

The measured trigger was five recent temporal controls. The golden candidate's
raw rank was 6, the existing evaluation cap was 5, and the candidate was
omitted before relevance. With 50 distractors its raw rank was 51.

The frozen run also found false-supported temporal controls. That is a
secondary finding and AR-1 does not repair it.

## Product change

`causal-evaluation-budget-v1` forms the causal evaluation frontier from:

```text
existing ordinary candidate-policy Top-K
  union
already-admitted causal-candidate-admission-v2 exact immutable-lineage changes
```

The existing candidate policy must also classify a preserved candidate as
primary-eligible or fallback-eligible; AR-1 never revives an ineligible or
supporting-only record.

The ordinary shortlist stays at its existing default of five. A dual-basis
candidate is evaluated once. The evidence-preserved candidate keeps its raw
score and raw rank. No lineage/evaluation bonus exists.

SC-2 proves at most one admitted source candidate for the current product
contract, so the default frontier is bounded at six before overlap. AR-1 does
not truncate protected candidates.

## After target

The raw Top-5 remains unchanged. An exact-lineage admitted candidate receives
bounded evidence-preserving evaluation even when it is outside that Top-5. Its
raw score and rank are unchanged, it receives no bonus, and existing relevance,
TC-4, support, and ranking semantics decide the downstream result.

## Durable audit and compatibility

New immutable analyses persist:

- `evaluation_policy_version = causal-evaluation-budget-v1`;
- per-candidate evaluation selection bases and frontier position; and
- a bounded budget summary.

The policy version participates in the analysis fingerprint. Historical
payloads load without fabricated AR-1 metadata and are not rewritten. No
database migration is needed.

## Frozen semantics

The following remain unchanged:

- raw candidate discovery, score, order, tie behavior, and Top-K identities;
- Path A 180-minute lookback;
- SC-2, SC-3, and SC-4 policies;
- `causal-relevance-v2` and its zero-score lineage bridge;
- TC-4 ledger and claim enum;
- TC-5 support/confidence;
- `13c-causal-v1` scoring and final hypothesis cap;
- incident, runtime, deployment-health, and topology graph behavior; and
- all LINEAGE-2A evaluator, fixture, workflow, and baseline artifacts.

## Product-test evidence

Focused AR-1 tests cover:

- raw ranks 6, 11, 21, and 51 entering evaluation only through exact lineage;
- unchanged raw Top-5 identities and scores;
- six and fifty temporal-only candidates retaining a five-member frontier;
- strict rejection of incomplete, ambiguous, wrong-policy, basis-missing, and
  similarity/risk/age-only candidates;
- dual-basis deduplication and deterministic basis order;
- insertion-order-independent membership/order;
- no protected slicing and the existing SC-2 maximum-one proof;
- one relevance handoff per candidate and no duplicate TC-4 ledger;
- persisted fresh-session audit readback;
- historical readback without fabricated metadata;
- unknown policy rejection;
- unchanged `13c-causal-v1` formula and final hypothesis cap; and
- absence of network, LLM, embedding, sentinel, namespace, or digest special
  casing in the generic evaluation policy.

## Measurement boundary

This checkpoint does not claim that the golden candidate becomes supported,
Top1, or Top3. It does not claim the known distractor false-support defect is
fixed. A fresh, separately authorized LINEAGE-2B run is required to measure the
post-repair causal outcome.
