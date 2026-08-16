"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import {
  AlertCircle,
  ArrowLeft,
  Clock3,
  RefreshCw,
} from "lucide-react"
import {
  useRouter,
  useSearchParams,
} from "next/navigation"

import { BusinessOverview } from "@/components/app/incident-briefing-business"
import { TechnicalWorkspace } from "@/components/app/incident-briefing-technical"
import { StatusBadge } from "@/components/app/incident-briefing-ui"
import { Button } from "@/components/ui/button"
import {
  formatBriefingDuration,
  humanizeToken,
  incidentElapsedSeconds,
  incidentWorkspaceHref,
  incidentWorkspaceMode,
  isActiveIncident,
  type IncidentWorkspaceMode,
} from "@/lib/incident-briefing"
import { getIncidentBriefing } from "@/lib/topo-api"
import type { IncidentBriefing } from "@/lib/topo-types"
import { cn } from "@/lib/utils"

const INCLUDE_AI =
  process.env.NEXT_PUBLIC_TOPO_BRIEFING_AI ===
  "true"

export function IncidentBriefingWorkspace({
  incidentId,
}: {
  incidentId: string
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const mode = incidentWorkspaceMode(
    searchParams.get("view"),
  )
  const [briefing, setBriefing] =
    useState<IncidentBriefing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] =
    useState<string | null>(null)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    async function loadBriefing() {
      setLoading(true)
      setError(null)

      try {
        const result = await getIncidentBriefing(
          incidentId,
          {
            includeAi: INCLUDE_AI,
            signal: controller.signal,
          },
        )
        setBriefing(result)
      } catch (requestError) {
        if (controller.signal.aborted) {
          return
        }
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to load the incident briefing.",
        )
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadBriefing()
    return () => controller.abort()
  }, [incidentId, retryKey])

  function selectMode(
    nextMode: IncidentWorkspaceMode,
  ) {
    router.replace(
      incidentWorkspaceHref(incidentId, nextMode),
      { scroll: false },
    )
  }

  if (loading && !briefing) {
    return <BriefingSkeleton />
  }

  if (error && !briefing) {
    return (
      <BriefingError
        message={error}
        onRetry={() =>
          setRetryKey((value) => value + 1)
        }
      />
    )
  }

  if (!briefing) {
    return null
  }

  return (
    <main className="mx-auto w-full max-w-[1480px] px-3 py-3 sm:px-5 sm:py-4">
      {error && (
        <div className="mb-4 flex items-start gap-3 rounded-md border border-warn/30 bg-warn/5 p-3 text-warn">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p className="font-mono text-xs">
            Refresh failed; showing the last loaded briefing. {error}
          </p>
        </div>
      )}

      <IncidentHeader
        briefing={briefing}
        mode={mode}
        onSelectMode={selectMode}
      />
      {mode === "technical" ? (
        <TechnicalWorkspace briefing={briefing} />
      ) : (
        <BusinessOverview briefing={briefing} />
      )}
    </main>
  )
}
function ModeButton({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex-1 rounded-sm px-4 py-1.5 text-xs font-semibold transition-colors sm:flex-none",
        active
          ? "bg-primary text-primary-foreground"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground",
      )}
    >
      {label}
    </button>
  )
}

function IncidentHeader({
  briefing,
  mode,
  onSelectMode,
}: {
  briefing: IncidentBriefing
  mode: IncidentWorkspaceMode
  onSelectMode: (
    mode: IncidentWorkspaceMode,
  ) => void
}) {
  const elapsed = formatBriefingDuration(
    briefing.outcome
      ?.time_to_resolution_seconds ??
      incidentElapsedSeconds(briefing),
  )
  const impact =
    briefing.operational_context?.business_impact
  const capability =
    briefing.operational_context
      ?.ownership.business_capability ??
    impact?.business_capabilities[0] ??
    briefing.blast_radius
      ?.business_capabilities[0] ??
    null

  const owner =
    briefing.operational_context?.ownership

  return (
    <header className="rounded-md border border-border bg-background/95 px-3 py-3 shadow-lg shadow-black/10 backdrop-blur sm:px-4 lg:sticky lg:top-16 lg:z-20">
      <div className="grid grid-cols-[32px_minmax(0,1fr)] items-start gap-2 sm:grid-cols-[32px_minmax(0,1fr)_auto] sm:items-center sm:gap-3 xl:grid-cols-[32px_minmax(0,1fr)_auto_auto]">
        <Link
          href="/app"
          aria-label="Back to incidents"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </Link>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              value={briefing.incident.status}
              tone={isActiveIncident(briefing) ? "danger" : "ok"}
            />
            <StatusBadge
              value={briefing.incident.severity}
              tone="danger"
            />
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
              <Clock3 className="h-3 w-3" />
              {elapsed
                ? isActiveIncident(briefing)
                  ? `${elapsed} active`
                  : `${elapsed} duration`
                : "duration unavailable"}
            </span>
          </div>

          <h1 className="mt-1.5 truncate font-heading text-lg font-black tracking-tight sm:text-xl">
            {briefing.incident.title}
          </h1>

          <div className="mt-1 hidden flex-wrap gap-x-4 gap-y-1 font-mono text-[9px] text-muted-foreground sm:flex sm:text-[10px]">
            <span>
              {briefing.incident.environment ?? briefing.incident.cluster_name}
            </span>
            {briefing.incident.namespace && (
              <span>namespace {briefing.incident.namespace}</span>
            )}
            {owner?.resolved && owner.owner_team && (
              <span>{owner.owner_team}</span>
            )}
            {capability && <span>{capability}</span>}
          </div>
        </div>

        <div
          className="col-span-2 row-start-2 inline-flex w-full rounded-md border border-border bg-card p-0.5 sm:col-span-1 sm:col-start-3 sm:row-start-1 sm:w-auto"
          aria-label="Incident workspace view"
        >
          <ModeButton
            label="Technical"
            active={mode === "technical"}
            onClick={() => onSelectMode("technical")}
          />
          <ModeButton
            label="Business"
            active={mode === "business"}
            onClick={() => onSelectMode("business")}
          />
        </div>

        {impact?.highest_criticality && (
          <div className="hidden border-l border-border pl-3 xl:block">
            <p className="font-mono text-[9px] uppercase text-muted-foreground">
              Criticality
            </p>
            <p className="mt-0.5 font-mono text-[10px] uppercase text-warn">
              {humanizeToken(impact.highest_criticality)}
            </p>
          </div>
        )}
      </div>
    </header>
  )
}

function BriefingSkeleton() {
  return (
    <main
      className="mx-auto w-full max-w-[1540px] animate-pulse px-4 py-6 sm:px-5"
      aria-label="Loading incident briefing"
    >
      <div className="h-4 w-32 rounded bg-secondary" />
      <div className="mt-5 rounded-md border border-border bg-card p-6">
        <div className="h-4 w-48 rounded bg-secondary" />
        <div className="mt-4 h-9 max-w-3xl rounded bg-secondary" />
        <div className="mt-4 h-3 max-w-xl rounded bg-secondary" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div className="h-64 rounded-md border border-border bg-card" />
        <div className="h-64 rounded-md border border-border bg-card" />
      </div>
      <div className="mt-6 h-72 rounded-md border border-border bg-card" />
      <p className="sr-only">Loading the unified incident briefing.</p>
    </main>
  )
}

function BriefingError({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <main className="mx-auto flex min-h-[65vh] w-full max-w-3xl items-center px-5 py-10">
      <section className="w-full rounded-md border border-danger/35 bg-danger/5 p-6">
        <AlertCircle className="h-6 w-6 text-danger" />
        <h1 className="mt-4 font-heading text-2xl font-bold">
          Incident briefing unavailable
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {message}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          The incident may not have a causal analysis yet. Generate the core RCA and try again.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button onClick={onRetry}>
            <RefreshCw /> Retry briefing
          </Button>
          <Button asChild variant="outline">
            <Link href="/app">Return to incident inbox</Link>
          </Button>
        </div>
      </section>
    </main>
  )
}
