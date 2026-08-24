# EVAL-GUARD-2 Repository-State Modernization Baseline

## Checkpoint type

Evaluation harness repair only. No product, agent, frontend, CLI, workflow,
manifest, ground-truth, or causal-grading behavior is changed.

## Observed pre-repair result

```text
621 collected
611 passed
10 failed
```

Nine failures came from mutable repository-state assumptions:

- five calls to the historical H3-only product diff helper;
- one EVAL-OCI product-cleanliness assertion;
- one runtime-causal product-cleanliness assertion;
- two source-failure-fixture product-cleanliness assertions.

One additional failure came from `test_lineage_baseline.py` invoking external
`rg` on a Windows environment where ripgrep was not installed or available on
`PATH`.

## Repair target

Replace mutable-worktree assumptions with immutable evidence:

```text
accepted historical commit
  -> deterministic changed paths under the intended scope
  -> exact frozen baseline comparison
```

Replace mandatory ripgrep execution with deterministic bounded Python source
scanning.

## Preserved invariants

- H3-R1's accepted historical product path set remains exact.
- Evaluation-only historical commits must contain no prohibited product paths.
- Frozen workflow and permanent manifest identities remain enforced.
- Forbidden LINEAGE scenario literals remain prohibited in product source.
- Evaluators remain independent of product reasoning implementation.
- Cause grading and ground truth remain unchanged.

## Non-claims

EVAL-GUARD-2 does not authorize a particular future product repair, alter causal
results, rerun LINEAGE, or make current worktree cleanliness an evaluation truth
signal. Product repair scope continues to be reviewed in that repair's own Git
diff and completion report.
