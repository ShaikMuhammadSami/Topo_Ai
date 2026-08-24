# Source File Mutation Identity v1

## Purpose

SC-1 repairs the first measured LINEAGE-1 divergence,
`SOURCE_CHANGE_IDENTITY_WRONG`. The signed GitHub push was already durable, but
its normalized metadata stopped at repository, ref, push-level before/after
commits, and commit count. Exact provider file mutations were discarded before
persistence.

This contract treats a source file mutation as change evidence. It is not a
topology entity or relationship and does not assert a causal connection to a
runtime component.

## Provider-authentic flow

```text
signed GitHub push
  -> stable parent ChangeEvent
  -> exact repository + commit GitHub REST enrichment
  -> bounded per-file evidence normalization
  -> ChangeEvent metadata JSON persistence
  -> normal ChangeEvent repository/API serialization
```

Signature verification remains before JSON parsing, delivery persistence, or
provider access. The webhook establishes the source event and exact repository
and commit request. The existing GitHub connector supplies repository, commit,
parent, file status/path, blob identity, and bounded file bytes. The local
working tree, evaluation data, titles, LLMs, embeddings, and fuzzy matching are
not evidence sources.

## Identity contract

Every mutation uses schema `source-file-mutation-v1` and has a deterministic
`source-file-mutation:<digest>` identity. Its canonical identity includes:

- provider and stable provider repository ID;
- exact child commit and explicit parent context;
- change type;
- exact previous/current provider paths;
- before/after identity state and provider blob OIDs.

Paths remain case-sensitive, provider-controlled repository-relative strings.
They are never joined to the local filesystem or converted to host path syntax.

The parent `ChangeEvent` identity remains based on its existing GitHub external
ID. Enrichment data is deliberately excluded from the parent fingerprint, so
complete, partial, and temporarily unavailable enrichment cannot split one push
into multiple logical source events.

## Commit and parent semantics

Mutations are commit-scoped, not merely push-range scoped. A bounded set of
commit IDs from the signed push is fetched individually, and each mutation
retains its exact child commit.

For a single-parent commit, the before side is looked up at that exact parent.
A root commit has an explicit unavailable before state unless the provider's
change semantics prove absence. A multi-parent commit records all parents and
marks before state ambiguous; SC-1 does not choose an arbitrary merge parent.

Multiple mutations sort deterministically by commit, exact paths, change type,
and mutation ID. Provider response order therefore cannot change serialization.

## Change-type semantics

- `added`: before is explicitly absent; after is resolved at the child commit.
- `removed`: before is resolved at the single parent; after is explicitly absent.
- `modified`: before and after are independently resolved at parent and child.
- `renamed`: the previous path is resolved at the parent and the current path at
  the child.

Only provider change semantics may prove absence. A 404, permission denial,
transport error, response limit, or malformed provider response is an explicit
unavailable state, never absence.

## Provider blob identity and content identity

GitHub blob OIDs are stored as provider-native identities and are not labelled
SHA-256. When exact provider-returned bytes are obtained within capture bounds,
Topo computes a separate lowercase SHA-256 over those exact bytes before any
text decoding or terminal-newline display handling.

Provider blob inconsistency between the commit file record and content response
rejects the content evidence. The commit-file blob identity remains visible with
an explicit provider-error reason.

## Bounded scalar text

`bounded-scalar-text-v1` is deterministic display evidence, not interpretation.
It requires exact bytes, a small byte/character ceiling, valid UTF-8, no NUL,
one scalar line, and a conservative character set. At most one terminal LF (and
its optional preceding CR) is removed for display. The exact byte hash is
computed first and remains authoritative.

Binary, multiline, oversized, empty, or non-scalar text gets no semantic value
and records an explicit reason. No patches, arbitrary source files, or complete
file bodies are persisted.

## Bounds and completeness

Capture limits are centralized and may only be configured downward from safe
server ceilings:

- 20 commits per push;
- 100 files per enrichment operation;
- 64 KiB per file-content request;
- 512 KiB of captured bytes per event;
- 256 bytes and 128 characters for scalar display.

The GitHub commit request asks for the provider's maximum bounded first page.
Reaching an operation cap is conservatively partial, never complete. Push commit
list truncation, commit/file limits, unsupported status, provider error,
permission denial, identity mismatch, content limit, and multi-parent ambiguity
are explicit. Enumeration completeness and each side's identity/content/scalar
capture state remain independently inspectable.

## Persistence and idempotency

The typed mutation collection is serialized under the existing
`ChangeEventRecord.metadata_json` document. It therefore survives commit, a
fresh repository/session load, and the existing `ChangeEventView` and API JSON
path without a table or migration.

Webhook delivery deduplication remains unchanged. A different delivery of the
same logical push resolves to the same parent event fingerprint and replaces the
deterministically ordered evidence collection instead of appending duplicates.

## Provider failure

Provider enrichment is degraded evidence, not failure of the authenticated
source event. The signed delivery and parent event persist with `unavailable` or
`partial` completeness and bounded reason codes. A later separately delivered
observation may enrich the same parent event without changing its identity.

## Explicit non-goals

SC-1 does not:

- create `SourceFile`/`SourceLine` graph entities or file-to-runtime edges;
- change topology predicates, incident lifecycle, or historical pinning;
- change the 13C 180-minute window, admission, relevance, scoring, or ranking;
- change H3-R1 image lineage, runtime exit-code evidence, or blast radius;
- infer causality, widen a time window, or rerun LINEAGE-1;
- use local Git, evaluation truth, LLMs, embeddings, or fuzzy matching.

