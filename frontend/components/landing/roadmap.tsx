const phases = [
  {
    phase: "phase 1",
    name: "foundation",
    items: [
      { id: "01", title: "K8s discovery + temporal graph model", body: "Versioned snapshots, evidence metadata, CLI: topo discover, topo diff --since 1h" },
      { id: "02", title: "Identity resolution subsystem", body: "Maps repo → image → helm release → deployment → pod → network identity with confidence." },
      { id: "03", title: "Git + CI/CD layer + signal ingestion", body: "GitHub/GitLab + Actions + ArgoCD + pod/k8s events on the graph with timestamps." },
    ],
  },
  {
    phase: "phase 2",
    name: "intelligence",
    items: [
      { id: "04", title: "Evidence-based blame engine", body: "Ranked hypotheses with supporting & counter-evidence. Confidence over single-answer." },
      { id: "05", title: "Recovery verification loop", body: "Confirms recovery against the same signals that triggered the alert. Builds ground truth." },
    ],
  },
  {
    phase: "phase 3",
    name: "product surface",
    items: [
      { id: "06", title: "Incident workspace (narrative-first)", body: "Timeline + evidence panel. Topology is secondary. Replay for past incidents." },
      { id: "07", title: "Workflow integration", body: "Slack / PagerDuty / PR comments only after RCA is explainable." },
    ],
  },
  {
    phase: "phase 4",
    name: "depth",
    items: [
      { id: "08", title: "eBPF network discovery (PoC)", body: "DaemonSet captures actual TCP/UDP flows. Ground truth, not inferred." },
      { id: "09", title: "LLM reasoning layer", body: "On-prem Llama/Mistral 70b over the graph + RAG over runbooks." },
    ],
  },
]

export function Roadmap() {
  return (
    <section id="roadmap" className="border-b border-border">
      <div className="mx-auto max-w-6xl px-5 py-20">
        <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          build roadmap
        </p>
        <h2 className="font-heading text-3xl font-black leading-tight tracking-tight text-balance sm:text-4xl">
          block by block, evidence-first.
        </h2>
        <p className="mt-4 max-w-xl text-pretty leading-relaxed text-muted-foreground">
          Temporal history is in Block 1, identity resolution gets its own block,
          signals before blame, and Slack only after the RCA is explainable.
        </p>

        <div className="mt-12 divide-y divide-border border-y border-border">
          {phases.map((p) => (
            <div key={p.name} className="grid gap-6 py-8 lg:grid-cols-[180px_1fr]">
              <div>
                <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                  {p.phase}
                </p>
                <h3 className="mt-1 font-heading text-xl font-bold">{p.name}</h3>
                {/* <p className="mt-1 font-mono text-[11px] text-warn">{p.weeks}</p> */}
              </div>
              <div className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
                {p.items.map((it) => (
                  <div key={it.id} className="bg-card p-5">
                    <div className="flex items-center gap-2">
                      <span className="rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-[10px] font-bold">
                        {it.id}
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {/* {it.weeks} */}
                      </span>
                    </div>
                    <h4 className="mt-3 text-sm font-semibold leading-snug">{it.title}</h4>
                    <p className="mt-1.5 font-mono text-[11px] leading-relaxed text-muted-foreground">
                      {it.body}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
