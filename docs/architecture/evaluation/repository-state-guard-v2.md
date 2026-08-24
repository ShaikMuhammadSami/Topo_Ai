# Evaluation Repository-State Guard v2

## Purpose

Evaluation contracts must protect durable truth boundaries without freezing a
developer's temporary worktree forever. EVAL-GUARD-2 separates immutable
repository evidence from non-authoritative local state.

## Why worktree cleanliness is not a product invariant

`git status --porcelain` answers whether a checkout differs from its current
index and `HEAD`. It does not answer whether an accepted historical evaluation
contract remains true. During a legitimate product repair, product files must
be dirty before review and commit. A permanent test requiring clean product
directories therefore prevents the evaluation suite from testing the exact
future repair it is supposed to evaluate.

Worktree state remains useful in a block completion report, but it is not used
as evidence for historical evaluation correctness.

## Historical H3-R1 origin

H3-R1 was the accepted product repair in commit
`38fd5e437b48250c654a96f236ea7d5e20eb5de0`. Its evaluation helper originally
allowed only the product files changed by that repair in the *current* Git
status. That was a temporary development convenience. Once later authorized
product blocks existed, the H3 file set became an accidental forever-allowlist.

Guard v2 preserves the meaningful historical claim: the product portion of the
accepted H3-R1 commit changed exactly the documented H3-R1 files. It derives the
observed path set from that immutable commit with `git diff-tree` and compares it
to the frozen expected set. A changed or missing historical path fails. A future
dirty product file is unrelated to that comparison.

## Historical evaluation-only blocks

Later evaluation blocks that intended to prove they introduced no product code
now inspect the accepted commit that implemented that block:

- LINEAGE-1A source failure fixture:
  `f9b152133a8075428766dd48b3f752b255ec5270`;
- LINEAGE-1C runtime causal observation:
  `9318efe6a13eab9e3dc114df75edd5784dacfdf9`;
- EVAL-OCI-1 runtime image identity:
  `6046f5d0ce7bb0a3d1b263322469b5b3420782b2`.

Their product-path assertion is therefore historical and immutable instead of
a requirement that every future checkout remain clean.

## Guard API

`evaluation/product_diff_guard.py` provides:

- typed historical commit baselines;
- deterministic historical changed-path extraction;
- exact historical path-set comparison;
- evaluation-only commit exclusion checks;
- exact SHA-256 and Git text-blob checks;
- deterministic repository text scanning.

The pure scope evaluator records current worktree paths only as
non-authoritative diagnostics. They cannot create historical violations.

## Future product repair compatibility

A future file such as
`backend/app/services/example_future_repair.py` may be modified or untracked
while historical evaluation contracts execute. It does not fail an unrelated
historical baseline. The repair's own block-specific review and Git report are
responsible for showing that its scope is authorized.

There is no branch-name logic, current-block path exception, or accumulating
product-repair allowlist.

## Portable source scanning

The prior LINEAGE product-literal check required the optional `rg` executable.
Guard v2 scans intended source roots directly with Python:

- roots are explicit and bounded;
- candidate paths and matches are sorted;
- common generated, dependency, cache, and virtual-environment directories are
  excluded;
- symlinks are not followed as files;
- binary, invalid UTF-8, and unreadable files are skipped deterministically;
- regular-expression search semantics preserve the prior forbidden-pattern
  check;
- no shell or external search executable is used.

## Guards that still deliberately fail

Guard v2 still fails when:

- an accepted historical commit's scoped path set changes or cannot be proven;
- the frozen H3-R1 historical product scope differs;
- an evaluation-only accepted commit contains a prohibited product path;
- the frozen provider workflow's exact byte SHA-256 changes;
- a permanent manifest's normalized Git blob identity changes;
- a forbidden evaluation scenario literal appears in product source;
- evaluator independence/import checks detect product reasoning dependencies;
- frozen ancestry, failure-branch, workflow, or manifest evidence changes.

Cause grading, LINEAGE truth, provider observation, OCI identity, source-cause
matching, and product reasoning semantics are unchanged.