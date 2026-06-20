import { Activity, Fingerprint, GitBranch, RefreshCw } from "lucide-react"

const features = [
  {
    icon: Activity,
    title: "Temporal graph",
    body: "Every node + edge carries timestamps. State-over-time, not just now. `topo diff --since 1h`.",
  },
  {
    icon: Fingerprint,
    title: "Identity resolution",
    body: "Repo → image → helm → deployment → pod, with confidence scores. The backbone.",
  },
  {
    icon: GitBranch,
    title: "Evidence engine",
    body: "Ranked hypotheses with supporting & counter-evidence. Not a single black-box answer.",
  },
  {
    icon: RefreshCw,
    title: "Recovery loop",
    body: "After a fix, topo watches the same signals to confirm — or flag a hidden second cause.",
  },
]

export function HowItWorks() {
  return (
    <section id="how" className="border-b border-border">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <div className="grid gap-8 lg:grid-cols-[1fr_1.4fr] lg:items-start">
          <div>
            <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              how it works
            </p>
            <h2 className="font-heading text-3xl font-black leading-tight tracking-tight text-balance sm:text-4xl">
              an incident is a story. not a graph.
            </h2>
          </div>
          <p className="max-w-xl text-pretty leading-relaxed text-muted-foreground lg:pt-12">
            topo ai is built around the narrative of an incident — what changed, when,
            what broke, and what evidence supports each theory. The topology view is
            secondary; the timeline + ranked hypotheses are the primary surface.
            Engineers spend less time spelunking, more time deciding.
          </p>
        </div>

        <div className="mt-12 grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <div key={f.title} className="bg-card p-6">
              <f.icon className="h-5 w-5 text-warn" strokeWidth={1.75} />
              <h3 className="mt-4 font-heading text-base font-bold">{f.title}</h3>
              <p className="mt-2 font-mono text-[12px] leading-relaxed text-muted-foreground">
                {f.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
