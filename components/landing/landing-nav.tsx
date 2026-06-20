import Link from "next/link"
import { ArrowUpRight } from "lucide-react"
import { TopoLogo } from "@/components/topo-logo"

export function LandingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
      <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-5">
        <Link href="/" aria-label="topo ai home">
          <TopoLogo />
        </Link>
        <div className="hidden items-center gap-7 font-mono text-xs text-muted-foreground md:flex">
          <a href="#how" className="transition-colors hover:text-foreground">
            how it works
          </a>
          <a href="#roadmap" className="transition-colors hover:text-foreground">
            roadmap
          </a>
          <a href="#evidence" className="transition-colors hover:text-foreground">
            why evidence
          </a>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-1 font-mono text-xs text-muted-foreground transition-colors hover:text-foreground sm:flex"
          >
            github <ArrowUpRight className="h-3 w-3" />
          </a>
          <Link
            href="/app"
            className="rounded-sm bg-primary px-3.5 py-2 font-mono text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90"
          >
            launch demo
          </Link>
        </div>
      </nav>
    </header>
  )
}
