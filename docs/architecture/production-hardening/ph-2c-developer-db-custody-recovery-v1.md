# PH-2C — Developer DB Custody Recovery v1

Date: 2026-08-29

## Scope

This note records the controlled recovery of the local developer SQLite database after a PH-2C test-harness dependency-isolation defect. It does not change production database infrastructure, migration authority, or frozen evaluation evidence.

The previous PH-1 developer DB SHA represented an unmanaged local-development artifact, not customer or evaluation evidence truth. Historical PH-1A and PH-1E records therefore remain unchanged. This note supersedes the earlier hash only for current developer DB custody.

## Custody incident

- Previous accepted developer DB SHA-256: `C3A2AB62DC6B8B8C68DEDFD26B858EBB3BB7199323217BE96B7764AEF7821BAF`
- Contaminated developer DB SHA-256: `ED95B8EC872B63C83340968E2F4256C541ADFFA0069A892E38EA201561400487`
- Cause: a PH-2C test created an isolated auth-session database but did not override FastAPI's existing `get_session` dependency. Calls to the agent-enrollment route therefore resolved the global `SessionLocal` and wrote to the default developer SQLite database.
- Proven contamination: four unintended, unused, unrevoked, single-use `agent_enrollment_tokens` rows.
- No migration, Alembic stamp, or schema mutation occurred.
- The exact previous byte-level artifact was unavailable and is not claimed to have been restored.

The contaminated artifact and a local-only manifest were durably quarantined outside Git under:

```text
$env:LOCALAPPDATA\TopoAI\custody\ph-2c\
```

## Logical recovery

A byte copy of the quarantined artifact was used as a separate repair candidate. Before mutation, the candidate was required to contain exactly the four accepted contamination timestamps, and every matching row was required to have `max_uses = 1`, `use_count = 0`, and no revocation timestamp.

One explicit transaction deleted exactly those four proven rows. No other enrollment record or table was changed. The candidate was not migrated, stamped, normalized, vacuumed, or reindexed.

Verification established:

- `PRAGMA quick_check`: `ok`
- `PRAGMA integrity_check`: `ok`
- tables: `41`
- columns: `725`
- `auth_sessions`: absent
- `alembic_version`: absent
- `agent_enrollment_tokens`: `13` rows after repair
- every other table: identical deterministic row count and content SHA-256
- schema fingerprint: unchanged

## Developer DB custody baseline V2

The verified repaired candidate establishes:

```text
0982D5C6A14BF323E173A5727529940F5C1A040A3F821E42D818423FFAB18D3E
```

This is **Developer DB Custody Baseline V2**, established by controlled logical recovery after proven PH-2C test-harness contamination. It is not described as restoration of the previous `C3A2...1BAF` byte-level artifact.

## Test-isolation repair

The PH-2C `session_app` fixture now overrides the exact FastAPI `get_session` dependency for the lifetime of the test application. Auth-session persistence and agent-enrollment route persistence consequently use the same disposable in-memory session factory.

A narrow regression replaces the global product `SessionLocal` with a fail-fast sentinel while invoking the enrollment route. The request must still succeed, and both the auth session and enrollment token must be present only in the in-memory database. This prevents recurrence without adding a production bypass or changing production persistence behavior.

A suite-wide database guard was intentionally not added. Existing backend tests include legitimate persistence and migration coverage, so a global prohibition would be invasive; the exact cross-dependency failure is instead guarded at its source.

## Preserved authorities

- Frozen LINEAGE database SHA-256 remains `9F3918A027C6D9A7BBD679495C48B387C9A1AC8C86141F85CF8B4495CD00B69F`.
- Alembic `0001_current_schema_baseline.py` SHA-256 remains `B02368D0D15445417A5EDE9445A267F34DA9D50DDDB181870D972BD23124B8A6`.
- PH-2C production implementation and database infrastructure are unchanged by this recovery.
