# EAI-1 Evaluation Artifact Integrity Contract Implementation Baseline

Date: 2026-08-27

Branch: `evaluation/eai-1-artifact-integrity-contract-v1`

Accepted main/product commit before EAI-1: `b7fd0da72536f284217b3ec045a2617c017d433d`

Accepted main summary: `b7fd0da docs(evaluation): close LINEAGE-2A distractor robustness (#49)`

EAI-1 status: **CONTRACT IMPLEMENTED / VERIFIED**

Contract: **`evaluation-artifact-integrity-v1`**

## 1. Scope

EAI-1 adds prospective evaluation-infrastructure support for deterministic
result-tree identity. It does not alter product behavior, RCA semantics,
candidate ranking, AR-1, AR-2, AR-3, causal relevance, TC-4, incident behavior,
provider lineage, or the accepted LINEAGE-2A result.

LINEAGE-2A remains:

```text
ACCEPTED / CLOSED
ROBUST_IN_MEASURED_MATRIX
NO_DIVERGENCE
```

## 2. Existing convention audit

Before implementation, the evaluation harness contained deterministic JSON
helpers and a LINEAGE-specific `artifact-hashes.json` inventory. The latter
inventoried JSON artifacts created before the inventory itself; it did not
freeze one generic all-regular-file result-tree identity or a reusable
verification contract.

EAI-1 therefore adds a standalone generic module rather than changing or
reinterpreting the frozen LINEAGE harness. A future result family's existing
non-EAI inventory remains an ordinary included file.

## 3. Implemented contract

| Dimension | EAI-1 behavior |
|---|---|
| Version | `evaluation-artifact-integrity-v1` |
| Algorithm | SHA-256 |
| Digest representation | lowercase hexadecimal |
| Logical root | `.` |
| Path representation | result-root-relative POSIX `/` path |
| Unicode | NFC per path segment |
| Ordering | UTF-8 byte lexicographic |
| Included scope | all regular finalized files recursively |
| Canonical manifest | `artifact-integrity-v1.json` |
| Manifest self-inclusion | excluded only at result-root path |
| Per-file identity | SHA-256 of exact raw bytes plus `size_bytes` |
| Tree identity | SHA-256 of canonical tree-material bytes |
| Canonical JSON | UTF-8, `ensure_ascii=False`, sorted keys, compact separators |
| Newline | exactly one final LF |
| Dynamic metadata | none |

Exact OS metadata exclusions are `.DS_Store`, `Thumbs.db`, and `desktop.ini`.
No broad wildcard exclusion exists.

Known unfinalized suffixes `.tmp`, `.temp`, `.swp`, `.swo`, `.partial`,
`.lock`, `-wal`, `-shm`, and `-journal` fail closed using deterministic ASCII
case-insensitive suffix recognition.

Symlinks, linked roots, Windows junctions/reparse points, and other
non-regular filesystem objects are unsupported and fail closed. Filesystem
links are not followed.

## 4. Utility and APIs

Implementation:

```text
evaluation/artifact_integrity.py
```

Reusable APIs:

```python
build_integrity_manifest(root)
write_integrity_manifest(root)
verify_integrity_manifest(root)
```

Version constant:

```python
EVALUATION_ARTIFACT_INTEGRITY_VERSION = "evaluation-artifact-integrity-v1"
```

CLI:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation.artifact_integrity generate --root <result-root>
& .\backend\.venv\Scripts\python.exe -m evaluation.artifact_integrity verify --root <result-root>
```

Generation uses an exclusive temporary sibling, flush, file `fsync`, and
atomic `os.replace`. The temporary output is cleaned after success and after a
handled write failure where practical.

## 5. Verification and security

Verification independently scans and hashes the supplied root. It fails
closed for:

- invalid roots;
- transient trees;
- symlinks/reparse points;
- unsupported file types;
- missing manifests;
- malformed or noncanonical manifests;
- unknown contract versions;
- unsafe or colliding paths;
- missing or unexpected files;
- content or size mismatches;
- manifest-material/tree-digest mismatches; and
- atomic write failures.

Manifest paths are validated before current-tree comparison and are never
blindly opened. Absolute, drive-qualified, empty, `.`, `..`, and escaping
paths are rejected. Duplicate and Unicode-normalized collisions fail closed.

Changing one included byte changes its file digest and the tree digest.
Restoring the exact byte restores the original identity. Adding or removing an
ordinary file fails verification because the current and recorded file sets
must be identical.

## 6. Files created

- `evaluation/artifact_integrity.py`;
- `evaluation/tests/test_artifact_integrity.py`;
- `docs/architecture/evaluation/evaluation-artifact-integrity-v1.md`; and
- `docs/architecture/evaluation/baselines/eai-1-evaluation-artifact-integrity-contract.md`.

No existing file was modified.

## 7. Focused verification

Focused suite:

```text
evaluation/tests/test_artifact_integrity.py
82 passed, 3 skipped in 0.93s
```

The three conditional skips were the symlink-inside-root,
symlink-outside-root, and symlink-root cases because this Windows host did not
permit symlink creation. The production implementation still inspects both
symlink mode and Windows reparse-point attributes without following links.

The focused cases cover:

- one-file, empty, nested, and unknown-file roots;
- contract metadata and lowercase SHA-256;
- logical root and machine-path exclusion;
- slash normalization, traversal rejection, drive/absolute rejection, NFC,
  collisions, and UTF-8 ordering;
- creation-order and absolute-parent independence;
- exact bytes, LF/CRLF distinction, mutation, and restoration;
- recursive scope, empty directories, self-exclusion, and inclusion of legacy
  inventories;
- exact OS metadata exclusions and non-broad behavior;
- every frozen transient suffix and case-independent detection;
- atomic success and handled-failure cleanup;
- link/root-link rejection when host permissions permit link creation;
- compact UTF-8 canonical JSON, sorted keys, one final LF, and no dynamic
  metadata;
- repeated generation and read-only repeated verification;
- missing, unknown-version, malformed, missing-file, extra-file, content,
  size, entry-hash, tree-hash, metadata, duplicate-path, path-traversal,
  drive-path, whitespace, uppercase-digest, unknown-field, and ordering
  failures;
- CLI generation, valid verification, nonzero mismatch, and missing-manifest
  behavior; and
- absence of scenario-specific identities and historical result-root targets.

## 8. Regression verification

| Suite | Result |
|---|---|
| Backend compile | passed |
| Backend tests | `976 passed, 1 warning in 42.23s` |
| Agent compile | passed |
| Agent tests | `15 passed in 2.29s` |
| Evaluation compile | passed |
| Evaluation tests | `780 passed, 3 skipped in 35.68s` |

The evaluation suite collected 783 cases: 698 previously accepted cases plus
85 EAI-1 cases. No existing regression failed.

## 9. Historical boundary

Historical behavior is frozen as:

```text
legacy accepted result hashes remain untouched
```

No historical backfill was performed. EAI-1 did not write a manifest into:

- `lineage-2a-distractors`;
- `lineage-2a-post-ar1`;
- `lineage-2a-post-ar2`;
- `lineage-2a-post-ar3`; or
- `post-sc4`.

The accepted legacy bookkeeping observation remains unchanged: original
LINEAGE-2A and post-AR-1 trees were byte-stable during R5 and their component
hashes/inventories validated, while the later R5 full-tree procedure did not
reproduce some older published full-tree values. EAI-1 does not call those
historical identities wrong and does not rewrite them.

## 10. Future-family requirement

Every new evaluation family created after EAI-1 acceptance should generate and
successfully verify:

```text
artifact-integrity-v1.json
```

before its result baseline is accepted. The root must be finalized and
quiescent first. This is a prospective process and contract requirement, not a
historical migration.

## 11. Claim boundary and next action

EAI-1 proves deterministic artifact generation and verification behavior under
the implemented temporary-directory tests and current platform regressions. It
does not prove generalized RCA correctness, artifact durability outside the
filesystem guarantees used by the host, every network filesystem behavior, or
cross-host symlink/junction creation behavior.

Next action:

```text
ARCHITECT REVIEW / MERGE EAI-1
```

Only after approval should work expand to the next adversarial family. EAI-1
does not authorize AR-4, LINEAGE-2B, broken-lineage scenario creation, product
repair, or historical backfill.
