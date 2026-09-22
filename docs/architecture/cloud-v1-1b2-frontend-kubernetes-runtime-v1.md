# CLOUD-V1-1B.2 - frontend Kubernetes runtime v1

## Scope

CLOUD-V1-1B.2-A adds only the Kubernetes source for the private TopoAI
frontend runtime. It does not deploy that source, modify AWS, publish an image,
or create a public edge. The later CLOUD-V1-1B.2-B procedure is documented
below but was not executed in this source block.

The accepted upstream source and artifact custody are:

| Property | Accepted value |
|---|---|
| Frontend source SHA | `2d43805820c65ffb7b12c3eff465535c70f6faac` |
| Workflow | `Topo Golden Frontend Image` |
| Workflow run | `35771441512` |
| Run attempt | run attempt `1` |
| Immutable tag | `frontend-sha-2d43805820c65ffb7b12c3eff465535c70f6faac-run-35771441512-1` |
| Image digest | `sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1` |
| Canonical image | `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1` |

The ECR digest and immutable tag were independently read back before this
source was written. The Deployment contains the canonical digest reference
directly; no tag, substitution field, or `latest` reference can move it.

## Resource model

All resources are in `topo-system` and are defined in
`infrastructure/kubernetes/golden/frontend.yaml`:

| Kind | Name | Purpose |
|---|---|---|
| `ServiceAccount` | `topo-frontend` | Dedicated identity with token automount disabled and no IAM annotation. |
| `Deployment` | `topo-frontend` | Two-replica immutable frontend runtime. |
| `Service` | `topo-frontend-internal` | Private `ClusterIP` validation path on port 80 to container port 3000. |
| `PodDisruptionBudget` | `topo-frontend` | Preserves at least one available replica. |

The private Service is deliberately not named `topo-frontend`. That identity
is reserved for the separately reviewed `NodePort` edge Service owned by
CLOUD-V1-1B.3. This block creates no `NodePort`, `LoadBalancer`, `Ingress`, ALB,
target group, listener, ACM certificate, WAF, Route53 record, Porkbun record,
or `app.topoai.io` application DNS.

## Availability and health

The Deployment runs two replicas with a `RollingUpdate` strategy of
`maxUnavailable: 0` and `maxSurge: 1`. It requires ten seconds of readiness
before a Pod is considered available and retains a 600-second rollout progress
deadline. The PDB has `minAvailable: 1`.

All probes use the static, non-secret frontend-only `/healthz` route on named
container port `http` (3000):

| Probe | Period | Timeout | Failure threshold | Purpose |
|---|---:|---:|---:|---|
| Startup | 2 seconds | 1 second | 30 | Allows up to 60 seconds for the standalone Next.js server to initialize before liveness enforcement. |
| Readiness | 5 seconds | 2 seconds | 3 | Removes an unresponsive frontend from private Service endpoints. |
| Liveness | 10 seconds | 2 seconds | 3 | Restarts a frontend process that no longer serves its static health route. |

`/healthz` does not contact the backend or database, require authentication,
or read credentials. No probe uses `/api/*`.

## Workload authority and security

Both the ServiceAccount and Pod set `automountServiceAccountToken: false`.
There is no RoleBinding, ClusterRoleBinding, IRSA role annotation, EKS Pod
Identity association, image pull secret, AWS credential, or Kubernetes API
credential. ECR pulls continue to rely on the already established worker-node
path. The frontend has no AWS workload authority.

The Pod and container run as UID/GID `10001:10001` and require non-root
execution. The Pod selects seccomp `RuntimeDefault`; the container disables
privilege escalation, drops all Linux capabilities, and sets
`readOnlyRootFilesystem: true`. It does not use privileged mode, host ports,
`hostPath`, `hostNetwork`, `hostPID`, or `hostIPC`.

The Deployment has no `env`, `envFrom`, Secret reference, ConfigMap reference,
volume, or volume mount. In particular it contains no database URL, API or
human bearer credential, observer credential, AWS credential, keyring,
`TOPO_BACKEND_URL`, or `NEXT_PUBLIC_TOPO_API_URL`. Later browser API traffic
will remain same-origin through ALB routing; the frontend Pod does not receive
a backend credential.

## Read-only-root filesystem proof

The exact accepted digest was pulled from ECR and run locally as an ephemeral
container with `--read-only`, all capabilities dropped, no-new-privileges, a
loopback-only ephemeral port, and no writable application volume. The measured
result was:

```text
GET /healthz -> HTTP 200, {"status":"ok","component":"frontend"}
GET /        -> HTTP 200
ReadonlyRootfs=true
User=10001:10001
Mounts=[]
CapDrop=["ALL"]
```

The container was removed after the check. Because both required routes
succeeded with `Mounts=[]`, the Kubernetes runtime uses
`readOnlyRootFilesystem: true` and has no writable volumes or filesystem
exceptions. No `/tmp`, Next.js cache, or arbitrary `emptyDir` was added.

## Resource bounds and topology

Each frontend Pod requests `100m` CPU and `256Mi` memory and is limited to
`500m` CPU and `512Mi` memory. These are conservative initial bounds for the
small standalone Next.js server, not a performance-tuning claim. Live
observation in 1B.2-B must inform any later separately reviewed adjustment.

Two soft topology-spread constraints use
`topology.kubernetes.io/zone` and `kubernetes.io/hostname`, both with
`maxSkew: 1` and `ScheduleAnyway`. They prefer different AZs and workers while
allowing recovery during a single-node or fault-domain impairment. Live
acceptance must record the placement actually achieved.

## CLOUD-V1-1B.2-B guarded live deployment procedure

This procedure is a handoff only. It was not executed by 1B.2-A. No human credential
may be submitted at any step.

1. Start from clean, merged `main`; record the exact merged SHA and require it to contain the accepted manifest without local changes.
2. Run `aws sts get-caller-identity` read-only and require AWS account `297361542190` before any deployment action.
3. Inspect the selected Kubernetes context read-only and require the context name `topo-golden`.
4. Verify the server-reported cluster identity, endpoint, and namespace are the intended `topo-golden` / `topo-system` target; stop on any mismatch.
5. Describe the ECR image read-only and require the exact accepted digest and frontend immutable tag to exist in `topo-golden/topo`.
6. Confirm read-only that `Deployment/topo-frontend`, `ServiceAccount/topo-frontend`, `Service/topo-frontend-internal`, and `PodDisruptionBudget/topo-frontend` do not already exist; stop rather than overwrite an unexplained resource.
7. Confirm read-only through the authoritative Porkbun view that the `app.topoai.io` application DNS record remains absent.
8. Confirm read-only that no TopoAI ALB, ACM application certificate, or WAF resource from later CLOUD-V1-1B blocks exists.
9. Parse the accepted YAML and perform server-side and client-side dry-run validation where appropriate, recording output and ensuring no object is persisted.
10. Apply only `infrastructure/kubernetes/golden/frontend.yaml` after a separate live-mutation approval; do not apply the directory or alter backend, observer, database, or runtime ConfigMap resources.
11. Wait for `Deployment/topo-frontend` rollout completion within a bounded timeout and capture any scheduling or pull failure without broadening authority.
12. Require exactly two desired, updated, available, and Ready frontend replicas.
13. Inspect both running containers and require each runtime `imageID` to resolve to `sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1`.
14. Prove both Pods run on existing private workers with no public worker address introduced.
15. Record each Pod's node and `topology.kubernetes.io/zone`, noting whether the two soft spread preferences achieved distinct workers and AZs.
16. Inspect Pod mounts and projected volumes and prove no service-account token is mounted.
17. Inspect the ServiceAccount, Pod identity, and AWS identity path and prove there is no IAM annotation, Pod Identity association, or frontend AWS workload authority.
18. Inspect effective Pod environment, volumes, and mounts and prove there is no Secret/ConfigMap credential injection, backend credential, database URL, bearer token, keyring, or AWS credential.
19. Use a bounded operator `port-forward` to `Service/topo-frontend-internal` and require `GET /healthz` to return HTTP 200 with the expected static component response.
20. Through the same private bounded path, require `GET /` to return HTTP 200 without submitting a human credential.
21. Perform one separately approved bounded voluntary disruption of a single frontend Pod while continuously checking private `/healthz`; require at least one serving replica throughout.
22. Require the Deployment to converge back to exactly two Ready replicas on the accepted digest after the bounded disruption.
23. Verify read-only that the existing backend replicas and singleton observer remain healthy, retain their accepted image identities, and were not rolled out or reconfigured.
24. Confirm no `NodePort`, `LoadBalancer`, `Ingress`, public address, ALB, target group, listener, or worker security-group edge rule appeared.
25. Reconfirm the `app.topoai.io` application DNS record remains absent and that no ACM/WAF/public-edge acceptance was implied.
26. Record the source SHA, workflow run/attempt, immutable tag, ECR digest, Deployment UID/revision, Pod UIDs/imageIDs/nodes/AZs, Service cluster IP, PDB identity, validation timestamps, and a bounded `CLOUD-V1-1B.2-B=PASS` or fail-closed marker.

## Acceptance boundary

CLOUD-V1-1B.2-A establishes reviewable source and deterministic contract tests.
CLOUD-V1-1B.2-B alone may prove live scheduling, ECR pull, private Service
routing, placement, disruption availability, and runtime identity after an
explicitly approved deployment. This block changes no backend/observer
resource or browser origin, creates no public endpoint, and performs no
credential-bearing browser acceptance.
