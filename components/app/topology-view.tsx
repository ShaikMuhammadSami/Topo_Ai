"use client"

import { useState } from "react"
import { timeScrubber } from "@/lib/topo-data"
import { TopologyGraph } from "@/components/app/topology-graph"
import { cn } from "@/lib/utils"

const stats = [
  { label: "NODES", value: "9" },
  { label: "EDGES", value: "10" },
  { label: "FAILING", value: "2", danger: true },
  { label: "SNAPSHOT", value: "14:32" },
]

const legend = [
  { label: "healthy", swatch: "border-muted-foreground" },
  { label: "elevated", swatch: "border-warn" },
  { label: "failing", swatch: "border-danger" },
]

export function TopologyView() {
  const [t, setT] = useState(5)

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            temporal graph
          </p>
          <h2 className="font-heading text-4xl font-black tracking-tight">
            topology @ <span className="text-warn">t={timeScrubber[t]}</span>
          </h2>
          <p className="mt-2 max-w-xl text-pretty leading-relaxed text-muted-foreground">
            Every node and edge carries a timestamp. Scrub through the last hour to
            see the state of the cluster before, during and after the incident.
          </p>
        </div>
        <div className="grid grid-cols-4 gap-px overflow-hidden rounded-sm border border-border bg-border">
          {stats.map((s) => (
            <div key={s.label} className="bg-card px-4 py-3 text-center">
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                {s.label}
              </p>
              <p
                className={cn(
                  "mt-1 font-heading text-xl font-bold",
                  s.danger && "text-danger",
                )}
              >
                {s.value}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Time scrubber */}
      <section className="rounded-md border border-border bg-card p-5">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="font-heading text-sm font-bold">Time scrubber</h3>
          <span className="font-mono text-[11px] text-muted-foreground">
            topo diff --since 1h
          </span>
        </div>
        <div className="flex items-center gap-1">
          {timeScrubber.map((time, i) => (
            <button
              key={time}
              onClick={() => setT(i)}
              className="group flex flex-1 flex-col items-center gap-2"
            >
              <span
                className={cn(
                  "h-2 w-full rounded-sm transition-colors",
                  i <= t ? "bg-warn" : "bg-secondary group-hover:bg-secondary/70",
                )}
              />
              <span
                className={cn(
                  "font-mono text-[10px]",
                  i === t ? "font-bold text-foreground" : "text-muted-foreground",
                )}
              >
                {time}
              </span>
            </button>
          ))}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <TopologyGraph />

        <aside className="space-y-5 rounded-md border border-border bg-card p-5">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Legend
            </p>
            <ul className="mt-3 space-y-2 font-mono text-[12px]">
              {legend.map((l) => (
                <li key={l.label} className="flex items-center gap-2">
                  <span className={cn("h-3 w-3 rounded-sm border bg-card", l.swatch)} />
                  {l.label}
                </li>
              ))}
              <li className="flex items-center gap-2 text-muted-foreground">
                <span className="h-px w-3 bg-muted-foreground" /> rpc edge
              </li>
              <li className="flex items-center gap-2 text-muted-foreground">
                <span className="h-px w-3 bg-danger" /> failing edge
              </li>
            </ul>
          </div>

          <div className="border-t border-border pt-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Diff vs t-1h
            </p>
            <div className="mt-3 space-y-1 font-mono text-[11px]">
              <p className="text-muted-foreground">
                ~ checkout-api state: ok → <span className="text-danger">blame</span>
              </p>
              <p className="text-muted-foreground">
                ~ pricing-svc state: ok → <span className="text-warn">warn</span>
              </p>
              <p className="text-ok">+ 0 new nodes</p>
              <p className="text-ok">+ 0 new edges</p>
            </div>
          </div>

          <div className="border-t border-border pt-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Tip
            </p>
            <p className="mt-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
              Hover any node to highlight only its connected edges. The graph fades
              the rest.
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}
