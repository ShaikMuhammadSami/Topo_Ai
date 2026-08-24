# LINEAGE-1C Runtime Causal Observation v1

Date: 2026-08-24

Branch: `evaluation/lineage-1-runtime-causal-observation-v1`

Final measurement verdict: **INCONCLUSIVE**

Reason: **INCONCLUSIVE_GROUND_TRUTH**. The exact private GHCR digest was
accepted by the Deployment specification but could not be pulled into the
local cluster with the already-authorized credentials. The container never
started, so structured exit code 42 and restart/backoff truth did not exist.
Topo output was therefore neither inspected nor graded.

## 1. Scope

LINEAGE-1C adds evaluation-only runtime and source-cause contracts. Product,
workflow, fixture template, failure branch, and permanent manifests are
frozen. No product repair was attempted.

## 2. Frozen LINEAGE-1B truth revalidation

- Repository: `ShaikMuhammadSami/Topo_Ai` (`1278498159`)
- Parent: `f9b152133a8075428766dd48b3f752b255ec5270`
- Failure commit: `4149b194c4c4fdfdcd402a157c5336ad59dfdbbe`
- Direct-parent check: exact
- Commit-wide changed files: one
- Changed path: `evaluation/fixtures/lineage-image/runtime-mode.txt`
- Before: `healthy\n`
- After: `fail\n`
- Before SHA-256:
  `63745aef95742025c6d7a1b4fc0e7107e6f3c3eb2e0cb290f33c46f176e6740d`
- After SHA-256:
  `2056a28ea38a000f3a3328cb7fabe330638d3258affe1a869e3f92986222d997`
- Expected failure mechanism: container entrypoint exit 42

Provider revalidation:

- Actions run: `32695735269`, attempt `1`
- Head SHA: failure commit above
- Status/conclusion: `completed/success`
- Docker build record artifact: `9508752475`, present, not expired
- Provider receipt artifact: `9508751900`, present, not expired
- Receipt source ref:
  `refs/heads/evaluation/lineage-1-failure-run-v1`
- Receipt digest:
  `sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed`

## 3. Local Kubernetes safety

The active context and cluster were both `docker-desktop`. The API server was
loopback-only. Nodes had Docker Desktop kind provider identities. The safety
policy accepted the cluster before mutation.

## 4. Rendered immutable deployment

The accepted template was not modified. Generated output replaced only
`__RUN_ID__` and `__IMMUTABLE_IMAGE_REF__`. Numeric label values were rendered
as YAML strings because Kubernetes labels require strings.

Namespace:
`topo-eval-lineage-causal-32695735269`

Image:
`ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval@sha256:a7616346acbcde6b295a4a1ce77fbe1b201c66643179b6c9fef8d9aa5d6bd8ed`

No command, args, environment, image tag, replica, or security-context field
was changed.

## 5–8. Kubernetes identities and ownership

- Deployment UID: `5dc55d77-d561-4a43-9e38-d3d86e24f084`
- ReplicaSet UID: `53229841-6317-4382-a694-70e43f48e7d0`
- Pod UID: `0f8559a9-2712-4434-b16a-ab5f9fd97a25`
- ReplicaSet controller owner UID:
  `5dc55d77-d561-4a43-9e38-d3d86e24f084`
- Pod controller owner UID:
  `53229841-6317-4382-a694-70e43f48e7d0`

The exact UID ownership chain was independently established.

## 9–12. Image, failure, manifestation, and impact

The Pod spec referenced the exact immutable digest, but runtime `imageID` was
empty because registry authorization failed. Structured state was:

- waiting reason: `ImagePullBackOff`
- restart count: `0`
- last termination reason: absent
- last termination exit code: absent
- Deployment desired/ready/available: `1/0/0`

Operational unavailability existed, but it was caused by package pull
authorization, not the frozen entrypoint. This is not valid proof of the
intended failure mechanism.

## 13–14. Independent runtime receipt and validity

No `eval-runtime-causal-receipt-v1` was emitted because its strict validity
gate correctly rejected the observation. An ignored attempt record was saved
as `runtime-attempt-32695735269.json`.

Ground-truth validity: **INCONCLUSIVE_GROUND_TRUTH**.

## 15–31. Current Topo observation

Topo ingestion, source-change ingestion, lineage edges, incident lifecycle,
incident pin, affected entity, causal candidates, relevance, Top1/Top3, and
TC4 evidence were not inspected. The independence rule requires a valid
runtime receipt first. Reading or grading Topo after an `ImagePullBackOff`
would answer a different experiment.

No `topo-32695735269.json` was created.

## 32. Observation matrix

| Dimension | Independent truth | Current Topo | Match |
|---|---|---|---|
| Repository | `ShaikMuhammadSami/Topo_Ai` | not inspected | not graded |
| Parent commit | `f9b152...` | not inspected | not graded |
| Failure commit | `4149b1...` | not inspected | not graded |
| Changed file | `runtime-mode.txt` | not inspected | not graded |
| Before semantic value | `healthy` | not inspected | not graded |
| After semantic value | `fail` | not inspected | not graded |
| Commit -> Actions | provider-confirmed | not inspected | not graded |
| Actions run | `32695735269` | not inspected | not graded |
| Run attempt | `1` | not inspected | not graded |
| Actions -> Image | receipt-confirmed | not inspected | not graded |
| Image digest | `sha256:a761...d8ed` | not inspected | not graded |
| Image -> Deployment | runtime image never materialized | not inspected | not graded |
| Deployment UID | captured | not inspected | not graded |
| Deployment -> ReplicaSet | owner UID exact | not inspected | not graded |
| ReplicaSet UID | captured | not inspected | not graded |
| ReplicaSet -> Pod | owner UID exact | not inspected | not graded |
| Pod UID | captured | not inspected | not graded |
| Pod failure | intended exit 42 not established | not inspected | not graded |
| Exit code | expected 42, absent | not inspected | not graded |
| Restart/backoff | required, absent | not inspected | not graded |
| Operational impact | `1/0/0` | not inspected | not graded |
| Incident | requires valid runtime gate | not inspected | not graded |
| Pinned topology | requires valid runtime gate | not inspected | not graded |
| Affected entity | requires valid runtime gate | not inspected | not graded |
| Causal candidate | requires valid runtime gate | not inspected | not graded |
| Causal relevance path | requires valid runtime gate | not inspected | not graded |
| Top1 root cause | initiating mutation expected | not inspected | not graded |
| Top3 supported causes | initiating mutation expected | not inspected | not graded |
| TC4 evidence ledger | structured audit required | not inspected | not graded |
| Root-cause semantic level | initiating mutation | not inspected | not graded |

## 33–37. Verdict and causal conclusion

Final LINEAGE-1C verdict: **INCONCLUSIVE**.

First internal divergence: not assigned. The source-cause evaluator was never
entered because the independent runtime validity gate failed first.

What Topo got right/missed: not measured.

Provenance conclusion: source → commit → Actions → immutable digest remains
provider-proven. Causal conclusion: not measured; provenance cannot substitute
for the missing exact runtime mechanism.

## 38–40. Files and product diff

Created evaluation-only code, tests, contracts, schema documents, and this
baseline. Product diff: none under `backend/app`, `backend/tests`, `agent/src`,
`frontend`, or `cli/src`.

## 41–45. Tests and schemas

The focused suite covers immutable identity, exact UIDs, owner chains,
structured exit/backoff/impact gates, source semantic levels, verdicts, first
divergence, abstention, evaluator independence, evidence semantics,
deterministic serialization, schema validation, and frozen guards.

Exact results:

- focused LINEAGE-1C: `83 passed in 11.85s`;
- evaluation compile: successful;
- full evaluation: `517 passed in 23.46s`;
- backend compile: successful;
- full backend: `695 passed, 1 existing deprecation warning in 25.57s`;
- agent compile: successful;
- full agent: `15 passed in 2.06s`.

Both new JSON schemas validated representative complete artifacts. The live
downloaded provider receipt also validated against the accepted strict
provider-receipt schema.

## 46–48. Frozen provider guards

- Workflow SHA-256 remained
  `145a10245d575e02a756be018aaa25c2eabd1d39cde82b43aebd0d605d951903`.
- All seven permanent manifest Git blob IDs remained frozen.
- The failure branch still resolved to the frozen failure commit.
- No Actions workflow was rerun.
- No image was published.
- No package, branch, artifact, receipt, or provider setting was changed.

The existing GitHub CLI credential lacked `read:packages`. Anonymous pull was
unauthorized and authenticated pull was forbidden. A request to expand OAuth
scope was rejected; no scope change occurred.

## 49–50. Kubernetes cleanup and generated artifacts

Cleanup revalidated the exact namespace prefix and run label, deleted only the
evaluation namespace, and confirmed `NotFound` afterward.

Ignored artifacts:

- `evaluation/results/lineage/causal/rendered-32695735269.yaml`
- `evaluation/results/lineage/causal/runtime-attempt-32695735269.json`

No valid runtime receipt or Topo result exists.

## 51. Proposed next boundary — not implemented

Before repeating LINEAGE-1C, a human must provide an already-authorized,
read-only way for the local cluster to retrieve the frozen private digest (or
explicitly authorize the GitHub CLI `read:packages` scope). Then rerun the
same immutable deployment from a clean namespace. Do not repair product RCA
until a valid runtime receipt exists and current Topo has been measured.

## 52. Known limitations

- The exact image was not executed due only to registry read authorization.
- No runtime exit 42 or restart/backoff evidence was available.
- No current Topo observation was made.
- Therefore the experiment says nothing about current Topo causal accuracy.
