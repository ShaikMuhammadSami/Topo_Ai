# CLOUD-V1-1A.4C1 — immutable live artifact definitions v1

## Scope and current state

CLOUD-V1-1A.2 already defines the production backend image and its trusted
GitHub commit → Actions run → immutable ECR digest chain. This sub-block adds
the equivalent source-controlled artifact path for the Topo Agent running as
the Kubernetes observer. It does not publish either image, dispatch a workflow,
change AWS, or deploy a workload.

The observer publication definition cannot be exercised from this feature
branch. The existing AWS OIDC trust intentionally accepts only the exact
configured repository on `refs/heads/main`. The definition must be reviewed and
merged before CLOUD-V1-1A.4C1-B performs the live GitHub OIDC → STS → ECR proof.

## Observer production image

`agent/Dockerfile` retains the existing Python module and `run` command while
hardening the artifact boundary:

- the official Python 3.12 slim base is pinned by SHA-256 digest;
- `agent/requirements.lock` freezes the Linux/Python 3.12 resolution of the
  existing agent dependencies;
- installation uses `--no-deps` followed by `pip check`, so resolution cannot
  float during a build;
- the allowlist-style `agent/.dockerignore` admits only the Dockerfile, lock,
  and runtime source tree;
- no `.env`, Git metadata, Terraform state, kubeconfig, tests, caches, build
  output, or local virtual environment enters the build context;
- the process runs as UID/GID 10001 and writes persistent state only beneath
  `/var/lib/topo-agent`;
- runtime code is loaded from `/opt/topo-agent/src`; and
- OCI labels carry source repository, revision, creation time, version, and
  the unambiguous `observer` component identity.

The image includes the already-supported cloud collector libraries because the
agent plugin registry imports those existing modules. It does not contain or
select cloud credentials. The golden runtime remains Kubernetes-only through
`TOPO_ENABLED_PLUGINS=kubernetes` and explicitly disabled AWS, Azure, and GCP
change watchers in the accepted 1A.3 manifest.

## Manifest compatibility

`infrastructure/kubernetes/golden/observer.yaml` is compatible without change:

- its single `run` argument extends the image entrypoint
  `python -m topo_agent`;
- pod UID/GID 10001 matches the image user;
- the read-only root filesystem is compatible with the mounted writable
  `/var/lib/topo-agent` state volume and `/tmp` memory volume;
- the service-account token is intentionally mounted because the Kubernetes
  collector lists Kubernetes resources through the in-cluster API;
- RBAC remains the 1A.3 list-only contract;
- backend URL, enrollment identity, and token remain runtime inputs; and
- the image field remains an immutable `repository@sha256:digest` placeholder.

No AWS, Azure, or GCP runtime credential is required for this Kubernetes-only
observer configuration.

## Trusted publication path

`.github/workflows/topo-golden-observer-image.yml` mirrors the accepted backend
trust boundary while keeping the component release independently auditable.

Pull requests receive only `contents: read` and perform a credential-free
Linux/AMD64 build with `push: false`. They cannot request a GitHub OIDC token,
authenticate to ECR, or publish an image.

Publication requires all of:

1. a manual `workflow_dispatch` event;
2. the exact `refs/heads/main` ref;
3. the exact confirmation `PUBLISH_GOLDEN_OBSERVER`;
4. a successful credential-free validation build; and
5. the existing AWS role's exact repository/main OIDC subject.

Only the publish job receives `contents: read` and `id-token: write`. It obtains
a short-lived AWS STS session and authenticates to ECR without static AWS
keys. Checkout is pinned to `github.sha` and does not persist Git credentials.
The workflow contains no EKS, Kubernetes, database, migration, or deployment
operation.

## Repository and IAM strategy

Backend and observer images share the existing immutable golden ECR repository.
This is appropriate for the bounded internal golden because each artifact is
unambiguous through its component-specific tag and, authoritatively, its image
digest. A second repository would add lifecycle and IAM surface without adding
an identity guarantee.

The workflow reuses `TOPO_GOLDEN_AWS_ROLE_ARN`, which resolves to the existing
`topo-golden-github-artifact-publisher` role created as
`aws_iam_role.github_artifact_publisher`. Its only permissions are ECR
authentication plus the private-ECR publication operations—including
`ecr:BatchGetImage`—scoped to the exact golden ECR repository ARN. It has no
EKS, EC2, RDS, IAM mutation, discovery, runtime, or deployment permission.

## Tag, digest, and provenance

The observer convenience tag is:

```text
observer-sha-<commit>-run-<run-id>-<run-attempt>
```

The immutable ECR repository prevents rewriting the tag, but the tag remains a
locator. The canonical artifact identity is always:

```text
<account>.dkr.ecr.<region>.amazonaws.com/<repository>@sha256:<digest>
```

Publication syntax-validates the build action's digest and uploads a
`topo-cloud-golden-artifact-v1` JSON receipt containing:

- `schema_version` and `component` (`observer`);
- `source_repository`;
- `git_commit_sha` and `git_ref`;
- `workflow_name`, `workflow_ref`, `workflow_run_id`, and
  `workflow_run_attempt`;
- `ecr_repository` and the convenience `image_tag`;
- exact `image_digest` and canonical `immutable_image_ref`;
- deterministic `image_created_at`; and
- code-owned descriptions of commit, digest, and run identity sources.

The receipt contains no GitHub token, OIDC token, AWS session material, ECR
password, kubeconfig, agent token, provider key, or application secret.

Backend and observer receipts use the same schema and repository identity, but
their workflow/run, component, tag, and digest prove separate artifacts. The
accepted backend workflow remains unchanged.

## Local validation

The observer image can be built without AWS credentials:

```powershell
Set-Location C:\Topo-ai

$revision = git rev-parse HEAD
docker build `
  --file agent/Dockerfile `
  --tag topo-observer:cloud-v1-1a4c1 `
  --build-arg "OCI_SOURCE=https://github.com/ShaikMuhammadSami/Topo_Ai" `
  --build-arg "OCI_REVISION=$revision" `
  --build-arg "OCI_CREATED=1970-01-01T00:00:00Z" `
  --build-arg "OCI_VERSION=observer-sha-$revision" `
  agent

docker run --rm --read-only `
  --tmpfs /tmp `
  --tmpfs /var/lib/topo-agent `
  topo-observer:cloud-v1-1a4c1 version
```

The bounded smoke verifies the packaged CLI/module and security-compatible
filesystem without an agent token or live Kubernetes API. A full `run` needs
the runtime enrollment secret, in-cluster service-account token, backend, and
Kubernetes API and is therefore deferred to deployment validation.

## CLOUD-V1-1A.4C1-B after merge

C1-B must prove live publication custody for **both** components before any
Kubernetes deployment. The live ECR repository begins this procedure with no
images, so the previously defined backend path is not considered live-proven
merely because it passed local and static validation.

### Precheck

Run C1-B only after this source is reviewed and merged to `main`. Before either
publication:

1. verify both workflows consume the same repository variables:
   `TOPO_GOLDEN_AWS_ROLE_ARN`, `TOPO_GOLDEN_AWS_REGION`, and
   `TOPO_GOLDEN_ECR_REPOSITORY_URL`;
2. verify the configured ECR URL identifies the expected live
   `topo-golden/topo` repository;
3. verify the AWS role trust still accepts only the exact configured GitHub
   repository on `refs/heads/main`; and
4. verify no Kubernetes deployment step is being performed as part of C1-B.

### Backend live publication

1. Manually dispatch **Topo Golden Backend Image** from `main` with its accepted
   confirmation input `PUBLISH_GOLDEN_BACKEND`.
2. Prove GitHub OIDC successfully exchanges the workflow identity for the
   existing short-lived AWS STS publisher role.
3. Prove the backend image push to the expected ECR repository succeeds.
4. Download and validate the backend provenance receipt.
5. Compare all three independent values and require equality:
   - workflow-produced digest;
   - backend receipt digest; and
   - AWS/ECR-reported digest for the published backend tag.
6. Preserve the canonical backend identity:

   ```text
   repository@sha256:<backend-digest>
   ```

### Observer live publication

1. Manually dispatch **Topo Golden Observer Image** from `main` with
   `PUBLISH_GOLDEN_OBSERVER`.
2. Prove GitHub OIDC successfully exchanges the workflow identity for the same
   existing short-lived AWS STS publisher role.
3. Prove the observer image push to the expected ECR repository succeeds.
4. Download and validate the observer provenance receipt.
5. Compare all three independent values and require equality:
   - workflow-produced digest;
   - observer receipt digest; and
   - AWS/ECR-reported digest for the published observer tag.
6. Preserve the canonical observer identity:

   ```text
   repository@sha256:<observer-digest>
   ```

### Final C1-B acceptance

C1-B passes only when:

- ECR contains both component images;
- the exact backend digest and observer digest are known;
- both receipts trace their component to the exact Git commit, Git ref,
  workflow name/ref, run ID, and run attempt;
- workflow output, receipt, and AWS/ECR digest agree independently for each
  component;
- neither component uses `latest`; and
- no Kubernetes deployment has occurred.

C1-B proves artifact publication custody only. Workload deployment, runtime
Secrets, database migrations, and Kubernetes apply remain later guarded work.
