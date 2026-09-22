# CLOUD-V1-1B.0 — public edge and browser authentication contract v1

## Status and scope

This document is the architecture-only contract for exposing the TopoAI V1
browser product at `https://app.topoai.io`. It records the boundary that later
implementation blocks must satisfy. It does not create or alter an AWS,
Kubernetes, DNS, certificate, WAF, database, browser-authentication, or runtime
resource.

The contract is reconciled against the current repository rather than assuming
a future implementation already exists. In particular:

- the frontend API transport accepts only relative `/api/...` paths and calls
  `fetch` with `credentials: "same-origin"`;
- the current Next.js rewrite sends local `/api/:path*` traffic to
  `TOPO_BACKEND_URL` and remains useful for local development;
- the backend session exchange, secure cookies, CSRF validation, and exact
  origin configuration already exist;
- the checked-in golden browser-origin value is currently the deny-all `[]`,
  not the production origin;
- `topo-backend` is currently a `ClusterIP` Service; and
- the Terraform foundation exports two public subnets for a later ALB but does
  not currently provision one.

## 1. Accepted golden runtime preserved

The accepted live runtime at the start of CLOUD-V1-1B is:

| Property | Accepted value |
|---|---|
| AWS account | `297361542190` |
| AWS region | `us-east-1` |
| EKS cluster | `topo-golden` |
| Worker placement | Private worker nodes across the existing two-AZ foundation |
| Backend | `topo-backend` Deployment with two Ready replicas |
| Database | Private PostgreSQL RDS |
| Observer | Live singleton `topo-observer` |
| Observer data path | Authenticated topology ingestion is working through the internal backend Service |
| Backend Service | Existing private/internal `ClusterIP` |
| Schema | Migrations frozen through `0015_security_audit` |

CLOUD-V1-1B.0 changes none of those resources or assertions. It creates no
runtime and grants no authority to redeploy them.

## 2. Public domain ownership and hostname contract

The production domain is `topoai.io`, registered with Porkbun. Porkbun remains
the authoritative V1 DNS provider. No Route53 hosted zone and no domain
transfer are required.

| Hostname | V1 disposition |
|---|---|
| `app.topoai.io` | The authenticated TopoAI browser product. This is the only hostname activated by CLOUD-V1-1B. |
| `topoai.io` | Reserved for a future marketing/root site. |
| `www.topoai.io` | Reserved for a future marketing alias. |
| `api.topoai.io` | Reserved for a later external-agent/public-API boundary. It is not needed by the V1 browser. |

Neither wildcard DNS nor a wildcard TLS certificate is required. The initial
certificate covers only `app.topoai.io`.

## 3. Same-origin browser boundary

The production browser sees exactly one origin:

```text
https://app.topoai.io
```

The routing model is:

```text
browser: https://app.topoai.io
             |
             | relative /api/... and page requests
             v
     internet-facing AWS ALB
         |               |
         | /api/*        | default
         | /health       |
         | /ready        |
         v               v
  backend target     frontend target
  group/NodePort     group/NodePort
```

Frontend browser calls remain relative `/api/...` requests. The current source
guard that rejects non-`/api/` paths and the `credentials: "same-origin"`
fetch option are production invariants.

The browser must never:

- store an API/operator token in `localStorage`, `sessionStorage`, IndexedDB,
  or another durable browser store;
- place an API/operator token in a URL;
- place an API/operator token or other secret in a `NEXT_PUBLIC_*` variable;
- embed a durable credential in the frontend image;
- require `api.topoai.io` for browser operation; or
- make browser API requests cross-origin.

The frontend's existing `TOPO_BACKEND_URL` Next.js rewrite may continue to
support local development. AWS production does not depend on it: the ALB owns
the `/api/*` path split before the request reaches the frontend target.

## 4. Browser authentication and CSRF contract

The existing browser session exchange remains authoritative:

1. A human enters an operator/API credential into the login form.
2. The frontend sends it once, in the `Authorization` header, to
   `POST /api/v1/auth/session`.
3. The backend validates human API-token authority and the exact request
   origin, then issues an opaque server-backed browser session.
4. The frontend clears the credential from component state and does not
   persist it.

The cookie contract remains:

| Cookie | Required attributes | Purpose |
|---|---|---|
| `topo_session` | `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/` | Opaque browser-session authority; raw authority is not browser-readable. |
| `topo_csrf` | `Secure`, browser-readable, `SameSite=Lax`, `Path=/` | Double-submit value used only for CSRF protection. |

Unsafe browser methods (`POST`, `PUT`, `PATCH`, and `DELETE`) copy the
`topo_csrf` value into `X-Topo-CSRF`. The original human credential is not the
ongoing browser authority.

Production browser origins must be configured as exactly:

```json
["https://app.topoai.io"]
```

`*`, alternate schemes, alternate ports, and unrelated origins are forbidden.
The current golden ConfigMap contains `browser-allowed-origins-json: "[]"` and
therefore is not yet production-ready. A later guarded runtime block must
change it; CLOUD-V1-1B.0 does not mutate it.

## 5. Production edge routing

The public workload edge is one internet-facing AWS Application Load Balancer
managed by Terraform. Kubernetes does not provision or own the ALB.

V1 deliberately does not introduce:

- AWS Load Balancer Controller;
- a Kubernetes `Ingress` object;
- a Helm/controller lifecycle for the golden ALB; or
- a second browser API hostname.

The ALB uses the two existing public ALB subnets exported by the foundation as
`public_alb_subnet_ids`. Its final HTTPS listener routing is deterministic:

| Listener match | Target |
|---|---|
| `/api/*` | Backend target group |
| `/health` | Backend target group |
| `/ready` | Backend target group |
| Default | Frontend target group |

The order must ensure the explicit backend rules win over the default frontend
rule. The routing preserves one browser origin while keeping frontend and
backend as independent immutable workloads.

## 6. Kubernetes edge Service contract

The existing `topo-backend` ClusterIP Service remains unchanged and private.
It continues to serve in-cluster clients such as `topo-observer`.

A later guarded block introduces two separate edge Services:

- `topo-backend-edge`, a `NodePort` Service selecting the existing backend
  Pods; and
- `topo-frontend`, a `NodePort` Service selecting the frontend Pods.

Both NodePort values must be deterministic in source, fall within the
Kubernetes NodePort range, and be checked for collision against the live
cluster before deployment. They are not public endpoints. No NodePort may be
opened to `0.0.0.0/0`, an office CIDR, or any source other than the ALB
security group.

The worker security group permits only the exact two edge TCP ports from the
ALB security group. The Services use `externalTrafficPolicy: Cluster` unless a
later measured implementation proves another policy is required.

## 7. Terraform-managed ALB target model

Both ALB target groups use `target_type = "instance"` and forward to the
corresponding Kubernetes NodePort on private worker instances.

Terraform attaches the Auto Scaling Groups owned by the managed EKS node
groups to both target groups. It must derive those groups from the managed node
group resources and must not hard-code the current EC2 instance IDs. A worker
replacement must therefore converge into the target groups automatically.

The backend target group:

- forwards to the backend edge NodePort;
- health-checks `/ready`;
- relies on the existing public/minimal, unauthenticated readiness route;
- treats readiness as serving eligibility, not authentication authority; and
- never exposes database errors, URLs, or credentials through its health body.

The frontend target group:

- forwards to the frontend NodePort; and
- uses a dedicated, non-secret frontend health endpoint introduced and tested
  with the frontend runtime.

The ALB security group permits Internet ingress only on intended listener
ports. In the final state those are TCP 443 and TCP 80, where 80 performs only
an HTTPS redirect. Its egress is bounded to the worker security group on the
two edge NodePorts. The worker security group has no Internet NodePort rule.

The ALB is the only Internet-facing workload edge. The EKS workers remain in
private subnets and require no public addresses.

## 8. Frontend immutable artifact contract

CLOUD-V1-1B.1 creates the frontend artifact without deploying it. The expected
artifact is:

- a production Next.js container;
- installed deterministically from `package-lock.json`;
- built in production mode;
- run as a non-root user;
- equipped with an explicit non-secret health endpoint;
- built without secret build arguments or `NEXT_PUBLIC_*` API secrets;
- published independently from the backend and observer workflows;
- addressed by immutable ECR digest and a component-specific immutable tag;
  and
- accompanied by a `topo-cloud-golden-artifact-v1` provenance receipt with
  `component="frontend"`.

The existing GitHub OIDC publisher role and ECR repository should be reused if
source inspection confirms their existing least-privilege ECR authority is
sufficient. A workflow must never deploy Kubernetes or gain broad AWS
authority merely because it publishes the frontend image. `latest` is
forbidden.

## 9. Frontend Kubernetes runtime contract

CLOUD-V1-1B.2 introduces the frontend workload with:

- two replicas on the existing private EKS workers;
- no AWS IAM workload authority;
- service-account token automount disabled;
- non-root execution;
- privilege escalation disabled;
- all Linux capabilities dropped;
- seccomp `RuntimeDefault`;
- a read-only root filesystem where compatible with measured Next.js runtime
  behavior;
- only explicitly bounded writable ephemeral paths if runtime evidence proves
  they are necessary;
- dedicated readiness and liveness checks against a non-secret frontend health
  endpoint;
- a PodDisruptionBudget preserving one replica;
- a rolling update that preserves availability;
- explicit resource requests and limits;
- topology spreading across the two worker/AZ fault domains where scheduling
  permits; and
- no application secret in frontend environment variables, ConfigMaps, or
  image layers.

The frontend Deployment does not gain direct backend credentials. Browser
requests reach the backend through same-origin ALB routing.

## 10. TLS and Porkbun DNS contract

CLOUD-V1-1B.4 requests an ACM certificate in `us-east-1` for only:

```text
app.topoai.io
```

ACM uses DNS validation. Because Porkbun remains authoritative:

1. Terraform/AWS requests the certificate.
2. ACM returns the DNS validation record name and value.
3. An operator adds only that ACM validation CNAME at Porkbun.
4. Certificate issuance is verified before enabling the HTTPS listener.
5. HTTPS 443, the certificate, routing, and health are validated through
   bounded operator-controlled access.
6. HTTP 80 is configured as redirect-only where appropriate.

The ACM validation CNAME and the application CNAME are different records with
different purposes. An ACM DNS-validation record may exist before public
application DNS and does not make the TopoAI application publicly addressable.
CLOUD-V1-1B.4 must not publish the `app.topoai.io` application CNAME. That
record is deferred until CLOUD-V1-1B.6, after both ACM/HTTPS and WAF have passed
their acceptance gates.

No Route53 hosted zone is created merely to automate certificate validation.

The eventual final edge serves application traffic on HTTPS 443. HTTP 80
redirects to HTTPS and must not accept, proxy, or be used to test browser
authentication. No browser login or human credential submission occurs in
CLOUD-V1-1B.4, including through the AWS-generated ALB hostname.

## 11. WAF contract

Before final public production acceptance, a regional AWS WAFv2 Web ACL is
associated with the ALB. CLOUD-V1-1B.5 defines and validates its exact rules.
At minimum the policy provides:

- managed baseline protections;
- bounded rate protection;
- explicit validation that legitimate browser, API, login/session, CSRF, and
  future approved webhook behavior is preserved; and
- staged observation/validation before any block-mode rule is accepted.

CLOUD-V1-1B.5 confirms legitimate frontend, backend health, and API behavior
without performing browser-session acceptance or submitting a human
credential. Only after the WAF acceptance gate passes may the ALB transition
to its intended final Internet listener exposure. The application CNAME still
remains unpublished until CLOUD-V1-1B.6.

WAF is defense in depth. It does not replace backend authentication,
authorization, tenant isolation, CSRF enforcement, input validation, or rate
controls owned by the application.

## 12. Public API and agent scope

`api.topoai.io` is not activated by CLOUD-V1-1B. Browser traffic uses only
`app.topoai.io`.

The current in-cluster observer continues to send authenticated traffic to:

```text
http://topo-backend.topo-system.svc.cluster.local
```

It does not traverse the public ALB and remains unchanged. A later external
customer-agent/public-API block may activate `api.topoai.io` with its own
explicit authentication, abuse, TLS, and availability boundary. That later
decision must not make browser traffic cross-origin or weaken the
`app.topoai.io` same-origin model.

## 13. Phased publication safety

The guarded delivery sequence is:

```text
1B.0  architecture contract only
  -> 1B.1 frontend immutable artifact
  -> 1B.2 frontend Kubernetes runtime
  -> 1B.3 Terraform ALB, target groups, and NodePort edge path
  -> 1B.4 ACM validation DNS and controlled HTTPS validation
  -> 1B.5 WAF and public-edge hardening
  -> 1B.6 application DNS publication and browser/session acceptance
```

In 1B.3, ALB, target-group, routing, security-group, and NodePort validation is
bounded to operator-controlled access and non-secret health checks. The
`app.topoai.io` application DNS record is not published, no human credential is
submitted, and the AWS-generated ALB hostname is not treated as the production
product hostname. Obscurity of that AWS hostname is not a security control;
access remains bounded by explicit listener, network, and acceptance controls.

In 1B.4, only the ACM DNS-validation CNAME is added at Porkbun. Certificate
issuance, HTTPS 443, redirect-only HTTP 80, routing, and health receive
controlled validation. Application DNS remains unpublished and browser login
remains forbidden.

In 1B.5, the WAF is attached and its managed baseline, bounded rate controls,
and legitimate health/API/frontend behavior are accepted before the ALB moves
to its intended final Internet listener exposure. Application DNS remains
unpublished, and browser-session acceptance is still forbidden.

Before 1B.6:

- HTTPS, target health, routing, and WAF are accepted;
- the `app.topoai.io` application CNAME is absent;
- human credentials have not been submitted in any pre-1B.6 validation;
- the backend continues to use the already accepted immutable artifact unless
  a separately reviewed source change requires a new digest; and
- every rollout is controlled and separately accepted.

In 1B.6, the operator publishes `app.topoai.io` to the ALB DNS hostname at
Porkbun and verifies public DNS convergence. The backend origin setting is then
set to exactly `["https://app.topoai.io"]` through any required controlled
rollout before real HTTPS browser/session acceptance begins.

## 14. Explicit non-goals for 1B.0

CLOUD-V1-1B.0 does not implement or mutate:

- an ALB, listener, target group, security-group rule, or Auto Scaling Group
  attachment;
- Porkbun DNS, Route53, ACM, TLS, or WAF;
- a frontend Dockerfile, image workflow, image, Deployment, Service, or PDB;
- a backend or frontend NodePort Service;
- a Kubernetes `Ingress` or AWS Load Balancer Controller;
- the backend deployment or browser-origin runtime value;
- `api.topoai.io`, `topoai.io`, `www.topoai.io`, or a marketing site;
- autonomous remediation or execution;
- database schema or migration history;
- observer workload, identity, RBAC, credentials, or routing; or
- human credentials or credential rotation.

## 15. Required follow-on blocks and gates

### CLOUD-V1-1B.1 — immutable frontend artifact

Responsibilities: add the production frontend Docker build, bounded context,
credential-free validation, independent manual publication path, immutable tag
and digest identity, and `component="frontend"` provenance receipt.

Acceptance gate: deterministic local/CI build passes; the image runs non-root
with no embedded secret; the health endpoint works; GitHub OIDC, workflow,
receipt, and ECR independently agree on the exact immutable digest; and no
deployment occurs.

### CLOUD-V1-1B.2 — frontend Kubernetes runtime

Responsibilities: add the hardened two-replica frontend Deployment,
ServiceAccount, private Service needed for runtime validation, PDB, rolling
strategy, resource bounds, topology spread, and health probes. Prove any
writable filesystem exception rather than assuming it.

Acceptance gate: both replicas become Ready on private workers, remain
available through a bounded rollout/disruption check, expose no secret or IAM
authority, and serve the dedicated health endpoint. The workload is not yet a
credential-bearing public login surface.

### CLOUD-V1-1B.3 — Terraform public ALB and NodePort edge path

Responsibilities: add deterministic backend/frontend edge NodePort manifests;
perform live collision prechecks; add the Terraform-managed internet-facing
ALB, instance target groups, managed-node-group ASG attachments, listener path
rules, and SG-to-SG NodePort restrictions.

Acceptance gate: no existing ClusterIP is replaced; target groups converge
without hard-coded instances; backend and frontend health checks pass;
`/api/*`, `/health`, `/ready`, and default routing reach the correct targets;
workers remain private; NodePorts reject non-ALB sources; validation remains
operator-controlled; application DNS is not published; and no human credential
is submitted. The ALB DNS name is diagnostic infrastructure identity, not the
production product hostname or a security boundary.

### CLOUD-V1-1B.4 — ACM, Porkbun DNS, and HTTPS

Responsibilities: request the `app.topoai.io` ACM certificate in `us-east-1`,
record and add only the exact Porkbun ACM validation CNAME, verify certificate
issuance, activate and control-validate the 443 listener, and configure the
80-to-443 redirect where appropriate. Do not publish the Porkbun application
CNAME and do not perform browser login or submit a human credential.

Acceptance gate: hostname and certificate match; the chain validates; HTTPS
routing and health work through controlled access; HTTP only redirects; the ACM
validation and application DNS records are explicitly distinguished;
`app.topoai.io` application DNS remains absent; no credential was submitted;
no mixed-content/cross-origin dependency exists; and no Route53 zone or
wildcard certificate was created.

### CLOUD-V1-1B.5 — WAF and public-edge hardening

Responsibilities: attach a regional WAFv2 Web ACL, define managed baseline and
bounded rate rules, validate legitimate application behavior, and promote
rules to block mode only from observed evidence. After acceptance, transition
the ALB to its intended final Internet listener exposure while keeping the
application CNAME unpublished. Do not perform human browser-session
acceptance.

Acceptance gate: the ACL is attached to the exact ALB; malicious probes are
bounded as designed; legitimate non-credential health, API, frontend, and
approved webhook behavior remains functional; logs expose no secret; backend
auth remains authoritative; application DNS remains absent; and no human
credential or browser login was used.

### CLOUD-V1-1B.6 — browser session and same-origin production acceptance

Responsibilities: publish the Porkbun application CNAME
`app.topoai.io -> <ALB DNS hostname>`, verify public DNS convergence, set the
backend production origin to exactly `["https://app.topoai.io"]` through any
required controlled rollout, and only then exercise the real HTTPS browser
path through login, session cookie issuance, CSRF-protected mutation, tenant
selection, API access, logout/expiry, frontend navigation, direct-route
refresh, forbidden requests, and cross-origin rejection.

Acceptance gate: ACM/HTTPS and WAF acceptance predate application DNS
publication; public DNS resolves `app.topoai.io` to the accepted ALB; the exact
origin setting is live; the transient human credential is sent once over HTTPS
and is not retained; cookie flags and CSRF behavior match this contract;
cross-origin, forbidden, and wildcard-origin cases fail closed; tenant
selection and authenticated API access work; logout/expiry work; `/api/*` is
ALB-routed without frontend rewrite dependence; 401/403 behaviors remain
distinct; WAF permits legitimate flows; and no browser operation requires
`api.topoai.io`.

## 16. Required security invariants

All implementation and acceptance blocks must preserve these invariants:

- The browser remains same-origin at `https://app.topoai.io`.
- No durable human bearer credential enters browser storage.
- No secret enters the frontend build, image, public environment, or
  `NEXT_PUBLIC_*` configuration.
- The production Origin allowlist is exactly
  `["https://app.topoai.io"]`, never `*`.
- `app.topoai.io` application DNS must not be published until ACM/HTTPS and
  WAF have both passed their acceptance gates.
- ACM DNS-validation records may exist before application DNS; they do not make
  the TopoAI application publicly addressable.
- Human credentials are forbidden from every pre-1B.6 validation. TLS, WAF,
  application DNS, and the exact production Origin must be accepted in order
  before credential submission.
- No reliance on obscurity of the AWS-generated ALB DNS name is considered a
  security control.
- The existing backend ClusterIP remains private.
- RDS remains private and is never an ALB target.
- The in-cluster observer and its internal Service path remain unchanged.
- NodePorts accept traffic only from the ALB security group.
- The ALB is the only Internet-facing workload edge.
- Public EKS worker addresses are not required.
- All deployed artifacts use immutable digests; `latest` is forbidden.
- An image-publication workflow gains no deployment or broad AWS authority.
- Terraform remains the authority for AWS infrastructure.
- Kubernetes manifests remain the authority for workload resources.
- Porkbun remains the V1 DNS authority.
- WAF remains defense in depth and never substitutes for authentication or
  authorization.

## 17. Authority boundaries and acceptance summary

The resulting ownership model is deliberately small:

| Concern | Authority |
|---|---|
| Domain registration and V1 DNS records | Porkbun/operator |
| ALB, target groups, listeners, security groups, ACM, WAF, ASG attachments | Terraform/AWS |
| Deployments, Services, NodePorts, ServiceAccounts, probes, PDBs | Kubernetes manifests |
| Human session, CSRF, route authentication, tenant authorization | TopoAI backend |
| Relative API transport and non-persistence of login credential | TopoAI frontend |
| Immutable component identity | ECR digest plus provenance receipt |

CLOUD-V1-1B is accepted only when these authorities compose into one HTTPS
same-origin browser product without making the backend ClusterIP, NodePorts,
workers, RDS, observer, or a separate browser API hostname public.
