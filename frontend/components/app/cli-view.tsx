import Link from "next/link"
import { ExternalLink, TerminalSquare } from "lucide-react"

const commands = [
  "topo --tenant <tenant-id> incidents list",
  "topo --tenant <tenant-id> causal-rca latest <incident-id>",
  "topo --tenant <tenant-id> incidents blast-radius <incident-id>",
  "topo --tenant <tenant-id> snapshots list",
]

export function CliView() {
  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-5">
      <header>
        <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
          command-line access
        </p>
        <h2 className="flex items-center gap-2 font-heading text-4xl font-black tracking-tight">
          <TerminalSquare className="h-7 w-7 text-info" /> Topo CLI
        </h2>
        <p className="mt-3 max-w-2xl leading-relaxed text-muted-foreground">
          This page is documentation, not an interactive terminal. It does not
          execute commands or represent a connection to your infrastructure.
        </p>
      </header>

      <section className="rounded-md border border-border bg-card p-5">
        <h3 className="font-heading text-lg font-bold">Use the real terminal CLI</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Install the CLI from the repository, select a tenant you can access,
          and run supported commands from your own terminal.
        </p>
        <pre className="mt-4 overflow-x-auto rounded-sm border border-border bg-background p-4 font-mono text-xs">
          <code>python -m pip install -e ./cli</code>
        </pre>
        <div className="mt-4 space-y-2">
          {commands.map((command) => (
            <pre
              key={command}
              className="overflow-x-auto rounded-sm border border-border bg-background px-4 py-3 font-mono text-xs text-muted-foreground"
            >
              <code>{command}</code>
            </pre>
          ))}
        </div>
        <Link
          href="https://github.com/ShaikMuhammadSami/Topo_Ai/blob/main/docs/LOCAL_EVALUATION.md"
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex items-center gap-2 rounded-sm border border-border px-3 py-2 font-mono text-xs transition-colors hover:bg-secondary"
        >
          Open the local evaluation guide <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      </section>
    </div>
  )
}
