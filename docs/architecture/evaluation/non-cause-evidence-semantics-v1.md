# Non-Cause Evidence Semantics v1

Status: implemented as an evaluation-harness contract on 2026-08-24.

Version: `non-cause-evidence-v1`.

## Measured defect

The original EVAL-1 non-cause check selected every supporting TC-4 ledger
item whose `claim_type` was in a fixed critical set and whose `entity_ids`
intersected a manifest-declared non-cause. It did not inspect the hypothesis's
candidate event, the incident affected entity, CR-1's candidate relevance
audit, selected path entity IDs, or selected path relationship IDs.

That conflated two different propositions:

1. a true fact establishes the identity, occurrence, timing, or own-entity
   linkage of a candidate; and
2. evidence connects that candidate to this incident's affected entity.

Sentinel B exposed the defect after CR-1 correctly removed the distractor's
`topology_path` and path `relationship_provenance`. Its remaining
`entity_linkage` and `identity_resolution` were true candidate-local facts,
but the old evaluator still failed the scenario.

## Evidence taxonomy

The independent evaluator now interprets serialized supporting evidence as:

- `candidate_fact`: candidate identity, source mutation, timing, or linkage
  only to the candidate's own entity.
- `causal_connectivity`: structured evidence connecting the candidate/source
  to the incident affected entity.
- `effect_evidence`: evidence that the incident effect exists on the affected
  entity, without attributing that effect to the candidate.
- `lineage_evidence`: artifact or event lineage. It is causal only when its
  structured references participate in a candidate-to-effect bridge.
- `unknown_ambiguous`: the serialized references are insufficient to decide
  safely.

This taxonomy interprets TC-4 output; it does not redefine TC-4 evidence
stances or product evidence semantics.

## Classification algorithm

The classifier consumes only serialized system-under-test output and manifest
truth:

1. Resolve manifest aliases to topology IDs using provider-native UIDs, as the
   existing independent evaluator already does.
2. Identify each hypothesis candidate using the serialized CR-1
   `candidate_relevance_audit`, durable change-event links, and a narrow legacy
   identity/linkage fallback for old EVAL-1 artifacts.
3. Evaluate only hypotheses whose candidate identity intersects an explicit
   manifest non-cause.
4. Resolve affected IDs from accepted affected aliases plus the observed
   incident affected ID.
5. Establish a selected candidate-to-effect path only from serialized CR-1
   path entities/relationships, or from an explicit supporting topology path
   in a legacy artifact.
6. Classify every supporting ledger item using its entity IDs, change-event
   IDs, relationship IDs, and source-reference IDs. Natural-language reasons
   are never parsed.
7. Count an item as false causal support only when its structured scope
   establishes candidate-to-effect connectivity.

The implementation is deterministic: inputs and all emitted interpretations
are sorted by stable serialized identifiers.

## Claim rules

- `source_change`, `identity_resolution`, and `temporal_precedence` are
  candidate facts for the selected candidate hypothesis.
- `runtime_failure` on an accepted affected entity is effect evidence. A
  candidate-local runtime fact remains a candidate fact.
- `entity_linkage` is a candidate fact when it links the change/event only to
  its own candidate entity. It is causal connectivity when its structured
  entity/event scope reaches the affected entity.
- `topology_path` is causal connectivity only when it directly bridges
  candidate and affected IDs or belongs to the serialized selected path.
- `relationship_provenance` is causal connectivity only when its relationship
  ID occurs on that selected path. Candidate-local relationship facts are not
  causal; unscoped relationship facts are ambiguous.
- `artifact_provenance` is lineage evidence. It is causal only when entity or
  selected-path relationship references bridge source and effect.
- `event_lineage` is lineage evidence. It is causal only when it names the
  candidate event and a structured selected candidate-to-effect path exists.
- Unknown or structurally under-specified claims are ambiguous.

## Explicit non-cause failure rule

The `noncause_support` and `unsupported_claims` assertions now fail only when:

```text
explicit_non_cause_false_causal_support_count > 0
```

Candidate facts, effect evidence, and candidate-local lineage do not fail the
assertion. This preserves true evidence instead of requiring the product to
deny candidate identity or timing.

## Ambiguous evidence

Ambiguous evidence is not guessed to be causal and is not counted as false
causal support. If it occurs on a hypothesis for a declared non-cause, it
materially prevents the required causal judgment, so the evaluator emits a
failed `noncause_evidence_classifiable` diagnostic with category
`INCONCLUSIVE`. Product failures continue to take precedence and produce
`FAIL`.

## Metrics

Legacy, raw metrics are preserved unchanged for before/after auditing:

- `explicit_non_cause_supported_count`: old fixed-claim-plus-entity-intersection
  raw count.
- `unsupported_critical_claim_count`: the same legacy raw count; retained for
  artifact compatibility, no longer used as the release assertion value.

Versioned semantic metrics are additive:

- `explicit_non_cause_supporting_fact_count`
- `explicit_non_cause_effect_evidence_count`
- `explicit_non_cause_lineage_evidence_count`
- `explicit_non_cause_false_causal_support_count`
- `unsupported_false_causal_claim_count`
- `explicit_non_cause_ambiguous_support_count`
- claim-type arrays for each interpretation
- `explicit_non_cause_evidence_interpretations`, containing the structured
  references and deterministic reason for every classified item.

## Result compatibility

New results persist top-level
`evidence_semantics_version: "non-cause-evidence-v1"`. The existing
`eval-1.result.v1` and `eval-1.v1` identifiers remain unchanged. The new field
is optional in the JSON Schema, so old EVAL-1 artifacts without it still
validate and load. New runner artifacts always include it.

## Independence

The classifier lives under `evaluation/` and imports no backend service,
ledger builder, causal candidate policy, or causal relevance policy. It grades
serialized Topo output as an external system under test. There are no
scenario-name branches or product-path modifications.

## Known limitations

- Rich artifact/event lineage can be judged only when TC-4 output supplies
  structured entity, event, and path relationship references. Missing scope is
  deliberately ambiguous.
- The narrow legacy candidate fallback exists only so pre-CR-1 artifacts can
  be interpreted; CR-1 relevance audit data is preferred.
- The evaluator does not parse natural-language evidence explanations.
- This contract judges explicit manifest non-causes; it is not a general
  causal calibration or recency-bias metric.
- Candidate-local topology claims without enough selected-path scope remain
  ambiguous rather than being guessed true or false.
