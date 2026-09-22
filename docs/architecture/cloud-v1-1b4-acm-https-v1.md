# CLOUD-V1-1B.4 — ACM DNS validation and controlled HTTPS

## Scope and accepted starting state

This source-only block prepares a single-name ACM certificate and an explicitly gated HTTPS transition for the accepted CLOUD-V1-1B.3 edge. It does not request or validate a live certificate, change Porkbun DNS, apply Terraform, mutate Kubernetes, publish application DNS, add WAF, or submit human credentials.

The accepted source base is `a51574057cd6151c6ecaa0b71914ce33ce949b41`. The accepted live environment is AWS account `297361542190` in `us-east-1`, with ALB `topo-golden-edge` at `topo-golden-edge-823808315.us-east-1.elb.amazonaws.com`, ALB security group `sg-039e2a36df4d18e31`, backend NodePort `32080`, and frontend NodePort `32081`. Both target groups were observed with two healthy targets. The current listener is controlled HTTP port 80 only, the backend browser origin remains `[]`, `app.topoai.io` application DNS is absent, and no ACM certificate or WAF Web ACL exists.

## Required invariants

- Exactly one ACM certificate is requested, for `app.topoai.io` only.
- The certificate uses DNS validation, `RSA_2048`, enabled certificate-transparency logging, and create-before-destroy lifecycle protection.
- No wildcard, apex, `www`, `api`, or other SAN is requested.
- Porkbun remains authoritative DNS. Terraform neither manages Porkbun nor creates Route 53 records.
- `app.topoai.io` application DNS must not be published until ACM/HTTPS and WAF have both passed their acceptance gates.
- An ACM DNS-validation record may exist earlier. That record proves domain control; it does not make TopoAI publicly addressable.
- The complete ACM-provided record name, type, and value are retained as authority. Porkbun's UI may display or accept a zone-relative name, but operators must compare the resulting public FQDN with the complete ACM name to avoid duplicating the `topoai.io` suffix.
- The ALB hostname is not the production product hostname, and obscurity of that hostname is not a security control.
- Human credentials are forbidden during this block and every pre-1B.6 validation step.
- No WAF, Route 53, CloudFront, public `0.0.0.0/0` ingress, or browser-origin publication is introduced here.

## Two-stage Terraform contract

The certificate request is unconditional. The serving transition is controlled by one server-side variable whose safe default is:

```hcl
edge_https_enabled = false
```

With the gate disabled:

- Terraform retains the ACM certificate request so its provider-authentic validation record can be obtained.
- The accepted HTTP port 80 listener and its existing resource addresses remain authoritative.
- The accepted default frontend and `/api/*`, `/health`, and `/ready` backend forwarding behavior remains unchanged.
- No ACM validation waiter, port 443 ingress, HTTPS listener, or HTTPS routing rule is created.

After the exact ACM validation CNAME has been added at Porkbun and its public resolution has been checked, an operator may prepare the enabled plan:

```hcl
edge_https_enabled = true
```

With the gate enabled:

- `aws_acm_certificate_validation.edge` represents the issuance gate.
- Port 443 ingress is limited to the same explicit `/32` values in `edge_validation_ipv4_cidrs`.
- The HTTPS listener uses the issued certificate ARN from the validation resource and policy `ELBSecurityPolicy-TLS13-1-2-RFC9151-INTEROP4-FIPS-2023-07`.
- HTTPS preserves the accepted routing: `/api/*`, `/health`, and `/ready` go to the backend target group; the default goes to the frontend target group.
- HTTP port 80 becomes redirect-only. Its default and all path-specific rules return `HTTP_301` to HTTPS port 443 while preserving host, path, and query.
- Existing HTTP listener and rule addresses are retained; the transition is an in-place action change rather than needless resource-address churn.

The validation resource intentionally has no Terraform-managed DNS record. An enabled apply would wait for ACM issuance, so it must not begin until the external DNS validation record has been published and checked.

## Output and Porkbun handoff

The grouped `tls` output exposes only non-secret certificate handoff data:

- certificate ARN;
- exact certificate domain;
- current ACM status;
- exactly one validation record with complete name, type, and value;
- the HTTPS gate state; and
- the selected ALB TLS policy.

The safe operational handoff is:

1. Apply only the disabled gate plan, which must add exactly the ACM certificate and leave accepted edge resources unchanged.
2. Read `terraform output -json tls` and preserve the complete validation record.
3. At Porkbun, add only that ACM validation CNAME. Do not add the `app.topoai.io` application CNAME.
4. Query public DNS for the complete ACM validation name and confirm that it resolves to the ACM value. Account for any zone-suffix behavior in the Porkbun form.
5. Confirm ACM reports `ISSUED` before accepting the enabled HTTPS apply. Do not treat a pending certificate as usable.
6. Plan with the gate enabled and review the validation waiter, controlled 443 rule, HTTPS listener and routes, and the HTTP redirect-only transition.

ACM validation CNAME records should normally remain after issuance so managed renewal can continue. Removal is a deliberate later lifecycle decision, not part of application DNS publication.

## Controlled HTTPS acceptance

Before WAF and application DNS, validation remains operator-controlled through the existing `/32` allowlist. No browser login is performed. Use TLS hostname verification without bypass flags by resolving the product hostname locally to the current ALB addresses, for example:

```powershell
$AlbName = "topo-golden-edge-823808315.us-east-1.elb.amazonaws.com"
curl.exe --connect-to "app.topoai.io:443:${AlbName}:443" "https://app.topoai.io/healthz"
curl.exe --connect-to "app.topoai.io:443:${AlbName}:443" "https://app.topoai.io/health"
curl.exe --connect-to "app.topoai.io:443:${AlbName}:443" "https://app.topoai.io/ready"
curl.exe --connect-to "app.topoai.io:443:${AlbName}:443" "https://app.topoai.io/api/v1/auth/session"
```

Do not use `-k` or `--insecure`; a certificate-name or trust failure is an acceptance failure. No human credentials, session cookie, CSRF token, or tenant data may be submitted. HTTP checks should confirm an `HTTP_301` redirect that preserves host, path, and query. Target-group health must remain two of two for both backend and frontend, and browser allowed origins must remain exactly `[]`.

## Plan acceptance

Plan A uses the current real operator `/32` only in an untracked temporary variable file and sets `edge_https_enabled = false`. It must report exactly one resource to add—the ACM certificate—with zero changes and zero destroys. It must not add the validation waiter, 443 ingress, HTTPS listener, or HTTPS rules, and it must not change any accepted 1B.3 address.

Plan B also uses the temporary `/32` and sets `edge_https_enabled = true`. It is a representation review only; no apply is allowed. It must show the validation waiter, bounded 443 ingress, HTTPS listener, mirrored HTTPS routes, and the in-place conversion of every HTTP action to redirect. It must not contain application DNS, WAF, Route 53, CloudFront, Kubernetes changes, or broad ingress.

## Rollback

If controlled HTTPS validation fails after a later authorized apply, first restore `edge_https_enabled = false`. That removes the HTTPS serving resources and restores the accepted HTTP forwarding actions without replacing their resource addresses. Keep the ACM certificate request and its validation CNAME unless certificate abandonment is an explicit decision; retaining the CNAME preserves renewal ability. Do not publish application DNS as a workaround, widen the security group, disable certificate verification, or submit credentials.

## Later-block handoff

- CLOUD-V1-1B.5 owns regional WAF attachment and acceptance. HTTPS completion does not authorize public application exposure.
- CLOUD-V1-1B.6 owns the actual Porkbun application CNAME, exact backend browser origin `["https://app.topoai.io"]`, controlled rollout, and real browser/session acceptance.

No live resource was changed while preparing this contract.
