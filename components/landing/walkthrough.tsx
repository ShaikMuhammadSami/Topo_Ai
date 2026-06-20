import Link from "next/link"
import { ArrowRight, Network } from "lucide-react"
import { TopoLogo } from "@/components/topo-logo"

export function Walkthrough() {
  return (
    <>
      <section className="border-b border-border">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-20 lg:grid-cols-2 lg:items-center">
          <h2 className="font-heading text-4xl font-black leading-[0.95] tracking-tight text-balance sm:text-5xl">
            walk through
            <br />a live incident.
          </h2>
          <div>
            <p className="max-w-md text-pretty leading-relaxed text-muted-foreground">
              The demo plays out INC-4419 in real time — alert, correlation, ranked
              hypotheses with evidence, on-call action, and recovery verification. No
              setup, no auth.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/app"
                className="inline-flex items-center gap-2 rounded-sm bg-primary px-4 py-2.5 font-mono text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90"
              >
                launch demo <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                href="/app/topology"
                className="inline-flex items-center gap-2 rounded-sm border border-border px-4 py-2.5 font-mono text-sm transition-colors hover:bg-secondary"
              >
                <Network className="h-4 w-4" /> see topology
              </Link>
            </div>
          </div>
        </div>
      </section>

      <footer className="bg-background">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-5 py-10 font-mono text-xs text-muted-foreground sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <TopoLogo />
            <span className="hidden sm:inline">· evidence-based RCA · demo build</span>
          </div>
          <div className="flex gap-5">
            <a href="#" className="hover:text-foreground">docs</a>
            <a href="#" className="hover:text-foreground">changelog</a>
            <a href="#" className="hover:text-foreground">security</a>
            <a href="#" className="hover:text-foreground">status</a>
          </div>
        </div>
      </footer>
    </>
  )
}
