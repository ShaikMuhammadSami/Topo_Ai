# H3-P1 GitHub Actions to immutable image observation audit

## Scope and result

H3-P1 is an evaluation-only audit of the current product. It does not repair
the product graph, alter TC-1 through TC-5, or change the accepted provider
fixture.

- Final verdict: `MISSING`
- First internal divergence: `RUN_IMAGE_RELATIONSHIP_MISSING`
- Next repair boundary: Actions-run to immutable-artifact linking only
- Product changes: none

The provider proves that GitHub Actions run `32688747741`, attempt `1`,
produced image digest
`sha256:ebd9da90b6d9d4366f1349ba18106792b1fd8cbbedbc2dc88f04d6b6b4441025`.
After the current supported ingestion and enrichment mechanisms were exercised,
Topo represented both exact entities but did not represent a relationship
between them.

## Provider truth and independent verification

The accepted provider receipt is:

`evaluation/results/provider-receipts/32688747741-1/topo-lineage-provider-receipt.json`

It validates against `eval-lineage-provider-receipt-v1`. Its SHA-256 before
and after observation was:

`7903be83d443a81f382fe08bc8458bc8b1ac6fc3e8858c50b4d2cb07edd3cec3`

No unredacted secret-shaped values were found. The commit SHA, run ID,
attempt, run-derived mutable tag, immutable digest, and evaluation-specific
GHCR repository all passed their accepted syntax and semantic checks.

Read-only GitHub API verification independently confirmed:

- repository `ShaikMuhammadSami/Topo_Ai`, ID `1278498159`;
- workflow `Topo Lineage Provider Fixture`, ID `340927959`;
- workflow path `.github/workflows/topo-lineage-provider-fixture.yml`;
- run ID `32688747741`, attempt `1`, run number `2`;
- head SHA `ceaaf438f24d8b01c5e2c769fda1bf791ab7f8e4`;
- event `workflow_dispatch`;
- status `completed`, conclusion `success`;
- created and started at `2026-08-24T04:05:58Z`;
- updated at `2026-08-24T04:06:38Z`;
- the receipt artifact remained present and unexpired.

The available GitHub credential did not permit GitHub Packages metadata reads,
and anonymous registry manifest inspection was denied. Consequently:

`registry_read_verification = unavailable`

This does not invalidate provider truth. The accepted receipt records the
digest from the structured build/push action output, and the independently
verified provider run completed successfully.

## Current product implementation audit

The current product contract uses these entities and canonical identities:

| Fact | Current kind | Canonical identity |
|---|---|---|
| Repository | `GitRepository` | `github:api.github.com:repository:{repository_id}` |
| Commit | `GitCommit` | `{repository_id}:commit:{lowercase_sha}` |
| Actions run | `GitHubWorkflowRun` | `github:api.github.com:workflow-run:{run_id}` |
| Immutable image | `ContainerImage` | `artifact:container-image:{sha256_digest}` |

Run attempt is not part of the current canonical run ID. It is retained as the
`run_attempt` entity property. H3 therefore compares the canonical run ID,
provider-native run ID, repository scope relationship, and run-attempt property
together. A commit SHA alone is never accepted as exact run identity.

The intended H3 relationship is:

`GitHubWorkflowRun --produces--> ContainerImage`

This agrees with TC-2's producer-to-artifact direction and CR-1's explicit
`produces` artifact-lineage semantics. When the current linker creates that
edge, it is inferred by
`backend.app.services.github_actions_graph`, uses linker version
`github-actions-artifact-linker:v1`, labels numeric confidence as a heuristic,
and records workflow-run ID, image digest, and mapping-method source references.

The current Actions ingestion does not create image entities and does not read
the provider receipt, GHCR package metadata, build outputs, or OCI labels. It
finds existing image entities through Kubernetes `uses` relationships. It then
requires a Deployment or Pod to carry one of these metadata keys before it can
link a run:

- `topo.ai/workflow-run-id`
- `github.actions/run-id`
- `ci.workflow-run-id`

Without one of those workload metadata values, the linker deliberately skips
the workload. Current Commit-to-Image inference is a separate workload-metadata
linker and cannot substitute for H3.

## Ingestion path exercised

The observation used a fresh isolated Docker Desktop namespace:

`topo-eval-h3-32688747741`

The namespace carried the required label
`topo.ai/evaluation-run=32688747741`. A zero-replica Deployment referenced the
exact immutable image. No Pod was started, no image was pulled, no runtime
failure was created, and no workflow-run metadata was added to the workload.

Kubernetes materialization was required because this current path creates the
image entity from workload container specifications. It proves only the image
to workload declaration; it does not prove the provider run produced the image.

Read-only provider-native repository, commit, and run payloads obtained directly
from GitHub were replayed into the existing service-layer enrichers. Provider
IDs and timestamps were preserved. The provider receipt was used for expected
truth and for the explicitly permitted exact-digest Kubernetes materialization,
not as a Topo Actions ingestion payload or relationship shortcut.

The disposable namespace was verified by exact prefix and label before guarded
deletion. It was absent after the run.

## H3 result matrix

| Dimension | Expected provider truth | Current Topo | Match |
|---|---|---|---|
| Repository | `ShaikMuhammadSami/Topo_Ai`, ID `1278498159` | exact repository entity | yes |
| Commit | `ceaaf438...1ab7f8e4` | exact commit entity | yes |
| Workflow | `Topo Lineage Provider Fixture` | exact run workflow name and workflow ID | yes |
| Run ID | `32688747741` | exact canonical/native/property ID | yes |
| Run attempt | `1` | entity property `run_attempt=1` | yes |
| Image repository | `ghcr.io/shaikmuhammadsami/topo_ai-topo-lineage-eval` | registry `ghcr.io` plus repository `shaikmuhammadsami/topo_ai-topo-lineage-eval` | yes |
| Image tag | `run-32688747741-1` | `null` on digest-only observation | not represented; not authoritative |
| Image digest | `sha256:ebd9da...41025` | exact external ID, property, and canonical ID | yes |
| Immutable image ref | repository at exact digest | retained in requested references | yes |
| Entity identities | exact scoped run and digest artifact | both exact | yes |
| Relationship | run to image | absent | no |
| Predicate | `produces` | unavailable because edge is absent | no |
| Direction | run to artifact | unavailable because edge is absent | no |
| Origin | current intended `inferred` | unavailable because edge is absent | no |
| Source component | current linker component | unavailable because edge is absent | no |
| Source references | exact run ID and digest | unavailable because edge is absent | no |
| Completeness | TC-2 complete | unavailable because edge is absent | no |
| Time semantics | provider run and receipt times retained separately | run time exact; image collection time present; relationship time absent | incomplete after earlier edge failure |

The enrichment result reported one workflow run, one commit-to-run relationship,
zero mapped runs, zero mapped images, and zero run-to-image relationships.

## Identity, provenance, and time conclusions

The exact run entity is structurally defensible: canonical ID, native ID,
repository containment, attempt, workflow, and head SHA all match provider
truth. The exact immutable image entity is also structurally defensible: the
digest is its canonical ID and provider-native ID, and the entity is marked
immutable.

There is no H3 edge on which to evaluate actual predicate, direction,
provenance, source references, confidence semantics, or TC-3 relationship time.
The first divergence is therefore the missing relationship, not the later
provenance or temporal dimensions.

Provider run time, receipt creation time, Topo run observation time, Topo image
observation time, and hypothetical relationship time remain separate fields.
`built_at` remains `null`; no build timestamp was fabricated.

## LINEAGE-0 implication

The prior hop conclusions remain:

- H1 Repository to Commit: `PROVEN`
- H2 Commit to Actions: `PROVEN`
- H3 Actions to Immutable Image: `MISSING`
- H4 Image to Deployment: `PROVEN`
- H5 Deployment to ReplicaSet: `PROVEN`
- H6 ReplicaSet to Pod: `PROVEN`
- H7 Pod to Runtime Failure: `PROVEN`

H3 is no longer provider-prerequisite-blocked. It is now measured as an internal
representation gap. The full source-to-runtime lineage chain is not complete.

This is provenance lineage only. It does not establish that the commit or
workflow run caused a runtime failure.

## Proposed next repair boundary

The next repair, if separately authorized, should target only the missing
Actions-run to immutable-artifact linking boundary. It should ingest or retain
explicit provider build-output evidence that identifies both the exact run
attempt and exact immutable digest. Kubernetes workload metadata may remain a
useful corroborating source, but it is not provider proof that a run produced an
artifact.

No repair is implemented by H3-P1.

