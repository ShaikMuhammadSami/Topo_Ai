# Structured Cause Match v1

Status: **authoritative current-model evaluation contract**

Version: `eval-cause-match-v1`

Scope: evaluation only. This contract grades serialized Topo output; it does
not change product normalization, candidate selection, relevance, causal
ranking, evidence, topology, persistence, titles, or APIs.

## Purpose

Root-cause correctness is equivalence between initiating mutations, not
similarity between display strings. The contract independently compares:

```text
manifest intent + execution receipt + provider verification
                         ↓
              expected cause fingerprint

root_event_id → serialized ChangeEvent.metadata
                         ↓
               actual cause fingerprint(s)
```

The expected side never consumes Topo's conclusion. The actual side never
consumes provider truth. This preserves evaluator independence.

## Semantic layer

The matched object is the initiating mutation, such as a Deployment image
field change. A failure mechanism, runtime manifestation, and operational
impact are related evidence layers but are not required to repeat the
initiating mutation's field or title. For example, an image mutation can be
the initiating cause while `ErrImagePull` is the runtime manifestation.

## Fingerprints

Both sides use `eval-cause-fingerprint-v1` with these dimensions:

- provider and normalized entity kind;
- canonical and provider-native entity identity;
- mutation family and changed field;
- canonical before/after references and SHA-256 hashes;
- initiating event and source change IDs when available;
- expected-side scenario aliases and evidence-source/completeness metadata.

Provider-native immutable identity is preferred. Canonical identity is used
when the expected side lacks provider-native identity. Display names alone are
not an identity proof when a stronger identity exists.

## Expected causes and alternatives

Expected fingerprints are derived only from the immutable scenario copy,
execution receipt, and provider-native verification. Each explicit accepted
entity alias produces an independent fingerprint. A non-abstention scenario
without selectors uses its declared causal root. Expected construction deep
copies its input and cannot mutate scenario truth.

An actual hypothesis may satisfy any explicit alternative. Alternatives do
not become fuzzy labels and are compared independently.

## Actual root-event resolution

Each hypothesis is resolved by its durable `root_event_id` against the
serialized `TopoObservation.change_events`. Exactly one matching event is
required. Its structured `metadata.entity_refs`, `changed_fields`,
before/after state, and origin change ID produce one or more actual
fingerprints. Missing or duplicate event references are indeterminate; a title
cannot substitute for the event.

The serialized observation is incident-bound output collected from the
incident analysis. The evaluator does not query latest topology or latest
change state to reconstruct an older cause.

## Identity rules

Identity comparison follows this priority:

1. provider-native immutable identity when independently known;
2. canonical identity otherwise;
3. stable aliases resolved through execution/provider receipts on the
   expected side.

Missing identity reduces completeness. Conflicting strong identity is a
structured mismatch. Multiple still-possible actual identities are
`ambiguous`; the evaluator does not guess.

## Field-path normalization

Known equivalence classes are explicit and evaluation-side. Current mappings
include:

| Provider/product representation | Canonical field |
|---|---|
| `spec.template.spec.containers[0].image` | `kubernetes.workload.container_image` |
| `properties.images` | `kubernetes.workload.container_image` |
| `properties.images[0]` | `kubernetes.workload.container_image` |
| `spec.replicas` / `properties.replicas` | `kubernetes.workload.desired_replicas` |
| `properties.available_replicas` | `kubernetes.workload.available_replicas` |

Identical raw paths compare directly. Different unknown representations are
not fuzzy-matched and yield unavailable comparison structure.

## Value rules

Values are normalized as deterministic JSON and hashed with SHA-256.
Singleton arrays normalize to their scalar value, allowing provider image
lists and normalized scalar image references to compare. JSON object key order
does not affect the hash. Image tags/references compare as exact normalized
strings; immutable digests compare exactly. No pretty-printed text, secret
plaintext, semantic similarity, embeddings, or LLM output participates.

## Match taxonomy

Implementation statuses are serialized in lower case:

- `exact`: all core comparable dimensions agree.
- `compatible_partial`: available dimensions agree but optional structure is
  absent. It is accepted only when provider, stable entity identity, and
  mutation family match, plus every independently known expected field and
  before/after value.
- `insufficient_structure`: equivalence cannot safely be determined.
- `ambiguous`: multiple structured interpretations remain possible.
- `value_mismatch`: same entity/mutation/field but before or after conflicts.
- `entity_match_mutation_mismatch`: same entity but a different mutation or
  known changed field.
- `mutation_match_entity_mismatch`: same mutation on a different entity.
- `different_cause`: other structured conflicts establish a different cause.

`exact` and accepted `compatible_partial` are matches. The four mismatch
states are false. `insufficient_structure` and `ambiguous` are indeterminate.

## Top-1 and Top-3

Top-1 evaluates only rank 1. The metric is `true` for an accepted structured
match, `false` for a definite structured mismatch, and `null` for insufficient
or ambiguous structure. A required null result contributes an INCONCLUSIVE
failure category, not a product failure.

Top-3 evaluates each of the first three hypotheses independently. It is true
if any hypothesis matches. It is false only when all present hypotheses are
definite mismatches. It is null when no hypothesis matches and at least one is
indeterminate, or when no hypothesis exists.

Abstention scenarios retain their abstention contract; root-cause match is
reported as not applicable rather than manufacturing expected cause truth.

## Presentation diagnostics

The bounded legacy title/alias selector remains diagnostic as
`root_cause_title_match`. It does not affect authoritative Top-1, Top-3, or
overall status. An exact structured cause with a generic title records a
presentation warning. A perfect title cannot hide a structured mismatch.

## Result metadata

Current runs declare:

- `cause_fingerprint_version`;
- `cause_match_version`;
- `cause_match_status`;
- expected fingerprints;
- Top-1 actual fingerprint and match;
- independent Top-3 match records;
- source, alternative, and presentation diagnostics.

The fields are additive so accepted older EVAL-1 results remain schema
loadable. A current run that terminates before cause evaluation still declares
the versions and `not_evaluated` status.

## Independence and boundaries

The implementation imports no product candidate, relevance, blast, RCA, or
evidence-ledger reasoning policy. It reads shared serialized concepts only.
It contains no scenario-ID override, title-token authority, fuzzy matching,
embeddings, or LLM dependency. TC-1 through TC-5 and all product reasoning
versions remain unchanged.
