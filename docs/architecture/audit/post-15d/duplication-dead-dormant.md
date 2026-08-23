# Duplication, dead-code and dormant-system audit

Audit date: 2026-08-23

Scope: repository state on `audit/post-15d-repository-reality`

The audit uses the maturity labels defined in [architecture-audit.md](architecture-audit.md). A duplicate is not automatically dead: several older systems are still reachable through APIs, the CLI, or the Advanced Analysis frontend.

## Confirmed duplicated concepts

### Incident analysis and incident identity — DUPLICATED

There are three related durable concepts:

1. `IncidentAnalysis` / `incident_analyses`, keyed by `analysis_id`, is the earlier signal-centric analysis. It is created by `POST /api/v1/incidents/analyze` through `backend/app/api/incidents.py`, `backend/app/services/incident_analysis.py`, and `backend/app/repositories/incident_repository.py`.
2. `IncidentRecord` / `incidents`, keyed by `incident_id`, is the canonical operational lifecycle record used by 15D, 14A–14E and 15A. Its owners are `backend/app/services/incident_lifecycle.py` and `backend/app/repositories/incident_record_repository.py`.
3. `CausalAnalysisResponse` / `causal_analyses`, keyed by `analysis_id` and incident ID, is Block 13C's durable causal contract, owned by `backend/app/services/causal_rca.py` and `backend/app/repositories/causal_analysis_repository.py`.

The older analysis is still active: `frontend/components/app/live-incident-workspace.tsx` uses it when `/app` is opened in Advanced mode, and the recommendation/orchestration APIs consume it. It therefore is not dead. The primary V1 truth path is `IncidentRecord → CausalAnalysis → IncidentBriefing`; consumers must not treat `GET /api/v1/incidents/{analysis_id}` as the canonical incident-detail endpoint.

### Snapshot repositories — DUPLICATED

`backend/app/repositories/snapshot_repository.py` implements save/list/get/load for `SnapshotRecord`. `backend/app/repositories/topology_snapshot_repository.py` contains an older commented implementation plus the active `load_topology_snapshot` wrapper against the same table. Both repository names are imported by active services. There is one table and one payload contract, not two stores, but two loaders/naming conventions increase the chance of inconsistent selection policy.

### Remediation and recovery models — DUPLICATED

The earlier path consists of `backend/app/services/recommendation_engine.py`, the `remediation_recommendations` table, recommendation APIs, and recovery verification APIs. Blocks 14B/14C use `backend/app/services/response_plan.py` and `backend/app/services/incident_outcome.py`. The 14B response plan is derived rather than persisted, while 14C intentionally imports legacy recommendation/recovery records as one possible outcome-evidence source.

Both paths remain reachable in Advanced Analysis through `frontend/components/app/incident-recommendations.tsx` and `frontend/components/app/incident-recovery-verification.tsx`. They are active compatibility surfaces, not dead, but product documentation must distinguish legacy recommendation IDs from 14B response action IDs.

### AI provider paths — DUPLICATED

`backend/app/services/llm_client.py` is the centralized optional OpenAI Responses API client used by the unified briefing, incident similarity, response intelligence, and execution readiness. It implements redaction, `store=false`, bounded retry/timeout and deterministic no-provider fallback.

Four active services also instantiate Groq directly:

- `backend/app/services/incident_copilot.py`
- `backend/app/services/incident_explanation.py`
- `backend/app/services/investigation_planner.py`
- `backend/app/services/post_incident_report.py`

Those direct calls bypass the central provider boundary. This is architectural duplication and complicates provider governance, redaction assurance, observability and model configuration.

### Incident explanation surfaces — DUPLICATED

The unified `IncidentBriefing.ai_summary` is an optional annotation over deterministic structured evidence. Separately, the incident-explanation, copilot, investigation-plan and post-incident-report services each produce their own human-facing representations and persist some of them. They serve different workflows, but overlap in summary, evidence and recommended-next-step language. V1 should identify the briefing as primary and label the others advanced/supporting.

### Cloud inventory representations — PARTIAL duplication

Cloud inventories are persisted as normalized `cloud_accounts` and `cloud_resources`, while agent snapshot ingestion also turns inventory into topology `Entity` objects inside `topology_snapshots`. This is intentional source-record versus graph-projection separation, but IDs differ: provider resource IDs live in cloud records/properties while graph entity IDs are hashes. There is no database-level link table or universal canonical cloud entity ID.

## Dormant future systems

### 14F execution readiness — DORMANT

`backend/app/services/execution_readiness.py`, its API, models, CLI command and tests exist. The system computes a read-only posture and never executes an action. `backend/tests/test_incident_briefing.py` and the frontend cockpit tests assert that the V1 briefing does not depend on or expose it.

### 14G approval control plane — DORMANT

`action_approvals` and `action_approval_events` plus `backend/app/services/action_approval.py`, authenticated APIs and CLI commands implement immutable evidence snapshots and approval audit history. This is intentionally outside the V1 customer path.

### 14H execution transactions — DORMANT

`execution_intents` and `execution_intent_events` plus `backend/app/services/execution_transaction.py` implement intent creation, idempotency, internal claim leases and audit state. There is no public claim or execute API, no worker process, no Kubernetes/Terraform/cloud mutator and no execution button in the cockpit. This is a future transaction foundation, not autonomous remediation.

## Stubbed frontend surfaces

- `frontend/components/app/ask-view.tsx` is a static demonstration and does not call the live copilot or briefing API.
- `frontend/components/app/cli-view.tsx` is a browser-only simulator and is unrelated to the real Python `topo` CLI.
- `frontend/components/app/app-sidebar.tsx` imports a hard-coded incident from `frontend/lib/topo-data.ts`, so the sidebar's global incident context is demo data even when other routes are live.
- `frontend/lib/topo-data.ts` is a fixture/demo data source with incident, hypotheses, graph, signal, commit and identity examples. It must not be cited as observed production truth.

## Dead code

No entire source file was classified `DEAD` with high confidence. All backend service/repository/API modules had a static reference from source, tests, or a registered route, and every frontend operational page had a route import. Two narrower dead artifacts are present:

- The commented-out earlier repository implementation at the top of `backend/app/repositories/topology_snapshot_repository.py` is inert and duplicates the active repository.
- The commented-out earlier `/health` handler in `backend/app/main.py` is inert; the active handler appears below it.

Static reachability is not runtime proof. A future coverage-based removal audit should capture production feature usage before deleting any legacy path.

## Contract collisions that are not code duplication

- `incident_id` and `analysis_id` are different identifiers even though older incident routes use an `analysis_id` path segment under `/incidents`.
- Logical identity IDs from `identity_resolutions` group entities; they do not replace topology `Entity.id`.
- `ChangeRecord` represents a normalized snapshot difference; `ChangeEventRecord` represents a durable external/native/topology-promoted event.
- A failure `SignalRecord` is an observation; an `IncidentRecord` is a correlated operational problem.
- `SnapshotRecord.payload_json` is historical graph truth; cloud/runtime tables are source-oriented inventory/telemetry records and are not substitutes for the pinned incident snapshot.

## Recommended disposition

1. Declare `IncidentRecord`, `CausalAnalysisResponse` and `IncidentBriefing` as the V1 canonical contracts.
2. Keep Advanced Analysis and legacy recommendation/recovery APIs for compatibility, but label them explicitly and stop adding new primary-product dependencies to them.
3. Consolidate snapshot loading/selection behind one repository policy in a future implementation block.
4. Route every optional model call through `llm_client.py` in a future hardening block.
5. Keep 14F/14G/14H compiled and tested but out of V1 navigation and briefing dependencies.
6. Separate static demo routes visually and in documentation from live operational surfaces.
