# SC-2 Lineage-Aware Candidate Admission Repair

Status: product repair checkpoint; LINEAGE-1 not rerun here.

## Before SC-2

- Exact provider-authentic source mutation: present.
- Exact source revision to Actions run to immutable image provenance: present.
- Source effective-time distance from incident: 789.95 minutes.
- Ordinary causal candidate window: 180 minutes.
- Candidate count: 0.
- Measured first divergence: `CAUSAL_CANDIDATE_MISSING`.

The frozen pre-SC-1 and post-SC-1 LINEAGE-1 baseline documents remain unchanged.

## After SC-2 target

An old canonical source revision may enter the existing causal evaluation only
when a strict path starts from the incident's explicitly pinned runtime topology,
identifies the exact affected container (or the only container), resolves the
exact immutable image used by the affected Pod and owning workload, and follows
complete provider-authentic build evidence to one exact repository/revision and
its canonical SC-1 source-change event.

The ordinary 180-minute path remains unchanged. An old event without exact
lineage remains excluded. Mutable tags, fuzzy identity, missing hops, ambiguous
multi-container scope, distinct-revision provenance for one digest, and traversal
overflow fail closed.

SC-2 does **not** claim source-level causal proof. It grants permission to
consider exact old evidence and preserves the existing downstream relevance,
ranking, evidence-ledger, and safe-abstention behavior. There is no lineage score
bonus, timestamp rewrite, source-age cutoff, or activation-time requirement.

## Remeasurement boundary

The same preserved LINEAGE-1 scenario must be rerun unchanged after this repair
is merged. That measurement, not this implementation checkpoint, determines
whether candidate admission succeeds in the real scenario and identifies the
next first divergence. SC-2 does not authorize a relevance, ranking, TC-4,
runtime-exit-code, incident-lifecycle, or evaluator repair.

