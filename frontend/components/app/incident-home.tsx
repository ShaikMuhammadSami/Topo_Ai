"use client"

import Link from "next/link"
import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  ArrowUpRight,
  Clock3,
  History,
  LoaderCircle,
  RefreshCw,
  Search,
  SlidersHorizontal,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  filterIncidentHomeRecords,
  incidentNeedsAttention,
  type IncidentHomeScope,
} from "@/lib/incident-home"
import { incidentWorkspaceHref } from "@/lib/incident-briefing"
import { listIncidentRecords } from "@/lib/topo-api"
import type {
  IncidentRecordSummary,
  IncidentStatus,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"

const statusStyles: Record<
  IncidentStatus,
  string
> = {
  open: "border-info/30 bg-info/10 text-info",
  investigating:
    "border-warn/30 bg-warn/10 text-warn",
  recommended:
    "border-ok/30 bg-ok/10 text-ok",
  remediating:
    "border-warn/30 bg-warn/10 text-warn",
  resolved: "border-ok/30 bg-ok/10 text-ok",
  dismissed:
    "border-border bg-secondary text-muted-foreground",
}

export function IncidentHome() {
  const [incidents, setIncidents] = useState<
    IncidentRecordSummary[]
  >([])
  const [scope, setScope] =
    useState<IncidentHomeScope>("attention")
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] =
    useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    let active = true

    async function loadIncidents() {
      setLoading(true)
      setError(null)

      try {
        const result = await listIncidentRecords({
          limit: 100,
        })

        if (active) {
          setIncidents(result)
        }
      } catch (requestError) {
        if (active) {
          setError(
            requestError instanceof Error
              ? requestError.message
              : "Unable to load incidents.",
          )
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    void loadIncidents()

    return () => {
      active = false
    }
  }, [retryKey])

  const visibleIncidents = useMemo(
    () =>
      filterIncidentHomeRecords(incidents, {
        query,
        scope,
      }),
    [incidents, query, scope],
  )
  const attentionCount = incidents.filter(
    incidentNeedsAttention,
  ).length

  return (
    <main className="mx-auto w-full max-w-[1450px] px-4 py-5 sm:px-6 lg:py-7">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-primary">
            Incident home
          </p>
          <h1 className="mt-1 font-heading text-2xl font-black tracking-tight sm:text-3xl">
            What needs attention?
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
            Open an incident to review Topo&apos;s unified answer, response guidance and evidence.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button asChild variant="ghost" size="sm">
            <Link href="/app?mode=advanced#analysis-history">
              <History /> Analysis history
            </Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/app?mode=advanced#custom-analysis">
              <SlidersHorizontal /> Run custom analysis
            </Link>
          </Button>
        </div>
      </header>

      <section className="mt-5 overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-col gap-3 border-b border-border p-3 sm:flex-row sm:items-center sm:justify-between">
          <div
            className="inline-flex w-fit rounded-sm border border-border bg-background p-0.5"
            aria-label="Incident list scope"
          >
            <ScopeButton
              active={scope === "attention"}
              onClick={() => setScope("attention")}
              label={`Needs attention · ${attentionCount}`}
            />
            <ScopeButton
              active={scope === "recent"}
              onClick={() => setScope("recent")}
              label={`Recent · ${incidents.length}`}
            />
          </div>

          <label className="flex h-8 min-w-0 items-center gap-2 rounded-sm border border-input bg-background px-2.5 sm:w-80">
            <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            <span className="sr-only">Search incidents</span>
            <input
              value={query}
              onChange={(event) =>
                setQuery(event.target.value)
              }
              placeholder="Search incident, service, namespace…"
              className="min-w-0 flex-1 bg-transparent font-mono text-[11px] outline-none placeholder:text-muted-foreground"
            />
          </label>
        </div>

        {error && (
          <div className="m-4 flex items-start justify-between gap-4 rounded-sm border border-danger/35 bg-danger/5 p-3 text-danger">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="font-mono text-xs">{error}</p>
            </div>
            <Button
              size="xs"
              variant="outline"
              onClick={() =>
                setRetryKey((value) => value + 1)
              }
            >
              <RefreshCw /> Retry
            </Button>
          </div>
        )}

        {loading ? (
          <div
            className="flex items-center gap-2 p-8 font-mono text-xs text-muted-foreground"
            aria-label="Loading incident home"
          >
            <LoaderCircle className="h-4 w-4 animate-spin" />
            Loading incidents…
          </div>
        ) : visibleIncidents.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-sm font-semibold">
              No matching incidents
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Try the recent view or clear the search.
            </p>
          </div>
        ) : (
          <ol className="divide-y divide-border">
            {visibleIncidents.map((incident) => (
              <IncidentHomeRow
                key={incident.incident_id}
                incident={incident}
              />
            ))}
          </ol>
        )}
      </section>

      <p className="mt-3 font-mono text-[10px] text-muted-foreground">
        Advanced analysis and stored analysis history remain available without changing the standard incident flow.
      </p>
    </main>
  )
}

function ScopeButton({
  active,
  onClick,
  label,
}: {
  active: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "rounded-[2px] px-3 py-1.5 font-mono text-[10px] transition-colors",
        active
          ? "bg-secondary text-foreground"
          : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  )
}

function IncidentHomeRow({
  incident,
}: {
  incident: IncidentRecordSummary
}) {
  const hypothesis =
    incident.top_hypothesis_title ??
    "Causal analysis is not available yet"

  return (
    <li>
      <Link
        href={incidentWorkspaceHref(
          incident.incident_id,
        )}
        className="group grid gap-3 px-4 py-4 transition-colors hover:bg-secondary/35 focus-visible:bg-secondary/35 focus-visible:outline-none sm:grid-cols-[minmax(0,1fr)_minmax(220px,0.7fr)_130px_24px] sm:items-center"
      >
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-sm border px-2 py-0.5 font-mono text-[9px] uppercase",
                statusStyles[incident.status],
              )}
            >
              {incident.status}
            </span>
            <span className="font-mono text-[9px] uppercase text-danger">
              {incident.severity}
            </span>
          </div>
          <h2 className="mt-2 truncate text-sm font-semibold sm:text-base">
            {incident.title}
          </h2>
          <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">
            {incident.cluster_name} · {incident.namespace ?? "cluster"} · {incident.affected_object_name ?? "unknown target"}
          </p>
        </div>

        <div className="min-w-0 border-l border-border pl-3">
          <p className="font-mono text-[9px] uppercase tracking-wider text-muted-foreground">
            Leading signal
          </p>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-foreground/85">
            {hypothesis}
          </p>
        </div>

        <div className="flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground sm:justify-end">
          <Clock3 className="h-3.5 w-3.5" />
          {formatRelativeTime(
            incident.last_observed_at,
          )}
        </div>

        <ArrowUpRight className="hidden h-4 w-4 text-muted-foreground transition-colors group-hover:text-primary sm:block" />
      </Link>
    </li>
  )
}

function formatRelativeTime(value: string): string {
  const timestamp = Date.parse(value)

  if (Number.isNaN(timestamp)) {
    return value
  }

  const minutes = Math.max(
    0,
    Math.floor((Date.now() - timestamp) / 60_000),
  )

  if (minutes < 60) {
    return `${minutes}m ago`
  }

  const hours = Math.floor(minutes / 60)

  if (hours < 24) {
    return `${hours}h ago`
  }

  return `${Math.floor(hours / 24)}d ago`
}
