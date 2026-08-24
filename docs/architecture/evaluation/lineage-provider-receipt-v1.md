# eval-lineage-provider-receipt-v1

## Purpose

`eval-lineage-provider-receipt-v1` is an evaluation-only provider receipt proving that one exact GitHub Actions workflow run pushed one exact immutable container digest. It supplies independent H3 provider truth for a later H3-P1 evaluation. It is not a Topo product model and does not prove that a commit caused a runtime failure.

## Evidence boundary

The receipt is generated only after `docker/build-push-action` successfully pushes the evaluation image. Repository, commit, workflow, and run fields come from the GitHub Actions context. `image_digest` comes directly from the build action's structured `digest` output. Time proximity, mutable tags, registry latest-state lookup, and Topo graph output are not used to construct the expected H3 relationship.

## Exact fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Constant `eval-lineage-provider-receipt-v1`. |
| `provider` | string | Constant `github`. |
| `repository` | string | GitHub `owner/name`. |
| `repository_id` | string or null | Provider-native repository ID when the Actions context supplies it. |
| `commit_sha` | string | Exact lowercase 40-character workflow commit SHA. |
| `workflow_name` | string | GitHub workflow display name. |
| `workflow_ref` | string | Provider workflow reference, including repository/path/ref. |
| `workflow_sha` | string or null | Commit SHA containing the workflow definition when available. |
| `run_id` | integer | Provider-native GitHub Actions run ID. |
| `run_attempt` | integer | Run attempt, preserving rerun identity. |
| `run_number` | integer | Workflow run number. |
| `event_name` | string | Expected to be `workflow_dispatch` for this fixture. |
| `image_registry` | string | Constant `ghcr.io`. |
| `image_repository` | string | Lowercase evaluation-only GHCR repository path. |
| `image_tag` | string | Diagnostic `run-<run-id>-<attempt>` tag. |
| `image_digest` | string | Authoritative `sha256:<64 hex>` digest returned by the push action. |
| `immutable_image_ref` | string | `image_repository@image_digest`. |
| `built_at` | date-time or null | Null because build output does not provide an authoritative build timestamp in H3-P0. |
| `receipt_created_at` | date-time | UTC receipt creation time after push success. |
| `source_ref` | string | Git ref dispatched by the user. |
| `provenance.digest_source` | string | Constant `build_push_action_output`. |
| `provenance.commit_source` | string | Constant `github_context`. |
| `provenance.run_source` | string | Constant `github_context`. |

The machine-readable contract is `lineage-provider-receipt.schema.json`.

## Digest semantics

`image_tag` is a mutable diagnostic locator and is never authoritative identity. `image_digest` is the immutable artifact identity. H3-P1 must compare the exact digest and construct the immutable reference from the recorded image repository and digest; it must not re-resolve the tag and treat that lookup as original provider truth.

## Provider independence

The receipt is produced by GitHub Actions from GitHub context and Docker build output before Topo evaluates the hop. Topo cannot define or rewrite expected repository, commit, run, or digest values.

## Security and redaction

The receipt contains an allowlisted field set. It excludes tokens, authorization headers, registry passwords, environment dumps, event payloads, actor email, and private configuration. The workflow passes `secrets.GITHUB_TOKEN` only to `docker/login-action`; it never passes it to receipt generation or the job summary. Unknown fields are rejected by the JSON Schema.

## Retention assumptions

The JSON artifact is retained for 30 days. The evaluation GHCR image is intentionally not auto-deleted because H3-P1 and later H4–H7 verification need its digest. Package cleanup, if desired after proof, is a separate explicit human operation.

## H3-P1 consumption

H3-P1 will consume `repository`, `repository_id`, `commit_sha`, `workflow_name`, `workflow_ref`, `workflow_sha`, `run_id`, `run_attempt`, `run_number`, `event_name`, `image_registry`, `image_repository`, `image_tag`, `image_digest`, `immutable_image_ref`, receipt times, `source_ref`, and the three provenance-source fields. It must cross-check provider run metadata and registry state independently before evaluating Topo's H3 representation.
