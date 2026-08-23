import { identities } from "@/lib/topo-data"
import { cn } from "@/lib/utils"

const stats = [
  { label: "TOTAL", value: 7, color: "text-foreground" },
  { label: "LABEL-MATCH", value: 4, color: "text-ok" },
  { label: "HEURISTIC", value: 2, color: "text-warn" },
  { label: "MANUAL", value: 1, color: "text-info" },
]

const sourceStyle: Record<string, string> = {
  "LABEL-MATCH": "border-ok/50 text-ok",
  "NAMING-HEURISTIC": "border-warn/50 text-warn",
  "MANUAL-OVERRIDE": "border-info/50 text-info",
}

export function IdentitiesView() {
  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-5">
      <div>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          identity resolution
        </p>
        <h2 className="font-heading text-4xl font-black tracking-tight">
          repo <span className="text-muted-foreground">→</span> pod, with a deterministic match score
        </h2>
        <p className="mt-2 max-w-2xl text-pretty leading-relaxed text-muted-foreground">
          The backbone of everything downstream. If identities are wrong, blame is
          wrong. Every match carries a heuristic match score and a source - label match
          (~0.99), naming heuristic (~0.7) or manual override (1.00).
        </p>
      </div>

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="bg-card px-5 py-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {s.label}
            </p>
            <p className={cn("mt-1 font-heading text-2xl font-bold", s.color)}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      <section className="overflow-x-auto rounded-md border border-border bg-card">
        <table className="w-full min-w-[860px] border-collapse">
          <thead>
            <tr className="border-b border-border font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              <th className="px-4 py-3 text-left font-normal">Repo</th>
              <th className="px-4 py-3 text-left font-normal">Image</th>
              <th className="px-4 py-3 text-left font-normal">Helm release</th>
              <th className="px-4 py-3 text-left font-normal">Deployment</th>
              <th className="px-4 py-3 text-left font-normal">Pod prefix</th>
              <th className="px-4 py-3 text-left font-normal">Svc CIDR</th>
              <th className="px-4 py-3 text-left font-normal">Source</th>
              <th className="px-4 py-3 text-left font-normal">Match score</th>
            </tr>
          </thead>
          <tbody className="font-mono text-[12px]">
            {identities.map((r) => (
              <tr
                key={r.image}
                className="border-b border-border last:border-0 transition-colors hover:bg-secondary/40"
              >
                <td className="px-4 py-3 text-info">{r.repo}</td>
                <td className="px-4 py-3">{r.image}</td>
                <td className="px-4 py-3 text-muted-foreground">{r.helm}</td>
                <td className="px-4 py-3 font-semibold">{r.deployment}</td>
                <td className="px-4 py-3 text-muted-foreground">{r.pod}</td>
                <td className="px-4 py-3 text-muted-foreground">{r.cidr}</td>
                <td className="px-4 py-3">
                  <span
                    className={cn(
                      "rounded-sm border px-1.5 py-0.5 text-[10px] uppercase",
                      sourceStyle[r.source],
                    )}
                  >
                    {r.source}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-16 overflow-hidden rounded-sm bg-secondary">
                      <span
                        className={cn(
                          "block h-full rounded-sm",
                          r.conf >= 0.9 ? "bg-ok" : "bg-warn",
                        )}
                        style={{ width: `${r.conf * 100}%` }}
                      />
                    </span>
                    {r.conf.toFixed(2)}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
