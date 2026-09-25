# CX-0A / COST-0 — reproducibility freeze v1

## Objective and accepted predecessor

CX-0A proves that the accepted golden environment can be recreated before any
cost teardown is considered. It inventories the live environment, reconciles
recreation-critical live facts with their authority, and records blockers.
It does not redesign the accepted CLOUD-V1 public edge.

The accepted predecessor is:

- commit: `e676559b3daf586b4dc53041d1638a3d2191910a`
- tree: `c4389d7613afeb7f908e87ed5c4e6c04e599fc0c`
- status: `CLOUD_V1_1B_PUBLIC_EDGE_BROWSER_PATH=ACCEPTED`

Accepted immutable application artifacts are:

- backend: `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:b32a93d9c3d33d6d83a73475c00687b68ba680b6d591ff84601933af99d7ff12`
- frontend: `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1`
- observer: discovered by the inventory and treated as live-only until its
  immutable digest is found in versioned or separately durable authority.

The browser contract remains HTTPS-only at `https://app.topoai.io`, with
same-origin `/api/*`, ALB routing, regional WAF defense in depth, and backend
authentication, authorization, tenant isolation, and CSRF as authority. The
accepted browser origin is exactly `["https://app.topoai.io"]`.

## Authority boundary

CX-0A has no delete or infrastructure mutation authority. Its executable
inventory and reconciliation helpers are allowlisted, read-only clients. They
must not change AWS, Kubernetes, Porkbun DNS, PostgreSQL, Terraform state, or
Git history. They never perform snapshot creation, RDS restore, release-tag
creation, Terraform apply/destroy/import, or Kubernetes mutation.

The gates are deliberately separate:

1. CX-0A.1 captures a secret-safe inventory.
2. CX-0A.2 reconciles live facts with source and external authority.
3. CX-0A.3 may prepare a release-freeze decision, but a human creates any tag.
4. CX-0A.4 later provides a separately reviewed, mutation-allowlisted restore
   proof harness.
5. CX-0A.5 plans the public-host transition without changing DNS.
6. CX-0A.6 plans teardown without containing delete commands.
7. An architect reviews the evidence.
8. Only a separately contracted CX-0B may perform teardown.

`TEARDOWN_AUTHORIZED=NO` throughout CX-0A.

## Source-of-truth hierarchy

Recreation inputs are classified in this order:

1. **VERSIONED_AUTHORITY** — Git, Terraform, Kubernetes manifests, Alembic
   migrations, release configuration, and reviewed architecture contracts.
2. **IMMUTABLE_ARTIFACT_AUTHORITY** — ECR digests, checksums, release receipts,
   and a future accepted database snapshot identifier.
3. **DURABLE_EXTERNAL_AUTHORITY** — Porkbun records, ACM validation lifecycle,
   Terraform remote-state identity, AWS account/domain ownership, and
   separately escrowed SecretStore recovery authority.
4. **LIVE_ONLY_STATE** — dangerous state that must be codified or promoted to
   documented external authority before teardown.

The reconciliation vocabulary is `MATCH`, `CODIFIED_DIFFERENTLY`,
`LIVE_ONLY_REQUIRED`, `INTENTIONALLY_DISPOSABLE`, and `UNKNOWN`.
`LIVE_ONLY_REQUIRED` and required `UNKNOWN` items block teardown. The helper
does not silently classify live state as disposable.

## Inventory categories

The inventory receipt contains an explicit allowlist of safe fields for Git
source, AWS caller identity, EKS and node groups, sanitized Kubernetes
workloads/RBAC/configuration, immutable images and ECR manifests, VPC routing,
security groups, ALB/listeners/target groups, WAF, ACM, authoritative DNS, RDS,
Alembic heads, SecretStore recovery metadata, Terraform identity and resource
addresses, IAM role metadata, logging retention, and cost-relevant resources.

Generated receipts are local artifacts under ignored `artifacts/cx0/`. They
are not release authority and must not be committed without separate review.

## Secret-redaction contract

The inventory serializes only explicit safe projections. It never serializes
Kubernetes Secret values, Terraform state values, database credentials,
SecretStore root keys, session/CSRF values, provider tokens, private keys, AWS
access keys, or raw encrypted-secret payloads. Kubernetes Secrets are queried
through a metadata template that emits names, types, key names, immutable
flags, safe label values, and annotation names only.

ConfigMap values are hashed. Plaintext is emitted only for the allowlisted
non-secret keys `browser-allowed-origins-json`, `cluster-name`, `environment`,
and `installation-id`. Literal container environment values are withheld
unless the variable name is on the script's narrow non-secret allowlist.

Terraform inspection is limited to source, version/provider identity,
workspace, and `terraform state list`. Raw state and bulk output are forbidden.
Failures never print captured stderr into receipts.

### Durable Terraform state boundary

The golden root's durable target is the private, versioned S3 bucket
`topo-tfstate-297361542190-us-east-1`, key `golden/terraform.tfstate`, in
`us-east-1`. Locking is Terraform's native S3 `use_lockfile = true` contract;
there is no DynamoDB dependency. The backend requires Terraform `>= 1.10, <
2.0`, AES256 SSE-S3, `BucketOwnerEnforced`, all public-access blocks, a
deny-non-TLS policy, and no state-version expiration.

Backend bootstrap remains independent of the golden Terraform root to avoid a
state-storage circular dependency. Bootstrap and migration are separate,
explicitly confirmed operations. The completed migration is accepted without
requiring destination lineage or serial equality: its receipt preserves source
lineage/serial and destination lineage/serial while requiring resource,
output, non-check-state, and unordered check-result equivalence. The receipt
stores no state payload or secret value.

Closure additionally requires the exact retained bucket controls, a versioned
AES256 state object, remote enumeration of all 80 resource addresses and the
five expected representatives, versioned source authority for native S3
locking, and explicit local demotion. The zero-byte local primary is
`NON_AUTHORITATIVE_EMPTY_PRIMARY`; the retained `.backup` is only
`NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT`. The S3 object remains
`DURABLE_EXTERNAL_AUTHORITY`.

## Stable fingerprints

Fingerprints use SHA-256 over UTF-8 canonical JSON or a sorted source-set
manifest. Object keys are sorted; explicitly unordered resource collections
are sorted by stable resource identity before hashing. Generated timestamps,
Kubernetes UIDs/resourceVersions, pod names, secret values, and transient
target-health descriptions are excluded. Ordered lists whose order is part of
the contract, such as listener actions and container commands, retain order.

## Live/source reconciliation and release freeze

The comparator consumes a schema-valid receipt and performs no live query or
mutation. It checks the accepted immutable images, workload/source hashes,
browser origin, services and NodePorts, EKS/node-group shape, edge route and
security-group contracts, WAF, ACM and DNS external authority, RDS source
requirements, Alembic authority, IAM, Terraform backend/state identity,
SecretStore recovery, and evidence logging.

Release freeze is not accepted until both blocker counters are zero, immutable
digests and migration head are recorded, Terraform backend/state identity is
known, DNS/ACM external authority is recorded, SecretStore recovery is proven,
and the working tree is clean. A future helper may display the exact candidate
commit for the suggested annotated tag
`cloud-v1-1b-accepted-2026-09-23`; it must never create, move, or overwrite it.

## Database recovery-proof contract

A backup is not accepted until a restore is proven. The current RDS instance
must remain untouched during CX-0A. The separately reviewed CX-0A.4 harness
must create an encrypted snapshot and isolated temporary restore, supply root
authority through a separate controlled channel, verify engine/schema and
Alembic head, verify representative records and one non-sensitive SecretStore
operation, run bounded smoke checks, record evidence, remove only the temporary
restore, and prove the original instance was untouched.

Until that reviewed proof passes:

```text
RDS_RESTORE_PROVEN=NO
ORIGINAL_RDS_DELETION_AUTHORIZED=NO
```

## DNS and certificate lifecycle

Porkbun remains authoritative. The application CNAME is
`app.topoai.io -> topo-golden-edge-823808315.us-east-1.elb.amazonaws.com`.
The ACM validation record
`_ae02df53f40f7c96b34bc6e98fb69e1d.app.topoai.io.` to
`_fd79c652992203959600f955507f54f4.wzccmgtwzk.acm-validations.aws.` is:

```text
DURABLE_EXTERNAL_AUTHORITY
DO_NOT_REMOVE_DURING_COST_TEARDOWN_UNLESS_CERTIFICATE_STRATEGY_IS_INTENTIONALLY_ABANDONED
```

CX-0A only documents the future choice to repoint the product host to an
accepted low-cost surface or intentionally replace/remove the application
CNAME. It never changes DNS and never leaves the name pointing to a deleted
ALB by design.

## Teardown-plan contract and gate separation

The plan records each resource's identifier, owner, dependency order,
retain/delete recommendation, billing class, recreation authority,
precondition, and post-action verification. It contains no executable delete
path. Likely runtime-cost candidates and retained evidence are hypotheses until
the live inventory confirms them.

CX-0A produces evidence for an architect. It cannot emit `COST-0=CLOSED` or
`TEARDOWN_AUTHORIZED=YES`. CX-0B is a separate contract, review, branch, and
authority boundary.
