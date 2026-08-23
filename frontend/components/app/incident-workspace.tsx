"use client"

import { useState } from "react"
import { Pause, Play, FastForward, RotateCcw } from "lucide-react"
import {
  incident,
  timeline,
  hypotheses,
  recovery,
} from "@/lib/topo-data"
import { TopologyGraph } from "@/components/app/topology-graph"
import { cn } from "@/lib/utils"

const kindStyle: Record<string, string> = {
  alert: "border-danger/50 text-danger",
  topo: "border-info/50 text-info",
  signal: "border-warn/50 text-warn",
}

export function IncidentWorkspace() {
  const [revealed, setRevealed] = useState(false)
  const [playing, setPlaying] = useState(true)

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      {/* Incident header card */}
      <section className="rounded-md border border-danger/40 bg-danger/[0.04] p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
            <span className="rounded-sm border border-border px-2 py-0.5">
              {incident.id}
            </span>
            <span className="rounded-sm border border-border px-2 py-0.5">
              {incident.sev}
            </span>
            <span className="rounded-sm border border-warn/50 px-2 py-0.5 text-warn">
              {incident.status}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPlaying((p) => !p)}
              className="inline-flex items-center gap-1.5 rounded-sm border border-border px-3 py-1.5 font-mono text-xs transition-colors hover:bg-secondary"
            >
              {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {playing ? "pause" : "play"}
            </button>
            <button
              onClick={() => setRevealed(true)}
              className="rounded-sm border border-border p-2 text-muted-foreground transition-colors hover:text-warn"
              aria-label="Fast forward"
            >
              <FastForward className="h-4 w-4" />
            </button>
            <button
              onClick={() => setRevealed(false)}
              className="rounded-sm border border-border p-2 text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Restart"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          </div>
        </div>

        <h2 className="mt-4 font-heading text-3xl font-black tracking-tight text-balance">
          {incident.title}
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          {incident.summary}
        </p>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 font-mono text-[11px] text-muted-foreground">
          <span>svc <span className="text-foreground">{incident.svc}</span></span>
          <span>ns <span className="text-foreground">{incident.ns}</span></span>
          <span>owner <span className="text-foreground">{incident.owner}</span></span>
          <span>detected <span className="text-foreground">{incident.detected}</span></span>
        </div>

        {/* mini timeline bar */}
        <div className="mt-5 flex items-center gap-1">
          <span className="mr-2 font-mono text-[10px] text-muted-foreground">t=14:32:08</span>
          {Array.from({ length: 14 }).map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-2 flex-1 rounded-sm",
                i < 6 ? "bg-warn" : "bg-secondary",
              )}
            />
          ))}
          <span className="ml-2 font-mono text-[10px] text-muted-foreground">14:39:14</span>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Timeline */}
        <section className="rounded-md border border-border bg-card">
          <header className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="font-heading text-sm font-bold">Incident timeline</h3>
            <span className="font-mono text-[11px] text-muted-foreground">
              {timeline.length}/10 events
            </span>
          </header>
          <ol className="space-y-5 p-5">
            {timeline.map((t, i) => (
              <li key={i} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="mt-1.5 h-2 w-2 rounded-sm bg-muted-foreground/40" />
                  {i < timeline.length - 1 && (
                    <span className="mt-1 w-px flex-1 bg-border" />
                  )}
                </div>
                <div className="-mt-0.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] uppercase",
                        kindStyle[t.kind],
                      )}
                    >
                      {t.kind}
                    </span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {t.time}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm font-semibold">{t.title}</p>
                  <p className="mt-0.5 font-mono text-[11px] leading-relaxed text-muted-foreground">
                    {t.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* Hypotheses */}
        <section className="rounded-md border border-border bg-card">
          <header className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="font-heading text-sm font-bold">Ranked hypotheses</h3>
            <span className="font-mono text-[11px] text-muted-foreground">
              {revealed ? "3 hypotheses · heuristic rank ≥ 0.18" : "awaiting evidence threshold…"}
            </span>
          </header>
          {revealed ? (
            <ul className="divide-y divide-border">
              {hypotheses.map((h) => (
                <li key={h.rank} className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "rounded-sm px-1.5 py-0.5 font-mono text-[11px] font-bold",
                          h.rank === "H1"
                            ? "bg-danger/15 text-danger"
                            : "bg-secondary text-muted-foreground",
                        )}
                      >
                        {h.rank}
                      </span>
                      <span className="text-sm font-semibold">{h.title}</span>
                    </div>
                    <span
                      className={cn(
                        "font-mono text-sm font-bold",
                        h.confidence >= 0.85
                          ? "text-warn"
                          : h.confidence >= 0.5
                            ? "text-foreground"
                            : "text-muted-foreground",
                      )}
                    >
                      {h.confidence.toFixed(2)}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-sm bg-secondary">
                    <span
                      className="block h-full rounded-sm bg-warn"
                      style={{ width: `${h.confidence * 100}%` }}
                    />
                  </div>
                  <div className="mt-3 space-y-1 font-mono text-[11px]">
                    {h.evidence.map((e, i) => (
                      <p key={i} className="text-muted-foreground">
                        <span className="text-ok">+{e.weight.toFixed(2)}</span> {e.label}
                      </p>
                    ))}
                    {h.counter.map((e, i) => (
                      <p key={i} className="text-muted-foreground">
                        <span className="text-danger">-{e.weight.toFixed(2)}</span> {e.label}
                      </p>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="flex min-h-48 flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="font-mono text-[12px] text-muted-foreground">
                topo is correlating signals… hypotheses appear once evidence
                heuristic rank ≥ 0.50
              </p>
              <button
                onClick={() => setRevealed(true)}
                className="rounded-sm bg-primary px-3 py-1.5 font-mono text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                reveal hypotheses →
              </button>
            </div>
          )}
        </section>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        {/* Topology */}
        <section className="rounded-md border border-border bg-card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-heading text-sm font-bold">Topology · blast radius</h3>
            <span className="font-mono text-[11px] text-muted-foreground">
              red edge = failing dependency
            </span>
          </div>
          <TopologyGraph />
        </section>

        {/* Recovery */}
        <section className="rounded-md border border-border bg-card">
          <header className="border-b border-border px-5 py-3">
            <h3 className="font-heading text-sm font-bold">Recovery verification</h3>
          </header>
          <div className="space-y-4 p-5">
            {recovery.map((r) => (
              <div key={r.label} className="font-mono text-[12px]">
                <div className="flex items-center justify-between">
                  <span>{r.label}</span>
                  <span className="text-muted-foreground">baseline {r.baseline}</span>
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <span className="text-danger line-through">{r.from}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="text-ok">{r.to}</span>
                </div>
              </div>
            ))}
            <div className="rounded-sm border border-border bg-background p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
              <p className="uppercase tracking-widest text-foreground">recovery confirmed</p>
              <p className="mt-1">
                topo re-evaluated the same signals that triggered the alert. Closed
                at 14:39:14 (Δ 3m23s after fix).
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
