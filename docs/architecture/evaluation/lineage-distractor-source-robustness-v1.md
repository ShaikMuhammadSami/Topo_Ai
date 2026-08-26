# LINEAGE-2A Distractor Source Robustness Contract v1

## Purpose

LINEAGE-2A measures whether TopoAI's evidence-supported source-to-runtime causal result remains stable when plausible but independently known-noncausal source changes are added near a frozen incident boundary.

This is an offline perturbation evaluation. It does not exercise live concurrent provider ingestion, Kubernetes, GitHub, GHCR, network services, an LLM, embeddings, or fuzzy matching.

## Frozen dependency

The evaluator requires the accepted post-SC4 database produced by LINEAGE-1L:

- path: `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`
- SHA-256: `9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f`
- golden causal event: `change-event:20a8946c8c445153d85c90ee2166d487`
- incident boundary: `2026-08-26T05:09:49Z`
- pinned snapshot: `snapshot:actions-enriched:20260826T051031Z:2d8416d3`

Before a run, the harness verifies file existence, exact SHA-256, SQLite `quick_check`, and SQLite `integrity_check`. It opens the seed only through a `mode=ro&immutable=1` URI with `PRAGMA query_only=ON`. Every scenario operates on a byte-for-byte copy.

## Safe reanalysis mechanism

Each scenario starts from a clean copy of the same seed. The product's existing `ingest_change_event()` service persists the controls, and `analyze_causal_rca(..., persist=True)` performs the analysis.

No analysis state is deleted or reset:

- count 0 has the same deterministic input fingerprint and exercises immutable reuse of the accepted causal analysis;
- nonzero counts change the sorted candidate-event set in the product fingerprint, creating a fresh deterministic analysis record inside only that scenario copy;
- source evidence, build evidence, topology, incident identity, incident boundary, pinned snapshot, and affected entity remain unchanged.

## Distractor construction

For each `(count, ordinal)`, the harness deterministically derives:

- an independent synthetic repository;
- a distinct 40-character revision;
- a canonical external identity and expected product event ID;
- a bounded risk score from 65 through 84;
- a source-event time between 5 and 175 minutes before the incident.

The controls use the current `ChangeEventCreate` contract with source `github`, kind `code`, environment `evaluation`, and incident-compatible cluster/namespace scope. They contain no entity references, golden commit, golden producer run, golden image digest, build evidence, or immutable lineage.

The product-visible input contains no `noncausal`, `distractor`, `expected=false`, or equivalent answer hint. The `NONCAUSAL_CONTROL` classification and its independent rationale exist only in each scenario's evaluator ground truth.

## Matrix and insertion order

Counts are exactly `0, 1, 5, 10, 20, 50`. Count 0 has one run. Every nonzero count has insertion-order seeds `0, 1, 2`, for 16 runs total.

For a given count, all three runs have an identical event set. Only a deterministic permutation derived from scenario version, count, and order seed changes. No UUID or wall-clock value determines control identity or effective time.

## Validity invariants

Before a scenario can be graded, the harness verifies:

- the golden event and mutation each occur exactly once;
- the exact immutable lineage and SC2 admission remain available;
- the golden image anchor, incident, boundary, pin, and affected entity are unchanged;
- every control exists exactly once and is inside ordinary temporal Path A;
- no control has exact immutable lineage or golden producer/image/entity evidence.

Invariant failure yields `INVALID`, not a product failure.

## Raw and supported surfaces

Raw order comes from `candidate_selection_audit.raw_rank`. Evidence-supported hypotheses are product hypotheses whose TC5 `confidence_semantics.evidence_state` is `supported_under_current_model`.

The evaluator records raw Top1/Top3 and supported Top1/Top3 independently. A raw-rank movement alone is not an adversarial causal failure. The structured golden match compares eight exact initiating-mutation fields and never uses title tokens, fuzzy matching, embeddings, or an LLM.

## Metrics

- supported Top1 flip: supported Top1 is not the golden event, including no supported Top1;
- supported Top3 retained: the golden event occurs in supported Top3;
- raw Top1 flip: raw Top1 is not the golden event;
- raw Top3 retained: the golden event occurs in raw Top3;
- false-supported candidate: a control appears with `supported_under_current_model`;
- false-supported candidate rate: false-supported control hypotheses divided by all control opportunities across all runs;
- false-supported scenario rate: valid runs containing at least one false-supported control divided by valid runs;
- admission/relevance/evidence stability: valid runs retaining the corresponding golden property divided by valid runs;
- order-sensitive count: identical control sets produce different supported Top1, supported Top3, golden supported rank, or false-supported set across insertion seeds.

All rates preserve numerator and denominator. Analysis identity and a normalized analysis hash are recorded. The normalized hash excludes persistence-only generated/created/updated/recorded timestamps.

## First-divergence order

1. `GOLDEN_CAUSE_NOT_ADMITTED`
2. `GOLDEN_CAUSAL_RELEVANCE_LOST`
3. `FALSE_SUPPORTED_DISTRACTOR`
4. `SUPPORTED_TOP1_FLIPPED`
5. `SUPPORTED_TOP3_DROPPED`
6. `ORDER_DEPENDENT_SUPPORTED_RESULT`
7. `GOLDEN_EVIDENCE_CHAIN_DEGRADED`
8. `NO_DIVERGENCE`

The first measured divergence is frozen; the evaluator does not repair product behavior.

## Outputs

The ignored result root is:

`evaluation/results/lineage/adversarial/lineage-2a-distractors/`

It contains the root manifest and aggregate plus, for every scenario, the input manifest, isolated database, analysis, candidate audit, relevance audit, TC4 summary, grade, and metrics. `artifact-hashes.json` inventories every JSON artifact written before the inventory itself.

## Execution

From `C:\Topo-ai`:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation.lineage_distractor_robustness
```

The harness refuses an existing output root unless `--replace-output` is explicit. Replacement is restricted to the exact LINEAGE-2A ignored result directory.

## Interpretation boundary

`ROBUST_IN_MEASURED_MATRIX` applies only to this frozen incident, these synthetic temporal-only controls, and this offline matrix. `ADVERSARIAL_DIVERGENCE_FOUND` records measured product behavior but authorizes no product repair. `INCONCLUSIVE` is used when any scenario is invalid.

This contract does not establish generalized robustness, live provider concurrency behavior, multi-incident behavior, or statistical significance.
