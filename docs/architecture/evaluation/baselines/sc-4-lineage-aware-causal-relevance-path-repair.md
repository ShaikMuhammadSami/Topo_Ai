# SC-4 Lineage-Aware Causal Relevance Path Repair

Date: 2026-08-26

Product policy: `causal-relevance-v2`

## Before

The accepted LINEAGE-1I checkpoint recorded:

| Dimension | Result |
|---|---|
| SC-1 source identity | `PASS` |
| SC-3 image identity | `PASS` |
| SC-2 candidate admission | `PASS` |
| Candidate count | `1` |
| Exact immutable lineage | `admitted` |
| Candidate entity ID | `null` |
| Causal relevance | `FAIL` |
| Relevance status | `identity_unresolved` |
| Topology component | `0.0` |
| First divergence | `CAUSAL_RELEVANCE_PATH_MISSING` |

The admitted candidate was a source/change-domain event rather than a topology
entity. SC-2 had already persisted exact source revision -> run -> immutable
image provenance, and incident-pinned topology contained image -> Deployment ->
ReplicaSet -> Pod. V1 did not use the immutable image as a separate relevance
anchor when `candidate_entity_id` was null.

## Repair target

`causal-relevance-v2` can consume an already-admitted exact immutable artifact
as a separate relevance anchor into incident-pinned topology while preserving
the candidate's source/change identity.

The source candidate retains `candidate_entity_id=null`. The audit separately
records the exact `ContainerImage` anchor, SC-2 provenance bridge, and topology
path. Both topology-native and lineage-anchor modes use the same unchanged v1
topology evaluator.

## Preserved boundaries

SC-4 adds no lineage or bridge score, changes no ranking formula, does not
modify the 180-minute Path A, does not rewrite timestamps, does not expand TC-4
claims, and does not change SC-2 admission or SC-3 image semantics. It adds no
source/change topology entities, bridge graph entities, reverse persisted
edges, latest-topology fallback, provider re-traversal, fuzzy matching,
embeddings, or LLM behavior.

Missing, ambiguous, conflicting, or non-pinned anchors fail closed. Exact
provenance without a supported runtime topology segment remains unsupported.

## Measurement status

SC-4 deterministic product tests establish the repair contract. SC-4 does
**not** claim real LINEAGE success.

The same preserved LINEAGE-1 source, provider run, immutable image, and runtime
scenario must be rerun unchanged after architect review and merge to determine
whether `CAUSAL_RELEVANCE_PATH_MISSING` disappears and to locate the next first
divergence, if any.
