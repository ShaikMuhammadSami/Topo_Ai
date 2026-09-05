# PH-5A — Issuer-aware principal identity, membership, and service migration v1

## Verdict and scope

`PASS`

PH-5A replaces raw-subject authorization identity with a durable internal
principal while preserving the accepted PH-1 persistence, PH-2 authentication,
PH-3 tenant isolation, PH-4 secret custody, agent authentication, provider
authentication, and causal/evidence foundations. It does not add permissions,
role bundles, durable security audit, enterprise OIDC, RLS, KMS, execution
authority, or HTTP routes.

Repository: `C:\Topo-ai`. Branch:
`security/ph-5a-issuer-aware-principal-identity-v1`. Accepted starting HEAD:
`2723e7c4eb4fce5247181ccd65343680a6e2acaa`
(`2723e7c test(security): close adversarial secret custody acceptance (#84)`).
The starting worktree was clean. No Git history or index mutation was
performed.

## Starting problem and forensic inventory

The old human authorization path was effectively authenticated subject to
tenant membership. Subjects are only meaningful inside their issuer, so the
same opaque subject from two issuers could not safely remain one durable
identity. A service credential was also too close to being treated as the
service identity itself, making rotation conceptually change the actor.

The final inventory searched production Python and TypeScript/JavaScript source
under `backend/app`, `cli/src`, `frontend`, and `agent/src` for exact
`subject`, `principal_id`, and `issuer` references. It found 305 matching source
lines (393 lexical token matches). Every line was reviewed by its dominant
security purpose:

| Classification | Source lines |
| --- | ---: |
| `AUTHENTICATION_SOURCE_IDENTITY` | 77 |
| `AUTHORIZATION_IDENTITY` | 104 |
| `DISPLAY_METADATA` | 20 |
| `AUDIT_METADATA` | 20 |
| `MACHINE_IDENTITY` | 20 |
| `LEGACY_COMPATIBILITY` | 64 |
| `UNKNOWN` | 0 |

The compatibility category consists of explicit legacy-local provisioning,
request/response compatibility, and preserved historical actor text. It is not
a membership lookup. Production runtime has zero
`TenantMembershipRecord.subject` queries, zero
`list_active_tenants_for_subject` calls, and zero subject fallback after a
principal lookup fails.

## Principal and external identity authorities

`auth_principals` is the security-global durable actor table. Its exact fields
are `principal_id`, `principal_type`, `display_name`, `status`, `created_at`, and
`updated_at`. IDs are random UUIDv4 values formatted as
`principal:<uuid4>`; they are not derived from issuer, subject, credential,
tenant, email, or display name. V1 types are exactly `human` and `service` and
statuses are exactly `active` and `disabled`.

`external_identities` maps a trusted human authentication identity to one
principal. Its exact fields are `external_identity_id`, `principal_id`,
`issuer`, `subject`, `status`, `created_at`, and `updated_at`. IDs are random
UUIDv4 values formatted as `identity:<uuid4>`. The exact, case-sensitive unique
authority is `(issuer, subject)`. Issuer and subject are bounded opaque values;
they are neither trimmed nor lowercased. Empty, oversized, outer-whitespace,
and control-character values are rejected.

The legacy human issuer is exactly `urn:topo:auth:legacy-local-v1`. The explicit
development-only issuer is `urn:topo:auth:development`. Existing static human
bearer identities provision through the legacy issuer. Development-disabled
mode provisions its development identity when the principal schema is
available; its process-random fallback exists only for explicit development
mode against a legacy/unavailable schema. An unknown production external
identity fails boundedly as `PRINCIPAL_NOT_PROVISIONED`; there is no implicit
email/display/subject merge and no generic identity-linking API.

`AuthPrincipal` now carries `principal_id`, `principal_type`, `display_name`,
`authentication_type`, roles retained from PH-2, and optional external issuer
and subject provenance. Its `subject` remains compatibility/display and
authentication provenance, never tenant authorization authority. The fields
are optional only for preserved, purpose-bound dormant system identities that
are not accepted by principal-based tenant authorization; human and service
application paths require a persisted active principal.

## Membership, session, and credential bindings

Final human membership authority is `(tenant_id, principal_id)`. The database
has a unique constraint on that pair, and all GET/list/context/mutation paths
query it using `principal_id`. One human principal can belong to multiple
tenants. `TenantContext` carries the durable `principal_id` plus
`authenticated_subject` solely as non-authoritative provenance for compatible
views and audit text.

Browser sessions persist `principal_id` and revalidate an active human
principal on every use. Named human API credentials persist `principal_id` and
authenticate directly to that human principal instead of re-resolving a raw
subject. Membership removal immediately denies an otherwise active session;
principal disablement denies sessions and both human and service credentials;
credential revocation remains an independent credential lifecycle operation.

A service principal is separate from its credentials:

```text
service principal
    -> one or more named service credentials
    -> existing fixed PH-3 tenant binding per credential
```

Credential rotation can retain the same service `principal_id`. The service
principal is row-locked while a credential is bound; existing bindings are
checked so concurrent or sequential attempts cannot bind that service
principal to a second tenant. No service principal is inserted into
`tenant_memberships`, and no `ExternalIdentity` is manufactured for services.
Legacy service credentials each receive their own service principal because no
safe persisted grouping authority existed.

Bootstrap tenant creation and recovery remain explicit PH-2 authorities. A
trusted static admin bearer is provisioned under the code-owned legacy issuer;
tenant creation binds the creator principal, and recovery requires the direct
static bearer plus explicit principal or explicit legacy-local subject. There
is no implicit installation-operator tenant membership.

Agents and providers remain purpose-bound machine identities. Enrollment and
steady-state agent tokens continue to derive machine tenant authority from the
agent record. Provider callbacks continue to verify the source secret and
derive the source-owned tenant. Neither path creates an `auth_principals`,
`external_identities`, or tenant-membership row, and neither inherits human or
service authority.

## Adversarial identity behavior

- Issuer A/subject X and issuer B/subject X produce distinct principal IDs.
- Repeating issuer A/subject X resolves the same semantic identity and
  principal, including concurrent PostgreSQL READ COMMITTED provisioning.
- Subject case is exact: `User123` and `user123` remain distinct.
- Same email-shaped subject across issuers remains distinct.
- Display-name collisions do not merge principals.
- The unique `(issuer, subject)` authority rejects external-identity
  reassignment.
- A human external identity cannot resolve through a service principal, and
  human/service credential type swaps fail closed.
- Cross-issuer tenant selection, session, and human-credential attacks cannot
  inherit the other issuer's membership or authority.
- Concurrent membership creation yields one membership.
- Concurrent cross-tenant service credential creation yields one accepted
  tenant authority and one rejection.

PH-2 `roles` are retained only for compatibility with the current
authentication/admin gates. They are not the PH-5 permission authority. PH-5A
introduces no permission vocabulary or execution permission.

## Migrations and persistence

Migration `0012_principal_identity_foundation.py`, revision
`0012_principal_identity`, parent `0011_secret_enforce`, creates exactly
`auth_principals` and `external_identities`, adds nullable principal foreign
keys/indexes to memberships, sessions, and credentials, then performs a
controlled backfill. One human principal and legacy external identity are
created per distinct valid legacy subject across those human records. One
service principal is created per legacy service credential. Invalid legacy
authority stops with `LEGACY_PRINCIPAL_IDENTITY_REVIEW_REQUIRED`; no guessed
issuer or grouping is used.

Migration `0013_principal_identity_enforcement.py`, revision
`0013_principal_enforce`, parent `0012_principal_identity`, validates complete
and type-correct bindings, makes all three principal foreign keys non-null,
removes `tenant_memberships.subject`, and replaces subject uniqueness/indexes
with `(tenant_id, principal_id)` authority. The final ORM is 47 tables and 819
columns. The only new tables are `auth_principals` and `external_identities`.
There is one Alembic head: `0013_principal_enforce`.

Downgrade `0013 -> 0012` reconstructs the legacy membership subject only when
every membership has an unambiguous legacy-local identity. Downgrade
`0012 -> 0011` is representable only when no non-legacy issuer exists.
Non-representable downgrade fails before destructive change with
`PRINCIPAL_IDENTITY_PREVENTS_DOWNGRADE`. Failed enforcement preflight remains
at 0012 without partial 0013 schema mutation.

Disposable SQLite proved fresh migration, populated legacy backfill, reuse of
one human identity across membership/session/human credential, separate
service backfill, multi-tenant principal membership, both representable
downgrades, non-legacy refusal, and re-upgrade. The controlled fixture backfill
created one human and one service principal; the algorithmic count is one human
per distinct legacy subject and one service per legacy service credential.

Disposable PostgreSQL 16 at READ COMMITTED proved fresh and populated
migration, ORM parity, re-upgrade, external-identity concurrency, membership
concurrency, stable service identity across two credentials, fixed-tenant
service concurrency, and failure atomicity. The task container was
`topo-ph5a-postgres-16`, image `postgres:16-alpine`, exact ID
`243bab5eed6ff72d4144289dd2c673da2134837506de49df1ba06f0eccac5be8`,
loopback `127.0.0.1:55446`, tmpfs
`/var/lib/postgresql/data:rw,noexec,nosuid,size=512m`, and `Mounts=[]`. It was
removed after verification; no persistent volume was used.

The existing PostgreSQL logical backup/restore regression was extended to
verify that principal, external-identity, and membership mappings survive the
restore. This is schema/identity proof only and does not claim PH-8 operational
backup closure.

## Custody

Canonical committed Git-content SHA-256 values for migrations 0001–0011 were
verified before and after PH-5A. Each migration has an empty Git diff:

| Migration | Before and after SHA-256 |
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

The unstaged working-file SHA-256 values are
`C5028EDB83D75542494619EEE267940955B54AC1A6284873A4A8A7C5A46F440D`
for 0012 and
`7388CBFD71B0EC35F945545B813BDB08D177C263AB34348E36449BF44DA91B29`
for 0013. They are recorded for review only and are not a staged or accepted
custody rebaseline.

Protected binary actual-byte hashes remained exact:

- Developer DB before/after:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- Frozen LINEAGE before/after:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

## Verification receipts

| Gate | Result |
| --- | --- |
| New SQLite principal/migration focused | PASS; principal runtime and migration modules green |
| New PostgreSQL principal/concurrency | 5 passed, 1 existing warning |
| PostgreSQL schema/runtime compatibility | 41 passed, 1 existing warning |
| PH-2/PH-3/PH-4/provider focused corpus | 236 passed, 75 expected skips, 2 warnings |
| Full backend default/SQLite | 1462 passed, 242 skipped, 2 warnings |
| Full backend PostgreSQL-enabled | 1694 passed, 10 skipped, 2 warnings |
| Full evaluation | 917 passed, 3 skipped |
| CLI compile / full suite | PASS / 81 passed |
| Agent compile / full suite | PASS / 24 passed, 1 platform skip |
| Frontend tests | 93 passed |
| Frontend typecheck | PASS |
| Frontend lint | PASS: 0 errors, 11 pre-existing warnings |
| Frontend production build | PASS: 14 routes; required one network-enabled retry for Google Fonts |
| PostgreSQL backup/restore | PASS; principal/identity/membership mappings restored |
| Scanner tests | 12 passed |
| Tracked-tree scanner | PASS, zero findings |
| New-file scanner | PASS, zero findings |
| Backend/evaluation/CLI/agent compile | PASS |
| Route taxonomy | 143 total: 116 tenant-required, 9 machine-bound, 7 tenant-control, 9 security-global, 2 public, 0 unknown |

The only backend warnings are the established Starlette/httpx deprecation and
the intentional SQLAlchemy duplicate-identity warning in a tenant adversarial
test. The frontend lint warnings predate PH-5A. No live provider or Kubernetes
operation was performed, and the causal/evidence evaluation result remained
unchanged.

## Limitations and PH-5B handoff

PH-5A is complete, but PH-5 is not. It intentionally provides no permissions,
four authority bundles, durable security/admin audit, identity-linking UI/API,
enterprise OIDC, agent/provider principal conversion, installation authority,
or execution authority. Legacy PH-2 roles remain temporary compatibility gates
and must not be treated as the future permission source.

PH-5B receives these stable authorities:

```text
human principal -> tenant membership
service principal -> one or more credentials -> one fixed tenant authority
agent -> fixed machine authority
provider -> fixed ingestion authority
installation operator -> human principal; separate installation authority later
```

The recommended next block is PH-5B — Minimum Permission Vocabulary + Four
Authority Bundles v1. It may add the small approved permission vocabulary and
bounded service permissions, but no execution authority. It was not started in
PH-5A.

PH-5A ACCEPTED / READY FOR ARCHITECT REVIEW
