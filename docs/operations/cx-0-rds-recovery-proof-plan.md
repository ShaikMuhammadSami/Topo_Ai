# CX-0 RDS recovery proof plan

This is a plan, not an executable restore harness. CX-0A.1 does not create a
snapshot, restore a database, alter RDS, or read database credentials.

## Independent SecretStore recovery authority

The exact complete golden keyring is retained independently of PostgreSQL in
AWS Secrets Manager. The recovery payload is binary and must remain in memory
through verification and any later separately authorized delivery:

```ini
RECOVERY_SECRET_NAME=topo/golden/recovery/secret-store-keyring-v1
RECOVERY_SECRET_ARN=arn:aws:secretsmanager:us-east-1:297361542190:secret:topo/golden/recovery/secret-store-keyring-v1-Y8D1I4
ACTIVE_KEY_ID=runtime-v1
KEYRING_SHA256=adb0bf496822d35043eeb7355a00f6819f095ca77179488d56f14c521ac058ff
```

```text
DURABLE_EXTERNAL_AUTHORITY
COST_0_RETAIN
DO_NOT_DELETE_DURING_CX_0B
```

Recovery procedure:

1. authenticate to account `297361542190` in `us-east-1` through the approved
   operator identity;
2. describe the exact named recovery object and require its recorded ARN;
3. retrieve `AWSCURRENT` as `SecretBinary` into process memory only;
4. calculate SHA-256 in memory and require the recorded fingerprint above;
5. parse the version-1 keyring in memory and require the recorded active key ID
   to exist in it;
6. under a separately reviewed restore allowlist, deliver those exact bytes to
   the isolated recovery runtime without shell arguments, logs, or plaintext
   files;
7. verify SecretStore readiness and decrypt/use only a purpose-built
   non-sensitive test secret; and
8. retain the recovery object unchanged after the proof.

Any absent object, identity difference, fingerprint difference, missing active
key, `SecretString` payload, or unexpected version blocks recovery. Recovery
never generates, replaces, updates, rotates, or deletes root-key material.

The future CX-0A.4 harness requires separate review and an exact mutation
allowlist. Its accepted sequence must:

1. create a final encrypted snapshot without altering the source instance;
2. record the snapshot ARN, encryption/KMS metadata, and source identity;
3. create an isolated temporary restore target;
4. restore the snapshot;
5. deliver the verified Secrets Manager keyring through the separately
   controlled in-memory procedure above;
6. verify PostgreSQL engine, schema, and the exact Alembic revision;
7. verify bounded representative tenant/application records;
8. prove decrypt/use with a purpose-built non-sensitive test secret;
9. run bounded application smoke checks against only the restored database;
10. record a secret-safe restore receipt;
11. remove only the temporary restore target under the reviewed allowlist; and
12. prove the original accepted RDS instance remained unchanged.

The proof must not print a connection URI, master password, Secrets Manager
value, SecretStore key, plaintext/ciphertext payload, or session credential.
Failure at any gate leaves the original instance intact.

Current status:

```text
RDS_RESTORE_PROVEN=NO
ORIGINAL_RDS_DELETION_AUTHORIZED=NO
TEARDOWN_AUTHORIZED=NO
```
