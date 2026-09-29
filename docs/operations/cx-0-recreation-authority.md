# CX-0 recreation authority

This document maps the accepted golden environment to the authority needed to
recreate it. The generated CX-0A inventory and reconciliation reports are the
current evidence; this document is the durable procedure contract.

| Domain | Primary authority | Required durable evidence |
|---|---|---|
| Application/source | Git commit and tree | Accepted predecessor plus current CX-0A source |
| AWS foundation | `infrastructure/aws/golden` and remote Terraform state identity | Source-set hash, provider lock hash, backend type/identifiers, workspace, resource-address list |
| Kubernetes runtime | `infrastructure/kubernetes/golden` plus deployment receipts | Manifest hash, sanitized live contract, immutable image digests |
| Images | ECR digest | Backend, frontend, and observer repository-at-digest references and ECR presence |
| Database schema | `backend/alembic` | Single repository head and safely obtained live revision |
| DNS | Porkbun | Authoritative nameserver evidence for application and ACM validation CNAMEs |
| TLS | ACM plus durable validation CNAME | Certificate ARN/status/lifecycle and exact validation record |
| SecretStore root authority | AWS Secrets Manager `topo/golden/recovery/secret-store-keyring-v1` | Exact live-keyring SHA-256 match, active key ID, stable ARN, recovery procedure, and retention classification |
| Evidence retention | Git/ECR/S3/CloudWatch/CloudTrail as applicable | Identifiers, retention settings, and reconstruction role; no raw customer payloads |

## Immutable application image authority

The accepted CLOUD-V1 application artifacts are the following exact ECR
repository-at-digest references:

```ini
BACKEND_IMAGE=297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:825e6da3440a51be229376ad494f33dbd5269c0a1158e347325841d366967c76
BACKEND_PUBLICATION_SOURCE_COMMIT=906513c0d9716a018bf0d5a38470fd57fd94aa45
BACKEND_PUBLICATION_SOURCE_TREE=5cc3651425bf8879e2af59f44545cc88401f6456
BACKEND_REPAIR_COMMIT=0907d5b957ada24a6cd3a53619ab1fa792707779
FRONTEND_IMAGE=297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1
OBSERVER_IMAGE=297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:b482df847d453ac6128348a3fc5570210d20299a3421ebc6a3e9fb7ec05348b3
```

`scripts/cloud/cx0/cloud_v1_1b_image_authority.json` is the machine-readable
versioned authority. ECR tags are discovery metadata only and are never
recreation authority. These three exact digests, not every historical image in
the repository, are classified as:

```text
DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY
COST_0_RETAIN
DO_NOT_DELETE_DURING_CX_0B
```

At CX-0A.2C verification time the ECR repository had no lifecycle policy, so
these digests were not exposed to automatic lifecycle expiration. Introducing
any lifecycle policy makes retention unproven until its rules receive a
separate fail-closed review. Recreation requires the live workload, pinned
Kubernetes source, machine-readable authority and exact ECR digest to agree.

## Database schema authority

The accepted source and live database each contain exactly one Alembic head:

```ini
DATABASE_SCHEMA_AUTHORITY=0015_security_audit
DATABASE_MIGRATION_HEAD=MATCH
DATABASE_PROBE_DRIVER=psycopg-v3
DATABASE_PROBE_TRANSACTION_MODE=READ_ONLY
DATABASE_PROBE_TRANSACTION_COMPLETION=ROLLBACK
```

`scripts/cloud/cx0/prove_database_migration_head.ps1` derives the source head
from the migration graph, derives the backend Pod selector from the live
Deployment, and runs a bounded query using the Pod's existing
`TOPO_DATABASE_URL` environment variable. It never emits that value. The probe
uses `BEGIN READ ONLY`, selects only the ordered Alembic version rows, and
always completes with `ROLLBACK`. Its sanitized receipt is consumed by the
inventory; missing evidence remains `UNKNOWN_REQUIRED`, while different or
non-unique heads block reconciliation.

Database schema identity remains part of final release and evaluation
authority. Matching the head proves schema identity only; it does not prove an
RDS backup can be restored and does not authorize teardown.

## Terraform state recovery authority

The golden root declares one deterministic S3 backend:

```ini
TERRAFORM_ROOT_MODULE=infrastructure/aws/golden
TERRAFORM_BACKEND_BUCKET=topo-tfstate-297361542190-us-east-1
TERRAFORM_BACKEND_KEY=golden/terraform.tfstate
TERRAFORM_BACKEND_REGION=us-east-1
TERRAFORM_LOCKING_MODEL=S3_NATIVE_USE_LOCKFILE
REQUIRED_TERRAFORM_VERSION=>= 1.10, < 2.0
```

The bucket is deliberately outside the golden root state, avoiding a circular
dependency between the state and its own storage. It is bootstrapped only by
`scripts/cloud/cx0/bootstrap_terraform_state_backend.py`, which defaults to a
read-only `PRECHECK` and may create only the exact approved, absent bucket
after explicit execution confirmation. An existing bucket with different
ownership or configuration is a hard stop; the utility never invents a new
name or repairs/replaces existing authority.

Required bucket controls are versioning `Enabled`, all four public-access
blocks enabled, `BucketOwnerEnforced`, default `AES256` SSE-S3 encryption, a
deny-non-TLS policy, no state-version expiry, and these classifications:

```text
DURABLE_EXTERNAL_AUTHORITY
COST_0_RETAIN
DO_NOT_DELETE_DURING_CX_0B
```

`scripts/cloud/cx0/migrate_golden_terraform_state.ps1` defaults to `PRECHECK`.
Its `EXECUTE` mode additionally requires `-ExecuteMigration -Confirmation
"MIGRATE_GOLDEN_STATE_TO_S3"` and delegates the transfer only to Terraform's
native `init -migrate-state` flow, retaining operator control of Terraform's
confirmation. It does not force-copy, disable locking, manually upload state,
or read state values. The accepted pre-migration fingerprints are:

```ini
LOCAL_STATE_SHA256=b3321648facd8506f322b7f91ad3ad04dd8b1a017ba89124c5f382e4abd48994
LOCAL_STATE_BACKUP_SHA256=3e22a83281206088253e3417b4e31acbfba15e3fca4cd17aa164c21f9e1c445d
STATE_RESOURCE_COUNT=80
```

Before migration, PRECHECK does not ask Terraform to select a workspace or
enumerate state because the source already declares the not-yet-initialized S3
backend. Instead `scripts/cloud/cx0/inspect_local_terraform_state.py` first
verifies the exact local SHA-256, then parses the secret-bearing state once in
memory and emits only format/Terraform versions, lineage, serial, count, and
booleans for the five approved representative addresses. Raw JSON, outputs,
attributes, provider data, and values are never emitted. Backend-dependent
`workspace show` and `state list` are reserved for post-migration verification.

The migration is now accepted. Terraform assigned a new destination lineage
and restarted the destination serial; neither is required to equal the source
identity. The safe receipt preserves both identities:

```ini
SOURCE_STATE_LINEAGE=13c78cf7-912f-cacc-74eb-15c7ee33112f
SOURCE_STATE_SERIAL=97
DESTINATION_STATE_LINEAGE=dc5223d7-8ffe-cacf-e04f-f1f42a8bc584
DESTINATION_STATE_SERIAL=1
REMOTE_STATE_VERSION_ID=Zq_uCrcG0Z51r_Qbho9lvn0QZ8AtA2.Z
REMOTE_STATE_ENCRYPTION=AES256
```

Acceptance is semantic rather than lineage equality: resources, outputs, and
all non-check state matched exactly; the 18 check results matched as an
unordered collection with identical `resource:1,var:17` kinds and `pass:18`
statuses. No state payload or secret value is retained in the receipt.

The versioned S3 object is `DURABLE_EXTERNAL_AUTHORITY`. Remote verification
enumerates exactly 80 addresses including the representative VPC/EKS/RDS/ALB/
ECR addresses. Terraform left the local primary as a zero-byte file with
SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
it is `NON_AUTHORITATIVE_EMPTY_PRIMARY`. The retained `.backup` file is only
`NON_AUTHORITATIVE_LOCAL_RECOVERY_ARTIFACT` and must not be copied back over
the primary or treated as current authority.

## SecretStore recovery custody

The SecretStore root key is never part of a CX-0 receipt. The current
Kubernetes Secret remains runtime delivery and is not itself disaster-recovery
authority. The exact complete live `secret-store-keyring.json` is independently
held as a binary AWS Secrets Manager payload. Only its safe identity and
fingerprint metadata are recorded here:

```ini
RECOVERY_SECRET_NAME=topo/golden/recovery/secret-store-keyring-v1
RECOVERY_SECRET_ARN=arn:aws:secretsmanager:us-east-1:297361542190:secret:topo/golden/recovery/secret-store-keyring-v1-Y8D1I4
ACTIVE_KEY_ID=runtime-v1
KEYRING_SHA256=adb0bf496822d35043eeb7355a00f6819f095ca77179488d56f14c521ac058ff
```

Its custody classifications are:

```text
DURABLE_EXTERNAL_AUTHORITY
COST_0_RETAIN
DO_NOT_DELETE_DURING_CX_0B
```

The object is independent of the RDS database and its backups. CX-0 tooling may
describe and read it in memory for fingerprint verification, but must never
print it, write it to plaintext disk, replace it, add a version, rotate it, or
delete it. Recovery uses the procedure in
`docs/operations/cx-0-rds-recovery-proof-plan.md`.

Recreation acceptance requires `LIVE_ONLY_REQUIRED_COUNT=0` and
`UNKNOWN_REQUIRED_COUNT=0`. An inventory identifier is not authority unless
the reconciliation report names its versioned or durable external source.
