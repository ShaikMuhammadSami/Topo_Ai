# Production-readiness gaps

This is a ranked repository-reality gap list, not an implementation plan. Severity reflects risk to the V1 read-only incident-intelligence promise.

## Critical

### P0 — No production database migration or lifecycle strategy

Evidence: `backend/app/db/database.py`, `backend/app/db/models.py`, absence of Alembic/migration files.

The backend defaults to local SQLite and creates missing tables with `Base.metadata.create_all`. It has no schema version history, forward/backward migration process, rollback procedure, HA configuration, backup/restore contract, retention policy or tested database upgrade path. Rich records are frequently stored as JSON strings and the 37 tables declare zero foreign keys. A production deployment cannot safely evolve or guarantee referential integrity under this model.

### P0 — No tenant isolation and incomplete authorization

Evidence: `backend/app/security/api_tokens.py`, `backend/app/security/approval_authorization.py`, `backend/app/db/models.py`.

General API tokens identify a principal, but topology, incidents, agents, connectors and historical records have no tenant/account boundary. Most `/api/v1` operations only require an authenticated principal when auth is enabled; fine-grained roles are applied mainly to dormant approval/execution mutations. Authentication defaults to disabled and yields an admin/operator development principal. This cannot support a multi-customer production service safely.

### P0 — The browser client has no API authentication flow

Evidence: `frontend/lib/topo-api.ts`, `frontend/app/app/layout.tsx`, `backend/app/security/api_tokens.py`.

The browser API helper sets `Accept` but does not attach a bearer token, session cookie or another credential. There is no frontend login/session implementation. The UI therefore depends on `TOPO_AUTH_ENABLED=false` or an external proxy that is not present in this repository. Enabling the backend's standard API authentication makes normal browser requests return 401. This blocks a secure customer-facing deployment even before tenant isolation is considered.

## High

### P1 — Kubernetes entity identity is inconsistent across ingestion paths

Evidence: `backend/app/collectors/kubernetes_collector.py`, `backend/app/services/agent_snapshot_ingest.py`, `backend/app/services/network_topology_enricher.py`.

UID-backed identities align. UID-less identities do not: direct collection uses literal namespace/name, agent ingest hashes `cluster|kind|namespace|name`, and network enrichment hashes `cluster|namespace|kind|name`. The same object can split into multiple graph nodes depending on path. This threatens change correlation, ownership lookup, source-to-runtime chains and historical comparison.

### P1 — Unpinned legacy incident change ranking can read a later graph

Evidence: `backend/app/services/incident_change_analysis.py`, `backend/app/services/causal_rca.py`.

Block 15D auto incidents are safely pinned and causal topology selection searches at/before incident time. But the candidate change-analysis helper can use the latest cluster snapshot for an unpinned incident without an incident-time cutoff. A manual/legacy unpinned incident may therefore get neighbor evidence from a future topology. This is not an allowed latest-snapshot fallback and weakens historical RCA correctness.

### P1 — Relationship provenance is not consistently auditable

Evidence: `backend/app/models/topology.py`, `backend/app/services/agent_snapshot_ingest.py`, `backend/app/services/network_topology_enricher.py`, cloud enrichment services.

Relationships support `source_system`, `observed_at`, `confidence`, `evidence_ids` and `properties`, but many constructors leave evidence IDs empty and use a default confidence even for derived matches. An auditor can often identify the snapshot/plugin, but not always the exact raw observation or rule that justified an individual edge.

### P1 — Confidence is presented more precisely than it is calibrated

Evidence: `backend/app/services/causal_rca.py`, `backend/app/services/incident_change_analysis.py`, `frontend/lib/code-runtime.ts`, incident cockpit presentation components.

Causal confidence and graph-link confidence are deterministic heuristic scores. The repository contains no labeled evaluation corpus, calibration curve, false-positive/false-negative measurement, or production feedback calibration. Percentage formatting can be read as probability. Product language should call these evidence/ranking scores until calibration exists.

### P1 — Historical ownership is current-state, not valid-time

Evidence: `backend/app/db/models.py:OwnershipMappingRecord`, `backend/app/services/ownership_resolver.py`, `backend/app/services/incident_context.py`.

Historical RCA uses a historical graph, but stored ownership mappings have no `valid_from`/`valid_to` or revision snapshot. Re-running an old incident can show today's owner. Snapshot entity metadata can preserve historical labels, but mapping-based ownership cannot prove who owned the service at incident time.

### P1 — Source-to-runtime proof is incomplete

Evidence: GitHub, Actions and container image enrichment services; `frontend/lib/code-runtime.ts`.

The repository has useful edges, but no committed golden test covers repository → commit → workflow → immutable image digest → deployment → ReplicaSet → Pod → Service. Helm entities are missing, registry attestation/SBOM provenance is absent, and image tag identity is mutable. The UI must not claim universal verified provenance.

### P1 — Secrets and outbound webhook configuration lack production-grade storage

Evidence: `backend/app/db/models.py:WebhookEndpointRecord`, `backend/app/services/webhook_delivery.py`, `backend/app/models/change_sources.py`.

Native change sources correctly store a `secret_ref` and resolve it from the environment. Outbound webhook endpoints include signing secret and header JSON in application persistence. There is no KMS/vault encryption boundary, rotation workflow, per-tenant isolation or database encryption guarantee. The current local `backend/.env` is ignored and not tracked, but secret-at-rest design remains a production gap.

## Medium

### P2 — Blast radius over-approximates graph influence

Evidence: `backend/app/services/blast_radius.py`.

Traversal treats all edges as undirected, includes every relationship type/confidence and stops only by entity dedupe and depth five. Direction, edge semantics, staleness and evidence strength do not constrain influence. The result is useful neighborhood context, but affected counts should not be marketed as confirmed customer impact. The function also dereferences `graph.entities` before its explicit `graph is None` guard, so a missing snapshot can escape as an unexpected exception.

### P2 — Backend is a single request process with no durable job scheduler

Evidence: `backend/app/main.py`, absence of worker/scheduler entrypoints; `agent/src/topo_agent/runner.py`.

Continuous collection is agent-driven. Backend ingestion performs orchestration/analysis in the request path, and there is no durable queue, retry worker, lease-based analysis job, backpressure policy or dead-letter path for incident analysis. Webhook change ingestion has dead letters, but lifecycle analysis does not have equivalent operational machinery.

### P2 — Health and observability are shallow

Evidence: `backend/app/main.py:/health`, `backend/app/api/automation.py`, agent plugin diagnostics.

`/health` returns a static availability object without database, storage, connector, queue or model-provider dependency checks. Lifecycle status exposes helpful timestamps and latest correlation/checkpoint metadata, but there is no metrics endpoint, tracing, structured audit correlation, SLO, alerting, readiness/liveness separation or production dashboard configuration.

### P2 — API surface is broad and version ownership is unclear

Evidence: `backend/app/main.py`, [api-inventory.json](api-inventory.json).

There are 128 active routes including health, spanning old analysis/recommendation/recovery contracts, primary V1 briefing contracts, agent administration, connector administration and dormant execution systems. All share `/api/v1`. There is no deprecation metadata or primary/advanced/future partition in OpenAPI, making it easy for clients to bind to the wrong incident model.

### P2 — Frontend mixes live and demo truth

Evidence: `frontend/components/app/ask-view.tsx`, `frontend/components/app/cli-view.tsx`, `frontend/components/app/app-sidebar.tsx`, `frontend/lib/topo-data.ts`.

The primary incident home/cockpit is live. Ask, CLI simulator and sidebar incident context are static. Without explicit demo labeling, a customer can interpret fixture evidence as observed data. Frontend tests cover only the incident cockpit/briefing; most other routes lack behavioral tests.

### P2 — LLM provider use is not centralized

Evidence: `backend/app/services/llm_client.py` and four direct Groq callers listed in [duplication-dead-dormant.md](duplication-dead-dormant.md).

This complicates redaction, provider allow-listing, request logging, model governance, cost control, no-key behavior and incident-level auditability. The primary briefing boundary is safe; the concern is system-wide consistency.

### P2 — Connector proof is mainly mocked/unit-level

Evidence: backend and agent test inventories, [connector-maturity.json](connector-maturity.json).

AWS/Azure/GCP cache and selected relationship tests do not prove authentication, pagination, rate limits, permissions, API version drift, partial failure or real account scale. Kubernetes lifecycle tests prove the internal contract after inventory creation, but not live Kubernetes API conformance. Vendor change webhooks have uneven test coverage.

### P2 — Data retention, deletion and privacy controls are absent

Evidence: [persistence-inventory.json](persistence-inventory.json), database repositories.

Snapshots, raw webhook payloads, copilot messages, LLM-generated reports, runtime metadata and audit events have no configured TTL, archival, legal hold, per-subject deletion or raw-payload minimization policy. `store=false` controls OpenAI storage but not local database retention.

## Low / product clarity

### P3 — Version strings and package identity are inconsistent

Backend reports `0.1.0`, the agent package is `0.7.0`, and the CLI is `1.2.0`; the frontend package is named `my-project` at `0.1.0`. Evidence: `backend/app/main.py`, `agent/pyproject.toml`, `cli/pyproject.toml`, `frontend/package.json`. This is operationally confusing for support and compatibility diagnosis.

### P3 — Deployment packaging is agent-centric

The agent has a Dockerfile, Kubernetes RBAC/deployment and systemd unit. The repository has no backend/frontend production container manifests, Helm chart, compose environment, ingress/TLS deployment, horizontal scaling configuration or disaster-recovery runbook. Evidence: `agent/deploy/*`, `agent/Dockerfile`, and absence of corresponding root/backend/frontend artifacts.

### P3 — No committed architecture fixture/golden incident dataset

Most intelligence tests build rich fixtures inside test files. There is only one file under `test-data`. A versioned golden incident with raw source inputs, pinned graph, changes, RCA, context, plan, history and briefing would make cross-block regressions and claims easier to audit.

## Production claims that are defensible today

- TopoAI is a read-only incident intelligence MVP.
- It can ingest agent-submitted topology and preserve immutable incident-time checkpoints.
- It can deterministically create/correlate supported Kubernetes failure incidents, pin topology, resolve exact affected entity identity, persist causal analysis and serve a unified briefing.
- It can combine current evidence with ownership, business impact, response guidance and bounded historical evidence without using an LLM as the source of truth.
- It does not execute remediation.

## Claims that are not yet defensible

- Production-ready multi-tenant SaaS security or database durability.
- Universal or calibrated root-cause probability.
- Confirmed customer impact for every node in blast radius.
- Complete code-to-runtime provenance across Git, CI, registry, Helm and runtime.
- Live production maturity for all cloud/change connectors.
- Historical ownership correctness from stored ownership mappings.
- Autonomous or approval-driven remediation execution.

