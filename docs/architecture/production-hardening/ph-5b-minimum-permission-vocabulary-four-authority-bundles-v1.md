# PH-5B — Minimum permission vocabulary and four authority bundles v1

## Scope and verdict

PH-5B freezes Topo's minimum V1 authorization language and durable authority
assignments. It does not enforce the plan on every HTTP route; that is PH-5C.
The starting commit was `fd6821a44adec9ae9465fb470801baaee1eaade4` on
`security/ph-5b-minimum-permissions-authority-bundles-v1`.

The model has four code-owned authority bundles: Tenant Viewer, Tenant
Responder, Tenant Admin, and Installation Operator. A service principal has an
explicit permission allowlist and is not a fifth role. Agents and providers
retain their accepted fixed-purpose machine authority. No execution permission,
custom role, wildcard, subject-derived authority, or credential-derived service
authority was introduced.

## Permission vocabulary and immutable bundles

The exact tenant vocabulary is:

- `incident.read`, `incident.respond`
- `topology.read`, `evidence.read`, `report.read`
- `integration.read`, `integration.manage`
- `ownership.read`, `ownership.manage`
- `member.read`, `member.manage`
- `credential.metadata.read`, `credential.rotate`
- `tenant.settings.manage`

The exact installation vocabulary is `installation.status.read`,
`installation.bootstrap`, `installation.recovery`, and
`installation.secret.manage`. The sets are disjoint.

| Bundle | Exact permission set |
| --- | --- |
| `tenant_viewer` | `evidence.read`, `incident.read`, `integration.read`, `ownership.read`, `report.read`, `topology.read` |
| `tenant_responder` | Viewer plus `incident.respond` |
| `tenant_admin` | All 14 tenant permissions, enumerated explicitly |
| `installation_operator` | All four installation permissions, enumerated explicitly |

Viewer is a strict subset of Responder, which is a strict subset of Admin.
Admin is not a wildcard. Installation Operator receives no tenant permission,
and a tenant role receives no installation permission. Adding an enum member in
the future does not modify any role because mappings are immutable explicit
sets.

The exact service-assignable set is `evidence.read`, `incident.read`,
`incident.respond`, `integration.manage`, `integration.read`,
`ownership.manage`, `ownership.read`, `report.read`, and `topology.read`.
Services cannot receive `member.*`, `credential.*`,
`tenant.settings.manage`, any `installation.*`, or any execution authority.

## Durable assignments and resolution

Migration `0014_min_authority`, whose parent is
`0013_principal_enforce`, adds exactly two tables and one membership column:

- `tenant_memberships.role`: non-null `String(30)`, no Python or database
  default, with an exact check for `tenant_viewer`, `tenant_responder`, and
  `tenant_admin`.
- `service_principal_permissions`: principal-ID primary/foreign key,
  `permissions_json`, positive `row_version`, `created_at`, and `updated_at`.
  It deliberately has no `tenant_id`; the accepted PH-3 service credential
  bindings remain the tenant authority.
- `installation_operator_assignments`: human principal-ID primary/foreign key,
  exact active/disabled status, `created_at`, and `updated_at`. It deliberately
  has no `tenant_id`.

The resulting ORM/schema contract is 49 tables, 829 columns, and seven foreign
keys. Existing memberships are backfilled to `tenant_admin` because those rows
previously had broad compatibility authority. Existing service principals,
including credentialless services, receive one canonical assignment containing
the exact nine service-assignable permissions. Multiple credentials for the
same service still resolve one principal assignment. No installation operator
is inferred from legacy role strings, memberships, subjects, display names, or
credentials.

Fresh tenant bootstrap explicitly creates its first membership as
`tenant_admin`; it does not automatically grant Installation Operator. Ordinary
membership creation and bounded recovery require an exact role. Reactivation
keeps the same membership/principal identity while accepting the explicit new
role. An active membership cannot be silently changed by replaying the create
operation with a different role.

New service-principal credential creation requires an explicit nonempty
allowlist and atomically persists principal, permission assignment, credential,
and fixed tenant binding. Another credential for an existing service uses its
existing assignment; omitted permissions are accepted, an identical explicit
set is harmless, and a different set is rejected. Credential revocation does
not alter service authority or tenant binding. A separate internal CAS
replacement primitive increments `row_version` and rejects stale writers.

Permission JSON must be a bounded, sorted, unique, compact array of exact
allowed strings. Unknown, forbidden, duplicate, empty, non-list, non-string,
non-canonical, or oversized input/stored state fails closed.

The three resolvers are principal-ID and scope specific:

1. Human tenant resolution requires an active human principal, active tenant,
   active membership, and exact stored `membership.role`.
2. Service resolution requires an active service principal and its single valid
   durable permission assignment. PH-3 separately proves the fixed tenant.
3. Installation resolution requires an active human principal and an active
   explicit installation assignment; it never asks for a tenant.

The resolvers do not union scopes and never use `AuthPrincipal.roles`, subject,
display name, static-token role text, agent role, or provider role as PH-5
authority. Current database state is re-read so disabled principals,
memberships, or operator assignments and changed service/role assignments do
not remain effective through a held ORM identity map.

Local deployment administration is available only as
`python -m app.installation_operator_admin status|grant|disable <principal_id>`.
It accepts an exact durable human principal ID, returns bounded non-secret
output, creates no HTTP route, and allows explicit revocation even after a
principal is disabled. Local deployment access is the custody boundary for the
first assignment.

## Authorization surface inventory

The live HTTP inventory remains exactly 143 routes. Every method/template has
one immutable plan entry; duplicates and unknowns are zero.

| PH-5B plan class | Routes |
| --- | ---: |
| `PUBLIC` | 2 |
| `AUTHENTICATION_SELF_SERVICE` | 7 |
| `TENANT_PERMISSION` | 109 |
| `INSTALLATION_PERMISSION` | 2 |
| `AGENT_FIXED_PURPOSE` | 8 |
| `PROVIDER_FIXED_PURPOSE` | 1 |
| `V1_DORMANT_EXECUTION_DENY` | 10 |
| `AUTHENTICATOR_CREDENTIAL_POLICY` | 4 |

This reconciles exactly with the accepted PH-3 taxonomy: 116 tenant-required,
nine machine-bound, seven tenant-control, nine security-global, and two public.

The seven tenant-control routes plan as follows: create tenant is
`installation.bootstrap`; recover membership is `installation.recovery`; list
the caller's tenants and resolve selected tenant context remain authentication
self-service; membership list is `member.read`; membership add/reactivate and
disable are `member.manage`.

Of the nine security-global routes, session create/get/delete, `whoami`, and the
fixed synthetic sample topology remain authentication self-service. The four
global API-credential routes use the architect-approved narrow
`AUTHENTICATOR_CREDENTIAL_POLICY`; it is not a Permission, role, authority
bundle, or generic escape hatch.

That policy freezes eight target branches. A human credential is self-owned by
exact caller principal for create/list/get/revoke and tenant membership grants
no cross-principal access. A service credential requires an authenticated human,
a validated selected tenant, `credential.metadata.read` for list/get or
`credential.rotate` for create/revoke, and the accepted same-tenant service
binding. Foreign IDs are 404. Raw secret delivery occurs only once at authorized
creation. Installation Operator grants neither branch authority. The existing
broad PH-2 human-admin gate remains explicitly `LEGACY_COMPATIBILITY` until
PH-5C replaces it comprehensively.

The machine mapping remains eight enrolled-agent routes plus one verified
provider callback. Machine ingestion must propagate only the already-proven
fixed principal/source binding; a caller-provided tenant is never authority.

The critical non-HTTP registry contains 98 exact operation/context entries:
65 tenant-permission, eight installation-permission, eight self-service, five
agent-fixed-purpose, one provider-fixed-purpose, and 11 dormant execution-deny.
This represents 90 reviewed production entrypoints plus eight target-specific
credential contexts. Delegated automatic ingestion callers are explicit; their
names are not an authentication bypass and PH-5C must prove their source.

Combined change-source/webhook credential mutations require all of
`integration.manage` and `credential.rotate`. Metadata views that expose secret
status require all of `integration.read` and `credential.metadata.read`.
Incident response, topology/evidence/report/ownership/membership, tenant
settings, installation secret/bootstrap/recovery, agent, provider, and
authentication operations map to the corresponding exact permission or fixed
trust domain in the registry.

All ten approval/execution-intent routes and all 11 underlying mutating or
refreshing approval/execution operations are V1 dormant-deny. GET/list is also
denied because those services refresh and persist active status. Read-only
execution-readiness evidence remains `evidence.read`. No execution permission
exists.

## Migration, concurrency, and custody

Migration tests cover fresh and populated SQLite/PostgreSQL 16 databases,
physical role constraints, exact backfills, no installation inference,
disposable downgrade/re-upgrade, migration atomicity, metadata/ORM parity, and
PostgreSQL READ COMMITTED behavior. Downgrade to 0013 deliberately discards
PH-5B authorization metadata and is supported only for disposable rollback
proofs; no authority is encoded into legacy roles.

PostgreSQL tests prove one-winner service assignment CAS, idempotent concurrent
operator grant, no lost update, and exact backup/restore of membership role,
service permission JSON/version, and operator assignment.

Canonical committed Git-content SHA-256 custody values for migrations
0001–0013 are unchanged:

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

The developer database actual-byte SHA-256 remains
`0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
The frozen LINEAGE product database actual-byte SHA-256 remains
`9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.
No protected migration or database is modified or rebaselined.

## Verification receipts

All PH-5B acceptance gates completed successfully:

- authority policy/resolver: 59 passed;
- authority creation and atomicity: 22 passed, one existing warning;
- authorization route/operation plan: 21 passed, one existing warning;
- combined focused PH-5B SQLite coverage: 112 passed, one existing warning;
- focused PostgreSQL authority: 20 passed, one existing warning;
- full backend default/SQLite: 1,574 passed, 262 skipped, two existing warnings;
- full backend with PostgreSQL 16 enabled: 1,828 passed, eight skipped, two
  existing warnings in 1,140.15 seconds;
- PH-2 regression: 76 passed, one existing warning;
- PH-3 regression: 177 passed, 74 skipped, two existing warnings;
- PH-4 regression: 130 passed, 75 skipped, one existing warning;
- PH-5A regression: 13 passed;
- provider/agent authentication regression: 17 passed, one existing warning;
- evaluation: 917 passed, three skipped;
- CLI: 85 passed;
- agent: 24 passed, one platform skip;
- scanner tests: 12 passed plus 14 subtests;
- tracked-tree secret scan: zero findings; and
- backend, CLI, agent, and evaluation compile gates: passed.

The two backend warnings are the pre-existing Starlette `httpx` deprecation
and SQLAlchemy identity-map warning in the adversarial same-identifier tenant
test. Neither is an authorization failure. Migrations 0001–0013 have no Git
diff. Both protected database files retain the accepted actual-byte SHA-256
values recorded above.

## PH-5C handoff

PH-5C receives these frozen flows:

```text
Human:       principal -> tenant membership role -> code-owned bundle
Service:     principal -> explicit permissions -> credential -> fixed tenant
Installation: human principal -> explicit operator assignment -> code-owned bundle
Agent:       authenticated fixed purpose and tenant/scope binding
Provider:    verified fixed purpose and persisted source tenant binding
```

PH-5C must enforce the complete route and service plan without reinventing
permissions, roles, wildcards, custom roles, execution authority, or a generic
credential escape hatch. It must replace the four credential routes' legacy
broad gate with human self-service and human same-tenant service-target logic.
Durable PH-5 audit is also not implemented in PH-5B.

PH-5B ACCEPTED / READY FOR ARCHITECT REVIEW
