# PH-4E — Adversarial secret-custody acceptance and PH-4 closure v1

## Verdict

`PASS_PH4_CLOSE`

PH-4E independently attacked the accepted PH-4A/B/C/D design before changing
product code. The corrected unchanged-product baseline exposed one real defect:
the central text redactor did not recognize credential-bearing PostgreSQL URLs.
The original zero-marker assertion was preserved, a four-line bounded redaction
repair was applied, and every focused, full-regression, platform, scanner,
backup, and custody gate passed afterward.

Repository: `C:\Topo-ai`. Branch:
`security/ph-4e-adversarial-secret-custody-acceptance-v1`. Accepted starting
HEAD: `4ef68beac3668b6dc52a750cdab3e8357013df72`
(`4ef68be feat(security): harden outbound secret boundaries (#83)`). The starting
worktree was clean. No Git history or index mutation was performed.

## Acceptance-first defect trace

The permanent hostile corpus was written and run against unchanged PH-4D
product code. After correcting test-to-contract mistakes, the baseline was 27
passed, 1 failed, and 18 PostgreSQL-only skipped under default/SQLite execution.
The sole product failure was
`test_database_validation_logging_repr_and_traceback_boundaries_are_zero_marker`:
a synthetic database password remained present in a logged
`postgresql://user:password@host/database` value.

The first divergence was `app.security.secret_redaction.safe_text()`. It handled
HTTP(S) URLs, bearer/basic values, credential prefixes, and assignments, but did
not classify PostgreSQL or SQLAlchemy driver-qualified PostgreSQL URLs before
log rendering. The bounded repair adds a database-URL expression for
`postgres://`, `postgresql://`, and `postgresql+driver://` and replaces the
complete matched URL with the existing `UNAVAILABLE` marker. No lookback,
tenant, provider, webhook, encryption, persistence, causal, or evidence
semantics changed. The failing assertion was not weakened or removed.

The pre-product test corrections were: supply the required installation ID;
reset module-scoped database state between cases; use replay result field
`succeeded`; call `create_test_event` with its real positional contract; unwrap
test-only `SecretStr` through `get_secret_value()`; and assert the frontend's
actual keyed-Fragment tenant remount. The explicit new-file scanner later
identified two scanner-shaped randomized database URL literals in the test
source; those fixtures now construct the identical hostile values at runtime.
These were fixture/source-hygiene corrections, not product repairs. Two tooling
interruptions were environment-only: the managed sandbox initially denied a
venv executable until the approved repository command was used, and a generic
Python Alpine image was not local, so the already-local Topo Agent Linux image
was used for the network-disabled POSIX proof.

## Permanent hostile corpus

- `backend/tests/test_ph4e_adversarial_secret_custody.py` exercises SQLite and
  PostgreSQL storage, binding authorization, roots/rewrap, all six inbound
  provider modes, dead letters, outbound webhooks, installation integrations,
  public validation, logging, representations, SQL, and route/env authority.
- `backend/tests/test_ph4e_secret_backup_postgres.py` performs a real
  `pg_dump`/drop/create/`pg_restore` ciphertext and root-key-separation proof.
- `cli/tests/test_ph4e_adversarial_client_custody.py` attacks profile/keyring,
  redirect, representation, and remote-error boundaries.
- `agent/tests/test_ph4e_adversarial_agent_custody.py` attacks argv/preflight,
  restrictive local persistence, write failure, and raw fallback.
- `frontend/test/secret-custody-adversarial.test.mjs` attacks browser storage,
  request-body, tenant-switch, form-reset, and response-type boundaries.
- `scripts/security/tests/test_check_tracked_secrets.py` adds randomized
  positive and safe negative scanner cases without rendering matched values.

Counting parameterized database/provider executions, the permanent corpus has
45 test-runner hostile cases (38 backend, 2 CLI, 2 agent, 3 frontend), seven
new scanner positive/negative subscenarios, and one isolated POSIX probe: 53
explicit adversarial checks. All values are independently randomized synthetic
markers; no real credential or live provider was used.

## Secret-custody findings

Database-read and domain-table raw reversible-secret counts were zero on both
SQLite and PostgreSQL. Wrong root material failed with
`SECRET_DECRYPT_FAILED`; absence of a required live key failed readiness with
`SECRET_REQUIRED_KEY_MISSING`; expiry of the previous version removed the old
key requirement; revoked material did not require a retired key. Interrupted
rewrap left ciphertext, key ID, envelope revision, active version, and row
version unchanged. Successful rewrap retained provider material version 1,
changed only envelope custody, and allowed retirement of the old root.

GitHub HMAC, GitLab signing, GitLab shared-token, Terraform Cloud, Jenkins, and
Azure DevOps authentication all passed active/previous-window verification,
expiry, revoke, and explicit reprovision attacks. Invalid proof was rejected
before body parsing. Persisted provider headers, delivery rows, errors, and
dead letters contained zero credential markers. Dead-letter replay did not
reload retired provider material. Cross-tenant reference copying and purpose
swaps failed before decryption.

Outbound webhook delivery sent signing/protected-header material only to the
configured intended sink, did not follow a 302, did not persist the remote echo,
and supported replacement and explicit clearing. Cross-tenant and cross-purpose
reference swaps failed closed. OpenAI, Groq, and GitHub installation bindings
were exact installation-scope, exact-purpose, active-only, zero-overlap,
revocable, and non-interchangeable. Runtime reads of legacy installation
environment authorities remained zero; only the bounded local import command
retains the known-name import map.

Raw marker counts were zero across database-password diagnostics, SQL bound
parameters, FastAPI validation, Pydantic representations, logs, tracebacks,
persisted errors, LLM errors, GitHub errors, CLI profiles/errors, agent
stdout/stderr/debug diagnostics, foreign redirect sinks, browser storage, and
ordinary operator output. The only permitted raw outputs remain deliberate
one-time channels: explicit CLI token stdout and intended authenticated request
sinks. They do not duplicate material into stderr, tables, logs, persistence,
or redirects.

Depth and item caps returned the fixed truncation marker without traversing
unvisited hostile values. Benign `token_count`, `token_budget`, `token_hint`,
`secret_ref`, and `credential_id` metadata remained visible. Bearer, Basic,
HTTP(S), and PostgreSQL URL redaction passed.

## Platform custody

The real Windows proof created a synthetic credential through production code.
Its DACL was protected and had only the current SID,
`SYSTEM` (`SY`), and Administrators (`BA`); Everyone (`WD`), Users (`BU`), and
Authenticated Users (`AU`) were absent. Focused Windows custody finished 9
passed and 1 skipped: the current Windows identity cannot create the symlink
used by that one platform test. Regular Windows ACL enforcement and injected
write failure both ran and passed.

An isolated Linux container used the final agent source mounted read-only,
`--network none`, a read-only root filesystem, and task-only tmpfs. It proved
mode `0600` before the first raw-byte write, final mode `0600`, group/other bits
zero on the credential directory, symlink rejection, FIFO rejection, and
atomic cleanup for injected `write`, `fsync`, and `replace` failures. Existing
valid material remained intact and temporary artifact count was zero.

## Backup, database, and migration custody

The PostgreSQL backup proof restored ciphertext byte-identically while the raw
marker, raw root key, and base64 root key were absent from the dump. Restored
readiness failed without the required key, decryption failed with wrong material
under the matching key ID, and the separately held correct root decrypted the
restored record. The existing representative-history backup/restore test also
ran in the full PostgreSQL suite. This proves PH-4 separation behavior; it does
not claim PH-8 operational backup/key-escrow closure.

The disposable database was PostgreSQL 16.15 at READ COMMITTED in container
`topo-ph4e-postgres-16`, image `postgres:16-alpine`, exact ID
`0102ecbe85bc0ddd0f9076728f428b796c1a439dd2c185e4824313f4e236ed32`,
bound only to `127.0.0.1:55445`. Data used tmpfs
`/var/lib/postgresql/data:rw,noexec,nosuid,size=512m`; `Mounts=[]`, so no
persistent named volume existed. It was created with `--rm`; final exact-ID and
name inspection found it absent.

Final schema remains 45 ORM tables, 804 ORM columns, one Alembic head
`0011_secret_enforce`, with no new table, migration 0012, or existing migration
diff. Canonical committed Git-content SHA-256 values before and after are:

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

Protected binary actual-byte hashes also remained exact:

- Developer DB before/after:
  `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
- Frozen LINEAGE before/after:
  `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.

## Verification receipts

| Gate | Final result |
| --- | --- |
| Hostile backend, SQLite + PostgreSQL + backup | 38 passed, 1 existing warning, 83.99s |
| PH-4B/C/D SecretStore/provider/webhook/outbound focused | 190 passed, 6 expected skips, 1 existing warning, 73.27s |
| PH-2/PH-3 auth/tenant focused | 248 passed, 1 expected skip, 2 existing warnings, 594.97s |
| Causal/truth/GitHub/LLM preservation pack | 329 passed, 1 existing warning, 24.04s |
| GitHub Actions source/build/artifact lineage | 87 passed, 8.26s |
| Mocked LLM/briefing/memory/response/tenant/outbound | 120 passed, 1 existing warning, 22.58s |
| Full backend default/SQLite final | 1449 passed, 237 PostgreSQL/platform skips, 2 existing warnings, 638.72s |
| Full backend PostgreSQL-enabled final | 1678 passed, 8 dialect/environment skips, 0 failures/errors, 2 existing warnings, 1271.886s |
| Full evaluation | 917 passed, 3 existing Windows skips, 94.57s |
| CLI compile / full CLI | PASS / 81 passed, 4.85s |
| Agent compile / full agent | PASS / 24 passed, 1 Windows symlink-privilege skip, 10.18s |
| Focused Windows agent custody | 9 passed, 1 symlink-privilege skip, 11.40s |
| Isolated POSIX custody | PASS: pre-write/final `0600`; symlink/FIFO rejected; write/fsync/replace cleanup passed |
| Frontend tests | 93 passed, 0 failed |
| Frontend typecheck | PASS |
| Frontend lint | PASS: 0 errors, 11 pre-existing warnings |
| Frontend production build | PASS: optimized build; all 14 routes generated |
| Scanner tests | 12 passed; randomized positive and negative subscenarios passed |
| Tracked-tree scanner | PASS, zero findings |
| New-file scanner | PASS, zero findings |
| Backend/evaluation/CLI/agent compile | PASS |
| ORM/Alembic | 45 tables, 804 columns; one head `0011_secret_enforce` |
| Production route inventory | 143 total; 0 new; 0 unknown; 0 SecretStore admin/decrypt/list routes |
| `git diff --check` | PASS |

The PostgreSQL run exercised READ COMMITTED and all four SecretStore CAS
combinations: rotate/rotate, rotate/revoke, rotate/rewrap, and rewrap/rewrap.
Provider conversion/concurrency and the existing PostgreSQL logical
backup/restore case passed. Evaluation did not execute Kubernetes or live
providers, and all LLM/provider transports were mocked or disabled. The two
warnings are the established Starlette/httpx deprecation and intentional
SQLAlchemy duplicate-identity warning. Frontend lint's 11 warnings predate
PH-4E and are outside its changed frontend files.

## Numbered completion record (1–196)

1. Scope: independent hostile acceptance of PH-4A/B/C/D and PH-4 closure only.
2. Accepted starting main commit: `4ef68beac3668b6dc52a750cdab3e8357013df72`.
3. Branch: `security/ph-4e-adversarial-secret-custody-acceptance-v1`.
4. Verdict: `PASS_PH4_CLOSE`.
5. Product code changed: YES, only after the preserved hostile failure.
6. Product file changed: `backend/app/security/secret_redaction.py`.
7. Test files changed: five new surface tests plus the scanner-test extension.
8. Docs changed: this one PH-4E closure document.
9. Scanner file changed: `scripts/security/tests/test_check_tracked_secrets.py`.
10. Frontend files changed: one hostile test and `package.json` test registration.
11. CLI file changed: one hostile test; CLI product code unchanged.
12. Agent file changed: one hostile test; agent product code unchanged.
13. Migration created: NO.
14. Alembic head count: 1.
15. Alembic head: `0011_secret_enforce`.
16. 0001 before/after: `B13506D8BD25C1018A3516395D2ED3B8994DB76A70113BE29FD2D656EB0F6EFD`.
17. 0002 before/after: `DB13AF3CCE4D85AFB210040B76D30F3231D3F02A175B00F34FEF8DF82C80CE92`.
18. 0003 before/after: `907F0F815FC907786675F347226002568D9E04863C8D1F4CA225E1323FC7426F`.
19. 0004 before/after: `D2F1A673D51BA76883D5B81C62669A730B19FAB9951188CA0C1903B0B55BCCD3`.
20. 0005 before/after: `14F7E50B3A82FFBD99FEFB041D63D4710C0ED1E20D2442457A3922B0BA899333`.
21. 0006 before/after: `D17DD14445072E5B3C3BFA0822516F5232ED1BC9E1B8E280989910D26BBC3728`.
22. 0007 before/after: `8F2B0D16C0C55D650BC9D2DD740A588E7F2C93DFAE6255AC0FAFF6F1B1309B84`.
23. 0008 before/after: `9F69829593E49F53AD5D3D47AD3F7DFA94EF8437681EA3E7F06D86AB1E1553A7`.
24. 0009 before/after: `20B1109D75E78F511B346F1D85DA8FA7FB9F6CAA8B8A92347A2859BA2D35CA5C`.
25. 0010 before/after: `4303D0826DCE3E8FB0750A376CB68B8ABCBA7E1D62296BEE23A1782EAA3EDCF4`.
26. 0011 before/after: `15E89A6B4BDF00FC7334E7A7D0128251B378803A98771700066568683F234DF8`.
27. Existing migration changes: NONE.
28. ORM table count: 45.
29. ORM column count: 804.
30. New tables: 0.
31. Hostile scenarios: 53 explicit checks under the accounting above.
32. Initial corrected baseline pass count: 27.
33. Initial corrected baseline failure count: 1; 18 PG-only skips.
34. Real product defects: 1, credential-bearing PostgreSQL log text.
35. First divergence: central `safe_text()` database-URL classification.
36. Bounded repair: replace PostgreSQL/driver-qualified URL text with `UNAVAILABLE`.
37. Failure-reproducing assertion preserved: YES.
38. Fixture/test mistakes: six contract-alignment categories plus scanner-safe literal construction, detailed above.
39. Environment-only failures: two tooling interruptions; zero final gate failures.
40. DB-read plaintext marker count: 0.
41. Domain-table plaintext marker count: 0.
42. Backup plaintext marker count: 0.
43. Wrong-root-key result: `SECRET_DECRYPT_FAILED`.
44. Missing-active-key result: readiness `SECRET_REQUIRED_KEY_MISSING`.
45. Missing-live-old-key result: readiness `SECRET_REQUIRED_KEY_MISSING`.
46. Expired-previous old-key result: old key no longer required.
47. Rewrap result: atomic; interrupted state unchanged; successful retirement passed.
48. Provider material version after rewrap: 1, unchanged.
49. GitHub provider acceptance: PASS.
50. GitLab signing acceptance: PASS.
51. GitLab shared-token acceptance: PASS.
52. Terraform acceptance: PASS.
53. Jenkins acceptance: PASS.
54. Azure acceptance: PASS.
55. Verify-before-parse: PASS.
56. Provider env runtime fallback count: 0.
57. Provider auth-header durable marker count: 0.
58. Provider rotation/expiry: bounded previous accepted then expired; PASS.
59. Provider revoke: revoked material rejected; PASS.
60. Provider reprovision: explicit reprovision only; PASS.
61. Provider A/B collision isolation: PASS.
62. Provider reference swap: rejected before decrypt.
63. Provider purpose swap: rejected before decrypt.
64. Dead-letter replay: PASS without secret reload.
65. Webhook signing: PASS at intended sink only.
66. Webhook protected header: PASS at intended sink only.
67. Webhook replacement: PASS.
68. Webhook clear: PASS.
69. Webhook cross-tenant reference attack: rejected.
70. Webhook purpose swap: rejected.
71. Webhook remote echo marker count: 0 persisted/returned.
72. Webhook redirect: 302 not followed; one intended request, zero foreign requests.
73. OpenAI installation binding: PASS.
74. Groq installation binding: PASS.
75. GitHub installation binding: PASS.
76. Installation runtime env reads: 0.
77. Installation cross-purpose attack: rejected.
78. Installation tenant-scope attack: rejected.
79. Installation rotation/revoke: active-only zero-overlap and revoke passed.
80. Arbitrary env oracle: absent; only fixed known-name import map exists.
81. Operator output marker count: 0 in ordinary status/receipts.
82. DB-password output marker count: 0.
83. SQL bound-parameter marker count: 0.
84. FastAPI validation marker count: 0.
85. Pydantic repr marker count: 0.
86. Log marker count: 0.
87. Traceback marker count: 0.
88. Persisted-error marker count: 0.
89. LLM exception marker count: 0.
90. GitHub exception marker count: 0.
91. Redactor depth attack: fixed truncation, marker count 0.
92. Redactor item-cap attack: fixed truncation, marker count 0.
93. Benign `token_count` preservation: PASS.
94. Bearer redaction: PASS.
95. Basic redaction: PASS.
96. URL redaction: HTTP(S) and PostgreSQL/driver-qualified PASS.
97. CLI profile marker count: 0.
98. CLI insecure-keyring behavior: fail closed.
99. CLI redirect foreign bearer count: 0.
100. CLI default enrollment-token stdout: metadata only, raw count 0.
101. CLI explicit raw stdout: one intentional stdout value only; stderr/table count 0.
102. Agent raw argv path count: 0.
103. Agent redirect bearer count: 0 at foreign sink.
104. Agent enrollment redirect-body count: 0 at foreign sink.
105. POSIX pre-write mode: `0600`.
106. POSIX final mode: `0600`.
107. POSIX symlink attack: rejected; target unchanged.
108. POSIX failure cleanup: write/fsync/replace fail closed; temp count 0.
109. Windows real ACL: protected DACL, current SID + `SY` + `BA` only.
110. Windows broad-principal read access: 0 (`WD`, `BU`, `AU` absent).
111. Agent persistence preflight: PASS before enrollment material consumption.
112. Agent write-failure raw fallback: none; prior credential remains.
113. Agent debug marker count: 0.
114. Cloud SDK debug marker count: 0; relevant loggers bounded to WARNING+.
115. Browser localStorage marker count: 0.
116. Browser sessionStorage marker count: 0.
117. Browser form reset: PASS after submit/cancel/remount boundaries.
118. Browser error marker count: 0.
119. Tenant-switch secret state: keyed remount clears component-local material.
120. Scanner positive coverage: PASS for six PH-4E randomized categories.
121. Scanner negative coverage: PASS for safe placeholders/metadata.
122. Scanner raw-value output: 0.
123. Current active tracked secret found: NO.
124. Backup/restore ciphertext: restored byte-identically; raw count 0.
125. Backup root-key co-location: NO.
126. Restore without required key: readiness fails closed.
127. Restore with wrong key: decrypt fails closed; correct separate key succeeds.
128. SecretStore focused suite: PASS within 190-pass PH-4 pack.
129. Provider/webhook focused suite: PASS within 190-pass PH-4 pack.
130. Outbound/redaction focused suite: PASS within 190-pass PH-4 pack.
131. PH-2 focused: PASS within 248-pass PH-2/PH-3 pack.
132. PH-3 focused: PASS within 248-pass PH-2/PH-3 pack.
133. Route total: 143.
134. New HTTP routes: 0.
135. Unknown routes: 0.
136. SecretStore HTTP admin/decrypt/list routes: 0.
137. Full backend SQLite: 1449 passed, 237 skipped, 2 warnings.
138. Full backend PostgreSQL: 1678 passed, 8 skipped, 2 warnings, 0 failures/errors.
139. PostgreSQL concurrency: all required CAS/conversion cases passed at READ COMMITTED.
140. Evaluation: 917 passed, 3 existing skips.
141. GitHub lineage: 87 passed.
142. LLM focused: 120 passed with mocked/disabled transports.
143. CLI: compile PASS; 81 passed.
144. Agent: compile PASS; 24 passed, 1 platform skip.
145. Windows custody: 9 focused passed, 1 symlink-privilege skip; ACL proof passed.
146. POSIX custody: isolated networkless/read-only container proof PASS.
147. Frontend tests: 93 passed.
148. Frontend typecheck: PASS.
149. Frontend lint: 0 errors, 11 pre-existing warnings.
150. Frontend build: PASS, 14 routes generated.
151. Scanner tests: 12 passed.
152. Tracked scan: PASS, zero findings.
153. New-file scan: PASS, zero findings.
154. Backup/restore regression: existing history and new secret-separation proofs passed.
155. Compile checks: backend, evaluation, CLI, agent, TypeScript/build PASS.
156. `git diff --check`: PASS.
157. Developer DB before: `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
158. Developer DB after: `0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E`.
159. Developer DB unchanged: YES.
160. Frozen LINEAGE before: `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.
161. Frozen LINEAGE after: `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.
162. Frozen LINEAGE unchanged: YES.
163. Migrations 0001–0011 unchanged: YES, canonical Git bytes.
164. Closure gate one-way auth: PASS; digest-only authority preserved.
165. Closure gate reversible persistence: PASS; encrypted records only.
166. Closure gate root key: PASS; outside database/backup.
167. Closure gate tenant/purpose: PASS before decrypt.
168. Closure gate providers: PASS across six inbound modes.
169. Closure gate webhooks: PASS.
170. Closure gate installation credentials: PASS.
171. Closure gate DB credential: bootstrap exception retained and diagnostics redacted.
172. Closure gate errors/logs/validation: PASS, zero marker leakage.
173. Closure gate URL/redirect: PASS.
174. Closure gate CLI: PASS.
175. Closure gate agent: PASS on real Windows and isolated POSIX.
176. Closure gate browser: PASS.
177. Closure gate scanner: PASS.
178. Closure gate backup separation: PASS; PH-8 not claimed.
179. Closure gate custody: PASS for migrations and protected databases.
180. Closure gate regression: PASS across backend/evaluation/CLI/agent/frontend.
181. Foundation blocker: NO.
182. Security blocker: NO.
183. Active exposure blocker: NO.
184. Platform custody blocker: NO.
185. Custody blocker: NO.
186. First blocker: NONE.
187. PH-4 closed: YES.
188. Exact closure: PH-4 secret custody is accepted for its documented v1 threat model.
189. Exclusions: process compromise/memory scraping, operator holding DB+root,
     HSM/FIPS, full SSRF/network egress, general customer-data minimization,
     PH-8 operational backup/key escrow, and PH-5 minimum RBAC.
190. Remaining production-hardening phase: PH-5 — Minimum RBAC.
191. Files created: five hostile test files and this closure document.
192. Files modified: central redactor, frontend test registration, scanner tests.
193. `git status --short`: three tracked modifications and six untracked files;
     no protected, migration, evaluator, workflow, or unexpected path.
194. `git diff --name-only`: the three tracked modified paths only; untracked
     files are enumerated in the final status.
195. `git diff --cached --name-only`: empty.
196. STOP: confirmed; PH-5 and all later phases were not started.

PH-4E ACCEPTED / PH-4 CLOSED
