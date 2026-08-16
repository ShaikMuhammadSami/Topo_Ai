"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  CircleAlert,
  Network,
  Activity,
  Fingerprint,
  GitBranch,
  TerminalSquare,
  Sparkles,
  Workflow,
  Server,
  GitPullRequestArrow,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { TopoLogo } from "@/components/topo-logo"
import { incident } from "@/lib/topo-data"

const navGroups = [
  {
    label: "Operations",
    items: [
      { href: "/app", label: "Incidents", icon: CircleAlert },
      { href: "/app/topology", label: "Topology", icon: Network },
      { href: "/app/live-cluster", label: "Live infrastructure", icon: Server },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { href: "/app/signals", label: "Changes", icon: Activity },
      { href: "/app/change-impact", label: "Change impact", icon: GitPullRequestArrow },
      { href: "/app/network-dependencies", label: "Dependencies", icon: Network },
      { href: "/app/code-to-runtime", label: "Code → runtime", icon: GitBranch },
      { href: "/app/identities", label: "Identities", icon: Fingerprint },
    ],
  },
  {
    label: "Tools",
    items: [
      { href: "/app/ask", label: "Ask Topo", icon: Sparkles },
      { href: "/app/cli", label: "CLI", icon: TerminalSquare },
      { href: "/app/integrations", label: "Integrations", icon: Workflow },
    ],
  },
]

export function AppSidebar() {
  const pathname = usePathname()

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-sidebar md:flex">
      <div className="flex h-16 items-center border-b border-border px-5">
        <Link href="/">
          <TopoLogo version="v0.1.0" />
        </Link>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        {navGroups.map((group) => (
          <section key={group.label}>
            <p className="px-3 pb-1.5 font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
              {group.label}
            </p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
            const active =
              item.href === "/app"
                ? pathname === "/app" ||
                  pathname.startsWith(
                    "/app/incidents/",
                  )
                : pathname.startsWith(item.href)
                return (
                  <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-sm px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-secondary font-medium text-foreground"
                      : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4" strokeWidth={1.75} />
                      {item.label}
                </Link>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </nav>
      <p className="mb-2 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
          Demo context
       </p>
      <div className="border-t border-border px-5 py-4 font-mono text-[11px] leading-relaxed text-muted-foreground">
        <p>
          cluster <span className="text-foreground">{incident.cluster}</span>
        </p>
        <p>
          ns <span className="text-foreground">{incident.ns}</span>
        </p>
        <p>
          snapshot <span className="text-foreground">t={incident.snapshot}</span>
        </p>
        <p className="mt-2 flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-ok" /> collector connected
        </p>
      </div>
    </aside>
  )
}
