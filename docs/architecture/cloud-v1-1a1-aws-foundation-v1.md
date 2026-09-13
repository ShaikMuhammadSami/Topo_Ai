# CLOUD-V1-1A.1 — AWS/EKS internal golden foundation v1

## Scope

This block defines the disposable AWS foundation for TopoAI's first real EKS
internal golden. It does not apply infrastructure, deploy TopoAI workloads,
build images, create delivery automation, inject a deliberate failure, or
change causal/RCA behavior.

The Terraform root is `infrastructure/aws/golden`. It deliberately uses native
AWS resources rather than introducing a generic internal module framework.

## Provisioned architecture

```text
one AWS region
  └─ one VPC (DNS support and hostnames enabled)
      ├─ Availability Zone A
      │   ├─ public subnet (future ALB + NAT)
      │   ├─ private EKS worker subnet (one managed node)
      │   └─ isolated database subnet
      ├─ Availability Zone B
      │   ├─ public subnet (future ALB + optional second NAT)
      │   ├─ private EKS worker subnet (one managed node)
      │   └─ isolated database subnet
      ├─ Internet gateway for public-subnet infrastructure
      ├─ NAT gateway (one by default; optionally one per AZ)
      └─ S3 gateway endpoint on both private-worker route tables

EKS control plane
  ├─ private API access for workers
  ├─ public API access restricted to operator-supplied CIDRs
  ├─ two one-node managed node groups, one private subnet/AZ each
  └─ encrypted worker volumes and IMDSv2

ECR
  └─ immutable tags, encryption, basic scan-on-push

RDS PostgreSQL 16
  ├─ Single-AZ DB instance
  ├─ DB subnet group spanning both AZs
  ├─ no public address
  ├─ encrypted gp3 storage and forced TLS
  ├─ inbound 5432 only from the dedicated EKS worker security group
  └─ master password generated and held by AWS Secrets Manager
```

The network is two-AZ even though the RDS instance is deliberately Single-AZ.
RDS requires the DB subnet group to span at least two AZs, but `multi_az=false`
keeps the golden's database compute footprint bounded. This is not an HA
database claim.

## Security decisions

- Worker nodes use only private subnets and never request public IPs.
- Public subnets are tagged for a future internet-facing AWS Load Balancer.
  No workload is exposed directly and no ALB is provisioned before a real
  listener/target exists.
- The EKS API has private access enabled. Its public endpoint requires a narrow
  office/VPN CIDR supplied by the operator; world-open CIDRs are rejected.
- PostgreSQL has no public route or address. Its security group permits TCP
  5432 only from the dedicated golden worker security group. It has no
  internet CIDR ingress.
- The database password is not an input. RDS creates and rotates the master
  password through AWS Secrets Manager; Terraform exposes only the secret ARN.
- ECR tags are immutable. Worker IAM uses pull-only ECR access.
- Worker metadata requires IMDSv2 with a hop limit of one.
- Database and worker storage encryption are explicit. PostgreSQL forces TLS.
- EKS creator-admin bootstrap is retained only so the initial internal golden
  is operable. Access entries and workload identity are CLOUD-V1-1A.2/.3 work.
- CNI permissions temporarily remain on the node role for initial bootstrap;
  a later workload-identity block will move them to the CNI service account.

This infrastructure does not add application egress purposes, generic HTTP
paths, credentials, provider keys, application schema migrations, or changes
to PH-4/PH-6 boundaries.

## Cost-sensitive decisions

The defaults create cost-bearing EKS control-plane, EC2 worker, NAT gateway,
NAT data-processing, RDS, CloudWatch Logs, ECR storage/scanning, public IPv4,
and ordinary AWS data-transfer resources. S3 gateway endpoints have no hourly
interface-endpoint charge.

- Two `t3.small` on-demand workers are explicit, one per AZ.
- One NAT gateway is the default. This reduces fixed cost but creates an
  accepted internal-golden availability and cross-AZ routing tradeoff.
  `nat_gateway_per_az=true` provisions one per AZ when the evidence warrants it.
- RDS defaults to `db.t4g.micro`, 20 GiB gp3, a 40 GiB autoscaling ceiling,
  one-day backups, no Performance Insights, and no enhanced monitoring.
- Control-plane log retention defaults to seven days.
- No paid interface VPC endpoint, ALB, Multi-AZ database, autoscaling platform,
  service mesh, Kafka, or self-hosted CI runner is provisioned.

Actual cost depends on region, runtime duration, data volume, selected instance
types, NAT usage, storage, and current AWS pricing. This document makes no
monthly-cost claim.

## State decision

No Terraform backend is configured. That is intentional: the repository had
no accepted state convention, and this block does not invent an account-
specific S3/KMS/DynamoDB backend. Terraform therefore uses local state unless
the operator supplies a reviewed backend configuration during initialization.

`.gitignore` excludes Terraform working directories, state, generated variable
files, crash logs, and override files. Do not use local state for shared or
long-lived deployments. Before the first shared apply, choose and review a
remote-state owner, S3 bucket, encryption policy, state locking mechanism,
access policy, recovery procedure, and environment isolation scheme.

## Validation without AWS mutation

From PowerShell:

```powershell
Set-Location C:\Topo-ai\infrastructure\aws\golden

terraform fmt -check -recursive
terraform init -backend=false
terraform validate
terraform test
```

`terraform init` downloads the declared provider but does not create AWS
resources. `terraform test` uses a mocked AWS provider and deterministic two-AZ
inventory. Neither command needs AWS credentials or calls AWS APIs.

Before a future real plan:

1. Install Terraform 1.8 or newer and AWS CLI v2.
2. Select a reviewed AWS account and single region.
3. Authenticate using a short-lived AWS profile or SSO session—never an access
   key stored in this repository.
4. Copy `terraform.tfvars.example` to ignored `terraform.tfvars`.
5. Replace the documentation CIDR with the operator's narrow office/VPN CIDR.
6. Confirm EKS 1.35 and RDS PostgreSQL 16 are offered in the selected region.
7. Decide whether local state is acceptable for a disposable individual run or
   provide the separately reviewed remote backend configuration.
8. Run `terraform plan -out=golden.tfplan` and review every resource. A plan is
   not authorization to apply.

## Destroying the golden

No resources were created by this block. For a later applied disposable
environment, first remove Kubernetes Services/Ingresses that own AWS load
balancers and empty the ECR repository. Then, using the exact same backend,
workspace, variables, account, and region:

```powershell
Set-Location C:\Topo-ai\infrastructure\aws\golden

terraform plan -destroy -out=golden-destroy.tfplan
terraform apply golden-destroy.tfplan
```

If retaining image evidence is not required, an operator may explicitly set
`ecr_force_delete=true` for the reviewed destroy. With
`rds_skip_final_snapshot=true`, the disposable default creates no final DB
snapshot. Set it to false before apply when retention is required. Never delete
state first; verify the plan targets only the intended golden resources.

## Outputs for later blocks

Terraform exports the region/AZs, VPC, three subnet classes, future public ALB
subnets, private route tables, NAT gateways, S3 endpoint, EKS name/ARN/endpoint/
CA/OIDC issuer/node groups/security groups, ECR identity/URL, RDS endpoint and
master-secret ARN, and the EKS IAM role ARNs.

No database URL or secret value is output. CLOUD-V1-1A.2/.3 must bind workload
identity and authorized secret consumption before deploying the application.

## Intentionally deferred

- Terraform plan/apply and AWS resource creation
- remote-state implementation and state-locking operations
- CI/CD, image build/push, signing, and deployment
- EKS access-entry hardening and OIDC/workload identity
- AWS Load Balancer Controller and public application ALB
- DNS, TLS certificate, WAF, and customer ingress
- TopoAI backend/frontend/agent Kubernetes workloads and runtime secrets
- RDS Multi-AZ, read replicas, cross-region recovery, and production backups
- autoscaling, Spot capacity, service mesh, Kafka, and enterprise observability
- paid interface VPC endpoints
- deliberate runtime failure and golden causal measurement
- Terraform-to-AWS causal lineage, new RCA logic, and generic AWS incidents
