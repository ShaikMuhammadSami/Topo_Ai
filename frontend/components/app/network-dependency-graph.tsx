"use client"

import {
  useMemo,
} from "react"
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MiniMap,
  Node,
  Position,
} from "reactflow"
import "reactflow/dist/style.css"

import type {
  NetworkDependencyAnalysisResponse,
} from "@/lib/topo-types"


export function NetworkDependencyGraph({
  data,
}: {
  data:
    NetworkDependencyAnalysisResponse
}) {
  const entityMap = useMemo(
    () =>
      new Map(
        data.entities.map(
          (entity) => [
            entity.entity_id,
            entity,
          ],
        ),
      ),
    [data],
  )


  const nodes: Node[] = useMemo(
    () =>
      data.entities.map(
        (entity, index) => {
          const lane = laneForKind(
            entity.entity_kind,
          )

          return {
            id: entity.entity_id,
            data: {
              label:
                entity.entity_name,
            },
            position: {
              x: lane * 260,
              y: (
                indexByLane(
                  data.entities,
                  entity.entity_kind,
                  index,
                ) * 120
              ),
            },
            sourcePosition:
              Position.Right,
            targetPosition:
              Position.Left,
            style: {
              border:
                "2px solid",
              borderColor:
                colorForKind(
                  entity.entity_kind,
                ),
              borderRadius: 8,
              padding: 10,
              minWidth: 160,
              background:
                "#ffffff",
              color: "#111827",
              textAlign:
                "center" as const,
            },
          }
        },
      ),
    [data],
  )


  const edges: Edge[] = useMemo(
    () =>
      data.relationships
        .filter(
          (relationship) =>
            relationship.resolved,
        )
        .map(
          (relationship) => ({
            id:
              relationship
                .relationship_id,
            source:
              relationship
                .source_entity_id,
            target:
              relationship
                .target_entity_id,
            type: "smoothstep",
            animated:
              relationship
                .relationship_type ===
                "calls",
            label:
              relationship
                .relationship_type,
            style: {
              stroke: "#64748b",
              strokeWidth: 2,
            },
          }),
        ),
    [data],
  )


  return (
    <div className="h-[600px] w-full overflow-hidden rounded-md border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesConnectable={false}
      >
        <Background />
        <Controls />

        <MiniMap
          nodeColor={(node) => {
            const entity =
              entityMap.get(node.id)

            return entity
              ? colorForKind(
                  entity.entity_kind,
                )
              : "#94a3b8"
          }}
        />
      </ReactFlow>
    </div>
  )
}


function laneForKind(
  kind: string,
): number {
  if (
    kind === "KubernetesIngress"
  ) {
    return 0
  }

  if (
    kind === "KubernetesService"
  ) {
    return 1
  }

  if (
    kind ===
    "KubernetesEndpointSlice"
  ) {
    return 2
  }

  if (
    kind === "KubernetesPod"
  ) {
    return 3
  }

  return 4
}


function indexByLane(
  entities:
    NetworkDependencyAnalysisResponse[
      "entities"
    ],
  kind: string,
  currentIndex: number,
): number {
  const currentLane =
    laneForKind(kind)

  return entities
    .slice(0, currentIndex)
    .filter(
      (entity) =>
        laneForKind(
          entity.entity_kind,
        ) === currentLane,
    ).length
}


function colorForKind(
  kind: string,
): string {
  switch (kind) {
    case "KubernetesIngress":
      return "#8b5cf6"

    case "KubernetesService":
      return "#2563eb"

    case "KubernetesEndpointSlice":
      return "#0891b2"

    case "KubernetesPod":
      return "#16a34a"

    case "ExternalEndpoint":
    case "DNSName":
      return "#dc2626"

    default:
      return "#64748b"
  }
}