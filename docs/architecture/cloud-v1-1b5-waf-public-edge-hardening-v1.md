# CLOUD-V1-1B.5 — WAF and public-edge hardening

## Accepted starting state and boundary

This source-only block starts from accepted base `b160dc52c85c3c1767abca641242a5e10a336a71`. The `app.topoai.io` ACM certificate is issued, HTTPS 443 is live, HTTP 80 is redirect-only, both listeners are restricted to the operator IPv4 `/32`, and both backend and frontend target groups are two of two healthy. ALB-to-worker traffic remains limited to NodePorts 32080 and 32081; worker ingress remains ALB-security-group-only; RDS is private; the observer is internal; browser allowed origins remain `[]`; WAF is absent; and `app.topoai.io` application DNS remains absent.

This block changes source and performs read-only plans only. It does not apply Terraform, mutate AWS or Kubernetes, modify Porkbun or ACM validation DNS, publish application DNS, or submit human credentials.

## WAF architecture

`edge_waf_enabled=false` is the zero-drift default. When enabled, Terraform creates one regional Web ACL and associates it only with the existing Terraform-managed `topo-golden-edge` ALB. The ACL default action is ALLOW because authentication and authorization remain backend authority; WAF is defense in depth.

The baseline wraps exactly these AWS-managed groups with deterministic priorities:

| Priority | Managed group |
| ---: | --- |
| 10 | `AWSManagedRulesCommonRuleSet` |
| 20 | `AWSManagedRulesKnownBadInputsRuleSet` |
| 30 | `AWSManagedRulesAmazonIpReputationList` |

No individual managed rule is recreated or excluded. Bot Control, CAPTCHA, Challenge, geographic blocking, custom authentication, CloudFront, API Gateway, Route 53, and another ALB are outside this authority.

## COUNT to BLOCK promotion

`edge_waf_mode` accepts only `count` or `block` and defaults to `count`.

- COUNT overrides every managed group to observation-only and makes the rate rule count matches.
- BLOCK restores each AWS-managed group's normal actions and makes the rate rule block matches.

Promotion is explicit. Evidence from legitimate and harmless malicious-pattern requests must be reviewed before BLOCK is applied. Backend authentication and backend rate controls remain authoritative in both modes.

## Rate policy and visibility

`SourceIpRateLimit` aggregates on the AWS WAF source IP, not caller-controlled `X-Forwarded-For`. Its default is 2,000 requests per source IP over 300 seconds. `edge_waf_rate_limit` is restricted to whole values from 100 through 2,000,000.

CloudWatch metrics are enabled for the Web ACL, each managed-group wrapper, and the rate rule with deterministic names. Sampled requests are disabled to avoid retaining ordinary request material.

## Logging and redaction

The dedicated log group is `aws-waf-logs-topo-golden-edge`, retained for 30 days. The WAF logging filter drops ordinary ALLOW traffic and retains only COUNT and BLOCK outcomes. TopoAI does not introduce request-body logging.

The logging configuration redacts:

- `Authorization`;
- `Cookie`; and
- `X-Topo-CSRF`, the exact CSRF header defined by `backend/app/security/session_auth.py` (represented in WAF's canonical lowercase form).

The real inbound change-source credential headers are also redacted: `X-Hub-Signature-256`, `X-Gitlab-Token`, `Webhook-Signature`, `X-Tfe-Notification-Signature`, and `X-Topo-Signature-256`.

Outputs contain only resource identity and mode metadata—never samples, headers, cookies, credentials, or tokens.

## Public-ingress safety contract

The accepted operator `/32` rules remain authoritative while `edge_public_ingress_enabled=false`. When public ingress is requested, those validation rules transition away and the ALB security group permits `0.0.0.0/0` IPv4 Internet ingress only on TCP 80 and TCP 443. Port 80 remains redirect-only and port 443 remains the accepted HTTPS listener. IPv6, other ALB ports, NodePorts, workers, EKS API, RDS, ClusterIP services, and the observer are not exposed.

A Terraform lifecycle precondition on the existing ALB security group fails the plan unless public ingress has all three prerequisites:

```text
edge_https_enabled = true
edge_waf_enabled = true
edge_waf_mode = "block"
```

Therefore public ingress with WAF disabled or WAF in COUNT mode is invalid. Documentation alone is not the safety authority.

## Staged live sequence

1. Confirm the compatibility plan with HTTPS enabled, the operator `/32`, WAF disabled, COUNT selected, and public ingress disabled is zero-change.
2. Enable WAF in COUNT mode while keeping operator-only ingress. Apply only in a separately authorized live block.
3. Confirm ACL association, log delivery, metrics, target health, and ordinary credential-free routing.
4. Probe `/`, `/healthz`, `/health`, `/ready`, and anonymous `/api/v1/system/whoami`; the latter must remain a backend-controlled 401.
5. Send bounded harmless malicious-pattern requests only to non-state-changing anonymous paths and confirm COUNT observations. Do not use destructive payloads.
6. Promote to BLOCK explicitly, then confirm selected harmless probes are blocked while legitimate endpoints remain unchanged.
7. Only after BLOCK acceptance, enable public IPv4 ingress and confirm exactly TCP 80/443 are public.
8. Keep application DNS unpublished and browser origins `[]` throughout 1B.5.

No human credentials, session cookies, CSRF mutations, login attempts, or authenticated state changes belong in this sequence.

## Webhook boundary

The inbound change-source webhook at `/api/v1/change-source-webhooks/{source_id}` loads a configured source and validates its provider-specific secret/signature. Administrative webhook routes require authenticated tenant authority. There is no credential-free webhook success route suitable for 1B.5. Webhook runtime acceptance is therefore deferred rather than fabricating a secret or weakening authentication. The WAF configuration adds no path-specific blanket block for webhook routes.

## DNS and application boundary

The app.topoai.io application DNS remains absent throughout CLOUD-V1-1B.5.

The ACM validation CNAME remains untouched for certificate renewal. No Route 53, CloudFront, A, AAAA, CNAME, wildcard, `api.topoai.io`, or application record is created. The actual `app.topoai.io -> ALB` record and exact browser origin `["https://app.topoai.io"]` remain CLOUD-V1-1B.6 authority.

## Rollback and forward fix

Before public exposure, a faulty WAF observation deployment can be rolled back by setting `edge_waf_enabled=false`, leaving the accepted operator-only TLS edge intact. After public exposure, fail closed: restore operator-only ingress or forward-fix the exact evidenced WAF rule before removing protection. Never keep public ingress while disabling WAF or returning it to COUNT; the Terraform precondition rejects that configuration. Do not widen NodePorts, bypass TLS, publish DNS early, or weaken backend authentication.

## CLOUD-V1-1B.6 handoff

CLOUD-V1-1B.6 owns Porkbun application DNS publication, the exact browser origin, controlled workload rollout, and real browser/session/CSRF acceptance. Completion of this source contract does not authorize those actions.
