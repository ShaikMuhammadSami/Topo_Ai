# H3-R1 Actions-to-image post-repair baseline

- Observed: 2026-08-24
- Branch: `architecture/actions-image-lineage-v1`
- Provider side effects: none
- Evaluation artifact: `evaluation/results/lineage/h3/h3-32688747741-1.json`

## Before

| Fact | H3-P1 result |
|---|---|
| Workflow run entity | exact |
| Container image entity | exact immutable digest |
| Run-to-image edge | absent |
| First divergence | `RUN_IMAGE_RELATIONSHIP_MISSING` |
| H3 | `MISSING` |

## Product evidence path after repair

The unchanged provider run was not rerun. The product path used authenticated,
read-only GitHub connector requests to load the repository, commit, workflow
run, run artifacts, and provider-managed Docker build record. Topo verified the
artifact and OCI descriptor hashes, normalized the structured BuildKit/SLSA
fact, persisted it, resolved the existing Kubernetes-observed immutable image,
and reconciled the edge. The custom evaluation receipt was not product input.

One disposable namespace named `topo-eval-h3-32688747741` materialized the
already published immutable image in a zero-replica Deployment. It added no
workflow metadata and created no runtime failure. Prefix and label guards were
checked before deletion; cleanup completed.

## After

| Fact | Measured result |
|---|---|
| Run entity | `github:api.github.com:workflow-run:32688747741` |
| Run attempt | `1` |
| Image entity | `artifact:container-image:sha256:ebd9da90b6d9d4366f1349ba18106792b1fd8cbbedbc2dc88f04d6b6b4441025` |
| Relationship ID | `rel:380016f0c64cfb1ba86d` |
| Predicate | `produces` |
| Direction | workflow run -> container image |
| Origin | `observed` |
| Source component | `backend.app.services.github_actions_artifact_lineage` |
| Linker | `github-actions-build-artifact-lineage:v1` |
| Completeness | `complete` |
| Confidence | absent; no probability invented |
| Temporal source | `github_workflow_run.updated_at` = `2026-08-24T04:06:38Z` |
| H3 first divergence | `NO_DIVERGENCE` |
| H3 | `PROVEN` |

The observed source references include repository ID `1278498159`, run ID
`32688747741`, attempt `1`, workflow ID/ref, artifact ID `9506541504`, GitHub
artifact digest, provider builder ID, BuildKit history digest, commit SHA,
immutable image reference, and exact image digest.

Product lineage statistics were: one provider artifact inspected, one build
record accepted, one evidence record persisted, one run and one image mapped,
one relationship created, zero unresolved evidence, and zero warnings.

## H1-H7 implication

For this one preserved provider-backed scenario, H1 Repository -> Commit,
H2 Commit -> Actions, H3 Actions -> Image, H4 Image -> Deployment,
H5 Deployment -> ReplicaSet, H6 ReplicaSet -> Pod, and H7 Pod -> Runtime Failure
are structurally proven by the existing lineage evaluation program.

This is **not statistically meaningful**. It establishes one end-to-end
structural provenance example. It does **not** prove that the source commit
caused a runtime failure; causal attribution remains untested by H3-R1.
