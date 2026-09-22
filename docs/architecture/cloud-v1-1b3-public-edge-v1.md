# CLOUD-V1-1B.3 - Terraform ALB and NodePort edge path v1

## Scope and accepted preflight

CLOUD-V1-1B.3 adds source for a controlled, pre-publication HTTP edge. It does
not apply Terraform or Kubernetes, publish DNS, request a certificate, create
a WAF, change browser origins, or authorize credential-bearing browser use.
No live resource was changed by this source block.

The accepted source base is
`67fdd719d88803b23a43879ef6f3485420e7431c`. The accepted 1B.3A preflight is:

| Evidence | Accepted value |
|---|---|
| AWS account / region | `297361542190` / `us-east-1` |
| EKS cluster / namespace | `topo-golden` / `topo-system` |
| VPC | `vpc-00dc74e72bd7f0129` |
| Worker security group | `sg-071e1b40296d57288` |
| Public ALB subnets | `subnet-09de63c6de35c3856`, `subnet-06a24d2d0f3185f73` |
| Private worker subnets | `subnet-04b0e6ad9a4d43e34`, `subnet-09b8a7fcc2a7be527` |
| Managed node groups | `topo-golden-us-east-1a`, `topo-golden-us-east-1b` |
| Accepted runtime | backend `2/2`, frontend `2/2`, observer `1/1` |
| Browser origins | `[]` |
| Existing private Services | `topo-backend`, `topo-frontend-internal` |
| Existing public-edge resources | zero NodePorts, Ingresses, controller, ALBs, target groups, ACM certificates, regional WAF ACLs, and application DNS records |
| Terraform foundation | zero drift |

Observed managed-ASG names are evidence only and are deliberately absent from
source. Terraform derives current and replacement ASG identity from the
managed node-group resources.

## Kubernetes edge Services

`infrastructure/kubernetes/golden/edge-services.yaml` adds two Services:

| Service | Selector | Service/target | NodePort | Policy |
|---|---|---|---:|---|
| `topo-backend-edge` | `topo-backend`, component `api` | 80 / named `http` (8000) | `32080` | `externalTrafficPolicy: Cluster` |
| `topo-frontend` | `topo-frontend`, component `web` | 80 / named `http` (3000) | `32081` | `externalTrafficPolicy: Cluster` |

These deterministic NodePorts are private worker entry points, not public
Services. The accepted `topo-backend` and `topo-frontend-internal` ClusterIP
Services remain unchanged. There is no Service annotation, `externalIPs`,
`LoadBalancer`, Ingress, Helm ingress lifecycle, or AWS Load Balancer
Controller.

## ALB and network boundary

Terraform creates one internet-facing IPv4 Application Load Balancer in the
existing two Terraform-managed public ALB subnets. It uses a dedicated
security group with no unrestricted ingress or egress.

The input `edge_validation_ipv4_cidrs` is a `list(string)` with the fail-closed
default `[]`. Populated values must be unique valid IPv4 `/32` host CIDRs;
`0.0.0.0/0`, VPC-wide, subnet-wide, office-wide, and IPv6 ranges are therefore
rejected. Multiple operator hosts remain representable as multiple `/32`
entries. This is temporary pre-publication validation authority, not durable
public exposure. A live operator CIDR must be supplied out of source for the
separately approved live operation. No personal/operator IP is checked into
this repository. `203.0.113.10/32` is RFC 5737 documentation space used only
for static plan validation and is never a live operator CIDR.

During 1B.3 the ALB security group permits TCP 80 only from that explicit
input. It has exactly two outbound SG-to-SG rules: TCP 32080 and TCP 32081 to
the worker security group. The worker security group gains matching inbound
rules whose source is only the ALB security group. No new NodePort rule uses
an Internet, IPv6, VPC, subnet, office, VPN, or operator CIDR. Existing
worker/control-plane rules, including required internal worker self-traffic,
remain untouched; no external NodePort authority is added except the ALB SG.

Workers remain in the accepted private subnets with no public-address
requirement. The ALB hostname is diagnostic infrastructure identity only. Its
obscurity is not a security control and it is not the TopoAI product hostname.

## Targets and managed-ASG convergence

Both target groups use `target_type = "instance"` in the golden VPC:

| Target group | Port | Health path | Health port | Matcher |
|---|---:|---|---|---|
| Backend | 32080 | `/ready` | `traffic-port` | `200` |
| Frontend | 32081 | `/healthz` | `traffic-port` | `200` |

Neither group targets Pod IPs, ClusterIP addresses, RDS, or hard-coded EC2
instances. Terraform forms a deterministic product of two availability-zone
managed node groups and two target groups. The resulting four
`aws_autoscaling_attachment` resources obtain each ASG name from
`aws_eks_node_group.golden[az].resources[0].autoscaling_groups[0].name`.
Managed worker replacement therefore converges without source edits.

## Temporary HTTP routing

The 1B.3 listener is HTTP port 80 and is reachable only from controlled
validation CIDRs. Its default action forwards to the frontend. Deterministic
backend rules are:

| Priority | Path | Target |
|---:|---|---|
| 100 | `/api/*` | Backend |
| 110 | `/health` | Backend |
| 120 | `/ready` | Backend |
| Default | Everything else | Frontend |

HTTP exists only to validate non-secret health and routing before TLS. No
human credential, login, session creation, bearer token, or secret-bearing API
request may traverse it. The browser origin remains `[]`; no hostname rule,
`api.topoai.io`, `app.topoai.io` DNS, port 443 listener, ACM certificate, WAF,
Route53 record, CloudFront distribution, frontend secret, or backend
credential is introduced.

## Terraform outputs

The stable non-secret `edge` output groups:

- ALB ARN, DNS name, zone ID, and security-group ID;
- backend and frontend target-group ARNs;
- temporary HTTP listener ARN; and
- deterministic backend/frontend NodePorts.

It exposes no credential, token, secret, application session, or database
material.

## Guarded live acceptance requirements

The following is a later, separately approved operation. This block does not
execute it.

1. Require clean merged `main`, record the exact merged SHA, and compare the accepted source files byte-for-byte.
2. Verify read-only that the caller is AWS account `297361542190`, region `us-east-1`, Kubernetes context/cluster `topo-golden`, and namespace `topo-system`.
3. Reconfirm the accepted VPC, public/private subnets, worker SG, managed node groups, private workers, runtime replica counts, private Services, and zero Terraform drift.
4. Reconfirm NodePorts 32080 and 32081 are unused and no Ingress, controller, ALB, target group, ACM certificate, regional WAF ACL, or `app.topoai.io` application DNS exists.
5. Supply the current narrow operator IPv4 CIDR out of source through `edge_validation_ipv4_cidrs`; reject world-open, IPv6, VPC-wide, subnet-wide, or unexplained authority.
6. Run formatting, validation, Kubernetes dry-runs, and a saved Terraform plan; require only the reviewed edge creates and exact SG rules.
7. Obtain explicit live-mutation approval for that exact plan and manifest before any apply.
8. Apply only the reviewed Terraform edge plan and `edge-services.yaml`; do not apply the entire Kubernetes directory or alter existing workloads/private Services.
9. Require both managed-node-group ASGs to register in both target groups, producing four healthy attachment relationships without hard-coded instance identity.
10. Require backend targets healthy only through `/ready` on 32080 and frontend targets healthy only through `/healthz` on 32081.
11. From the exact allowed validation source, verify `/api/*`, `/health`, and `/ready` route to the backend and default/root plus `/healthz` route to the frontend.
12. Use only non-secret requests; No human credential, login, session exchange, API token, cookie, or CSRF flow is permitted over HTTP.
13. Prove both private ClusterIP Services, all workload image digests, replica counts, observer routing, database, browser origin `[]`, and private-worker placement remain unchanged.
14. Prove worker NodePorts are unreachable from every unapproved external source and that the only new worker ingress source is the ALB SG.
15. Confirm there is no 443 listener, ACM, WAF, Route53, Porkbun application DNS, CloudFront, public worker address, or frontend/backend secret change.
16. Record Terraform plan/apply identity, ALB/SG/listener/target-group/ASG identities, target health, route evidence, NodePort Services, validation CIDR custody, and a fail-closed acceptance marker.

## Rollback

Rollback removes only the two edge NodePort Services and the Terraform-managed
1B.3 edge resources after a reviewed destroy plan. It must not delete or
replace the private ClusterIP Services, workloads, node groups, VPC/subnets,
NAT, EKS control plane, RDS, ECR, or observer. If rollback outcome is
ambiguous, stop routing validation, remove the temporary ALB ingress authority
when safe, preserve evidence, and reconcile Terraform state before retrying.
No broad manual deletion is authorized.

## Later handoffs

- **CLOUD-V1-1B.4** requests ACM for `app.topoai.io`, adds only the Porkbun
  ACM validation CNAME, validates HTTPS 443 under controlled access, and turns
  HTTP 80 into redirect-only behavior. It still does not publish application
  DNS or accept human credentials.
- **CLOUD-V1-1B.5** attaches and accepts regional WAF protections before final
  Internet listener exposure. Application DNS and credential-bearing browser
  acceptance remain absent.
- **CLOUD-V1-1B.6** alone publishes `app.topoai.io`, changes browser origins to
  exactly `["https://app.topoai.io"]`, and performs HTTPS browser/session
  acceptance after ACM and WAF gates pass.

Until those handoffs are separately accepted, this edge is a controlled
non-secret diagnostic path, not a public product endpoint.
