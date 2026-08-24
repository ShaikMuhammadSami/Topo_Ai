# Actions-to-image lineage v1

- Status: implemented and measured
- Version: `actions-image-lineage-v1`
- Scope: GitHub Actions provider evidence to an existing immutable container-image entity

## Measured defect

H3-P1 found the exact `GitHubWorkflowRun` and exact digest-addressed
`ContainerImage`, but no relationship connected them. The first divergence was
`RUN_IMAGE_RELATIONSHIP_MISSING`. H3-R1 repairs only that relationship.

## Provider evidence

The accepted source is the provider-managed Docker build record emitted by
`docker/build-push-action`. Topo obtains the record from the GitHub Actions
artifacts API and parses its OCI BuildKit history record. A complete fact
requires all of the following to agree:

- GitHub artifact scope: repository ID, run ID, and head SHA;
- GitHub workflow run: repository, run ID, run attempt, commit SHA, successful
  conclusion, and provider update time;
- BuildKit SLSA predicate: GitHub repository ID/name, run ID, run attempt,
  commit context, and exact provider builder ID;
- BuildKit image exporter: an explicitly pushed image repository;
- BuildKit result descriptor: one or more immutable `sha256` image digests;
- artifact and OCI descriptor content hashes.

This is a general provider surface. Topo does not read the evaluation receipt,
workflow-specific output, custom `topo.*` labels, or evaluation identifiers.
The receipt remains independent expected truth.

Rejected bases include mutable tags, commit equality by itself, names, temporal
proximity, Kubernetes annotations without provider build evidence, log prose,
fuzzy matching, and LLM output.

## Normalized evidence

`BuildArtifactEvidence` is a narrow internal source fact. It records only
allowlisted identifiers and times needed to defend linkage:

- provider, repository ID/name, workflow ID/ref, run ID/attempt, and commit SHA;
- artifact type, pushed image repository, immutable digest/reference;
- evidence type, GitHub artifact ID/URL/digest, BuildKit record digest, and
  provider builder ID;
- provider build times when present, provider run update time, Topo observation
  time, TC-3 metadata, and completeness.

Raw build records and provider credentials are not persisted. Secret-bearing
or unrelated BuildKit fields are ignored.

## Entity resolution and relationship

The linker never creates either endpoint. It resolves and reuses:

```text
GitHubWorkflowRun
  github:api-host:workflow-run:<run-id>
        --produces-->
ContainerImage
  artifact:container-image:sha256:<digest>
```

Resolution requires one unambiguous entity at each canonical ID. The run must
be a `GitHubWorkflowRun`, be contained by the exact repository entity, and have
the exact external run ID, run property, run attempt, and head SHA. The image
must be an immutable `ContainerImage` whose external ID and digest property
both equal the evidence digest and whose repository matches the pushed image
repository.

An attempt mismatch abstains. The accepted TC-1 run identity still does not
include attempt, so rerun identity remains a documented adversarial limitation;
H3-R1 does not redesign it.

The canonical direction and predicate are strictly:

```text
GitHubWorkflowRun --produces--> ContainerImage
```

The relationship ID is a deterministic hash of source canonical ID,
`produces`, and target canonical ID. Replay therefore replaces the same
semantic edge rather than duplicating it.

## TC-2 provenance

Origin is `observed`: the provider-managed record directly asserts both the
exact executing run/attempt and exact build result digest. This is not a score
or a Topo inference. No confidence value or probability is attached.

Completeness is `complete` only after all provider and entity checks pass.
Source references retain repository/run/attempt/workflow, artifact ID/URL and
digest, provider builder ID, BuildKit record digest, commit SHA, immutable image
reference, and immutable image digest. The stable source component is
`backend.app.services.github_actions_artifact_lineage`; linker version is
`github-actions-build-artifact-lineage:v1`.

## TC-3 time

The provider run `updated_at` is the relationship's exact authoritative source
event time. Topo observation and recording times remain separate. SLSA build
start/finish times are retained independently when present. Missing build time
stays missing; Topo does not fabricate `built_at` or reinterpret receipt time as
build time.

## Ordering, persistence, and reconciliation

Normalized evidence is saved idempotently in the existing SQLAlchemy store.
The provider enrichment orchestration always re-reads bounded durable evidence
for the exact repository and runs being processed, then reconciles it against
the supplied graph:

```text
provider record first -> durable evidence -> image appears -> next enrichment links
image first           -> provider record arrives          -> enrichment links
```

No background worker is required. Missing endpoints remain unresolved evidence
and never cause fabricated entities. Existing immutable snapshots, incident
pins, and causal-analysis records are not rewritten by late evidence; later
enriched snapshots may contain the relationship.

## Conflicts and cardinality

Malformed digests, content-hash failures, wrong repository/run/attempt/commit,
ambiguous endpoints, unsuccessful runs, expired artifacts, and provider
failures produce structured abstention warnings and no edge. One run may have
multiple explicitly evidenced image outputs. Independently proven runs may
produce the same digest. Digest uniqueness is never used to infer a run.

## Limitations

- v1 consumes GitHub provider-managed Docker/BuildKit records only.
- The relevant graph must undergo provider enrichment after both endpoints are
  visible; there is deliberately no worker or retrospective incident rewrite.
- Current run canonical identity excludes run attempt; exact attempt matching
  prevents cross-attempt linkage but does not solve rerun representation.
- This relationship proves build provenance, not that the source commit caused
  a later runtime failure.
- The single preserved provider-backed H1-H7 scenario is structurally useful
  but not statistically meaningful.
