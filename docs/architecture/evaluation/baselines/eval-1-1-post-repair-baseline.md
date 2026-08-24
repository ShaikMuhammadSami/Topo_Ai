# EVAL-1.1 Post-Repair Baseline

Measured: 2026-08-24 against `docker-desktop`.

Evaluator evidence semantics: `non-cause-evidence-v1`.

The generated JSON artifacts are under ignored `evaluation/results/`; their
run-specific names are recorded below for reproducibility.

## 1. Evaluator defect

EVAL-1 treated a supporting critical claim as support for an explicit
non-cause when the item's `entity_ids` intersected the non-cause IDs. The code
used claim type, stance, and entity intersection, but not candidate event ID,
affected entity ID, candidate relevance audit, selected topology path, or
selected relationship references. Sentinel B therefore failed on two true
candidate-local facts after CR-1 had already removed its false path evidence.

## 2. New evidence semantics version

New result artifacts persist
`evidence_semantics_version: non-cause-evidence-v1`. Product policy and truth
contract versions are unchanged.

## 3. Evidence taxonomy

The evaluator uses `candidate_fact`, `causal_connectivity`,
`effect_evidence`, `lineage_evidence`, and `unknown_ambiguous`. Only evidence
whose structured scope establishes candidate-to-effect connectivity counts as
false causal support.

## 4. Sentinel B exact before claim interpretation

Explicit non-cause candidate event:
`change-event:89d7b0a690e8306c48f5562865c3f6fa`.

Candidate entity:
`k8s:docker-desktop:deployment:18a3d17c-2e5e-4e1f-ac73-33b7602eb36a`.

Affected entity:
`k8s:docker-desktop:pod:39648735-e1b7-4cdf-a1aa-b5133446da4c`.

All five items had TC-4 stance `supporting`.

| Claim | Structured references | Old evaluator | New evaluator | Reason |
| --- | --- | --- | --- | --- |
| `entity_linkage` | candidate entity; candidate event; `change-link:5da46cbefa52b58cd5f600eb6d198501` | Forbidden/count 1 | `candidate_fact` | Change links only to its own distractor Deployment. |
| `identity_resolution` | candidate entity; candidate event; same change-link | Forbidden/count 1 | `candidate_fact` | Exact candidate identity is true but does not reach the failed Pod. |
| `runtime_failure` | affected Pod; `signal:kubernetes-state:036addc762da10d0f6f5a4caf35b7bc2` | Not in old critical set | `effect_evidence` | Establishes the victim Pod failure, not distractor causality. |
| `source_change` | candidate event; `change:a04019d6a2b7d226fc64be4b116790ef` | Not counted because `entity_ids` was empty | `candidate_fact` | The distractor really changed. |
| `temporal_precedence` | candidate event; same normalized change | Not in old critical set | `candidate_fact` | The distractor really preceded the incident. |

The distractor had no supporting `topology_path` and no supporting
`relationship_provenance`; `topology_path` remained explicitly missing.

## 5. Sentinel B explicit non-cause before/after metric

| Metric | Value |
| --- | ---: |
| Legacy raw `explicit_non_cause_supported_count` | 2 |
| New candidate fact count | 4 |
| New effect evidence count | 1 |
| New lineage evidence count | 0 |
| New false causal support count | 0 |
| New ambiguous count | 0 |

The old raw value remains serialized for auditability but no longer drives the
assertion. The false-causal value drives it, so Sentinel B passes.

## 6. Sentinel A result

Artifact: `sentinel-a-c890120a.json`. Status `PASS`. Actual Deployment
mutation was Top-1 and in Top-3; required semantic path and TC-5 invariant
passed. Blast precision/recall were 1.0/1.0.

## 7. Sentinel B result

Artifact: `sentinel-b-3bfb53f2.json`. Status `PASS`. Victim Deployment was
Top-1 at 63.33 with `semantic_path` topology component 0.65. Distractor was
rank 2 at 47.08 with `no_supported_path` and topology component 0.0. False
causal support and ambiguity were both zero.

## 8. Sentinel C result

Artifact: `sentinel-c-18c587eb.json`. Status `PASS`. Actual Deployment
mutation was Top-1 and in Top-3; required semantic path, forbidden path, TC-5,
and blast assertions passed. Blast precision/recall were 1.0/1.0.

## 9. Sentinel D result

Artifact: `sentinel-d-91e38de8.json` from the final blast pass. Status `PASS`.
Actual Deployment mutation was Top-1 and in Top-3. Blast precision/recall were
1.0/1.0 with zero false positives and zero false negatives.

## 10. blast-01 result

Artifact: `blast-01-d6530602.json`. Status `FAIL` for separate root-cause
Top-1 and Top-3 assertions. The BR-1 blast baseline remained correct:
precision 1.0, recall 1.0, zero false positives, and zero false negatives.

## 11. blast-02 result

Artifact: `blast-02-a87f610b.json`. Status `PASS`. The scenario correctly
abstained with no hypotheses. Blast precision/recall were 1.0/1.0 with zero
false positives and zero false negatives.

## 12. blast-03 result

Artifact: `blast-03-8bdf7bf1.json`. Status `FAIL` for separate root-cause
Top-1 and Top-3 assertions. The BR-1 blast baseline remained correct:
precision 1.0, recall 1.0, zero false positives, and zero false negatives.

## 13. Permanent corpus summary

Sentinel A, B, C, D and blast-02 passed. blast-01 and blast-03 failed only
their causal root selection assertions. All seven runs used unchanged
manifests and `non-cause-evidence-v1`. Every blast precision/recall pair was
1.0/1.0.

This seven-scenario corpus is **NOT STATISTICALLY MEANINGFUL**. The counts are
deterministic regression observations, not product accuracy percentages.

## 14. Remaining product failures

- blast-01 generated a Top-1 `KubernetesDeployment updated` hypothesis that
  did not match the predeclared cause; truth was absent from Top-3.
- blast-03 generated the same class of mismatched Top-1 hypothesis; truth was
  absent from Top-3.

These are product causal-ranking/selection findings. EVAL-1.1 did not modify
or attempt to repair them. Blast-impact behavior remained correct.

## 15. Remaining evaluator limitations

The evaluator requires structured scope to judge artifact/event lineage and
selected paths; otherwise it reports ambiguity. It deliberately does not
parse natural language, reuse product reasoning, estimate probabilities, or
generalize beyond explicit manifest non-causes. The permanent corpus remains
small and is not a statistical benchmark.
