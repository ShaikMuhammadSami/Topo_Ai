import Link from "next/link"
import { Search, Bell, GitCommitHorizontal } from "lucide-react"
import { incident } from "@/lib/topo-data"

export function AppTopbar({
  title,
  path,
}: {
  title: string
  path: string
}) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-border bg-background/85 px-5 backdrop-blur">
      <div className="flex min-w-0 items-center gap-2">
        <h1 className="truncate font-heading text-sm font-bold">{title}</h1>
        <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
          / {path}
        </span>
      </div>

      <div className="ml-auto hidden items-center gap-2 rounded-sm border border-border bg-card px-3 py-1.5 lg:flex">
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          placeholder="search services, pods, sha, identities…"
          className="w-64 bg-transparent font-mono text-xs text-foreground outline-none placeholder:text-muted-foreground"
        />
        <kbd className="rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </div>

      <Link
        href="/app"
        className="flex items-center gap-2 rounded-sm border border-danger/40 bg-danger/10 px-2.5 py-1.5 font-mono text-xs font-semibold text-danger"
      >
        <span className="h-1.5 w-1.5 rounded-sm bg-danger" />
        {incident.id} · {incident.sev}
      </Link>

      <button
        className="rounded-sm border border-border p-2 text-muted-foreground transition-colors hover:text-foreground"
        aria-label="Notifications"
      >
        <Bell className="h-4 w-4" />
      </button>

      <div className="hidden items-center gap-1.5 rounded-sm border border-border px-2.5 py-1.5 font-mono text-xs text-muted-foreground sm:flex">
        <GitCommitHorizontal className="h-3.5 w-3.5" />
        {incident.sha}
      </div>
    </header>
  )
}
