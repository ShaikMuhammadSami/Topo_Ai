# PH-5D — Minimum Durable Security/Admin Audit v1

## Decision

PH-5D adds one narrow, durable security/admin evidence ledger. It records who
performed or attempted a supported security-sensitive operation, the trusted
authority and optional tenant under which the decision was made, the exact
permissions relevant to the decision, a safe resource reference, and whether
the operation completed or was denied.

This is not application observability, an incident activity log, a SIEM,
analytics, compliance reporting, external log shipping, a WORM store, a hash
chain, or a retention system. PH-10 remains responsible for operational
observability and PH-7 must define retention/deletion behavior. A database
superuser remains outside the V1 application-level append-only threat model.

Starting authority: commit `f699deea0eb71d7b54b5cd4cc38319e9fd705a6f`
(`f699dee feat(security): enforce route and service authorization (#87)`) on
`security/ph-5d-durable-security-admin-audit-v1`.

## Forensic operation inventory

The frozen PH-5C operation plan remains the authority source. All 98 operations
are classified and `UNKNOWN` is zero:

| Classification | Count | Meaning |
| --- | ---: | --- |
| `AUDIT_ALLOWED_PRIVILEGED_MUTATION` | 22 | Successful current security/admin mutations |
| `AUDIT_ALLOWED_SECURITY_READ` | 4 | Credential/installation security metadata reads |
| `AUDIT_AUTHORIZATION_DENIAL` | 11 | Dormant execution operations whose authenticated rejection is recorded |
| `OUT_OF_SCOPE_MINIMUM_AUDIT` | 60 | Ordinary product, incident, evidence, ingestion, or authentication lifecycle work |
| `NONATOMIC_OPERATOR_ACTION` | 1 | Historical local legacy-secret conversion |

The denial reason families are `missing_permission`, `wrong_authority_kind`,
`membership_missing`, `service_permission_missing`,
`credential_target_denied`, `execution_disabled`, and `unknown_operation`.
The route registry remains exactly 143 routes with zero new, duplicate, or
unknown routes. The operation registry remains exactly 98 operations. PH-5B
permissions and role bundles are unchanged; there are still zero execution
permissions.

## Persistence contract

Migration `0015_security_admin_audit.py` has revision
`0015_security_audit`, parent `0014_min_authority`, and is the single Alembic
head. It creates only `security_audit_events`. The final ORM contains 50 tables
and 844 columns.

The table has exactly these 15 fields:

1. `audit_event_id`
2. `occurred_at`
3. `actor_principal_id`
4. `actor_kind`
5. `actor_reference`
6. `authentication_type`
7. `authority_kind`
8. `tenant_id`
9. `action`
10. `permissions_json`
11. `resource_type`
12. `resource_id`
13. `result`
14. `reason_code`
15. `request_id`

IDs are server-created `audit:<uuid4>` values and timestamps are server-created
UTC values. The four indexes are `(tenant_id, occurred_at)`,
`(actor_principal_id, occurred_at)`, `(action, occurred_at)`, and `request_id`.
There is deliberately no physical foreign key to a principal, tenant, or
resource: historical security evidence must survive resource disablement or
deletion without cascade loss. There is no generic metadata/payload/details
JSON column.

The supported repository API is append-only. It exposes no update, patch,
delete, or upsert operation, and PH-5D adds no read/export HTTP route, frontend,
or remote CLI. The claim is application-level append-only behavior, not
database-superuser resistance or cryptographic immutability.

## Trusted event construction

One central service validates and constructs events. It rejects control
characters, enforces field bounds without silent truncation, accepts only
code-owned action/reason/resource values, and canonicalizes permissions as a
compact, sorted, unique JSON array of known PH-5B permission codes. It never
accepts a request body, exception object, arbitrary URL, subject, display name,
role, header, cookie, token, or secret material.

Actor representation is derived only from accepted PH-5 contexts:

- Human and service actors use their durable issuer-aware `principal_id`, with
  no subject/display name/role copied into the ledger.
- Agent events use a null principal and a server-verified durable agent or
  enrollment-record reference.
- Provider events use a null principal and the verified server-side source
  record reference; unverified provider payloads cannot create authority.
- Local operator events use a null principal and null actor reference rather
  than guessing an OS identity.

Authority kinds are `authentication_self_service`, `human_tenant`,
`service_tenant`, `installation`, `agent_fixed_purpose`,
`provider_fixed_purpose`, and `local_operator`. Actor kinds are `human`,
`service`, `agent`, `provider`, and `local_operator`. Results are exactly
`allowed` or `denied`.

`tenant_id` is the exact validated tenant for tenant authority, null for global
human self-authentication and installation/local work, and is never inferred
from resource text. `request_id` remains null because the current server has no
trusted request-ID middleware; PH-5D does not promote caller-controlled headers
to correlation authority.

## Frozen action and reason registries

The exact 33 action codes are:

- `authorization.denied`, `execution.denied`
- `tenant.created`
- `tenant_membership.created`, `tenant_membership.reactivated`,
  `tenant_membership.disabled`, `tenant_membership.recovered`
- `change_source.created`, `change_source.updated`
- `webhook_endpoint.created`, `webhook_endpoint.updated`
- `ownership_mapping.upserted`
- `identity_override.upserted`, `identity_override.deactivated`
- `api_credential.human.created`, `api_credential.human.revoked`
- `api_credential.service.created`, `api_credential.service.revoked`,
  `api_credential.service.listed`, `api_credential.service.inspected`
- `service_permissions.updated`
- `agent_enrollment_token.created`, `agent.enrolled`, `agent.revoked`
- `installation_operator.granted`, `installation_operator.disabled`,
  `installation_operator.inspected`
- `installation_secret.inspected`, `installation_secret.set`,
  `installation_secret.reprovisioned`, `installation_secret.rotated`,
  `installation_secret.imported`, `installation_secret.revoked`

The exact 11 reason codes are `completed`, `missing_permission`,
`wrong_authority_kind`, `principal_inactive`, `membership_missing`,
`service_permission_missing`, `installation_assignment_missing`,
`credential_target_denied`, `execution_disabled`, `unknown_operation`, and
`resource_unavailable`.

## Transaction and denial semantics

For an ordinary DB-backed privileged mutation, the service first performs the
business change in the caller-owned transaction, appends the allowed event in
that same transaction, and then uses the existing single commit. Audit insert
failure rolls back the mutation. Business failure produces no false allowed
event. Services do not commit inside the central audit append.

An authorization denial has no successful business transaction. Central PH-5C
enforcement writes one denial through a short independent transaction before
returning the existing denial. Request-scoped suppression prevents a route and
its service from recording duplicate semantic denials. Direct trusted service
calls can supply the independent writer explicitly. If denial persistence
fails, the operation remains denied and the only operational log is the
bounded code `SECURITY_AUDIT_WRITE_FAILED action=<code>`; exceptions and
payloads are not stringified. Audit failure can never grant authority.

The request-scoped authorization context is consumed for successful events only
inside an active audited request. This prevents stale context from legacy or
direct test/service calls being mistaken for a current actor. Explicit typed
contexts remain supported at trusted fixed-purpose boundaries.

## Covered successful operations

- Membership create, reactivate, disable, and installation recovery use
  `member.manage` or the relevant installation permission and store only safe
  membership/principal identifiers. There is no current supported active
  membership role-change operation: attempting a different role for an active
  membership is rejected, so no speculative role-change action was added.
- Change-source/provider and webhook create/update use the existing
  `integration.manage` plus `credential.rotate` contract when a secret changes.
  No URL, protected header, provider payload, or credential is recorded. The
  current webhook surface has no delete/disable endpoint, so none was invented.
- Ownership mapping and identity override changes record only safe IDs and the
  exact management permission.
- Human credential create/revoke is global authenticator self-service. Service
  credential create/revoke is performed by validated same-tenant human
  authority. Service credential list/get is classified as a security-sensitive
  read and records `credential.metadata.read`. Raw credentials and digests are
  never audit fields.
- Service permission assignments record `service_permissions.updated` without
  copying a role or arbitrary permission payload.
- Enrollment-token creation, verified agent enrollment, and agent revocation
  are covered. Heartbeats, snapshots, telemetry, and runtime events remain out
  of scope. There is no current enrollment-token revoke operation.
- Installation operator grant/disable/status and installation SecretStore
  status/set/reprovision/rotate/import/revoke are recorded at the local operator
  boundary without key or secret material. No root-rewrap command exists in the
  current product, so none was fabricated.
- Tenant creation and membership recovery are the current truthful
  bootstrap/recovery events. There is no separate mutable tenant-settings route
  in the current V1 surface; no setting values or speculative action were added.

The legacy secret conversion operation is explicitly
`NONATOMIC_OPERATOR_ACTION`. It historically runs at migration 0010, before
this ledger exists, and commits object conversions independently. PH-5D neither
rewrites that historical migration nor falsely claims current-head atomic audit
for it. Local root-key/filesystem recovery must remain possible when the audit
database is unavailable; an already completed external side effect cannot be
rolled back by a later audit failure.

## Authorization and masking preservation

The global PH-5C guard records authenticated 403 decisions, including missing
permission, wrong authority kind, forbidden service administration, authority
separation, unknown guarded operation, and V1 execution-disabled decisions.
The representative test matrix covers viewer/responder/tenant-admin/operator,
service, machine fixed-purpose, and dormant execution decisions through the
same central guard/service enforcement; the dedicated route proof confirms a
viewer admin denial and an execution-disabled denial each produce exactly one
event. Direct trusted service denial is independently durable.

Unauthenticated or invalid/expired-credential failures remain 401 and create no
trusted-actor audit event. Foreign and nonexistent resource/credential probes
retain the same masked 404 contract. PH-5D deliberately leaves these masked
404s outside the durable ledger rather than persisting evidence that could
confirm foreign existence; both therefore produce no audit row and remain
semantically equivalent.

No execution or approval route became reachable. An authenticated access to a
dormant execution operation records only `execution.denied` with
`execution_disabled`; it never stores the dormant request payload.

## Secret and redaction proof

Hostile token, provider-secret, database-password, protected-header,
SecretStore-material, and credential-bearing URL markers were exercised. The
security ledger contained zero secret markers and zero raw URL credentials.
Injected writer exceptions containing hostile material produced zero secret
markers in audit logs or public authorization errors. The existing PH-4
redaction and verify-before-parse boundaries are unchanged.

The secret scanner remains unchanged. Its 12 tests pass, the tracked-tree scan
passes, and a separate scan of all untracked PH-5D files passes.

## Migration, concurrency, and restore proof

SQLite proves a fresh upgrade to the single head with exact ORM parity, a
populated 0014-to-0015 upgrade that preserves existing records and begins with
an empty ledger, destructive downgrade/reupgrade behavior for the new ledger
only, and the append-only application API.

Real PostgreSQL 16.15, loopback-only with tmpfs storage and no persistent
volume, proves fresh and populated migration, exact indexes/schema, concurrent
unique event appends with UTC timestamps, same-transaction allowed mutation
atomicity, independent denial durability after the request transaction closes,
denial-writer failure without privilege gain, and logical dump/restore with the
exact existing audit row and no synthesized event. The disposable container
was removed after testing.

## Regression results

- Focused SQLite audit model/service/routes: 17 passed; migration proofs: 4
  passed. These are also included in both full backend runs.
- Focused PostgreSQL PH-5D audit: 6 passed.
- Full backend SQLite: 1603 passed, 270 skipped, 2 warnings in 581.66 seconds.
- Full backend PostgreSQL-enabled: 1865 passed, 8 skipped, 2 warnings in
  1346.66 seconds.
- Full evaluation: 917 passed, 3 skipped in 65.28 seconds.
- Significant GitHub/source-to-runtime lineage: 294 passed in 13.67 seconds.
- Mocked LLM/briefing/history: 105 passed, 1 existing warning in 15.23 seconds;
  no live LLM call was made and audit data is not sent to an LLM.
- CLI: 85 passed, 0 failed, 0 skipped in 3.856 seconds.
- Agent: 25 tests, 0 failures, 1 skip in 5.669 seconds.
- Frontend configured tests: 93 passed, 0 failed/skipped in 384 ms. Frontend
  code is unchanged, so no audit viewer or export UX exists.
- Backend, evaluation, CLI, and agent compile checks pass.

The two full-backend warnings are the pre-existing Starlette TestClient
deprecation and a pre-existing SQLAlchemy identity-map warning in the
same-session tenant adversarial rollback test. There are no test failures.

## Custody

Committed Git-blob SHA-256 values for migrations 0001 through 0014 remain:

| Migration | SHA-256 |
| --- | --- |
| 0001 | `B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD` |
| 0002 | `DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92` |
| 0003 | `907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F` |
| 0004 | `D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3` |
| 0005 | `14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333` |
| 0006 | `D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728` |
| 0007 | `8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84` |
| 0008 | `9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7` |
| 0009 | `20B1109D75E78F511B346F1D85DA8FA7FB9F6CAA8B8A92347A2859BA2D35CA5C` |
| 0010 | `4303D0826DCE3E8FB0750A376CB68B8ABCBA7E1D62296BEE23A1782EAA3EDCF4` |
| 0011 | `15E89A6B4BDF00FC7334E7A7D0128251B378803A98771700066568683F234DF8` |
| 0012 | `C5028EDB83D75542494619EEE267940955B54AC1A6284873A4A8A7C5A46F440D` |
| 0013 | `7388CBFD71B0EC35F945545B813BDB08D177C263AB34348E36449BF44DA91B29` |
| 0014 | `864328578509AEA48B28F2FE6B705DA3D8F609424C553DB9B0070253B751BC9F` |

There is no diff for migrations 0001–0014. Protected binary hashes remain:

- Developer database:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`
- Frozen LINEAGE database:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`

## PH-5E handoff

PH-5E receives issuer-aware principals, frozen roles/permissions, complete
route/service enforcement, fixed-purpose machine authority, target-aware
credential policy, and this durable minimum security/admin audit ledger. PH-5E
must perform the adversarial authorization/audit closure; PH-5D does not begin
that work and does not claim PH-5 as a whole is complete.

PH-5D ACCEPTED / READY FOR ARCHITECT REVIEW
