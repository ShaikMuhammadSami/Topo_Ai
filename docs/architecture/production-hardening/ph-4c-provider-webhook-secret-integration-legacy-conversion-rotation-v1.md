# PH-4C — Provider and webhook secret integration, controlled legacy conversion, and rotation v1

## Scope, authority, and verdict

Repository: `C:\Topo-ai`. Branch:
`security/ph-4c-provider-webhook-secret-integration-v1`. Accepted starting HEAD:
`16f2f95d996d4793598447ca1223c43aaca3fbde`
(`feat(security): add encrypted secret store foundation (#81)`). The starting
worktree was clean.

PH-4C integrates the existing inbound change-source credentials and outbound
customer webhook credentials with the PH-4B encrypted `SecretStore`. It also
provides a controlled, operator-run conversion from the legacy environment-name
and plaintext webhook representations, bounded inbound rotation, active-only
outbound replacement, typed non-secret provider configuration, and write-only
secret API inputs.

This block does not migrate OpenAI, Groq, installation GitHub outbound, database,
CLI-local, agent-local, or cloud-SDK credentials. It does not change one-way
authentication digests, tenant authority, canonical identity, causal/evidence
semantics, or execution behavior. PH-4 is not closed; PH-4D and PH-4E remain.

## Final architecture

```text
Human source/webhook write
  -> authenticated TenantContext
  -> typed non-secret configuration and URL/header policy
  -> server-derived SecretBinding(tenant, owner, purpose)
  -> caller-owned transaction
       -> SecretStore put/rotate/reprovision/revoke
       -> opaque domain reference update
  -> metadata-only response

Inbound provider delivery
  -> exact tenant-bound source locator
  -> authorized active/unexpired-previous SecretStore material
  -> verify raw request
  -> parse and persist bounded non-authentication evidence

Outbound webhook delivery
  -> exact tenant-bound endpoint
  -> authorized active-only signing/header material
  -> transient request construction
  -> bounded type-only delivery result
```

There is no public SecretStore route and no client-selectable scope, owner,
purpose, key ID, material version, or secret reference. Existing source and
webhook routes are changed in place; no route is added.

## Persistence and staged migration

PH-4C creates exactly two migrations and no table:

| Stage | Revision | Parent | Purpose |
| --- | --- | --- | --- |
| 0010 | `0010_secret_refs` | `0009_secret_store` | Add conversion-only webhook reference/name fields while retaining legacy columns |
| 0011 | `0011_secret_enforce` | `0010_secret_refs` | Validate converted bindings/config, constrain source refs, and remove webhook plaintext columns |

The final Alembic graph has one head: `0011_secret_enforce`. The final ORM has
45 tables and 804 columns.

Final `change_sources` custody:

- `secret_ref` is nullable `String(64)` and is either NULL or an opaque
  `secret:<uuid4>` reference.
- An enabled source must have a non-NULL reference.
- The provider and GitLab authentication mode determine the exact server-owned
  purpose. Raw material and environment names are not domain data.

Final `webhook_endpoints` custody:

- `signing_secret_ref`: nullable opaque reference.
- `protected_headers_secret_ref`: nullable opaque reference.
- `protected_header_names_json`: non-secret names metadata only.
- Legacy `signing_secret` and `headers_json` columns are physically absent.

The 0011 preflight is metadata-only. It refuses unconverted environment names,
plaintext webhook values, enabled sources without a credential, invalid/foreign
bindings, untyped legacy provider configuration, mismatched protected-header
names, and credential-bearing webhook URLs. Alembic never reads environment
secret values, decrypts material, or infers tenant/owner authority.

Normal application startup requires the final schema head. An installation left
at 0010 is intentionally unavailable except through the conversion utility.

### Downgrade behavior

Downgrading 0011 to 0010 recreates empty legacy webhook columns; it does not
decrypt or export credentials. Downgrading 0010 to 0009 succeeds only when no
source or webhook SecretStore consumer reference exists. A converted database is
refused with `SECRET_CONSUMER_REFERENCES_PREVENT_DOWNGRADE`. Operators should use
backups and a forward fix rather than expect plaintext reconstruction.

## Operator conversion procedure

The safe populated-installation sequence is:

```powershell
Set-Location C:\Topo-ai\backend

# 1. Stop normal application processes and back up the database and root-key custody separately.
& .\.venv\Scripts\alembic.exe upgrade 0010_secret_refs

# 2. Review a strict absolute-path manifest; dry-run is the default.
& .\.venv\Scripts\python.exe -m app.secret_conversion_admin `
  --manifest C:\secure-operator-input\topo-ph4c-conversion.json

# 3. Make the required legacy environment values available only to this process,
#    configure the accepted PH-4B encrypted store/keyring, then apply.
& .\.venv\Scripts\python.exe -m app.secret_conversion_admin `
  --manifest C:\secure-operator-input\topo-ph4c-conversion.json --apply

# 4. Re-run dry-run for an idempotency receipt, then enforce and start normally.
& .\.venv\Scripts\python.exe -m app.secret_conversion_admin `
  --manifest C:\secure-operator-input\topo-ph4c-conversion.json
& .\.venv\Scripts\alembic.exe upgrade 0011_secret_enforce
```

The manifest is a versioned owner-selection document, never a secret-value file:

```json
{
  "version": 1,
  "sources": [
    {
      "tenant_id": "tenant:example",
      "source_id": "source:example",
      "expected_provider": "gitlab",
      "expected_auth_mode": "signing",
      "expected_legacy_env_name": "TOPO_LEGACY_GITLAB_SIGNING",
      "action": "import"
    }
  ],
  "webhooks": [
    {
      "tenant_id": "tenant:disabled-example",
      "webhook_id": "webhook:disabled-example",
      "action": "discard_and_disable"
    }
  ]
}
```

The converter requires an absolute, bounded regular file with no symlink/reparse
path component, rejects duplicate JSON keys and duplicate object identities, and
requires database revision exactly `0010_secret_refs`. It matches row identity,
tenant, provider, optional auth mode, and exact legacy environment name before
calling `getenv`. It never enumerates the environment. A cross-tenant or
environment-oracle manifest therefore fails before material access.

Each object converts in its own transaction under a row lock. Operation IDs are
deterministic non-secret owner/purpose hashes, making completed conversion
rerunnable without deriving identity from secret bytes. Dry-run neither reads
secret values nor mutates data. A failed object rolls back its SecretStore and
domain changes together.

Active-tenant legacy sources may be imported. An inactive/disabled owner is not
temporarily re-enabled: legacy material must be explicitly
`discard_and_disable`, which clears the legacy reference and leaves the source
disabled. Active-tenant webhook plaintext signing values and the complete custom
header map are converted directly from their controlled database rows. A disabled
owner with legacy webhook values requires an explicit manifest discard entry;
discard clears the values/references and disables the endpoint. Unknown or
credential-like legacy config, invalid URLs/headers, inconsistent pre-existing
references, or missing environment material fail closed for operator review.

## Exact consumer bindings and lifecycle

| Consumer | Server-derived purpose | Runtime versions |
| --- | --- | --- |
| GitHub | `change_source.github_hmac` | active plus at most one unexpired previous |
| GitLab signing | `change_source.gitlab_signing` | active plus at most one unexpired previous |
| GitLab shared token | `change_source.gitlab_shared_token` | active plus at most one unexpired previous |
| HCP Terraform | `change_source.terraform_hmac` | active plus at most one unexpired previous |
| Jenkins | `change_source.jenkins_hmac` | active plus at most one unexpired previous |
| Azure DevOps Basic password | `change_source.azure_basic_password` | active plus at most one unexpired previous |
| Webhook signing | `webhook_endpoint.signing` | active only |
| Webhook custom headers | `webhook_endpoint.protected_headers` | active only |

Inbound rotation defaults to zero overlap and is capped at 86400 seconds. Exact
expiry removes previous material; a second rotation immediately evicts anything
older than the immediately previous value. Revoke immediately makes the binding
unusable and clears overlap. An explicit bounded `reprovision` extension supports
revoked-to-active configuration on the same stable logical reference using fresh
material, a new version, CAS, a stable operation ID, and no previous material or
overlap. Revoked material never becomes usable again.

A GitLab `secret_token`/`signing` purpose transition requires a new credential in
the same atomic update. The service creates the new purpose-bound secret, changes
the source binding, and revokes the old binding in one caller-owned transaction;
it never relabels ciphertext.

Externally retryable mutations require `Idempotency-Key` and use a stable
non-secret operation hash. Same operation and same material is idempotent; a
conflicting retry is rejected. SecretStore mutators contain no commit. Injected
source/webhook create and update failures prove that domain and credential state
roll back together.

## Provider verification and evidence boundary

The six mechanisms retain their established algorithms: GitHub HMAC, GitLab
signing, GitLab shared token, Terraform HMAC, Jenkins HMAC, and Azure DevOps Basic
password. The source is located and SecretStore binding authorized before raw
request authentication. Parsing and persistence happen only after verification.
No payload tenant selector or `X-Topo-Tenant-ID` participates.

Bad signatures, missing/revoked/expired/foreign credentials, disabled sources,
and inactive tenants expose the same generic authentication failure. A global
SecretStore configuration/decryption outage exposes only a generic service-
unavailable response. No response or ordinary log identifies active versus
previous material, version, key ID, reference, tenant secret status, or decrypt
detail.

New receipt evidence excludes authentication-value headers including
Authorization and provider signature/token/HMAC proofs. Delivery/event IDs,
event type, and bounded timestamp metadata may remain. Dead-letter replay remains
an authorized replay of an already authenticated receipt and does not retrieve or
reverify provider material or extend overlap.

There is zero final provider runtime behavior equivalent to
`os.getenv(source.secret_ref)` and no plaintext/environment fallback.

## Typed provider configuration

Unknown fields are forbidden. The exact common fields are `environment`,
`cluster_name`, `namespace`, and bounded `entity_refs`. Provider additions are:

- GitHub: bounded `source_file_capture` limits.
- GitLab: `auth_mode` and `signature_max_age`.
- Jenkins: common fields only.
- Azure DevOps: `username`.
- Terraform Cloud: `provider`.

Filters are limited to `event_types`, `repositories`, and `environments`.
Credential-like unknown config cannot become an alternate persistence path.
GitLab signing age defaults to 300 seconds and cannot exceed 3600 seconds.

## Outbound webhook custody

Signing material is stored only under its SecretStore reference. The complete
custom header map is serialized as canonical UTF-8 JSON:

```json
{"headers":{"Authorization":"Bearer <protected>"},"version":1}
```

Only header names are kept as domain metadata and returned to callers. Header
values never appear in normal create/update/read/list/test responses or browser
state. Up to 32 unique case-insensitive names are accepted; names, values, and
the encrypted bundle are bounded. HTTP transport and Topo-owned headers such as
Host, Content-Length, Transfer-Encoding, Connection, Content-Type, User-Agent,
and `X-Topo-*` signing metadata are rejected. Authorization and API-key headers
are allowed because their values take the protected path.

Replacement rotates with zero overlap and outbound delivery resolves active
material only. Clearing a credential revokes it and clears the domain reference.
There is no automatic retry using an old outbound value. The delivery path loads
material only at the use boundary and bounds/redacts remote response copies and
errors to type-level state.

New URLs reject userinfo, fragments, and credential-like query parameter names.
Legacy credential-bearing URLs block 0011 until operator review; there is no
runtime compatibility exception.

## Product API, CLI, and browser boundary

Source creation accepts a write-only raw `credential`; caller-supplied
`secret_ref` and arbitrary purpose are not accepted. Source updates use explicit
rotate/replace, revoke, and reprovision actions. Enabled creation or enabling
without a valid credential is rejected. Reads and doctor output contain only
configuration/status metadata such as whether a credential is configured; they
never expose raw material, reference, key ID, material version, previous value,
environment name, or keyring path.

The CLI reads a raw source credential only from a CLI-local `--secret-env`,
`--secret-stdin`, or hidden prompt and sends it through the write-only API field.
It never asks the server to interpret an environment name. Rotate and revoke
commands generate one UUID idempotency key per logical operation and retain it
across HTTP retry.

The webhook frontend keeps current password/header values only in component
state. Replace and clear are explicit; responses retain flags and protected
header names only. A random operation key accompanies each mutation. Tests prove
no raw value is written to local/session storage and that API types are
metadata-only.

## Database, concurrency, and attack proof

Fresh and populated conversion paths run on SQLite and PostgreSQL. The converter
uses database row locking where supported and preserves per-object atomicity.
PostgreSQL concurrency proves provider rotation conflicts are CAS-bounded; the
same SecretStore guarantees cover rotate/revoke. Outbound replacement has no
overlap and remains atomically coupled to endpoint metadata.

Tests cover equal provider metadata across tenants, cross-tenant reference
tampering, purpose swaps, webhook reference swaps, inactive tenants, revoked
material, expiry, second rotation, explicit reprovision, verify-before-parse,
source/webhook rollback, dry-run, idempotent conversion, manifest/environment
oracle attacks, destructive-DDL rollback, downgrade refusal, and raw-marker
absence outside ciphertext. No SecretStore envelope, AES-GCM, AAD, keyring,
rewrap, or root-key lifecycle redesign is made.

## Custody and preservation

Canonical committed Git blob SHA-256 is the authority for immutable text
migrations. The accepted before/after values are:

| Migration | SHA-256 before and after |
| --- | --- |
| 0001 | B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD |
| 0002 | DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92 |
| 0003 | 907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F |
| 0004 | D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3 |
| 0005 | 14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333 |
| 0006 | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |
| 0007 | 8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84 |
| 0008 | 9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7 |
| 0009 | 20B1109D75E78F511B346F1D85DA8FA7FB9F6CAA8B8A92347A2859BA2D35CA5C |

Protected binary actual-byte authorities:

- Developer DB `backend/data/topo.db`:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- Frozen LINEAGE database:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

No older migration or protected database is modified. No causal/evidence
preservation test, evaluator, workflow, agent source, canonical ID, topology
relationship, score, timestamp, confidence, or attribution rule is weakened or
excluded.

## Verification receipts

All acceptance commands ran after the final product source change:

| Gate | Final result |
| --- | --- |
| Backend compile | PASS, exit 0 |
| Complete default backend | 1414 passed, 219 skipped, 2 existing warnings, 476.61s |
| Complete PostgreSQL-enabled backend | 1624 passed, 9 skipped, 2 existing warnings, 924.94s |
| Explicit PostgreSQL backup/restore | 1 passed, 3.84s; not skipped |
| Provider + PH-2 + PH-3 focused pack | 78 passed, 1 environment-specific skip, 1 existing warning, 31.84s |
| Evaluation compile / complete evaluation | PASS / 917 passed, 3 existing Windows skips, 73.34s |
| Agent compile / complete agent | PASS / 15 passed, exit 0 |
| CLI compile / complete CLI | PASS / 73 passed, 3.77s |
| Frontend typecheck | PASS |
| Frontend tests | 88 passed, 0 failed |
| Frontend lint | 0 errors, 11 unchanged warnings outside the PH-4C files |
| Frontend production build | PASS; optimized compile and all 14 pages generated |
| SEC-1 tests | 8 passed, 0.09s |
| Tracked-tree scan | PASS |
| New-file scan | 12 files, 0 findings |
| Route inventory | 143 total: tenant-required 116, machine-bound 9, tenant-control 7, security-global 9, public 2; unknown 0; new routes 0 |
| `git diff --check` | PASS, exit 0 |

The first sandboxed frontend build failed only because `next/font` could not
reach Google Fonts for the existing Geist, Geist Mono, and Roboto Slab imports.
The identical build with network access compiled successfully in 4.1s, passed
its TypeScript stage, generated all 14 pages, and exited 0. This was not a source
compilation failure.

The PostgreSQL proof used only disposable container
`topo-ph4c-secrets-20260901`, image `postgres:16`, exact ID
`a0d83c354f7bc867d29dcfd96040a0b6ab53791993f5ea1aec37ffad9f404111`,
loopback port `55439`, and tmpfs database storage. Test-only trust authentication
is not production guidance. Tests create/drop isolated databases. Final review
re-inspected that exact ID/name/image, confirmed `Mounts=[]` and tmpfs
`/var/lib/postgresql/data:rw,noexec,nosuid`, stopped and removed only that exact
container, then verified the exact-ID search empty.

## Remaining PH-4 work

PH-4D owns installation OpenAI and Groq keys, installation GitHub outbound token,
database URL/error boundaries, shared log/error/Pydantic sanitization, remote
response echo, redirect and URL credential rules outside this bounded webhook
surface, CLI/agent local custody, debug/repr behavior, and scanner gaps. PH-4E
remains the subsequent architecture/acceptance closure. PH-4C does not claim all
outbound credentials protected or global redaction complete.

No staging, commit, push, branch switch, migration 0012, PH-4D implementation,
or history modification is performed.

PH-4C ACCEPTED / READY FOR ARCHITECT REVIEW
