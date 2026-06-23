import type {
  GraphSnapshot,
  SnapshotDiffResult,
  TopologyEntity,
} from "@/lib/topo-types"

export type VisualState =
  | "normal"
  | "added"
  | "changed"
  | "removed"

export type VisualNode = {
  id: string
  label: string
  kind: string
  layer: string
  layerIndex: number
  x: number
  y: number
  state: VisualState
  entity: TopologyEntity
}

export type VisualEdge = {
  id: string
  from: string
  to: string
  label: string
  state: VisualState
}

export type VisualLayer = {
  index: number
  label: string
  x: number
}

export type VisualTopology = {
  nodes: VisualNode[]
  edges: VisualEdge[]
  layers: VisualLayer[]
  width: number
  height: number
}

const layerDefinition: Record<
  string,
  {
    index: number
    label: string
  }
> = {
  KubernetesCluster: {
    index: 0,
    label: "Cluster",
  },
  KubernetesNamespace: {
    index: 1,
    label: "Namespace",
  },
  KubernetesDeployment: {
    index: 2,
    label: "Deployment",
  },
  KubernetesReplicaSet: {
    index: 3,
    label: "ReplicaSet",
  },
  KubernetesPod: {
    index: 4,
    label: "Pod",
  },
  KubernetesService: {
    index: 5,
    label: "Service",
  },
}

function getLayer(kind: string) {
  return (
    layerDefinition[kind] ?? {
      index: 6,
      label: "Other",
    }
  )
}

export function buildVisualTopology(
  snapshot: GraphSnapshot,
  diff: SnapshotDiffResult | null,
): VisualTopology {
  const entityStates = new Map<
    string,
    VisualState
  >()

  for (
    const entity
    of diff?.added_entities ?? []
  ) {
    entityStates.set(entity.id, "added")
  }

  for (
    const entity
    of diff?.removed_entities ?? []
  ) {
    entityStates.set(entity.id, "removed")
  }

  for (
    const entity
    of diff?.changed_entities ?? []
  ) {
    entityStates.set(
      entity.entity_id,
      "changed",
    )
  }

  /*
   * Add removed entities first, and then current
   * entities. Current entities win if IDs overlap.
   */
  const entityMap = new Map<
    string,
    TopologyEntity
  >()

  for (
    const entity
    of diff?.removed_entities ?? []
  ) {
    entityMap.set(entity.id, entity)
  }

  for (const entity of snapshot.entities) {
    entityMap.set(entity.id, entity)
  }

  const groupedEntities = new Map<
    number,
    TopologyEntity[]
  >()

  for (
    const entity
    of entityMap.values()
  ) {
    const layer = getLayer(entity.kind)

    const group =
      groupedEntities.get(layer.index) ?? []

    group.push(entity)
    groupedEntities.set(
      layer.index,
      group,
    )
  }

  for (
    const group
    of groupedEntities.values()
  ) {
    group.sort((first, second) =>
      first.name.localeCompare(second.name),
    )
  }

  const columnWidth = 210
  const rowHeight = 82
  const leftPadding = 120
  const topPadding = 100

  const highestLayer = Math.max(
    ...Array.from(
      groupedEntities.keys(),
    ),
    0,
  )

  const largestGroup = Math.max(
    ...Array.from(
      groupedEntities.values(),
    ).map((group) => group.length),
    1,
  )

  const width = Math.max(
    1100,
    leftPadding * 2 +
      (highestLayer + 1) * columnWidth,
  )

  const height = Math.max(
    620,
    topPadding + largestGroup * rowHeight + 80,
  )

  const nodes: VisualNode[] = []

  for (
    const [layerIndex, entities]
    of groupedEntities.entries()
  ) {
    const layerLabel =
      getLayer(
        entities[0]?.kind ?? "",
      ).label

    entities.forEach(
      (entity, entityIndex) => {
        nodes.push({
          id: entity.id,
          label: entity.name,
          kind: entity.kind,
          layer: layerLabel,
          layerIndex,
          x:
            leftPadding +
            layerIndex * columnWidth,
          y:
            topPadding +
            entityIndex * rowHeight,
          state:
            entityStates.get(entity.id) ??
            "normal",
          entity,
        })
      },
    )
  }

  const relationshipStates = new Map<
    string,
    VisualState
  >()

  for (
    const relationship
    of diff?.added_relationships ?? []
  ) {
    relationshipStates.set(
      relationship.id,
      "added",
    )
  }

  for (
    const relationship
    of diff?.removed_relationships ?? []
  ) {
    relationshipStates.set(
      relationship.id,
      "removed",
    )
  }

  for (
    const relationship
    of diff?.changed_relationships ?? []
  ) {
    relationshipStates.set(
      relationship.relationship_id,
      "changed",
    )
  }

  const relationshipMap = new Map(
    (
      diff?.removed_relationships ?? []
    ).map((relationship) => [
      relationship.id,
      relationship,
    ]),
  )

  for (
    const relationship
    of snapshot.relationships
  ) {
    relationshipMap.set(
      relationship.id,
      relationship,
    )
  }

  const knownNodeIds = new Set(
    nodes.map((node) => node.id),
  )

  const edges: VisualEdge[] = Array
    .from(relationshipMap.values())
    .filter(
      (relationship) =>
        knownNodeIds.has(
          relationship.source_entity_id,
        ) &&
        knownNodeIds.has(
          relationship.target_entity_id,
        ),
    )
    .map((relationship) => ({
      id: relationship.id,
      from:
        relationship.source_entity_id,
      to:
        relationship.target_entity_id,
      label:
        relationship.relationship_type,
      state:
        relationshipStates.get(
          relationship.id,
        ) ?? "normal",
    }))

  const layers: VisualLayer[] = Array
    .from(groupedEntities.entries())
    .map(([index, entities]) => ({
      index,
      label:
        getLayer(
          entities[0]?.kind ?? "",
        ).label,
      x:
        leftPadding +
        index * columnWidth,
    }))
    .sort(
      (first, second) =>
        first.index - second.index,
    )

  return {
    nodes,
    edges,
    layers,
    width,
    height,
  }
}