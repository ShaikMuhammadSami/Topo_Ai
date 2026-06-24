"use client"

import { useState } from "react"
import { signals, commits, type SignalKind } from "@/lib/topo-data"
import { cn } from "@/lib/utils"

const filters: (SignalKind | "ALL")[] = [
  "ALL",
  "ALERT",
  "DEPLOY",
  "DIFF",
  "POD",
  "METRIC",
  "SCALE",
  "CONFIG",
]

const kindStyle: Record<SignalKind, string> = {
  ALERT: "border-danger/50 text-danger",
  DEPLOY: "border-info/50 text-info",
  DIFF: "border-warn/50 text-warn",
  POD: "border-danger/50 text-danger",
  METRIC: "border-warn/50 text-warn",
  SCALE: "border-ok/50 text-ok",
  CONFIG: "border-ok/50 text-ok",
}

export function SignalsView() {
  const [active, setActive] = useState<(typeof filters)[number]>("ALL")
  const filtered =
    active === "ALL" ? signals : signals.filter((s) => s.kind === active)

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          signal stream
        </p>
        <h2 className="font-heading text-4xl font-black tracking-tight">
          Signals &amp; changes
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          Every signal — git diffs, deploys, k8s events, metric anomalies — pinned to
          the temporal graph at the moment it occurred.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {filters.map((f) => (
          <button
            key={f}
            onClick={() => setActive(f)}
            className={cn(
              "rounded-sm border px-3 py-1.5 font-mono text-xs transition-colors",
              active === f
                ? "border-transparent bg-primary text-primary-foreground"
                : "border-border text-muted-foreground hover:bg-secondary",
            )}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.7fr_1fr]">
        <section className="rounded-md border border-border bg-card">
          <header className="flex items-center justify-between border-b border-border px-5 py-3">
            <h3 className="font-heading text-sm font-bold">Stream</h3>
            <span className="font-mono text-[11px] text-muted-foreground">
              {filtered.length} signals
            </span>
          </header>
          <ul className="divide-y divide-border">
            {filtered.map((s, i) => (
              <li
                key={i}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3.5 transition-colors hover:bg-secondary/40"
              >
                <span className="font-mono text-[11px] text-muted-foreground">
                  {s.time}
                </span>
                <span
                  className={cn(
                    "w-20 rounded-sm border px-2 py-0.5 text-center font-mono text-[10px] uppercase",
                    kindStyle[s.kind],
                  )}
                >
                  {s.kind}
                </span>
                <span className="font-mono text-[12px] text-foreground">{s.svc}</span>
                <span className="font-mono text-[12px] text-muted-foreground">
                  {s.text}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-md border border-border bg-card">
          <header className="border-b border-border px-5 py-3">
            <h3 className="font-heading text-sm font-bold">Recent commits</h3>
          </header>
          <ul className="divide-y divide-border">
            {commits.map((c) => (
              <li key={c.sha} className="p-5">
                <div className="flex items-center gap-2 font-mono text-[11px]">
                  <span className="text-warn">{c.repo}</span>
                  <span className="text-muted-foreground">· {c.time}</span>
                  {c.suspected && (
                    <span className="rounded-sm bg-danger/15 px-1.5 py-0.5 text-[10px] text-danger">
                      SUSPECTED
                    </span>
                  )}
                </div>
                <p className="mt-1.5 text-sm font-medium leading-snug">{c.msg}</p>
                <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                  {c.sha} {c.pr} by {c.by}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
