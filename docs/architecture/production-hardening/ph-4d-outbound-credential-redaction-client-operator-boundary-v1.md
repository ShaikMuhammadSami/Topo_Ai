# PH-4D — Outbound credential, redaction, client, and operator boundary v1

## Scope and authority

Repository: `C:\Topo-ai`. Branch:
`security/ph-4d-outbound-redaction-client-custody-v1`. Accepted starting HEAD:
`44587673a16f014b097d4c39129c425a727d2030`.

PH-4D moves the installation-wide OpenAI, Groq, and outbound GitHub credentials
behind the existing PH-4B `SecretStore`; removes their legacy environment
variables as normal runtime authorities; provides a local operator-only
administration path; and applies shared secret-safe boundaries to backend,
client, agent, browser, SQL, HTTP, logging, validation, and scanning surfaces.

This block does not alter PH-4B encryption, PH-4C provider/webhook bindings,
one-way authentication digests, tenant authority, canonical identities,
causal/evidence semantics, or execution behavior. It creates no migration,
table, credential HTTP API, provider, or dependency. PH-4 remains open pending
independent PH-4E acceptance.

## Installation credential bindings

The three bindings are fixed in server code and use only the validated
`TOPO_INSTALLATION_ID` installation UUID:

| Integration | Scope | Owner type | Owner ID | Purpose |
| --- | --- | --- | --- | --- |
| OpenAI | `installation` | `installation_integration` | `openai` | `installation_integration.openai_api` |
| Groq | `installation` | `installation_integration` | `groq` | `installation_integration.groq_api` |
| GitHub outbound API | `installation` | `installation_integration` | `github` | `installation_integration.github_api` |

`describe_for_binding()` and `get_for_binding()` resolve the existing unique
scope/owner/purpose binding and then use the same SecretStore authorization,
lifecycle, active-version, decryption, and error pipeline as reference-based
access. Descriptors remain metadata-only. Callers cannot browse installation
secrets, select tenant or installation scope, supply a purpose, derive a secret
reference, or retrieve prior outbound material.

Runtime access opens a short database session, resolves exactly one active
material value at the final provider-use boundary, constructs the provider
client/request, and retains no process-global plaintext cache. Revoked,
unavailable, invalid, or undecryptable bindings are not used. Outbound rotation
uses zero overlap; only the active version is returned.

## Operator configuration and lifecycle

`python -m app.installation_secret_admin` is a local module and registers no
HTTP route. Supported operations are `status`, `set`, `rotate`, `reprovision`,
`revoke`, and `import-known-env`.

Examples from `C:\Topo-ai\backend`:

```powershell
# Configure without putting material in argv or stdout.
$credential | & .\.venv\Scripts\python.exe -m app.installation_secret_admin `
  set openai --secret-stdin --operation-id operator-change-2026-09-04

# Hidden prompt is the default when --secret-stdin is absent.
& .\.venv\Scripts\python.exe -m app.installation_secret_admin rotate groq `
  --operation-id operator-rotation-2026-09-04

# Explicit one-time legacy import; runtime never reads these variables.
& .\.venv\Scripts\python.exe -m app.installation_secret_admin `
  import-known-env github --operation-id operator-import-2026-09-04

& .\.venv\Scripts\python.exe -m app.installation_secret_admin status
& .\.venv\Scripts\python.exe -m app.installation_secret_admin revoke github
```

The exact legacy import map is `openai -> OPENAI_API_KEY`,
`groq -> GROQ_API_KEY`, and `github -> TOPO_GITHUB_TOKEN`. The command neither
accepts an arbitrary environment-variable name nor enumerates the environment.
Other material enters only through stdin or a hidden prompt. The parser has no
raw secret option, and invalid arguments are not echoed.

`set` uses `put`; `rotate` uses zero-overlap `rotate`; `revoke` uses `revoke`;
and an explicitly revoked binding must use `reprovision`. Mutations accept or
generate a stable, non-secret operation ID. An identical retry is idempotent;
same operation with different material is a bounded conflict. Status and
mutation receipts contain integration, configured/status state, update time,
operation, and safe operation ID only. They exclude raw material, secret
reference, key ID, material version, ciphertext, and keyring path.

## Runtime provider behavior

OpenAI client construction reads only the installation OpenAI SecretStore
binding. Optional or automatic calls without usable material keep the existing
deterministic no-LLM fallback. Explicit provider paths preserve their existing
bounded unavailable/error result; they do not fall back to the environment.
`store=False`, tenant context, evidence assembly, prompts, and structured output
semantics are unchanged.

All four Groq branches use the same installation SecretStore boundary. Missing
or revoked material preserves deterministic fallback/unavailable behavior. No
raw SDK exception text is returned, logged, or persisted.

Authenticated GitHub API, source-file, build, and artifact retrieval uses only
the installation GitHub SecretStore binding. The existing public unauthenticated
GitHub capability remains available when no credential is configured. Private
capability then remains unavailable; there is no environment fallback. Repository,
commit, workflow-run, image, artifact, and source evidence semantics are
unchanged. Any transient settings representation containing a token marks it
non-representable and holds it only at the request boundary.

Final production runtime reads of `OPENAI_API_KEY`, `GROQ_API_KEY`, and
`TOPO_GITHUB_TOKEN` are zero. Those names remain only in the exact operator
import map, documentation, tests, examples, and scanner patterns.

## Database bootstrap exception and SQL safety

`TOPO_DATABASE_URL` and Alembic `sqlalchemy.url` remain deployment/operator
configuration because the SecretStore cannot be opened before its database is
available. They are deliberately not SecretStore-backed.

Application and Alembic SQLAlchemy engines set `hide_parameters=True`, keeping
bound values out of SQL exceptions and debug representations without changing
SQL semantics or SQLite/PostgreSQL compatibility. Database, migration, schema
administration, and startup paths expose bounded error state/type rather than a
credential-bearing URL, raw bound parameters, or arbitrary database exception
text.

## Central backend redaction and error contract

`app.security.secret_redaction` is the shared defense-in-depth boundary. The
primary rule remains to avoid storing, serializing, or logging raw credentials
in the first place. The module provides bounded structured sanitization, header
sanitization, URL-safe formatting, base-URL validation, exception metadata,
validation-error formatting, response-header filtering, safe text handling, and
a global log-record factory.

Structured sensitive-key classification is explicit, case-insensitive, and
separator-insensitive. It covers authentication, proxy authorization, cookies,
passwords, generic/provider API credentials, access/refresh/bearer/enrollment
tokens, private/signing material, CSRF, and provider proof headers. Explicit
benign keys such as `token_count`, `token_budget`, `token_hint`, `secret_ref`,
and `credential_id` remain visible. Traversal is capped at depth 6, 100 items,
and 5000 text characters. A cutoff returns a fixed marker and never stringifies
an unvisited subtree.

Log/error header formatting uses a small metadata allowlist. Authorization,
proxy authorization, Cookie/Set-Cookie, Topo CSRF/signature, GitHub/GitLab,
Terraform, and webhook proof values are suppressed. Unknown custom headers are
not logged with values. URLs retain only scheme, host, safe port, and a bounded
path; userinfo, query, and fragment are omitted. Defense-in-depth text handling
recognizes Bearer and Basic schemes, current credential prefixes,
credential-like assignments, and credential-bearing URLs.

FastAPI request validation returns location, bounded generic validation
message, and error type only; it never returns Pydantic's raw `input` value or
exception context. HTTP exception headers are filtered so an error path cannot
echo Set-Cookie or authentication proofs. Raw credential input models and
one-time token response fields are non-representable. Public, provider, webhook,
LLM, GitHub, and persisted diagnostic errors use stable state/type information
rather than arbitrary exception or remote-response bodies.

The log record factory sanitizes message arguments and structured extras and
replaces traceback bodies with exception type. `httpx`, `httpcore`, `openai`,
`groq`, and `sqlalchemy.engine` are kept at WARNING or above. Context and evidence
remain available to LLM calls as product data; they are not mislabeled as
credentials. This is credential redaction, not a claim that general customer-
data egress has been minimized.

## URL and redirect policy

Credential-bearing Topo API, agent, GitHub API, and Next backend base URLs must
be HTTP(S) URLs with a host and without userinfo, query, or fragment. They fail
before a credential-bearing request is sent. Diagnostic rendering strips
userinfo, query, and fragment.

CLI and agent transports disable automatic redirects and reject 3xx responses,
so bearer credentials and enrollment bodies cannot be forwarded cross-origin.
GitHub API/content requests likewise reject redirects. Artifact downloads retain
their necessary bounded manual redirect flow; the Authorization header is
removed whenever the redirect origin changes, and invalid/unsafe chains fail.
Webhook redirect behavior remains disabled under PH-4C.

## CLI boundary

CLI profiles store only URL/profile metadata in their file and keep bearer
tokens in the OS keyring. Known null, plaintext, and otherwise insecure keyring
backends fail closed; an explicitly supplied process environment token retains
its documented precedence without being persisted. Topo API redirects are
disabled, network/HTTP errors are bounded, remote response objects are not
dumped, and the client representation excludes bearer material.

Agent enrollment creation shows metadata by default. Raw one-time output
requires explicit `--output-token-stdout`, prints only the token to stdout, and
returns immediately so it cannot be mixed into a table or log. Change-source
secret commands retain their PH-4C stdin/prompt/environment-input boundary and
do not store raw material in profiles.

## Agent local credential custody

The agent no longer accepts a raw token through command-line arguments. Initial
material enters through stdin or a hidden prompt. The credential destination is
preflighted before the server enrollment token is consumed. The client rejects
unsafe base URLs and redirects, and its representation and errors exclude token
material.

On POSIX, a temporary regular file is created with restrictive permission
before bytes are written, file content is flushed and fsynced, an atomic replace
is used, the parent directory is fsynced, and the final regular non-symlink file
is validated at mode `0600`. Unsafe ownership/mode/type/symlink conditions fail
closed.

On Windows, an atomic temporary file is ACL-protected before secret bytes are
written. The final protected DACL grants full control only to the current user,
SYSTEM, and Administrators; unrelated explicit ACEs are removed and inherited
access is disabled. The implementation then reads the effective SDDL through
the Windows security API and validates the allowed identities. A real Windows
ACL proof produced a protected DACL with those three principals and no broad
Users, Everyone, or Authenticated Users read access. Unsupported or failed ACL
enforcement aborts persistence; no raw token fallback is printed or retained.

Agent logging sanitizes messages and structured arguments, emits exception type
instead of arbitrary provider/transport exception text, and raises transport
and cloud SDK logging thresholds. Persisted plugin diagnostics contain bounded
type/status metadata only. Agent config and client representations do not reveal
the credential.

## Browser and frontend boundary

Browser authentication remains HttpOnly-cookie based. Product source contains
no authentication secret read/write to `localStorage`, `sessionStorage`, query,
or path. Secret form state remains component-local and is cleared on successful
submission, cancellation, navigation/unmount, tenant switch, and session
failure. Frontend error handling accepts bounded known messages but does not
stringify unknown structured response bodies; credential-shaped errors become a
generic safe message. `TOPO_BACKEND_URL` validation rejects userinfo, query, and
fragment before Next proxy construction.

## Scanner expansion

The SEC-1 scanner adds OpenAI, Groq, GitHub, Topo API/agent/enrollment prefixes,
Basic authentication, credential-bearing database URLs, and the three legacy
credential environment names. Existing patterns remain. Findings report path,
line, category, and a safe hint only—not the matched value. Synthetic positive,
safe-output, and placeholder/negative tests cover each addition. Both tracked
and untracked/new files are scanned before acceptance.

## Preservation and custody

PH-4D uses the existing `secret_records` and `secret_versions` tables. Expected
and final schema is one Alembic head, `0011_secret_enforce`, 45 ORM tables, and
804 ORM columns. Migration 0012 does not exist. Canonical committed Git content
for migrations 0001–0011 remains the authority:

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
| 0010 | 4303D0826DCE3E8FB0750A376CB68B8ABCBA7E1D62296BEE23A1782EAA3EDCF4 |
| 0011 | 15E89A6B4BDF00FC7334E7A7D0128251B378803A98771700066568683F234DF8 |

Protected binary actual-byte authorities are:

- `backend/data/topo.db`:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- Frozen LINEAGE `evaluation/results/lineage/post-sc4/topo-product-32695735269.db`:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

No migration or protected database is changed or rebaselined. The SecretStore
root/envelope design, PH-4C provider/webhook architecture, one-way credential
digests, tenant authority, canonical identities, and causal/evidence semantics
remain unchanged.

## Remaining limits

PH-4D does not claim protection from a fully compromised application process,
an operator holding both the database and root key, memory scraping, a database
superuser integrity attack, absence of HSM/FIPS facilities, full network/SSRF
controls, general customer-data egress, complete retention/deletion policy,
backup/key escrow rehearsal, or minimum-role RBAC. Database bootstrap material
remains deployment custody. Platform proof applies to the explicitly tested
POSIX semantics and Windows ACL implementation/environment.

## PH-4E handoff

PH-4E must independently attack database-read confidentiality; missing, wrong,
and retired root keys; provider/webhook rotation; installation OpenAI/Groq/GitHub
credentials; logs, errors, and representations; Pydantic validation; URLs and
redirects; SQL errors; browser storage; CLI and keyring behavior; agent files and
ACLs; provider receipts and dead letters; LLM/GitHub outbound transport; backup
ciphertext/key separation; and scanner coverage. It should add no new foundational
secret architecture if PH-4D is accepted.

## Verification receipts

All product checks below ran after the final product source change:

| Gate | Final result |
| --- | --- |
| Backend compile | PASS, exit 0 |
| Full backend default/SQLite | 1429 passed, 219 skipped, 2 existing warnings, 454.11s |
| Full backend PostgreSQL-enabled | 1640 passed, 8 dialect/environment skips, 2 existing warnings, 965.40s |
| Explicit PostgreSQL backup/restore | 1 passed, not skipped, 7.32s |
| PH-4B/PH-4C/outbound credential focused | 190 passed, 6 dialect skips, 1 existing warning, 53.69s |
| PH-2 + PH-3 focused | 183 passed, 2 existing warnings, 58.45s |
| Exact route-accounting tests | 3 passed, 1 existing warning, 5.23s |
| Evaluation compile / full evaluation | PASS / 917 passed, 3 existing Windows skips, 68.75s |
| GitHub source/build/artifact lineage | 176 passed, 6.80s |
| Mocked LLM and tenant outbound context | 148 passed, 1 existing warning, 17.21s |
| CLI compile / full CLI | PASS / 79 passed, 4.46s |
| Agent compile / full agent | PASS / 22 passed, 1 Windows privilege skip, 10.72s |
| Focused agent credential custody | 7 passed, 1 skipped because this identity cannot create a symlink, 8.21s |
| Isolated Linux/POSIX credential proof | PASS: pre-write mode 0600, final mode 0600, atomic replace and parent fsync used, symlink rejected, failed-write temp absent |
| Frontend tests | 90 passed, 0 failed |
| Frontend typecheck | PASS, exit 0 |
| Frontend lint | PASS: 0 errors, 11 pre-existing warnings outside the PH-4D frontend files |
| Frontend production build | PASS; optimized compile and all 14 pages generated |
| SEC-1 scanner tests | 11 passed, 0.15s |
| Tracked-tree scan | PASS, zero findings |
| New-file scan | 9 files, zero findings |
| Route inventory | 143 total: 116 tenant-required, 9 machine-bound, 7 tenant-control, 9 security-global, 2 public; unknown 0; new routes 0 |
| ORM / migration | 45 tables, 804 columns; one head `0011_secret_enforce`; migration 0012 absent |
| `git diff --check` | PASS, exit 0 |

The PostgreSQL proof used only task-owned disposable container
`topo-ph4d-postgres-16`, image `postgres:16-alpine`, exact ID
`1a9d8c2c12faf9fab4bbc7b7febc49b45736d29b06ebba4c2e5aadcf9b96cfc3`,
loopback `127.0.0.1:55444`, and tmpfs
`/var/lib/postgresql/data:rw,noexec,nosuid,size=512m`; `Mounts=[]`. The test URL
and password were synthetic and local to the disposable database. Final review
re-verified name, image, ID, loopback binding, and tmpfs, then stopped the exact
container. It was created with `--rm`; final exact-ID/name inspection found it
absent. No persistent named volume or customer database was used.

The full PostgreSQL run's eight skips are the established dialect/environment
variants; the PostgreSQL SecretStore concurrency and explicit backup/restore
proofs ran. The full SQLite run's 219 skips are PostgreSQL-specific proofs, not
silent deselection. Existing warnings are the Starlette/httpx deprecation and
the intentional SQLAlchemy duplicate-identity warning in the tenant adversarial
test. The one agent skip is explicitly limited to symlink creation unavailable
to the Windows test identity; regular-path Windows ACL protection was exercised
and passed. An additional network-disabled, read-only disposable Linux container
mounted the final agent source read-only and proved restrictive pre-write/final
mode, atomic replacement, parent fsync, symlink rejection, and failed-write
cleanup with synthetic material. A real Windows proof produced
`D:PAI(A;;FA;;;BA)(A;;FA;;;SY)(A;;FA;;;S-1-5-21-…-1002)`, with no broad Users,
Everyone, or Authenticated Users ACE. Its exact temporary proof file and empty
directory were removed after validation.

The final frontend build had network access for the existing Google Fonts and
completed successfully. Lint's 11 warnings predate this block and are not in the
PH-4D frontend changes; there are no lint errors. Tests make no live OpenAI,
Groq, GitHub, cloud-provider, or Kubernetes call.

A preliminary route-only command mistyped one frozen test node ID and therefore
failed collection before executing a test. The corrected exact three-test
command passed, and both complete backend suites plus the 183-test PH-2/PH-3
pack independently cover the same route contract. No assertion or test was
weakened.

Final custody re-hashed migrations from committed Git blob bytes and the two
protected databases from actual file bytes. All values match the authorities
above. There is no migration diff, migration 0012, protected database change,
evaluator/workflow change, staged file, or Git history operation.

No installation-credential, redaction, agent-custody, redirect, security,
active-exposure, schema, or custody blocker remains. The PH-4D verdict is PASS.
Architect review remains required before staging or committing.

PH-4D ACCEPTED / READY FOR ARCHITECT REVIEW
