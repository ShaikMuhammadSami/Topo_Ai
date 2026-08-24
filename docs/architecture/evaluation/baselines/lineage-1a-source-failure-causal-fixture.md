# LINEAGE-1A source-to-failure causal fixture baseline

- Status: fixture prepared; no failure commit exists
- Phase: LINEAGE-1A only
- Provider side effects: none
- Product changes: none

## Why provenance is insufficient

H1-H7 prove that Topo can structurally connect repository, commit, Actions,
immutable image, Deployment, ReplicaSet, Pod, and runtime failure for one
provider-backed scenario. A connected chain does not independently establish
that source content caused the failure. LINEAGE-1 separates source truth,
mechanism, runtime state, and impact before observing Topo's conclusion.

## Four semantic cause levels

```text
initiating mutation
runtime-mode.txt: healthy -> fail
        ↓
failure mechanism
image entrypoint exits 42
        ↓
runtime manifestation
last exit 42 + restartCount >= 1 + BackOff/CrashLoopBackOff
        ↓
operational impact
Deployment desired=1, ready=0, available=0
```

These values are deterministic evaluation expectations, not Topo output.

## Healthy baseline

`evaluation/fixtures/lineage-image/runtime-mode.txt` contains exactly
`healthy\n`. The image entrypoint reads `/opt/topo/runtime-mode.txt`; healthy
mode enters a low-resource sleep loop. It opens no port and performs no network
operation.

## Future one-file mutation

LINEAGE-1B should change only:

```diff
-healthy
+fail
```

No Dockerfile, script, workflow, manifest, or formatting change belongs in the
failure commit. The future commit SHA and direct parent SHA remain pending and
must not be invented during LINEAGE-1A.

## Deterministic failure mechanism

The same image build process packages the changed source file. `fail` makes the
entrypoint emit one safe fixed message and exit `42`. Unknown or unreadable
mode exits `64`. Behavior has no randomness, clock dependency, external
service, environment-secret inspection, or Kubernetes override.

## Kubernetes manifestation and impact

LINEAGE-1C must deploy the exact provider-produced immutable digest into the
guarded template at `evaluation/fixtures/lineage-causal/deployment.yaml`. It
must observe structured container status and Deployment replica status with a
bounded retry window. A transient display string alone is insufficient.

## Source mutation fingerprint

`eval-source-mutation-v1` records provider repository identity, direct parent
and child commits, the sole changed file, canonical before/after hashes and
semantics, fixed mechanism/exit code, and `initiating_mutation` role. Its
preparation form permits null provider/commit fields.

The evaluation helper verifies full SHAs, direct ancestry, the commit-wide
changed-file set, and exact Git blob bytes. It consumes no Topo result.

## Required provider evidence

LINEAGE-1B must capture:

- repository ID/name;
- direct parent and failure commit SHA;
- exact source blob bytes/hashes and changed-file list;
- workflow run ID, attempt, status, and head SHA;
- provider-managed Docker build record;
- immutable image digest/reference;
- existing provider receipt as independent audit truth.

The existing manual-only workflow already builds the entire fixture directory,
so the healthy-to-fail file change requires no workflow modification. Existing
OCI source/revision/run labels and H3-R1 build-record evidence remain intact.

## Required runtime evidence

LINEAGE-1C must capture namespace/run label, immutable image reference,
Deployment/ReplicaSet/Pod UIDs and owner references, container last exit code,
restart count, waiting/termination reason, desired/ready/available replicas,
and bounded observation/cleanup times.

Only after provider runtime truth is fixed may it capture Topo incident ID,
pinned topology ID, root cause, hypotheses, and evidence for comparison.

## Safety boundaries

The template uses a prefix-and-label guarded disposable namespace, one replica,
no Service, no service-account token, no privilege, no host namespaces or
paths, no volume, read-only root filesystem, dropped capabilities, and small
CPU/memory requests and limits. Future failure observation must be bounded and
cleanup must verify namespace prefix plus evaluation-run label.

LINEAGE-1A does not render or apply the template.

## Phase boundaries

- **LINEAGE-1A:** prepare healthy fixture, contracts, template, and local tests.
- **LINEAGE-1B:** human-controlled one-file mutation, Git commit/push, and
  manual GitHub provider run. Codex does not perform these history/provider
  actions.
- **LINEAGE-1C:** deploy exact immutable digest, capture provider runtime truth,
  then observe current Topo.

No product repair is authorized until LINEAGE-1C measures a real first
divergence. LINEAGE-1A does not execute the provider, deploy Kubernetes, or
inspect a future Topo conclusion.

## LINEAGE-1B prerequisites

The LINEAGE-1A branch must be reviewed and merged with a healthy mode file,
unchanged manual workflow, green regressions, and frozen manifest hashes. The
human operator must begin from a clean worktree and confirm the intended diff
contains only `runtime-mode.txt`.

## LINEAGE-1C entry criteria

Do not enter LINEAGE-1C until the provider run is successful, its head SHA is
the exact one-file failure commit, the build record and receipt identify the
same run/attempt, and the immutable digest is independently captured. Never
deploy a mutable tag.

