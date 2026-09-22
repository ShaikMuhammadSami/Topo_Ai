# CLOUD-V1-1B.1 — immutable frontend artifact v1

## Scope

CLOUD-V1-1B.1-A prepares the source, build, validation, and publication
contract for the TopoAI frontend image. It does not publish an image or deploy
a workload. Live publication is a separate guarded CLOUD-V1-1B.1-B operation
after this source is reviewed and merged to `main`.

This block preserves the CLOUD-V1-1B.0 boundaries:

- the browser uses relative `/api/...` requests at one origin;
- no browser credential or API origin is embedded in the frontend artifact;
- the AWS production path will be split by the ALB rather than depending on a
  Next.js backend rewrite;
- application DNS remains unpublished until the later HTTPS and WAF gates have
  passed; and
- no human credential is used during artifact validation or publication.

## Source changes

| File | Purpose |
|---|---|
| `frontend/next.config.mjs` | Enables Next.js standalone output while retaining existing image and local rewrite behavior. |
| `frontend/package.json` | Includes the frontend artifact contract test and pins the approved Next.js and PostCSS security patches. |
| `frontend/package-lock.json` | Records the npm-resolved dependency graph used by local, CI, and container builds. |
| `frontend/app/healthz/route.ts` | Adds the static frontend-only target health endpoint. |
| `frontend/Dockerfile` | Defines the pinned, multi-stage, non-root production container. |
| `frontend/.dockerignore` | Restricts the Docker context to explicit application build inputs. |
| `frontend/test/production-artifact.test.mjs` | Protects health, standalone, same-origin, and container-source invariants. |
| `.github/workflows/topo-golden-frontend-image.yml` | Defines credential-free validation and guarded immutable publication. |
| `scripts/cloud/tests/test_cloud_v1_1b1_contract.py` | Statically enforces the container, workflow, provenance, and IAM boundaries. |
| `docs/architecture/cloud-v1-1b1-immutable-frontend-artifact-v1.md` | Records this contract and the later live procedure. |

The correction upgrades Next.js from `16.2.6` to exactly `16.3.3` and
PostCSS from the previously resolved `8.5.15` to exactly `8.5.28`. Both the
root manifest and lockfile package records carry those exact versions. React
19 and the application behavior remain unchanged.

`nodemon` and `shadcn` are development/build tooling rather than deployed
server dependencies. No application or server module imports `nodemon`, and
no npm script invokes it. `shadcn` supplies its Tailwind stylesheet during the
build and its `components.json` metadata is tooling input; no runtime JavaScript
imports it. They moved from `dependencies` to `devDependencies` without a
version change: the declared ranges remain `^3.1.14` and `^4.8.0`, while the
lockfile continues to resolve `3.1.14` and `4.11.0` respectively.

## Standalone packaging model

`frontend/next.config.mjs` sets `output: "standalone"`. The builder runs
`npm ci` from the checked-in npm lockfile and then performs the production
`next build`. The runtime stage receives only:

- `.next/standalone`;
- `.next/static`; and
- `public` application assets.

It does not copy the builder's complete source tree, development dependencies,
npm cache, tests, developer `.next` cache, or local `node_modules` into the
runtime stage.

Final-image inspection confirms there is no `node_modules/nodemon`,
`node_modules/shadcn`, `.bin/nodemon`, or `.bin/shadcn` path, and neither
package can be resolved by the standalone server. Development tooling remains
available to the builder through the normal full `npm ci` graph but is absent
from the deployed artifact.

Next.js 16.3.3 deterministically adds
`import "./.next/types/root-params.d.ts"` to `next-env.d.ts`. Removing that
line, deleting `.next`, and running a clean build regenerated it, so the
tracked generated change is retained as a required output of the accepted
framework upgrade rather than discarded as local churn.

The existing `images.unoptimized` behavior is unchanged. The existing
`TOPO_BACKEND_URL` rewrite remains available for local development, including
its URL validation. Browser code still accepts only relative `/api/` paths and
uses `credentials: "same-origin"`. The production ALB will intercept those
paths before they reach the frontend target, so the cloud architecture does
not rely on this rewrite.

No `NEXT_PUBLIC_TOPO_API_URL`, public backend origin, token, or credential was
introduced.

## Production dependency security gate

The npm lockfile is the dependency authority. Local verification and CI first
run `npm ci`, then assess only the production graph with:

```text
npm audit --omit=dev --audit-level=high
```

The `validate-production-dependencies` workflow job uses Node 24, has only
`contents: read`, and must pass alongside the credential-free container build
before the publication job can run. The publication path never runs
`npm audit fix` or `npm audit fix --force` and never rewrites dependencies
automatically.

The original production audit still included the development-only `nodemon`
and `shadcn` trees because they had been misclassified as runtime dependencies.
After moving only those two unchanged roots to `devDependencies`, both
`npm ls --omit=dev nodemon` and `npm ls --omit=dev shadcn` return an empty
production tree. `npm explain` identifies each as a dev-only root.

The remaining moderate advisory, CVE-2026-45819, affected the resolved
`baseline-browser-mapping@2.10.38`; its patched range begins at `2.11.0`.
The package remained transitive through
`next@16.3.3 -> baseline-browser-mapping` and was not added to `package.json`.
A targeted `npm update baseline-browser-mapping --package-lock-only` changed
only that lock record's version, resolved URL, and integrity, resolving it to
`2.11.25`. No direct dependency or npm override was introduced.

The final production audit reports:

| Severity | Count |
|---|---:|
| info | 0 |
| low | 0 |
| moderate | 0 |
| high | 0 |
| critical | 0 |
| total | 0 |

The CI gate remains fail-closed at high severity. Producing a currently clean
artifact does not change the accepted high/critical publication policy or
weaken the threshold.

## Font build-time boundary

The existing Geist, Geist Mono, and Roboto Slab sources use
`next/font/google`. Next.js downloads the Google font assets during the build
and packages them into the application for self-hosting. A deployed browser
does not fetch these fonts from Google, no font CDN URL is added to browser
code, and there is no runtime cross-origin or Google Fonts privacy dependency.

This is a build-availability dependency: the production build environment
needs outbound access for npm/package retrieval and the `next/font` Google
font download. The resulting runtime serves the built font assets itself.

## Frontend health endpoint

The future frontend target group health check is:

```text
GET /healthz
```

It returns HTTP 200 with a static JSON body:

```json
{
  "status": "ok",
  "component": "frontend"
}
```

The route is forced static. It does not access PostgreSQL, the TopoAI backend,
the filesystem, environment configuration, providers, or credentials. It is
not an authentication or application-readiness claim; it proves only that the
frontend server can answer its dedicated minimal health route. Backend
`/health` and `/ready` are unchanged.

## Container contract

The multi-stage Dockerfile uses the official Node 24 Bookworm slim image pinned
to:

```text
node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
```

Dependency installation is exactly `npm ci` against `package-lock.json`.
The final image creates and runs as UID/GID 10001, exposes TCP 3000, and starts
the standalone server directly with:

```text
node server.js
```

The runtime defaults are non-secret `NODE_ENV=production`,
`NEXT_TELEMETRY_DISABLED=1`, `HOSTNAME=0.0.0.0`, and `PORT=3000`. No
`TOPO_BACKEND_URL` or credential is baked into the image. CLOUD-V1-1B.2 owns
the independent proof of read-only-root-filesystem compatibility and any
strictly bounded writable runtime paths; this source block does not assume
that result.

OCI labels reuse the accepted component convention:

- `org.opencontainers.image.source`;
- `org.opencontainers.image.revision`;
- `org.opencontainers.image.created`;
- `org.opencontainers.image.version`;
- `org.opencontainers.image.vendor`; and
- `topo.component=frontend`.

## Bounded Docker context

`frontend/.dockerignore` is deny-by-default: its first rule is `**`, followed
by explicit inclusion of only the Docker definition, npm manifests, Next.js/
TypeScript/PostCSS configuration, and the `app`, `components`, `lib`, and
`public` runtime source trees.

Defense-in-depth rules re-exclude nested:

- `node_modules` and `.next`;
- Git metadata;
- `.env*` files;
- tests, coverage, and caches;
- logs and temporary files; and
- editor/OS junk.

Repository-root UI screenshots are outside the allowlist. Application assets
under `public/` remain available to the build. Because `frontend` is the Docker
context, repository-root secrets and infrastructure material cannot enter it.

## Workflow and publication boundary

The independent workflow is named:

```text
Topo Golden Frontend Image
```

Pull requests run the credential-free dependency-security and container-build
jobs with `contents: read`; they cannot request a GitHub OIDC token or
authenticate to ECR. Live publication requires all of:

1. `workflow_dispatch`;
2. exact `refs/heads/main`;
3. confirmation `PUBLISH_GOLDEN_FRONTEND`;
4. a production dependency audit with zero high or critical findings;
5. successful credential-free validation build; and
6. the existing AWS role's exact repository/main OIDC subject.

Only the publish job receives `id-token: write`. It uses the existing
repository variables:

```text
TOPO_GOLDEN_AWS_ROLE_ARN
TOPO_GOLDEN_AWS_REGION
TOPO_GOLDEN_ECR_REPOSITORY_URL
```

GitHub exchanges its OIDC identity for a 30-minute AWS STS session and logs in
to the existing `topo-golden/topo` ECR repository. No static AWS key is used.

The workflow contains no Terraform, EKS, Kubernetes, DNS, ACM, WAF, database,
migration, backend-rollout, or deployment action. Backend, observer, and
frontend publication remain separate workflows.

## Existing IAM authority

No IAM source change is required. The existing artifact publisher already has
the precise authority needed by the private-ECR push protocol:

```text
ecr:GetAuthorizationToken                Resource "*"

ecr:BatchCheckLayerAvailability          exact golden repository ARN
ecr:BatchGetImage                        exact golden repository ARN
ecr:CompleteLayerUpload                  exact golden repository ARN
ecr:InitiateLayerUpload                  exact golden repository ARN
ecr:PutImage                             exact golden repository ARN
ecr:UploadLayerPart                      exact golden repository ARN
```

Its trust remains the exact configured GitHub repository on
`refs/heads/main`. It has no EKS, EC2, RDS, IAM mutation, DNS, certificate,
WAF, or deployment authority. Adding another image to the same exact ECR
repository requires no permission broadening.

## Immutable identity and provenance receipt

The frontend convenience tag is:

```text
frontend-sha-<git-sha>-run-<run-id>-<run-attempt>
```

The ECR repository's immutable-tag policy prevents reuse. The tag is a locator;
the canonical identity retained for CLOUD-V1-1B.2 is:

```text
<account>.dkr.ecr.<region>.amazonaws.com/topo-golden/topo@sha256:<digest>
```

The workflow syntax-validates the build action's SHA-256 digest and writes:

```text
file:     topo-golden-frontend-provenance.json
artifact: topo-golden-frontend-provenance-<run-id>-<run-attempt>
schema:   topo-cloud-golden-artifact-v1
component: frontend
```

The receipt contains:

- source repository;
- Git commit SHA and ref;
- workflow name and workflow ref;
- workflow run ID and attempt;
- exact ECR repository;
- frontend convenience tag;
- image digest and canonical immutable image reference;
- deterministic commit-derived creation time; and
- code-owned commit, digest, and run identity-source descriptions.

It contains no OIDC token, AWS credential, ECR password, GitHub token,
application credential, backend URL, database URL, keyring, agent token, or
human API credential.

## Local validation procedure

Run repository frontend checks using the npm lockfile:

```powershell
Set-Location C:\Topo-ai\frontend

npm test
npm run typecheck
npm run lint
npm run build
```

Build the production container without credentials:

```powershell
Set-Location C:\Topo-ai

$revision = git rev-parse HEAD
docker build `
  --file frontend/Dockerfile `
  --tag topo-frontend:cloud-v1-1b1 `
  --build-arg "OCI_SOURCE=https://github.com/example/topo-ai" `
  --build-arg "OCI_REVISION=$revision" `
  --build-arg "OCI_CREATED=1970-01-01T00:00:00Z" `
  --build-arg "OCI_VERSION=frontend-sha-$revision" `
  frontend
```

Run a secret-free smoke on a loopback-only ephemeral host port:

```powershell
$container = docker run --rm --detach `
  --publish 127.0.0.1::3000 `
  topo-frontend:cloud-v1-1b1

$binding = docker port $container 3000/tcp
$port = ([regex]::Match($binding, ':(\d+)$')).Groups[1].Value
curl.exe --fail --silent --show-error --noproxy "*" "http://127.0.0.1:$port/healthz"
curl.exe --fail --silent --show-error --noproxy "*" "http://127.0.0.1:$port/"
docker inspect --format '{{.Config.User}}' $container
docker rm --force $container
```

Expected user identity is `10001:10001`. The smoke does not set
`TOPO_BACKEND_URL`, call a backend, or submit a human credential.

## CLOUD-V1-1B.1-B guarded live publication after merge

Run 1B.1-B only after this source is reviewed and merged to `main`:

1. Verify the checkout is clean `main` and record the exact merged Git SHA.
2. Verify no `topo-frontend` Kubernetes workload or Service exists.
3. Verify no `app.topoai.io` application DNS record exists. An ACM validation
   record, if separately authorized later, is not application DNS.
4. Manually dispatch **Topo Golden Frontend Image** from `main` with exact
   confirmation `PUBLISH_GOLDEN_FRONTEND`.
5. Prove GitHub OIDC assumed the existing short-lived AWS artifact-publisher
   role for the exact repository/main subject.
6. Prove the image was pushed to the expected live `topo-golden/topo` ECR
   repository under the frontend-specific immutable convenience tag.
7. Download only the frontend provenance artifact for that run and attempt.
8. Validate `schema_version`, `component="frontend"`, source repository, exact
   merged SHA, `refs/heads/main`, workflow name/ref, run ID, run attempt, and
   ECR repository.
9. Independently compare and require equality among the workflow-produced
   digest, receipt digest, and AWS/ECR-reported digest for the published tag.
10. Preserve the canonical
    `repository@sha256:<frontend-digest>` reference for CLOUD-V1-1B.2.
11. Prove no Kubernetes deployment, backend rollout, or other runtime mutation
    occurred during publication.

CLOUD-V1-1B.1-B proves Git commit → GitHub Actions run → immutable frontend
artifact custody. It does not prove Kubernetes runtime behavior, ALB routing,
TLS, WAF, DNS, or browser authentication.

## Explicit non-goals

CLOUD-V1-1B.1-A does not create or change:

- a `topo-frontend` Deployment, Service, NodePort, ServiceAccount, PDB, or
  runtime ConfigMap;
- the backend Deployment, backend ClusterIP, observer, RDS, or migrations;
- Terraform infrastructure, IAM, ECR configuration, an ALB, target group, or
  security-group rule;
- ACM certificates, Porkbun DNS, Route53, WAF, or `app.topoai.io`;
- the backend browser-origin setting;
- human credential material or browser-session acceptance;
- the production public edge; or
- autonomous remediation or execution.

At the end of 1B.1-A, the repository has source capable of building and later
publishing an immutable frontend artifact, but no frontend artifact has been
published and no workload or public endpoint has been created.
