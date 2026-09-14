# CLOUD-V1-1A.4C2-A0 — Initial runtime secret material

## Decision

C2-A inspection found that TopoAI had production parsers for its static
bootstrap registry and SecretStore root-key ring, but no supported
operator-facing generator. Test-only snippets were not a production
provisioning interface. This source-only block adds a small wrapper whose
production validators are authoritative; the utility does not define a new
secret format or cryptographic primitive.

The utility performs initial generation only. It does not implement token or
root-key rotation, a Kubernetes controller, Vault, External Secrets, AWS
Secrets Manager integration, or any database credential workflow.

## Authoritative formats

`TOPO_API_TOKEN_HASHES_JSON` is a JSON object keyed by lowercase, 64-character
SHA-256 hexadecimal digests. Each value is an object containing a stable,
trimmed, non-`unknown` `subject`, a `roles` JSON list of trimmed non-empty
strings, and an optional string `display_name` that defaults to the subject.
The generator supplies all three metadata fields and derives the key with the
production `app.security.api_tokens.token_digest()` function. The caller must
provide the subject and every legacy role explicitly. No tenant identity is
accepted or inferred. Legacy role metadata does not grant PH-5 permissions;
durable installation and tenant authority remain separate server-side records.

The SecretStore keyring is a JSON object with exactly `version: 1` and `keys`.
`keys` contains between one and 32 entries. Each key ID matches
`[A-Za-z0-9][A-Za-z0-9_.-]{0,63}` and maps to the canonical base64url encoding
of exactly 32 random bytes. The active key ID is a separate value and must name
a member of that mapping. C2-A0 emits one 32-byte key and validates the staged
file through `app.security.secret_keyring.load_keyring()`.

## Operator interface

Use the backend virtual environment because it contains the same production
modules and dependencies that validate these values:

```powershell
Set-Location C:\Topo-ai
& .\backend\.venv\Scripts\python.exe `
  .\scripts\cloud\generate_runtime_secret_material.py `
  --output-dir 'C:\Users\<operator>\TopoAI-private\runtime-material' `
  --subject '<stable-bootstrap-subject>' `
  --display-name '<bootstrap-display-name>' `
  --role admin `
  --role operator
```

`--output-dir` is mandatory and must resolve outside the Git worktree. The
display name is optional and defaults to the subject. At least one `--role` is
required and the option is repeated for additional legacy metadata. `--key-id`
is optional and defaults to the non-secret identifier `runtime-v1`.

The command creates exactly:

| File | Classification | Later runtime use |
| --- | --- | --- |
| `bootstrap-token.txt` | plaintext bearer credential; secret | one-time operator custody for initial authenticated access |
| `bootstrap-token-hashes.json` | security-sensitive digest and identity metadata | `bootstrap-token-hashes-json` in `topo-backend-runtime` |
| `secret-store-keyring.json` | SecretStore root key; secret | read-only mounted `secret-store-keyring.json` |
| `secret-store-active-key-id.txt` | non-secret alone, security configuration | `secret-store-active-key-id` |

Scalar files deliberately contain no trailing newline so later file-based
Secret materialization does not add one to environment values. The command
does not print any generated value and does not create a Kubernetes Secret,
Secret manifest, database password, cloud credential, or kubeconfig.

## Output safety and failure behavior

The destination is resolved before creation. The repository root and every
descendant are rejected even if the requested path used relative components.
All four final paths use exclusive creation; existing material is never
silently overwritten and there is no overwrite flag. Material is generated in
memory, the registry is parsed through `load_token_registry()`, and a
restrictive temporary keyring is parsed through `load_keyring()` before final
files are created. A handled final-write failure removes files created by that
invocation and never prints a success claim. An abrupt host/process failure can
still leave a partial set; the next invocation refuses it, requiring explicit
operator inspection and cleanup rather than overwriting an ambiguous outcome.

On POSIX, a newly created directory is set to mode `0700` and files to `0600`.
On Windows, Python permission modes do not prove restrictive Windows ACL
custody. The operator must select a private directory protected by an
appropriate user ACL and must preserve that protection when moving or backing
up the files. Git ignore rules are not the primary boundary: repository-local
output is rejected.

## Lifecycle and handoff

The plaintext bootstrap token exists because the initial operator must present
the bearer value once over the accepted authenticated path. Only its digest and
metadata enter backend configuration. The plaintext file and root-key file are
sensitive, must never be committed, attached to tickets, copied into shell
history, or printed in logs, and remain under operator custody until their
documented lifecycle permits secure deletion.

C2-A1 may now consume the existence and exact filenames of this supported
material set while designing database-role bootstrap. C2-B will generate the
real material outside the repository and combine it with separately generated
database URLs when a human materializes `topo-backend-runtime`. C2-C will use
that runtime Secret for the separate migration Job and backend rollout. This
document does not authorize those live actions and does not establish a future
rotation procedure.

No live environment was changed. No AWS API, RDS database, Kubernetes API, or
workload was accessed by C2-A0.
