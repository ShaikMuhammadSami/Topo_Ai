# LINEAGE-1 Post-SC-1 Causal Baseline v1

Date: 2026-08-25

Branch: `evaluation/lineage-1-post-sc1-baseline-v1`

Final LINEAGE-1E verdict: **MISSING**

First divergence: **CAUSAL_CANDIDATE_MISSING**

## 1. Checkpoint purpose

This document permanently preserves the accepted LINEAGE-1E post-SC-1
measurement before SC-2 changes causal candidate admission. It is a
documentation checkpoint only. It does not modify or reinterpret product code,
evaluators, causal policy, provider state, Kubernetes state, or the frozen
experiment.

Before SC-1, the accepted first divergence was
`SOURCE_CHANGE_IDENTITY_WRONG`. LINEAGE-1E exercised the real signed GitHub and
provider-enrichment path and established that this divergence disappeared.

## 2. SC-1 live gate

SC-1 gate: **PASS**.

The real signed GitHub/provider path durably preserved the exact source
mutation:

| Field | Accepted observation |
|---|---|
| Repository | `ShaikMuhammadSami/Topo_Ai` |
| Repository ID | `1278498159` |
| Parent | `f9b152133a8075428766dd48b3f752b255ec5270` |
| Failure commit | `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe` |
| File | `evaluation/fixtures/lineage-image/runtime-mode.txt` |
| Change type | `modified` |
| Before provider blob | `a26ff891d28783dfe93a0b0a91850986ccd43993` |
| After provider blob | `9dae856c349e3e137b85a641d1ca206a7d41ff4e` |
| Before exact SHA-256 | `63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d` |
| After exact SHA-256 | `2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997` |
| Before bounded semantic value | `healthy` |
| After bounded semantic value | `fail` |
| Mutation completeness | `complete` |

`SOURCE_CHANGE_IDENTITY_WRONG` disappeared. The mutation survived signed
ingestion, live provider enrichment, normalized persistence, and fresh-session
repository readback with exact structural identity.

## 3. Preserved provenance chain

LINEAGE-1E recorded **PASS** for every provenance and incident-context hop:

- Repository -> Commit;
- Commit -> GitHub Actions run;
- Actions run -> immutable OCI image;
- Deployment `uses` Image;
- Deployment -> ReplicaSet;
- ReplicaSet -> Pod;
- Pod failure signal;
- automatic incident;
- incident-boundary topology pin; and
- affected exact Pod.

The independently established chain was:

```text
source commit
  -> GitHub Actions run
  -> immutable OCI image
  -> affected Deployment
  -> ReplicaSet
  -> failing Pod
```

## 4. Independent runtime truth

| Dimension | Accepted observation |
|---|---|
| OCI resolution | `EXACT_INDEX` |
| Exit code | `42`, independently proven |
| Restart count | `>= 1` |
| Runtime manifestation | `CrashLoopBackOff` / `BackOff` |
| Termination reason | `Error` |
| Deployment desired | `1` |
| Deployment ready | `0` |
| Deployment available | `0` |

This ground truth was established independently of Topo output.

## 5. Post-SC-1 causal measurement

Final LINEAGE-1E verdict: **MISSING**.

First divergence: **CAUSAL_CANDIDATE_MISSING**.

| Dimension | Measured value |
|---|---|
| Source-event effective time | `2026-08-24T06:02:03Z` |
| Incident boundary | `2026-08-24T19:12:00Z` |
| Exact gap | `47397` seconds / `789.95` minutes |
| Configured generic 13C lookback | `180` minutes |
| Candidate count | `0` |
| Exact source candidate | absent |
| Causal relevance | not reached |
| Top1 | none |
| Top3 supported | empty |
| Semantic level | `ABSTAINED` |

The exact source event did not receive an individual rejection-audit row
because it fell outside the initial bounded candidate query. Its durable
mutation identity was correct, but its provider-effective time was 789.95
minutes before the incident boundary and therefore outside the unchanged
180-minute generic lookback.

## 6. Architectural interpretation

The candidate failure is now temporal admission, not source identity. This is
not justification to globally widen the lookback.

The source mutation is old in wall-clock terms, but it is not merely an
unrelated historical change. Independent immutable provenance proves that its
commit produced the GitHub Actions run and immutable image actually used by the
affected Deployment whose ReplicaSet produced the failing Pod.

A future candidate-admission repair should therefore be based on direct
artifact/workload lineage rather than a larger generic time window.

## 7. Approved SC-2 boundary

Approved next repair:

**SC-2 — Lineage-Aware Causal Candidate Admission v1**

SC-2 may later permit an older source change to enter the candidate set only
when deterministic lineage proves that the candidate produced the artifact
actually used by the affected workload.

SC-2 explicitly does not authorize:

- a global lookback increase;
- timestamp rewriting;
- ranking changes;
- causal-relevance changes;
- score changes;
- Top1 forcing;
- LLM or fuzzy matching; or
- runtime exit-code repair.

## 8. Secondary downstream finding

Current Topo runtime evidence still exposed exit code `null`, while independent
runtime truth proved exit code `42`.

This remains a downstream observation and is **not** the next repair target.

## 9. Frozen post-SC-1 result identities

| Artifact | SHA-256 |
|---|---|
| Runtime receipt | `4DA7861ECE872E58959CC662A5E99FDD8F4BA7B5F42C17601496BDB144D364A7` |
| Topo product database | `857626A07DA79201DD420AAC20FA9F69EE4C19F9723AA9F133D8E9B4CAEF0421` |
| Topo observation | `73AE2C49E25EC105028BB7371076A0CA5E9BA7D477EF3255FF16809759EAC36B` |
| Final grade | `F360937E60107E9C7A5B5E711FAB726CDD1ABC49D4DE7F8E2869594538A31EE4` |
| Product diagnostics | `D3C7881E2DE27A3779AE96DF8CDDD496294B714D408E4B56945613847244B85D` |

These identify the ignored artifacts used for the accepted LINEAGE-1E
measurement. They are separate from, and do not overwrite, the frozen pre-SC-1
LINEAGE-1 result artifacts.

## 10. Measurement limit

This remains one deterministic scenario and is not statistically meaningful.
It proves only that:

- SC-1 corrected source mutation identity for this scenario;
- source/build/runtime provenance remains intact;
- the next measured divergence is candidate admission; and
- safe abstention remains preferable to unsupported attribution.

The frozen pre-SC-1 baseline remains authoritative for the measurement before
SC-1 and is not modified by this checkpoint.
