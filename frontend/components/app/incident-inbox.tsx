"use client"

import Link from "next/link"
import {
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  CircleDot,
  ExternalLink,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldAlert,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  getIncidentRecord,
  getIncidentRelatedSignals,
  listIncidentRecords,
  updateIncidentRecordStatus,
} from "@/lib/topo-api"
import type {
  IncidentRecordSummary,
  IncidentRecordView,
  IncidentRelatedSignals,
  IncidentStatus,
  SignalSummary,
} from "@/lib/topo-types"
import {
  IncidentOwnershipImpactPanel,
} from "@/components/app/incident-ownership-impact"
import {
  IncidentAiExplanation,
} from "@/components/app/incident-ai-explanation"
import {
  IncidentCopilot,
} from "@/components/app/incident-copilot"
import {
  IncidentInvestigationPlan,
} from "@/components/app/incident-investigation-plan"
import {
  IncidentPostIncidentReport,
} from "@/components/app/incident-post-incident-report"
import { cn } from "@/lib/utils"


const statusStyles: Record<
  IncidentStatus,
  string
> = {
  open:
    "border-info/30 bg-info/10 text-info",
  investigating:
    "border-warn/30 bg-warn/10 text-warn",
  recommended:
    "border-ok/30 bg-ok/10 text-ok",
  remediating:
    "border-warn/30 bg-warn/10 text-warn",
  resolved:
    "border-ok bg-ok/20 text-ok",
  dismissed:
    "border-muted-foreground/30 bg-secondary text-muted-foreground",
}


type IncidentInboxProps = {
  selectedIncidentId: string
  onSelectIncident: (incidentId: string) => void
  onOpenAnalysis: (analysisId: string) => void
}


export function IncidentInbox({
  selectedIncidentId,
  onSelectIncident,
  onOpenAnalysis,
}: IncidentInboxProps) {
  const [incidents, setIncidents] =
    useState<IncidentRecordSummary[]>([])

  const [incident, setIncident] =
    useState<IncidentRecordView | null>(null)

  const [
    relatedSignals,
    setRelatedSignals,
  ] = useState<IncidentRelatedSignals | null>(
    null,
  )

  const [statusFilter, setStatusFilter] =
    useState<IncidentStatus | "">("")

  const [namespace, setNamespace] =
    useState("")

  const [statusNote, setStatusNote] =
    useState("")

  const [loadingList, setLoadingList] =
    useState(false)

  const [loadingDetail, setLoadingDetail] =
    useState(false)

  const [updating, setUpdating] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  async function refreshIncidents() {
    setLoadingList(true)
    setError(null)

    try {
      const results =
        await listIncidentRecords({
          status:
            statusFilter || undefined,
          namespace:
            namespace.trim() ||
            undefined,
          limit: 100,
        })

      setIncidents(results)

      if (
        !selectedIncidentId &&
        results[0]
      ) {
        onSelectIncident(
          results[0].incident_id,
        )
      }
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoadingList(false)
    }
  }


  async function loadIncident(
    incidentId: string,
  ) {
    if (!incidentId) {
      setIncident(null)
      setRelatedSignals(null)
      return
    }

    setLoadingDetail(true)
    setError(null)

    try {
      const [
        incidentResult,
        signalsResult,
      ] = await Promise.all([
        getIncidentRecord(incidentId),
        getIncidentRelatedSignals(
          incidentId,
          { limit: 200 },
        ),
      ])

      setIncident(incidentResult)
      setRelatedSignals(signalsResult)
      setStatusNote(
        incidentResult.status_note ?? "",
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoadingDetail(false)
    }
  }


  useEffect(() => {
    void refreshIncidents()
  }, [])


  useEffect(() => {
    void loadIncident(
      selectedIncidentId,
    )
  }, [selectedIncidentId])


  const selectedSummary =
    useMemo(
      () =>
        incidents.find(
          (item) =>
            item.incident_id ===
            selectedIncidentId,
        ) ?? null,
      [
        incidents,
        selectedIncidentId,
      ],
    )


  async function handleStatusUpdate(
    nextStatus: IncidentStatus,
  ) {
    if (!incident) {
      return
    }

    setUpdating(true)
    setError(null)

    try {
      const updated =
        await updateIncidentRecordStatus(
          incident.incident_id,
          {
            status: nextStatus,
            note:
              statusNote.trim() ||
              null,
          },
        )

      setIncident(updated)
      setStatusNote(
        updated.status_note ?? "",
      )

      await refreshIncidents()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setUpdating(false)
    }
  }


  return (
    <section className="grid min-h-[760px] gap-6 xl:grid-cols-[430px_minmax(0,1fr)]">
      <aside className="overflow-hidden rounded-md border border-border bg-card">
        <header className="border-b border-border px-5 py-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                incident records
              </p>

              <h3 className="mt-1 font-heading text-lg font-bold">
                Incident inbox
              </h3>
            </div>

            <Button
              size="sm"
              variant="outline"
              disabled={loadingList}
              onClick={() =>
                void refreshIncidents()
              }
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

          <div className="mt-4 grid gap-3">
            <input
              value={namespace}
              onChange={(event) =>
                setNamespace(
                  event.target.value,
                )
              }
              placeholder="namespace filter"
              className="h-9 rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            />

            <select
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(
                  event.target
                    .value as IncidentStatus | "",
                )
              }
              className="h-9 rounded-sm border border-input bg-background px-3 font-mono text-xs outline-none focus:border-info"
            >
              <option value="">
                All statuses
              </option>
              <option value="open">
                Open
              </option>
              <option value="investigating">
                Investigating
              </option>
              <option value="recommended">
                Recommended
              </option>
              <option value="remediating">
                Remediating
              </option>
              <option value="resolved">
                Resolved
              </option>
              <option value="dismissed">
                Dismissed
              </option>
            </select>

            <Button
              variant="outline"
              onClick={() =>
                void refreshIncidents()
              }
            >
              Apply filters
            </Button>
          </div>
        </header>

        {loadingList &&
        incidents.length === 0 ? (
          <Loading text="Loading incidents…" />
        ) : incidents.length === 0 ? (
          <Empty text="No incident records found." />
        ) : (
          <div className="max-h-[720px] divide-y divide-border overflow-y-auto">
            {incidents.map((item) => (
              <IncidentRow
                key={item.incident_id}
                incident={item}
                selected={
                  item.incident_id ===
                  selectedIncidentId
                }
                onSelect={() =>
                  onSelectIncident(
                    item.incident_id,
                  )
                }
              />
            ))}
          </div>
        )}
      </aside>

      <main className="overflow-hidden rounded-md border border-border bg-card">
        <header className="border-b border-border px-5 py-4">
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            selected incident
          </p>

          <h3 className="mt-1 font-heading text-lg font-bold">
            {selectedSummary?.title ??
              "Incident detail"}
          </h3>
        </header>

        {error && (
          <div className="m-5 flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

            <p className="font-mono text-xs">
              {error}
            </p>
          </div>
        )}

        {loadingDetail ? (
          <Loading text="Loading incident detail…" />
        ) : incident ? (
          <IncidentDetail
            incident={incident}
            relatedSignals={
              relatedSignals?.signals ?? []
            }
            statusNote={statusNote}
            updating={updating}
            onStatusNoteChange={
              setStatusNote
            }
            onStatusUpdate={(status) =>
              void handleStatusUpdate(
                status,
              )
            }
            onOpenAnalysis={
              onOpenAnalysis
            }
          />
        ) : (
          <Empty text="Select an incident." />
        )}
      </main>
    </section>
  )
}


function IncidentRow({
  incident,
  selected,
  onSelect,
}: {
  incident: IncidentRecordSummary
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full px-4 py-4 text-left transition-colors",
        selected
          ? "bg-info/10"
          : "hover:bg-secondary/40",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <StatusBadge
          status={incident.status}
        />

        <span className="font-mono text-[10px] uppercase text-muted-foreground">
          {incident.severity}
        </span>
      </div>

      <p className="mt-3 line-clamp-2 font-heading text-base font-bold">
        {incident.title}
      </p>

      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        {incident.namespace ?? "cluster"}
        {" · "}
        {incident.affected_object_kind ??
          "object"}
        /
        {incident.affected_object_name ??
          "unknown"}
      </p>

      <p className="mt-2 line-clamp-1 font-mono text-[10px] text-muted-foreground">
        {incident.top_hypothesis_title ??
          "No hypothesis yet"}
      </p>

      <div className="mt-3 flex justify-between gap-3 font-mono text-[10px] text-muted-foreground">
        <span>
          recs {incident.recommendation_count}
        </span>

        <span>
          occurrences {incident.occurrence_count}
        </span>

        <span>
          {formatDate(
            incident.last_observed_at,
          )}
        </span>
      </div>
    </button>
  )
}


function IncidentDetail({
  incident,
  relatedSignals,
  statusNote,
  updating,
  onStatusNoteChange,
  onStatusUpdate,
  onOpenAnalysis,
}: {
  incident: IncidentRecordView
  relatedSignals: SignalSummary[]
  statusNote: string
  updating: boolean
  onStatusNoteChange: (
    value: string,
  ) => void
  onStatusUpdate: (
    status: IncidentStatus,
  ) => void
  onOpenAnalysis: (
    analysisId: string,
  ) => void
}) {
  const topologyUrl =
    incident.topology_snapshot_id &&
    incident.affected_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          incident.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          incident.affected_entity_id,
        )}`
      : null

  return (
    <div className="space-y-6 p-5">
      <section className="rounded-md border border-danger/30 bg-danger/5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge
                status={incident.status}
              />

              <span className="rounded-sm border border-danger/30 bg-danger/10 px-2 py-1 font-mono text-[10px] uppercase text-danger">
                {incident.severity}
              </span>
            </div>

            <h4 className="mt-4 font-heading text-2xl font-bold">
              {incident.title}
            </h4>

            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
              {incident.summary}
            </p>

            <p className="mt-3 font-mono text-[10px] text-muted-foreground">
              {incident.cluster_name}
              {" / "}
              {incident.namespace ?? "cluster"}
              {" · last observed "}
              {formatDate(
                incident.last_observed_at,
              )}
            </p>
          </div>

          {topologyUrl && (
            <Link
              href={topologyUrl}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-sm border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-secondary"
            >
              <Server className="h-4 w-4" />
              Open affected entity
              <ExternalLink className="h-4 w-4" />
            </Link>
          )}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-border bg-border lg:grid-cols-4">
        <Metric
          label="OCCURRENCES"
          value={incident.occurrence_count}
        />

        <Metric
          label="RECOMMENDATIONS"
          value={incident.recommendation_count}
        />

        <Metric
          label="TOP SCORE"
          value={
            incident.top_hypothesis_score === null
              ? "—"
              : `${Math.round(
                  incident.top_hypothesis_score *
                    100,
                )}%`
          }
        />

        <Metric
          label="RECOVERY"
          value={incident.recovery_status ?? "—"}
        />
      </section>
<IncidentOwnershipImpactPanel
  incidentId={incident.incident_id}
/>
<IncidentAiExplanation
  incidentId={incident.incident_id}
/>
<IncidentCopilot
  incidentId={incident.incident_id}
/>
<IncidentInvestigationPlan
  incidentId={incident.incident_id}
/>
<IncidentPostIncidentReport
  incidentId={incident.incident_id}
/>
      <section className="rounded-md border border-border bg-background p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              latest analysis
            </p>

            <h5 className="mt-1 font-heading text-lg font-bold">
              {incident.top_hypothesis_title ??
                "No analysis available"}
            </h5>
          </div>

          {incident.latest_analysis_id && (
<Button
  type="button"
  onClick={(event) => {
    event.preventDefault()
    event.stopPropagation()

    if (incident.latest_analysis_id) {
      onOpenAnalysis(
        incident.latest_analysis_id,
      )
    }
  }}
>
  Open analysis
</Button>
          )}
        </div>
      </section>

      <section className="rounded-md border border-border bg-background p-5">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          related signals
        </p>

        {relatedSignals.length === 0 ? (
          <p className="mt-4 font-mono text-xs text-muted-foreground">
            No related signals found.
          </p>
        ) : (
          <div className="mt-4 divide-y divide-border">
            {relatedSignals.map((signal) => (
              <RelatedSignalRow
                key={signal.signal_id}
                signal={signal}
              />
            ))}
          </div>
        )}
      </section>

      <section className="rounded-md border border-border bg-background p-5">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          lifecycle status
        </p>

        <textarea
          value={statusNote}
          onChange={(event) =>
            onStatusNoteChange(
              event.target.value,
            )
          }
          rows={3}
          placeholder="Add operator note"
          className="mt-3 w-full rounded-sm border border-input bg-background px-3 py-2 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
        />

        <div className="mt-4 flex flex-wrap gap-2">
          <LifecycleButton
            status="investigating"
            updating={updating}
            onStatusUpdate={
              onStatusUpdate
            }
          />

          <LifecycleButton
            status="remediating"
            updating={updating}
            onStatusUpdate={
              onStatusUpdate
            }
          />

          <LifecycleButton
            status="resolved"
            updating={updating}
            onStatusUpdate={
              onStatusUpdate
            }
          />

          <LifecycleButton
            status="dismissed"
            updating={updating}
            onStatusUpdate={
              onStatusUpdate
            }
          />
        </div>
      </section>
    </div>
  )
}


function RelatedSignalRow({
  signal,
}: {
  signal: SignalSummary
}) {
  return (
    <div className="grid gap-3 py-3 md:grid-cols-[120px_minmax(0,1fr)_120px]">
      <span className="font-mono text-[10px] uppercase text-danger">
        {signal.severity}
      </span>

      <div>
        <p className="font-mono text-xs font-semibold">
          {signal.reason ?? signal.title}
        </p>

        <p className="mt-1 text-sm text-muted-foreground">
          {signal.title}
        </p>
      </div>

      <p className="font-mono text-[10px] text-muted-foreground">
        {signal.occurrence_count} occurrences
      </p>
    </div>
  )
}


function LifecycleButton({
  status,
  updating,
  onStatusUpdate,
}: {
  status: IncidentStatus
  updating: boolean
  onStatusUpdate: (
    status: IncidentStatus,
  ) => void
}) {
  return (
    <Button
      variant={
        status === "resolved"
          ? "default"
          : status === "dismissed"
            ? "destructive"
            : "outline"
      }
      disabled={updating}
      onClick={() =>
        onStatusUpdate(status)
      }
    >
      {status}
    </Button>
  )
}


function StatusBadge({
  status,
}: {
  status: IncidentStatus
}) {
  return (
    <span
      className={cn(
        "inline-flex rounded-sm border px-2 py-1 font-mono text-[10px] uppercase",
        statusStyles[status],
      )}
    >
      {status}
    </span>
  )
}


function Metric({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="bg-card px-4 py-3 text-center">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p className="mt-1 truncate font-heading text-2xl font-bold">
        {value}
      </p>
    </div>
  )
}


function Loading({
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


function Empty({
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

  return Number.isNaN(parsed.getTime())
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