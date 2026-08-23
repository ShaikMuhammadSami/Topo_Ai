# TC-4 causal evidence ledger

## Purpose

TC-4 makes the evidence behind every new 13C causal hypothesis explicit and auditable. It does not replace candidate generation, topology traversal, causal-chain construction, scoring, confidence, or ranking. The existing `13c-causal-v1` analysis remains authoritative; TC-4 records what the selected analysis generation can support, what it can directly contradict, and what expected proof is unavailable.

The canonical runtime owner is `app.services.causal_evidence_ledger.build_hypothesis_evidence_ledger`. A ledger is attached to each `CausalHypothesis`, persisted inside the immutable `CausalAnalysisRecord.payload`, and reused by the incident briefing.

## Before-state matrix

| Existing evidence-like concept | Producer and source | Meaning | Persisted before TC-4 | Pinned snapshot | Durable reference | Temporal metadata | Relationship provenance | Score input | Before TC-4 form |
|---|---|---|---|---|---|---|---|---|---|
| Incident change candidate | 13A/13B records through `incident_change_analysis` | A durable change is temporally/scopally/entity relevant | Yes, indirectly in the RCA payload | Candidate correlation may use the pin | Change event ID | TC-3 after TC-3 | Not applicable | Yes | Candidate fields and reasons |
| Candidate reasons | `incident_change_analysis` and 13C | Human explanation of time, scope, and entity match | Yes | Sometimes | Often only through candidate | Partial | No | Reflect an already-computed score | Prose |
| `CausalEvidenceItem` | 13C | Temporal or causal-graph edge evidence | Yes | Analysis contains the pin | Evidence/event/entity IDs where available | TC-3 | No typed TC-2 object | Some inputs already affect score | Mixed structured data and prose |
| Change-to-entity link | `ChangeEntityLinkRecord` | Durable association between a change and topology entity | Yes | Correlation snapshot is recorded by ingestion | Event/entity/link row IDs | Link record times only | Not applicable | Yes, through direct/neighbor match | Repository row, not exposed as a stance |
| Entity path | Existing 13C graph traversal | Path from the changed entity to the incident entity | Yes, as chain steps | Yes after TC-3 | Entity and sometimes relationship IDs | Snapshot bounded | Available on snapshot relationship after TC-2 | Yes | Chain steps and reasons |
| Relationship provenance | TC-2 relationship linker/collector | Why an edge exists and who asserted it | Yes in snapshot | Yes | Relationship and provenance source references | Snapshot/relationship time | Yes | No separate score | Not exposed in hypothesis evidence |
| Event lineage | Existing 13C event graph | Selected predecessor/successor change chain | Yes | Analysis generation | Change event IDs and causal edge | Event TC-3 metadata exists | Not applicable | Yes | Causal chain and graph edges |
| Failure signal | Signal repository and incident lifecycle | Durable observed failure associated with the incident | Yes | Signal/incident may name the pin | Signal ID and involved entity/UID | TC-3 | Not applicable | Not a new TC-4 score | Incident context, not a hypothesis ledger |
| Contradiction | None as a first-class 13C collection | Evidence that directly conflicts with a claim | No | No | No | No | No | No | Occasional warning/prose only |
| Missing expected proof | Warnings/reasons in several services | A defensible expected source is absent or weak | Partial | Sometimes | Inconsistent | Inconsistent | Inconsistent | No | Warning/prose |

TC-4 preserves these producers and adds one typed, per-hypothesis view. It does not turn every warning or absence into evidence.

## Ledger shape

Each hypothesis has one versioned `CausalEvidenceLedger` with three deterministic collections:

- `supporting`: a durable source is consistent with a specific hypothesis claim.
- `contradicting`: a durable source directly conflicts with a specific hypothesis claim.
- `missing`: a specific source was reasonably expected for the claim but is unavailable, ambiguous, weak, or legacy-incomplete.

Every item contains a deterministic evidence ID, hypothesis ID, stance, claim type, source category, concise explanation, durable source references, applicable entity/change/relationship/signal/snapshot IDs, evidence quality, and typed TC-1/TC-2/TC-3 context where applicable.

The active claim taxonomy is:

1. `source_change`
2. `temporal_precedence`
3. `identity_resolution`
4. `entity_linkage`
5. `topology_path`
6. `relationship_provenance`
7. `runtime_failure`
8. `artifact_provenance`
9. `event_lineage`

The machine-readable definitions and allowed stances are in [causal-evidence-ledger-contract.json](./causal-evidence-ledger-contract.json).

## Stance semantics

### Supporting

Supporting evidence is tied to a real, durable source and is consistent with the hypothesis. Examples include a selected durable change event, an authoritative change time before the incident, a resolved TC-1 entity reference, a stored change/entity link, a real relationship on the pinned path, complete TC-2 provenance, the incident's durable primary failure signal, and an immutable image digest used by the changed workload.

Supporting means “consistent with and relevant to this claim.” It does not mean “proves the root cause.” A recent change or a topology path can be supporting evidence without being independently sufficient.

### Contradicting

Contradiction requires a source that proves a conflict. Current examples are:

- authoritative change effective time is after the incident boundary; and
- an exact non-empty candidate scope conflicts with the incident scope; or
- TC-1 resolves a source identity to one entity while a durable candidate link identifies another entity.

TC-4 does not infer contradiction from silence, missing logs, ambiguous identity, missing provenance, or absence of a path.

### Missing

Missing is used only when the architecture can state why a source was expected. The item must carry `expectation_basis`. Current examples include:

- an event explicitly names an entity but TC-1 resolution is ambiguous or unresolved;
- an existing 13C path relationship has legacy or incomplete TC-2 provenance;
- a durable linked candidate should have a path to the affected entity, but the pinned traversal found none;
- an incident explicitly references a primary signal that cannot be loaded; or
- a deployment/rollout/pipeline hypothesis reaches only a mutable image reference and lacks immutable digest or build-to-image proof.

No item is emitted merely because optional logs, traces, metrics, runbooks, history, or provider metadata do not exist.

## Unknown is not contradiction

The following states are missing or absent—not contradicting:

- identity ambiguity;
- unresolved identity;
- legacy relationship provenance;
- incomplete relationship source references;
- unavailable explicitly referenced signal;
- mutable artifact tags without immutable digest;
- no topology path where a durable linkage made the path expectation defensible; and
- sources that were never promised and have no defensible expectation.

This distinction prevents evidence sparsity from being presented as negative proof.

## Evidence identity

`evidence_id` is a deterministic digest over stable semantics: ledger version, hypothesis ID, stance, claim type, stable source-reference identity, durable entity/relationship/change/signal IDs, and snapshot ID.

It deliberately excludes prose, source-reference attributes, observed/recorded times, quality wording, and provenance serialization order. Those fields may be enriched without changing the identity of the underlying evidence claim. Sorted canonical references and IDs make ordering deterministic.

Evidence identity is generation-specific through `hypothesis_id`. It is not a global assertion that two future analyses have identical meaning.

## Source references

`CausalEvidenceSourceReference` records `reference_type`, stable `reference_id`, optional `source_system`, and non-identity attributes. It points back to durable records such as a change event, change/entity link, signal, snapshot, topology relationship, entity, artifact, or event-lineage pair.

An item must have at least one defensible source or durable ID. Missing items must additionally state the exact basis for expecting the unavailable evidence.

## Topology and relationship references

TC-4 receives the entity path already chosen by 13C. It performs no independent graph search and does not alter distance or path selection. For each adjacent entity pair, it finds the exact relationship on the already loaded pinned snapshot and records:

- relationship ID and predicate;
- path direction;
- relationship origin and source component;
- TC-2 source references;
- linker version; and
- TC-2 completeness.

Complete TC-2 provenance is supporting. Legacy or incomplete provenance is missing evidence with an expectation grounded in the real path relationship. The underlying relationship is not rewritten or upgraded.

## Temporal evidence

TC-4 carries the complete TC-3 `TemporalMetadata` for change and signal evidence. It compares the change event's effective time to the incident boundary chosen by the accepted temporal contract:

- authoritative pre-incident effective time: supporting precedence;
- authoritative post-incident effective time: contradicting precedence; and
- non-authoritative or weakly qualified time: missing temporal confidence where a comparison is expected.

Late arrival is not late occurrence. A change whose authoritative source time precedes the incident remains supporting even if `observed_at` or `recorded_at` is later. Those clocks remain visible and are never collapsed.

## Identity evidence

TC-4 calls the accepted TC-1 resolver against entities in the pinned snapshot. The full `CanonicalIdentityResolution` is stored on the evidence item.

- Resolved canonical/source-native/scoped-alias identity can support the hypothesis.
- Ambiguous identity is missing evidence and includes deterministic candidates.
- Unresolved required identity is missing evidence.
- A resolved identity that disagrees with a durable entity link remains supporting identity evidence, while the exact linkage disagreement is separately contradicting evidence.
- No fuzzy match, embedding, LLM, or best-effort owner rewrite is used.

Durable `ChangeEntityLinkRecord` rows are separately exposed as `entity_linkage` evidence so identity resolution and stored correlation are not conflated.

## Change, signal, lineage, and artifact evidence

A source-change item identifies each durable event already selected in the hypothesis chain. Event-lineage items expose only predecessor/successor edges already selected by 13C; TC-4 does not build another event graph.

Runtime-failure evidence references the incident's durable primary `NormalizedSignal`, preserves its stable involved identity and TC-3 time, and never invents signal proof. If the incident promises a primary signal ID but the row is unavailable, one bounded missing item is emitted. If no signal was ever referenced, no telemetry warning is fabricated.

Artifact evidence uses only real artifact entities and workload-to-artifact relationships on the pinned snapshot. An immutable digest is direct evidence. A mutable tag/reference is limited support and produces a separate missing item for immutable artifact/producer proof when the candidate semantics make that proof relevant. TC-4 is not a supply-chain inference engine and never claims a build produced an image without a durable producer reference.

## Persistence and immutability

The ledger is derived as part of a new causal-analysis generation and embedded in the existing JSON payload. No new table or duplicate evidence store is introduced.

Persisting the same deterministic `analysis_id` returns the existing record; it does not overwrite the payload or `generated_at`. This makes a persisted generation immutable. If durable late evidence changes the analysis input fingerprint, an explicit new analysis run produces a new generation and the prior generation remains loadable unchanged.

TC-4 adds its ledger version to the analysis input fingerprint. Recomputing an old pre-TC-4 analysis therefore creates a distinct generation rather than silently mutating the old row.

## Legacy behavior

Old analysis payloads validate with `evidence_ledger = null`. They are not backfilled with evidence that was not captured for that generation. Legacy topology relationship provenance remains labeled legacy and can yield an honest missing item only in a newly computed TC-4 generation.

## Historical correctness

The ledger uses only `CausalAnalysisResponse.topology_snapshot_id` and the snapshot loaded by 13C for that analysis. It never asks for the latest snapshot. A harmless later snapshot cannot change a persisted generation, supply a path, upgrade provenance, or repair artifact evidence.

## Relationship to current ranking

TC-4 does not change `13c-causal-v1` ranking. Existing components remain:

- 40% existing incident-change candidate score;
- topology component × 25;
- temporal component × 15;
- change-kind prior × 10; and
- event-lineage component × 10.

Ledger stance counts, evidence quality labels, missing evidence, and contradiction counts do not change the score or reorder candidates. In particular, a recent but unlinked change may still rank under current 13C rules; TC-4 makes its lack of entity/topology support visible rather than redesigning ranking.

## Briefing integration

The 15A incident briefing exposes the top hypothesis's canonical `causal_evidence_ledger` directly. It does not rebuild, paraphrase, or rescore the evidence. Existing compact `causal_evidence` remains for API compatibility.

## LLM and history separation

No LLM creates, classifies, ranks, or mutates ledger evidence. Optional incident narrative remains downstream and cannot alter structured facts.

Incident memory, similarity, historical response intelligence, response plans, and outcomes are also downstream. They may be shown beside an RCA but cannot enter TC-4 supporting, contradicting, or missing collections. This prevents a historically popular action or generated explanation from becoming causal proof.

## Known limitations

- TC-4 explains the evidence used by today's 13C algorithm; it does not correct all ranking weaknesses.
- Contradiction types are intentionally narrow because current durable data proves only a small set of conflicts.
- Artifact provenance is limited when collectors expose mutable tags without digests or durable build-to-image edges.
- Runtime evidence is limited to the incident's durable primary signal; TC-4 does not manufacture missing logs, traces, or metrics.
- A topology path explains connectivity, not causation.
- A source change and temporal precedence remain correlational evidence.
- Old analyses intentionally have no ledger until explicitly recomputed as a new generation.

These limitations are product truth, not failures to be hidden with probabilistic or generated language.
