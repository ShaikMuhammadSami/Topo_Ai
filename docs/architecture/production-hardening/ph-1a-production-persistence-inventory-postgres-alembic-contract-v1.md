# PH-1A — Production Persistence Inventory & Postgres/Alembic Migration Contract v1

- Status: **ARCHITECTURE / INVENTORY CANDIDATE**
- Repository: `C:\Topo-ai`
- Branch inspected: `architecture/ph-1a-production-persistence-inventory-v1`
- Accepted commit: `db8761e0a5bc3c7d13338c6d0a4d02a8bc9f0d8d` (`db8761e docs(architecture): freeze v1 production hardening transition (#60)`)
Scope: forensic inventory and migration contract only; no product, evaluator, migration, dependency, database, Postgres, or cloud changes.

## 1. Executive finding

TopoAI has one synchronous SQLAlchemy 2.0 persistence surface and one accepted ORM metadata set: **38 tables, 687 columns, 38 single-column string primary keys, 0 declared foreign keys, 0 check constraints, 10 named multi-column `UniqueConstraint`s, 9 column-level unique indexes, and 296 ORM index objects created from `index=True`**. All ORM declarations are in `backend/app/db/models.py`; `backend/app/db/database.py` owns `Base`, engine construction, `SessionLocal`, request sessions, and `create_all()` initialization.

The schema is intentionally denormalized. Complete topology graphs, causal hypotheses and the TC-4 evidence ledger, analysis outputs, reports, source payloads, and configuration fragments are persisted as serialized JSON in **59 `TEXT` columns**. There are no SQLAlchemy `JSON`, `DateTime`, native `Enum`, `Numeric`, autoincrement, ORM relationship, cascade, or server-default declarations. All **134 timestamp-shaped columns are `VARCHAR(50)` ISO strings**. Domain references are application-level strings or JSON arrays; the reproducible non-PK `_id`/reference-array scan finds **95 logical reference-shaped fields**.

The frozen LINEAGE evaluation seed is an exact schema match for current ORM intent. The local developer database is not: it has three empty legacy DB-only tables, lacks two current `change_source_dead_letters` columns, and lacks two current delivery indexes. This is expected unmanaged developer drift, not corruption. It proves that `Base.metadata.create_all()` creates missing tables but is not schema evolution.

No product runtime raw SQLite SQL or SQLite JSON function is present. Direct `sqlite3`, `PRAGMA`, `rowid`, and positional-placeholder SQL is confined to the evaluation harness/tests. The product query surface is SQLAlchemy ORM/Core and is broadly portable. The material Postgres risks are transaction ownership, check-then-insert races currently softened by SQLite writer serialization, text timestamp semantics, locale/collation differences, long indexed identifiers, plaintext webhook secrets, and the absence of production schema authority—not a need to rewrite TopoAI domain semantics.

**PH-1A verdict: GO.** PH-1B should implement one canonical Alembic revision 0001 that creates exactly this accepted 38-table schema from an empty database, plus verified adoption for pre-existing databases. It must never stamp an unknown schema. No automatic arbitrary SQLite-to-Postgres data mover is required for V1.

## 2. Governing answer and evidence boundary

The persistent reality today is:

1. **ORM intent** — `Base.metadata` in `backend/app/db/models.py`; it describes the accepted 38-table schema.
2. **Actual default SQLite** — `backend/data/topo.db`; it is an unmanaged local development database with known drift.
3. **Application-enforced semantics** — repositories and services resolve logical references, generate IDs, serialize payloads, preserve pinned topology, and own most commits. The database does not enforce those references.
4. **Evaluation-seed dependency** — `evaluation/results/lineage/post-sc4/topo-product-32695735269.db` is a frozen SQLite artifact copied byte-for-byte into isolated scenarios and then mutated only in the scenario copy.

The merged PH-0 document, `docs/architecture/v1-evidence-boundary-production-hardening-transition-v1.md`, was read completely. It freezes the V1 evidence boundary and makes production persistence hardening the next workstream while preserving LINEAGE, TC, blast-radius, AR, and EAI behavior.

### Audit method

- Parsed live SQLAlchemy metadata without writing a helper file.
- Created only a transient in-memory SQLite schema to prove what current metadata produces.
- Opened both on-disk SQLite databases using URI `mode=ro&immutable=1` and `PRAGMA query_only=ON`.
- Ran `PRAGMA quick_check`, `PRAGMA integrity_check`, schema/column/index/constraint introspection, and read-only row counts.
- Searched `backend/app`, `backend/tests`, `evaluation`, `agent`, `cli`, and relevant configuration/documentation for engine/session/schema creation, raw SQL, time, JSON, transaction, query, and SQLite assumptions.
- Did not run product/evaluator regression suites because PH-1A is documentation-only.

## 3. Current persistence architecture

```text
FastAPI lifespan
  -> app.db.database.init_db()
  -> import app.db.models
  -> Base.metadata.create_all(engine)

API request
  -> Depends(get_session)
  -> one synchronous SessionLocal session
  -> service/repository calls
  -> repository/service/API-owned commit(s)
  -> session closes at request end

TOPO_DATABASE_URL absent
  -> sqlite:///C:/Topo-ai/backend/data/topo.db

TOPO_DATABASE_URL set
  -> passed directly to SQLAlchemy create_engine()
  -> check_same_thread=False only when URL starts with "sqlite"
```

`backend/app/db/database.py` always creates `backend/data` at import time, even for a non-SQLite URL. The installed audit environment uses SQLAlchemy `2.0.51`; `backend/requirements.txt` specifies `SQLAlchemy>=2.0,<3.0`. No Alembic or Postgres driver dependency/configuration exists.

Engine/session details:

- synchronous `create_engine(DATABASE_URL, connect_args=...)`;
- no `pool_pre_ping`, explicit pool class/size, transaction isolation, or `future=True` override;
- `SessionLocal(autoflush=False, autocommit=False, expire_on_commit=False)`;
- request dependency yields a session but does not centrally commit;
- closing an exceptional request discards uncommitted work, while already committed repository steps remain committed.

The agent and CLI do not create the product schema. They use HTTP and their own filesystem buffers/caches. Evaluation starts isolated backend processes with a temporary SQLite URL and relies on backend startup `create_all()` for an empty schema.

## 4. ORM table inventory

All 38 ORM classes below are declared in `backend/app/db/models.py`. `backend/app/db/database.py` declares `Base`. No other ORM table source was found.

| Table | ORM class | Persistence role | Historical/mutation contract | PH-3 tenancy preparation |
|---|---|---|---|---|
| `action_approval_events` | `ActionApprovalEventRecord` | approval audit ledger | append-preserving; service-convention immutable | tenant-derived from approval/incident |
| `action_approvals` | `ActionApprovalRecord` | approval lifecycle snapshot | mutable current state plus frozen readiness evidence | tenant-derived from incident |
| `agent_enrollment_tokens` | `AgentEnrollmentTokenRecord` | enrollment credential lifecycle | mutable current/security audit | unknown: tenant bootstrap policy required |
| `build_artifact_evidence` | `BuildArtifactEvidenceRecord` | provider-authentic run/image evidence | immutable historical fact by service convention | unknown until repository identity ownership is fixed |
| `causal_analyses` | `CausalAnalysisRecord` | 13C analysis plus TC-4 ledger | immutable generation; same ID returns original payload | tenant-derived from incident |
| `change_entity_links` | `ChangeEntityLinkRecord` | change-to-graph correlation | append-preserving/idempotent derived link | tenant-derived from change/snapshot |
| `change_events` | `ChangeEventRecord` | durable native/provider change event | append-preserving identity; enriched on redelivery | tenant-owned ingestion fact |
| `change_source_dead_letters` | `ChangeSourceDeadLetterRecord` | replay queue/audit | mutable lifecycle, payload preserved | tenant-derived from source/delivery |
| `change_source_deliveries` | `ChangeSourceDeliveryRecord` | inbound delivery idempotency/audit | append-preserving receipt, mutable processing status | tenant-derived from source |
| `change_sources` | `ChangeSourceRecord` | connector configuration/status | mutable current configuration | tenant-owned |
| `changes` | `ChangeRecord` | normalized snapshot difference | derived durable, same ID may refresh presentation fields | tenant-derived from snapshots |
| `cloud_accounts` | `CloudAccountRecord` | cloud inventory account state | mutable current/recomputable | tenant-owned |
| `cloud_resources` | `CloudResourceRecord` | provider inventory resource state | mutable current/recomputable | tenant-derived from cloud account |
| `execution_intent_events` | `ExecutionIntentEventRecord` | execution transaction audit ledger | append-preserving; service-convention immutable | tenant-derived from execution/incident |
| `execution_intents` | `ExecutionIntentRecord` | dormant future execution state | mutable state machine with row version | tenant-derived from incident |
| `identity_overrides` | `IdentityOverrideRecord` | manual canonicalization rule | mutable current; soft deactivation | tenant-owned |
| `identity_resolutions` | `IdentityResolutionRecord` | materialized per-snapshot identity result | generation-keyed cache/recomputable; updatable | tenant-derived from snapshot |
| `incident_analyses` | `IncidentAnalysisRecord` | legacy signal-centric analysis | derived durable generation; same ID updatable | tenant-derived from signal/snapshot |
| `incident_copilot_messages` | `CopilotMessageRecord` | conversation evidence | append-preserving message history | tenant-derived from incident/session |
| `incident_copilot_sessions` | `CopilotSessionRecord` | conversation header/state | mutable current session | tenant-derived from incident |
| `incident_explanations` | `IncidentExplanationRecord` | grounded explanation | derived durable generation/cache | tenant-derived from incident |
| `incident_investigation_plans` | `InvestigationPlanRecord` | grounded plan generation | generation-based, mutable plan status | tenant-derived from incident |
| `incident_investigation_steps` | `InvestigationStepRecord` | plan step progress | mutable response workflow | tenant-derived from plan/incident |
| `incident_outcomes` | `IncidentOutcomeRecord` | 14C final/current outcome | durable but mutable as incident progresses | tenant-derived from incident |
| `incidents` | `IncidentRecord` | canonical correlated incident | mutable lifecycle; preserves first observation and topology pin | tenant-owned operational root |
| `ownership_mappings` | `OwnershipMappingRecord` | ownership catalog selector | mutable current/soft active flag | tenant-owned |
| `post_incident_report_actions` | `ReportActionItemRecord` | report follow-up item | mutable current child state | tenant-derived from report/incident |
| `post_incident_reports` | `PostIncidentReportRecord` | versioned grounded report | generation/version based, review state mutable | tenant-derived from incident |
| `recovery_verifications` | `RecoveryVerificationRecord` | legacy recovery comparison | derived durable generation | tenant-derived from recommendation/analysis |
| `remediation_recommendations` | `RecommendationRecord` | legacy recommendation record | derived durable guidance, status mutable | tenant-derived from analysis/signal |
| `runtime_dependencies` | `RuntimeDependencyRecord` | coalesced observed connection fact | mutable current/recomputable counters and window | tenant-derived from agent/sensor |
| `runtime_processes` | `RuntimeProcessRecord` | coalesced observed process fact | mutable current/recomputable counters and window | tenant-derived from agent/sensor |
| `runtime_sensors` | `RuntimeSensorRecord` | sensor registration/health | mutable current | tenant-derived from agent |
| `signals` | `SignalRecord` | normalized operational observation | append-preserving identity; occurrence/time state mutates | tenant-owned ingestion fact |
| `topo_agents` | `TopoAgentRecord` | agent identity/config/health | mutable current/security lifecycle | tenant-owned |
| `topology_snapshots` | `SnapshotRecord` | serialized immutable graph checkpoint | immutable historical record by service convention | tenant-owned historical root |
| `webhook_deliveries` | `WebhookDeliveryRecord` | outbound delivery audit | append-preserving identity; attempts/status mutate | tenant-derived from endpoint/resource |
| `webhook_endpoints` | `WebhookEndpointRecord` | outbound webhook config | mutable current configuration | tenant-owned |

No separately persisted table exists for topology entities, topology relationships, graph evidence, causal hypotheses, TC-4 ledger entries, business impact, blast radius, response plans, response intelligence, incident memory/similarity, historical response intelligence, or 14F execution readiness. Those are embedded in durable payloads and/or recomputed from the tables above. This distinction must survive migration.

### Deterministic complete column inventory

Notation: `PK` primary key; `NN` non-null; `NULL` nullable; `IDX` ORM `index=True`; `UNIQUE` column-level unique index; `PY=` Python-side default. There are **no server defaults**. Named multi-column uniqueness is listed in §5.

#### `action_approval_events` — `ActionApprovalEventRecord`

`event_id VARCHAR(255) PK NN; sequence INTEGER NN; approval_id VARCHAR(255) NN IDX; incident_id VARCHAR(1000) NN IDX; action_id VARCHAR(1000) NN IDX; event_type VARCHAR(30) NN IDX; from_status VARCHAR(30) NULL; to_status VARCHAR(30) NN IDX; actor_subject VARCHAR(500) NN IDX; actor_display_name VARCHAR(500) NN; actor_roles_json TEXT NN PY='[]'; authentication_type VARCHAR(100) NN; reason TEXT NULL; evidence_fingerprint VARCHAR(64) NN IDX; occurred_at VARCHAR(50) NN IDX`

#### `action_approvals` — `ActionApprovalRecord`

`approval_id VARCHAR(255) PK NN; incident_id VARCHAR(1000) NN IDX; action_id VARCHAR(1000) NN IDX; action_family VARCHAR(100) NN IDX; status VARCHAR(30) NN IDX; risk VARCHAR(30) NN; requires_human_approval BOOLEAN NN; policy_version VARCHAR(100) NN IDX; readiness_status_at_request VARCHAR(50) NN; evidence_fingerprint VARCHAR(64) NN IDX; target_entity_ids_json TEXT NN PY='[]'; target_change_event_id VARCHAR(1000) NULL IDX; readiness_snapshot_json TEXT NN; pending_key VARCHAR(64) NULL IDX UNIQUE; request_reason TEXT NULL; requested_by_subject VARCHAR(500) NN IDX; requested_by_display_name VARCHAR(500) NN; requested_by_roles_json TEXT NN PY='[]'; requested_at VARCHAR(50) NN IDX; decided_by_subject VARCHAR(500) NULL IDX; decided_by_display_name VARCHAR(500) NULL; decided_by_roles_json TEXT NN PY='[]'; decided_at VARCHAR(50) NULL IDX; decision_reason TEXT NULL; expires_at VARCHAR(50) NN IDX; revoked_by_subject VARCHAR(500) NULL IDX; revoked_by_display_name VARCHAR(500) NULL; revoked_at VARCHAR(50) NULL IDX; revocation_reason TEXT NULL; invalidated_at VARCHAR(50) NULL IDX; invalidation_reason TEXT NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `agent_enrollment_tokens` — `AgentEnrollmentTokenRecord`

`enrollment_token_id VARCHAR(255) PK NN; token_hash VARCHAR(64) NN IDX UNIQUE; token_hint VARCHAR(32) NN; label VARCHAR(255) NULL; max_uses INTEGER NN PY=1; use_count INTEGER NN PY=0; expires_at VARCHAR(50) NN IDX; last_used_at VARCHAR(50) NULL; revoked_at VARCHAR(50) NULL; created_by VARCHAR(255) NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `build_artifact_evidence` — `BuildArtifactEvidenceRecord`

`evidence_id VARCHAR(255) PK NN; provider VARCHAR(100) NN IDX; repository_id VARCHAR(255) NN IDX; repository VARCHAR(1000) NN IDX; workflow_id VARCHAR(255) NULL IDX; workflow_ref VARCHAR(2000) NULL; workflow_run_id VARCHAR(255) NN IDX; run_attempt INTEGER NN IDX; commit_sha VARCHAR(40) NN IDX; artifact_type VARCHAR(100) NN IDX; image_repository VARCHAR(2000) NN IDX; image_reference VARCHAR(3000) NULL; image_digest VARCHAR(71) NN IDX; immutable_image_ref VARCHAR(3000) NN; provider_evidence_type VARCHAR(150) NN IDX; provider_evidence_id VARCHAR(255) NN IDX; provider_evidence_reference VARCHAR(3000) NN; provider_evidence_digest VARCHAR(71) NN; provider_build_record_digest VARCHAR(71) NN; provider_builder_id VARCHAR(3000) NN; provider_build_started_at VARCHAR(50) NULL; provider_build_finished_at VARCHAR(50) NULL; provider_run_updated_at VARCHAR(50) NN IDX; observed_at VARCHAR(50) NN IDX; temporal_json TEXT NN; completeness VARCHAR(50) NN IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `causal_analyses` — `CausalAnalysisRecord`

`analysis_id VARCHAR(255) PK NN; incident_id VARCHAR(1000) NN IDX; generated_at VARCHAR(50) NN IDX; algorithm_version VARCHAR(100) NN; candidate_count INTEGER NN PY=0; hypothesis_count INTEGER NN PY=0; top_hypothesis_score FLOAT NULL IDX; top_root_event_id VARCHAR(255) NULL IDX; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `change_entity_links` — `ChangeEntityLinkRecord`

`link_id VARCHAR(255) PK NN; event_id VARCHAR(255) NN IDX; entity_id VARCHAR(1000) NN IDX; link_type VARCHAR(50) NN IDX; confidence FLOAT NN PY=0.0; reason TEXT NULL; snapshot_id VARCHAR(255) NULL IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `change_events` — `ChangeEventRecord`

`event_id VARCHAR(255) PK NN; event_fingerprint VARCHAR(128) NN IDX UNIQUE; source VARCHAR(100) NN IDX; kind VARCHAR(100) NN IDX; external_id VARCHAR(1000) NULL IDX; origin_change_id VARCHAR(255) NULL IDX; title VARCHAR(1000) NN; summary TEXT NULL; actor VARCHAR(500) NULL IDX; occurred_at VARCHAR(50) NN IDX; received_at VARCHAR(50) NN IDX PY=utc_now_iso; environment VARCHAR(255) NULL IDX; provider VARCHAR(100) NULL IDX; account_id VARCHAR(255) NULL IDX; region VARCHAR(255) NULL IDX; cluster_name VARCHAR(255) NULL IDX; namespace VARCHAR(255) NULL IDX; repository VARCHAR(1000) NULL IDX; commit_sha VARCHAR(255) NULL IDX; pipeline_name VARCHAR(500) NULL IDX; release_version VARCHAR(255) NULL IDX; terraform_workspace VARCHAR(500) NULL IDX; risk_score INTEGER NN IDX PY=0; risk_level VARCHAR(30) NN IDX PY='low'; status VARCHAR(50) NN IDX PY='observed'; observation_count INTEGER NN PY=1; metadata_json TEXT NN PY='{}'; raw_payload_json TEXT NN PY='{}'; agent_id VARCHAR(255) NULL IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `change_source_dead_letters` — `ChangeSourceDeadLetterRecord`

`dead_letter_id VARCHAR(255) PK NN; source_id VARCHAR(255) NN IDX; delivery_id VARCHAR(255) NN IDX; event_type VARCHAR(255) NULL; reason TEXT NN; payload_json TEXT NN PY='{}'; attempt_count INTEGER NN PY=0; status VARCHAR(50) NN IDX PY='pending'; last_attempt_at VARCHAR(50) NULL; replayed_at VARCHAR(50) NULL; created_at VARCHAR(50) NN PY=utc_now_iso`

#### `change_source_deliveries` — `ChangeSourceDeliveryRecord`

`delivery_id VARCHAR(255) PK NN; source_id VARCHAR(255) NN IDX; delivery_key VARCHAR(128) NN IDX UNIQUE; source_delivery_id VARCHAR(1000) NULL IDX; event_type VARCHAR(255) NULL IDX; status VARCHAR(50) NN IDX PY='received'; payload_sha256 VARCHAR(64) NN IDX; headers_json TEXT NN PY='{}'; payload_json TEXT NN PY='{}'; event_ids_json TEXT NN PY='[]'; error TEXT NULL; received_at VARCHAR(50) NN IDX PY=utc_now_iso; processed_at VARCHAR(50) NULL`

#### `change_sources` — `ChangeSourceRecord`

`source_id VARCHAR(255) PK NN; name VARCHAR(255) NN IDX; source_type VARCHAR(100) NN IDX; enabled BOOLEAN NN IDX PY=True; secret_ref VARCHAR(255) NULL; config_json TEXT NN PY='{}'; filters_json TEXT NN PY='{}'; status VARCHAR(50) NN IDX PY='configured'; delivery_count INTEGER NN PY=0; failure_count INTEGER NN PY=0; last_event_at VARCHAR(50) NULL; last_success_at VARCHAR(50) NULL; last_error_at VARCHAR(50) NULL; last_error TEXT NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `changes` — `ChangeRecord`

`change_id VARCHAR(255) PK NN; fingerprint VARCHAR(100) NN IDX; change_type VARCHAR(50) NN IDX; category VARCHAR(50) NN IDX; importance VARCHAR(30) NN IDX; source_system VARCHAR(100) NN; title VARCHAR(500) NN; summary TEXT NN; detected_at VARCHAR(50) NN IDX; from_snapshot_id VARCHAR(255) NN IDX; to_snapshot_id VARCHAR(255) NN IDX; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; entity_id VARCHAR(500) NULL IDX; entity_kind VARCHAR(100) NULL IDX; entity_name VARCHAR(255) NULL; relationship_id VARCHAR(255) NULL IDX; relationship_type VARCHAR(100) NULL; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `cloud_accounts` — `CloudAccountRecord`

`cloud_account_id VARCHAR(255) PK NN; provider VARCHAR(50) NN IDX; account_number VARCHAR(255) NN IDX; display_name VARCHAR(255) NN; principal_arn VARCHAR(1000) NULL; metadata_json TEXT NN PY='{}'; last_seen_at VARCHAR(50) NN IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `cloud_resources` — `CloudResourceRecord`

`cloud_resource_id VARCHAR(1000) PK NN; provider VARCHAR(50) NN IDX; account_id VARCHAR(255) NN IDX; region VARCHAR(100) NN IDX; resource_type VARCHAR(100) NN IDX; resource_id VARCHAR(1000) NN IDX; arn VARCHAR(2000) NULL IDX; name VARCHAR(1000) NN IDX; status VARCHAR(100) NULL IDX; vpc_id VARCHAR(255) NULL IDX; subnet_ids_json TEXT NN PY='[]'; tags_json TEXT NN PY='{}'; properties_json TEXT NN PY='{}'; observed_at VARCHAR(50) NN IDX; agent_id VARCHAR(255) NN IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `execution_intent_events` — `ExecutionIntentEventRecord`

`event_id VARCHAR(255) PK NN; sequence INTEGER NN; execution_id VARCHAR(255) NN IDX; incident_id VARCHAR(1000) NN IDX; approval_id VARCHAR(255) NN IDX; action_id VARCHAR(1000) NN IDX; event_type VARCHAR(30) NN IDX; from_status VARCHAR(30) NULL; to_status VARCHAR(30) NN IDX; actor_subject VARCHAR(500) NN IDX; actor_display_name VARCHAR(500) NN; actor_roles_json TEXT NN PY='[]'; authentication_type VARCHAR(100) NN; claim_generation INTEGER NN PY=0; reason TEXT NULL; occurred_at VARCHAR(50) NN IDX`

#### `execution_intents` — `ExecutionIntentRecord`

`execution_id VARCHAR(255) PK NN; incident_id VARCHAR(1000) NN IDX; approval_id VARCHAR(255) NN IDX UNIQUE; action_id VARCHAR(1000) NN IDX; action_family VARCHAR(100) NN IDX; status VARCHAR(30) NN IDX; approval_evidence_fingerprint VARCHAR(64) NN IDX; policy_version VARCHAR(100) NN IDX; risk VARCHAR(30) NN; target_entity_ids_json TEXT NN PY='[]'; target_change_event_id VARCHAR(1000) NULL IDX; execution_snapshot_json TEXT NN; idempotency_key VARCHAR(64) NN IDX UNIQUE; created_by_subject VARCHAR(500) NN IDX; created_by_display_name VARCHAR(500) NN; created_by_roles_json TEXT NN PY='[]'; created_by_authentication_type VARCHAR(100) NN; created_at VARCHAR(50) NN IDX; claimed_by_subject VARCHAR(500) NULL IDX; claimed_by_display_name VARCHAR(500) NULL; claimed_by_authentication_type VARCHAR(100) NULL; claimed_at VARCHAR(50) NULL IDX; claim_expires_at VARCHAR(50) NULL IDX; claim_token_hash VARCHAR(64) NULL; claim_generation INTEGER NN PY=0; attempt_count INTEGER NN PY=0; cancelled_by_subject VARCHAR(500) NULL IDX; cancelled_by_display_name VARCHAR(500) NULL; cancelled_at VARCHAR(50) NULL IDX; cancellation_reason TEXT NULL; invalidated_at VARCHAR(50) NULL IDX; invalidation_reason TEXT NULL; expired_at VARCHAR(50) NULL IDX; expiration_reason TEXT NULL; started_at VARCHAR(50) NULL; completed_at VARCHAR(50) NULL; failed_at VARCHAR(50) NULL; last_error_code VARCHAR(255) NULL; last_error_message TEXT NULL; result_reference VARCHAR(1000) NULL; execution_performed BOOLEAN NN PY=False; row_version INTEGER NN PY=1; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `identity_overrides` — `IdentityOverrideRecord`

`override_id VARCHAR(100) PK NN; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NN IDX; entity_kind VARCHAR(100) NN; entity_name VARCHAR(255) NN; action VARCHAR(30) NN; canonical_name VARCHAR(255) NULL; reason TEXT NN; active BOOLEAN NN PY=True; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `identity_resolutions` — `IdentityResolutionRecord`

`snapshot_id VARCHAR(255) PK NN; generated_at VARCHAR(50) NN IDX; identity_count INTEGER NN; unresolved_count INTEGER NN; excluded_count INTEGER NN; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_analyses` — `IncidentAnalysisRecord`

`analysis_id VARCHAR(255) PK NN; signal_id VARCHAR(500) NN IDX; topology_snapshot_id VARCHAR(255) NN IDX; algorithm_version VARCHAR(50) NN; generated_at VARCHAR(50) NN IDX; incident_title VARCHAR(500) NN; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; candidate_count INTEGER NN; hypothesis_count INTEGER NN; top_hypothesis_title VARCHAR(500) NULL; top_hypothesis_score VARCHAR(30) NULL; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_copilot_messages` — `CopilotMessageRecord`

`message_id VARCHAR(255) PK NN; session_id VARCHAR(255) NN IDX; incident_id VARCHAR(500) NN IDX; role VARCHAR(30) NN IDX; content TEXT NN; provider VARCHAR(50) NULL; answer_status VARCHAR(50) NULL; confidence VARCHAR(30) NULL; evidence_ids_json TEXT NN PY='[]'; evidence_json TEXT NN PY='[]'; suggested_questions_json TEXT NN PY='[]'; warning TEXT NULL; created_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_copilot_sessions` — `CopilotSessionRecord`

`session_id VARCHAR(255) PK NN; incident_id VARCHAR(500) NN IDX; title VARCHAR(500) NN; provider VARCHAR(50) NN IDX; model_name VARCHAR(255) NULL; status VARCHAR(30) NN IDX PY='active'; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_explanations` — `IncidentExplanationRecord`

`explanation_id VARCHAR(255) PK NN; incident_id VARCHAR(500) NN IDX; topology_snapshot_id VARCHAR(500) NULL IDX; analysis_id VARCHAR(500) NULL IDX; provider VARCHAR(50) NN IDX; model_name VARCHAR(255) NULL; prompt_version VARCHAR(100) NN; grounding_hash VARCHAR(100) NN IDX; confidence VARCHAR(30) NN; generated_at VARCHAR(50) NN IDX; payload_json TEXT NN; evidence_json TEXT NN; warnings_json TEXT NN PY='[]'; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_investigation_plans` — `InvestigationPlanRecord`

`plan_id VARCHAR(255) PK NN; incident_id VARCHAR(500) NN IDX; title VARCHAR(500) NN; objective TEXT NN; incident_summary TEXT NN; provider VARCHAR(50) NN IDX; model_name VARCHAR(255) NULL; prompt_version VARCHAR(100) NN; grounding_hash VARCHAR(100) NN IDX; status VARCHAR(30) NN IDX PY='active'; overall_confidence VARCHAR(30) NN; evidence_gaps_json TEXT NN PY='[]'; warnings_json TEXT NN PY='[]'; evidence_json TEXT NN PY='[]'; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_investigation_steps` — `InvestigationStepRecord`

`step_id VARCHAR(255) PK NN; plan_id VARCHAR(255) NN IDX; incident_id VARCHAR(500) NN IDX; sequence INTEGER NN; title VARCHAR(500) NN; objective TEXT NN; command_type VARCHAR(50) NN; command TEXT NULL; target VARCHAR(1000) NN; expected_observation TEXT NN; success_criteria TEXT NN; failure_indication TEXT NN; evidence_ids_json TEXT NN PY='[]'; status VARCHAR(30) NN IDX PY='pending'; finding TEXT NULL; responder_notes TEXT NULL; completed_at VARCHAR(50) NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incident_outcomes` — `IncidentOutcomeRecord`

`outcome_id VARCHAR(255) PK NN; incident_id VARCHAR(1000) NN IDX UNIQUE; status VARCHAR(50) NN IDX; causal_analysis_id VARCHAR(255) NULL IDX; response_plan_reference VARCHAR(255) NULL IDX; rca_verdict VARCHAR(50) NN IDX; mitigated_at VARCHAR(50) NULL IDX; resolved_at VARCHAR(50) NULL IDX; source_json TEXT NN PY='{}'; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `incidents` — `IncidentRecord`

`incident_id VARCHAR(255) PK NN; fingerprint VARCHAR(255) NN IDX; status VARCHAR(50) NN IDX; severity VARCHAR(50) NN IDX; title VARCHAR(500) NN; summary TEXT NN; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; primary_signal_id VARCHAR(500) NN IDX; latest_signal_id VARCHAR(500) NULL IDX; topology_snapshot_id VARCHAR(255) NULL IDX; affected_entity_id VARCHAR(500) NULL IDX; affected_object_kind VARCHAR(100) NULL; affected_object_name VARCHAR(255) NULL; first_observed_at VARCHAR(50) NN IDX; last_observed_at VARCHAR(50) NN IDX; latest_analysis_id VARCHAR(255) NULL IDX; top_hypothesis_title VARCHAR(500) NULL; top_hypothesis_score VARCHAR(30) NULL; recommendation_count INTEGER NN PY=0; latest_recommendation_id VARCHAR(255) NULL IDX; recovery_status VARCHAR(50) NULL IDX; latest_recovery_verification_id VARCHAR(255) NULL IDX; occurrence_count INTEGER NN PY=1; status_note TEXT NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `ownership_mappings` — `OwnershipMappingRecord`

`ownership_id VARCHAR(255) PK NN; fingerprint VARCHAR(100) NN IDX UNIQUE; entity_id VARCHAR(500) NULL IDX; service_name VARCHAR(255) NULL IDX; cluster_name VARCHAR(255) NULL IDX; namespace VARCHAR(255) NULL IDX; entity_kind VARCHAR(100) NULL IDX; entity_name VARCHAR(255) NULL IDX; environment VARCHAR(100) NULL IDX; owner_team VARCHAR(255) NN IDX; owner_email VARCHAR(320) NULL; oncall_contact VARCHAR(500) NULL; repository_url VARCHAR(1000) NULL; business_capability VARCHAR(255) NULL IDX; criticality VARCHAR(30) NN IDX PY='tier_3'; source VARCHAR(50) NN PY='manual'; active BOOLEAN NN PY=True; notes TEXT NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `post_incident_report_actions` — `ReportActionItemRecord`

`action_item_id VARCHAR(255) PK NN; report_id VARCHAR(255) NN IDX; incident_id VARCHAR(500) NN IDX; sequence INTEGER NN; title VARCHAR(500) NN; description TEXT NN; owner_team VARCHAR(255) NULL IDX; owner_contact VARCHAR(500) NULL; priority VARCHAR(30) NN IDX; due_date VARCHAR(50) NULL; success_criteria TEXT NN; evidence_ids_json TEXT NN PY='[]'; status VARCHAR(30) NN IDX PY='open'; notes TEXT NULL; completed_at VARCHAR(50) NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `post_incident_reports` — `PostIncidentReportRecord`

`report_id VARCHAR(255) PK NN; incident_id VARCHAR(500) NN IDX; version INTEGER NN; title VARCHAR(500) NN; status VARCHAR(30) NN IDX PY='draft'; provider VARCHAR(50) NN IDX; model_name VARCHAR(255) NULL; prompt_version VARCHAR(100) NN; grounding_hash VARCHAR(100) NN IDX; overall_confidence VARCHAR(30) NN; payload_json TEXT NN; evidence_json TEXT NN; warnings_json TEXT NN PY='[]'; reviewer_name VARCHAR(255) NULL; review_notes TEXT NULL; reviewed_at VARCHAR(50) NULL; approved_at VARCHAR(50) NULL; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `recovery_verifications` — `RecoveryVerificationRecord`

`verification_id VARCHAR(255) PK NN; recommendation_id VARCHAR(255) NN IDX; analysis_id VARCHAR(255) NN IDX; signal_id VARCHAR(500) NN IDX; pre_snapshot_id VARCHAR(255) NN IDX; post_snapshot_id VARCHAR(255) NN IDX; algorithm_version VARCHAR(100) NN; generated_at VARCHAR(50) NN IDX; applied_at VARCHAR(50) NN; status VARCHAR(30) NN IDX; confidence VARCHAR(30) NN; summary TEXT NN; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; target_entity_id VARCHAR(500) NULL IDX; target_entity_kind VARCHAR(100) NULL; target_entity_name VARCHAR(255) NULL; passed_count INTEGER NN; failed_count INTEGER NN; unknown_count INTEGER NN; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `remediation_recommendations` — `RecommendationRecord`

`recommendation_id VARCHAR(255) PK NN; analysis_id VARCHAR(255) NN IDX; hypothesis_id VARCHAR(255) NN IDX; signal_id VARCHAR(500) NN IDX; change_id VARCHAR(255) NN IDX; algorithm_version VARCHAR(50) NN; generated_at VARCHAR(50) NN IDX; title VARCHAR(500) NN; action_type VARCHAR(100) NN IDX; status VARCHAR(30) NN IDX; confidence VARCHAR(30) NN; risk VARCHAR(30) NN IDX; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; target_entity_id VARCHAR(500) NULL IDX; target_entity_kind VARCHAR(100) NULL; target_entity_name VARCHAR(255) NULL; applied_at VARCHAR(50) NULL; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `runtime_dependencies` — `RuntimeDependencyRecord`

`runtime_dependency_id VARCHAR(255) PK NN; agent_id VARCHAR(255) NN IDX; sensor_id VARCHAR(255) NN IDX; cluster_name VARCHAR(255) NN IDX; node_name VARCHAR(255) NN IDX; source_namespace VARCHAR(255) NULL IDX; source_pod_name VARCHAR(255) NULL IDX; source_pod_uid VARCHAR(255) NULL IDX; source_workload_name VARCHAR(255) NULL IDX; source_container_id VARCHAR(255) NULL IDX; source_binary VARCHAR(1000) NULL IDX; source_pid INTEGER NULL; destination_name VARCHAR(1000) NULL IDX; destination_address VARCHAR(255) NN IDX; destination_port INTEGER NN IDX; protocol VARCHAR(20) NN IDX; direction VARCHAR(20) NN IDX PY='outbound'; observation_count INTEGER NN PY=0; success_count INTEGER NN PY=0; failure_count INTEGER NN PY=0; first_seen_at VARCHAR(50) NN IDX; last_seen_at VARCHAR(50) NN IDX; metadata_json TEXT NN PY='{}'; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `runtime_processes` — `RuntimeProcessRecord`

`runtime_process_id VARCHAR(255) PK NN; agent_id VARCHAR(255) NN IDX; sensor_id VARCHAR(255) NN IDX; cluster_name VARCHAR(255) NN IDX; node_name VARCHAR(255) NN IDX; exec_id VARCHAR(500) NULL IDX; pid INTEGER NULL; binary VARCHAR(1000) NN IDX; namespace VARCHAR(255) NULL IDX; pod_name VARCHAR(255) NULL IDX; pod_uid VARCHAR(255) NULL IDX; container_id VARCHAR(255) NULL IDX; parent_exec_id VARCHAR(500) NULL; exec_count INTEGER NN PY=0; exit_count INTEGER NN PY=0; last_exit_code INTEGER NULL; last_signal VARCHAR(100) NULL; first_seen_at VARCHAR(50) NN IDX; last_seen_at VARCHAR(50) NN IDX; metadata_json TEXT NN PY='{}'; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `runtime_sensors` — `RuntimeSensorRecord`

`sensor_id VARCHAR(255) PK NN; agent_id VARCHAR(255) NN IDX; node_name VARCHAR(255) NN IDX; cluster_name VARCHAR(255) NN IDX; source VARCHAR(100) NN IDX PY='tetragon'; version VARCHAR(50) NN; status VARCHAR(30) NN IDX PY='enrolled'; heartbeat_interval_seconds INTEGER NN PY=30; processed_event_count INTEGER NN PY=0; dropped_event_count INTEGER NN PY=0; parser_error_count INTEGER NN PY=0; buffered_batch_count INTEGER NN PY=0; submitted_batch_count INTEGER NN PY=0; source_file VARCHAR(1000) NULL; source_file_offset INTEGER NN PY=0; last_error TEXT NULL; capabilities_json TEXT NN PY='[]'; metadata_json TEXT NN PY='{}'; last_seen_at VARCHAR(50) NULL IDX; last_heartbeat_at VARCHAR(50) NULL IDX; last_batch_at VARCHAR(50) NULL IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `signals` — `SignalRecord`

`signal_id VARCHAR(255) PK NN; fingerprint VARCHAR(100) NN IDX; signal_type VARCHAR(50) NN IDX; severity VARCHAR(30) NN IDX; category VARCHAR(50) NN IDX; source_system VARCHAR(100) NN IDX; title VARCHAR(500) NN; summary TEXT NN; reason VARCHAR(255) NULL IDX; action VARCHAR(255) NULL; first_observed_at VARCHAR(50) NN; last_observed_at VARCHAR(50) NN IDX; occurrence_count INTEGER NN; cluster_name VARCHAR(255) NN IDX; namespace VARCHAR(255) NULL IDX; involved_entity_id VARCHAR(500) NULL IDX; involved_object_uid VARCHAR(255) NULL IDX; involved_object_kind VARCHAR(100) NULL; involved_object_name VARCHAR(255) NULL; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `topo_agents` — `TopoAgentRecord`

`agent_id VARCHAR(255) PK NN; name VARCHAR(255) NN IDX; agent_type VARCHAR(100) NN IDX PY='kubernetes'; cluster_name VARCHAR(255) NN IDX; environment VARCHAR(100) NULL IDX; version VARCHAR(50) NN; token_hash VARCHAR(64) NN IDX UNIQUE; token_hint VARCHAR(32) NN; status VARCHAR(30) NN IDX PY='enrolled'; collection_interval_seconds INTEGER NN PY=300; heartbeat_interval_seconds INTEGER NN PY=30; namespace_scope_json TEXT NN PY='[]'; capabilities_json TEXT NN PY='[]'; labels_json TEXT NN PY='{}'; metadata_json TEXT NN PY='{}'; buffered_item_count INTEGER NN PY=0; last_collection_status VARCHAR(50) NULL; last_error TEXT NULL; last_seen_at VARCHAR(50) NULL IDX; last_heartbeat_at VARCHAR(50) NULL IDX; last_snapshot_at VARCHAR(50) NULL IDX; enrolled_at VARCHAR(50) NN PY=utc_now_iso; revoked_at VARCHAR(50) NULL IDX; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `topology_snapshots` — `SnapshotRecord`

`snapshot_id VARCHAR(255) PK NN; schema_version VARCHAR(30) NN; collected_at VARCHAR(50) NN IDX; collector_name VARCHAR(100) NN; collector_version VARCHAR(50) NN; cluster_name VARCHAR(255) NULL IDX; namespace VARCHAR(255) NULL IDX; entity_count INTEGER NN; relationship_count INTEGER NN; evidence_count INTEGER NN; scope_json TEXT NN; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso`

#### `webhook_deliveries` — `WebhookDeliveryRecord`

`delivery_id VARCHAR(255) PK NN; webhook_id VARCHAR(255) NN IDX; event_id VARCHAR(255) NN IDX; event_type VARCHAR(100) NN IDX; resource_type VARCHAR(100) NN IDX; resource_id VARCHAR(500) NN IDX; status VARCHAR(30) NN IDX; attempt_count INTEGER NN PY=0; response_status INTEGER NULL; response_body TEXT NULL; error_message TEXT NULL; requested_at VARCHAR(50) NN; completed_at VARCHAR(50) NULL; payload_json TEXT NN; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

#### `webhook_endpoints` — `WebhookEndpointRecord`

`webhook_id VARCHAR(255) PK NN; name VARCHAR(255) NN; url VARCHAR(2000) NN; event_types_json TEXT NN; headers_json TEXT NN PY='{}'; signing_secret TEXT NULL; active BOOLEAN NN IDX PY=True; timeout_seconds INTEGER NN PY=10; max_attempts INTEGER NN PY=3; created_at VARCHAR(50) NN PY=utc_now_iso; updated_at VARCHAR(50) NN PY=utc_now_iso`

## 5. Constraint and logical-reference inventory

### Declared database constraints

- Primary keys: 38 single-column keys; no composite PKs.
- Integer/autoincrement PKs: 0.
- Foreign keys: 0.
- ORM `relationship()` mappings and cascades: 0.
- Check constraints: 0.
- Named multi-column `UniqueConstraint`s: 10.
- Column-level `unique=True`: 9; because each also has `index=True`, these are named unique indexes in SQLite.
- Explicit `Index(...)` declarations: 0.
- Total ORM index objects generated by column `index=True`: 296.
- Server defaults: 0; all defaults are application/Python-side.

Named unique constraints:

| Constraint | Table | Columns | Correctness role |
|---|---|---|---|
| `uq_action_approval_event_sequence` | `action_approval_events` | `approval_id, sequence` | one audit event per approval sequence |
| `uq_build_artifact_provider_fact` | `build_artifact_evidence` | `provider, repository_id, workflow_run_id, run_attempt, image_digest, provider_evidence_id` | provider evidence fact idempotency |
| `uq_change_event_entity_link` | `change_entity_links` | `event_id, entity_id, link_type` | idempotent event/entity link |
| `uq_execution_intent_event_sequence` | `execution_intent_events` | `execution_id, sequence` | one audit event per intent sequence |
| `uq_identity_override_target` | `identity_overrides` | `cluster_name, namespace, entity_kind, entity_name` | one current override per scoped object |
| `uq_investigation_plan_sequence` | `incident_investigation_steps` | `plan_id, sequence` | stable plan ordering |
| `uq_post_incident_report_action_sequence` | `post_incident_report_actions` | `report_id, sequence` | stable report-action ordering |
| `uq_post_incident_report_version` | `post_incident_reports` | `incident_id, version` | one report generation per incident version |
| `uq_runtime_sensor_agent_node_source` | `runtime_sensors` | `agent_id, node_name, source` | one sensor registration per node/source |
| `uq_webhook_delivery_event` | `webhook_deliveries` | `webhook_id, event_id` | outbound delivery idempotency |

Column-level unique indexes are `action_approvals.pending_key`, `agent_enrollment_tokens.token_hash`, `change_events.event_fingerprint`, `change_source_deliveries.delivery_key`, `execution_intents.approval_id`, `execution_intents.idempotency_key`, `incident_outcomes.incident_id`, `ownership_mappings.fingerprint`, and `topo_agents.token_hash`.

### Logical reference definition and count

The exact count **95** is reproducible as: every non-PK ORM column ending `_id`, every `*_ids_json`/evidence-reference array, and explicit event/root reference fields selected by the same rule. It excludes each row's own PK and non-`_id` provider identities such as `commit_sha`, image digests, ARNs, `workflow_ref`, `provider_evidence_reference`, `response_plan_reference`, and `result_reference`; those immutable identities are audited separately below.

No logical reference is database-enforced. Application enforcement ranges from an explicit parent lookup and error, through best-effort resolution, to no existence check. There is no database or ORM cascade. The default deletion contract is **retain historical children and do not cascade**; product code only soft-deactivates identity overrides, while destructive deletes found in the repository are test/evaluator-only.

The following table names every one of the 95 fields. `1` means one scalar reference, `N[]` a serialized list, and `0..1` optional. Requiredness is the ORM nullability; an `NN` JSON list may validly be empty. “FK in PH-1B” is **NO for every row** because revision 0001 must reproduce accepted semantics. Future FK candidates remain deferred to a data-lifecycle proof.

| Source table | Field -> target/domain | Cardinality / required | Application enforcement | Delete/historical contract | Future FK posture |
|---|---|---|---|---|---|
| `action_approval_events` | `approval_id -> action_approvals`; `incident_id -> incidents`; `action_id -> embedded response-plan action` | 1/NN each | approval service constructs from known objects; action has no table | retain audit even if parent/config disappears | defer all; action cannot be FK |
| `action_approvals` | `incident_id -> incidents`; `action_id -> embedded action`; `target_entity_ids_json -> entities embedded in pinned snapshot`; `target_change_event_id -> change_events` | first three NN, change event 0..1 | readiness/approval service validates evidence snapshot; no DB check | frozen evidence must remain independently auditable | defer |
| `build_artifact_evidence` | `repository_id`, `workflow_id`, `workflow_run_id`, `provider_evidence_id`, `provider_builder_id -> provider-native identity domains` | mixed NN/0..1 | provider adapter validates/authenticates evidence; no local target table | immutable external identity | not relational FKs |
| `causal_analyses` | `incident_id -> incidents`; `top_root_event_id -> change_events` | incident 1/NN; root 0..1 | analysis loads incident/events; no DB check | analysis generation remains immutable if source later changes | defer |
| `change_entity_links` | `event_id -> change_events`; `entity_id -> entity embedded in snapshot`; `snapshot_id -> topology_snapshots` | first two 1/NN, snapshot 0..1 | correlation resolver; historical direct links can predate snapshot | never cascade away audit/path evidence | defer; embedded entity cannot be FK |
| `change_events` | `external_id -> provider domain`; `origin_change_id -> changes`; `account_id -> provider account scope`; `agent_id -> topo_agents` | all 0..1 | normalizer/agent context; origin and account are not guaranteed local rows | preserve provider identity and original observation | only `agent_id`/origin are possible future candidates; defer |
| `change_source_dead_letters` | `source_id -> change_sources`; `delivery_id -> change_source_deliveries` | 1/NN each | replay explicitly loads both and fails if absent | queue/audit must not cascade silently | defer; future restrict candidate |
| `change_source_deliveries` | `source_id -> change_sources`; `source_delivery_id -> provider domain`; `event_ids_json -> change_events[]` | source NN; provider 0..1; list NN | ingestion loads source and writes event IDs | authenticated receipt survives normalization failure | defer; JSON list is not FK-able |
| `changes` | `from_snapshot_id`, `to_snapshot_id -> topology_snapshots`; `entity_id -> embedded entity`; `relationship_id -> embedded relationship` | snapshots NN; graph refs 0..1 | snapshot diff constructs them | retain exact historical endpoints | defer; graph refs cannot be FK |
| `cloud_resources` | `account_id -> provider account number/domain`; `resource_id`, `vpc_id`, `subnet_ids_json -> provider-native domains`; `agent_id -> topo_agents` | account/resource/agent NN; VPC 0..1; subnets NN list | cloud inventory ingestion | current inventory is recomputable; no cascade assumption | defer; account field is not `cloud_accounts.cloud_account_id` |
| `execution_intent_events` | `execution_id -> execution_intents`; `incident_id -> incidents`; `approval_id -> action_approvals`; `action_id -> embedded action` | 1/NN each | transaction service constructs audit entry | retain immutable audit | defer; action cannot be FK |
| `execution_intents` | `incident_id -> incidents`; `approval_id -> action_approvals`; `action_id -> embedded action`; `target_entity_ids_json -> pinned-snapshot entities[]`; `target_change_event_id -> change_events` | first four NN; change 0..1 | service validates approved evidence; DB uniquely binds approval | retain frozen contract and audit | defer |
| `incident_analyses` | `signal_id -> signals`; `topology_snapshot_id -> topology_snapshots` | 1/NN each | analysis service loads inputs | generation must retain historical pin | defer; future restrict candidate |
| `incident_copilot_messages` | `session_id -> incident_copilot_sessions`; `incident_id -> incidents`; `evidence_ids_json -> heterogeneous evidence IDs[]` | 1/NN each, list may empty | repository/service context | retain conversation/evidence attribution | defer; heterogeneous IDs cannot be FK |
| `incident_copilot_sessions` | `incident_id -> incidents` | 1/NN | service opens against incident | retain session history | defer |
| `incident_explanations` | `incident_id -> incidents`; `topology_snapshot_id -> topology_snapshots`; `analysis_id -> analysis domain (legacy/current depending generation)` | incident NN; others 0..1 | explanation grounding service | preserve grounding generation | defer |
| `incident_investigation_plans` | `incident_id -> incidents` | 1/NN | planner loads incident | preserve grounded generation | defer |
| `incident_investigation_steps` | `plan_id -> incident_investigation_plans`; `incident_id -> incidents`; `evidence_ids_json -> heterogeneous evidence[]` | 1/NN; list may empty | plan repository | preserve response record; no cascade | defer |
| `incident_outcomes` | `incident_id -> incidents`; `causal_analysis_id -> causal_analyses` | incident NN, analysis 0..1 | outcome service loads incident/context | final outcome must survive source retention changes | defer |
| `incidents` | `primary_signal_id`, `latest_signal_id -> signals`; `topology_snapshot_id -> topology_snapshots`; `affected_entity_id -> embedded pinned-snapshot entity`; `latest_analysis_id -> causal/legacy analysis domain`; `latest_recommendation_id -> remediation_recommendations`; `latest_recovery_verification_id -> recovery_verifications` | primary NN; rest 0..1 | lifecycle resolves/pins inputs; pending states permit nulls | initial topology pin must never move; retain incident history | defer; polymorphic/embedded references require design proof |
| `ownership_mappings` | `entity_id -> canonical/topology entity domain` | 0..1 | ownership resolver uses exact/scoped matching | ownership rule remains independent of snapshot retention | cannot safely FK to embedded entity |
| `post_incident_report_actions` | `report_id -> post_incident_reports`; `incident_id -> incidents`; `evidence_ids_json -> heterogeneous evidence[]` | 1/NN; list may empty | repository/planner | preserve report lineage | defer |
| `post_incident_reports` | `incident_id -> incidents` | 1/NN | report service | versioned historical artifact | defer |
| `recovery_verifications` | `recommendation_id -> remediation_recommendations`; `analysis_id -> incident_analyses`; `signal_id -> signals`; `pre_snapshot_id`, `post_snapshot_id -> topology_snapshots`; `target_entity_id -> embedded entity` | first five NN; entity 0..1 | recovery service loads inputs | preserve before/after comparison | defer; embedded entity cannot be FK |
| `remediation_recommendations` | `analysis_id -> incident_analyses`; `hypothesis_id -> hypothesis embedded in analysis payload`; `signal_id -> signals`; `change_id -> changes`; `target_entity_id -> embedded entity` | first four NN; entity 0..1 | recommendation engine derives from analysis | preserve evidence context | defer; embedded hypothesis/entity cannot be FK |
| `runtime_dependencies` | `agent_id -> topo_agents`; `sensor_id -> runtime_sensors`; `source_container_id -> runtime/provider identity` | agent/sensor NN; container 0..1 | ingest authenticates agent/sensor context | mutable/recomputable observation | agent/sensor are future restrict candidates; defer |
| `runtime_processes` | `agent_id -> topo_agents`; `sensor_id -> runtime_sensors`; `exec_id`, `container_id`, `parent_exec_id -> runtime/provider identity domain` | agent/sensor NN; runtime refs 0..1 | runtime ingestion | mutable/recomputable observation | only agent/sensor future candidates; defer |
| `runtime_sensors` | `agent_id -> topo_agents` | 1/NN | sensor registration/auth | mutable current state | defer; future restrict candidate |
| `signals` | `involved_entity_id -> entity embedded in incident-time topology` | 0..1 | lifecycle resolves against pinned snapshot | preserve original evidence even unresolved | cannot FK to embedded entity |
| `webhook_deliveries` | `webhook_id -> webhook_endpoints`; `event_id -> outbound event identity (not a shared table)`; `resource_id -> polymorphic resource` | 1/NN each | delivery service constructs and dedupes | retain delivery audit if endpoint/resource changes | only endpoint is a future restrict candidate; defer others |

Provider/domain identities not included in the 95 count—commit SHAs, image digests/references, repository names/IDs, workflow refs, ARNs, cloud resource IDs, `response_plan_reference`, `result_reference`, and graph IDs embedded in JSON—are deliberately string-valued and often have no relational target. A suffix must never be treated as authority to create an FK.

## 6. Historical truth contract

### Immutable historical records

- `topology_snapshots`: complete `GraphSnapshot` payload, scope, counts, and collection identity. The repository only inserts; historical RCA pins by ID.
- `causal_analyses`: one immutable analysis generation. `save_causal_analysis()` returns the original persisted payload when the deterministic `analysis_id` already exists.
- `build_artifact_evidence`: provider-authentic source/run/image fact with a uniqueness constraint.
- `action_approval_events` and `execution_intent_events`: append-preserving audit events; service convention forbids edits even though the DB has no update guard.

### Append-preserving but stateful

- `signals`: same signal ID merges observation count and first/last time; original first observation and existing topology/entity context win.
- `change_events`: unique fingerprint preserves event identity and original temporal interpretation while richer evidence may be merged on redelivery.
- `change_source_deliveries`/dead letters: authenticated receipt is committed before normalization; processing/replay status mutates.
- `incidents`: correlation updates occurrence/latest state while first observation and original topology pin remain authoritative.
- `change_entity_links`, copilot messages, webhook deliveries, reports, and audit children preserve prior evidence even when status fields later change.

### Mutable current state

`change_sources`, `cloud_accounts`, `cloud_resources`, `identity_overrides`, `ownership_mappings`, `topo_agents`, `agent_enrollment_tokens`, `runtime_sensors`, `runtime_dependencies`, `runtime_processes`, `webhook_endpoints`, approvals, execution intents, investigation steps, report actions, and recommendation/outcome statuses are current lifecycle/configuration or coalesced observation state.

### Generation-based / derived durable

`identity_resolutions`, `incident_analyses`, `incident_explanations`, investigation plans, post-incident reports, recovery verifications, remediation recommendations, incident outcomes, and causal analyses are generated from durable evidence. Some are mutable caches keyed to one generation; causal analyses are explicitly immutable generations.

### Cache/recomputable

Cloud resources, runtime process/dependency aggregates, identity resolutions, blast radius, business impact, incident similarity/memory, response intelligence, and execution readiness are recomputable. Recomputable does not mean disposable during an in-place migration: pinned snapshot payloads and generated evidence outputs remain historical truth.

Historical deletion principle: no initial migration may infer cascade behavior. A future retention design must explicitly distinguish parent configuration deletion from historical evidence retention. PH-1B reproduces zero FKs and zero cascades.

## 7. JSON and large-text payload audit

There are **59 JSON-shaped columns, all SQLAlchemy `Text`**, and **0 portable SQLAlchemy `JSON` columns**. There are **101 total unbounded `TEXT` columns**; the remaining 42 store prose, commands, errors, response bodies, notes, and secrets.

| Table | JSON-text columns | Serialization/validation path | Byte/semantic contract | Initial migration decision |
|---|---|---|---|---|
| `action_approval_events` | `actor_roles_json` | `json.dumps/loads`, sorted roles | audit context; canonical order used in evidence flows | KEEP TEXT |
| `action_approvals` | `target_entity_ids_json`, `readiness_snapshot_json`, `requested_by_roles_json`, `decided_by_roles_json` | sorted `json.dumps`; Pydantic snapshot `model_dump_json/model_validate_json` | readiness/evidence fingerprints are canonical-semantic; preserve stored bytes | KEEP TEXT |
| `build_artifact_evidence` | `temporal_json` | Pydantic temporal dump/load | TC-3 evidence payload | KEEP TEXT |
| `causal_analyses` | `payload_json` | `CausalAnalysisResponse.model_dump_json/model_validate_json` | contains hypotheses, causal chain, confidence semantics and TC-4 evidence ledger; immutable bytes | KEEP TEXT |
| `change_events` | `metadata_json`, `raw_payload_json` | `json.dumps/loads`; source enrichment merges dictionaries | semantic JSON; source mutation fingerprints use separate canonical serialization | KEEP TEXT |
| `change_source_dead_letters` | `payload_json` | redacted delivery JSON copied/replayed | replay/audit bytes | KEEP TEXT |
| `change_source_deliveries` | `headers_json`, `payload_json`, `event_ids_json` | safe-header `json.dumps`; recursive redaction; list dump/load | authenticated receipt/audit; list order is processing order | KEEP TEXT |
| `change_sources` | `config_json`, `filters_json` | `json.dumps/loads` | mutable connector configuration; key order not queried | KEEP TEXT |
| `changes` | `payload_json` | `NormalizedChange.model_dump_json/model_validate_json` | derived historical payload | KEEP TEXT |
| `cloud_accounts` | `metadata_json` | `json.dumps/loads` | provider metadata | KEEP TEXT |
| `cloud_resources` | `subnet_ids_json`, `tags_json`, `properties_json` | `json.dumps/loads` | provider inventory; list/map semantics | KEEP TEXT |
| `execution_intent_events` | `actor_roles_json` | sorted `json.dumps/loads` | audit context | KEEP TEXT |
| `execution_intents` | `target_entity_ids_json`, `execution_snapshot_json`, `created_by_roles_json` | sorted dumps; Pydantic contract snapshot | evidence fingerprint and immutable contract snapshot | KEEP TEXT |
| `identity_resolutions` | `payload_json` | `IdentityResolutionResult.model_dump_json/model_validate_json` | generation payload | KEEP TEXT |
| `incident_analyses` | `payload_json` | `IncidentAnalysis.model_dump_json/model_validate_json` | legacy generated evidence | KEEP TEXT |
| `incident_copilot_messages` | `evidence_ids_json`, `evidence_json`, `suggested_questions_json` | `json.dumps/loads` | evidence ID and presentation ordering may matter | KEEP TEXT |
| `incident_explanations` | `payload_json`, `evidence_json`, `warnings_json` | Pydantic payload plus JSON lists | grounded output/audit | KEEP TEXT |
| `incident_investigation_plans` | `evidence_gaps_json`, `warnings_json`, `evidence_json`, `payload_json` | JSON lists plus Pydantic plan payload | grounded generation and ordered plan context | KEEP TEXT |
| `incident_investigation_steps` | `evidence_ids_json` | `json.dumps/loads` | ordered evidence references | KEEP TEXT |
| `incident_outcomes` | `source_json`, `payload_json` | source uses sorted `json.dumps`; outcome uses Pydantic | durable resolution source and payload | KEEP TEXT |
| `post_incident_report_actions` | `evidence_ids_json` | `json.dumps/loads` | ordered evidence refs | KEEP TEXT |
| `post_incident_reports` | `payload_json`, `evidence_json`, `warnings_json` | Pydantic plus JSON lists | versioned grounded report | KEEP TEXT |
| `recovery_verifications` | `payload_json` | Pydantic dump/load | before/after derived evidence | KEEP TEXT |
| `remediation_recommendations` | `payload_json` | Pydantic dump/load | evidence-backed guidance | KEEP TEXT |
| `runtime_dependencies` | `metadata_json` | `json.dumps/loads`, merged | current observation metadata | KEEP TEXT |
| `runtime_processes` | `metadata_json` | `json.dumps/loads`, merged | current observation metadata | KEEP TEXT |
| `runtime_sensors` | `capabilities_json`, `metadata_json` | `json.dumps/loads` | sensor config/status metadata | KEEP TEXT |
| `signals` | `payload_json` | `NormalizedSignal.model_dump_json/model_validate_json` | authoritative normalized observation and TC-3 metadata | KEEP TEXT |
| `topo_agents` | `namespace_scope_json`, `capabilities_json`, `labels_json`, `metadata_json` | `json.dumps/loads` | agent config/current metadata | KEEP TEXT |
| `topology_snapshots` | `scope_json`, `payload_json` | `json.dumps(scope)` and `GraphSnapshot.model_dump_json/model_validate_json` | graph entity/relationship/evidence order and historical bytes must be preserved | KEEP TEXT |
| `webhook_deliveries` | `payload_json` | canonical outbound event body stored/read | delivery audit | KEEP TEXT |
| `webhook_endpoints` | `event_types_json`, `headers_json` | `json.dumps/loads` | endpoint behavior; headers may be sensitive | KEEP TEXT |

No product SQL query inspects JSON content. No `json_extract`, `json_each`, or other SQLite JSON function is used. Pydantic and Python own validation. Converting these columns to Postgres JSONB in revision 0001 would change byte representation, key/duplicate handling, and potentially array/object round trips without providing current query value. Therefore all 59 remain `TEXT`; JSON/JSONB conversion is a separately measured future migration, not PH-1B.

## 8. Datetime and TC-3 inventory

Persisted SQLAlchemy `DateTime` columns: **0** (`timezone=True`: 0; `timezone=False`: 0). Timestamp-shaped `VARCHAR(50)` columns: **134**. They store ISO-8601 strings produced primarily by timezone-aware UTC `datetime.now(timezone.utc).isoformat()` or Pydantic serialization.

| Table | ISO-string timestamp fields |
|---|---|
| `action_approval_events` | `occurred_at` |
| `action_approvals` | `requested_at`, `decided_at`, `expires_at`, `revoked_at`, `invalidated_at`, `created_at`, `updated_at` |
| `agent_enrollment_tokens` | `expires_at`, `last_used_at`, `revoked_at`, `created_at`, `updated_at` |
| `build_artifact_evidence` | `provider_build_started_at`, `provider_build_finished_at`, `provider_run_updated_at`, `observed_at`, `created_at`, `updated_at` |
| `causal_analyses` | `generated_at`, `created_at`, `updated_at` |
| `change_entity_links` | `created_at`, `updated_at` |
| `change_events` | `occurred_at`, `received_at`, `created_at`, `updated_at` |
| `change_source_dead_letters` | `last_attempt_at`, `replayed_at`, `created_at` |
| `change_source_deliveries` | `received_at`, `processed_at` |
| `change_sources` | `last_event_at`, `last_success_at`, `last_error_at`, `created_at`, `updated_at` |
| `changes` | `detected_at`, `created_at`, `updated_at` |
| `cloud_accounts` | `last_seen_at`, `created_at`, `updated_at` |
| `cloud_resources` | `observed_at`, `created_at`, `updated_at` |
| `execution_intent_events` | `occurred_at` |
| `execution_intents` | `created_at`, `claimed_at`, `claim_expires_at`, `cancelled_at`, `invalidated_at`, `expired_at`, `started_at`, `completed_at`, `failed_at`, `updated_at` |
| `identity_overrides` | `created_at`, `updated_at` |
| `identity_resolutions` | `generated_at`, `created_at`, `updated_at` |
| `incident_analyses` | `generated_at`, `created_at`, `updated_at` |
| `incident_copilot_messages` | `created_at` |
| `incident_copilot_sessions` | `created_at`, `updated_at` |
| `incident_explanations` | `generated_at`, `created_at`, `updated_at` |
| `incident_investigation_plans` | `created_at`, `updated_at` |
| `incident_investigation_steps` | `completed_at`, `created_at`, `updated_at` |
| `incident_outcomes` | `mitigated_at`, `resolved_at`, `created_at`, `updated_at` |
| `incidents` | `first_observed_at`, `last_observed_at`, `created_at`, `updated_at` |
| `ownership_mappings` | `created_at`, `updated_at` |
| `post_incident_report_actions` | `completed_at`, `created_at`, `updated_at` (`due_date` is a date-like string but excluded from the timestamp count) |
| `post_incident_reports` | `reviewed_at`, `approved_at`, `created_at`, `updated_at` |
| `recovery_verifications` | `generated_at`, `applied_at`, `created_at`, `updated_at` |
| `remediation_recommendations` | `generated_at`, `applied_at`, `created_at`, `updated_at` |
| `runtime_dependencies` | `first_seen_at`, `last_seen_at`, `created_at`, `updated_at` |
| `runtime_processes` | `first_seen_at`, `last_seen_at`, `created_at`, `updated_at` |
| `runtime_sensors` | `last_seen_at`, `last_heartbeat_at`, `last_batch_at`, `created_at`, `updated_at` |
| `signals` | `first_observed_at`, `last_observed_at`, `created_at`, `updated_at` |
| `topo_agents` | `last_seen_at`, `last_heartbeat_at`, `last_snapshot_at`, `enrolled_at`, `revoked_at`, `created_at`, `updated_at` |
| `topology_snapshots` | `collected_at`, `created_at` |
| `webhook_deliveries` | `requested_at`, `completed_at`, `created_at`, `updated_at` |
| `webhook_endpoints` | `created_at`, `updated_at` |

TC-3 distinguishes source/effective, observed, recorded, validity, origin, quality, and status inside typed JSON metadata. `parse_utc()` rejects naive authoritative timestamps unless a legacy path explicitly opts in, converts `Z` to `+00:00`, and normalizes to UTC. Historical snapshot selection parses values to UTC before comparison rather than trusting lexical ordering.

Clock findings:

- Product code contains one `datetime.utcnow()` call in `investigation_planner.py`; it is only a force-regeneration ID salt, not a persisted authoritative event time. It remains a naive-string consistency risk but does not justify a PH-1B schema change.
- Product/agent code otherwise uses timezone-aware `datetime.now(timezone.utc)` (or `UTC`) in the shared model clock, temporal service, repositories, collectors, agent watchers, analysis generators, and webhook creation.
- Several legacy load paths call `fromisoformat()` and explicitly attach UTC to naive stored values. That compatibility behavior must remain.
- String comparisons exist in repository filters/orderings. Canonical UTC ISO strings are lexically useful, but offsets and legacy naive values can differ; TC-3 critical paths parse before comparison.

Changing revision 0001 to `TIMESTAMP WITH TIME ZONE` would parse/rewrite values, normalize representation, reject legacy strings, change returned Python types, and risk TC-3/evaluation hashes. **Initial migration requires no timestamp semantic change. Keep `VARCHAR(50)` exactly.** A future typed-timestamp migration must be data-profiled, dual-read/backfilled, and TC-3-regression tested.

## 9. Enum, Boolean, numeric, and permissive typing inventory

- Native SQL `Enum`: 0.
- A deterministic name/discriminator scan finds **91 string enum-like/discriminator fields** (status, type, kind, source/provider, severity, category, risk/confidence, action, protocol/direction, and related fields). Some are Python Enum values; others intentionally accept open provider strings. None has a DB check constraint.
- Recommendation: preserve `VARCHAR`/`TEXT`; do not introduce native Postgres enums in PH-1B.
- Boolean columns: 6 — `action_approvals.requires_human_approval`, `change_sources.enabled`, `execution_intents.execution_performed`, `identity_overrides.active`, `ownership_mappings.active`, and `webhook_endpoints.active`. SQLAlchemy Boolean is portable; current SQLite integer representation is an implementation detail. Preserve SQLAlchemy `Boolean` exactly.
- Integer columns: 56; none is a primary key. Counters, sequence/generation, ports/PIDs, timeouts, scores, and versions use Python integers.
- Float columns: 2 (`causal_analyses.top_hypothesis_score`, `change_entity_links.confidence`). There is no Decimal/Numeric precision contract.
- SQLite permissive typing currently accepts any value SQLite can store, while Postgres will enforce declared lengths/types and Boolean values. Pydantic/repository validation is the present first line of defense. PH-1B must test representative persisted values without silently coercing the domain.

## 10. Identity and primary-key contract

Every table has exactly one application-supplied string PK; no PK has a Python or server default. There are no sequences or autoincrement assumptions.

- 37 PKs are `VARCHAR(255)` or shorter; `cloud_resources.cloud_resource_id` is `VARCHAR(1000)`.
- Random/high-entropy IDs are used for configuration/lifecycle roots such as overrides, source records, webhook endpoints, copilot sessions/messages, enrollment tokens, agents, approval IDs/events, and execution IDs/events.
- Deterministic hash/fingerprint IDs are used for signals, incidents/recurrences, changes, change events/links, causal analyses and evidence nodes, recommendations, recovery verification, plans/reports/steps, runtime dependency/process/sensor facts, build artifact evidence, cloud resources, graph relationships/evidence, and many generated analysis artifacts.
- Provider-native identity is preserved in separate columns: repository/run/commit/image/provider evidence, cloud IDs/ARNs, Kubernetes UID/name/scope, runtime exec/container IDs, and delivery IDs.
- `identity_resolutions.snapshot_id` deliberately reuses the snapshot identity as its PK, enforcing one materialized resolution per snapshot without an FK.

Observed prefixes include `snapshot:`, `incident:`, `signal:`, `causal-analysis:`, `causal-hypothesis:`, `change-event:`, `change:`, `agent:`, `override:`, `webhook:`, `build-artifact-evidence:`, `rel:`, `evidence:`, `k8s:`, `github:`, `image:`, `runtime-*`, approval, and execution identities. Exact case and canonicalization remain application-owned.

Portability risks:

- PostgreSQL enforces declared `VARCHAR(n)` lengths; SQLite does not.
- Default Postgres collation/locale can order strings differently from SQLite BINARY order. Equality is generally case-sensitive in both, but SQLite `LIKE` has ASCII case-insensitive behavior while Postgres `LIKE` is case-sensitive. No product `.like()`/`.ilike()` query was found.
- Indexed fields as large as `VARCHAR(1000)` and PK `cloud_resource_id VARCHAR(1000)` can exceed practical Postgres B-tree entry limits for unusually long multibyte values. Empty DDL will succeed, but long inserts can fail. Representative maximum-value testing is a PH-1C gate; do not truncate or hash-replace domain identity in PH-1B.
- No product logic depends on integer PK ordering or `last_insert_rowid()`.

## 11. Index and query-pattern audit

Current metadata has 296 single-column index objects and no explicit composite `Index(...)` declarations. The 10 multi-column unique constraints create their own backing indexes. The existing explicit indexes cover nearly every commonly filtered scalar: incident/signal/snapshot/analysis/change/entity IDs, fingerprints, provider fields, cluster/namespace/environment, account/region, status/type/severity/category, and many timestamp fields.

Correctness-critical current indexes/constraints include token hashes, change event fingerprint, source delivery key, approval pending key, execution approval/idempotency keys, one outcome per incident, ownership fingerprint, audit/report/step sequences, event/entity link uniqueness, artifact provider fact uniqueness, sensor identity, and outbound delivery uniqueness. Revision 0001 must reproduce their names, uniqueness, and nullability exactly.

Likely missing correctness/transaction protections—not PH-1B index additions—are:

- one open incident per correlation family/window (a simple unique fingerprint would incorrectly block later recurrences);
- atomic enrollment-token max-use consumption;
- check-then-insert handling for deterministic snapshot, signal, runtime, cloud, ownership, webhook, and evidence IDs;
- race-safe `max(sequence)+1` or equivalent event/report/step generation;
- transaction-level linkage across incident creation, topology pinning, RCA persistence, and incident summary attachment.

Performance-only composite candidates for PH-1C/PH-10 measurement:

- `topology_snapshots(cluster_name, namespace, collected_at)`;
- `signals(cluster_name, namespace, last_observed_at)`;
- `incidents(cluster_name, namespace, status, last_observed_at)` and fingerprint/status/time correlation;
- `causal_analyses(incident_id, generated_at)`;
- `change_events(cluster_name, namespace, occurred_at)`, repository/commit/time, and source/kind/time;
- `change_source_deliveries(source_id, status, received_at)`;
- `runtime_dependencies(cluster_name, source_namespace, source_pod_uid, last_seen_at)`;
- `runtime_processes(cluster_name, namespace, pod_uid, last_seen_at)`;
- `cloud_resources(provider, account_id, region, resource_type)`;
- approval/execution incident/status/time and child parent/sequence access.

These are hypotheses, not permission to tune revision 0001. Query plans and production cardinality must justify them later.

## 12. Database initialization and test setup

Exact startup behavior:

1. Importing `app.db.database` computes `BACKEND_DIR`, creates `backend/data`, selects `TOPO_DATABASE_URL` or the file default, creates the synchronous engine, and creates `SessionLocal`.
2. FastAPI lifespan in `backend/app/main.py` calls `init_db()` before serving.
3. `init_db()` imports `app.db.models` and calls `Base.metadata.create_all(bind=engine)`.
4. On an empty database, all currently declared tables/indexes/constraints are created.
5. On an existing database, missing tables and missing named indexes may be created, but existing tables are not altered to add/rename/drop columns or change types/nullability/constraints. Removed tables remain.
6. Therefore startup can silently accumulate schema drift while appearing successful.

There is no schema revision table, migration history, downgrade mechanism, drift verifier, or startup expected-revision check. `PRAGMA user_version` is 0 in both inspected databases.

Nineteen backend test modules call `Base.metadata.create_all()` against in-memory SQLite: `test_action_approval.py`, `test_blast_impact_policy.py`, `test_canonical_identity.py`, `test_causal_candidate_policy.py`, `test_causal_evaluation_budget.py`, `test_causal_evidence_ledger.py`, `test_causal_hypothesis_projection.py`, `test_causal_relevance_policy.py`, `test_continuous_lifecycle.py`, `test_execution_transaction.py`, `test_github_actions_build_lineage.py`, `test_identity_transition_diff.py`, `test_incident_outcome.py`, `test_lineage_candidate_admission.py`, `test_lineage_causal_relevance.py`, `test_relationship_provenance.py`, `test_sc3_container_image_identity.py`, `test_source_file_mutations.py`, and `test_temporal_semantics.py`.

All 19 use `sqlite:///:memory:` or `sqlite+pysqlite:///:memory:`; several use `StaticPool` and `check_same_thread=False`. `test_execution_transaction.py` additionally uses temporary file-backed SQLite databases for creation/claim race tests. `backend/tests/conftest.py` exposes a `db_session` using the default global `SessionLocal`; despite its “transactional” docstring, it only closes the session and does not wrap/rollback a test transaction. That is a test-isolation risk and a reason migration tests need dedicated engines.

Future authority split:

- Explicit unit/evaluation helpers may intentionally create a transient SQLite schema.
- Production must receive a separately migrated database and fail closed when its Alembic revision does not match the application.
- Application startup must not use `create_all()` as production schema evolution.

## 13. URL, engine, and Postgres portability

| Assumption | Location | Classification | PH-1 implication |
|---|---|---|---|
| default file `backend/data/topo.db` | `app/db/database.py` | SQLite/local by design | preserve local default unless separately changed; production supplies URL |
| `DATA_DIR.mkdir()` at import | same | filesystem/SQLite convenience | harmless but unnecessary for Postgres; not a PH-1B semantic change unless authority separation requires it |
| URL passed directly to `create_engine` | same | portable | add supported Postgres driver in PH-1B |
| `DATABASE_URL.startswith("sqlite")` | same | dialect guard | correctly limits `check_same_thread=False`; verify variants |
| `check_same_thread=False` | same/tests | SQLite-only | do not pass to Postgres |
| no pool tuning/pre-ping | same | development default | production operational tuning belongs PH-1C/PH-10 |
| synchronous sessions | all repositories | portable | use sync Postgres driver; no async rewrite |
| `autoflush=False` | `SessionLocal` | portable but behaviorally significant | explicit flush points and query-before-flush behavior must remain |
| `expire_on_commit=False` | `SessionLocal` | portable but stale-read relevant | preserve initially |
| default isolation | engine | dialect-dependent | Postgres `READ COMMITTED` differs from SQLite locking; concurrency gates required |
| file-copy evaluator seeds | evaluation | evaluation-only SQLite | retain unchanged |

No CLI or agent code parses or opens the product DB URL. No Postgres dependency is currently present.

## 14. Raw SQL and SQLite-specific behavior

Product runtime findings:

- direct `sqlite3`: none;
- `PRAGMA`: none;
- raw `text()` SQL: none;
- SQLite `INSERT OR ...`, `ON CONFLICT`, `rowid`, `AUTOINCREMENT`, `last_insert_rowid`, `strftime`, `datetime`, JSON functions, `COLLATE NOCASE`, `GLOB`, `BEGIN IMMEDIATE`, `VACUUM`, and `ATTACH`: none;
- one product `session.execute()` is SQLAlchemy Core `update()` in `execution_intent_repository.py`, guarded by expected state/row version and portable to Postgres.

Direct SQLite use is isolated to eight evaluation/evaluation-test files: `evaluation/causal_forensics.py`, `evaluation/lineage_broken_image_workload.py`, `evaluation/lineage_broken_run_image.py`, `evaluation/lineage_distractor_robustness.py`, and their four corresponding tests. Uses include:

- immutable/read-only inspection via `mode=ro&immutable=1` and `PRAGMA query_only=ON`;
- `quick_check`/`integrity_check` and `sqlite_master` inspection;
- deterministic `ORDER BY rowid` forensic extraction;
- `?` positional placeholders;
- controlled `DELETE`/`UPDATE` mutations against isolated copies for broken-lineage experiments;
- SQLAlchemy `text()` count checks inside the evaluator.

These flows are evaluation-only, intentionally SQLite, and do not block the Postgres product path. They must not be rewritten merely because production adds Postgres.

## 15. Transaction-boundary inventory

Static application AST inventory found **57 `commit()` calls, 10 `rollback()` calls, 3 `flush()` calls, 27 `refresh()` calls, 1 Core `execute()` call, no `session.begin()`, and no nested transaction** across 31 files. Twenty-four repository modules commit internally:

`action_approval_repository`, `agent_repository`, `build_artifact_evidence_repository`, `causal_analysis_repository`, `change_event_repository`, `change_repository`, `change_source_repository`, `cloud_repository`, `copilot_repository`, `execution_intent_repository`, `identity_repository`, `incident_explanation_repository`, `incident_outcome_repository`, `incident_record_repository`, `incident_repository`, `investigation_plan_repository`, `ownership_repository`, `post_incident_report_repository`, `recommendation_repository`, `recovery_repository`, `runtime_observability_repository`, `signal_repository`, `snapshot_repository`, and `webhook_repository`.

Additional commit owners are `api/agents.py`, `services/change_event_bridge.py`, `services/change_source_ingest.py`, `services/continuous_lifecycle.py`, and `services/incident_lifecycle.py`. `services/webhook_delivery.py` can roll back. Some repositories accept `commit=False` to allow local bundling (`causal_analysis`, build artifact, change event/correlation), but the pattern is not uniform.

Important logical multi-step operations:

- **Automatic lifecycle:** snapshot persistence, signal persistence, incident create/correlate, causal-analysis persistence, incident summary attachment, and outbound webhook may commit in separate steps. A later failure can leave a valid degraded state, but there is no enclosing transaction.
- **Agent snapshot ingest:** graph snapshot, enrichments, cloud/runtime aggregates, agent success state, derived failure signals, incident lifecycle, and RCA cross multiple repository commits.
- **Change-source webhook:** the authenticated delivery is intentionally committed first; event normalization/link insertion is grouped with `commit=False`, then delivery/source status commits. On failure, dead-letter state commits. This durability boundary is deliberate and must not be flattened accidentally.
- **Incident/RCA:** the immutable `CausalAnalysisRecord` commit and the mutable incident `latest_analysis_id`/summary commit are separate, allowing recoverable attachment lag.
- **Approval/execution:** creation handles uniqueness races; execution state transitions use a conditional Core update and row version, followed by event creation. Event sequence allocation remains a potential race.
- **Enrollment:** max-use check, use increment, and agent insert share one commit but use read-modify-write without a row lock.

Risk classification:

| Pattern | Classification | Examples | Target |
|---|---|---|---|
| deterministic PK/check-then-insert | likely multi-writer race; DB constraint required and retry contract needed | signals, snapshots, runtime facts, cloud inventory, ownership, event links | PH-10, with Postgres tests in PH-1C |
| read-modify-write counters | safe only under light/single writer; lost update possible | occurrence counts, source delivery/failure counts, sensor counters, token uses | PH-10 |
| max/sequence allocation then insert | unique constraint catches collision but retry may be missing | audit events, report/step sequences | PH-10 |
| open incident correlation | application-only uniqueness/window policy | fingerprint/status/time search | PH-10; do not add naive unique fingerprint |
| immutable generation insert | PK/unique constraint is correct; idempotent load behavior must be preserved | causal analysis, build evidence | PH-1B parity + PH-1C concurrency test |
| conditional state update | comparatively Postgres-ready | execution intent `_atomic_transition` with row version | PH-1C regression |
| intentional durable receipt before processing | multi-transaction by design | change-source ingestion | preserve and document |

SQLite's coarse writer serialization can mask races that Postgres permits. PH-1B must not pretend schema migration solves them; PH-1C exercises Postgres behavior and PH-10 owns concurrency/operational hardening.

## 16. Actual SQLite schema inspection

Both files were opened immutable/query-only. No WAL/SHM companion was used or changed.

### Local developer database

- Path: `backend/data/topo.db`
- Exists: **YES**
- Size during audit: `336,576,512` bytes
- SHA-256 before: `C3A2AB62DC6B8B8C68DEDFD26B858EBB3BB7199323217BE96B7764AEF7821BAF`
- SHA-256 after: `C3A2AB62DC6B8B8C68DEDFD26B858EBB3BB7199323217BE96B7764AEF7821BAF`
- `PRAGMA quick_check`: `ok`
- `PRAGMA integrity_check`: `ok`
- `user_version`: `0`
- `schema_version`: `349` (SQLite internal schema counter, not a migration revision)
- Tables: 41
- Columns: 725
- PK columns: 41
- Named/non-auto indexes: 308
- SQLite autoindexes: 52
- Named `UniqueConstraint`-origin autoindexes: 11
Foreign keys: 0

Comparison to current ORM:

- ORM-only tables: none.
- DB-only tables: `integrations`, `integration_deliveries`, `change_dead_letters`; all three contained zero rows during inspection.
- Column drift: `change_source_dead_letters` is missing current ORM columns `last_attempt_at` and `replayed_at`.
- Index drift: `change_source_deliveries` is missing `ix_change_source_deliveries_payload_sha256` and `ix_change_source_deliveries_received_at`.
- Constraint drift: legacy `integration_deliveries` has extra `uq_integration_delivery_key`; current-table PK/unique constraints otherwise match.

Classification: **CURRENT DEV DB DRIFT**, not corruption. The three legacy tables correspond structurally to the renamed change-source tables and were never dropped. `create_all()` also failed to add two columns to an existing table. This database must not be blindly stamped as current.

### Frozen LINEAGE seed

- Path: `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`
- Exists: **YES**
- Size during audit: `1,773,568` bytes
- SHA-256 before: `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`
- SHA-256 after: `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`
- `PRAGMA quick_check`: `ok`
- `PRAGMA integrity_check`: `ok`
- `user_version`: `0`
- `schema_version`: `334`
- Tables: 38
- Columns: 687
- PK columns: 38
- Named/non-auto indexes: 296
- SQLite autoindexes: 48
- Named `UniqueConstraint`-origin autoindexes: 10
Foreign keys: 0

Comparison to current ORM: no table, column, PK, named index, unique-constraint, or FK divergence. Classification: **NO DIVERGENCE**. This result is evidence about schema parity only; the seed remains a historical immutable artifact and is never upgraded or stamped.

## 17. Why `create_all()` is not migration

`create_all()` is create-if-absent DDL. Current consequences:

| Model change | Existing database result |
|---|---|
| new table | created at next startup |
| new index on existing table | may be created |
| new nullable/non-null column | not added |
| renamed column | old remains; new is not created |
| changed type/nullability/default | unchanged |
| new FK/check/unique constraint | generally not applied to existing table |
| removed index/constraint | remains unless manually removed |
| removed table | remains |

The developer DB demonstrates these outcomes directly. Production startup must not silently depend on `create_all()` for evolution. Tests/evaluation may retain explicit schema creation when they knowingly create disposable SQLite state.

## 18. Alembic initial-revision strategies

| Strategy | New Postgres | Existing local SQLite | Frozen seed/tests | Verification/rollback | Assessment |
|---|---|---|---|---|---|
| **A. 0001 creates today's accepted ORM schema** | correct clean installation | upgrade collides with existing tables unless separately adopted | empty SQLite tests work; frozen seed must not run 0001 | clear downgrade on disposable DB; does not itself solve adoption | necessary foundation but incomplete alone |
| **B. stamp an assumed pre-existing schema** | inappropriate for empty DB | dangerously labels drifted DB current | could falsely label historical seed | no proof schema equals revision | reject |
| **C. separate SQLite and Postgres histories** | can work | preserves local path | evaluator remains SQLite | two authorities drift and double review burden | reject as default |
| **D. one canonical 0001 plus verified dual-entry adoption** | run upgrade from empty to head | exact-schema existing DB may be stamped only after fingerprint verification; drifted DB fails closed or remains legacy local | empty fixtures migrate; frozen seeds use explicit evaluation compatibility and are untouched | one history; disposable downgrade; unknown schema never stamped | **recommend** |

### Recommended strategy: D

Revision 0001 must explicitly reproduce the accepted 38-table metadata—names, column types/lengths, nullability, PKs, Python-vs-server default reality, 10 named unique constraints, 9 unique indexes, and all 296 named indexes—from an empty SQLite database and a new Postgres database.

Adoption contract:

1. Empty database: `alembic upgrade head` creates revision 0001.
2. Existing database: compute/compare a reviewed schema fingerprint containing tables, columns/types/nullability, PKs, named indexes/uniqueness, and FKs.
3. Exact match to 0001: an explicit operator action may stamp 0001 without DDL.
4. Any mismatch: fail closed. Do not stamp. Back up first and choose rebuild, explicit repair migration, or continued legacy-local use.
5. Never auto-stamp because tables merely “look present.”

This keeps one schema authority while acknowledging that unmanaged developer DBs and immutable evaluator seeds have different operational contracts.

## 19. Existing SQLite-data policy

- **Frozen evaluation seeds:** remain byte-identical SQLite. Never migrate, stamp, or open them through a production startup revision check. Scenario runners copy them and may mutate only the copy.
- **Developer `topo.db`:** may remain a local SQLite database. The inspected file is drifted and cannot be verified/stamped as revision 0001. Before any future repair/rebuild, make a backup and use an explicit reviewed data-preservation procedure.
- **New local/test databases:** may be Alembic-created or explicitly metadata-created in isolated tests according to the test contract; migration parity tests should prefer Alembic.
- **Future customer production databases:** start under Alembic/Postgres before customer data. There is no accepted production/customer database history requiring arbitrary migration.

Automatic arbitrary SQLite-to-Postgres migration for V1: **NO**. This is the last low-cost point to establish migration discipline. If a real customer/developer-data transfer requirement appears, it should be a separately tested export/import project with identity, JSON-byte, timestamp, row-count, and referential audits.

## 20. Tenancy preparation inventory

No `tenant_id` exists. The only column found by tenant/workspace/project naming is `change_events.terraform_workspace`, which is Terraform provider scope, not a Topo tenant. `account_id` is cloud/provider scope, also not tenancy.

- **Tenant-owned candidates:** `topology_snapshots`, `signals`, `incidents`, `change_events`, `change_sources`, `cloud_accounts`, `topo_agents`, `identity_overrides`, `ownership_mappings`, and `webhook_endpoints`.
- **Tenant-derived candidates:** all analysis/change children, entity links, deliveries/dead letters, cloud resources, runtime sensor/process/dependency rows, explanations/copilot/plans/reports/outcomes, approvals/events, execution intents/events, webhook deliveries, and other incident children.
- **Global system candidates:** none of the 38 domain tables is proven global. Alembic's future version table is global schema infrastructure, not tenant data.
- **Unknown pending PH-3:** `agent_enrollment_tokens` (global bootstrap versus tenant issuance) and `build_artifact_evidence` (tenant-owned repository fact versus safely shared immutable provider fact).
- **Evaluation/local only:** no ORM table is intrinsically evaluation-only; evaluation uses ordinary product tables in isolated SQLite copies.

PH-1B must not add tenant fields or rewrite uniqueness. Its migration organization and downgrade policy must make PH-3 additive migrations possible without losing historical data.

## 21. Auth and security persistence

| Surface | Persisted data | Sensitivity / risk | Tenancy implication |
|---|---|---|---|
| API principals/tokens | no table; token-hash registry and principal roles come from `TOPO_API_TOKEN_HASHES_JSON` | hashes/config are environment secrets; auth defaults disabled for local development | PH-2/PH-3 must define persisted identity separately |
| `agent_enrollment_tokens` | SHA-256 token hash, partial hint, use/expiry/revocation, creator | raw token returned once; high-entropy unsalted hash is still sensitive; max-use race | tenant issuance unclear |
| `topo_agents` | SHA-256 agent token hash, hint, identity/config/health | raw agent token returned once; hash sensitive | likely tenant-owned |
| `change_sources` | `secret_ref`, config/filter JSON | stores a reference, not the secret; config may still contain sensitive provider metadata | tenant-owned |
| change deliveries | safe allowlisted headers and recursively redacted payload | redaction matches known keys, so unusual secret keys remain a residual risk | tenant-derived |
| `webhook_endpoints` | URL, arbitrary outbound `headers_json`, **plaintext `signing_secret`** | explicit production blocker for secret management; headers may contain plaintext authorization | tenant-owned; encryption/secret manager in PH-4/PH-5 |
| `webhook_deliveries` | outbound payload, response body/error | response body may contain sensitive remote content | tenant-derived/audited |
| approvals/events | actor subjects/display names/roles/auth type, reasons, evidence fingerprint | security/audit PII and decision record | tenant-derived; retention/access controls required |
| execution intents/events | actor/claimer identity, roles, claim token hash, errors/result reference, frozen execution snapshot | dormant future execution security/audit data; never expose claim hash | tenant-derived |

No users, roles, sessions, or generic API credential table exists. Plaintext webhook secret/header persistence is the highest raw-secret finding. PH-1A does not repair it.

## 22. Evaluation compatibility contract

The following is frozen for PH-1B/C:

1. Frozen seed files stay SQLite and byte-identical.
2. Seed copy semantics remain `shutil.copy2`; mutations occur only in isolated copies.
3. Evaluator-only `sqlite3`, `PRAGMA`, `rowid`, and direct SQL remain allowed.
4. Isolated evaluation backends may still create disposable SQLite schema without requiring external Postgres.
5. Backend services invoked directly against scenario SQLite—especially `analyze_causal_rca`, snapshot loading, change/event/lineage repositories, temporal semantics, and evidence projection—must continue to work.
6. LINEAGE, TC, blast, AR, and EAI regression suites remain required gates.
7. No migration/version check may reject a frozen seed solely because it intentionally lacks `alembic_version`; evaluation compatibility must be explicit and cannot weaken production fail-closed behavior.

## 23. Postgres compatibility risk matrix

| Risk | Current evidence / SQLite behavior | Potential Postgres difference | Severity | Block PH-1B? | Required action / target |
|---|---|---|---|---|---|
| schema authority | startup `create_all`, no revision | unmanaged drift is invisible | critical | no, PH-1B fixes foundation | Alembic head + fail-closed verification, PH-1B |
| unknown-schema stamping | developer DB looks mostly current but is drifted | stamp would lie about columns/indexes/tables | critical | yes if strategy B used | verified adoption only, PH-1B |
| transaction ownership | 57 internal commits, no outer begin | partial operations and different isolation become visible | high | no | preserve deliberate boundaries; inventory tests PH-1C, redesign PH-10 |
| concurrent writers | SQLite serializes writers broadly | Postgres permits overlapping read/modify/write | high | no | race tests PH-1C; locks/retries PH-10 |
| unique/check-then-insert races | many app existence checks | `IntegrityError` frequency increases | high | no | verify/retry contracts PH-10 |
| incident correlation uniqueness | app-only bounded policy | duplicate active incident possible | high | no | concurrency contract PH-10; no naive unique key |
| timestamps/timezone | 134 ISO strings, legacy-naive compatibility | typed timestamptz would alter values/types | high | no if kept VARCHAR | preserve strings PH-1B; typed migration later with TC-3 gates |
| lexical time order | canonical UTC usually sortable | offset/legacy strings and collation can reorder | medium | no | parse critical comparisons; regression TC-3 |
| JSON/TEXT | 59 serialized `TEXT`; no SQL JSON queries | JSONB changes byte/duplicate/order semantics | high | no if kept TEXT | preserve all TEXT in 0001 |
| booleans | SQLite stores integer affinity | Postgres enforces Boolean | medium | no | representative migration tests |
| string length | SQLite ignores `VARCHAR(n)` length | Postgres rejects oversized values | high | no | profile and boundary tests PH-1C |
| long indexed identity | SQLite indexes long text flexibly | Postgres B-tree entry size can reject large multibyte values | high | no for empty baseline | representative max identity test PH-1C; domain redesign only if proven |
| collation/case | SQLite BINARY/order and ASCII-insensitive LIKE defaults | locale order and LIKE semantics differ | medium | no | deterministic tie-break ordering/canonical IDs; query tests PH-1C |
| NULL ordering | dialect default differs for ASC/DESC | recent/list order may move nulls | medium | no | test nullable ordered fields; add explicit null ordering later if needed |
| native enums | none | PG enums create deployment coupling | low | no | keep strings |
| foreign keys/cascades | none; references application-only | adding FKs can reject historical/orphan-compatible data | high | no | add none in PH-1B; lifecycle proof later |
| autoincrement | none | no difference | low | no | preserve string PKs |
| raw SQL | product none; evaluator SQLite-specific | evaluator SQL is not portable | low/product | no | keep evaluator SQLite |
| file/path assumptions | local default and evaluator copy files | Postgres is network service | medium | no | URL/driver/deployment configuration PH-1B/C |
| connection pool/liveness | engine defaults, no pre-ping | stale/network connections exist | high operational | no | PH-1C/PH-10 |
| test fixtures | 19 in-memory create-all modules; default fixture can hit dev DB | SQLite-only tests miss PG semantics | high | no | migration parity + targeted Postgres matrix PH-1B/C |
| plaintext secrets | webhook secret/headers stored directly | exposure risk exists on both dialects | critical security | not schema-foundation blocker | PH-4/PH-5; protect backups/logs meanwhile |

Postgres requires product-domain semantic changes for initial migration: **NO**. It requires careful preservation and later concurrency/security hardening, not a domain rewrite.

## 24. Exact PH-1B scope and non-goals

### Allowed/recommended PH-1B scope

1. Add reviewed Alembic and synchronous Postgres driver dependencies.
2. Add Alembic configuration, `env.py`, metadata wiring, and a single head.
3. Create revision 0001 reproducing the accepted 38-table schema exactly.
4. Test 0001 upgrade from empty SQLite and compare tables, columns, types, nullability, PKs, indexes, unique constraints, and FKs to metadata.
5. Test the initial downgrade only on a disposable database.
6. Add schema revision inspection and verified-adoption support; unknown/drifted existing schemas fail closed.
7. Separate production schema authority from intentional test/evaluation SQLite schema creation.
8. Add optional/new-Postgres migration execution when the environment exists; full Postgres runtime validation may continue in PH-1C.
9. Document operator upgrade/current/head commands and evaluation compatibility.

### Explicit PH-1B non-goals

No tenant ID, FK, cascade, check constraint, normalization, rename, old-table cleanup, JSONB/native JSON conversion, native Postgres enum, typed timestamp conversion, new correctness/performance index sweep, retention column/policy, RBAC/auth/secret redesign, provider schema redesign, concurrency rewrite, arbitrary SQLite-to-Postgres copy utility, evaluator rewrite, frozen-seed migration, or customer data migration.

Initial migration requires new FKs: **NO**. JSONB conversion: **NO**. Native PG enums: **NO**. Timestamp semantic changes: **NO**.

## 25. Rollback contract

- Revision 0001 `downgrade()` may drop all 38 Topo tables, constraints/indexes, and the Alembic version state **only on an explicitly disposable empty/test database created for migration verification**.
- It must be documented as destructive and never used as an operational rollback against customer data.
- Production operational rollback is backup/snapshot restore or application rollback to a version compatible with the upgraded schema, followed by a corrective forward migration when required.
- Migration downgrade correctness and safe production rollback are distinct. Future non-initial revisions should prefer backward-compatible expand/contract sequencing and tested backup restoration.

## 26. Schema verification contract

Minimum production architecture:

1. Deployment preflight runs `alembic upgrade head` with exclusive operational ownership.
2. CI proves `alembic heads` has one reviewed head and migration metadata matches the application expectation.
3. Production application startup checks current revision equals expected head and fails closed if absent, behind, ahead, or ambiguous. It performs no `create_all()` evolution.
4. Existing-schema stamp requires the exact fingerprint verifier described in §18 and an explicit operator action.
5. A later health/readiness surface may expose revision status without leaking credentials/schema details.

`alembic current` proves revision state, not absence of out-of-band drift. CI schema-parity tests and the adoption fingerprint provide the additional evidence.

## 27. Regression gates

### SQLite gates

- empty SQLite upgrade 0001 -> head;
- metadata/schema parity including exact names and zero FKs;
- downgrade on disposable SQLite only;
- all 19 current in-memory schema consumers;
- full backend suite;
- isolated evaluation backend startup and manual local default workflow;
- frozen seed pre/post hashes unchanged.

### Migration gates

- one Alembic head;
- deterministic upgrade from empty DB;
- current/head inspection;
- exact-schema verified adoption succeeds only when exact;
- developer DB drift fixture is rejected, not stamped;
- upgrade is idempotent through Alembic state;
- downgrade destroys only disposable fixture data and recreating/upgrading returns exact schema;
- autogenerate drift check produces no unexplained operations after 0001.

### Postgres gates

- empty Postgres upgrade to head and exact schema comparison;
- representative CRUD for all 38 ORM tables or table-family fixtures;
- JSON TEXT round-trip and payload byte preservation where authoritative;
- TC-3 timezone/legacy-naive behavior;
- string enum/Boolean behavior;
- deterministic ID and maximum representative length tests;
- unique/idempotency constraints and null-unique behavior;
- nullable ordering and recent-query behavior;
- intentional multi-commit change-source lifecycle;
- targeted concurrent creation/transition tests before production acceptance.

### Evaluation gates

LINEAGE source-to-runtime, TC-1 through TC-5/temporal and evidence ledger, blast-radius baselines, AR evidence preservation/gating, EAI artifact integrity, and SQLite broken-lineage/distractor scenarios must remain green without converting frozen seeds to Postgres.

## 28. Stop conditions and architecture blocker assessment

Stop PH-1B and report an architecture blocker if:

- revision 0001 cannot reproduce the 38-table metadata on empty SQLite;
- Postgres cannot create or accept representative accepted identifiers without a domain change;
- serialized payloads do not round-trip byte/semantically as required;
- TC-3 or TC-4 must be rewritten to use Postgres;
- an unknown customer/production database history is discovered;
- production schema authority cannot be separated from evaluation compatibility without weakening fail-closed behavior.

Current PH-1A architecture blocker: **NO**. Current ORM metadata exactly reproduces the frozen accepted schema, product SQL is portable, and known developer drift has no data in its three DB-only tables. The risks are explicit and testable.

## 29. PH-1B decision

Verdict: **GO**.

Exact next block: **PH-1B — Alembic Foundation + Current-Schema Baseline**.

PH-1B begins only after this document is reviewed. PH-1A does not install Alembic, add dependencies/configuration/revisions, change models/repositories/services/startup/URL behavior, modify any SQLite database, create Postgres, add FKs/indexes/tenant fields, or begin PH-2/CLOUD-V1-1.

## 30. Audit result capsule

| Item | Result |
|---|---|
| ORM tables / columns | 38 / 687 |
| ORM source | `backend/app/db/models.py` |
| composite PK / integer PK | 0 / 0 |
| string PK | 38 |
| FKs / checks | 0 / 0 |
| named multi-column unique constraints | 10 |
| column unique indexes | 9 |
| explicit `Index(...)` declarations | 0 |
| metadata index objects | 296 |
| logical reference-shaped fields | 95 (defined in §5) |
| JSON-shaped columns | 59, all `TEXT` |
| portable SQLAlchemy JSON | 0 |
| timestamp-shaped columns | 134, all `VARCHAR(50)` |
| SQLAlchemy DateTime timezone true/false | 0 / 0 |
| native SQL Enum | 0 |
| string enum-like/discriminator candidates | 91 |
| Boolean columns | 6 |
| unbounded Text columns | 101 |
| Python-side defaults / server defaults | 164 / 0 |
| direct product sqlite3/raw text SQL | 0 / 0 |
| transaction calls | 57 commits, 10 rollbacks, 3 flushes, 27 refreshes |
| developer DB | healthy SQLite, 41 tables, known current drift |
| frozen seed | healthy SQLite, exact ORM schema match |
| automatic arbitrary SQLite -> Postgres migration needed | NO |
| initial semantic/FK/JSONB/enum/timestamp conversion needed | NO / NO / NO / NO / NO |
| PH-1A blocker / verdict | NO / GO |

## 31. Validation and custody

Only this document is created. Product diff: none. Evaluator diff: none. Workflow diff: none. Migration files: none. Database files: unchanged as proven by matching hashes in §16.

Required final repository checks are `git status --short`, `git diff --name-only`, and `git diff --check`. The expected tracked diff is empty because the architecture document is untracked; expected status is exactly this one new document (apart from nonfatal local permission warnings while Git traverses ignored pytest-cache directories).

## 32. Stop confirmation

**STOP after PH-1A.** Do not begin PH-1B, PH-2, or CLOUD-V1-1; do not stage, commit, or push.
