import { MessageSquare, TriangleAlert, GitPullRequest } from "lucide-react"

const slack = [
  { who: "topo", bot: true, time: "14:32:14", text: "*INC-4419* checkout-api error-rate 3.2%. Investigating — I'll post when evidence confidence > 0.85." },
  { who: "topo", bot: true, time: "14:32:34", text: "Top hypothesis (0.91): regression from PR #2284 (cache removal). 2 corroborating signals + 1 diff." },
  { who: "m.solis", bot: false, time: "14:33:11", text: "yeah that was me. on it. reverting." },
  { who: "topo", bot: true, time: "14:35:50", text: "Detected revert sha 3c01ab8 deploying — recovery loop armed." },
  { who: "topo", bot: true, time: "14:39:14", text: "Recovery confirmed. Error-rate 0.14% / p99 240ms. Closing INC-4419. PR comment posted to #2284." },
]

const pagerduty = [
  "top hypothesis H1 · conf 0.91",
  "suspected commit 9a4f12c (PR #2284)",
  "blast radius 9/11 pods OOM",
  "runbook cache-removal-blast-radius",
  "recommended revert PR #2284",
]

export function IntegrationsView() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          workflow integrations
        </p>
        <h2 className="font-heading text-4xl font-black tracking-tight">
          where topo shows up
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          Once a hypothesis crosses the confidence threshold, topo posts to your
          existing tools. No new dashboard required.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Slack */}
        <section className="rounded-md border border-border bg-card">
          <header className="flex items-center gap-2 border-b border-border px-5 py-3">
            <MessageSquare className="h-4 w-4 text-warn" />
            <h3 className="font-heading text-sm font-bold">Slack · #incidents-payments</h3>
          </header>
          <ul className="space-y-4 p-5">
            {slack.map((m, i) => (
              <li key={i} className="flex gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-secondary font-mono text-[11px] font-bold">
                  {m.who[0]}
                </span>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{m.who}</span>
                    {m.bot && (
                      <span className="rounded-sm bg-warn/20 px-1 font-mono text-[9px] uppercase text-warn">
                        bot
                      </span>
                    )}
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {m.time}
                    </span>
                  </div>
                  <p className="mt-0.5 font-mono text-[12px] leading-relaxed text-muted-foreground">
                    {m.text}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* PagerDuty */}
        <section className="rounded-md border border-border bg-card">
          <header className="flex items-center gap-2 border-b border-border px-5 py-3">
            <TriangleAlert className="h-4 w-4 text-danger" />
            <h3 className="font-heading text-sm font-bold">PagerDuty · INC-4419</h3>
          </header>
          <div className="space-y-4 p-5 font-mono text-[12px]">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Incident
              </p>
              <p className="mt-1">checkout-api: elevated 5xx + latency</p>
            </div>
            <div className="border-t border-border pt-4">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                topo enrichment
              </p>
              <ul className="mt-2 space-y-1 text-muted-foreground">
                {pagerduty.map((p) => (
                  <li key={p}>❯ {p}</li>
                ))}
              </ul>
            </div>
            <div className="border-t border-border pt-4">
              <p className="text-[10px] uppercase tracking-widest text-muted-foreground">
                Recovery verification
              </p>
              <p className="mt-2 text-ok">✓ confirmed at 14:39:14 (Δ 3m23s after fix)</p>
            </div>
          </div>
        </section>
      </div>

      {/* GitHub */}
      <section className="rounded-md border border-border bg-card">
        <header className="flex items-center gap-2 border-b border-border px-5 py-3">
          <GitPullRequest className="h-4 w-4 text-info" />
          <h3 className="font-heading text-sm font-bold">GitHub · acme/checkout #2284</h3>
        </header>
        <div className="p-5">
          <p className="text-sm font-semibold">
            perf: drop in-memory cache on price_quote (use pricing-svc)
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
            topo-bot · just now · pre-merge analysis
          </p>
          <pre className="mt-4 overflow-x-auto rounded-sm border border-border bg-background p-4 font-mono text-[12px] leading-relaxed text-muted-foreground">
            <code>
              <span className="text-foreground">**topo blast-radius analysis**</span>
              {"\n\n"}
              This PR removes <span className="text-warn">@lru_cache(maxsize=4096)</span> from{" "}
              <span className="text-warn">price_quote()</span>. Based on production traffic
              snapshot from the last 24h:{"\n\n"}
              - estimated DB query increase on pricing.quotes:{" "}
              <span className="text-danger">18×</span> (3.2/s → 58/s){"\n"}
              - pricing-svc p99 latency forecast:{" "}
              <span className="text-danger">320ms</span>
              {"\n"}- 9 of 11 checkout-api pods within 35Mi of memory limit — likely OOM
              {"\n\n"}
              <span className="text-foreground">
                **Recommendation:** raise memory limit to 1Gi or keep an LRU cache (size ≥
                1024) before merging.
              </span>
            </code>
          </pre>
          <div className="mt-4 flex gap-2">
            <button className="rounded-sm bg-danger px-3 py-1.5 font-mono text-xs font-semibold text-danger-foreground">
              request changes
            </button>
            <button className="rounded-sm border border-border px-3 py-1.5 font-mono text-xs transition-colors hover:bg-secondary">
              acknowledge &amp; merge
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
