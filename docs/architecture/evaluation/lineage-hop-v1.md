# eval-lineage-hop-v1

`eval-lineage-hop-v1` is the evaluation-only contract for comparing one source-to-runtime lineage hop against provider-native truth. It does not modify or replace TC-1 through TC-5 and is not a product persistence model.

## Evidence boundary

Expected identities and relationships come from provider receipts collected independently of Topo. Topo entities and relationships are observations to be tested; they never define the expected provider lineage. Equality is structural and exact when provider-native IDs, Kubernetes UIDs, commit SHAs, workflow run IDs, or image digests exist. Display-name similarity and time proximity are not identity evidence.

## Hop fields

Each hop records:

- `hop_version`, `hop_id`, and source/target logical aliases;
- independently derived expected source and target provider identities;
- the expected relationship semantic;
- provider truth, including direction, evidence references, and provider times;
- the Topo entity IDs, relationship, predicate, stored direction, TC-2 provenance, source references, linker version, completeness, and Topo time;
- explicit evaluation dimensions and one status.

Provider and Topo timestamps remain separate. Adjacent provider timestamps receive a bounded five-minute skew tolerance because creation and publication sources can have slightly different clock/semantic boundaries. Larger inversions remain incomplete evidence.

## Accepted semantic map

| Hop | Provider semantic | Accepted Topo storage |
|---|---|---|
| H1 | Repository contains Commit | `GitRepository -> contains -> GitCommit` |
| H2 | Commit is exact workflow head | `GitCommit -> triggers -> GitHubWorkflowRun` |
| H3 | Workflow run produces immutable image | `GitHubWorkflowRun -> produces -> ContainerImage` |
| H4 | Deployment consumes immutable image | `KubernetesDeployment -> uses -> ContainerImage` |
| H5 | Deployment owns ReplicaSet | `KubernetesDeployment -> owns -> KubernetesReplicaSet` |
| H6 | ReplicaSet owns Pod | direct collector `runs`; agent inventory `owns` |
| H7 | Structured failure involves Pod | `NormalizedSignal.involved_entity_id` and exact object UID |

H4 intentionally evaluates the accepted stored direction rather than inventing an image-to-workload product predicate. H6 preserves the documented difference between the direct collector and agent inventory.

## Status taxonomy

- `PROVEN`: independent truth and Topo agree on strong identity, semantic direction, provenance, required source references, time, and immutable identity where required.
- `PARTIAL`: useful lineage exists, but a required dimension is weaker or incomplete.
- `MISSING`: provider truth proves the hop and Topo has no corresponding representation.
- `WRONG`: Topo identity, direction, predicate, or other provider-native fact conflicts with provider truth.
- `INCONCLUSIVE`: independent truth or Topo structure cannot support a safe verdict.
- `PROVIDER_PREREQUISITE_BLOCKED`: the environment lacks evidence needed to run that proof safely.

The first broken hop is the earliest non-`PROVEN` hop. A blocked H3 is reported both as `first_broken_hop = PROVIDER_PREREQUISITE_BLOCKED` and `first_broken_hop_id = H3` so the exact repair boundary remains visible.

## Immutable artifact rule

The container artifact identity is `sha256:<digest>`. A mutable tag is not an immutable artifact and cannot make H3 or H4 `PROVEN`. Full lineage is true only when H1 through H7 are all `PROVEN`; source-change causal attribution is a separate field and is never inferred from lineage completeness.

## Historical rule

When an incident is present, `snapshot_id` must equal the incident's `pinned_snapshot_id`. Evaluation rejects current/latest fallback. Runs without an incident state that the incident-pinned check was not applicable.

## Safety

Provider bundles are sanitized recursively. Secret-shaped fields and signed URL query values are redacted before serialization. Generated run bundles belong under ignored `evaluation/results/lineage/`.
