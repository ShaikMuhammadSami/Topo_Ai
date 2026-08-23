# TopoAI post-15D repository reality audit

Audit date: 2026-08-23

Repository: `C:\Topo-ai`

Branch inspected: `audit/post-15d-repository-reality`
Scope: documentation/inventory only; no runtime behavior changed

## Executive conclusion

TopoAI contains a coherent read-only V1 incident-intelligence path, not merely disconnected feature stubs. The strongest repository-backed chain is:

```text
Topo Agent inventory and supported failure observation
  → immutable incident-time topology checkpoint
  → deterministic internal incident correlation
  → exact affected-entity resolution
  → durable Block 13C causal analysis
  → ownership/business impact/response/history/outcome orchestration
  → unified Block 15A briefing
  → incident home and cockpit
```

The internal checkpoint-to-briefing path is integration-tested. The repository does **not** prove every external connector against a live provider, a complete repository-to-Pod chain, probabilistically calibrated RCA, production database/security/tenancy, or autonomous execution. The latter is intentionally absent from the read-only V1.

The baseline contains 128 active FastAPI routes including `/health`, 37 SQLAlchemy tables, 77 produced entity kinds, 20 declared relationship enum values, and 14 relationship predicates constructed by current production graph builders. Four major architecture generations overlap: legacy signal analysis versus 13C/canonical incidents, legacy recommendations/recovery versus 14B/14C, centralized OpenAI versus direct Groq callers, and two snapshot repository interfaces. Blocks 14F/14G/14H are functional but dormant foundations; no infrastructure executor exists.

Critical production blockers are database/schema lifecycle, multi-tenant authorization, and the absence of browser authentication plumbing. High-risk truth gaps are inconsistent UID-less Kubernetes IDs, an unsafe latest-snapshot candidate-analysis fallback for unpinned legacy incidents, incomplete edge provenance, uncalibrated confidence percentages, current-state ownership applied to history, and incomplete source-to-runtime proof.

## Audit artifacts

- This human-readable architecture audit
- [implementation-inventory.json](implementation-inventory.json) — 40 classified capabilities
- [api-inventory.json](api-inventory.json) — every registered route
- [persistence-inventory.json](persistence-inventory.json) — every SQLAlchemy table/column/index
- [entity-relationship-inventory.json](entity-relationship-inventory.json) — identity producers and edge matrix
- [connector-maturity.json](connector-maturity.json) — connector maturity by dimension
- [frontend-api-consumption.json](frontend-api-consumption.json) — route/API truth sources
- [duplication-dead-dormant.md](duplication-dead-dormant.md)
- [truth-paths.md](truth-paths.md)
- [architecture-findings.md](architecture-findings.md)
- [production-readiness-gaps.md](production-readiness-gaps.md)

## Maturity definitions

Every major capability receives exactly one primary classification in `implementation-inventory.json`:

- **PROVEN** — implementation exists and a relevant committed automated/integration test exercises the stated boundary. It does not imply production certification.
- **IMPLEMENTED_BUT_UNPROVEN** — executable implementation appears present but the repository lacks convincing proof across the stated boundary or external system.
- **PARTIAL** — useful portions exist but the complete advertised capability is materially incomplete.
- **STUBBED** — a placeholder/demo interface exists with little or no live backend behavior.
- **DORMANT** — functional code exists but is intentionally outside the current V1 path.
- **DUPLICATED** — multiple active implementations or concepts substantially overlap without one universal owner.
- **DEAD** — code is unreachable/obsolete with no active route, process, test or documented purpose.
- **MISSING** — no implementation of the stated capability was found.

## Repository tree summary

The bounded tree contains five substantive roots:

```text
C:\Topo-ai
├── agent
│   ├── src/topo_agent          # agent, plugins, watchers, sensor
│   ├── tests                   # 6 test files
│   ├── deploy                  # Kubernetes, Tetragon, systemd artifacts
│   ├── Dockerfile
│   └── pyproject.toml
├── backend
│   ├── app/api                 # registered FastAPI routers
│   ├── app/collectors          # direct Kubernetes collectors
│   ├── app/connectors          # GitHub connector
│   ├── app/db                  # SQLAlchemy engine/models
│   ├── app/models              # Pydantic contracts
│   ├── app/repositories        # table access
│   ├── app/security            # API/agent/approval auth
│   ├── app/services            # graph and intelligence services
│   ├── tests                   # 20 test files
│   └── requirements.txt
├── cli
│   ├── src/topo_cli            # Typer client
│   ├── tests                   # 11 test files
│   └── pyproject.toml
├── frontend
│   ├── app                     # Next.js App Router pages
│   ├── components              # live and demo surfaces
│   ├── lib                     # API/types/presentation logic
│   ├── test                    # 2 Node test files
│   └── package.json
└── test-data                   # one repository test-data artifact
```

No root `scripts`, `config`, `infra`, `migrations`, `docker`, `compose`, or `helm` architecture exists. The only deployment artifacts are agent-focused. Generated package `dist` directories exist for agent/CLI but are not architecture sources.

## 1. Runtime and process architecture

| Process | Entrypoint/runtime | Responsibility and background behavior | Auth/persistence/network | V1 | Maturity |
|---|---|---|---|---|---|
| Backend API | `backend/app/main.py:app`; FastAPI/Uvicorn | Registers routers, request-time ingestion/intelligence, DB startup | API bearer middleware; agent and webhook exceptions have dedicated verification; SQLAlchemy; external GitHub/OpenAI/Groq/webhooks | Yes | PROVEN |
| Topo Agent | `agent/pyproject.toml` → `topo_agent.main:app`; `topo-agent run` | Long-running plugin collection every 300s by default, heartbeat every 30s, change poll every 30s, local retry buffer | Enrolls then uses agent bearer token; local config/credentials/buffer files; Kubernetes/cloud/local APIs and backend | Yes | PROVEN internally; connector behavior varies |
| Tetragon sensor | `agent/pyproject.toml` → `topo_agent.sensor_main:app`; `topo-sensor` | Separate long-running Tetragon event reader/aggregator | Agent bearer; local Tetragon stream; runtime sensor/event APIs | Optional | PARTIAL |
| Frontend | `frontend/package.json`; `next dev/build/start` | Next.js 16 App Router UI | Direct browser fetch to `NEXT_PUBLIC_TOPO_API_URL`; no bearer/session auth; no persistence | Yes | PROVEN for cockpit, mixed elsewhere |
| Python CLI | `cli/pyproject.toml` → `topo_cli.main:app`; `topo` | Interactive/automation client for backend APIs | Profile config, environment/keyring token, HTTPX; no domain persistence | Yes/supporting | PARTIAL |

There is no separate backend worker, scheduler, durable job queue, notification daemon or executor. Agent watchers are embedded in the agent runner. Automatic causal analysis executes in the backend ingestion transaction/request path.

## 2. Backend API inventory

`backend/app/main.py` registers every active router. FastAPI 0.128 represents included routers as `_IncludedRouter`, so the audit traversed each registered `original_router`; this produced 127 `/api/v1` operations and the hidden `/health` route, total 128. Documentation routes are framework-generated and excluded from the endpoint inventory.

The authoritative per-route method/path/handler/module/request/response/service/repository/persistence/auth/V1/maturity map is [api-inventory.json](api-inventory.json).

Authentication rules come from `backend/app/security/api_tokens.py`:

- `/health`, OpenAPI/docs and OPTIONS are public.
- `/api/v1/agents/enroll` uses a one-time enrollment token enforced inside the agent API.
- `/api/v1/agent/*` uses the dedicated active-agent bearer dependency.
- `/api/v1/change-source-webhooks/*` bypasses global API-token middleware but verifies the configured provider signature/shared secret in `change_source_ingest.py`.
- Other `/api/*` routes require a Topo bearer token only when `TOPO_AUTH_ENABLED=true`; otherwise they receive an admin/operator development principal.
- Approval/execution mutations add admin/operator policy from `backend/app/security/approval_authorization.py`; most other domains have no distinct role authorization.

Primary V1 endpoints are incident records, signals, snapshots, change events, causal RCA, blast radius, operational context, response plan, outcome, history/response intelligence, lifecycle status, briefing and automation status. Legacy/advanced endpoints remain registered. Readiness, approval and execution-intent routes are future/dormant but reachable.

## 3. Database and persistence inventory

`backend/app/db/models.py` defines 37 tables. [persistence-inventory.json](persistence-inventory.json) records every ORM class, key, column, reference-shaped field, unique constraint, index, timestamp and serialized JSON field.

Domain totals:

- Topology/identity: `topology_snapshots`, `identity_resolutions`, `identity_overrides`.
- Change intelligence: `changes`, `change_events`, `change_entity_links`, `change_sources`, deliveries/dead letters.
- Incident intelligence: `signals`, canonical `incidents`, legacy `incident_analyses`, `causal_analyses`, explanations/copilot/plans/reports/outcomes.
- Response/ownership: ownership mappings, legacy recommendations/recovery.
- Agent/runtime/cloud: agents/enrollment, runtime sensors/processes/dependencies, cloud accounts/resources.
- Integrations: outbound webhook endpoints/deliveries.
- Dormant control plane: approval and execution intent current/event tables.

Important graph/evidence payloads are serialized in `topology_snapshots.payload_json`, `causal_analyses.payload_json`, legacy analysis/recommendation/recovery payloads, identity resolution payloads, incident outcome payload/source JSON, and LLM-derived explanation/plan/report payload/evidence JSON. Webhook/change records also retain raw or processed JSON.

Schema lifecycle is MVP-only: `backend/app/db/database.py` defaults to `backend/data/topo.db`, accepts `TOPO_DATABASE_URL`, and calls `Base.metadata.create_all` during lifespan startup. No Alembic/migration files exist. The model metadata contains zero foreign keys. Referential links such as incident ID, snapshot ID and analysis ID are application-enforced strings. Immutability/append-only behavior is mostly service convention; event tables preserve audit history, while incident/configuration tables mutate.

## 4. Entity identity inventory

The canonical graph contract is `backend/app/models/topology.py:Entity`. It separates graph `id`, `external_id`, source system, type/kind/name, environment, observed time, labels and properties. The complete constructor inventory is in [entity-relationship-inventory.json](entity-relationship-inventory.json).

Major formats:

- Kubernetes direct: `k8s:{cluster}:{kind}:{uid-or-scoped-name}`.
- Kubernetes agent: `k8s:{cluster}:{kind}:{uid-or-24-char-hash}`.
- GitHub repository: `github:{host}:repository:{database_id}`; commit appends SHA; workflow run uses provider run ID.
- Container image: digest identity when available, otherwise hash of normalized reference.
- AWS/Azure/GCP: provider ID and scope normalized into provider-prefixed hashes; raw provider IDs remain properties/external IDs.
- Runtime: content digests for host/process/container/port/endpoint observations.
- Logical identity: `backend/app/services/identity_resolver.py` creates separate grouping IDs and supports manual overrides; these do not replace graph IDs.
- Incident/change/signal fingerprints are separate domain identities and must not be parsed as entity IDs.

### IDENTITY MODEL CONFLICTS

1. **HIGH — UID-less Kubernetes identity differs by path.** `kubernetes_collector.py` uses literal `namespace:name`; `agent_snapshot_ingest.py` hashes `cluster|kind|namespace|name`; `network_topology_enricher.py` hashes `cluster|namespace|kind|name`. UID-backed objects are safe; fallback objects can split.
2. **MEDIUM — Pod identity is lifetime-stable, not workload-stable.** A Pod UID changes on replacement. Incident fingerprinting intentionally strips ReplicaSet/Pod suffixes to correlate a workload, but the affected entity remains the exact Pod in the pinned graph. These are correctly distinct concepts but easy for consumers to conflate.
3. **MEDIUM — Image reference and image digest identities differ.** Digest nodes represent immutable content; tag/reference nodes represent a mutable name.
4. **MEDIUM — Change provider IDs versus cloud graph hashes.** `ChangeEventEntityReference` supports provider resource ID/external ID, while graph IDs are opaque hashes. Correlation must search properties; no universal DB link enforces it.
5. **MEDIUM — Git repository identity differs across data sources.** GitHub graph identity prefers provider database ID, while change events frequently carry owner/name or URL. Linking depends on normalized repository metadata.

Affected-entity selection in `continuous_lifecycle.py:_entity_for_signal` is deterministic: explicit graph ID, exact UID/external ID, then exact scoped kind/name. It has no fuzzy or LLM matching. Tests prove UID selection for ephemeral Pods.

## 5. Relationship and edge inventory

The model declares 20 `RelationshipType` values; current production builders construct 14: `contains`, `owns`, `produces`, `triggers`, `runs`, `selects`, `exposes`, `routes_to`, `calls`, `depends_on`, `uses`, `protects`, `resolves_to`, and `attached_to`. `deploys`, `emits`, `observes`, `affects`, `derived_from`, and `unknown` are declared but were not found as intended production constructors.

Compact edge matrix:

| Source | Predicate | Target | Construction/evidence | Maturity |
|---|---|---|---|---|
| Cluster/Namespace | contains | namespace/workload/service | inventory scope/UID | PROVEN internally |
| Deployment | owns | ReplicaSet | ownerReference UID | PROVEN |
| ReplicaSet | owns | Pod | ownerReference UID | PROVEN |
| Pod | attached_to | Node | `node_name` exact lookup | PROVEN internally |
| Service | selects | Pod | selector equals labels | PROVEN |
| Ingress | routes_to | Service | backend service name | PARTIAL |
| Service/EndpointSlice | routes_to/exposes | Pod/endpoint | EndpointSlice target UID/address | PARTIAL |
| Pod/Process | calls | endpoint | annotation or runtime observation | PARTIAL |
| Repository | contains | Commit | provider repository/commit data | IMPLEMENTED_BUT_UNPROVEN |
| Commit | triggers | WorkflowRun | head SHA | IMPLEMENTED_BUT_UNPROVEN |
| Commit/Workflow | produces | ContainerImage | digest/SHA/tag/annotation metadata | PARTIAL |
| Workload | uses/runs | ContainerImage/Container | requested image/runtime digest/container metadata | PARTIAL |
| Cloud scope/network | contains/attached_to/protects/routes_to/runs | provider resources | provider reference fields | PARTIAL |
| Host/Container/Process | contains/runs/exposes/calls | runtime object/endpoint | local inventory or Tetragon event | PARTIAL |

Every relationship is snapshot-scoped once persisted. It stores `observed_at`, `source_system`, `confidence`, optional evidence IDs and properties. Direct owner/select relationships have strong raw identity evidence. Cloud, source-artifact and dependency relationships can be inferred from provider properties, names, annotations or prefixes. Many constructors leave `evidence_ids=[]` and default confidence to 1.0 even when inference is involved. This is the primary edge-provenance gap.

RCA shortest paths and blast radius consume these edges. RCA treats topology paths as undirected for distance; blast radius also treats every edge as bidirectional.

## 6. Source-to-runtime linkage audit

| Hop | Mechanism/identifiers | Temporal/provenance | Proof | Maturity | Missing proof |
|---|---|---|---|---|---|
| Repository → Commit | GitHub repo database ID and commit SHA; `github_graph.py` `contains` | GitHub observed data | No focused connector test | IMPLEMENTED_BUT_UNPROVEN | Live pagination/auth and multi-repo proof |
| Commit → CI/CD build | Actions run `head_sha`; `github_actions_graph.py` `triggers` | run/commit times | No focused test | IMPLEMENTED_BUT_UNPROVEN | Other CI providers do not create graph pipeline entities |
| Build → Container image | run image digest/metadata; `produces` | workflow metadata | No golden chain | PARTIAL | Registry/build attestation and reliable digest output |
| Commit → image | workload annotations or exact/prefix SHA tag | snapshot observation | Ambiguity suppression in code | PARTIAL | Signed provenance; tag collision/retag proof |
| Image → Deployment/Pod | normalized requested reference and runtime digest; workload `uses/runs` | snapshot collection time | Graph code exists | PARTIAL | Registry identity unification and full chain test |
| Deployment → ReplicaSet | Kubernetes owner UID | object observation time | Lifecycle/topology fixtures | PROVEN |
| ReplicaSet → Pod | Kubernetes owner UID | object observation time | Lifecycle/topology fixtures | PROVEN |

No Helm chart/release entity exists, so Repository → Image → Helm → Deployment is impossible as a formal graph path today. The frontend code-to-runtime view builds chains from actual edges but does not make them more authoritative.

Terraform path:

| Hop | Status |
|---|---|
| Terraform Cloud notification → ChangeEvent | PARTIAL; webhook normalizer/security exists |
| ChangeEvent → cloud entity | PARTIAL; configured/provider reference correlation can link |
| Cloud resource → load balancer/network dependency | PARTIAL; provider inventory relationships exist |
| Cloud resource → Kubernetes workload/application | PARTIAL; provider/name matching exists only for selected managed-cluster/node cases |

There is no Terraform state/resource graph or plan-to-runtime provenance chain. A Terraform change event alone does not prove which cloud topology edge changed.

## 7. Topology model

`GraphSnapshot` contains schema version, snapshot ID, `collected_at`, dict `scope`, entities, relationships, evidence and metadata. The database stores the complete Pydantic payload as JSON. The “live graph” is the latest persisted/selected snapshot; there is no separate mutable graph database.

Capture paths:

- Manual API capture: `backend/app/api/snapshots.py` uses direct Kubernetes collection and remains an expert fallback.
- Agent periodic full collection: plugin manager → agent submission → graph enrichment → checkpoint persistence.
- Change checkpoint: meaningful topology-affecting events request automatic collection; default debounce is 30 seconds.
- Incident boundary: agent prioritizes incident-boundary collection when failure signals exist and includes trigger signal IDs.
- Periodic reconciliation: default agent collection interval is 300 seconds.

`topology_state_digest` canonicalizes entity/relationship material state and ignores observation-only noise. `persist_topology_checkpoint` reuses identical state and can debounce rapid automatic checkpoints. Snapshot metadata records reason, previous snapshot, digest, debounce and trigger IDs. Snapshot diffs become `NormalizedChange` records and may be promoted to topology change events.

Historical selection:

- Incident lifecycle pins the first safe snapshot and never moves it.
- Pending reconciliation accepts at/before incident time or exact signal-linked incident-boundary snapshots.
- Causal analysis loads the pin or a checkpoint at/before incident time.
- Blast radius, operational context, response, memory and briefing use the incident/analysis pin.
- **Unsafe exception:** unpinned legacy `incident_change_analysis` can select the latest cluster snapshot without an incident-time cutoff, affecting neighbor candidate evidence.

## 8. Temporal semantics

| Domain field | Current meaning |
|---|---|
| `Entity.observed_at`, `Relationship.observed_at`, topology `Evidence.observed_at` | collector observation time; not resource valid-from time |
| `GraphSnapshot.collected_at` | collection/checkpoint time supplied by collector/agent |
| `SnapshotRecord.saved_at` | database system/persistence time |
| normalized change `detected_at` | snapshot diff detection time; before/after snapshot IDs carry material interval |
| `ChangeEvent.occurred_at` | provider/source event time |
| `ChangeEvent.received_at`, delivery `received_at` | Topo ingestion time |
| change/event `created_at`, `updated_at` | record system time |
| signal `first_observed_at`, `last_observed_at` | source observation interval |
| signal `received_at`/record timestamps | ingestion/system time |
| incident `first_observed_at`, `last_observed_at` | correlated signal observation interval |
| incident `created_at`, `updated_at`, `resolved_at` where present | record lifecycle/system/responder time |
| causal `generated_at` | analysis computation/persistence time; event evidence retains its own times |
| outcome mitigation/resolution/action times | responder/evidence-derived event times; outcome create/update are system time |

Valid time and system time are not formalized across all tables. Timestamps are frequently ISO strings in SQLite rather than typed DB timestamps. Ownership/configuration lacks valid-time versioning. Cloud/runtime current records can be updated in place, while snapshots preserve historical observation. Clock skew between providers, agent and backend is not modeled.

## 9. Change intelligence

13A preserves two related contracts. `NormalizedChange` represents entity/relationship/material snapshot differences and is persisted by `change_repository.py`. `ChangeEventRecord` represents durable native/topology-promoted events with deterministic fingerprint, source/kind/risk, raw payload, observation count and entity links.

13B source adapters:

- Configured webhooks: GitHub, GitLab, Jenkins, Azure DevOps and Terraform Cloud.
- Agent-submitted change events: Kubernetes and polling AWS CloudTrail/Azure Activity Log/GCP Audit Log observers.
- Native enrichment: GitHub repository/Actions graph enrichment.

Webhook verification uses HMAC, signed token, secret token or Basic auth as appropriate. `ChangeSourceCreate` stores a `secret_ref`, not the actual secret; `resolve_secret` loads it from the configured environment. Delivery IDs/payload hashes provide idempotency; failed deliveries have dead-letter/replay persistence. Raw payloads are redacted for configured sensitive key names before persistence, though redaction cannot guarantee every vendor-specific secret field.

Entity linking uses explicit graph ID first, then external/provider IDs and exact scoped kind/name matches against a selected snapshot. Links store type, confidence, reason and optional snapshot ID. Incident relevance ranking is deterministic temporal/entity-neighbor/scope/risk scoring.

Independent connector maturity is in [connector-maturity.json](connector-maturity.json).

## 10. Connector maturity

There are 24 connector/integration entries in the inventory, including missing future vendors. No broad cloud/Kubernetes connector is marked PROVEN merely from mocked unit tests. Summary:

- PROVEN internal contract: Topo Agent submission/auth and Kubernetes failure/checkpoint lifecycle after an inventory is produced.
- PARTIAL: Kubernetes inventory; AWS/Azure/GCP inventory; Tetragon; GitHub and Terraform webhook subsets.
- IMPLEMENTED_BUT_UNPROVEN: cloud audit-log polling, host/Docker/network collectors, GitHub/Actions enrichment, GitLab/Jenkins/Azure DevOps, outbound webhook.
- MISSING: Alertmanager, Grafana, Datadog, New Relic, PagerDuty, ServiceNow, Jira and Opsgenie adapters.

The exact per-connector dimensions—inventory, event ingestion, auth, normalization, relationship construction, entity linking, automated test, golden proof and runtime wiring—are in [connector-maturity.json](connector-maturity.json).

## 11. Signal and incident lifecycle

The accepted 15D production path is:

1. `KubernetesChangePoller` in `agent/src/topo_agent/change_watch_kubernetes.py` observes Kubernetes events and separates topology changes from failure signals.
2. Supported reasons are `BackOff`, `CrashLoopBackOff`, `ErrImagePull`, `ImagePullBackOff`, `Failed`, `FailedScheduling`, `FailedMount`, `FailedAttachVolume`, `FailedCreate`, and `Unhealthy`.
3. The agent runner takes/reuses an incident-boundary checkpoint before submitting deferred failures and adds the returned snapshot ID to signals.
4. `backend/app/api/agents.py:submit_failure_signals` validates agent scope and invokes `ingest_failure_signal_batch`.
5. Signals are safely bound to topology, persisted in `signals`, and grouped only if severity is warning/error/critical. Info signals do not create incidents.
6. `incident_fingerprint` hashes `incident-group-v2|cluster|namespace|stable_workload_subject`. It intentionally omits exact reason so BackOff/ImagePull variants for one workload coalesce. This also means distinct failure categories on the same workload inside the window may coalesce.
7. `find_correlatable_incident` searches the same fingerprint among active statuses within a default 120-minute server window. Resolved/dismissed or stale incidents are not reused; replay protection prevents an old resolved signal from creating a false recurrence.
8. `upsert_incident_from_orchestration` creates or enriches the canonical incident, preserves first observed time and signal evidence, and never changes an existing topology pin.
9. Affected entity resolution is explicit ID → UID → exact scoped kind/name.
10. `_complete_automatic_analysis` reuses existing causal analysis or calls `analyze_causal_rca(persist=True)`, attaches summary fields to the incident, and returns completed, completed-no-hypothesis, pending-topology, pending-entity or failed state.

`reconcile_pending_incidents_for_checkpoint` is bounded/idempotent and refuses arbitrary future/latest snapshots. This path is proven by the repository's integration-style checkpoint-to-briefing test. No preserved external live-cluster artifact in the repository establishes provider conformance, so the golden claim is limited to the in-repo pipeline.

## 12. Causal RCA implementation

`backend/app/services/causal_rca.py` algorithm `13c-causal-v1`:

1. Load canonical incident and incident change candidates (default RCA window 180 minutes before, 10 after, max source query 2,000 through repository path).
2. Choose pinned historical snapshot or checkpoint at/before the incident.
3. Build entity adjacency and shortest paths up to request max four topology hops.
4. Build a change-event lineage graph; event pairs over 180 minutes apart do not link. Add lineage contributions: same commit 0.45, shared entity 0.35, release 0.25, repository 0.20, pipeline 0.15, cluster 0.10, namespace 0.10, delivery/observed continuity 0.10, ≤15-minute proximity 0.10 or ≤60-minute proximity 0.05; cap 0.98 and discard lineage edges below 0.35.
5. Score each candidate and rank/deduplicate hypotheses; return at most five by default and persist the complete response.

13A candidate score:

- Pre-incident time: `40 * exp(-minutes/60)`; post-incident: at most `5 - abs(minutes)`.
- Exact affected entity: 35; topology neighbor: 20.
- Environment, cluster and namespace match: 4 each.
- Risk: `risk_score * 0.09`.
- Total capped at 100.

13C final score:

- 40% of prior candidate score.
- Topology component ×25: distance 0=1.00, 1=.85, 2=.65, 3=.45, farther=.25, no path=0.
- Temporal component ×15: pre-incident `exp(-minutes/90)`; post-incident `.05*exp(-abs(minutes)/30)`.
- Change-kind prior ×10: deployment 1.00, infrastructure .95, configuration/security/database .85, scaling .70, topology .65, pipeline .55, code .50, pull request .35, unknown .30.
- Strongest incoming lineage component ×10.
- Cap 0–100; confidence is score/100; high ≥.75, medium ≥.50, otherwise low.

These constants are source-authored heuristics. Tests verify event-chain and shortest-path mechanics plus larger briefing/lifecycle regressions, but no empirical calibration/evaluation dataset exists.

### CONFIDENCE SEMANTICS

Current causal `confidence` is a normalized deterministic weighted ranking score. It is **not** a probability that the hypothesis is true. Edge confidence is also source/rule confidence rather than calibrated reliability. Precise UI percentages are useful ranking presentation but are not statistically defensible as probabilities. Product language should say “causal evidence score/confidence” and retain cautious conditional remediation wording.

Alternative hypotheses are retained and ranked. When none meets supported evidence, the analysis persists with no top hypothesis; the lifecycle and frontend can present “Topo has not identified a supported root cause yet.”

## 13. Evidence model

Evidence is hybrid:

- `topology.Evidence` stores source, summary, time, related entity/relationship IDs and raw payload.
- Legacy `IncidentEvidence` explicitly distinguishes supporting versus counter evidence and carries signed weight.
- 13C `CausalEvidenceItem`, evidence nodes/edges and causal-chain steps attach source IDs, entity/link/relationship references, timestamps, weights/confidence and reasons.
- Change entity links and signal IDs are durable evidence references.
- Outcomes retain responder source/evidence and action observations.

Today's 13C is a weighted score plus an evidence graph, not a complete claim ledger. Supporting references are strong where exact IDs exist. Contradiction is more explicit in legacy incident/outcome/history models than in the core 13C evidence-item contract. Missing evidence is expressed through warnings/reasons/no hypothesis rather than a first-class expected-evidence record. Relationship provenance is inconsistently linked to raw evidence. These gaps are inputs to a future Truth Contract, not changes made by this audit.

## 14. Blast radius

`calculate_blast_radius` loads the canonical incident and its pinned snapshot, starts at `affected_entity_id`, performs undirected BFS over all relationships to maximum depth five, deduplicates visited entities and then constructs shortest dependency paths. It applies distance impact values 1.0/.85/.65/.45/.25 and risk labels/scores. It does not filter by relationship type, direction, confidence, staleness or evidence.

Precision safeguards are limited to pinned historical snapshot, depth and visited-node dedupe. There is no entity-count cap in the service response. Business impact reuses this exact result; it does not run a second graph. Tests indirectly exercise blast radius through 14A/15A, but there is no focused `test_blast_radius.py`.

Known bug: the service builds an entity map from `graph.entities` before its explicit `graph is None` check. A missing persisted snapshot can raise unexpectedly. This audit does not fix it.

## 15. Ownership and business impact

`OwnershipMappingRecord` supports exact entity, stable service, scoped kind/name and cluster/namespace/environment selectors. Mapping precedence and confidence:

1. exact entity: 1.00;
2. service: .90 plus .02 for each scope dimension, capped .99;
3. kind/name selector: .85;
4. entity label/property fallback: .75;
5. unresolved: false/0, no invented owner.

The model preserves owner team/email, on-call, repository, business capability and tier 1–4 criticality. `calculate_incident_ownership_impact` resolves every blast entity, aggregates deduplicated teams/capabilities/on-call/repositories, selects highest criticality, computes critical/high/medium/low/none business impact and produces routing/warnings. `incident_context.py` separately resolves the causal root entity against the causal analysis's pinned snapshot, then combines root ownership and overall impact.

Historical limitation is confirmed: `ownership_mappings` has active/current timestamps but no validity interval or mapping revision pin. Reanalysis can show current stored ownership for a historical graph.

## 16. Response and remediation intelligence

14B `response_plan.py` derives, deduplicates and ranks investigation and mitigation actions from current 13C evidence, root/target change events, pinned topology and operational context. A deployment/configuration rollback requires strong current evidence (the plan treats .75 as strong), a compatible durable event, incident ordering, target entity and evidence IDs. Risk, target, why, supporting evidence, human approval flag, runbooks and deterministic validation checks are returned. Missing/weak evidence yields investigation-first guidance.

14E `response_intelligence.py` starts with the 14B action list; history cannot introduce an absent action or make rollback eligible. It matches deterministic action families, weights history by RCA verdict (confirmed 1.0, partially confirmed .75, inconclusive .25, not confirmed 0), records positive/negative support and conflicts, and applies `min(observed_count/3, 1)` small-sample scaling. Strong support requires at least three observations and score ≥.70; supported requires at least two and score ≥.35. One success remains limited. Historical timing is descriptive, not predictive.

## 17. Outcomes and history

14C persists one idempotent `IncidentOutcome` per incident, merging bounded responder updates and deriving timing, RCA verdict, resolution action and effectiveness. It imports durable legacy recommendation/recovery evidence when present. Action attribution is conservative: simultaneous plausible actions can keep the result inconclusive. Resolution/mitigation durations never go negative.

14D similarity uses only pre-resolution incident features and queries at most 500 completed outcome candidates. Weights are:

| Factor | Weight |
|---|---:|
| root service | .24 |
| causal change kind | .18 |
| affected entities | .14 |
| topology neighborhood | .14 |
| root entity kind | .08 |
| causal source | .06 |
| business capability | .06 |
| environment | .04 |
| owner team | .03 |
| severity | .03 |

Missing factors contribute zero and the score is deliberately not renormalized, preventing weak common fields from inflating similarity. Outcomes do not affect similarity, which prevents resolution leakage. Pattern threshold is .60; high-quality similarity is .72. The API defaults to minimum .25 and five results, bounded to 20.

## 18. LLM/OpenAI audit

Central provider boundary: `backend/app/services/llm_client.py` uses the OpenAI Responses API, defaults to `gpt-5-mini` through `TOPO_OPENAI_MODEL`, sets `store=false`, sanitizes secret-shaped keys, uses a 60-second timeout and two retries. Callers include incident briefing, incident similarity, response intelligence and execution readiness. Inputs are already-determined structured evidence; output is annotation prose/status and cannot mutate deterministic facts. Tests mock all calls and cover disabled/no-key/provider-error behavior.

Legacy direct provider paths: incident copilot, incident explanation, investigation planner and post-incident report instantiate Groq and call Chat Completions directly, with legacy model default `openai/gpt-oss-120b` through `TOPO_AI_LLM_MODEL`. They may generate their own bounded structured/human-facing artifacts, but are not sources of truth for the unified structured briefing. This is active provider duplication.

No model determines checkpointing, incident qualification/correlation, affected entity, causal score, owner, blast radius, current response eligibility or outcome.

## 19. Dormant 14F/14G/14H control plane

14F has one readiness API and no persistence table of its own. 14G has six approval routes plus `action_approvals` and append-preserving `action_approval_events`. 14H has four public intent routes plus `execution_intents` and `execution_intent_events`. CLI subcommands expose all three future systems.

They are isolated from the 15A briefing and main cockpit by implementation and tests. Approval/readiness information may exist but is not required for incident creation, causal analysis or briefing. The transaction service has an internal claim lease primitive, but no public claim endpoint, no worker process and no executor. Repository search found no Kubernetes, Terraform, cloud or CI mutation implementation. The only rollback commands are read-only guidance strings.

## 20. Frontend reality

There are 14 page routes including landing and 13 `/app` routes. [frontend-api-consumption.json](frontend-api-consumption.json) maps each to components and contracts.

- `/app` defaults to live canonical incident records and links to one cockpit.
- `/app/incidents/{id}` primarily calls exactly one unified briefing plus lifecycle status while pending. It does not independently recalculate RCA, ownership, history, response or outcome.
- `/app?mode=advanced` uses legacy signal-centric incident analysis and remains an expert compatibility surface.
- Topology, live cluster, signals, identities, dependencies, change impact, code-to-runtime and outbound integrations use live APIs.
- The code-to-runtime page reconstructs display paths in `frontend/lib/code-runtime.ts`; it should not overstate provenance/confidence.
- Ask Topo and browser CLI are static demos.
- Global sidebar incident context comes from `frontend/lib/topo-data.ts`, not a live API.

Business and technical cockpit modes are two presentations of the same briefing and URL, not separate reasoning systems. Frontend tests cover cockpit hierarchy, pending/error states, pinned topology, read-only boundary and no 14F/G/H calls.

Browser authentication is missing: `topo-api.ts` sends no bearer token or session credential. The operational UI works with backend auth disabled; no in-repo secure production flow exists.

## 21. CLI audit

Root commands: version, health, login/logout, whoami and doctor. Groups:

- **V1 user-facing:** incidents (list/get/briefing/blast radius/context/response/outcome/history/response intelligence/change events), causal RCA, changes/change events.
- **Engineering/admin:** snapshots, agents, clouds, identities indirectly through API only, change sources, profiles, blast-radius alias.
- **Advanced/legacy:** explanations, copilot, investigations, reports, legacy recommendation/recovery behavior through incidents and APIs.
- **Future/dormant:** execution readiness, nested approvals and execution intents.

The HTTP client URL-encodes identifiers, supports JSON preservation, maps auth/errors and retries temporary failures. Tests are concentrated on Blocks 14A–15A and 14F–14H rather than every older/admin command. The browser CLI screen is not this CLI.

## 22. Security paths

- API tokens are compared by SHA-256 hash using constant-time comparison; registry metadata supplies subject/display/roles.
- Agent enrollment tokens and agent tokens are hashed in persistence; runtime endpoints bind to an active agent and validate submission scope.
- Approval/execution mutations enforce authenticated admin/operator principals and separation-of-duty policy.
- CORS allows localhost ports 3000/5173 and one Vercel origin, credentials, all methods and all headers.
- Backend `.env` is ignored and untracked. Only key names were inspected; the local file contains `TOPO_GITHUB_OWNER`, `TOPO_GITHUB_REPO`, and `TOPO_GITHUB_TOKEN`. No value is reported. `backend/.env.example` is tracked.
- Change-source secrets are references resolved from environment variables; inbound signatures are verified.
- CLI tokens use environment/keyring and are not written into normal profile config (`cli/tests/test_config.py`).
- Outbound webhook secrets/headers are application-persisted and lack a vault/KMS boundary.
- The frontend has no auth credential/session flow.

No credential value was printed or copied into audit artifacts. The scan excluded binary `dist`, `.venv`, `node_modules`, ignored local env values and generated build output.

## 23. Dead, duplicated and dormant code

The detailed proof is [duplication-dead-dormant.md](duplication-dead-dormant.md).

- DUPLICATED: incident analysis generations, remediation/recovery generations, LLM provider paths, snapshot repository interfaces.
- DORMANT: 14F readiness, 14G approval, 14H execution transactions.
- STUBBED: Ask Topo frontend, browser CLI simulator and demo sidebar incident context.
- DEAD: no complete source file proven dead; only commented legacy snapshot repository and health-handler blocks are inert.

## 24. Test evidence map

| Capability | Implementation | Unit/component proof | Integration proof | Real/golden proof | Classification |
|---|---|---|---|---|---|
| Topology discovery | agent Kubernetes/cloud plugins | cloud enrichment/cache tests | plugin manager/agent runner fakes | none committed against live provider | PARTIAL |
| Entity identity | collector/ingest/identity resolver | lifecycle UID resolution | checkpoint-to-briefing uses exact Pod | no cross-connector golden identity corpus | PARTIAL |
| Relationship construction | K8s/cloud/runtime/Git graphs | selected cloud relation tests | lifecycle fixtures traverse K8s graph | no complete source-runtime fixture | PARTIAL |
| Snapshot correctness | checkpoint service | digest/debounce tests | automatic/periodic/manual lifecycle tests | no live scale/HA proof | PROVEN |
| Change ingestion | normalizers/repositories | GitHub normalizer, webhook security, link idempotency | topology change checkpoint test | no vendor golden suite | PARTIAL |
| Failure signal | Kubernetes poller/lifecycle | agent contract tests | backend failure-to-incident tests | no stored live K8s artifact | PROVEN internal contract |
| Incident correlation | grouping/repository/lifecycle | repeat/unrelated/stale/resolved tests | full lifecycle suite | no production replay corpus | PROVEN |
| Affected entity | lifecycle resolver | UID/name/pending tests | real-agent-shaped pipeline fixture | no provider golden corpus | PROVEN internally |
| Automatic RCA | lifecycle + causal repository | idempotency/no hypothesis | checkpoint-to-briefing test | no labeled RCA evaluation | PROVEN execution, uncalibrated accuracy |
| Causal ranking | causal RCA | event-chain/shortest path | briefing regressions | no empirical calibration | PROVEN mechanics |
| Blast radius | blast service | indirect 14A/15A assertions | briefing uses same result | no focused/golden accuracy suite | IMPLEMENTED_BUT_UNPROVEN |
| Ownership | resolver/business impact | 14A tests | briefing regression | no historical mapping proof | PROVEN current-state |
| Response/history/outcome | 14B–14E services | focused suites | unified briefing reuse tests | no production response corpus | PROVEN mechanics |
| Briefing | orchestration/API | 30+ focused backend tests | all section reuse/degraded modes | no external environment artifact | PROVEN |
| Frontend cockpit | briefing workspace | 70 Node component/source contract tests across the frontend suite | one briefing fetch/lifecycle behavior | no browser E2E/visual suite | PROVEN component contract |

Mocked/unit proof is not connector production proof. The integration-style 15D test starts at an agent-shaped inventory/checkpoint, not a live Kubernetes API.

## 25. Critical V1 truth path

| Desired hop | Implementation/evidence | Status | Missing proof |
|---|---|---|---|
| source change → normalized change | provider normalizers and topology diff | PARTIAL | full vendor payload matrix |
| normalized change → repository/entity | change entity refs/correlation | PARTIAL | universal identity mapping |
| repository → commit | GitHub graph | IMPLEMENTED_BUT_UNPROVEN | live connector test |
| commit → CI/CD | GitHub Actions head SHA | IMPLEMENTED_BUT_UNPROVEN | non-GitHub pipelines and golden chain |
| CI/CD → image | workflow/image metadata | PARTIAL | registry attestation/digest guarantee |
| image → deployment | workload image ref/digest | PARTIAL | immutable end-to-end identity |
| deployment → ReplicaSet → Pod | owner UIDs | PROVEN | live cluster conformance |
| Pod → failure | supported K8s reasons/signals | PROVEN internal contract | broader failure vocabulary/real corpus |
| failure → incident | deterministic fingerprint/window | PROVEN | workload-level category separation policy evaluation |
| incident → pinned topology | safe boundary/at-before policy | PROVEN | transaction/queue durability under outage |
| incident → causal candidate | bounded change ranking | PROVEN mechanics | unsafe unpinned legacy fallback; labeled precision |
| candidate → ranked hypothesis | 13C weighted graph | PROVEN mechanics | calibration/counter-evidence standard |
| incident → blast radius | undirected depth-five BFS | IMPLEMENTED_BUT_UNPROVEN | semantic edge filters and accuracy corpus |
| blast/root → ownership | mapping/metadata resolver | PROVEN current-state | historical mapping versioning |
| RCA/context → response/history | 14B/14D/14E | PROVEN mechanics | production outcome corpus |
| sections → briefing | 15A orchestration | PROVEN | performance/scale evaluation |
| briefing → frontend | unified cockpit | PROVEN component contract | authenticated browser and browser E2E |

This is the recommended skeleton for a future golden evaluation harness. It must preserve raw inputs, entity/edge derivations, snapshot pin, candidate scores, final claims and negative/missing evidence.

## 26. Architecture findings

Ranked findings, affected capabilities, recommended next actions and whether they block Truth Contract/evaluation/V1 are in [architecture-findings.md](architecture-findings.md). The leading items are:

1. CRITICAL: production persistence/schema lifecycle absent.
2. CRITICAL: multi-tenant authorization and browser auth absent.
3. HIGH: inconsistent UID-less entity identity.
4. HIGH: unsafe latest graph for unpinned legacy candidate analysis.
5. HIGH: incomplete edge provenance and confidence calibration.
6. HIGH: ownership mapping lacks historical validity.
7. HIGH: source-to-runtime chain is partial.

The audit recommends targeted formalization/evaluation, not a rewrite.

## 27. Truth Contract inputs

| Contract area | Existing reusable primitives | Conflicts | Missing formal concept |
|---|---|---|---|
| Canonical entity identity | `Entity.id`, `external_id`, source/kind/scope, Kubernetes UID, provider IDs, identity overrides | three UID-less K8s formats; logical versus graph IDs; tag/digest split | versioned ID scheme, aliases, authority and collision policy |
| Relationship provenance | relationship source/time/confidence/evidence IDs/properties; snapshot metadata | empty evidence IDs, default confidence, observed/inferred not explicit | derivation rule ID/version, raw source reference, assertion status |
| Temporal semantics | source event, observation, collection, received, create/update and pinned snapshot times | ISO strings, clock domains, current ownership applied to history | explicit event/system/valid time and skew policy |
| Evidence ledger | topology evidence, signals, change links, causal graph, warnings, outcome evidence | legacy counter evidence versus 13C supporting graph; missing evidence implicit | claim ID, support/counter/missing edges, source authority and immutability |
| Confidence semantics | component scores, evidence weights, levels, raw counts | probability-like names/UI, default edge 1.0, no calibration | score taxonomy, calibration status, uncertainty/coverage and display policy |

Recommended Truth Contract order:

1. Freeze canonical entity ID version and alias rules, starting with Kubernetes and container images.
2. Define edge assertion/provenance/observed-versus-inferred contract.
3. Define event time, observation time, system time and snapshot validity selection.
4. Define a claim/evidence ledger with support, contradiction and explicit missing evidence.
5. Rename/formalize confidence as heuristic evidence/ranking score until calibrated.
6. Build one narrow Kubernetes + GitHub Actions + registry golden environment before broadening connectors.

## 28. Production-readiness gap

The complete ranked report is [production-readiness-gaps.md](production-readiness-gaps.md). In addition to the blockers above:

- indexes exist on many query fields, but no migration/explain/load evidence establishes production suitability;
- no retention, backup/restore, HA, upgrade/rollback, customer data deletion or disaster-recovery contract exists;
- health is static and dependency-blind;
- lifecycle analysis has no durable background queue/backpressure/retry job;
- CORS is static and broad in methods/headers;
- optional LLM paths are not fully centralized;
- backend/frontend production deployment artifacts are absent;
- package versions are inconsistent;
- connector tests do not establish live provider behavior.

## Baseline validation

Validation ran against the unchanged product baseline on 2026-08-23:

- Backend `python -m compileall app`: passed.
- Backend `python -m pytest`: **264 passed**, one Starlette `httpx` deprecation warning, 26.04s.
- Agent `python -m compileall src`: passed.
- Agent `python -m pytest`: **13 passed**, 2.11s.
- Frontend `npm run typecheck`: passed.
- Frontend `npm test`: **70 passed**, 0 failed.
- Frontend `npm run lint`: exit 0 with **11 warnings**, 0 errors. Warnings are missing React hook dependencies and unused symbols in existing product files; this audit did not change them.
- Frontend `npm run build`: passed; Next.js 16.2.6 compiled and generated 14 pages/routes without a font/network failure.
- CLI `python -m compileall src`: passed.
- CLI `python -m pytest`: **58 passed**, 0.76s.

No product file was changed to make validation pass.

## Final factual baseline

TopoAI's repository supports the narrow statement that it is an evidence-oriented, read-only incident-intelligence MVP with deterministic topology checkpoints, incident lifecycle, causal ranking, ownership/business impact, response/history/outcome composition and a unified cockpit. Its causal and impact scores are heuristics; its external connector maturity is uneven; its source-to-runtime linkage is partial; and its platform is not production-ready for secure multi-tenant customers. The correct next work is Truth Contract formalization plus a narrow golden evaluation environment—not feature expansion or 15E.
