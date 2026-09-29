# CX-0 teardown plan input

This document contains no executable teardown. It is the review template that
the CX-0A inventory/reconciliation evidence populates before a separate CX-0B
contract is written.

| Resource | Identifier | Ownership/source | Dependency order | Recommendation | Billing class | Recreation authority | Pre-delete prerequisite | Post-delete verification |
|---|---|---|---|---|---|---|---|---|
| EKS control plane | inventory | Terraform | after workload evidence | candidate | likely continuous | Terraform/state/source | accepted inventory and CX-0B approval | absent; retained evidence intact |
| Worker node groups/EC2/ASGs | inventory | Terraform/EKS | before control plane | candidate | likely continuous | Terraform/state/source | workload and image evidence frozen | no orphan compute/volumes |
| NAT gateways/EIPs | inventory | Terraform | after private runtime | candidate | likely continuous | Terraform/state/source | dependent runtime removed | no unowned allocation |
| ALB/target groups | accepted edge inventory | Terraform | after DNS transition | candidate | likely continuous | Terraform/state/source | accepted DNS replacement/removal | hostname does not target deleted ALB |
| WAF | accepted WebACL inventory | Terraform | after public edge | conditional candidate | likely continuous | Terraform/state/source | no protected public resource remains | association/log retention reviewed |
| RDS instance | inventory | Terraform/RDS | only after recovery proof | conditional candidate | likely continuous | Terraform plus proven snapshot/restore; `DATABASE_SCHEMA_AUTHORITY=0015_security_audit`; `DATABASE_MIGRATION_HEAD=MATCH` | `RDS_RESTORE_PROVEN=YES` and migration-head identity remains reconciled | snapshot/recovery evidence retained; restored schema head re-proven read-only |
| VPC endpoints | inventory | Terraform | after dependents | candidate | unknown until inventory | Terraform/state/source | dependency review | no required path lost |
| Logs/alarms | inventory | Terraform/AWS | after retention review | conditional | storage/unknown | source plus retention record | evidence retention decision | required audit evidence remains |
| Accepted ECR backend/frontend/observer digests | `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:825e6da3440a51be229376ad494f33dbd5269c0a1158e347325841d366967c76`; `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:ba86d89733b552cd3ced4792f40b59032524f83275b806ffc20f3249b8b1bdf1`; `297361542190.dkr.ecr.us-east-1.amazonaws.com/topo-golden/topo@sha256:b482df847d453ac6128348a3fc5570210d20299a3421ebc6a3e9fb7ec05348b3` | `DURABLE_IMMUTABLE_ARTIFACT_AUTHORITY` | retain before/during/after runtime teardown | retain; `COST_0_RETAIN`; `DO_NOT_DELETE_DURING_CX_0B` | storage | exact ECR digest plus `scripts/cloud/cx0/cloud_v1_1b_image_authority.json`; mutable tags are not authority; backend digest is bound to publication commit `906513c0d9716a018bf0d5a38470fd57fd94aa45`, tree `5cc3651425bf8879e2af59f44545cc88401f6456`, and repair ancestor `0907d5b957ada24a6cd3a53619ab1fa792707779` | all three exact digests exist and no automatic lifecycle expiration threatens them | exact manifests remain present; no broad retention claim is made for unrelated historical images |
| Final RDS snapshot | future proof | immutable artifact | retain | retain | storage | RDS snapshot ARN | proven restore | retained and encrypted |
| SecretStore recovery keyring | `arn:aws:secretsmanager:us-east-1:297361542190:secret:topo/golden/recovery/secret-store-keyring-v1-Y8D1I4` | durable external authority | retain before/during/after all runtime and database actions | retain; `COST_0_RETAIN`; `DO_NOT_DELETE_DURING_CX_0B` | low/storage | exact binary keyring fingerprint plus documented recovery procedure | fingerprint and active key ID remain verified | object ARN retained and fingerprint unchanged |
| Domain and ACM validation record | Porkbun/ACM | external authority | retain unless intentional retirement | retain | low/no runtime | domain/certificate custody | explicit certificate strategy | authoritative records verified |
| Terraform backend/state | `s3://topo-tfstate-297361542190-us-east-1/golden/terraform.tfstate` | accepted versioned S3 durable authority, independent of golden root state | retain before/during/after every runtime teardown action | retain; `COST_0_RETAIN`; `DO_NOT_DELETE_DURING_CX_0B` | low/storage | versioned private S3, SSE-S3, native `use_lockfile` | exact bucket controls, state VersionId, 80 remote addresses, representatives, and semantic-equivalence receipt verified | remote state remains readable without object-body output; empty local primary is non-authoritative and `.backup` remains only a recovery artifact |

The live inventory is authoritative for completeness and may add resources.
No row is permission to act. The final plan must have one reviewed row per live
resource, with exact identifiers and dependency order, before CX-0B review.

`TEARDOWN_AUTHORIZED=NO`.

The Terraform backend bucket and every noncurrent state version are outside
CX-0B deletion authority. No lifecycle expiration is permitted by this
contract. Migration is accepted by semantic equivalence across the source and
destination lineage/serial transition. The zero-byte local primary must not be
restored from `.backup`; neither local file is current state authority.

The three accepted image digests listed above are likewise outside CX-0B
deletion authority. This is a narrow retain rule for those exact digests, not
permission or a requirement to retain every image ever published to the shared
repository. A future ECR lifecycle policy must not be accepted until its rules
are proven unable to expire the accepted artifacts automatically.

The matching live/source Alembic head is release and evaluation evidence, not
database recovery proof. CX-0B remains unauthorized until the independent RDS
restore gate passes, and any future restored database must independently prove
the same single migration-head authority through the read-only probe.
