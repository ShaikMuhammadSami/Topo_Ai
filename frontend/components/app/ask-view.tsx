import Link from "next/link"
import { ArrowRight, Sparkles } from "lucide-react"

export function AskView() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-5">
      <header>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          incident-scoped assistance
        </p>
        <h2 className="flex items-center gap-2 font-heading text-4xl font-black tracking-tight">
          <Sparkles className="h-7 w-7 text-warn" /> Ask Topo
        </h2>
      </header>

      <section className="rounded-md border border-border bg-card p-6">
        <h3 className="font-heading text-lg font-bold">
          Start from a recorded incident
        </h3>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          This page does not run a general chatbot or generate an analysis.
          Open an incident to use the existing Incident Copilot with that
          incident&apos;s tenant-scoped evidence and citations.
        </p>
        <p className="mt-3 max-w-2xl font-mono text-xs leading-relaxed text-muted-foreground">
          Provider and model details are shown only when returned by a real
          Copilot session. No AI provider is assumed to be configured.
        </p>
        <Link
          href="/app"
          className="mt-5 inline-flex items-center gap-2 rounded-sm bg-primary px-3 py-2 font-mono text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
        >
          View incidents <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </section>
    </div>
  )
}
