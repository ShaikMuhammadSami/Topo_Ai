# AR-2 Evidence-Gated Supported-Hypothesis Classification Repair

Status: product repair implemented; frozen LINEAGE-2A experiment not rerun.

Branch: `feature/ar-2-evidence-gated-supported-hypothesis-classification-v1`

Accepted foundation HEAD recorded before implementation:
`68cea672f4b67d8933870289fb72e885212a4677`.

Support policy: `causal-support-gate-v1`.

## Repair target

AR-2 repairs exactly the accepted post-AR-1 first divergence:

```text
FALSE_SUPPORTED_DISTRACTOR
```

It does not repair the queued final five-hypothesis-cap observation.

## Before

```text
LINEAGE-2A-R1 verdict: ADVERSARIAL_DIVERGENCE_FOUND
first divergence: FALSE_SUPPORTED_DISTRACTOR
false-supported controls: 54
false-supported scenarios: 15/16
```

First measured distractor:

```text
change-event:05a3d2361472923f5d545eaca1981f35
```

| Dimension | Frozen observation |
|---|---|
| Raw rank | `1` |
| Raw score | `50.65` |
| `candidate_entity_id` | `null` |
| Relevance | `identity_unresolved` |
| Topology component | `0` |
| TC-4 | `3 supporting / 0 contradicting / 0 missing / 0 unknown` |
| Claims | `runtime_failure`, `source_change`, `temporal_precedence` |
| Classification | `supported_under_current_model` |
| Completeness | `complete_for_current_model` |

The old path derived support from ledger presence with no contradiction or
missing item. It did not require accepted relevance or candidate-specific
linkage.

## Product repair

AR-2 inserts a categorical support gate after unchanged relevance and TC-4
evidence construction. A hypothesis is supported only when:

1. its current relevance audit is a recognized direct/semantic success tied to
   the affected incident scope;
2. its TC-4 ledger contains supporting candidate-bound linkage evidence; and
3. existing contradiction/missing semantics permit support.

Incident failure evidence and candidate temporal/source context remain useful
but cannot satisfy linkage.

## After target

The measured distractor shape may retain:

```text
TC-4: 3/0/0/0
raw rank: 1
high numerical score
```

AR-2 does not modify those facts. It now receives:

```text
relevance gate: unsatisfied
candidate-linkage gate: unsatisfied
support state: insufficient_candidate_specific_evidence
evidence completeness: partial
```

It is not called contradicted. No missing TC-4 claim is invented.

## Preserved legitimate causes

The accepted SC-4 source candidate remains supportable with:

- `candidate_entity_id = null`;
- resolution through `exact_immutable_lineage_anchor`;
- unchanged incident-pinned semantic topology path;
- topology component `0.85` in the synthetic golden contract;
- unchanged candidate-bound `topology_path` and
  `relationship_provenance` evidence; and
- no lineage or support score bonus.

Topology-native candidates remain supportable through real entity identity and
an accepted direct/semantic path. Same-entity relevance remains valid at zero
hops.

## Versioning and persistence

New analyses persist `causal-support-gate-v1` and a per-hypothesis gate audit.
The policy version is material to the analysis fingerprint. Save/readback
preserves gate state, reasons, and evidence references.

Historical analyses without AR-2 metadata remain readable. Their stored
support/confidence classification is retained rather than reinterpreted.

## Frozen boundaries

AR-2 leaves unchanged:

- `13c-causal-v1` scoring and ranking coefficients;
- raw ordering and tie behavior;
- Path A `180` minutes;
- SC-2, SC-3, and SC-4;
- `causal-relevance-v2` and its traversal sub-policy;
- `causal-evaluation-budget-v1`, ordinary Top-5, and selection bases;
- final five-hypothesis cap;
- TC-4 claim enum, generation, evidence references, IDs, and counts;
- incidents, topology, runtime, deployment health, agent, frontend, and
  workflows; and
- all files under `evaluation/`.

The count-50 final-cap observation remains queued. The synthetic count-50
contract records the unchanged natural behavior: the AR-1 frontier remains six,
all five returned temporal controls fail AR-2, and the exact-lineage candidate
reaches relevance but may remain outside the unchanged final five-hypothesis
projection. AR-2 does not special-case or repair that projection.

## Product-test evidence

Focused tests cover:

- the exact temporal-only `3/0/0/0` false-support shape;
- unresolved, ambiguous, unsupported-path, and high-score rejection;
- candidate claim binding and deterministic role audit;
- incident/context evidence insufficiency;
- candidate-bound topology, relationship, artifact, and event-lineage roles;
- topology-native, exact-lineage null-entity, and zero-hop success;
- contradiction, missing, and safe-abstention semantics;
- mixed raw-first distractor plus supported golden cause;
- count-50-shaped AR-1 frontier and unchanged final cap;
- support policy fingerprint materiality;
- persistence/fresh-session readback;
- historical payload compatibility; and
- absence of score, LLM, embedding, provider, evaluator-truth, or frozen-ID
  special cases.

## Measurement boundary

AR-2 product tests show that the measured defect shape is rejected while the
accepted legitimate contracts remain supportable. They do not prove that
LINEAGE-2A is robust, statistically general, or corrected in every preserved
scenario.

The same accepted 16-run LINEAGE-2A matrix must be rerun unchanged after
architect review and merge to determine whether `FALSE_SUPPORTED_DISTRACTOR`
disappears. No matrix rerun occurred in AR-2.
