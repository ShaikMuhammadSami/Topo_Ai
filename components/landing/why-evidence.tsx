export function WhyEvidence() {
  return (
    <section id="evidence" className="border-b border-border bg-card/40">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 py-20 lg:grid-cols-2 lg:items-center">
        <div>
          <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            why evidence first
          </p>
          <h2 className="font-heading text-3xl font-black leading-tight tracking-tight text-balance sm:text-4xl">
            a confidence score you can defend in review.
          </h2>
          <p className="mt-5 max-w-md text-pretty leading-relaxed text-muted-foreground">
            Single-answer RCA tools are unfalsifiable. topo ai is built around an
            evidence ledger: every score breaks down into the diffs, signals and
            temporal correlations that contributed — and the counter-evidence that
            subtracted. Disagree with the verdict? Show your work.
          </p>
        </div>

        <div className="rounded-md border border-border bg-card">
          <div className="border-b border-border px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
            // hypothesis #1 — confidence 0.91
          </div>
          <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-relaxed">
            <code>
              <span className="text-ok">+ 0.42</span> diff: payments/checkout.py removed @lru_cache{"\n"}
              <span className="text-ok">+ 0.31</span> temporal: deploy 14:28:41 → spike 14:32:08 (Δ+3m27s){"\n"}
              <span className="text-ok">+ 0.18</span> signal: pricing.quotes db queries ↑ 18× (58/s){"\n"}
              <span className="text-danger">- 0.05</span> counter: 2/11 pods show healthy memory{"\n"}
              <span className="text-muted-foreground">{"─".repeat(46)}</span>{"\n"}
              <span className="text-warn">= 0.91</span>{" "}
              <span className="text-muted-foreground">(threshold for slack post: 0.85)</span>
            </code>
          </pre>
        </div>
      </div>
    </section>
  )
}
