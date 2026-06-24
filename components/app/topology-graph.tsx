"use client"

import { useState } from "react"
import { graphNodes, graphEdges, type NodeState } from "@/lib/topo-data"
import { cn } from "@/lib/utils"

const stateColor: Record<NodeState, string> = {
  healthy: "var(--color-muted-foreground)",
  elevated: "var(--color-warn)",
  failing: "var(--color-danger)",
}

export function TopologyGraph({ className }: { className?: string }) {
  const [hover, setHover] = useState<string | null>(null)

  const connected = new Set<string>()
  if (hover) {
    connected.add(hover)
    graphEdges.forEach((e) => {
      if (e.from === hover) connected.add(e.to)
      if (e.to === hover) connected.add(e.from)
    })
  }

  const nodeById = (id: string) => graphNodes.find((n) => n.id === id)!

  return (
    <div
      className={cn(
        "relative aspect-[16/11] w-full overflow-hidden rounded-sm border border-border bg-background",
        className,
      )}
      style={{
        backgroundImage:
          "linear-gradient(var(--color-border) 1px, transparent 1px), linear-gradient(90deg, var(--color-border) 1px, transparent 1px)",
        backgroundSize: "40px 40px",
      }}
    >
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        {graphEdges.map((e, i) => {
          const a = nodeById(e.from)
          const b = nodeById(e.to)
          const dim = hover && !(connected.has(e.from) && connected.has(e.to))
          const color =
            e.state === "failing"
              ? "var(--color-danger)"
              : e.state === "low"
                ? "var(--color-border)"
                : "var(--color-muted-foreground)"
          return (
            <line
              key={i}
              x1={`${a.x}%`}
              y1={`${a.y}%`}
              x2={`${b.x}%`}
              y2={`${b.y}%`}
              stroke={color}
              strokeWidth={e.state === "failing" ? 1.5 : 1}
              strokeDasharray={e.state === "low" ? "4 4" : undefined}
              opacity={dim ? 0.12 : e.state === "failing" ? 0.9 : 0.4}
            />
          )
        })}
      </svg>

      {graphNodes.map((n) => {
        const dim = hover && !connected.has(n.id)
        return (
          <button
            key={n.id}
            onMouseEnter={() => setHover(n.id)}
            onMouseLeave={() => setHover(null)}
            className="absolute -translate-x-1/2 -translate-y-1/2 transition-opacity"
            style={{ left: `${n.x}%`, top: `${n.y}%`, opacity: dim ? 0.3 : 1 }}
          >
            <span
              className="flex flex-col items-center"
              style={{ color: stateColor[n.state] }}
            >
              <span
                className="rounded-sm border bg-card px-2.5 py-1 font-mono text-[11px] font-medium text-foreground"
                style={{ borderColor: stateColor[n.state] }}
              >
                {n.label}
              </span>
              <span className="mt-1 font-mono text-[9px] text-muted-foreground">
                {n.kind}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
