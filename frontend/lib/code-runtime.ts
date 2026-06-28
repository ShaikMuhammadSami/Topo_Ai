import type {
  GraphSnapshot,
  TopologyEntity,
  TopologyRelationship,
} from "@/lib/topo-types"

export type CodeRuntimeChain = {
  id: string

  repository: TopologyEntity | null
  commit: TopologyEntity
  workflowRun: TopologyEntity
  image: TopologyEntity

  workloads: TopologyEntity[]

  commitToRun: TopologyRelationship
  runToImage: TopologyRelationship
  workloadToImage: TopologyRelationship[]

  confidence: number
  mappingMethod: string
}

export function buildCodeRuntimeChains(
  snapshot: GraphSnapshot,
): CodeRuntimeChain[] {
  const entitiesById = new Map(
    snapshot.entities.map((entity) => [
      entity.id,
      entity,
    ]),
  )

  const repositoryByContainedEntity =
    new Map<string, TopologyEntity>()

  const triggerByRun =
    new Map<string, TopologyRelationship[]>()

  const usesByImage =
    new Map<string, TopologyRelationship[]>()

  for (const relationship of snapshot.relationships) {
    const source = entitiesById.get(
      relationship.source_entity_id,
    )

    const target = entitiesById.get(
      relationship.target_entity_id,
    )

    if (!source || !target) {
      continue
    }

    if (
      relationship.relationship_type === "contains" &&
      source.kind === "GitRepository"
    ) {
      repositoryByContainedEntity.set(
        target.id,
        source,
      )
    }

    if (
      relationship.relationship_type === "triggers" &&
      source.kind === "GitCommit" &&
      target.kind === "GitHubWorkflowRun"
    ) {
      const current =
        triggerByRun.get(target.id) ?? []

      current.push(relationship)

      triggerByRun.set(
        target.id,
        current,
      )
    }

    if (
      relationship.relationship_type === "uses" &&
      target.kind === "ContainerImage"
    ) {
      const current =
        usesByImage.get(target.id) ?? []

      current.push(relationship)

      usesByImage.set(
        target.id,
        current,
      )
    }
  }

  const chains: CodeRuntimeChain[] = []

  for (const relationship of snapshot.relationships) {
    if (
      relationship.relationship_type !== "produces" ||
      relationship.source_system !== "github-actions"
    ) {
      continue
    }

    const workflowRun = entitiesById.get(
      relationship.source_entity_id,
    )

    const image = entitiesById.get(
      relationship.target_entity_id,
    )

    if (
      !workflowRun ||
      !image ||
      workflowRun.kind !== "GitHubWorkflowRun" ||
      image.kind !== "ContainerImage"
    ) {
      continue
    }

    const triggerRelationships =
      triggerByRun.get(workflowRun.id) ?? []

    for (const commitToRun of triggerRelationships) {
      const commit = entitiesById.get(
        commitToRun.source_entity_id,
      )

      if (!commit || commit.kind !== "GitCommit") {
        continue
      }

      const workloadRelationships =
        usesByImage.get(image.id) ?? []

      const workloads = workloadRelationships
        .map((item) =>
          entitiesById.get(item.source_entity_id),
        )
        .filter(
          (
            entity,
          ): entity is TopologyEntity =>
            Boolean(entity) &&
            (
              entity?.kind ===
                "KubernetesDeployment" ||
              entity?.kind ===
                "KubernetesPod"
            ),
        )

      const uniqueWorkloads = Array.from(
        new Map(
          workloads.map((workload) => [
            workload.id,
            workload,
          ]),
        ).values(),
      )

      const confidenceValues = [
        commitToRun.confidence,
        relationship.confidence,
        ...workloadRelationships.map(
          (item) => item.confidence,
        ),
      ]

      const confidence = Math.min(
        ...confidenceValues,
      )

      chains.push({
        id: `${commit.id}:${workflowRun.id}:${image.id}`,

        repository:
          repositoryByContainedEntity.get(
            commit.id,
          ) ?? null,

        commit,
        workflowRun,
        image,

        workloads: uniqueWorkloads,

        commitToRun,
        runToImage: relationship,
        workloadToImage:
          workloadRelationships,

        confidence,

        mappingMethod: stringProperty(
          relationship.properties,
          "mapping_method",
        ),
      })
    }
  }

  return chains.sort((first, second) => {
    const firstDate = Date.parse(
      stringProperty(
        first.workflowRun.properties,
        "updated_at",
      ),
    )

    const secondDate = Date.parse(
      stringProperty(
        second.workflowRun.properties,
        "updated_at",
      ),
    )

    return secondDate - firstDate
  })
}

export function stringProperty(
  properties: Record<string, unknown>,
  key: string,
): string {
  const value = properties[key]

  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return ""
  }

  return String(value)
}