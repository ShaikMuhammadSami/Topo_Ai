# CX-0 DNS/public-host transition plan

No DNS change is authorized by this plan.

The current product host is `app.topoai.io`, a Porkbun CNAME to
`topo-golden-edge-823808315.us-east-1.elb.amazonaws.com`. Before any later ALB
deletion, an architect must choose and review exactly one transition:

1. repoint `app.topoai.io` to an accepted low-cost private-beta/development
   surface; or
2. intentionally replace/remove the application CNAME and verify that the
   retired hostname no longer targets the ALB.

The ACM validation CNAME is independent of the application CNAME. It is a
durable lifecycle record and must remain unless the certificate strategy is
intentionally abandoned:

- owner: `_ae02df53f40f7c96b34bc6e98fb69e1d.app.topoai.io.`
- value: `_fd79c652992203959600f955507f54f4.wzccmgtwzk.acm-validations.aws.`

Required pre-transition evidence includes the exact current authoritative
answers from each Porkbun nameserver, ACM issuance/in-use status, the chosen
replacement target, TTL-aware convergence expectations, rollback authority,
and a check that no human credential is sent to an unaccepted target.

Future product surface direction remains:

- `topoai.io` — marketing
- `app.topoai.io` — authenticated product
- `docs.topoai.io` — documentation

No reliance on DNS obscurity is a security control. CX-0A performs only
read-only resolution and emits no Porkbun credential or mutation request.
