# PH-2D Agent and Provider Authentication Hardening v1

PH-2D preserves the authentication-domain split accepted in PH-2A through
PH-2C. Human API tokens and browser sessions, Topo Agent bearer tokens, and
change-source provider credentials remain separate authorities. No credential
from one domain authenticates a request in another domain.

## Atomic agent enrollment

An enrollment token is consumed with one conditional database update. The
predicate requires the digest to exist, the token not to be revoked or expired,
and `use_count < max_uses`. Exactly one affected row is required. The increment
and the new agent row are committed by the same SQLAlchemy session and
transaction; any agent insert or commit failure rolls both operations back.

The raw agent bearer token is generated only after the conditional update wins,
is persisted only as a SHA-256 digest plus a bounded hint, and is placed in the
response only after the shared transaction commits. Enrollment rejections use
one public message regardless of whether the credential is unknown, revoked,
expired, exhausted, or lost a concurrent race.

The measured concurrency claim is intentionally bounded: enrollment-token
max-use consumption is atomic for the temporary file-backed SQLite test path
and the PostgreSQL 16 READ COMMITTED production baseline.

## Agent steady-state boundary

Agent runtime routes continue to require a non-revoked Topo Agent bearer token.
They do not use browser sessions or human API tokens and do not require browser
CSRF validation. Existing cluster and namespace binding checks remain in the
runtime submission routes. Revocation remains durable and takes effect on the
next request, including after application restart.

## Provider callback boundary

Provider callbacks continue to authenticate the exact raw request body before
JSON parsing or durable delivery persistence. Unknown and disabled sources, and
missing or invalid caller credentials, return the same generic 401 response.
A genuine server-side authentication configuration outage returns a generic
503 without revealing the secret reference.

Supported verifier paths remain provider-specific:

- GitHub: HMAC-SHA256 over the raw body.
- GitLab: signing-token verification with the existing timestamp window, or
  the explicitly configured legacy secret-token mode.
- HCP Terraform: HMAC-SHA512 over the raw body.
- Jenkins: Topo HMAC-SHA256 over the raw body.
- Azure DevOps: configured HTTP Basic credentials.

GitLab signing provides a bounded signed-timestamp replay window. The other
provider paths make no such cryptographic replay-window claim. All supported
paths retain durable delivery idempotency: an identical authenticated delivery
reuses its original delivery record and cannot duplicate its domain effect.

## Persistence and custody

PH-2D adds no tables or columns and changes no Alembic revision. Provider
secrets remain server-side environment references under the existing custody
model. Agent enrollment and bearer credentials remain digest-only in product
persistence. PH-4 remains the authority for future production secret custody.
