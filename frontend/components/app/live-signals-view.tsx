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
  ArrowRightLeft,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  FileDiff,
  Info,
  LoaderCircle,
  RefreshCw,
  Server,
} from "lucide-react"

import {
  Button,
  buttonVariants,
} from "@/components/ui/button"
import {
  getChange,
  getSignal,
  listChanges,
  listSignals,
} from "@/lib/topo-api"
import type {
  ChangeImportance,
  ChangeSummary,
  NormalizedChange,
  NormalizedSignal,
  SignalSeverity,
  SignalSummary,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"


type SourceFilter =
  | "all"
  | "signals"
  | "changes"

type PriorityFilter =
  | ""
  | SignalSeverity
  | ChangeImportance

type TimelineSelection = {
  kind: "signal" | "change"
  id: string
}

type TimelineItem =
  | {
      kind: "signal"
      id: string
      occurredAt: string
      namespace: string | null
      category: string
      priority: SignalSeverity
      title: string
      summary: string
      objectLabel: string
      signal: SignalSummary
    }
  | {
      kind: "change"
      id: string
      occurredAt: string
      namespace: string | null
      category: string
      priority: ChangeImportance
      title: string
      summary: string
      objectLabel: string
      change: ChangeSummary
    }


const signalStyles: Record<
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

const changeStyles: Record<
  ChangeImportance,
  string
> = {
  low:
    "border-muted-foreground/30 bg-secondary text-muted-foreground",
  medium:
    "border-warn/30 bg-warn/10 text-warn",
  high:
    "border-danger/30 bg-danger/10 text-danger",
}


export function LiveSignalsView() {
  const [signals, setSignals] =
    useState<SignalSummary[]>([])

  const [changes, setChanges] =
    useState<ChangeSummary[]>([])

  const [selection, setSelection] =
    useState<TimelineSelection | null>(
      null,
    )

  const [signalDetail, setSignalDetail] =
    useState<NormalizedSignal | null>(
      null,
    )

  const [changeDetail, setChangeDetail] =
    useState<NormalizedChange | null>(
      null,
    )

  const [namespace, setNamespace] =
    useState("")

  const [source, setSource] =
    useState<SourceFilter>("all")

  const [priority, setPriority] =
    useState<PriorityFilter>("")

  const [category, setCategory] =
    useState("")

  const [loadingList, setLoadingList] =
    useState(true)

  const [
    loadingDetail,
    setLoadingDetail,
  ] = useState(false)

  const [error, setError] =
    useState<string | null>(null)


  async function refreshTimeline() {
    setLoadingList(true)
    setError(null)

    try {
      const namespaceFilter =
        namespace.trim() || undefined

      const [
        signalResults,
        changeResults,
      ] = await Promise.all([
        listSignals({
          namespace: namespaceFilter,
          limit: 300,
        }),
        listChanges({
          namespace: namespaceFilter,
          limit: 300,
        }),
      ])

      setSignals(signalResults)
      setChanges(changeResults)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoadingList(false)
    }
  }


  useEffect(() => {
    void refreshTimeline()
  }, [])


  const timeline = useMemo(
    () =>
      buildTimeline(
        signals,
        changes,
      )
        .filter((item) => {
          if (
            source === "signals" &&
            item.kind !== "signal"
          ) {
            return false
          }

          if (
            source === "changes" &&
            item.kind !== "change"
          ) {
            return false
          }

          if (
            priority &&
            item.priority !== priority
          ) {
            return false
          }

          if (
            category &&
            item.category !== category
          ) {
            return false
          }

          return true
        })
        .sort(
          (first, second) =>
            Date.parse(
              second.occurredAt,
            ) -
            Date.parse(
              first.occurredAt,
            ),
        ),
    [
      signals,
      changes,
      source,
      priority,
      category,
    ],
  )


  useEffect(() => {
    if (timeline.length === 0) {
      setSelection(null)
      setSignalDetail(null)
      setChangeDetail(null)
      return
    }

    const selectionStillExists =
      selection &&
      timeline.some(
        (item) =>
          item.id === selection.id &&
          item.kind === selection.kind,
      )

    if (!selectionStillExists) {
      setSelection({
        kind: timeline[0].kind,
        id: timeline[0].id,
      })
    }
  }, [timeline, selection])


  useEffect(() => {
    async function loadDetail() {
      if (!selection) {
        return
      }

      setLoadingDetail(true)
      setError(null)

      try {
        if (
          selection.kind === "signal"
        ) {
          const result =
            await getSignal(
              selection.id,
            )

          setSignalDetail(result)
          setChangeDetail(null)
        } else {
          const result =
            await getChange(
              selection.id,
            )

          setChangeDetail(result)
          setSignalDetail(null)
        }
      } catch (requestError) {
        setError(
          errorMessage(requestError),
        )
      } finally {
        setLoadingDetail(false)
      }
    }

    void loadDetail()
  }, [selection])


  const metrics = useMemo(
    () => ({
      total: timeline.length,
      signals: timeline.filter(
        (item) =>
          item.kind === "signal",
      ).length,
      changes: timeline.filter(
        (item) =>
          item.kind === "change",
      ).length,
      failures: timeline.filter(
        (item) =>
          item.kind === "signal" &&
          (
            item.priority === "error" ||
            item.priority === "critical"
          ),
      ).length,
      highChanges: timeline.filter(
        (item) =>
          item.kind === "change" &&
          item.priority === "high",
      ).length,
    }),
    [timeline],
  )


  return (
    <div className="mx-auto w-full max-w-[1700px] space-y-6 p-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
            operational evidence timeline
          </p>

          <h2 className="font-heading text-4xl font-black tracking-tight">
            Signals and changes
          </h2>

          <p className="mt-2 max-w-3xl leading-relaxed text-muted-foreground">
            Correlate infrastructure changes with
            Kubernetes failures and lifecycle
            events in chronological order.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-sm border border-ok/30 bg-ok/10 px-3 py-2 font-mono text-xs text-ok">
          <CheckCircle2 className="h-4 w-4" />
          persisted evidence
        </div>
      </header>


      <section className="rounded-md border border-border bg-card p-5">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-[1fr_180px_180px_220px_auto]">
          <label>
            <FieldLabel>
              Namespace
            </FieldLabel>

            <input
              value={namespace}
              onChange={(event) =>
                setNamespace(
                  event.target.value,
                )
              }
              placeholder="All namespaces"
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
            />
          </label>

          <label>
            <FieldLabel>
              Source
            </FieldLabel>

            <select
              value={source}
              onChange={(event) =>
                setSource(
                  event.target
                    .value as SourceFilter,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="all">
                All
              </option>

              <option value="signals">
                Signals
              </option>

              <option value="changes">
                Changes
              </option>
            </select>
          </label>

          <label>
            <FieldLabel>
              Priority
            </FieldLabel>

            <select
              value={priority}
              onChange={(event) =>
                setPriority(
                  event.target
                    .value as PriorityFilter,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                All priorities
              </option>

              <optgroup label="Signals">
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
              </optgroup>

              <optgroup label="Changes">
                <option value="low">
                  Low
                </option>

                <option value="medium">
                  Medium
                </option>

                <option value="high">
                  High
                </option>
              </optgroup>
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
                  event.target.value,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                All categories
              </option>

              <optgroup label="Failure signals">
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

                <option value="availability">
                  Availability
                </option>
              </optgroup>

              <optgroup label="Changes">
                <option value="deployment">
                  Deployment
                </option>

                <option value="scaling">
                  Scaling
                </option>

                <option value="configuration">
                  Configuration
                </option>

                <option value="runtime">
                  Runtime
                </option>

                <option value="service">
                  Service
                </option>

                <option value="topology">
                  Topology
                </option>
              </optgroup>
            </select>
          </label>

          <Button
            className="self-end"
            onClick={() =>
              void refreshTimeline()
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

            Refresh
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


      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-5">
        <Metric
          label="TIMELINE"
          value={metrics.total}
        />

        <Metric
          label="SIGNALS"
          value={metrics.signals}
          className="text-info"
        />

        <Metric
          label="CHANGES"
          value={metrics.changes}
          className="text-warn"
        />

        <Metric
          label="FAILURES"
          value={metrics.failures}
          className="text-danger"
        />

        <Metric
          label="HIGH CHANGES"
          value={metrics.highChanges}
          className="text-danger"
        />
      </section>


      <div className="grid min-h-[700px] gap-6 xl:grid-cols-[minmax(0,1fr)_470px]">
        <section className="overflow-hidden rounded-md border border-border bg-card">
          <header className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-info" />

              <h3 className="font-heading text-lg font-bold">
                Operational timeline
              </h3>
            </div>

            <span className="font-mono text-[11px] text-muted-foreground">
              {timeline.length} records
            </span>
          </header>

          {loadingList ? (
            <LoadingMessage text="Loading operational evidence…" />
          ) : timeline.length === 0 ? (
            <EmptyMessage text="No signals or changes matched the selected filters." />
          ) : (
            <div className="max-h-[820px] divide-y divide-border overflow-y-auto">
              {timeline.map((item) => (
                <TimelineRow
                  key={`${item.kind}:${item.id}`}
                  item={item}
                  selected={
                    selection?.kind ===
                      item.kind &&
                    selection.id === item.id
                  }
                  onSelect={() =>
                    setSelection({
                      kind: item.kind,
                      id: item.id,
                    })
                  }
                />
              ))}
            </div>
          )}
        </section>


        <aside className="rounded-md border border-border bg-card">
          <header className="border-b border-border px-5 py-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Evidence detail
            </p>

            <h3 className="mt-1 font-heading text-lg font-bold">
              Selected record
            </h3>
          </header>

          {loadingDetail ? (
            <LoadingMessage text="Loading detail…" />
          ) : signalDetail ? (
            <SignalDetail
              signal={signalDetail}
            />
          ) : changeDetail ? (
            <ChangeDetail
              change={changeDetail}
            />
          ) : (
            <EmptyMessage text="Select a timeline record." />
          )}
        </aside>
      </div>
    </div>
  )
}


function buildTimeline(
  signals: SignalSummary[],
  changes: ChangeSummary[],
): TimelineItem[] {
  const signalItems: TimelineItem[] =
    signals.map((signal) => ({
      kind: "signal",
      id: signal.signal_id,
      occurredAt:
        signal.last_observed_at,
      namespace: signal.namespace,
      category: signal.category,
      priority: signal.severity,
      title:
        signal.reason ??
        signal.title,
      summary: signal.title,
      objectLabel: [
        signal.involved_object_kind,
        signal.involved_object_name,
      ]
        .filter(Boolean)
        .join("/"),
      signal,
    }))

  const changeItems: TimelineItem[] =
    changes.map((change) => ({
      kind: "change",
      id: change.change_id,
      occurredAt: change.detected_at,
      namespace: change.namespace,
      category: change.category,
      priority: change.importance,
      title: change.title,
      summary: change.summary,
      objectLabel: [
        change.entity_kind,
        change.entity_name,
      ]
        .filter(Boolean)
        .join("/"),
      change,
    }))

  return [
    ...signalItems,
    ...changeItems,
  ]
}


function TimelineRow({
  item,
  selected,
  onSelect,
}: {
  item: TimelineItem
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "grid w-full gap-3 px-5 py-4 text-left transition-colors md:grid-cols-[120px_minmax(0,1fr)_220px_150px]",
        selected
          ? "bg-info/10"
          : "hover:bg-secondary/40",
      )}
    >
      <div>
        {item.kind === "signal" ? (
          <SignalBadge
            severity={item.priority}
          />
        ) : (
          <ChangeBadge
            importance={item.priority}
          />
        )}

        <p className="mt-2 font-mono text-[9px] uppercase text-muted-foreground">
          {item.kind}
          {" · "}
          {item.category}
        </p>
      </div>

      <div className="min-w-0">
        <p className="truncate font-mono text-xs font-semibold">
          {item.title}
        </p>

        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
          {item.summary}
        </p>

        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          {item.namespace ?? "cluster"}
        </p>
      </div>

      <div className="font-mono text-[10px]">
        <p className="break-all text-foreground">
          {item.objectLabel || "Topology relationship"}
        </p>

        <p className="mt-2 text-muted-foreground">
          {formatDate(item.occurredAt)}
        </p>
      </div>

      <div className="text-right">
        {item.kind === "signal" ? (
          <>
            <p className="font-heading text-xl font-bold">
              {
                item.signal
                  .occurrence_count
              }
            </p>

            <p className="font-mono text-[9px] uppercase text-muted-foreground">
              occurrences
            </p>
          </>
        ) : (
          <>
            <FileDiff className="ml-auto h-5 w-5 text-warn" />

            <p className="mt-2 font-mono text-[9px] uppercase text-muted-foreground">
              {item.change.change_type}
            </p>
          </>
        )}
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
      <SignalBadge
        severity={signal.severity}
      />

      <div>
        <h4 className="font-heading text-xl font-bold">
          {signal.reason ??
            signal.title}
        </h4>

        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {signal.summary}
        </p>
      </div>

      {topologyUrl && (
        <Link
          href={topologyUrl}
          className={cn(
            buttonVariants({
              variant: "outline",
            }),
            "w-full",
          )}
        >
          <Server />
          Open affected entity
          <ExternalLink />
        </Link>
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
          label="snapshot"
          value={
            signal.topology_snapshot_id
          }
        />

        <DetailRow
          label="entity ID"
          value={
            signal.involved_entity_id
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
      </DetailSection>

      <DetailSection title="Raw evidence">
        <JsonBlock
          value={signal.raw_payload}
        />
      </DetailSection>
    </div>
  )
}


function ChangeDetail({
  change,
}: {
  change: NormalizedChange
}) {
  const affectedEntityId =
    change.entity_id ??
    change.source_entity_id ??
    change.target_entity_id

  const topologyUrl =
    affectedEntityId
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          change.to_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          affectedEntityId,
        )}`
      : null

  return (
    <div className="space-y-5 p-5">
      <ChangeBadge
        importance={change.importance}
      />

      <div>
        <h4 className="font-heading text-xl font-bold">
          {change.title}
        </h4>

        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {change.summary}
        </p>
      </div>

      {topologyUrl && (
        <Link
          href={topologyUrl}
          className={cn(
            buttonVariants({
              variant: "outline",
            }),
            "w-full",
          )}
        >
          <Server />
          Open changed entity
          <ExternalLink />
        </Link>
      )}

      <DetailSection title="Change">
        <DetailRow
          label="type"
          value={change.change_type}
        />

        <DetailRow
          label="category"
          value={change.category}
        />

        <DetailRow
          label="detected"
          value={formatDate(
            change.detected_at,
          )}
        />

        <DetailRow
          label="entity"
          value={
            change.entity_name
              ? `${change.entity_kind}/${change.entity_name}`
              : null
          }
        />

        <DetailRow
          label="relationship"
          value={
            change.relationship_type
          }
        />
      </DetailSection>

      <DetailSection title="Snapshot transition">
        <DetailRow
          label="from"
          value={
            change.from_snapshot_id
          }
        />

        <DetailRow
          label="to"
          value={
            change.to_snapshot_id
          }
        />
      </DetailSection>

      <DetailSection title="Changed fields">
        <JsonBlock
          value={change.changed_fields}
        />
      </DetailSection>

      <DetailSection title="Before">
        <JsonBlock
          value={change.before ?? {}}
        />
      </DetailSection>

      <DetailSection title="After">
        <JsonBlock
          value={change.after ?? {}}
        />
      </DetailSection>
    </div>
  )
}


function SignalBadge({
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
        signalStyles[severity],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {severity}
    </span>
  )
}


function ChangeBadge({
  importance,
}: {
  importance: ChangeImportance
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 font-mono text-[10px] uppercase",
        changeStyles[importance],
      )}
    >
      <ArrowRightLeft className="h-3.5 w-3.5" />
      {importance}
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
    <div className="grid grid-cols-[90px_1fr] gap-3 py-1.5 font-mono text-[10px]">
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

  return Number.isNaN(
    parsed.getTime(),
  )
    ? value
    : parsed.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}