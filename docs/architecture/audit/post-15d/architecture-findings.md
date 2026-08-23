# Ranked architecture findings

No finding was repaired during this audit. “Blocks” distinguishes production V1 from Truth Contract/evaluation work; the current local/MVP workflow can still function.

## Critical

### F-001 — Production schema lifecycle is absent

- Evidence: `backend/app/db/database.py`, `backend/app/db/models.py`, no migration directory.
- Risk: startup `create_all`, zero foreign keys and JSON-heavy records cannot provide safe upgrades, rollback or referential guarantees.
- Affected: every durable V1 capability.
- Next action: establish a supported production database, migration baseline, constraints, backup/restore and upgrade test in a dedicated hardening block.
- Blocks: production V1; not a prerequisite for defining the Truth Contract.

### F-002 — Customer authentication/authorization boundary is incomplete

- Evidence: `backend/app/security/api_tokens.py`, `backend/app/security/approval_authorization.py`, `frontend/lib/topo-api.ts`, database models.
- Risk: auth defaults off; browser sends no credential; most routes have no role policy; no tenant columns/scopes exist.
- Affected: every customer-facing API/UI and data store.
- Next action: define deployment/auth session and tenant boundary before customer data is hosted.
- Blocks: production V1; does not block a local single-tenant evaluation harness.

## High

### F-003 — UID-less Kubernetes identity has three incompatible formats

- Evidence: `backend/app/collectors/kubernetes_collector.py:_entity_id`, `backend/app/services/agent_snapshot_ingest.py:_entity_id`, `backend/app/services/network_topology_enricher.py:_entity_id`.
- Risk: duplicate nodes and broken change/ownership/history correlation.
- Affected: identity, graph, source-runtime, lifecycle, RCA, blast radius.
- Next action: make a versioned canonical identity/alias decision in the Truth Contract, then migrate safely.
- Blocks: canonical identity Truth Contract and robust golden evaluation; only UID-less objects in current V1.

### F-004 — Legacy unpinned candidate analysis can use future/latest topology

- Evidence: `backend/app/services/incident_change_analysis.py` snapshot selection versus `backend/app/services/causal_rca.py` and `backend/app/services/continuous_lifecycle.py` safe selection.
- Risk: historical causal candidates can receive neighbor evidence unavailable at incident time.
- Affected: unpinned manual/legacy incidents, 13C input correctness.
- Next action: after Truth Contract temporal policy is approved, require pinned or at/before checkpoint selection consistently.
- Blocks: historical RCA evaluation for legacy/unpinned incidents; accepted 15D pinned path remains safe.

### F-005 — Edge provenance is incomplete and observed/inferred semantics are implicit

- Evidence: `backend/app/models/topology.py`, graph/enrichment services listed in `entity-relationship-inventory.json`.
- Risk: an edge can influence RCA/blast radius without an exact raw evidence reference or derivation rule/version.
- Affected: graph truth, source-runtime, RCA, blast radius.
- Next action: define relationship assertion authority, observation/inference status, rule version, evidence reference and confidence semantics.
- Blocks: relationship Truth Contract and defensible golden causal evaluation.

### F-006 — Confidence is heuristic but percentage-like

- Evidence: `backend/app/services/causal_rca.py`, `backend/app/services/incident_change_analysis.py`, `frontend/lib/code-runtime.ts`.
- Risk: customers interpret a weighted score as probability/certainty.
- Affected: RCA, code-runtime and remediation language.
- Next action: formalize score names/components/coverage and evaluate calibration before probability claims.
- Blocks: probability claims; does not block ranked evidence guidance with cautious wording.

### F-007 — Ownership mappings are not historical

- Evidence: `OwnershipMappingRecord` in `backend/app/db/models.py`; `backend/app/services/ownership_resolver.py`.
- Risk: old incidents can show today's stored owner rather than the owner at incident time.
- Affected: historical context, escalation, business impact.
- Next action: define ownership valid-time/revision behavior after temporal Truth Contract.
- Blocks: “owner at incident time” claims; current routing still works.

### F-008 — Complete source-to-runtime provenance is not proven

- Evidence: GitHub/Actions/container graph services and `frontend/lib/code-runtime.ts`; no Helm models/tests.
- Risk: UI/marketing can imply a verified chain where links are inferred, mutable or missing.
- Affected: change-to-RCA differentiation and responder trust.
- Next action: build one golden GitHub Actions + immutable registry digest + Kubernetes environment and preserve all raw link evidence.
- Blocks: full code-to-runtime claim and golden evaluation; not core Kubernetes incident lifecycle.

### F-009 — Blast radius ignores direction and edge semantics

- Evidence: `backend/app/services/blast_radius.py:traverse_blast_radius`.
- Risk: over-broad “affected” counts and business-impact routing; missing snapshot can also raise before the null guard.
- Affected: blast radius, ownership aggregation, briefing impact.
- Next action: define semantic traversal policy and evaluate precision against golden incidents before changing runtime behavior.
- Blocks: confirmed-impact claims, not graph-neighborhood context.

## Medium

### F-010 — Active architecture generations overlap

- Evidence: `backend/app/api/incidents.py`, `backend/app/api/incident_records.py`, legacy recommendation/recovery services, 14B/14C, advanced frontend.
- Risk: clients bind to the wrong IDs/contracts and new work reinforces two truth paths.
- Affected: API, frontend Advanced Analysis, CLI and persistence.
- Next action: publish canonical V1/deprecated/advanced ownership and add deprecation metadata before removal decisions.
- Blocks: clarity and maintainability; does not block current V1 cockpit.

### F-011 — Optional model governance has direct-provider bypasses

- Evidence: `llm_client.py` plus direct Groq calls in copilot/explanation/planner/report services.
- Risk: inconsistent redaction, fallback, observability and provider policy.
- Affected: advanced AI surfaces; not deterministic V1 facts.
- Next action: consolidate provider calls after the evidence/Truth Contract boundary is formalized.
- Blocks: enterprise model governance; not AI-disabled V1.

### F-012 — Frontend mixes live and demo truth sources

- Evidence: `frontend/lib/topo-data.ts`, `ask-view.tsx`, `cli-view.tsx`, `app-sidebar.tsx`.
- Risk: static examples can look like observed infrastructure/incident data.
- Affected: product trust outside the main cockpit.
- Next action: label/remove demo data from customer routes in a later product block; do not independently reconstruct conclusions.
- Blocks: customer presentation readiness; main cockpit remains live.

### F-013 — Automatic lifecycle lacks a durable backend job boundary

- Evidence: `backend/app/api/agents.py`, `backend/app/services/continuous_lifecycle.py`, absence of worker/scheduler process.
- Risk: expensive analysis occurs inline; process failure/backpressure can leave retry dependent on later ingestion/checkpoint events.
- Affected: 15D reliability and scale.
- Next action: specify idempotent job state and recovery semantics in production hardening, reusing existing durable records.
- Blocks: high-scale/HA production, not repository integration behavior.

### F-014 — Connector maturity lacks live/golden proof

- Evidence: `connector-maturity.json`, agent/backend tests.
- Risk: credentials, permissions, pagination, API drift and partial failures are unknown in real accounts.
- Affected: discovery/change coverage.
- Next action: prove one narrow Kubernetes/source environment before adding vendors.
- Blocks: broad production connector claims, not local MVP.

## Low

### F-015 — Package versions/deployment artifacts are inconsistent

- Evidence: backend `0.1.0`, agent `0.7.0`, CLI `1.2.0`, frontend `my-project` `0.1.0`; agent-only deployment artifacts.
- Risk: support/compatibility diagnosis and release operations are ambiguous.
- Affected: packaging and operations.
- Next action: define one release compatibility manifest and production packaging after truth/evaluation work.
- Blocks: neither Truth Contract nor local V1.
