# CX-0 durable accepted evaluation receipts

This tracked directory is the durable release-evidence authority for accepted,
sanitized G1-G6 scenario receipts. `evaluation/results/` remains ignored
scratch space and is never sufficient for gate acceptance.

Before a G1-G6 gate is accepted, its quiescent result family must be copied or
finalized here with:

- the schema-valid scenario receipt;
- the deterministic semantic-validator decision;
- `artifact-integrity-v1.json` generated and verified under
  `evaluation-artifact-integrity-v1`; and
- a small manifest binding the scenario ID, receipt SHA-256, EAI-1 tree
  SHA-256, source commit/tree, and immutable artifact identities.

Recommended layout:

```text
docs/architecture/evaluation/receipts/cx0/
  <scenario-id>/
    <accepted-receipt-id>/
      scenario-receipt.json
      semantic-validation.json
      receipt-authority.json
      artifact-integrity-v1.json
```

Only sanitized evidence may be tracked. Credentials, tokens, cookies,
database URLs, kubeconfig material, SecretStore values, raw secret-bearing
provider payloads, and customer data are forbidden.

G6 must bind every accepted durable receipt identity and hash into the
`GOLDEN_EVALUATION_RECEIPT_V1` closure artifact. A scratch result, missing EAI
manifest, failed semantic validation, or untracked receipt cannot satisfy the
gate.
