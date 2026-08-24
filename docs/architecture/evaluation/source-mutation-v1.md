# Source mutation truth v1

`eval-source-mutation-v1` is an evaluation-only contract for the initiating
source mutation in LINEAGE-1. It is not a Topo product Truth Contract.

## Purpose

Provenance can show that a commit led to a workflow run, image, workload, and
runtime signal without showing that the commit caused the failure. This
contract independently establishes the exact source fact that the later
causal experiment will test:

```text
evaluation/fixtures/lineage-image/runtime-mode.txt
healthy -> fail
```

The before and after bytes are canonical UTF-8 text with one trailing newline.
The contract records their SHA-256 hashes and safe semantic values. It never
stores secrets or derives expected truth from Topo output.

## Pending preparation state

LINEAGE-1A has no failure commit. A preparation record therefore uses
`status=pending` and sets repository ID/name, parent SHA, and child SHA to
`null`. Their future values must not be guessed.

The hashes and semantics can already be fixed because the allowed source
states are known:

- before bytes: `healthy\n`
- after bytes: `fail\n`
- mutation family: `file_content_change`
- scenario role: `initiating_mutation`
- expected failure: container entrypoint exits `42`

## Completed provider truth

LINEAGE-1B must populate the contract only after independently verifying the
provider repository, exact child commit, and its direct parent. The helper in
`evaluation/source_mutation_truth.py` reads bytes from local Git objects using
full provider-confirmed commit SHAs, verifies direct ancestry, and requires the
commit-wide changed-file set to contain only `runtime-mode.txt`.

Topo change records, explanations, hypotheses, or evidence are never inputs.

## Determinism and exclusions

There is no fuzzy diff, semantic similarity, time-window inference, LLM, or
embedding behavior. Any non-canonical bytes, extra changed files, abbreviated
SHA, parent mismatch, or unexpected semantic transition cause the evaluation
helper to reject the source claim.

