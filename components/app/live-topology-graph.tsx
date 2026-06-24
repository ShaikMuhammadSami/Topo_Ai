"use client"

import { useMemo, useState } from "react"

import type {
  VisualEdge,
  VisualNode,
  VisualState,
  VisualTopology,
} from "@/lib/topology-visualizer"
import { cn } from "@/lib/utils"

const stateStyles: Record<
  VisualState,
  string
> = {
  normal:
    "border-muted-foreground/50 bg-card",
  added:
    "border-ok bg-ok/10",
  changed:
    "border-warn bg-warn/10",
  removed:
    "border-danger border-dashed bg-danger/10 opacity-75",
}

const edgeColors: Record<
  VisualState,
  string
> = {
  normal: "var(--color-muted-foreground)",
  added: "var(--color-ok)",
  changed: "var(--color-warn)",
  removed: "var(--color-danger)",
}

export function LiveTopologyGraph({
  topology,
  selectedNodeId,
  onSelectNode,
}: {
  topology: VisualTopology
  selectedNodeId: string | null
  onSelectNode: (node: VisualNode) => void
}) {
  const [hoveredNodeId, setHoveredNodeId] =
    useState<string | null>(null)

  const nodeById = useMemo(
    () =>
      new Map(
        topology.nodes.map((node) => [
          node.id,
          node,
        ]),
      ),
    [topology.nodes],
  )

  const connectedNodeIds = useMemo(() => {
    const connected = new Set<string>()

    if (!hoveredNodeId) {
      return connected
    }

    connected.add(hoveredNodeId)

    for (const edge of topology.edges) {
      if (edge.from === hoveredNodeId) {
        connected.add(edge.to)
      }

      if (edge.to === hoveredNodeId) {
        connected.add(edge.from)
      }
    }

    return connected
  }, [
    hoveredNodeId,
    topology.edges,
  ])

  function edgeIsDimmed(
    edge: VisualEdge,
  ) {
    if (!hoveredNodeId) {
      return false
    }

    return !(
      connectedNodeIds.has(edge.from) &&
      connectedNodeIds.has(edge.to)
    )
  }

  return (
    <div className="overflow-auto rounded-md border border-border bg-background">
      <div
        className="relative"
        style={{
          width: topology.width,
          height: topology.height,
          backgroundImage:
            "linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      >
        {topology.layers.map((layer) => (
          <div
            key={layer.index}
            className="absolute top-5 -translate-x-1/2 font-mono text-[10px] uppercase tracking-widest text-muted-foreground"
            style={{
              left: layer.x,
            }}
          >
            {layer.label}
          </div>
        ))}

        <svg
          className="absolute inset-0"
          width={topology.width}
          height={topology.height}
          aria-hidden
        >
          <defs>
            <ArrowMarker
              id="normal"
              color="var(--color-muted-foreground)"
            />

            <ArrowMarker
              id="added"
              color="var(--color-ok)"
            />

            <ArrowMarker
              id="changed"
              color="var(--color-warn)"
            />

            <ArrowMarker
              id="removed"
              color="var(--color-danger)"
            />
          </defs>

          {topology.edges.map((edge) => {
            const source =
              nodeById.get(edge.from)

            const target =
              nodeById.get(edge.to)

            if (!source || !target) {
              return null
            }

            const dimmed =
              edgeIsDimmed(edge)

            return (
              <line
                key={edge.id}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke={
                  edgeColors[edge.state]
                }
                strokeWidth={
                  edge.state === "normal"
                    ? 1
                    : 2
                }
                strokeDasharray={
                  edge.state === "removed"
                    ? "5 4"
                    : undefined
                }
                markerEnd={`url(#arrow-${edge.state})`}
                opacity={
                  dimmed
                    ? 0.08
                    : edge.state === "normal"
                      ? 0.35
                      : 0.9
                }
              >
                <title>{edge.label}</title>
              </line>
            )
          })}
        </svg>

        {topology.nodes.map((node) => {
          const dimmed =
            hoveredNodeId !== null &&
            !connectedNodeIds.has(node.id)

          const selected =
            selectedNodeId === node.id

          return (
            <button
              key={node.id}
              type="button"
              title={`${node.kind}: ${node.label}`}
              onClick={() =>
                onSelectNode(node)
              }
              onMouseEnter={() =>
                setHoveredNodeId(node.id)
              }
              onMouseLeave={() =>
                setHoveredNodeId(null)
              }
              className={cn(
                "absolute w-40 -translate-x-1/2 -translate-y-1/2 rounded-sm border px-3 py-2 text-left transition-all",
                stateStyles[node.state],
                selected &&
                  "ring-2 ring-info ring-offset-2 ring-offset-background",
                dimmed && "opacity-20",
              )}
              style={{
                left: node.x,
                top: node.y,
              }}
            >
              <span className="block truncate font-mono text-[11px] font-semibold text-foreground">
                {node.label}
              </span>

              <span className="mt-1 block truncate font-mono text-[9px] text-muted-foreground">
                {node.kind}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ArrowMarker({
  id,
  color,
}: {
  id: string
  color: string
}) {
  return (
    <marker
      id={`arrow-${id}`}
      viewBox="0 0 10 10"
      refX="8"
      refY="5"
      markerWidth="5"
      markerHeight="5"
      orient="auto-start-reverse"
    >
      <path
        d="M 0 0 L 10 5 L 0 10 z"
        fill={color}
      />
    </marker>
  )
}