# LINEAGE-1 Final Source-to-Runtime Causal Baseline v1

Date: 2026-08-24

Branch: `evaluation/lineage-1-final-baseline-v1`

Final LINEAGE-1 verdict: **MISSING**

First divergence: **SOURCE_CHANGE_IDENTITY_WRONG**

## 1. Scope

LINEAGE-1D is a documentation and evaluation checkpoint only. It permanently
preserves the accepted LINEAGE-1C-FINAL measurement before any product repair.
It does not modify product code, evaluators, workflows, provider state, or the
frozen experiment.

This baseline records one preserved source-to-runtime causal scenario. It is
not a rerun and does not use current external state to reinterpret the accepted
result.

## 2. Frozen source experiment

- Healthy parent:
  `f9b152133a8075428766dd48b3f752b255ec5270`
- Failure commit:
  `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`
- Changed-file count: `1`
- Changed file:
  `evaluation/fixtures/lineage-image/runtime-mode.txt`
- Mutation: `healthy -> fail`
- Failure source SHA-256:
  `2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997`
- Expected deterministic failure mechanism: process exit code `42`

## 3. Frozen provider experiment

- GitHub Actions run: `32695735269`
- Run attempt: `1`
- Provider OCI index:
  `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed`

The accepted provider evidence tied the exact failure commit and run attempt to
this immutable OCI index. That evidence was frozen before Topo was graded.

## 4. Independently proven runtime truth

- Exit code: `42`
- Restart count: `>= 1`
- Runtime manifestation: `BackOff / CrashLoopBackOff`
- Termination reason: `Error`
- Deployment desired replicas: `1`
- Deployment ready replicas: `0`
- Deployment available replicas: `0`
- UID ownership: exact
  `Deployment -> ReplicaSet -> Pod`

The runtime receipt established the intended baked source-controlled failure
mechanism independently of Topo output.

## 5. Current Topo result matrix

| Dimension | Result | Accepted observation |
|---|---|---|
| Repository identity | **PASS** | Exact repository identity was preserved. |
| Parent/failure commit identity | **PASS** | Exact parent and failure commit were preserved. |
| Repository -> Commit | **PASS** | Exact repository-to-commit relationship was present. |
| Commit -> Actions | **PASS** | Exact commit linked to run `32695735269`, attempt `1`. |
| Actions -> Image | **PASS** | Provider build evidence linked the run to the immutable OCI index. |
| Image -> Deployment association | **PASS** | The real graph represented the workload-to-image association as Deployment `uses` Image. |
| Deployment -> ReplicaSet | **PASS** | Exact Kubernetes owner UID relationship was present. |
| ReplicaSet -> Pod | **PASS** | Exact Kubernetes owner UID relationship was present. |
| Pod BackOff evidence | **PASS** | Structured BackOff evidence resolved to the exact Pod. |
| Automatic incident | **PASS** | The 15D lifecycle automatically created the incident. |
| Affected Pod | **PASS** | The incident resolved the exact runtime Pod. |
| Incident-boundary topology pin | **PASS** | The incident pinned the exact signal-associated boundary checkpoint without a latest-snapshot fallback. |
| Changed file identity | **FAIL** | The normalized source change did not retain the changed file path. |
| Before source value | **FAIL** | The normalized source change did not retain `healthy`. |
| After source value | **FAIL** | The normalized source change did not retain `fail`. |
| Source causal candidate | **MISSING** | The exact source mutation did not enter the causal candidate set. |
| Supported Top1 | **NONE** | No supported Top1 hypothesis was produced. |
| Supported Top3 | **EMPTY** | No supported Top3 hypotheses were produced. |
| Topo behavior | **ABSTAINED** | Topo did not fabricate a root cause from insufficient evidence. |

## 6. Final causal verdict

Final LINEAGE-1 verdict: **MISSING**.

First divergence: **SOURCE_CHANGE_IDENTITY_WRONG**.

The GitHub/source change was ingested, but its durable normalized identity did
not preserve the provider-authentic per-file mutation required by the frozen
Level-1 target. Repository, parent, commit, build, image, runtime, incident,
and topology evidence could not substitute for the missing file-level source
identity.

First-divergence discipline therefore places the first future repair boundary
at source-change identity. It does not permit candidate selection, lookback,
relevance, or ranking changes to be treated as the first repair.

## 7. Secondary downstream findings

These are recorded separately and explicitly are **not** the first repair
target:

1. The source event occurred about `419` minutes before the incident and
   therefore fell outside the current 13C `180`-minute lookback.
2. Current product runtime evidence did not expose container termination exit
   code `42`, although the independent runtime receipt proved it.

These observations do not authorize either behavior to be repaired yet.

## 8. Provenance and causal-attribution conclusion

Full provenance was proven for this one preserved scenario:

```text
Repository
  -> Commit
  -> GitHub Actions run
  -> immutable OCI image
  -> Deployment
  -> ReplicaSet
  -> Pod
  -> BackOff failure evidence
```

Source-level causal attribution was **not** proven. The product could establish
where the artifact came from and where it failed, but it could not identify the
exact `runtime-mode.txt: healthy -> fail` mutation as a supported cause.

Topo's abstention was preferable to unsupported attribution. It preserved the
difference between complete provenance and incomplete causal proof.

## 9. Measurement limits

This is one deterministic preserved scenario. It is not statistically
meaningful and does not establish a general product accuracy, recall, or
probability claim.

The result establishes only that, for this scenario:

- source-to-runtime provenance was complete;
- source-level causal attribution was missing;
- the first failure occurred in source-change identity; and
- Topo safely abstained instead of selecting an unsupported cause.

## 10. Frozen ignored result hashes

| Result | SHA-256 |
|---|---|
| Runtime receipt | `23129D11D453C6C6C55A659CC19D39397DBCB9E3A5934D0F0E96F65DC0BB2C4D` |
| Topo observation | `BAAA4EA3CC4D2C8FC78D0F1A8108A3868C07F145043470600A18AE478BF5848F` |
| Final grade | `E301DCBC9563B87B0CD4B7BB86E4BBCB2885CE8E56D4FB680E0CCB0B74151583` |

These hashes identify the ignored artifacts used for the accepted final
measurement. They must not be regenerated or reinterpreted as part of this
documentation checkpoint.

## 11. Architect decisions

### A. Preserve per-file source mutations

Durable GitHub/source change intelligence should preserve provider-authentic
per-file mutations as structured change evidence. The evidence must retain the
identity needed to distinguish the exact changed file and before/after source
state without fuzzy title matching, an LLM, or evaluator truth being fed into
the product.

### B. Keep the global lookback bounded

Do not globally widen the current `180`-minute causal lookback. A global
increase would admit more unrelated historical changes and would not repair
the first missing source-change identity.

### C. Measure a lineage-aware admission rule separately

A future, separately designed and measured repair may admit an older source
mutation only when direct immutable lineage proves:

```text
source commit
  -> Actions run
  -> immutable image
  -> recently activated affected workload
```

That future rule must remain deterministic, evidence-backed, bounded, and
separate from this baseline. It must not be implemented before source-change
identity is repaired and remeasured.

## 12. Frozen interpretation

The accepted conclusion is:

> Topo proved the complete provenance chain for one preserved failure scenario,
> but it did not preserve the file-level source mutation needed to prove the
> initiating root cause. The correct final verdict is MISSING, the first
> divergence is SOURCE_CHANGE_IDENTITY_WRONG, and abstention was the safe
> behavior.

This baseline is the permanent pre-repair checkpoint for LINEAGE-1.
