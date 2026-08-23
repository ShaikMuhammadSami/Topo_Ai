# TopoAI truth paths

This document identifies what the repository can prove, where evidence becomes inferred, and where the chain stops. Paths refer to the repository state after Block 15D.

## 1. Infrastructure-to-topology truth path

```text
external infrastructure APIs / local runtime
  → agent collector plugin
  → PluginCollectionResult inventory
  → AgentRunner snapshot submission
  → authenticated /api/v1/agent/snapshots
  → agent_snapshot_ingest normalization/enrichment
  → topology_checkpoint digest/debounce policy
  → topology_snapshots.payload_json (GraphSnapshot)
```

Owners and evidence:

- Plugin protocol/manager: `agent/src/topo_agent/plugin.py`, `agent/src/topo_agent/plugin_manager.py`, `agent/src/topo_agent/plugin_registry.py`.
- Periodic runner and disk buffer: `agent/src/topo_agent/runner.py`, `agent/src/topo_agent/buffer.py`.
- Agent API/auth: `agent/src/topo_agent/client.py`, `backend/app/api/agents.py`, `backend/app/security/agent_tokens.py`.
- Inventory-to-graph projection: `backend/app/services/agent_snapshot_ingest.py`, provider/runtime enrichment services.
- Immutable checkpoint payload: `backend/app/services/topology_checkpoint.py`, `backend/app/repositories/snapshot_repository.py`, `topology_snapshots`.

Truth boundary: the snapshot proves what a collector reported at `collected_at`, not that every external resource was visible. Partial plugin failures survive collection and are recorded in snapshot metadata. Relationship `evidence_ids` are often empty, so the snapshot/source metadata is frequently the only provenance.

## 2. Source-to-runtime truth path

```text
GitHub repository
  → GitCommit
  → GitHubWorkflowRun
  → ContainerImage
  → KubernetesDeployment / KubernetesPod
  → KubernetesService / dependency graph
```

Implemented link owners:

- Repository → commit: `backend/app/services/github_graph.py`, from GitHub repository database ID and commit SHA.
- Commit → workflow: `backend/app/services/github_actions_graph.py`, from workflow `head_sha`.
- Commit/workflow → image: GitHub enrichment/action metadata plus `backend/app/services/container_image_graph.py`; matching can use digest, annotations, exact SHA-like tags, or bounded prefix matches.
- Workload → image: requested image reference and observed runtime digest in Kubernetes inventory.
- Deployment → ReplicaSet → Pod: Kubernetes owner UID relationships.
- Service → Pod: exact selector-to-label matching.

The complete chain is `PARTIAL`, not proven end-to-end. No committed test constructs one real repository, workflow, registry artifact, deployment and Pod through live connectors. `frontend/lib/code-runtime.ts` reconstructs presentation chains from snapshot edges and computes a minimum edge confidence; it is a view algorithm, not an independent backend truth engine. Helm release/chart entities do not exist. Terraform changes are events but Terraform state resources are not graph entities. Therefore claims such as “Topo proves every commit is running in this Pod” exceed the current repository.

## 3. Change truth path

```text
snapshot A + snapshot B
  → snapshot_diff
  → NormalizedChange / changes table
  → optional promoted topology ChangeEvent

provider webhook or agent cloud/Kubernetes observation
  → source-specific normalizer
  → ChangeEventCreate
  → deterministic fingerprint/idempotent delivery
  → change_events + change_entity_links
```

Owners: `backend/app/services/snapshot_diff.py`, `backend/app/services/change_normalizer.py`, `backend/app/repositories/change_repository.py`, `backend/app/services/external_change_normalizers.py`, `backend/app/services/change_source_ingest.py`, and `backend/app/repositories/change_event_repository.py`.

A change is not a failure. `backend/app/services/topology_checkpoint.py:is_topology_affecting_change_event` decides whether a change requests a checkpoint. `backend/app/services/incident_grouping.py:is_failure_signal` separately decides whether a signal can create an incident.

## 4. Failure-to-briefing truth path

```text
qualifying Kubernetes failure observation
  → NormalizedSignal with exact object identity and timestamps
  → incident-boundary checkpoint submission/reuse
  → safe snapshot validation (at/before failure or exact signal-linked boundary)
  → deterministic entity resolution in that snapshot
  → signal persistence
  → incident fingerprint + bounded active-incident correlation
  → IncidentRecord with immutable first topology pin
  → automatic analyze_causal_rca
  → causal_analyses.payload_json
  → IncidentBriefing orchestration
  → /api/v1/incidents/{incident_id}/briefing
  → /app/incidents/{incidentId}
```

Owners: `agent/src/topo_agent/change_watch_kubernetes.py`, `agent/src/topo_agent/runner.py`, `backend/app/api/agents.py`, `backend/app/services/continuous_lifecycle.py`, `backend/app/services/incident_lifecycle.py`, `backend/app/services/causal_rca.py`, and `backend/app/services/incident_briefing.py`.

The first pinned snapshot does not move when later correlated signals arrive. If no safe checkpoint exists, the incident remains pending topology. `reconcile_pending_incidents_for_checkpoint` accepts only a checkpoint at/before the incident or an exact incident-boundary checkpoint carrying the incident's signal ID; it rejects an arbitrary future/latest graph.

Affected entity resolution order is exact explicit graph ID, exact Kubernetes UID, then exact scoped cluster/namespace/kind/name. There is no fuzzy or LLM identity choice. An ephemeral Pod remains the affected graph entity when exact Pod identity exists; workload ownership is represented by graph edges rather than silently rewriting identity.

Automatic RCA persists through `save_causal_analysis`, the same repository consumed by `/causal-rca/latest` and briefing. A valid graph with no supported change hypothesis is a controlled completed-no-hypothesis lifecycle state; Topo must not fabricate a root cause.

This path is covered by `backend/tests/test_continuous_lifecycle.py:test_real_agent_checkpoint_to_briefing_pipeline`, without a manual snapshot API call, manual RCA call or manual entity assignment. The agent side of collection/submission is separately covered with fakes in `agent/tests/test_continuous_capture.py`; that is not equivalent to a live Kubernetes conformance suite.

## 5. Causal RCA truth path

```text
IncidentRecord + pinned incident-time GraphSnapshot
  + bounded incident change-event candidates
  → event-lineage evidence graph
  → shortest topology paths
  → deterministic weighted ranking
  → ranked CausalHypothesis list
  → durable CausalAnalysisResponse
```

`backend/app/services/causal_rca.py` uses algorithm version `13c-causal-v1`. Its final score combines the prior incident-change candidate score (40%), topology component (25 points), temporal component (15), change-kind prior (10), and event-lineage component (10), capped at 100. The returned `confidence` is score divided by 100. It is a normalized heuristic ranking score, not a measured probability, posterior probability, reliability calibration, or guarantee.

The evidence graph records incident, change, entity-link, topology and temporal nodes/edges. It is strongest when exact change entity links and real topology paths exist. It does not have a first-class missing-evidence ledger, and the Block 13C `CausalEvidenceItem` contract is less explicit about counter-evidence than the older `IncidentEvidence` model. A no-hypothesis result is more truthful than a weak invented cause.

Historical correctness: `causal_rca._snapshot_for_incident` prefers the pinned snapshot and otherwise searches checkpoints at or before incident time. However, `backend/app/services/incident_change_analysis.py` can select the latest cluster snapshot for an unpinned legacy/manual incident without an incident-time cutoff. Since causal RCA invokes that candidate analysis, an unpinned legacy incident can acquire neighbor evidence from a later graph even though the causal topology path itself is incident-time bounded. This is a HIGH-severity truth-contract gap.

## 6. Blast radius and business impact truth path

```text
IncidentRecord.affected_entity_id
  + IncidentRecord.topology_snapshot_id
  → calculate_blast_radius (depth ≤ 5)
  → impacted entity IDs and paths
  → resolve_entity_ownership for each impacted entity
  → criticality/team/capability aggregation
  → IncidentOwnershipImpact
```

Owners: `backend/app/services/blast_radius.py`, `backend/app/services/ownership_resolver.py`, and `backend/app/services/business_impact.py`.

Blast radius uses the pinned snapshot, but currently traverses every relationship in both directions. It therefore represents graph proximity/possible influence, not proven traffic direction or a calibrated impact probability. Impact scores are distance/risk heuristics.

Ownership exact entity mappings score 1.0; scoped service mappings 0.90–0.99; kind/name mappings 0.85; entity metadata fallback 0.75; unresolved ownership is 0 and never invented. Stored mappings are current-state records with no validity interval. A historical incident resolves against a historical graph but current ownership configuration, so “owner at incident time” is not proven unless entity metadata in the snapshot supplies it.

## 7. Response and outcome truth path

```text
CausalAnalysis + pinned topology + OperationalContext
  → deterministic ResponsePlan actions and validation checks
  + bounded similar completed incidents/outcomes
  → ResponseIntelligence annotations
  → read-only remediation preview and verification plan

responder updates + durable recovery/change evidence
  → IncidentOutcome
  → future historical similarity/response evidence
```

Owners: `backend/app/services/response_plan.py`, `backend/app/services/incident_memory.py`, `backend/app/services/incident_similarity.py`, `backend/app/services/response_intelligence.py`, and `backend/app/services/incident_outcome.py`.

A rollback candidate requires a sufficiently strong current causal hypothesis plus a compatible durable change event and entity target. History cannot create current rollback eligibility. Historical support uses raw observed counts, conservative RCA-quality weighting and small-sample caps; it is not a success probability. Outcome attribution remains inconclusive when multiple simultaneous actions cannot be separated.

No response action executes infrastructure. Command-like text is guidance for a human. The main briefing has no execution transaction fields and does not call 14F, 14G or 14H.

## 8. Unified briefing and optional AI truth path

```text
deterministic structured incident facts
  → IncidentBriefing sections
  → optional sanitized prompt
  → central OpenAI client
  → ai_summary annotation only
```

`backend/app/services/incident_briefing.py` calls service-layer functions, not internal HTTP APIs. The structured result is built before any model call. Missing key, disabled AI or provider failure preserves the briefing and returns AI status/warnings. Tests assert that LLM prose cannot alter structured root cause, owner, impact, action, risk, history or outcome.

The older copilot, explanation, investigation and post-incident-report paths can call Groq directly. Their outputs are not authoritative inputs to the 15A structured briefing, but the provider duplication weakens system-wide governance.

## 9. Persistence truth boundary

All 37 tables are defined in `backend/app/db/models.py`. The default database is a local SQLite file selected in `backend/app/db/database.py`; startup calls `Base.metadata.create_all`. There are no declared foreign keys and no migration framework. Many rich domain records are serialized as JSON strings. This is suitable for an MVP/local deployment, but database constraints do not enforce cross-record provenance, immutability or retention.

The machine-readable table inventory is [persistence-inventory.json](persistence-inventory.json).


