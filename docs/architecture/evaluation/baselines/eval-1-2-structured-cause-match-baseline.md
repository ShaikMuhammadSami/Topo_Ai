# EVAL-1.2 Structured Cause Match Baseline

Measured: 2026-08-24 against Kubernetes context `docker-desktop` on branch
`evaluation/structured-root-cause-match-v1`.

## 1. Previous cause-match defect

The previous evaluator dereferenced `root_event_id` only to collect display
text and entity links. It concatenated hypothesis `root_title`/`root_source`
with event title, kind, change type, and summary, lowercased the prose, and
required every manifest `title_contains_all` token plus an entity-alias
intersection. Top-3 repeated the same title/alias predicate. It did not compare
provider, UID, mutation family, changed field, before/after values, or durable
source change identity. Missing data became `false` and a PRODUCT failure.

CA-0 proved this was the first divergence for blast-01 and blast-03: both
winning root events preserved the exact initiating image mutation but exposed
the generic title `KubernetesDeployment updated`.

## 2. `eval-cause-match-v1` authoritative semantics

Current-model Top-1 and Top-3 correctness use structured initiating-mutation
equivalence. Expected truth is independent; actual truth is resolved from the
selected durable root event. Titles are never authoritative. Accepted matches
are `exact` and policy-qualified `compatible_partial`; definite structured
conflicts fail; insufficient or ambiguous structure is indeterminate.

## 3. Fingerprint fields

Version `eval-cause-fingerprint-v1` carries provider, entity kind, canonical
ID, provider-native ID, mutation family, changed field, before/after references
and hashes, initiating event ID, source change ID, scenario logical entity and
change, evidence source, and completeness.

## 4. Exact/partial/insufficient/mismatch states

- `exact`: every core comparable dimension agrees.
- `compatible_partial`: missing optional structure, accepted only with matching
  provider, stable identity, mutation family, and every independently known
  expected field/before/after value.
- `insufficient_structure`: equivalence cannot safely be judged.
- `ambiguous`: multiple structured interpretations remain.
- `value_mismatch`, `entity_match_mutation_mismatch`,
  `mutation_match_entity_mismatch`, and `different_cause`: definite failure.

Required insufficient/ambiguous results become INCONCLUSIVE, not guessed
product failures.

## 5. Identity matching rules

Provider-native immutable identity is strongest. Canonical identity is used
when expected provider identity is absent. Expected logical aliases must first
resolve through the execution receipt/provider verification. Display names are
not identity proof when a UID is available. Conflicts fail; unresolved
multi-identity cases are ambiguous.

## 6. Field-path normalization

Known mappings are explicit, not fuzzy. Provider
`spec.template.spec.containers[0].image` and Topo `properties.images` /
`properties.images[0]` map to
`kubernetes.workload.container_image`. Desired and available replica paths are
separate known canonical fields. Unknown cross-representation paths are not
guessed and remain not comparable.

## 7. Value matching

Values use deterministic canonical JSON SHA-256. Singleton arrays normalize
to their scalar value, allowing provider image lists and normalized image
fields to compare. Image refs/tags and digests use exact normalized equality.
JSON object key order is irrelevant. No pretty text, secret plaintext,
embedding, semantic similarity, or LLM participates.

## 8. Top-1 matching

Rank 1 is independently resolved through `root_event_id` and evaluated against
each accepted expected fingerprint. `true` means an accepted structured match,
`false` means a definite different initiating cause, and `null` means
insufficient or ambiguous structure.

## 9. Top-3 matching

The first three ranked hypotheses are evaluated independently. The metric is
true when any matches, false only when all are definite mismatches, and null
when no match exists but at least one candidate is indeterminate (or no
hypothesis exists). There is no title-token fallback.

## 10. Alternative expected causes

Every explicitly accepted entity alias produces its own expected fingerprint.
One actual hypothesis may match any explicit alternative. Alternatives remain
structured; they are not collapsed into fuzzy labels. The seven preserved
manifests were not changed.

## 11. Insufficient/ambiguous behavior

A missing/duplicate selected root event, insufficient expected structure, or
unresolvable cause returns null correctness and an INCONCLUSIVE evaluation
category when root cause is required. Multiple satisfying actual identities do
not trigger arbitrary selection unless the scenario explicitly permits
alternatives.

## 12. Title/presentation diagnostics

The previous title selector is retained only as
`root_cause_title_match`. Structured correctness controls result status.
An exact cause with a generic title records
`cause_presentation_generic=true` and a presentation warning. A perfect title
cannot override a structured mismatch.

## 13. Evaluator independence

Expected fingerprints consume only scenario intent, execution receipt, and
provider verification. Actual fingerprints consume only serialized Topo
observation and the selected event/change references. The evaluator imports no
product candidate, relevance, blast, 13C, or TC-4 reasoning implementation and
contains no scenario-ID special case, LLM, or embedding dependency.

## 14. Version metadata

Every current result declares `eval-cause-fingerprint-v1` and
`eval-cause-match-v1`, including `not_evaluated` runs that stop before causal
matching. Results add expected fingerprints, Top-1 actual/match, independent
Top-3 matches, cause status, and diagnostics. Existing fields and accepted old
result schema compatibility are preserved.

## 15. Sentinel A result

Run `5c5da6ec`: PASS. Cause status `matched`; Top-1 true; Top-3 true;
structured match `exact`; root event
`change-event:0ea8b62fa06f25a7bbfd5f328fb25c37`; title presentation matched.

## 16. Sentinel B result

Run `1d5add8e`: PASS. Cause status `matched`; Top-1 true; Top-3 true;
structured match `exact`; root event
`change-event:d2c4c0c7eac560a6bd223d2dd3207aa7`; distractor/non-cause checks
remain satisfied.

## 17. Sentinel C result

Run `482e4d34`: PASS. Cause status `matched`; Top-1 true; Top-3 true;
structured match `exact`; root event
`change-event:2723662e36aee179eb10c0530c86085f`. Derived topology-diff noise did
not replace the initiating mutation.

## 18. Sentinel D result

Run `71089040`: PASS. Cause status `matched`; Top-1 true; Top-3 true;
structured match `exact`; root event
`change-event:9e343403849cd4bdda6c8b6da0b0e932`. BR-1 directional blast
semantics remain satisfied.

## 19. blast-01 structured before/after

Run `70426024`: PASS.

| Dimension | Expected independent truth | Actual selected event | Comparison |
|---|---|---|---|
| Provider | `kubernetes` | `kubernetes` | matched |
| Kind | `Deployment` | `Deployment` | matched |
| Provider UID | `6bcb4f27-6b8f-44b1-9d1b-f138909bf6e7` | same | matched |
| Mutation | `field_change` | `field_change` | matched |
| Field | `spec.template.spec.containers[0].image` | `properties.images` | matched canonical image field |
| Before | `nginx:1.27-alpine` / `f220981d...e6b6` | same | matched |
| After | `registry.invalid/topo-eval/blast-01:70426024` / `86758591...4477` | same | matched |

Root event:
`change-event:176b3a2988f8ca75d9a152ff4ed6b62c`; source change:
`change:b16598cc8f7e508aa5068578df1de06b`. Match `exact`; Top-1 true;
Top-3 true; overall PASS. Root title remains
`KubernetesDeployment updated`; legacy title match false;
`cause_presentation_generic=true`; presentation warning only. The same event
also carried an availability-field mutation, which was independently compared
and rejected as the expected image cause before the exact image fingerprint
was selected.

## 20. blast-02 result

Run `d3baa22b`: PASS. Required abstention remained correct. Cause match status
is `not_applicable_abstention`; Top-1/Top-3 cause correctness are null, not
fabricated. Existing non-cause and BR-1 blast assertions pass.

## 21. blast-03 structured before/after

Run `afa903d5`: PASS.

| Dimension | Expected independent truth | Actual selected event | Comparison |
|---|---|---|---|
| Provider | `kubernetes` | `kubernetes` | matched |
| Kind | `Deployment` | `Deployment` | matched |
| Provider UID | `ee3da7ff-3b01-4ae1-adbc-166cbd23dc9e` | same | matched |
| Mutation | `field_change` | `field_change` | matched |
| Field | `spec.template.spec.containers[0].image` | `properties.images` | matched canonical image field |
| Before | `nginx:1.27-alpine` / `f220981d...e6b6` | same | matched |
| After | `registry.invalid/topo-eval/blast-03:afa903d5` / `90502d09...385e` | same | matched |

Root event:
`change-event:d4d65d0a6fc353e7e2eb096b43aad8b6`; source change:
`change:cbd47e1d89b8b23a2e506a3292838a04`. Match `exact`; Top-1 true;
Top-3 true; overall PASS. Root title remains
`KubernetesDeployment updated`; legacy title match false;
`cause_presentation_generic=true`; presentation warning only. Its separate
availability-field fingerprint did not satisfy the independent image truth.

## 22. Seven-scenario permanent corpus summary

| Scenario | Fresh run | Result | Structured cause status |
|---|---|---|---|
| Sentinel A | `5c5da6ec` | PASS | matched / exact |
| Sentinel B | `1d5add8e` | PASS | matched / exact |
| Sentinel C | `482e4d34` | PASS | matched / exact |
| Sentinel D | `71089040` | PASS | matched / exact |
| blast-01 | `70426024` | PASS | matched / exact |
| blast-02 | `d3baa22b` | PASS | not applicable / abstention |
| blast-03 | `afa903d5` | PASS | matched / exact |

All were fresh isolated current-model runs. All result schemas, forensic
schemas, and manifest schemas validated. This seven-scenario corpus is **NOT
STATISTICALLY MEANINGFUL**. It establishes only that the seven preserved
deterministic regression scenarios pass under the current versioned product
and evaluator policies; it is not an accuracy measurement.

## 23. Remaining product defects

No new product correctness defect was found by this seven-scenario rerun. That
statement is limited to the preserved deterministic corpus and does not imply
general product correctness. Product roots were unchanged by EVAL-1.2.

## 24. Remaining evaluator limitations

Expected action semantics and known field equivalence classes cover the
current Kubernetes corpus, not every future connector. Unknown cross-source
field transformations deliberately become INCONCLUSIVE. The current manifest
alternative representation is entity-alias based; richer future mutation
alternatives will need explicit structured schema. This corpus is too small
and narrow for statistical release claims.

## 25. Presentation limitations

Blast-01 and blast-03 still expose the generic root title
`KubernetesDeployment updated`. EVAL-1.2 records this separately and does not
change product titles. More specific human-readable initiating-mutation
presentation remains future product work.

## Verification summary

- backend compile: pass; backend tests: 608 passed;
- agent compile: pass; agent tests: 15 passed;
- evaluation compile: pass; evaluation tests: 134 passed (96 existing + 38);
- all seven result artifacts, forensic bundles, and manifests: schema valid;
- all seven manifest Git object hashes: unchanged;
- product source diff guard: empty.
