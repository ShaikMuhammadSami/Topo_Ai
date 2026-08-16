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
    <main className="mx-auto w-full max-w-[1540px] px-4 py-5 sm:px-5 lg:py-7">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/app"
          className="inline-flex items-center gap-2 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Incident inbox
        </Link>

        <div
          className="inline-flex rounded-md border border-border bg-card p-1"
          aria-label="Incident workspace view"
        >
          <ModeButton
            label="Technical"
            active={mode === "technical"}
            onClick={() => selectMode("technical")}
          />
          <ModeButton
            label="Business"
            active={mode === "business"}
            onClick={() => selectMode("business")}
          />
        </div>
      </div>

      {error && (
        <div className="mb-4 flex items-start gap-3 rounded-md border border-warn/30 bg-warn/5 p-3 text-warn">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <p className="font-mono text-xs">
            Refresh failed; showing the last loaded briefing. {error}
          </p>
        </div>
      )}

      <IncidentHeader briefing={briefing} />
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
        "rounded-sm px-4 py-1.5 text-xs font-semibold transition-colors",
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
}: {
  briefing: IncidentBriefing
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

  return (
    <header className="border-y border-border bg-card/60 px-4 py-5 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-5">
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
            {impact && (
              <StatusBadge
                value={`${impact.business_impact_level} business impact`}
                tone="warn"
              />
            )}
          </div>

          <h1 className="mt-3 max-w-5xl font-heading text-2xl font-black tracking-tight sm:text-3xl">
            {briefing.incident.title}
          </h1>

          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 font-mono text-[11px] text-muted-foreground">
            <span>
              {briefing.incident.environment ?? briefing.incident.cluster_name}
            </span>
            {briefing.incident.namespace && (
              <span>namespace {briefing.incident.namespace}</span>
            )}
            <span>
              first observed {formatDateTime(briefing.incident.first_observed_at)}
            </span>
            {elapsed && (
              <span className="inline-flex items-center gap-1.5">
                <Clock3 className="h-3.5 w-3.5" />
                {isActiveIncident(briefing)
                  ? `active for ${elapsed}`
                  : `duration ${elapsed}`}
              </span>
            )}
          </div>
        </div>

        {capability && (
          <div className="min-w-[220px] border-l-2 border-primary pl-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Primary capability
            </p>
            <p className="mt-1 font-heading text-lg font-bold">
              {capability}
            </p>
            {impact?.highest_criticality && (
              <p className="mt-1 font-mono text-[10px] uppercase text-warn">
                {humanizeToken(impact.highest_criticality)}
              </p>
            )}
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

function formatDateTime(value: string): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  })
}
