# LINEAGE-2A Distractor Source Robustness Baseline

## Final verdict

**ADVERSARIAL_DIVERGENCE_FOUND**

LINEAGE-2A is an evaluation checkpoint only. No product behavior was changed to influence this result.

## Frozen dependency and scope

- accepted main baseline: `4f119ae`
- accepted golden product commit underlying LINEAGE-1K: `42f68835333c71371d3e54033a9bcdd69c1de36d`
- golden dependency: LINEAGE-1L `PROVEN`, first divergence `NO_DIVERGENCE`
- method: offline controlled perturbation of isolated post-SC4 database copies
- Kubernetes execution: none
- GitHub/GHCR/provider calls: none
- live concurrent provider ingestion: not tested

The independent golden truth remained:

- source event: `change-event:20a8946c8c445153d85c90ee2166d487`
- mutation: `source-file-mutation:8603928ab096886df3b7c84d94cc0e9f3ce79633`
- revision: `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`
- image: `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed`
- incident boundary: `2026-08-26T05:09:49Z`
- pinned topology: `snapshot:actions-enriched:20260826T051031Z:2d8416d3`
- affected entity: `k8s:docker-desktop:pod:0ca94031-d80c-4ea5-90dd-8d74bb671168`

## Seed identity and immutability

Seed:

`evaluation/results/lineage/post-sc4/topo-product-32695735269.db`

- expected SHA-256: `9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f`
- observed pre-run SHA-256: exact match
- SQLite quick check: `ok`
- SQLite integrity check: `ok`
- tables: 38
- open mode: `mode=ro&immutable=1` plus `PRAGMA query_only=ON`
- observed post-run SHA-256: `9f3918a027c6d9a7bbd679495c48b387c9a1ac8c86141f85cf8b4495cd00b69f`

Every scenario used its own byte-identical copy. No derived analysis deletion was required. Count 0 reused the existing immutable deterministic analysis. Each nonzero event set generated a new deterministic analysis ID inside its copy because candidate event IDs are part of the product analysis fingerprint.

## Distractor contract

Controls were canonical GitHub/code `ChangeEventCreate` inputs with deterministic independent repositories, distinct 40-character revisions, bounded risk values, and exact source-reported times. Times were distributed at integer-second intervals from 5 to 175 minutes before the incident, entirely inside ordinary 180-minute Path A and never after the boundary.

The controls had incident-compatible environment/cluster/namespace scope but no entity references, exact immutable lineage, golden commit, golden producer run, golden image, golden build evidence, or affected topology identity.

`NONCAUSAL_CONTROL` existed only in the evaluator manifest. No expected-answer hint was product-visible.

## Matrix

The exact counts were `0, 1, 5, 10, 20, 50`. Count 0 ran once; each nonzero count ran insertion seeds `0, 1, 2`. Total: 16 runs. Valid: 16. Invalid: 0.

All three orders for a count produced the same raw order, supported order, deterministic analysis ID, and normalized analysis hash.

| Count | Orders | Golden raw rank | Golden supported rank | False-supported controls per run | First run-level divergence | Verdict |
|---:|:---:|---:|---:|---:|---|---|
| 0 | 0 | 1 | 1 | 0 | `NO_DIVERGENCE` | `PROVEN` |
| 1 | 0, 1, 2 | 2 | 2 | 1 | `FALSE_SUPPORTED_DISTRACTOR` | `WRONG` |
| 5 | 0, 1, 2 | 6 | absent | 5 | `GOLDEN_CAUSAL_RELEVANCE_LOST` | `WRONG` |
| 10 | 0, 1, 2 | 11 | absent | 5 | `GOLDEN_CAUSAL_RELEVANCE_LOST` | `WRONG` |
| 20 | 0, 1, 2 | 21 | absent | 5 | `GOLDEN_CAUSAL_RELEVANCE_LOST` | `WRONG` |
| 50 | 0, 1, 2 | 51 | absent | 5 | `GOLDEN_CAUSAL_RELEVANCE_LOST` | `WRONG` |

## Count-zero control

Count 0 reproduced the accepted golden result:

- analysis: `causal-analysis:76c9b683e95e2f2fd599677122f2ebae`
- raw Top1 and supported Top1: golden event
- raw and supported golden rank: 1
- golden TC4: supporting 5, contradicting 0, missing 0, unknown 0
- exact structured cause match: 8/8
- verdict: `PROVEN`
- divergence: `NO_DIVERGENCE`

## Count-one finding

All three insertion seeds produced the same control event:

`change-event:05a3d2361472923f5d545eaca1981f35`

It became raw Top1 and product-supported Top1; the golden event moved to raw and supported rank 2. The control's relevance audit was explicitly `identity_unresolved`, `resolution_basis=unresolved`, `path_semantic=unsupported_unknown`, `topology_component=0.0`, and contained no topology relationship.

Despite that, its TC4 ledger had three supporting claims—`source_change`, `temporal_precedence`, and `runtime_failure`—with zero contradicting, missing, or unknown items. TC5 therefore labeled it `supported_under_current_model` and `complete_for_current_model`. This is the exact false-support mechanism observed.

## Counts five through fifty

At count 5, all five recent controls outranked the golden event in raw candidate order. The product selected its maximum five hypotheses, so the still-admitted exact golden event at raw rank 6 did not enter causal relevance evaluation or the supported surface. The same effect continued at counts 10, 20, and 50, where golden raw rank was 11, 21, and 51.

Each of the five selected controls per run had unresolved identity, no supported causal topology path, and the same three-claim TC4 pattern. All five nevertheless appeared as supported hypotheses.

Following the required taxonomy order, the matrix's first adversarial divergence is:

`GOLDEN_CAUSAL_RELEVANCE_LOST`

The first scenario for that category is count 5, order 0. Its exact control set was:

1. `change-event:1ea923e137c14a3e4d0bd8dc913c1c4d`
2. `change-event:da776f81acf6202c5e1b1ced5404e355`
3. `change-event:2e8e5f8c3dbf6d57197a9d408c1a71d2`
4. `change-event:1532bb28f0ffbcbcf59faa867f04e358`
5. `change-event:6c8058129ca1bad7195277157aa2d678`

Chronologically, a false-supported result already occurs at count 1. It is recorded as a separate earlier-pressure finding, but `GOLDEN_CAUSAL_RELEVANCE_LOST` precedes `FALSE_SUPPORTED_DISTRACTOR` in the frozen first-divergence taxonomy.

## Raw versus supported results

Recent controls predictably displaced the 2,827.77-minute-old golden source in raw ordering. That alone would not be a causal failure. The causal failure is that relevance-unresolved controls also entered the supported surface, while the exact lineage-admitted golden candidate was eventually excluded before relevance evaluation.

- golden raw-rank range: 1 through 51, observed in all 16 runs
- golden supported-rank range: 1 through 2, observed in only 4 runs
- false-supported control hypotheses: 63
- runs with at least one false-supported control: 15 of 16
- safe abstentions: 0

Because a proven cause exists, abstention would represent lost evidence rather than an ideal result; the product did not abstain.

## Aggregate metrics

| Metric | Numerator | Denominator | Rate |
|---|---:|---:|---:|
| Supported Top1 flips | 15 | 16 | 93.75% |
| Supported Top3 retained | 4 | 16 | 25.00% |
| Raw Top1 flips | 15 | 16 | 93.75% |
| Raw Top3 retained | 4 | 16 | 25.00% |
| False-supported control hypotheses | 63 | 258 | 24.4186% |
| Scenarios with false support | 15 | 16 | 93.75% |
| Golden admission stable | 16 | 16 | 100.00% |
| Golden relevance stable | 4 | 16 | 25.00% |
| Golden evidence completeness retained | 4 | 16 | 25.00% |
| Order-sensitive counts | 0 | 5 | 0.00% |

The evidence-completeness denominator treats the golden chain as not retained when the golden hypothesis is never generated. In the four runs where it was evaluated, its ledger remained supporting 5, contradicting 0, missing 0, unknown 0.

## Release-gate observations

- supported Top1 flip rate = 0: **not achieved**
- supported Top3 retention = 100%: **not achieved**
- false-supported candidates = 0: **not achieved**
- golden admission stability = 100%: **achieved**
- golden relevance stability = 100%: **not achieved**
- evidence-completeness stability = 100%: **not achieved**
- order sensitivity = 0: **achieved**

These are measurements, not authorization to change thresholds or product logic.

## Artifact identity

Ignored result root:

`evaluation/results/lineage/adversarial/lineage-2a-distractors/`

- run databases: 16
- JSON artifacts inventoried: 114
- `manifest.json` SHA-256: `c188951d0fba220555dfbf18d6680f24176711d5491fe21c8d3eedaa15d2daa2`
- `aggregate.json` SHA-256: `9173559982853ef2afd29f8885696aa4d47c7ffee122c52f65d020fd1ad69348`
- `artifact-hashes.json` SHA-256: `2a9ea7e01fd11aeb540a8813674db6d78d836c269ce7d4df8a0a02de70abe7a3`

The inventory contains per-run input, analysis, candidate audit, relevance audit, TC4, grade, and metrics hashes. It excludes itself by construction.

## Integrity and limitations

All golden invariants passed in all 16 scenarios: event, mutation, immutable lineage, SC2 admission, image anchor, incident, boundary, pin, and affected entity. The post-run seed SHA-256 remained exact.

This evaluation proves that the current product has a deterministic, insertion-order-independent adversarial divergence for one preserved incident under synthetic temporal-only control pressure. It does not prove live concurrent provider-ingestion behavior, generalized robustness, behavior across incident families, multi-file robustness, broken-lineage behavior, or statistical significance.

No repair was performed. First-divergence discipline preserves the evidence for a separate future product-repair block.
