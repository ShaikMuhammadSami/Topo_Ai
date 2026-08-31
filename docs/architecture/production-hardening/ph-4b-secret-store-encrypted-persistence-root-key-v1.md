# PH-4B — Encrypted SecretStore and root-key lifecycle v1

## Scope and custody

Repository: `C:\Topo-ai`. Branch: `security/ph-4b-secret-store-foundation-v1`.
Accepted starting HEAD: `f8467a2ec33d448a6df58181802435c4aedb39dd`
(`docs(security): define secret custody architecture (#80)`). Starting worktree
was clean. This implements the PH-4A internal custody foundation only.

Verdict: **PASS — PH-4B foundation ready for architect review.** All required
final backend, PostgreSQL, evaluation, scanner and custody gates passed.
Architect review remains required before staging, committing or integrating consumers.

No provider/source verification, outbound webhook credential handling, LLM/SCM
credential lookup, one-way authentication persistence, TenantContext, membership,
service/machine binding, canonical identity, causal/evidence/evaluation semantics,
frontend, CLI, agent, workflow or execution code is changed. No live provider,
Kubernetes, cloud or LLM experiment is performed. PH-4C/D are not started.

Canonical committed Git blobs remain the authority for immutable text migrations;
working-copy CRLF expansion is not a rebaseline. Protected DBs use actual bytes.

| Artifact | SHA-256 before AND after all final suites (identical) |
| --- | --- |
| 0001 | B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD |
| 0002 | DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92 |
| 0003 | 907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F |
| 0004 | D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3 |
| 0005 | 14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333 |
| 0006 | D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728 |
| 0007 | 8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84 |
| 0008 | 9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7 |
| Developer DB V2, `backend/data/topo.db` | 0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E |
| Frozen LINEAGE, `evaluation/results/lineage/post-sc4/topo-product-32695735269.db` | 9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F |

Preflight, post-focused, PostgreSQL, backend and evaluation custody checks match,
including the final comparison after both full backend runs. Every 0001–0008
`git diff HEAD -- <migration>` is empty and each raw committed Git blob matches
the accepted hash above. Neither protected database was opened as a mutable
application/test database. Full suite subprocesses explicitly select separate
task-local temporary SQLite paths. No normalization or rebaseline was performed.

## Architecture and scope authority

```text
Existing server-validated PH-3 authority (future consumer)
  -> explicit SecretBinding(scope, owner, purpose)
  -> enabled backend + active tenant / configured installation check
  -> scope/owner/purpose-qualified record SQL
  -> lifecycle and usable material-version selection
  -> exact root-key ID + authenticated AES-GCM envelope
  -> transient SecretMaterial for internal use only
```

This is not a general-purpose tenant vault. The internal `SecretStore` protocol
has `put`, `describe`, `get_for_use`, `rotate`, `revoke`, `rewrap`. The concrete
`EncryptedDatabaseSecretStore` additionally provides `validate_readiness`.
There is no new HTTP route, decrypt/export endpoint or plaintext listing.

`SecretScope` carries existing authority, not a new membership model. Python
server code is trusted, just as existing repository tenant arguments are trusted;
the dataclass is not an unforgeable capability against arbitrary Python code.
Future consumers MUST derive it from existing validated TenantContext or owned
machine records, never request-body scope/tenant fields. A tenant scope requires
a valid existing active tenant; installation operations must match the explicitly
configured installation identity. No fake/default tenant, hostname or automatic
installation ID is generated. A tenant-only store does not require installation
configuration. Installation scope is not selected by a tenant-facing API.

The store qualifies SQL by scope kind, scope ID, tenant ID, owner type, owner ID
and purpose BEFORE selecting ciphertext. Wrong reference/owner/purpose behaves
absent. Material-version reads join back to the qualified record. Root-key AAD
authentication supplements but does not replace this authorization boundary.

## Persistence

Only `backend/alembic/versions/0009_secret_store_foundation.py` is added:

```text
revision = 0009_secret_store
down_revision = 0008_tenant_scoped_identity_namespace
one head = 0009_secret_store
```

ORM count: **45 tables, 803 columns**. Exactly two additions, no changes to the
existing 43 table schemas. PH-3 retains all 38 NOT NULL tenant-owned tables and
25 tenant-local composite identities unchanged. The new dual-scope records are
not forced into the domain tenant mixin.

`secret_records` contains 17 metadata columns: `secret_ref`, `scope_kind`,
`scope_id`, `tenant_id`, `owner_type`, `owner_id`, `purpose`, `status`,
`active_version`, `previous_version`, `previous_accept_until`, `row_version`,
`created_at`, `updated_at`, `created_by_subject`, `updated_by_subject`, `revoked_at`.
It contains NO plaintext, ciphertext, nonce, tag or root key.

`secret_versions` contains 15 columns: `secret_ref`, `version`, `key_id`,
`algorithm`, `envelope_version`, `nonce`, `ciphertext`, `operation_id`,
`operation_kind`, `overlap_seconds`, `envelope_revision`, `created_at`,
`created_by_subject`, `rewrapped_at`, `rewrapped_by_subject`. Ciphertext includes
the full tag. No plaintext, root key, plaintext digest, auth header or raw token
column exists. Operation kind/overlap are bounded retry metadata, not secret
verifiers. No data backfill, inferred ownership, inserted default record, key
generation or server default occurs in the migration.

Constraints:

- Globally random `secret:<uuid4>` primary key; `uuid.uuid4`, no content-derived ID.
- Unique `(scope_kind, scope_id, owner_type, owner_id, purpose)` logical binding.
- Tenant: `scope_kind='tenant'`, tenant non-NULL and `scope_id=tenant_id`.
- Installation: `scope_kind='installation'`, tenant NULL. Application validates
  `installation:<canonical lowercase UUIDv4>` and exact configured identity.
- Active/revoked status, positive row/material versions; previous pointer/deadline
  both absent or both present, with previous less than active.
- Versions: composite primary key `(secret_ref, version)`, unique
  `(secret_ref, operation_id)`, physical FK to `secret_records.secret_ref`.
- Positive envelope revision and overlap from 0 through 86400 seconds.

Downgrade drops `secret_versions` then `secret_records`, and nothing else. It is
destructive to these new secrets, not a production rollback recommendation.
Production operators need backup/compatible application/forward-fix procedures.

## Exact purpose policy

| Exact enum value | Required owner type | Scope | Previous accepted for use? |
| --- | --- | --- | --- |
| `change_source.github_hmac` | `change_source` | tenant | bounded |
| `change_source.gitlab_signing` | `change_source` | tenant | bounded |
| `change_source.gitlab_shared_token` | `change_source` | tenant | bounded |
| `change_source.terraform_hmac` | `change_source` | tenant | bounded |
| `change_source.jenkins_hmac` | `change_source` | tenant | bounded |
| `change_source.azure_basic_password` | `change_source` | tenant | bounded |
| `webhook_endpoint.signing` | `webhook_endpoint` | tenant | never |
| `webhook_endpoint.protected_headers` | `webhook_endpoint` | tenant | never |
| `installation_integration.openai_api` | `installation_integration` | installation | never |
| `installation_integration.groq_api` | `installation_integration` | installation | never |
| `installation_integration.github_api` | `installation_integration` | installation | never |

There is no arbitrary string purpose or caller flag to retrieve older outbound
material. These are reserved synthetic-tested bindings, NOT migrated consumers.

## Cryptography and transient material

Direct backend dependency: `cryptography>=50.0.1,<51`; tested installed version
50.0.1 (transitive cffi 2.1.1, pycparser 3.0). The existing requirements-file
convention is preserved. No custom cipher, Fernet substitution or new provider.

AESGCM uses exactly 32-byte keys, independently random `os.urandom(12)` nonces for
every encryption/rewrap, and full 16-byte authentication tags. Plaintext accepts
1 through 65536 bytes. The maintained library's authenticated-encryption API
and nonce requirements are documented in [cryptography's AESGCM reference](https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
Random nonces make collisions negligibly likely for bounded V1 operation; this
does not claim mathematically impossible collisions or unlimited per-key volume.

Exact AAD fields: `scope_kind`, `scope_id`, `tenant_id` (string or JSON null),
`secret_ref`, `owner_type`, `owner_id`, `purpose`, `material_version` (integer),
`envelope_version` (integer), `algorithm`, `key_id`. Encoding is typed JSON,
sorted keys, separators `(',', ':')`, `ensure_ascii=False`, UTF-8. There is no
delimiter concatenation or material in AAD.

Decrypt validates algorithm, envelope version, key-ID format, material version,
12-byte nonce and 17..65552-byte ciphertext. Scope/lifecycle metadata is validated
before use. One exact root-key ID is selected; no try-all-key behavior. Tamper,
wrong key, missing key at decrypt, malformed envelope and tag failure produce
`SECRET_DECRYPT_FAILED`, without raw chained crypto exceptions or input values.

`SecretMaterial` exposes bytes only through explicit `reveal()`. `repr` and `str`
are `SecretMaterial(<redacted>)`; ordinary JSON serialization fails. It is not an
ORM field or domain/API model. No global plaintext cache or Python zeroization
claim is made. Memory/SDK copies and privileged Python reflection remain outside
the DB-at-rest guarantee.

`SecretDescriptor` contains only reference, binding, status, active/usable previous
version and deadline, row version, created/updated/revoked timestamps. No nonce,
ciphertext/tag, key material or plaintext. ORM repr is explicit metadata/protected
text. `SecretBinary` protects ordinary bound/result byte representations. SQL
debug dumps, arbitrary direct DB dumps and application memory inspection are not
a substitute for the later PH-4D global redaction boundary; do not enable raw
driver result logging with credentials.

Store database exceptions are mapped outside their handler to bounded codes,
without raw SQL/driver parameter chains. The store logs no material. This is a
narrow SecretStore boundary, not a claim that all older product logs are safe.

## Root-key custody and startup

Exact settings:

- `TOPO_SECRET_STORE_BACKEND`: default `disabled`; only `encrypted_db` enables use.
- `TOPO_SECRET_KEYRING_FILE`: explicit absolute operator-mounted path.
- `TOPO_SECRET_ACTIVE_KEY_ID`: explicit member key, no automatic selection.
- `TOPO_INSTALLATION_ID`: optional for tenant-only use; required for installation use.

File shape: JSON object with exactly `version: 1` and `keys` mapping validated
key IDs to base64url-encoded 32-byte values. Optional canonical padding accepted.
Maximum file 65536 bytes; 1..32 keys; key IDs match
`[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`. Duplicate JSON keys at any object level, unknown
format version, invalid encoding/length/ID, missing/empty/oversized file or absent
active key fail closed. No environment contents/path/key bytes appear in errors.

The loader rejects directories, symlink/reparse leaves and ancestors, bounds
reads, compares opened file identity with lstat, uses O_NOFOLLOW where available,
and enforces no group/other permission bits on POSIX. Windows development tests
are supported; **secure Windows production ACL custody is NOT established**.
No insecure-permissions override is introduced. There is no tracked real/example
keyring or automatic root-key creation. Tests generate fresh synthetic keys.

Startup order is existing schema initialization/authority -> SecretStore
configuration and metadata readiness -> existing required human-admin authority
-> ready. Existing routes still return only their minimal health/ready JSON.
No public key IDs, backend configuration, paths, refs, tenant IDs or errors.

Encrypted mode requires valid configuration/active key even for an empty store.
Disabled mode refuses readiness if EITHER table has any row, including revoked
records or corrupt version-only storage. No missing-table or plaintext fallback.
Readiness uses keyset pages of at most 256 metadata records, with at most two
version-metadata lookups per active record. It never loads ciphertext or decrypts.
Each currently usable active/previous version must exist and its exact key must
be available. Expired previous and revoked material need not retain old keys.
This is the narrower PH-4B retirement policy, not PH-4A's earlier broad wording.

Readiness is a point-in-time configuration check, not continuous keyring reload or
proof every ciphertext is intact. Decryption revalidates integrity on use.

## Transactions, rotation, revocation and rewrap

All mutating operations use the caller's SQLAlchemy Session and NEVER commit the
outer transaction. A savepoint contains each operation. SQLite legacy transaction
mode needs a physical BEGIN before SAVEPOINT so RELEASE cannot commit outside
the caller's subsequent rollback; this is transaction control, not domain SQL.
PH-4C can therefore commit/rollback a domain reference and its secret together.

Put creates record and version 1 atomically. Exact operation/material retries
return metadata only. Same operation with different bytes, or conflicting binding
creation, fails. Equality uses decrypt plus `hmac.compare_digest`, not a stored
plaintext hash. Operation IDs are caller-provided non-secret idempotency metadata.

Rotate increases material version monotonically. Default overlap is zero; inbound
overlap is server-bounded at 24 hours; outbound overlap must be zero. Positive
overlap accepts the former active version only until the original UTC deadline.
Exactly at expiry it is no longer returned. A second rotation replaces previous,
so at most two values are ever returned. Exact operation/material/overlap retries
do not create versions, extend deadlines or reactivate older versions. A retry
requiring a retired historical key fails closed rather than weakening retirement
or falling back to plaintext comparison; retries should be completed before key
retirement. PH-4C must retain operation IDs through its atomic consumer transaction.

Revoke is immediate at the next authorized read boundary, clears previous
acceptance and is idempotent. It does not delete ciphertext or provide unrevoke.
Already in-flight material cannot be recalled from process memory.

Rewrap re-encrypts currently usable active/previous material with the configured
active root key and a fresh nonce. Material version, operation identity and
overlap deadline remain unchanged; envelope revision and rewrap metadata advance.
Already-current envelopes are a no-op after integrity validation. Expired/revoked
history is not silently decrypted or reactivated. Retire an old root only after
all currently usable envelopes have been rewrapped; physical escrow/backup/key
destruction remains PH-8/operator work.

CAS uses expected record `row_version`, active pointer, active status and exact
binding in SQL UPDATE. Rewrap additionally compares envelope revision and prior
key ID. PostgreSQL READ COMMITTED is the measured target. Competing operations
from one expected state cannot both mutate successfully. There are no process
locks. A stale operation returns `SECRET_CONCURRENT_MODIFICATION`; callers may
re-read and deliberately retry. A failed concurrent revoke is not reported as a
successful revocation. No automatic last-writer-wins overwrite or secret worker.

Tests inject failures after record insert, after rotation CAS/before version
insert, and after rewrap encryption/record CAS/before envelope update. A caught
operation exception followed by caller commit still preserves the previous
valid state. Retrying the operation after removing the synthetic fault succeeds.

## Evaluation, schema regression and preservation boundaries

Older migration tests targeting 0007/0008 now compare against explicit
`frozen_0007_metadata`/`frozen_0008_metadata`; they do not accidentally demand the
new tables at an old revision. Current-head schema assertions include all 45
tables. The original PH-1/PH-3 generic ORM corpus retains its 43 historical tables;
the new constrained binary tables have dedicated real-engine tests rather than
invalid generic strings. PH-3's 38 owned-table partition stays exact; the new
dual-scope tables are explicitly accounted for, not ambiguous exclusions.

No causal preservation test, protected source hash, evaluator, frozen receipt,
world-model assertion, lineage candidate rule, score/confidence, evidence stance,
graph edge, timestamp or canonical identity is excluded or changed. Full unchanged
backend/evaluation regressions remain required. Existing provider/HMAC/Basic
verification and environment-based secret lookups are deliberately unchanged.

## Verification environment and receipts

Disposable PostgreSQL container: `topo-ph4b-secrets-20260831`, image `postgres:16`,
ID `4301b3e2f523be61c47317358d0f5388dc2f994a14adb15295bd70ce5834269a`,
loopback `127.0.0.1:55438`, database `ph4b_acceptance`, tmpfs
`/var/lib/postgresql/data`, `Mounts=[]`. Test-only loopback trust is not production
authentication guidance. Measured server version: `16.15 (Debian 16.15-1.pgdg13+2)`,
isolation `read committed`. Tests create/drop their own databases. After the final
suite, inspection reconfirmed that exact ID/name/image and tmpfs-only storage;
`docker stop` and `docker rm` targeted only that ID, both exited 0. Final exact-ID
container search returned zero matches. Its disposable data was removed; there
was no persistent named volume or user DB to delete.

| Check | Result |
| --- | --- |
| Initial new SQLite corpus | 59 passed, 45 PostgreSQL skips, 4 setup errors; oversized synthetic parameter IDs exceeded Windows fixture filename limits, corrected with explicit short IDs, no product/assertion weakening |
| Initial new SQLite/PostgreSQL store+migration+CAS corpus | 115 passed, 5 dialect-specific skips, 1 existing Starlette warning, 65.97s |
| Initial full SQLite backend before readiness-fixture repair | 1398 passed, 216 skipped, 2 fixture failures, 2 existing warnings, 1151.79s; no SecretStore security/crypto assertion failure |
| Expanded startup/schema/tenant/PostgreSQL compatibility regression | 99 passed, 1 SQLite-only HTTP fixture skip, 1 existing warning, 312.54s |
| Full backend SQLite / compile, final source | 1401 passed, 217 skipped, 2 existing warnings, 1092.29s / exit 0 |
| Full backend PostgreSQL-enabled, final source | 1610 passed, 8 explained dialect-specific skips, 2 existing warnings, 1865.03s / exit 0 |
| Full evaluation / compile, final source | 917 passed, 3 existing Windows symlink skips, 182.54s / exit 0 (earlier run: 917 passed, 3 skipped, 206.70s) |
| Provider / PH-2 / PH-3 focused | 89 passed, 1 existing warning, 63.62s |
| SEC-1 tests / tracked scan / explicit new-file scan | 8 passed in 0.27s / exit 0 / 10 new files, 0 findings |
| Existing PostgreSQL backup/restore regression | `test_backup_restore_preserves_representative_history` passed, not skipped; downgrade/reupgrade compatibility also passed |
| Final custody / Git diff check / cleanup | All 8 canonical migration hashes and both actual-byte DB hashes unchanged / exit 0, no whitespace errors / exact disposable container removed |

No skip is reported as PostgreSQL proof. The dedicated four concurrency cases
run only on PostgreSQL; their SQLite variants intentionally skip. The migration
DDL rollback case likewise requires PostgreSQL. The HTTP development-mode fixture
is SQLite-only; direct encrypted-store and schema-authority tests cover PostgreSQL.
The eight full PostgreSQL-enabled skips are exactly: four SQLite CAS variants,
three SQLite transactional-DDL variants (machine tenant, identity namespace,
SecretStore), and the PostgreSQL variant of that SQLite-only HTTP fixture. No
PostgreSQL CAS, migration, storage or backup/restore proof was skipped.

The four new modules contain 31 test functions / 157 parameterized cases:

| Module | PostgreSQL-enabled run: passed | Intentionally skipped |
| --- | ---: | ---: |
| `test_secret_store.py` | 121 | 0 |
| `test_secret_store_migrations.py` | 5 | 1 |
| `test_secret_store_postgres.py` | 4 | 4 |
| `test_secret_store_startup.py` | 21 | 1 |
| Total | 151 | 6 |

The four real PostgreSQL transaction pairs were rotate/rotate, rotate/revoke,
rotate/rewrap and rewrap/rewrap. Each produced exactly one successful mutation
and one bounded CAS conflict with consistent final record/version state.

## PH-4C handoff (not implementation authority here)

After architect acceptance, PH-4C should bind existing change sources and webhook
endpoints to these internal methods, using server-owned PH-3 tenant and exact
owner/purpose. Preserve the six existing inbound provider mechanisms and
verify-before-parse/replay semantics. Keep one-way auth digests outside SecretStore.
Use one caller transaction for secret write/rotation and domain reference; never
commit either side independently. Preserve operation IDs and expected row version;
reconcile CAS conflicts explicitly. Use active plus unexpired previous only for
inbound verification, active only for outbound signing/header credentials.

Make new material inputs write-only; responses expose descriptors/status, never
raw values or ciphertext. Separate protected header bundles from ordinary config.
Implement an explicitly owner-proven legacy conversion, not automatic migration
DDL backfill or arbitrary environment reference import. Handle revoked/disabled
tenant/source and unavailable key material with bounded existing auth responses.
Installation LLM/SCM integration and broad redaction remain PH-4D. Do not activate
execution, add a rotation daemon, or introduce another tenant authority.

PH-4 is NOT closed. Product provider/webhook secrets are NOT migrated or removed
from their existing plaintext/environment paths. At-rest confidentiality covers
SecretStore rows against a DB-read attacker without root keys. It does not cover
compromised application processes, keyring access, runtime memory, database
superuser integrity manipulation, global log custody, arbitrary SQL dumps,
production Windows ACLs, HSM/FIPS certification, HA rotation coordination, or
physical backup/key escrow. Broader PH-4 and later hardening gates remain open.

## Final acceptance accounting

The following item numbers reconcile the architect's complete 170-item request.
Behavioral PASS entries refer to the focused evidence and completed full final
regression gates above, not merely static design claims.

| Requested item(s) | Evidence / answer |
| --- | --- |
| 1–4 | Isolated PH-4B foundation; accepted HEAD and branch above; final verdict PASS |
| 5–8 | Six product files (two existing, four new), thirteen test/helper files (nine existing, four new), one document, one dependency file; migration counted separately |
| 9–13 | One new `0009_secret_store_foundation.py`; revision `0009_secret_store`; parent `0008_tenant_scoped_identity_namespace`; exactly one head |
| 14–21 | Exact before/after canonical SHA-256 values for all eight frozen migrations in custody table; all identical |
| 22 | Existing migration changes NONE |
| 23–29 | ORM45; exactly two new tables; old43 schema changes0; plaintext columns0 in either new table; root-key columns0 |
| 30–32 | Explicit tenant or configured installation; SQL scope CHECK and application ID validation, no default or caller-selected authority |
| 33–36 | `secret:<uuid4>`, OS-backed UUID randomness, global PK uniqueness, exact five-column logical binding uniqueness |
| 37–38 | Eleven exact enum values and owner/scope compatibility in purpose table |
| 39–44 | Six internal protocol methods; no helper commit; redacted non-JSON SecretMaterial; exact metadata-only descriptor listed above; raw fields0 |
| 45–50 | cryptography50.0.1 AES-256-GCM, 32-byte key, 12-byte fresh random nonce, 16-byte full tag, 65536-byte maximum plaintext |
| 51–52 | Eleven typed AAD fields; canonical sorted compact UTF-8 JSON as listed |
| 53–59 | Same-plaintext nonces/ciphertexts differ; byte/nonce/key-ID/algorithm/envelope/material-version and all binding-field tamper fail; wrong key fails |
| 60 | Generic decrypt error contains no sensitive input or chained crypto error |
| 61–67 | Four exact settings; version1 JSON keyring; 65536-byte/32-key bounds; strict ID/base64url/32-byte checks; unknown active key denied |
| 68–69 | POSIX group/other permissions rejected, including opened-file check; Windows development only, no production ACL claim |
| 70–73 | Disabled default; any record OR version row denies disabled readiness; installation UUIDv4 explicit/configured, never autogenerated |
| 74–78 | Valid empty encrypted startup succeeds; absent active or required live old key fails; expired previous/revoked old-key retirement succeeds |
| 79–82 | Atomic put and caller rollback; same operation+bytes retry succeeds; conflicting bytes rejected, no plaintext digest |
| 83–85 | Active use succeeds; inbound at most active+one unexpired previous; outbound active only, nonzero overlap rejected |
| 86–90 | Default overlap0, inbound maximum86400s; exact expiry exclusion; second rotation drops older; retry does not change deadline/version |
| 91–92 | Revoke denies subsequent use/rotation and clears previous; repeat revoke is metadata-only/idempotent |
| 93–97 | Rewrap live envelopes with new root/fresh nonce; material version unchanged; old live keys required until all live rewrap; retired old history need not remain decryptable |
| 98–102 | Parent row+active+status CAS and envelope revision/key CAS; all four actual PostgreSQL transaction pairs produce one accepted mutation and one conflict |
| 103–105 | Injected partial put/rotate/rewrap roll back even if caller catches and commits; retry succeeds |
| 106–110 | A/B equal owner-purpose coexist; foreign-ref, owner, purpose, installation/tenant and disabled-tenant attacks rejected before ciphertext query/decrypt |
| 111–114 | Synthetic plaintext occurrences in raw version rows0; plaintext/ciphertext/root-key in normal repr, descriptor, public output, bounded errors/logs0 in tested corpus |
| 115–120 | Existing provider lookup, webhook handling, auth digests, AuthPrincipal/TenantContext, canonical IDs and causal semantics all unchanged |
| 121–125 | SQLite fresh/populated0008->0009, strict parity45, populated new-store downgrade/reupgrade, real SQL/crypto corpus; final full receipt below |
| 126–132 | Same real PostgreSQL16 migration/runtime proofs; four CAS pairs; current application rejects behind0008 before keyring/auth readiness |
| 133 | Existing real PostgreSQL backup/restore regression passed, not skipped, as did downgrade/reupgrade compatibility |
| 134–141 | Full SQLite1401/217, PG1610/8, evaluation917/3 passed/skipped; focused89 passed; backend and evaluation compile exit0; exact times/warnings above |
| 142–145 | SEC-1 eight tests passed; tracked scan exit0; ten new files scanned with zero findings; final diff-check exit0 |
| 146–152 | Actual-byte DB before/after and canonical0001–0008 custody above; all identical after final suites, no normalization or rebaseline |
| 153–154 | Direct `cryptography>=50.0.1,<51` dependency only, required maintained AESGCM implementation, not custom crypto |
| 155–158 | Exact ten created / twelve modified paths and final Git output recorded below; `git diff --name-only` is exactly the twelve modified paths |
| 159–164 | Crypto blocker NO; SecretStore blocker NO; concurrency blocker NO; security blocker NO; custody blocker NO; first blocker NONE |
| 165–166 | PH-4 closed NO; product provider/webhook secrets migrated NO |
| 167–169 | Encrypted foundation ready for PH-4C YES, subject to architect review; exact handoff above; recommended next block: PH-4C — Provider + Webhook Reversible Secret Integration + Legacy Plaintext/Environment Conversion + Rotation v1; not started |
| 170 | Stop after final report; no stage/commit/push or subsequent block |

Two old startup fixtures bypassed schema initialization entirely. They now opt
into actual disposable SQLite schemas for readiness testing. No assertion was
removed, product readiness was not bypassed and auth behavior was not weakened.
The initial full run's failures are recorded separately from the final rerun.
Review also tightened the first readiness keyset page: it starts without a lower
bound, so a corrupt empty reference cannot be skipped. A permanent real-engine
test now requires denial for that malformed metadata. In-progress verification
runs were superseded and restarted to cover this final guard; no partial run is
claimed as a full-suite success.
Every pre-existing ORM class is AST-identical to starting HEAD; new classes are
exactly `SecretRecord` and `SecretVersionRecord`. SecretStore internal commit-call
count is zero. These structural checks complement, not replace, runtime tests.

No stage, commit, push, branch switch, history change or subsequent block is
authorized or performed.

## Exact change surface

Created:

```text
backend/alembic/versions/0009_secret_store_foundation.py
backend/app/db/secret_types.py
backend/app/models/secret_store.py
backend/app/security/secret_keyring.py
backend/app/services/secret_store.py
backend/tests/test_secret_store.py
backend/tests/test_secret_store_migrations.py
backend/tests/test_secret_store_postgres.py
backend/tests/test_secret_store_startup.py
docs/architecture/production-hardening/ph-4b-secret-store-encrypted-persistence-root-key-v1.md
```

Modified:

```text
backend/app/db/models.py
backend/app/main.py
backend/requirements.txt
backend/tests/conftest.py
backend/tests/frozen_schema_fixtures.py
backend/tests/test_authentication_default_on.py
backend/tests/test_domain_tenant_migration.py
backend/tests/test_machine_tenant_migration.py
backend/tests/test_postgres_runtime_compatibility.py
backend/tests/test_schema_migrations.py
backend/tests/test_tenant_adversarial_inventory.py
backend/tests/test_tenant_identity_namespace.py
```

22 paths total, OTHER0. Existing/new product6, migration1, dependency1, test/helper13,
document1. Frontend0, CLI0, agent0, evaluators0, workflows0. Tracked `git diff --stat`
does not include the ten unstaged new files; they are enumerated explicitly here.

Final `git status --short`:

```text
 M backend/app/db/models.py
 M backend/app/main.py
 M backend/requirements.txt
 M backend/tests/conftest.py
 M backend/tests/frozen_schema_fixtures.py
 M backend/tests/test_authentication_default_on.py
 M backend/tests/test_domain_tenant_migration.py
 M backend/tests/test_machine_tenant_migration.py
 M backend/tests/test_postgres_runtime_compatibility.py
 M backend/tests/test_schema_migrations.py
 M backend/tests/test_tenant_adversarial_inventory.py
 M backend/tests/test_tenant_identity_namespace.py
?? backend/alembic/versions/0009_secret_store_foundation.py
?? backend/app/db/secret_types.py
?? backend/app/models/secret_store.py
?? backend/app/security/secret_keyring.py
?? backend/app/services/secret_store.py
?? backend/tests/test_secret_store.py
?? backend/tests/test_secret_store_migrations.py
?? backend/tests/test_secret_store_postgres.py
?? backend/tests/test_secret_store_startup.py
?? docs/architecture/production-hardening/ph-4b-secret-store-encrypted-persistence-root-key-v1.md
```

`git diff --stat`: 12 tracked files changed, 147 insertions(+), 39 deletions(-).
`git diff --name-only` exactly matches the Modified list above; untracked files
are not omitted from the Created list. `git diff --cached --name-only` is empty.
HEAD and branch remain the starting values. `git diff --check` exits 0 with no
whitespace errors. Git's expected working-copy LF/CRLF notices and pre-existing
inaccessible `.pytest_cache` directory warnings are not custody changes.

## Reproducible verification commands

These commands use disposable test databases, NOT `backend/data/topo.db` or the
frozen LINEAGE seed. They do not configure a real provider or persist real keys.

```powershell
Set-Location C:\Topo-ai\backend
$env:TOPO_DATABASE_URL = 'sqlite:///' + ($env:TEMP -replace '\\','/') + '/topo-ph4b-review.db'
$env:TOPO_SECRET_STORE_BACKEND = 'disabled'
Remove-Item Env:TOPO_TEST_POSTGRES_URL -ErrorAction SilentlyContinue
& .\.venv\Scripts\python.exe -m compileall -q app
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

# Primary-engine proof requires the task-local disposable PostgreSQL container
# (or a newly created, equivalently isolated review container after cleanup).
$env:TOPO_TEST_POSTGRES_URL = 'postgresql+psycopg://postgres@127.0.0.1:55438/ph4b_acceptance'
$env:TOPO_TEST_POSTGRES_CONTAINER = 'topo-ph4b-secrets-20260831'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

Set-Location C:\Topo-ai
& .\backend\.venv\Scripts\python.exe -m compileall -q evaluation
& .\backend\.venv\Scripts\python.exe -m pytest evaluation -q -p no:cacheprovider --tb=short
& .\backend\.venv\Scripts\python.exe -m pytest scripts/security/tests -q -p no:cacheprovider
& .\backend\.venv\Scripts\python.exe scripts/security/check_tracked_secrets.py
git branch --show-current
git status --short
git diff --stat
git diff --check
```

Pytest cache writing is disabled because the pre-existing cache directories are
inaccessible; no test is deselected by this option and no cache was deleted.
JUnit receipts use `%TEMP%/topo-ph4b-*.xml`; they are operational test receipts,
not frozen experiment results. Complete final receipts are identified below.

Final SQLite receipt: `%TEMP%/topo-ph4b-backend-sqlite-final.xml`, 1618 collected,
zero failures/errors. Final PostgreSQL receipt:
`%TEMP%/topo-ph4b-backend-postgres.xml`, 1618 collected, zero failures/errors.
Final evaluation receipt: `%TEMP%/topo-ph4b-evaluation-final.xml`, 920 collected,
zero failures/errors. Times in the results table are pytest's final console
durations; JUnit's suite durations are respectively 1092.170s, 1864.894s and
180.828s and exclude some reporter overhead.
The 157 new parameterized cases are distributed across four new modules; the
SQLite-default run passes 88 and intentionally skips 69. PostgreSQL-enabled
verification passes 151 and intentionally skips 6, as accounted for above.
Existing warnings are Starlette/httpx deprecation and the intentional duplicate
ORM identity attack in the unchanged tenant-adversarial test.

Scope is stopped at PH-4B. No source integration, PH-4C/D work, migration 0010,
provider execution, staging, commit, push or history modification was performed.

PH-4B ACCEPTED / READY FOR ARCHITECT REVIEW
