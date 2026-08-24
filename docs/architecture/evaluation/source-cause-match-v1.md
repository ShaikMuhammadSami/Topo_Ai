# Source Cause Match v1

Status: **LINEAGE-1C independent evaluation contract**

Version: `eval-source-cause-match-v1`

## Purpose

This evaluator asks whether current Topo identifies the exact initiating
source mutation, rather than merely a true downstream symptom. It compares
structured identities only:

- repository;
- direct parent and failure commit SHA;
- changed file path;
- exact before/after SHA-256 values;
- canonical `healthy` to `fail` semantics.

Titles, token overlap, fuzzy matching, embeddings, time proximity alone, and
LLM output are never authoritative.

## Independent semantic levels

The actual Topo answer is classified as exactly one of:

1. `INITIATING_MUTATION` — the source file mutation;
2. `FAILURE_MECHANISM` — entrypoint exit 42;
3. `RUNTIME_MANIFESTATION` — termination, restart, or backoff;
4. `OPERATIONAL_IMPACT` — one desired and zero ready/available replicas;
5. `UNRELATED`;
6. `ABSTAINED`.

A lower, true level is `PARTIAL`, not exact root-cause success. A defensible
abstention is recorded separately and is not rewritten into a false claim.

## Verdicts

- `PROVEN`: Top1 is the exact initiating mutation and the structured lineage
  through the runtime failure is complete.
- `PARTIAL`: exact mutation is supported below Top1, only commit/image is
  identified, a lower semantic level is selected, or evidence is incomplete.
- `WRONG`: Topo supports a different initiating mutation.
- `MISSING`: a required upstream observation or supported hypothesis is absent.
- `INCONCLUSIVE`: reserved for an invalid/unfair experiment before grading.

## First divergence

The evaluator walks a fixed upstream-to-downstream taxonomy. The earliest
missing or wrong observation wins. It does not blame ranking when source
change ingestion or artifact lineage is absent.

## Evidence semantics

Supporting, contradicting, unknown, and missing evidence remain separate.
An item explicitly marked unknown is not counted as contradiction. Every
missing-evidence item requires a structured `expectation_basis`; absence of a
basis invalidates the evaluation artifact.

## Boundaries

The implementation is under `evaluation/`, imports no product reasoning
module, and never passes the expected source contract into Topo. It grades a
serialized observation produced after independent source/provider/runtime
truth is frozen.
