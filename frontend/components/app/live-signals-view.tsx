"use client"

import Link from "next/link"
import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  Info,
  LoaderCircle,
  RefreshCw,
  Server,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  getSignal,
  listSignals,
} from "@/lib/topo-api"
import type {
  NormalizedSignal,
  SignalCategory,
  SignalSeverity,
  SignalSummary,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"

type SeverityFilter =
  | ""
  | SignalSeverity

type CategoryFilter =
  | ""
  | SignalCategory

const severityStyles: Record<
  SignalSeverity,
  string
> = {
  info:
    "border-info/30 bg-info/10 text-info",
  warning:
    "border-warn/30 bg-warn/10 text-warn",
  error:
    "border-danger/30 bg-danger/10 text-danger",
  critical:
    "border-danger bg-danger/20 text-danger",
}

export function LiveSignalsView() {
  const [signals, setSignals] =
    useState<SignalSummary[]>([])

  const [
    selectedSignalId,
    setSelectedSignalId,
  ] = useState("")

  const [
    selectedSignal,
    setSelectedSignal,
  ] = useState<NormalizedSignal | null>(
    null,
  )

  const [namespace, setNamespace] =
    useState("")

  const [severity, setSeverity] =
    useState<SeverityFilter>("")

  const [category, setCategory] =
    useState<CategoryFilter>("")

  const [loadingList, setLoadingList] =
    useState(true)

  const [
    loadingDetail,
    setLoadingDetail,
  ] = useState(false)

  const [error, setError] =
    useState<string | null>(null)

  async function refreshSignals() {
    setLoadingList(true)
    setError(null)

    try {
      const results = await listSignals({
        namespace:
          namespace.trim() || undefined,
        severity:
          severity || undefined,
        limit: 300,
      })

      setSignals(results)

      const nextId =
        results.some(
          (signal) =>
            signal.signal_id ===
            selectedSignalId,
        )
          ? selectedSignalId
          : results[0]?.signal_id ?? ""

      setSelectedSignalId(nextId)

      if (!nextId) {
        setSelectedSignal(null)
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoadingList(false)
    }
  }

  async function loadSignalDetail(
    signalId: string,
  ) {
    if (!signalId) {
      setSelectedSignal(null)
      return
    }

    setLoadingDetail(true)
    setError(null)

    try {
      const result =
        await getSignal(signalId)

      setSelectedSignal(result)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoadingDetail(false)
    }
  }

  useEffect(() => {
    void refreshSignals()
  }, [])

  useEffect(() => {
    void loadSignalDetail(
      selectedSignalId,
    )
  }, [selectedSignalId])

  const visibleSignals = useMemo(
    () =>
      category
        ? signals.filter(
            (signal) =>
              signal.category === category,
          )
        : signals,
    [signals, category],
  )

  const metrics = useMemo(() => {
    const result = {
      total: visibleSignals.length,
      info: 0,
      warning: 0,
      error: 0,
      critical: 0,
      mapped: 0,
    }

    for (const signal of visibleSignals) {
      result[signal.severity] += 1

      if (signal.involved_entity_id) {
        result.mapped += 1
      }
    }

    return result
  }, [visibleSignals])

  return (
    <div className="mx-auto w-full max-w-[1600px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            persisted operational evidence
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Signals and events
          </h2>

          <p className="mt-2 max-w-3xl leading-relaxed text-muted-foreground">
            Investigate normalized Kubernetes
            events, affected resources, occurrence
            counts and their raw source evidence.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <CheckCircle2 className="h-4 w-4" />
          persisted signals
        </div>
      </header>

      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-[1fr_220px_220px_auto]">
          <label>
            <FieldLabel>
              Namespace
            </FieldLabel>

            <input
              value={namespace}
              onChange={(event) =>
                setNamespace(event.target.value)
              }
              placeholder="All namespaces"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
            />
          </label>

          <label>
            <FieldLabel>
              Severity
            </FieldLabel>

            <select
              value={severity}
              onChange={(event) =>
                setSeverity(
                  event.target
                    .value as SeverityFilter,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                All severities
              </option>
              <option value="info">
                Info
              </option>
              <option value="warning">
                Warning
              </option>
              <option value="error">
                Error
              </option>
              <option value="critical">
                Critical
              </option>
            </select>
          </label>

          <label>
            <FieldLabel>
              Category
            </FieldLabel>

            <select
              value={category}
              onChange={(event) =>
                setCategory(
                  event.target
                    .value as CategoryFilter,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                All categories
              </option>
              <option value="health">
                Health
              </option>
              <option value="image">
                Image
              </option>
              <option value="scheduling">
                Scheduling
              </option>
              <option value="storage">
                Storage
              </option>
              <option value="configuration">
                Configuration
              </option>
              <option value="lifecycle">
                Lifecycle
              </option>
              <option value="availability">
                Availability
              </option>
              <option value="security">
                Security
              </option>
              <option value="other">
                Other
              </option>
            </select>
          </label>

          <Button
            className="self-end"
            onClick={() =>
              void refreshSignals()
            }
            disabled={loadingList}
          >
            <RefreshCw
              className={
                loadingList
                  ? "animate-spin"
                  : ""
              }
            />
            Apply filters
          </Button>
        </div>
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}

      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-6">
        <Metric
          label="TOTAL"
          value={metrics.total}
        />

        <Metric
          label="INFO"
          value={metrics.info}
          className="text-info"
        />

        <Metric
          label="WARNING"
          value={metrics.warning}
          className="text-warn"
        />

        <Metric
          label="ERROR"
          value={metrics.error}
          className="text-danger"
        />

        <Metric
          label="CRITICAL"
          value={metrics.critical}
          className="text-danger"
        />

        <Metric
          label="ENTITY MAPPED"
          value={metrics.mapped}
          className="text-ok"
        />
      </section>

      <div className="grid min-h-[650px] gap-6 xl:grid-cols-[minmax(0,1fr)_430px]">
        <section className="overflow-hidden rounded-md border border-border bg-card">
          <header className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-info" />

              <h3 className="font-heading text-lg font-bold">
                Signal stream
              </h3>
            </div>

            <span className="font-mono text-[11px] text-muted-foreground">
              {visibleSignals.length} records
            </span>
          </header>

          {loadingList ? (
            <LoadingMessage text="Loading signals…" />
          ) : visibleSignals.length === 0 ? (
            <EmptyMessage text="No signals matched the selected filters." />
          ) : (
            <div className="max-h-[760px] divide-y divide-border overflow-y-auto">
              {visibleSignals.map(
                (signal) => (
                  <SignalRow
                    key={signal.signal_id}
                    signal={signal}
                    selected={
                      signal.signal_id ===
                      selectedSignalId
                    }
                    onSelect={() =>
                      setSelectedSignalId(
                        signal.signal_id,
                      )
                    }
                  />
                ),
              )}
            </div>
          )}
        </section>

        <aside className="rounded-md border border-border bg-card">
          <header className="border-b border-border px-5 py-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Signal evidence
            </p>

            <h3 className="mt-1 font-heading text-lg font-bold">
              Event details
            </h3>
          </header>

          {loadingDetail ? (
            <LoadingMessage text="Loading signal detail…" />
          ) : selectedSignal ? (
            <SignalDetail
              signal={selectedSignal}
            />
          ) : (
            <EmptyMessage text="Select a signal to inspect its evidence." />
          )}
        </aside>
      </div>
    </div>
  )
}

function SignalRow({
  signal,
  selected,
  onSelect,
}: {
  signal: SignalSummary
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-3 px-5 py-4 text-left transition-colors md:grid-cols-[110px_minmax(0,1fr)_180px_90px]",
        selected
          ? "bg-info/10"
          : "hover:bg-secondary/40",
      )}
    >
      <div>
        <SeverityBadge
          severity={signal.severity}
        />

        <p className="mt-2 font-mono text-[10px] uppercase text-muted-foreground">
          {signal.category}
        </p>
      </div>

      <div className="min-w-0">
        <p className="truncate font-mono text-xs font-semibold">
          {signal.reason ??
            signal.title}
        </p>

        <p className="mt-1 truncate text-sm text-muted-foreground">
          {signal.title}
        </p>

        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          {signal.namespace ?? "cluster"}
        </p>
      </div>

      <div className="font-mono text-[10px]">
        <p className="text-foreground">
          {signal.involved_object_kind ??
            "Unknown"}
          {signal.involved_object_name
            ? `/${signal.involved_object_name}`
            : ""}
        </p>

        <p className="mt-2 text-muted-foreground">
          {formatDate(
            signal.last_observed_at,
          )}
        </p>
      </div>

      <div className="text-right">
        <p className="font-heading text-xl font-bold">
          {signal.occurrence_count}
        </p>

        <p className="font-mono text-[9px] uppercase text-muted-foreground">
          occurrences
        </p>
      </div>
    </button>
  )
}

function SignalDetail({
  signal,
}: {
  signal: NormalizedSignal
}) {
  const topologyUrl =
    signal.topology_snapshot_id &&
    signal.involved_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          signal.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          signal.involved_entity_id,
        )}`
      : null

  return (
    <div className="space-y-5 p-5">
      <div>
        <SeverityBadge
          severity={signal.severity}
        />

        <h4 className="mt-3 font-heading text-xl font-bold">
          {signal.reason ??
            signal.title}
        </h4>

        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {signal.summary}
        </p>
      </div>

      {topologyUrl && (
        <Button
          asChild
          variant="outline"
          className="w-full"
        >
          <Link href={topologyUrl}>
            <Server />
            Open affected entity
            <ExternalLink />
          </Link>
        </Button>
      )}

      <DetailSection title="Affected object">
        <DetailRow
          label="kind"
          value={
            signal.involved_object_kind
          }
        />

        <DetailRow
          label="name"
          value={
            signal.involved_object_name
          }
        />

        <DetailRow
          label="namespace"
          value={signal.namespace}
        />

        <DetailRow
          label="entity ID"
          value={
            signal.involved_entity_id
          }
        />

        <DetailRow
          label="object UID"
          value={
            signal.involved_object_uid
          }
        />
      </DetailSection>

      <DetailSection title="Observation">
        <DetailRow
          label="first seen"
          value={formatDate(
            signal.first_observed_at,
          )}
        />

        <DetailRow
          label="last seen"
          value={formatDate(
            signal.last_observed_at,
          )}
        />

        <DetailRow
          label="count"
          value={String(
            signal.occurrence_count,
          )}
        />

        <DetailRow
          label="controller"
          value={
            signal.reporting_controller
          }
        />

        <DetailRow
          label="instance"
          value={
            signal.reporting_instance
          }
        />
      </DetailSection>

      <DetailSection title="Normalized attributes">
        <JsonBlock
          value={signal.attributes}
        />
      </DetailSection>

      <DetailSection title="Raw Kubernetes evidence">
        <JsonBlock
          value={signal.raw_payload}
        />
      </DetailSection>
    </div>
  )
}

function SeverityBadge({
  severity,
}: {
  severity: SignalSeverity
}) {
  const Icon =
    severity === "info"
      ? Info
      : severity === "warning"
        ? AlertTriangle
        : severity === "critical"
          ? CircleAlert
          : AlertCircle

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 font-mono text-[10px] uppercase",
        severityStyles[severity],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {severity}
    </span>
  )
}

function DetailSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-border pt-4">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {title}
      </p>

      {children}
    </section>
  )
}

function DetailRow({
  label,
  value,
}: {
  label: string
  value: string | null | undefined
}) {
  return (
    <div className="grid grid-cols-[95px_1fr] gap-3 py-1.5 font-mono text-[10px]">
      <span className="text-muted-foreground">
        {label}
      </span>

      <span className="break-all text-foreground">
        {value || "—"}
      </span>
    </div>
  )
}

function JsonBlock({
  value,
}: {
  value: Record<string, unknown>
}) {
  return (
    <pre className="max-h-72 overflow-auto rounded-sm border border-border bg-background p-3 font-mono text-[10px] leading-relaxed text-muted-foreground">
      {JSON.stringify(
        value,
        null,
        2,
      )}
    </pre>
  )
}

function Metric({
  label,
  value,
  className = "",
}: {
  label: string
  value: number
  className?: string
}) {
  return (
    <div className="bg-card px-4 py-3 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p
        className={`mt-1 font-heading text-2xl font-bold ${className}`}
      >
        {value}
      </p>
    </div>
  )
}

function FieldLabel({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      {children}
    </span>
  )
}

function LoadingMessage({
  text,
}: {
  text: string
}) {
  return (
    <div className="flex items-center gap-2 p-6 font-mono text-xs text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {text}
    </div>
  )
}

function EmptyMessage({
  text,
}: {
  text: string
}) {
  return (
    <div className="p-10 text-center font-mono text-xs text-muted-foreground">
      {text}
    </div>
  )
}

function formatDate(
  value: string,
): string {
  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}