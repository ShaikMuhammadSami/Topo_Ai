# CLOUD-V1-1A.2 — OIDC CI and immutable backend artifact v1

## Scope

This block establishes the production backend container and the trusted GitHub
commit → GitHub Actions run → immutable ECR digest chain for the AWS/EKS
internal golden. It does not deploy the image to EKS, connect the application
to RDS, create runtime workload identity, trigger incidents, or change RCA.

## Production container

`backend/Dockerfile` uses the repository's Python 3.12 convention and pins the
official multi-platform base image by digest. `backend/requirements.lock` is a
Linux/Python 3.12 resolution of the existing runtime requirements with every
package version exact. Installation uses `--no-deps` followed by `pip check`,
so dependency resolution cannot float during the image build.

The image contains only the application, Alembic configuration/migrations, and
the runtime lock. The allowlist-style `.dockerignore` excludes `.env`, Git,
databases, tests, reports, caches, Terraform state, local virtual environments,
and credentials. It runs Uvicorn directly as UID/GID 10001, exposes only port
8000, and preserves the existing `app.main:app` entrypoint. It adds no process
manager or health endpoint. `/health` and `/ready` already exist; Kubernetes
probe policy remains CLOUD-V1-1A.3 scope.

OCI labels carry:

- `org.opencontainers.image.source`
- `org.opencontainers.image.revision`
- `org.opencontainers.image.created`
- `org.opencontainers.image.version`

CI derives `created` deterministically from the checked-out commit timestamp.

## OIDC trust model

Terraform creates (or accepts the exact ARN of an existing) AWS IAM OIDC
provider for:

```text
issuer:   https://token.actions.githubusercontent.com
audience: sts.amazonaws.com
subject:  repo:<configured-owner>/<configured-repository>:ref:refs/heads/main
```

The repository is an exact validated variable without wildcard syntax, and the
branch is deliberately fixed to the same `main` ref required by the workflow.
An arbitrary repository, fork pull request, tag, environment subject, or
different branch cannot satisfy the role trust. No AWS account ID is hard-coded.

Only the publish job receives `id-token: write`. GitHub exchanges that token
directly for a 30-minute AWS STS role session. There is no AWS access-key or
secret-key repository/environment secret.

An AWS account can have an existing GitHub OIDC provider. In that case supply
`github_oidc_provider_arn`; otherwise Terraform creates it. Import or reuse the
existing provider instead of attempting to create a duplicate.

The GitHub provider intentionally omits Terraform's optional
`thumbprint_list`. AWS validates GitHub's OIDC certificate through its trusted
CA library, and any AWS-populated stored thumbprint is not configuration owned
by this Terraform root. Do not hard-code or calculate a GitHub certificate
thumbprint, and do not hide provider drift with `lifecycle.ignore_changes`.

## IAM permission boundary

The artifact publisher has exactly:

```text
ecr:GetAuthorizationToken                Resource "*"

ecr:BatchCheckLayerAvailability          exact golden ECR repository ARN
ecr:BatchGetImage                        exact golden ECR repository ARN
ecr:CompleteLayerUpload                  exact golden ECR repository ARN
ecr:InitiateLayerUpload                  exact golden ECR repository ARN
ecr:PutImage                             exact golden ECR repository ARN
ecr:UploadLayerPart                      exact golden ECR repository ARN
```

`GetAuthorizationToken` does not support repository-level resource scoping.
All image publication operations, including the `BatchGetImage` read required
by the private-ECR push protocol, are restricted to the one golden repository.
The role has no EKS, EC2, RDS, IAM mutation, discovery, runtime, or deployment
permission and no wildcard action.

## Workflow trust and triggers

Pull requests run only the credential-free container build job. It has
`contents: read` and cannot request a GitHub OIDC token.

Publication is manual and requires all of:

1. `workflow_dispatch`;
2. the exact `refs/heads/main` ref;
3. the confirmation value `PUBLISH_GOLDEN_BACKEND`;
4. successful completion of the credential-free build;
5. the exact OIDC repository/main subject accepted by AWS.

The publish job has only `contents: read` and `id-token: write`. Checkout pins
`github.sha` and does not persist GitHub credentials.

Configure these non-secret repository variables after the Terraform apply:

```text
TOPO_GOLDEN_AWS_ROLE_ARN        github_artifact_publisher.role_arn
TOPO_GOLDEN_AWS_REGION          aws_region
TOPO_GOLDEN_ECR_REPOSITORY_URL  ecr.repository_url
```

## Immutable provenance

Each publication uses the collision-resistant convenience tag:

```text
sha-<40-character-commit>-run-<run-id>-<run-attempt>
```

ECR tag immutability prevents rewriting it. The tag is only a locator. The
canonical deployable identity is always:

```text
<account>.dkr.ecr.<region>.amazonaws.com/<repository>@sha256:<digest>
```

The build action's returned digest is syntax-validated before a receipt is
created. The uploaded `topo-cloud-golden-artifact-v1` JSON contains only:

- source repository;
- Git commit SHA and ref;
- workflow name and workflow ref;
- workflow run ID and attempt;
- ECR repository URL;
- convenience tag;
- image SHA256 digest;
- immutable image reference;
- deterministic image creation timestamp; and
- code-owned identity-source descriptions.

It contains no OIDC token, AWS credential, ECR password, database credential,
application secret, or GitHub token. CLOUD-V1-1A.3 must consume the digest from
this receipt, never infer deployment identity from a tag.

This receipt proves only commit → build run → ECR artifact. It does not prove
that the application starts against production dependencies, deploys, becomes
healthy, or causes/resolves an incident.

## Local validation

Build without AWS credentials:

```powershell
Set-Location C:\Topo-ai

$revision = git rev-parse HEAD
docker build `
  --file backend/Dockerfile `
  --tag topo-backend:cloud-v1-1a2 `
  --build-arg "OCI_SOURCE=https://github.com/example/topo-ai" `
  --build-arg "OCI_REVISION=$revision" `
  --build-arg "OCI_CREATED=1970-01-01T00:00:00Z" `
  --build-arg "OCI_VERSION=sha-$revision" `
  backend
```

The bounded SQLite smoke mode exists only to validate container startup; it is
not production configuration:

```powershell
docker run --rm --detach `
  --name topo-backend-cloud-v1-1a2 `
  --publish 127.0.0.1:18000:8000 `
  --env TOPO_AUTH_MODE=development-disabled `
  --env TOPO_DATABASE_URL=sqlite:////opt/topo/data/smoke.db `
  topo-backend:cloud-v1-1a2

curl.exe --fail --silent --show-error --noproxy "*" http://127.0.0.1:18000/health
curl.exe --fail --silent --show-error --noproxy "*" http://127.0.0.1:18000/ready
docker rm --force topo-backend-cloud-v1-1a2
```

Real production startup requires an Alembic-current PostgreSQL database,
required authentication authority, and the PH-4 encrypted SecretStore
configuration. CLOUD-V1-1A.3 owns that runtime wiring.

## Troubleshooting

### OIDC or STS failure

Verify the workflow ran through manual dispatch on `main`, the configured
repository matches Terraform exactly, the OIDC audience is `sts.amazonaws.com`,
the role variable contains the Terraform output, and an existing account OIDC
provider was imported/reused rather than duplicated. Do not add static keys as
a workaround.

### ECR authentication failure

Verify the role has `ecr:GetAuthorizationToken`, the configured region matches
the ECR URL, and the logged-in registry prefix equals the repository prefix.

### Layer or manifest push failure

Verify the five repository-scoped upload actions target the exact ECR ARN. A
tag collision should not be bypassed by making ECR mutable; use the unique run
attempt tag and retain digest identity.

### Missing digest or provenance

Treat a missing/non-SHA256 build output as a failed publication. Do not derive
a digest from a tag or create a receipt without the build action's digest.

## Deferred to CLOUD-V1-1A.3

- actual Terraform plan/apply and GitHub variable configuration;
- backend Kubernetes Deployment/Service and non-root pod security context;
- migration preflight and RDS managed-secret consumption;
- backend ServiceAccount and EKS workload identity;
- Kubernetes RBAC and deployment authority;
- EKS deployment by immutable digest;
- startup, readiness, and liveness probe policy;
- rollout verification and runtime evidence;
- frontend/agent deployment, ALB, DNS, and TLS;
- deliberate failure and incident/RCA golden measurement.
