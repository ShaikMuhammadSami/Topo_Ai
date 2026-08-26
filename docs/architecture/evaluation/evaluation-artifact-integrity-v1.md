# Evaluation Artifact Integrity Contract v1

Contract version: `evaluation-artifact-integrity-v1`

Canonical manifest: `artifact-integrity-v1.json`

Status: prospective evaluation-infrastructure contract

## 1. Purpose and boundary

EAI-1 defines one deterministic, portable identity for a finalized evaluation
result tree. It makes the file scope, per-file identities, tree identity, and
verification behavior explicit before a future evaluation baseline is
accepted.

This is evaluation infrastructure only. It does not change RCA semantics,
candidate ranking, AR-1, AR-2, AR-3, causal relevance, TC-4, incident behavior,
provider lineage, or the accepted LINEAGE-2A verdict.

The contract is prospective. Accepted result families created before EAI-1
remain legacy/pre-contract artifact identities. Their published hashes and
inventories are historical facts and are not rewritten, regenerated, renamed,
or backfilled.

## 2. Algorithm and digest representation

All content and tree digests use SHA-256. Canonical machine-readable digests
are exactly 64 lowercase hexadecimal characters. Verification validates this
canonical representation and performs digest equality checks after safe case
normalization.

## 3. Explicit result root

The caller supplies one existing directory as the evaluation result root. The
contract operates only beneath that root. The logical root recorded in
canonical material is always:

```text
.
```

Absolute repository paths, drive letters, workspace directories, usernames,
hostnames, and machine locations never enter the canonical identity. Two
byte-identical result trees at different absolute locations therefore receive
the same identity.

The supplied root must be a real directory. A missing root, regular-file root,
symlink root, junction, or other reparse-point root fails closed.

## 4. Canonical path semantics

Every included file is represented relative to the supplied result root.
Canonical paths:

- use `/` separators;
- preserve filename case exactly;
- contain no absolute, drive-qualified, empty, `.`, or `..` segments;
- contain no path escape;
- normalize each segment with Unicode NFC; and
- contain no environment-specific root prefix.

The path-normalization identifier is:

```text
relative-posix-nfc-v1
```

Backslash-separated input is normalized to forward-slash form by the reusable
normalizer. Persisted manifest paths must already be canonical. If two native
paths or two manifest entries normalize to the same canonical path, generation
or verification fails with `canonical_path_collision`; no path is silently
chosen.

## 5. Ordering

Entries are ordered lexicographically by the UTF-8 encoded bytes of their
canonical normalized paths. The ordering identifier is:

```text
utf8-byte-lexicographic
```

Identity never depends on recursive iterator order, filesystem creation order,
database order, locale, operating-system case folding, Python set iteration,
or dictionary insertion order.

## 6. Included and excluded scope

All regular finalized files recursively beneath the result root are included.
Directories are not entries, so empty directories do not affect identity.
Unknown filenames and future artifact types are included automatically.

The only self-excluded canonical path is the root manifest itself:

```text
artifact-integrity-v1.json
```

A nested file with the same basename is an ordinary included artifact.
Existing non-EAI files such as `artifact-hashes.json`, evaluator manifests,
inventories, databases, receipts, logs, and unknown regular files are included.

The exact OS metadata basenames excluded at any depth are:

```text
.DS_Store
Thumbs.db
desktop.ini
```

These exclusions are exact and case-sensitive. No wildcard, extension,
directory, JSON-only, or known-filename allowlist exclusion exists.

## 7. Finalized-tree and transient policy

A tree must be quiescent before generation or verification. A regular file
whose basename ends with any of these suffixes fails closed:

```text
.tmp
.temp
.swp
.swo
.partial
.lock
-wal
-shm
-journal
```

Suffix recognition is ASCII case-insensitive so platform case behavior cannot
turn known transient state into a finalized artifact. Transient files are not
silently excluded or hashed.

## 8. Links, reparse points, and special files

Symlinks, Windows junctions/reparse points, and linked roots are unsupported.
Scanning uses non-following metadata inspection and fails before treating a
link as a file or directory. Links are never traversed inside or outside the
root.

Non-regular filesystem objects such as sockets, devices, and FIFOs also fail
closed. EAI-1 identities cover regular finalized files only.

## 9. Per-file hashing and canonical entry

Each included file is streamed as raw bytes and receives:

```text
SHA256(raw file bytes)
```

EAI-1 does not decode text, normalize line endings, parse JSON, normalize
whitespace, or reserialize artifacts. LF and CRLF content are different bytes
and intentionally receive different identities.

Each canonical entry has exactly this structure:

```json
{"path":"relative/posix/path.json","sha256":"<lowercase sha256>","size_bytes":123}
```

`size_bytes` is the number of bytes actually hashed and is part of the
canonical tree material. Entries contain no mtime, ctime, inode, Windows file
ID, owner, permission, absolute path, or other environment-dependent field.

## 10. Canonical tree material

The tree digest covers this deterministic material without `tree_sha256`:

```json
{
  "algorithm": "sha256",
  "contract": "evaluation-artifact-integrity-v1",
  "entries": [
    {
      "path": "relative/posix/path.json",
      "sha256": "<lowercase sha256>",
      "size_bytes": 123
    }
  ],
  "ordering": "utf8-byte-lexicographic",
  "path_normalization": "relative-posix-nfc-v1",
  "scope": {
    "included": "all_regular_files_recursive",
    "links": "unsupported_symlink_or_reparse_point",
    "manifest_excluded": "artifact-integrity-v1.json",
    "os_metadata_excluded": [
      ".DS_Store",
      "Thumbs.db",
      "desktop.ini"
    ],
    "root": ".",
    "transient_files": {
      "policy": "forbidden",
      "suffixes": [
        ".tmp",
        ".temp",
        ".swp",
        ".swo",
        ".partial",
        ".lock",
        "-wal",
        "-shm",
        "-journal"
      ]
    }
  },
  "serialization": "utf8-json-sorted-keys-compact-lf-v1"
}
```

The illustrative indentation above is for documentation only. It is not the
canonical encoding.

## 11. Canonical JSON and tree digest

Canonical serialization is exactly Python `json.dumps` with:

```python
json.dumps(
    value,
    ensure_ascii=False,
    separators=(",", ":"),
    sort_keys=True,
) + "\n"
```

The resulting text is encoded as UTF-8. It contains no insignificant JSON
whitespace and ends with exactly one LF byte. The serialization identifier is:

```text
utf8-json-sorted-keys-compact-lf-v1
```

The tree identity is:

```text
tree_sha256 = SHA256(canonical_tree_material_bytes)
```

Generation then creates the final manifest by adding lowercase
`tree_sha256` to the material and canonically serializing the full object. The
manifest excludes itself from `entries`, avoiding circular identity.

No timestamp, branch, commit, hostname, absolute root, or generation metadata
is added. Repeated generation over an unchanged finalized tree therefore
produces identical entries, the same tree digest, and byte-identical manifest
content.

## 12. Generation and atomic output

The reusable module is `evaluation.artifact_integrity`:

```python
build_integrity_manifest(root)
write_integrity_manifest(root)
verify_integrity_manifest(root)
```

`build_integrity_manifest` is read-only. `write_integrity_manifest` writes
deterministic bytes to the exclusive temporary sibling
`.artifact-integrity-v1.json.tmp`, flushes and `fsync`s the file, and atomically
replaces `artifact-integrity-v1.json`. It removes its temporary file after
success and after handled write failure where practical. A pre-existing
temporary file is forbidden transient state and prevents generation.

## 13. Verification

Verification treats the manifest as untrusted input. It validates all manifest
paths and schema before using the current tree for comparison; it never opens a
path supplied by the manifest. It independently enumerates and hashes the
current root, then checks:

- manifest existence and canonical UTF-8 JSON bytes;
- exact supported contract version and metadata;
- exact entry schema, lowercase digests, and non-negative byte sizes;
- canonical, unique, correctly ordered paths;
- current file set against the manifest entry set;
- each included file size and SHA-256;
- stored tree digest against manifest material; and
- stored tree digest against independently rebuilt current tree material.

Verification fails rather than warns on a missing or unexpected file, modified
content, size mismatch, transient artifact, unsupported link, path collision,
malformed manifest, or digest mismatch. Adding an ordinary file after
generation is therefore a verification failure.

Unknown versions, including `evaluation-artifact-integrity-v2`, fail closed.
They are never interpreted as v1.

Structured error codes include:

- `invalid_root`;
- `transient_tree`;
- `unsupported_link`;
- `unsupported_file_type`;
- `missing_manifest`;
- `malformed_manifest`;
- `unsupported_version`;
- `invalid_canonical_path`;
- `canonical_path_collision`;
- `file_set_mismatch`;
- `content_mismatch`;
- `tree_digest_mismatch`; and
- `manifest_write_error`.

## 14. CLI

From the repository root:

```powershell
& .\backend\.venv\Scripts\python.exe -m evaluation.artifact_integrity generate --root <result-root>
& .\backend\.venv\Scripts\python.exe -m evaluation.artifact_integrity verify --root <result-root>
```

Successful output reports the contract, lowercase tree SHA-256, included-file
count, canonical manifest filename, and verification state. It does not place
an absolute root in canonical output. Verification or generation failure emits
a structured error code and exits nonzero.

## 15. Historical non-backfill boundary

EAI-1 does not alter any accepted LINEAGE-2A result family, post-SC4 seed, old
`artifact-hashes.json`, historical baseline, or published legacy hash. The
legacy original/post-AR-1 full-tree hash reproduction discrepancy remains
recorded as bookkeeping history, not silently reclassified as corruption.

No EAI-1 manifest is written into an accepted historical result root. A future
result tree's pre-existing non-EAI inventory is simply another included regular
file.

## 16. Future evaluation-family requirement

Every new evaluation family created after EAI-1 acceptance should generate and
successfully verify `artifact-integrity-v1.json` before its result baseline is
accepted. Generation happens only after the result root is finalized and
quiescent. Verification is a release/checkpoint gate and must fail closed.

Future contract versions require explicit implementation and architect review.
They must not reinterpret v1 or retrofit historical accepted families without
separate authorization.
