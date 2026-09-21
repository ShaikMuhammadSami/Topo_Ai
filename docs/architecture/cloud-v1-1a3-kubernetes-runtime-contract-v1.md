# CLOUD-V1-1A.3 — Kubernetes runtime contract v1

## Scope and topology

This block defines, but does not deploy, the first TopoAI AWS/EKS internal
golden runtime:

```text
1A.2 immutable backend receipt
  -> one pre-deployment Alembic Job
  -> two-replica topo-backend Deployment
  -> ClusterIP topo-backend Service

singleton topo-observer Deployment
  -> dedicated Kubernetes ServiceAccount
  -> exact read-only ClusterRole
  -> authenticated Topo backend submission
```

There is no public ingress, NodePort, AWS apply, Kubernetes apply, or live
credential in this block. `infrastructure/kubernetes/golden` is a set of
ordered reviewable templates, not an instruction to apply the whole directory.

## Immutable artifact consumption

All three occurrences of the backend placeholder image—the main backend,
keyring-staging init container, and migration Job—must be replaced with the
same `immutable_image_ref` from the 1A.2 provenance receipt:

```text
<golden-ecr-repository>@sha256:<64 lowercase hexadecimal characters>
```

The Deployment and migration Job never consume `latest`, and the Job does not
rebuild the application. The checked-in all-zero digest and `example.invalid`
repository are deliberately non-deployable placeholders. A live bring-up must
reject them before submitting resources to Kubernetes.

The observer manifest also requires a digest reference, but 1A.2 published only
the backend. A separately reviewed immutable Topo Agent build and digest is a
live bring-up prerequisite; this block does not invent a second artifact
identity or claim that the placeholder observer image exists.

## Backend Deployment and Service

The backend runs two replicas as UID/GID 10001 with a read-only root filesystem,
all Linux capabilities dropped, privilege escalation disabled and seccomp
`RuntimeDefault`. It has no host network, host PID/IPC, privileged mode or
`hostPath`. A bounded memory-backed `/tmp` is its only writable filesystem.

The `topo-backend` ServiceAccount disables token automount and has no Role or
ClusterRole binding. The backend therefore has no Kubernetes API authority.
The Service is ClusterIP-only and selects the exact backend API labels. Public
ALB, DNS and TLS remain later work.

Resource requests are 250 millicores and 512 MiB per replica; limits are one
CPU and 1 GiB. These are internal-golden starting values, not measured
production capacity claims.

### SecretStore keyring delivery normalization

The application does not consume the Kubernetes Secret projection directly.
Kubernetes represents projected Secret keys through symlinks and the original
`0440` projection is group-readable, while `load_keyring` intentionally accepts
only a regular, non-symlink, owner-only POSIX file. That application custody
invariant remains unchanged.

The raw `secret-store-keyring.json` key is mounted only into a hardened,
non-root init container using the same immutable backend image as the main
container. As UID/GID 10001, the init container reads at most 65,536 bytes,
rejects empty or oversized input and exclusively creates
`/run/topo/keyring/keyring.json` in a bounded memory-backed
per-Pod `emptyDir`. It copies the bytes unchanged and verifies an owner-only
`0600` regular, non-symlink destination. The main backend mounts only that
staged volume, read-only; it cannot see the raw Secret projection.

The init container is the custody-normalization boundary: the raw Kubernetes
Secret projection is untrusted input and may use Kubernetes symlink semantics,
but the entire trusted path consumed by the application must have no symlink or
reparse ancestor. `/var/run` is intentionally forbidden for the trusted
keyring because the production backend image resolves it through the
`/var/run -> /run` symlink. The trusted volume is therefore mounted directly at
`/run/topo/keyring` and `TOPO_SECRET_KEYRING_FILE` is exactly
`/run/topo/keyring/keyring.json`.

This is delivery normalization, not key rotation, re-encoding, or
transformation. The keyring bytes, cryptographic format, active key identifier,
SecretStore implementation and `load_keyring` policy are unchanged.

## Rollout, placement and disruption

The RollingUpdate policy is:

```text
replicas:       2
maxUnavailable: 0
maxSurge:       1
minReadySeconds: 10
```

An old Ready Pod remains available while the replacement is not Ready. A
`minAvailable: 1` PodDisruptionBudget permits one voluntary disruption without
allowing both replicas to be evicted. It does not protect against involuntary
node failure or a database outage.

Soft topology-spread constraints prefer separate zones and hosts but use
`ScheduleAnyway`. Normal placement can use the two 1A.1 workers/AZs, while a
surviving node remains eligible when the other node or AZ is unavailable.

## Startup, liveness and readiness

The probe endpoints have these exact meanings:

| Probe | Endpoint | Meaning |
|---|---|---|
| startup | `/startup` | FastAPI entered application lifespan and initialized sufficiently to answer requests. It does not query PostgreSQL or optional providers and does not claim serving readiness. |
| liveness | `/health` | The FastAPI process can answer a minimal request. It does not test PostgreSQL or optional providers. |
| readiness | `/ready` | Startup gates completed and a current `SELECT 1` succeeds. |

`/startup` returns only `{"status":"started"}` after application-process
initialization, or a minimal 503 `{"status":"not_started"}` before lifespan
has started. `/health` returns the existing minimal body and never calls
PostgreSQL, OpenAI, Groq, GitHub or another optional integration. `/ready` returns only
`{"status":"ready"}` or a minimal 503 `{"status":"not_ready"}` and never
returns a driver exception, host, URL or credential.

Normal PostgreSQL application sessions retain `pool_pre_ping`, a three-second
connection timeout and a two-second pool-checkout timeout. The current
readiness query uses a separate SQLAlchemy `NullPool` connection with a
probe-only two-second connection timeout and two-second PostgreSQL statement
timeout. It therefore neither waits for an application pool slot nor imposes
an aggressive statement timeout on product queries. Four seconds is its
intended internal maximum. Five seconds remains the conservative bound for a
pending database-startup retry using the normal engine. Kubernetes allows
eight seconds for `/ready`, which is greater than both intended paths. Startup
and liveness retain two-second HTTP timeouts because neither performs
dependency I/O. The readiness query is the constant, cheap `SELECT 1`.

If PostgreSQL becomes unavailable after startup, liveness remains 200 while
readiness becomes 503, removing the Pod from Service endpoints without causing
a liveness or startup restart storm. `/startup` remains 200 because current
database availability is not process-start authority. If PostgreSQL is
unavailable during cold startup, the HTTP process remains alive, `/startup`
succeeds, and `/ready` retries the database-dependent serving gates while
returning 503. The startup probe allows up to five minutes only for a process
that cannot initialize enough to serve `/startup`; PostgreSQL unavailability is
not startup-probe failure after that point. Schema mismatch, invalid SecretStore
configuration and missing authentication authority remain fail-closed rather
than being reclassified as healthy serving readiness.

Readiness does not depend on LLM providers, GitHub, cloud APIs, customer
webhooks or the observer.

## Database credentials and runtime configuration

No Kubernetes Secret value is committed. A live bring-up must create the
`topo-backend-runtime` Secret out of band with these keys:

| Key | Consumer | Contract |
|---|---|---|
| `database-url` | backend Deployment | Dedicated application PostgreSQL login; TLS-required URL, URL-encoded, never logged. |
| `migration-database-url` | migration Job | Separately controlled schema-migration login. |
| `bootstrap-token-hashes-json` | backend Deployment | Digest-only initial/break-glass registry; use `{}` after durable named admin authority exists. |
| `secret-store-keyring.json` | keyring-staging init container only | PH-4 root-key bytes are read from the `0440` projection and copied unchanged into a memory-backed owner-only `0600` regular file; the backend mounts only the staged file read-only. |
| `secret-store-active-key-id` | backend Deployment | Identifier selecting the mounted active root key. |

The 1A.1 RDS managed-master secret is bootstrap authority, not the permanent
application credential. During the reviewed live bring-up, an operator must use
that managed secret without printing it to create the dedicated migration and
application database roles, then materialize their URLs into the Kubernetes
Secret. The RDS master secret is not mounted into application Pods. Automatic
Secrets Manager synchronization is deferred; no large secret controller is
introduced here.

`topo-runtime-config` contains only non-secret identity/configuration
placeholders: installation UUID, cluster name, environment and exact browser
origins JSON. The installation ID must be a stable valid Topo installation UUID
before deployment. Database URLs, passwords, tokens and root keys must never be
placed in that ConfigMap.

## Migration responsibility

PostgreSQL application startup calls `init_db`, which verifies that the database
is already at the repository's single Alembic head. It does not execute
migrations. Therefore two backend replicas never race schema mutation.

The one-shot `topo-backend-migrate` Job is the explicit pre-deployment owner of:

```text
python -m alembic -c /opt/topo/alembic.ini upgrade head
```

Run and verify that Job before creating or updating the Deployment. It uses the
same backend digest but the separately controlled migration database URL. The
live automation must give each migration execution a reviewed unique lifecycle
and stop rollout if it fails. No drop/reset command or migration operator was
added, and frozen Alembic history is unchanged.

## Observer classification and topology

The Topo Agent binary is mixed-capability: it can load cluster-wide Kubernetes
inventory, cloud plugins and node-local Docker/host/network/runtime plugins.
The golden manifest intentionally selects only the Kubernetes plugin, so this
particular workload is a cluster-wide observer, not a node agent.

Current Kubernetes behavior is polling, not a Kubernetes watch stream or leader
election. The collector lists inventory every five minutes, and the change
poller lists Kubernetes Events every 30 seconds. One replica with `Recreate`
avoids simultaneous active pollers. This accepts a short observation gap during
replacement. Correctness does not rely on perfect singleton execution: agent
submission IDs, durable backend idempotency, failure fingerprints, overlap and
incident correlation remain responsible for duplicate safety. The `emptyDir`
buffer is not durable across Pod replacement; a persistent observer checkpoint
is future reliability work.

The observer uses its own `topo-observer` ServiceAccount and a separate
`topo-observer-runtime` Secret containing only its server-issued `agent-id` and
`agent-token`. It does not reuse backend credentials.

## Exact Kubernetes RBAC

Actual code calls Kubernetes list APIs only. It does not call `get` or establish
`watch=true` streams today, so the golden grants only `list`:

| API group | Resources | Verbs |
|---|---|---|
| core | namespaces, nodes, pods, services, events | list |
| apps | deployments, replicasets | list |
| networking.k8s.io | ingresses | list |
| discovery.k8s.io | endpointslices | list |

There is no wildcard, Secret or ConfigMap read, pod exec, workload mutation,
RBAC mutation or cluster-admin authority. A future real watch implementation
must separately justify adding `watch`; the prompt's preferred read-only verb
set is a ceiling, not authority to grant unused verbs.

## AWS IAM versus Kubernetes RBAC

The backend dependency set does not contain an AWS SDK and the backend does not
call AWS APIs for this runtime. The observer is configured with Kubernetes only;
AWS, Azure and GCP change watches are explicitly disabled. Consequently neither
ServiceAccount has an AWS role annotation and no runtime IAM role is created.

ECR image pulling remains node/kubelet authority from 1A.1, not Pod IAM.
Secrets Manager access remains an operator bring-up responsibility. The GitHub
artifact-publisher role from 1A.2 is never reused by either workload.

## RDS network boundary

This block retains the 1A.1 dedicated-worker-security-group to RDS rule for the
internal golden. It is explicitly node-level, not Pod-specific. Any workload
scheduled on those workers with a network path could attempt TCP 5432; TLS and
database authentication remain additional controls. This is the accepted
blast radius for the isolated internal golden.

Security Groups for Pods, a network-policy enforcement engine and extra
controllers are not introduced without operational proof. A later production
hardening decision must evaluate Pod-level security groups or an enforced
NetworkPolicy before describing RDS access as backend-only.

## Ordered live prerequisites

Before any live apply, the next block must:

1. Obtain the 1A.2 backend provenance receipt and reject its placeholder,
   non-SHA256 or non-ECR image reference.
2. Publish and record a separately reviewed immutable Topo Agent digest.
3. Create the namespace and non-secret ConfigMap with real installation and
   cluster identities.
4. Create `topo-backend-runtime` without displaying its values.
5. Use the RDS managed master credential only to create the dedicated migration
   and application roles.
6. Run the migration Job using the exact backend digest and require success.
7. Establish initial bootstrap authority, then create durable named admin and
   tenant authority before rotating the bootstrap mapping to `{}`.
8. Deploy the backend, wait for both replicas to become Ready and verify spread.
9. Enroll one observer and create `topo-observer-runtime` without logging the
   returned token.
10. Deploy the singleton observer and verify authenticated topology submissions.

## Still unvalidated and deferred

- real EKS admission, scheduling, DNS and Service routing;
- ECR pulls and digest availability;
- RDS TLS, migrations, role provisioning and connection capacity;
- real Kubernetes probe timing and rollout behavior;
- live agent enrollment, event permissions and topology ingestion;
- runtime resource sizing;
- public ALB, ACM, DNS, WAF and frontend deployment;
- Pod-level RDS network isolation and observer durable state;
- deployment automation, deliberate failure, incident/RCA measurement and
  rollback.

Those require the authorized live bring-up block. Local parsing and contract
tests prove only the checked-in definitions and deterministic backend probe
semantics.
