# Evaluation Cause Fingerprint v1

Status: **CA-0 forensic contract**. This contract is evaluation-only and does
not change product behavior, product persistence, scenario expectations, or
EVAL-1 pass/fail semantics.

## Contract families

TopoAI keeps these version families separate:

- Product truth: TC-1 `v1`, TC-2 `tc2.v1`, TC-3 `tc3.v1`, TC-4 `tc4.v1`,
  TC-5 `tc5.v1`.
- Product reasoning: `blast-impact-v1`, `causal-candidate-v1`,
  `causal-relevance-v1`, `13c-causal-v1`.
- Evaluation: `non-cause-evidence-v1`, `eval-cause-fingerprint-v1`,
  `eval-cause-match-v1`.

## `eval-cause-fingerprint-v1`

A cause fingerprint records only structure represented by the layer being
audited. Its fields are:

| Field | Meaning |
|---|---|
| `provider` | Provider family, when structurally known. |
| `entity_kind` | Provider entity kind with only deterministic prefix normalization. |
| `canonical_entity_id` | Topo canonical ID, when the audited layer carries it. |
| `provider_native_entity_id` | Provider UID/resource ID, when carried or deterministically encoded by the canonical ID. |
| `mutation_family` | Structured mutation class, such as `field_change`. |
| `changed_field` | Exact field path represented by that layer. |
| `before_value_ref/hash` | Canonical value reference and SHA-256, or null. |
| `after_value_ref/hash` | Canonical value reference and SHA-256, or null. |
| `initiating_event_id` | Durable ChangeEvent ID, or null. |
| `source_change_id` | Durable NormalizedChange/ChangeRecord ID, or null. |
| `scenario_logical_entity` | Predeclared logical alias; expected-side only. |
| `scenario_logical_change` | Predeclared logical change; expected-side only. |
| `evidence_source` | Exact layer/source used to build the fingerprint. |
| `fingerprint_completeness` | `complete`, `partial`, or `insufficient_structure`. |

The expected fingerprint is derived solely from the predeclared manifest,
execution receipt, and provider verification. Topo output is never an input.
An actual fingerprint is derived separately at each layer. Missing upstream
fields remain null; downstream knowledge is never backfilled.

The action-semantic mapping `causal_bad_image` to Kubernetes container-image
field mutation is generic to the evaluation action, not keyed by scenario ID
or expected outcome. Kubernetes snapshot-diff `properties.images` and the
provider API path `spec.template.spec.containers[0].image` form one explicit
field-equivalence class. Singleton image arrays and scalar image values use the
same canonical value hash.

## `eval-cause-match-v1`

The comparator evaluates:

- provider;
- entity kind;
- provider-native identity when expected provider identity is available,
  otherwise canonical identity;
- mutation family;
- explicit changed-field equivalence;
- canonical before and after value hashes;
- initiating event and source change IDs when both sides expose them.

It returns one of:

- `exact`;
- `compatible_partial`;
- `entity_match_mutation_mismatch`;
- `mutation_match_entity_mismatch`;
- `insufficient_structure`;
- `different_cause`.

`exact` requires all core cause dimensions to be comparable and equal.
Unavailable event/change IDs do not prevent an otherwise complete cause match,
because independent provider truth does not originate with Topo IDs. A partial
record never becomes exact.

The comparator deliberately does not consume titles, summaries, fuzzy text,
embeddings, display-name similarity, or LLM output.

## First-divergence rule

Forensic layers are evaluated in causal data-flow order. The first layer whose
structured truth verdict is false owns `first_divergence`; later mismatches are
downstream consequences. Exactly one classification is emitted. Identical
chains emit `NO_DIVERGENCE_FOUND`.

The CA-0 bundle schema is
[`cause-forensic-bundle.schema.json`](cause-forensic-bundle.schema.json). The
runner can opt into ignored forensic capture with `--forensic-output-dir`.
Normal EVAL-1 runs and the accepted evaluator remain unchanged.

## Historical correctness

The bundle compares the incident record, causal analysis, and TC-4 ledger
snapshot IDs. It reports historical correctness only when all reference the
same incident-pinned snapshot. It reads TC-3 metadata from the selected durable
event. It never consults latest topology and adds no pre-V1 compatibility
adapter.
