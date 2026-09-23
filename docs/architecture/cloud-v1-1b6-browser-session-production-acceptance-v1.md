# CLOUD-V1-1B.6 — browser session and same-origin production acceptance v1

## Status and scope

CLOUD-V1-1B.6 is the final application-publication and browser-session
acceptance block for CLOUD-V1-1B.

The accepted prerequisite is CLOUD-V1-1B.5:

- the internet-facing ALB is public only on TCP 80 and 443;
- HTTP 80 is redirect-only;
- HTTPS 443 is active with the issued ACM certificate for app.topoai.io;
- the regional WAF is associated with the exact ALB and is in BLOCK mode;
- backend and frontend target groups are healthy;
- worker NodePorts remain reachable only from the ALB security group;
- RDS remains private;
- the ACM DNS-validation CNAME remains present for certificate renewal; and
- no human credential was submitted before this block.

## Production hostname

The only V1 browser product hostname is:

https://app.topoai.io

Porkbun remains the authoritative DNS provider.

No Route53 hosted zone, CloudFront distribution, wildcard DNS entry,
api.topoai.io hostname, or wildcard certificate is introduced by this block.

The application record is:

app.topoai.io -> topo-golden-edge-823808315.us-east-1.elb.amazonaws.com

as a Porkbun CNAME.

The existing ACM validation CNAME must remain untouched permanently.

## Production browser origin

The golden runtime ConfigMap must contain exactly:

["https://app.topoai.io"]

No wildcard origin is permitted.

No additional browser origin is permitted.

The backend consumes this value through:

TOPO_BROWSER_ALLOWED_ORIGINS_JSON

from ConfigMap:

topo-runtime-config / browser-allowed-origins-json

## Controlled live sequence

Live acceptance is intentionally staged.

1. Confirm CLOUD-V1-1B.5 remains accepted.
2. Publish only the app.topoai.io Porkbun application CNAME to the accepted
   ALB DNS hostname.
3. Verify that every authoritative Porkbun nameserver returns the exact
   application CNAME.
4. Reconfirm the ACM validation CNAME is still present.
5. Apply the reviewed topo-runtime-config production-origin source.
6. Perform a controlled topo-backend rollout because environment variables
   sourced from ConfigMaps are resolved when each Pod is created.
7. Verify two of two backend replicas become Ready.
8. Verify the live ConfigMap value is exactly
   ["https://app.topoai.io"].
9. Verify legitimate unauthenticated HTTPS behavior and WAF enforcement.
10. Only after all preceding gates pass may one transient human credential
    be used for the real browser/session acceptance.

## Browser/session acceptance

Acceptance must verify the real HTTPS browser path for:

- frontend navigation;
- direct-route refresh;
- login/session exchange;
- Secure session cookie issuance;
- expected HttpOnly and SameSite cookie behavior;
- CSRF-protected mutation;
- tenant selection;
- authenticated relative /api/* access;
- distinct 401 and 403 behavior;
- cross-origin rejection;
- wildcard-origin rejection;
- logout;
- expiry behavior; and
- continued WAF compatibility with legitimate browser traffic.

The browser must use relative /api/... requests through app.topoai.io.
The browser must not require api.topoai.io.

## Credential boundary

No durable human bearer credential may enter browser storage, frontend
source, frontend image, public environment variables, NEXT_PUBLIC_*
configuration, logs, Git history, or documentation.

Any human credential used for final acceptance is transient, submitted only
after DNS, HTTPS, WAF, and exact production Origin have been accepted, and is
not retained by the acceptance harness.

## Explicit non-goals

CLOUD-V1-1B.6 does not:

- weaken WAF policy;
- expose worker NodePorts publicly;
- expose RDS;
- activate api.topoai.io;
- introduce Route53 or CloudFront;
- add wildcard DNS or wildcard TLS;
- alter ALB routing;
- grant autonomous remediation authority; or
- replace backend authentication, authorization, tenant isolation, CSRF, or
  application rate controls.

## Acceptance invariant

CLOUD-V1-1B is complete only when:

- public DNS resolves app.topoai.io to the accepted ALB;
- ACM remains issued;
- the ACM validation CNAME remains present;
- WAF remains associated and in BLOCK mode;
- public ALB ingress remains only TCP 80 and 443;
- HTTP redirects to HTTPS;
- the production browser origin is exactly
  ["https://app.topoai.io"];
- both backend and frontend remain healthy;
- the real HTTPS browser/session path passes;
- cross-origin and forbidden requests fail closed; and
- no durable credential or browser bearer token was introduced.
