import Link from "next/link"
import { ArrowRight, Terminal } from "lucide-react"

export function Hero() {
  return (
    <section className="relative overflow-hidden border-b border-border">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-foreground) 1px, transparent 1px), linear-gradient(90deg, var(--color-foreground) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
        aria-hidden
      />
      <div className="relative mx-auto grid max-w-6xl items-center gap-12 px-5 py-20 lg:grid-cols-2 lg:py-28">
        <div>
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 font-mono text-[11px] uppercase tracking-widest text-warn">
            <span className="h-1.5 w-1.5 rounded-full bg-warn" />
            evidence-based RCA for kubernetes
          </div>
          <h1 className="font-heading text-5xl font-black leading-[0.95] tracking-tight text-balance sm:text-6xl">
            stop guessing
            <br />
            <span className="text-warn">at root cause.</span>
          </h1>
          <p className="mt-6 max-w-md text-pretty leading-relaxed text-muted-foreground">
            topo ai correlates your temporal k8s graph, git diffs, deploy events and
            live signals into a ranked list of hypotheses — each with supporting{" "}
            <span className="text-foreground">and counter</span> evidence, and a
            confidence you can defend in an incident review.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/app"
              className="inline-flex items-center gap-2 rounded-sm bg-primary px-4 py-2.5 font-mono text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
            >
              launch the live incident <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/app/cli"
              className="inline-flex items-center gap-2 rounded-sm border border-border px-4 py-2.5 font-mono text-sm transition-colors hover:bg-secondary"
            >
              <Terminal className="h-4 w-4" /> open the CLI
            </Link>
          </div>
          <div className="mt-8 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-ok" /> on-prem LLM ready
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-ok" /> eBPF flows (PoC)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-ok" /> slack · pagerduty · github
            </span>
          </div>
        </div>

        <HeroTerminal />
      </div>
    </section>
  )
}

function HeroTerminal() {
  return (
    <div className="rounded-md border border-border bg-card shadow-2xl">
      <div className="flex items-center gap-1.5 border-b border-border px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
        <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
        <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30" />
        <span className="ml-3 font-mono text-[11px] text-muted-foreground">
          topo — zsh — 120×30
        </span>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-relaxed">
        <code>
          <span className="text-warn">topo</span>{" "}
          <span className="text-info">topo</span> why checkout-api{"\n"}
          <span className="text-muted-foreground">
            {"  "}~ pulling temporal graph @ t=14:32:08Z ± 60m{"\n"}
            {"  "}~ 27 signals · 4 diffs · 11 pod events · 1 deploy{"\n\n"}
          </span>
          <span className="text-danger">H1</span>{" "}
          <span className="text-warn">conf=0.91</span>{" "}
          Cache removal regression in price_quote(){"\n"}
          <span className="text-muted-foreground">
            {"    "}+0.42 diff: payments/checkout.py removed @lru_cache{"\n"}
            {"    "}+0.31 temporal: deploy @ 14:28:41 → spike 14:32:08 (Δ+3m27s){"\n"}
            {"    "}+0.18 signal: 28 queries on pricing.quotes ↑ 18×{"\n"}
          </span>
          <span className="text-warn">H2</span>{" "}
          <span className="text-muted-foreground">conf=0.74</span>{" "}
          Memory limit exhaustion (OOMKilled){"\n"}
          <span className="text-warn">H3</span>{" "}
          <span className="text-muted-foreground">conf=0.18</span>{" "}
          Upstream pricing-svc latency{"\n\n"}
          <span className="text-ok">✓ ranked 3 hypotheses with evidence chains in 412ms</span>
        </code>
      </pre>
    </div>
  )
}
