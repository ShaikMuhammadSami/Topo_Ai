# H3-P0 — Evaluation-Safe Actions-to-Image Provider Fixture v1

## 1. H3-P0 scope

H3-P0 creates a static, evaluation-only provider fixture. No workflow was triggered, no image or GHCR package was published, no Kubernetes workload was created, no Topo product behavior was repaired, and no Git history operation was performed.

## 2. LINEAGE-0 prerequisite being solved

LINEAGE-0 proved H1, H2, and H4–H7 but classified H3 as `PROVIDER_PREREQUISITE_BLOCKED`. The selected Actions run built a CLI archive only. It contained no provider-native relationship between the run and an immutable container digest. H3-P0 supplies a safe future mechanism for creating that missing provider fact; it does not evaluate Topo's representation of the fact.

## 3. Existing workflow/repository audit

Existing workflows before H3-P0:

| Workflow | Trigger | Output / behavior |
|---|---|---|
| `Topo CLI` (`topo-cli.yml`) | pull request; push to `main`; `cli-v*` tag | Tests/builds CLI archives; tag release job can publish a GitHub release. |
| `topo-proof` (`topo-proof.yml`) | `workflow_dispatch` | Prints run ID and commit only. |

No existing workflow used GHCR, `docker/setup-buildx-action`, `docker/login-action`, or `docker/build-push-action`. The only existing Dockerfile is `agent/Dockerfile`, which is a product image and was not reused. Existing workflow action references use major versions (`actions/checkout@v6`, `actions/upload-artifact@v7`). The fixture follows that convention and uses the current Docker action majors `setup-buildx@v4`, `login@v4`, and `build-push@v7`. Existing workflows were not modified.

## 4. Fixture architecture

```text
User workflow_dispatch after merge
        ↓ exact EVALUATION_ONLY confirmation
Checkout exact ref / GitHub context
        ↓
Lowercase evaluation GHCR path + run tag
        ↓
Build harmless linux/amd64 Alpine image
        ↓
Push with GITHUB_TOKEN
        ↓
docker/build-push-action digest output
        ↓
Structured allowlisted JSON receipt
        ├── 30-day Actions artifact
        └── safe job summary
```

The workflow file is `.github/workflows/topo-lineage-provider-fixture.yml`; the isolated build context is `evaluation/fixtures/lineage-image/`.

## 5. Trigger safety

The sole trigger is `workflow_dispatch`. There is no `push`, `pull_request`, `schedule`, `workflow_run`, `release`, `deployment`, or `repository_dispatch` trigger. The publish job additionally requires `inputs.confirm == 'EVALUATION_ONLY'`. Merging the file has zero execution side effect. There is no deployment environment, cloud action, release action, Kubernetes command, Terraform command, or package cleanup job.

## 6. Permission model

Workflow permissions are exactly:

```yaml
permissions:
  contents: read
  packages: write
```

It requests no Actions, deployment, issue, pull-request, security-event, attestation, or OIDC write permission. The repository currently has Actions enabled with `allowed_actions=all`; its default workflow permission is read, so the fixture's explicit package-write grant is visible and bounded.

## 7. Authentication model

The workflow authenticates to `ghcr.io` with `github.actor` and the built-in `secrets.GITHUB_TOKEN` through `docker/login-action`. No PAT, Docker Hub token, registry password, cloud credential, secret provisioning, repository setting mutation, or GitHub environment is required. The token is not passed to receipt generation, Docker build arguments, image labels, marker content, or the job summary.

## 8. GHCR package naming

The owner and repository name are lowercased and validated against a conservative path component pattern. The resulting package is:

```text
ghcr.io/<lower-owner>/<lower-repository>-topo-lineage-eval
```

For the current repository, the expected path is:

```text
ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval
```

The `-topo-lineage-eval` suffix prevents accidental publication to a product package.

## 9. Docker fixture

The dedicated image uses `alpine:3.22`, contains only a safe text marker with repository, commit, run ID, run attempt, and workflow reference, runs as UID/GID `65532`, exposes no port, starts no network listener, and uses a harmless long-running sleep loop. It is intentionally healthy. A later runtime-failure evaluation may override its command in a disposable Deployment without changing the provider artifact.

## 10. Build/push design

The workflow checks out the dispatched ref, configures Buildx, logs in to GHCR, and builds only `evaluation/fixtures/lineage-image/Dockerfile` for `linux/amd64`. `push: true` is explicit. The only tag is:

```text
run-<github.run_id>-<github.run_attempt>
```

No `latest` tag exists. The tag is diagnostic and never treated as immutable identity.

## 11. Digest capture

The authoritative digest comes directly from `${{ steps.build.outputs.digest }}` after the pushed build. Receipt generation rejects anything not matching lowercase `sha256:<64 hex>`. It does not guess a tag, search by time, inspect `latest`, or associate an unrelated registry artifact.

## 12. OCI provenance labels

The pushed image receives:

- `org.opencontainers.image.source`
- `org.opencontainers.image.revision`
- `topo.eval.github.run_id`
- `topo.eval.github.run_attempt`
- `topo.eval.github.workflow_ref`

All values come from safe GitHub context fields. H3-P0 deliberately does not add signing, SBOM, SLSA, cosign, OIDC, or attestation infrastructure.

## 13. Provider receipt contract

The receipt version is `eval-lineage-provider-receipt-v1`. It binds the repository and provider repository ID, exact commit SHA, workflow name/ref/SHA, run ID/attempt/number/event, GHCR image repository, diagnostic tag, immutable digest/reference, receipt time, source ref, and explicit sources for digest/commit/run evidence. Its schema and field semantics are documented separately in `lineage-provider-receipt-v1.md` and `lineage-provider-receipt.schema.json`.

## 14. Receipt security/redaction

Receipt generation constructs a Python dictionary and serializes deterministic, sorted JSON. It does not concatenate unescaped JSON or dump the environment/GitHub event. The schema disallows unknown fields. Tokens, authorization headers, passwords, full contexts, actor email, and event payloads are absent. The job summary contains only repository, commit, run identity, image repository/tag, digest, and immutable reference.

## 15. Artifact retention

The receipt artifact name is `topo-lineage-receipt-<run-id>-<attempt>` and retention is 30 days. The GHCR package has no automatic cleanup because H3-P1 and H4–H7 need the immutable artifact. Any later package cleanup is an explicit human decision after lineage proof.

## 16. What this fixture proves

After a successful future user dispatch, provider evidence can establish:

```text
exact repository + exact commit
        ↓ exact GitHub workflow head/run context
exact Actions run + attempt
        ↓ docker/build-push-action structured output
exact evaluation GHCR image digest
```

The receipt establishes build provenance independently of Topo.

## 17. What this fixture does NOT prove

H3-P0 does not prove Topo represents Actions Run → Image correctly; that is H3-P1. It does not prove the commit caused a runtime failure, does not execute H4–H7, does not deploy infrastructure, does not repair product connector/linker code, and does not establish a production container supply chain.

## 18. Files created

- `.github/workflows/topo-lineage-provider-fixture.yml`
- `evaluation/fixtures/lineage-image/Dockerfile`
- `evaluation/fixtures/lineage-provider-receipt.example.json`
- `evaluation/tests/test_h3_provider_fixture.py`
- `docs/architecture/evaluation/lineage-provider-receipt-v1.md`
- `docs/architecture/evaluation/lineage-provider-receipt.schema.json`
- `docs/architecture/evaluation/baselines/h3-p0-actions-image-provider-fixture.md`

## 19. Files modified

None. Existing workflows, product files, truth contracts, LINEAGE-0 implementation, and permanent manifests remain unchanged.

## 20. Product diff

None under `backend/app/`, `backend/tests/`, `agent/src/`, `frontend/`, or `cli/src/`.

## 21. Static safety tests

`evaluation/tests/test_h3_provider_fixture.py` contains 94 checks covering all required trigger, guard, permission, authentication, GHCR naming, tag/digest, build output, receipt, retention, OCI label, Docker safety, secret, scenario, product-diff, and manifest-hash rules. Focused result: **94 passed in 0.78s**.

The test suite uses PyYAML `BaseLoader`, explicitly preserving the GitHub Actions `on` key as a string and avoiding the YAML 1.1 boolean-key trap.

## 22. Evaluation regressions

- Evaluation compile: pass.
- Full evaluation: **286 passed in 6.92s** (`192` accepted + `94` H3-P0).

## 23. Backend regressions

- Backend compile: pass.
- Backend tests: **608 passed, 1 warning in 19.40s**.
- Warning: existing Starlette `httpx` deprecation warning only.

## 24. Agent regressions

- Agent compile: pass.
- Agent tests: **15 passed in 1.68s**.

Frontend and CLI were not run because they were not modified.

## 25. Schema validation

The representative safe receipt at `evaluation/fixtures/lineage-provider-receipt.example.json` validated against `lineage-provider-receipt.schema.json` using both the focused schema-contract test and PowerShell `Test-Json`: **True**. Unknown secret-shaped fields are rejected; evaluation redaction tests also pass.

## 26. Permanent manifest hash verification

Git blob hashes remain unchanged:

| Manifest | Hash |
|---|---|
| `sentinel-a` | `599ba19827d5097fded3f52264cad8dd35abb839` |
| `sentinel-b` | `f404607eaca904baac362edb2365fa53652565fe` |
| `sentinel-c` | `9bb3c201b190708224770a30ec9c23939623f683` |
| `sentinel-d` | `e7e2a8f4e2cde066bee209191ec27304a41193f7` |
| `blast-01` | `2f292f5ee1c116d2c2c832bc2165a61bc13dedc5` |
| `blast-02` | `695d0feda176f26c7e601a57060f4ad0d29310a9` |
| `blast-03` | `0f9974a4a5f4a08d6b01d2e02be319698175f6c1` |

## 27. GitHub provider precheck

Read-only checks established:

- authenticated GitHub account: `ShaikMuhammadSami`;
- repository: `ShaikMuhammadSami/Topo_Ai`;
- GraphQL repository ID: `R_kgDOTDRVbw`;
- visibility: private;
- default branch: `main`;
- Actions enabled: true;
- allowed actions: all;
- default workflow token permission: read;
- workflow-level `packages: write` is therefore explicit and reviewable.

No token value or credential was printed or stored. No provider mutation occurred.

## 28. Post-merge USER trigger command

Run only after architecture acceptance, user staging/commit/push, PR review, merge, and clean-main verification:

```powershell
Set-Location C:\Topo-ai

gh workflow run topo-lineage-provider-fixture.yml `
  --repo ShaikMuhammadSami/Topo_Ai `
  --ref main `
  -f confirm=EVALUATION_ONLY
```

This command was documented only and was **not executed** by Codex.

## 29. Run observation commands

After the user dispatches:

```powershell
Set-Location C:\Topo-ai

$repo = "ShaikMuhammadSami/Topo_Ai"
$run = gh run list `
  --repo $repo `
  --workflow topo-lineage-provider-fixture.yml `
  --branch main `
  --event workflow_dispatch `
  --limit 1 `
  --json databaseId,headSha,status,conclusion,createdAt,url |
  ConvertFrom-Json

$run | Format-List
$runId = [string]$run[0].databaseId

gh run watch $runId --repo $repo --exit-status

gh run view $runId `
  --repo $repo `
  --json databaseId,workflowName,headSha,headBranch,event,status,conclusion,createdAt,startedAt,updatedAt,url
```

These are read-only after the documented user dispatch.

## 30. Receipt download procedure

```powershell
Set-Location C:\Topo-ai

$repo = "ShaikMuhammadSami/Topo_Ai"
$runAttempt = gh api "repos/$repo/actions/runs/$runId" --jq .run_attempt
$artifactName = "topo-lineage-receipt-$runId-$runAttempt"
$receiptDirectory = Join-Path `
  (Get-Location) `
  "evaluation\results\provider-receipts\$runId-$runAttempt"

New-Item -ItemType Directory -Path $receiptDirectory -Force | Out-Null

gh run download $runId `
  --repo $repo `
  --name $artifactName `
  --dir $receiptDirectory

$receiptPath = Join-Path `
  $receiptDirectory `
  "topo-lineage-provider-receipt.json"

Get-Content -Raw $receiptPath |
  Test-Json -SchemaFile `
    .\docs\architecture\evaluation\lineage-provider-receipt.schema.json

Get-Content -Raw $receiptPath | ConvertFrom-Json | Format-List
```

No credential output is required.

## 31. Expected H3-P1 inputs

H3-P1 will consume exactly:

- `schema_version`
- `provider`
- `repository`
- `repository_id`
- `commit_sha`
- `workflow_name`
- `workflow_ref`
- `workflow_sha`
- `run_id`
- `run_attempt`
- `run_number`
- `event_name`
- `image_registry`
- `image_repository`
- `image_tag` as a diagnostic locator only
- `image_digest` as immutable identity
- `immutable_image_ref`
- `built_at`
- `receipt_created_at`
- `source_ref`
- `provenance.digest_source`
- `provenance.commit_source`
- `provenance.run_source`

H3-P1 must independently query GitHub run metadata and GHCR digest state, then compare those facts to Topo. The receipt cannot define Topo truth.

## 32. Possible provider prerequisites

Repository or account package policy may still prevent the future `GITHUB_TOKEN` from publishing GHCR packages. If the run fails, record the provider error and inspect GitHub Actions/package access policy first. Do not weaken permissions or immediately introduce a PAT. The evaluation package may initially be private; later H3-P1 access must use existing authorized tooling without exposing credentials.

## 33. Generated artifacts

No Actions run, GHCR image/package, provider receipt artifact, build provenance, or registry artifact was generated because the workflow was not run. The committed representative JSON file is a synthetic safe schema fixture, not provider evidence.

## 34. Git status

Expected branch: `evaluation/h3-provider-fixture-v1`. The seven files listed in section 18 are untracked. Nothing is staged, committed, pushed, merged, or tagged.

## 35. git diff --check

Pass. A separate trailing-whitespace check also covers the untracked new files because ordinary `git diff --check` does not inspect untracked content.

## Known limitations

- H3 remains unproven until the user later creates a real run and receipt after merge.
- `built_at` is null because H3-P0 does not invent a provider timestamp not supplied by the structured build output.
- Action references follow the repository's major-version convention; H3-P0 is not an action-SHA-pinning migration.
- The base image tag is a build input, not the produced artifact identity; the pushed output digest remains authoritative.
- No automatic package cleanup exists by design.
