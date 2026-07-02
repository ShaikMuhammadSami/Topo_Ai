"use client"

import Link from "next/link"
import {
  useCallback,
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  FileCheck2,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
  X,
} from "lucide-react"

import {
  Button,
  buttonVariants,
} from "@/components/ui/button"
import {
  generateRecommendations,
  getRecommendation,
  listRecommendations,
  updateRecommendationStatus,
} from "@/lib/topo-api"
import type {
  IncidentAnalysis,
  RecommendationRisk,
  RecommendationStatus,
  RecommendationSummary,
  RemediationRecommendation,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"


const statusStyles: Record<
  RecommendationStatus,
  string
> = {
  proposed:
    "border-info/30 bg-info/10 text-info",
  approved:
    "border-ok/30 bg-ok/10 text-ok",
  applied:
    "border-ok bg-ok/20 text-ok",
  dismissed:
    "border-muted-foreground/30 bg-secondary text-muted-foreground",
}


const riskStyles: Record<
  RecommendationRisk,
  string
> = {
  low:
    "border-ok/30 bg-ok/10 text-ok",
  medium:
    "border-warn/30 bg-warn/10 text-warn",
  high:
    "border-danger/30 bg-danger/10 text-danger",
}


export function IncidentRecommendations({
  analysis,
}: {
  analysis: IncidentAnalysis
}) {
  const [
    summaries,
    setSummaries,
  ] = useState<
    RecommendationSummary[]
  >([])

  const [
    selectedRecommendationId,
    setSelectedRecommendationId,
  ] = useState("")

  const [
    recommendation,
    setRecommendation,
  ] = useState<
    RemediationRecommendation | null
  >(null)

  const [statusNote, setStatusNote] =
    useState("")

  const [loadingList, setLoadingList] =
    useState(true)

  const [
    loadingRecommendation,
    setLoadingRecommendation,
  ] = useState(false)

  const [generating, setGenerating] =
    useState(false)

  const [updating, setUpdating] =
    useState(false)

  const [
    copiedCommand,
    setCopiedCommand,
  ] = useState<string | null>(null)

  const [error, setError] =
    useState<string | null>(null)


  const refreshSummaries = useCallback(
    async (
      preferredRecommendationId?: string,
    ) => {
      setLoadingList(true)
      setError(null)

      try {
        const results =
          await listRecommendations({
            analysisId:
              analysis.analysis_id,
            limit: 50,
          })

        setSummaries(results)

        setSelectedRecommendationId(
          (current) => {
            if (
              preferredRecommendationId &&
              results.some(
                (item) =>
                  item.recommendation_id ===
                  preferredRecommendationId,
              )
            ) {
              return preferredRecommendationId
            }

            if (
              current &&
              results.some(
                (item) =>
                  item.recommendation_id ===
                  current,
              )
            ) {
              return current
            }

            return (
              results[0]
                ?.recommendation_id ?? ""
            )
          },
        )

        if (results.length === 0) {
          setRecommendation(null)
        }
      } catch (requestError) {
        setError(
          errorMessage(requestError),
        )
      } finally {
        setLoadingList(false)
      }
    },
    [analysis.analysis_id],
  )


  useEffect(() => {
    setSelectedRecommendationId("")
    setRecommendation(null)
    setStatusNote("")

    void refreshSummaries()
  }, [refreshSummaries])


  useEffect(() => {
    if (!selectedRecommendationId) {
      setRecommendation(null)
      return
    }

    let cancelled = false

    async function loadSelected() {
      setLoadingRecommendation(true)
      setError(null)

      try {
        const result =
          await getRecommendation(
            selectedRecommendationId,
          )

        if (cancelled) {
          return
        }

        setRecommendation(result)

        setStatusNote(
          result.status_note ?? "",
        )
      } catch (requestError) {
        if (!cancelled) {
          setError(
            errorMessage(requestError),
          )
        }
      } finally {
        if (!cancelled) {
          setLoadingRecommendation(
            false,
          )
        }
      }
    }

    void loadSelected()

    return () => {
      cancelled = true
    }
  }, [selectedRecommendationId])


  async function handleGenerate() {
    setGenerating(true)
    setError(null)

    try {
      const generated =
        await generateRecommendations(
          analysis.analysis_id,
          {
            minimumScore: 0.5,
            maxRecommendations: 3,
          },
        )

      const first =
        generated[0] ?? null

      if (first) {
        setRecommendation(first)

        setSelectedRecommendationId(
          first.recommendation_id,
        )
      }

      await refreshSummaries(
        first?.recommendation_id,
      )
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setGenerating(false)
    }
  }


  async function handleStatusUpdate(
    nextStatus: RecommendationStatus,
  ) {
    if (!recommendation) {
      return
    }

    if (
      nextStatus === "applied"
    ) {
      const confirmed = window.confirm(
        [
          "Mark this recommendation as applied?",
          "",
          "This records that an operator performed the remediation.",
          "Topo AI will not execute any command.",
        ].join("\n"),
      )

      if (!confirmed) {
        return
      }
    }

    setUpdating(true)
    setError(null)

    try {
      const updated =
        await updateRecommendationStatus(
          recommendation
            .recommendation_id,
          {
            status: nextStatus,
            note:
              statusNote.trim() ||
              null,
          },
        )

      setRecommendation(updated)

      setStatusNote(
        updated.status_note ?? "",
      )

      await refreshSummaries(
        updated.recommendation_id,
      )
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setUpdating(false)
    }
  }


  async function handleCopy(
    command: string,
  ) {
    try {
      await navigator.clipboard.writeText(
        command,
      )

      setCopiedCommand(command)

      window.setTimeout(() => {
        setCopiedCommand(
          (current) =>
            current === command
              ? null
              : current,
        )
      }, 2000)
    } catch {
      setError(
        "The command could not be copied to the clipboard.",
      )
    }
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <div className="flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-warn" />

            <h3 className="font-heading text-lg font-bold">
              Remediation recommendations
            </h3>
          </div>

          <p className="mt-1 text-sm text-muted-foreground">
            Review evidence-backed actions.
            Commands remain operator-controlled.
          </p>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={loadingList}
            onClick={() =>
              void refreshSummaries(
                selectedRecommendationId,
              )
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

          <Button
            disabled={generating}
            onClick={() =>
              void handleGenerate()
            }
          >
            {generating ? (
              <LoaderCircle className="animate-spin" />
            ) : (
              <Sparkles />
            )}

            {generating
              ? "Generating"
              : summaries.length
                ? "Regenerate"
                : "Generate"}
          </Button>
        </div>
      </header>


      {error && (
        <div className="m-5 flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      {loadingList &&
      summaries.length === 0 ? (
        <LoadingPanel text="Loading recommendations…" />
      ) : summaries.length === 0 ? (
        <div className="p-10 text-center">
          <FileCheck2 className="mx-auto h-7 w-7 text-muted-foreground" />

          <h4 className="mt-4 font-heading text-lg font-bold">
            No recommendations generated
          </h4>

          <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
            Generate actions from the ranked
            hypotheses. Only candidates meeting
            the configured confidence threshold
            will be included.
          </p>
        </div>
      ) : (
        <div className="grid min-h-[720px] xl:grid-cols-[380px_minmax(0,1fr)]">
          <div className="border-r border-border">
            <div className="border-b border-border px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {summaries.length} recommendations
            </div>

            <div className="divide-y divide-border">
              {summaries.map((item) => (
                <RecommendationRow
                  key={
                    item.recommendation_id
                  }
                  recommendation={item}
                  selected={
                    item.recommendation_id ===
                    selectedRecommendationId
                  }
                  onSelect={() =>
                    setSelectedRecommendationId(
                      item.recommendation_id,
                    )
                  }
                />
              ))}
            </div>
          </div>

          <div>
            {loadingRecommendation ? (
              <LoadingPanel text="Loading recommendation…" />
            ) : recommendation ? (
              <RecommendationDetail
                analysis={analysis}
                recommendation={
                  recommendation
                }
                statusNote={statusNote}
                updating={updating}
                copiedCommand={
                  copiedCommand
                }
                onStatusNoteChange={
                  setStatusNote
                }
                onStatusUpdate={(
                  status,
                ) =>
                  void handleStatusUpdate(
                    status,
                  )
                }
                onCopy={(command) =>
                  void handleCopy(command)
                }
              />
            ) : (
              <div className="p-10 text-center font-mono text-xs text-muted-foreground">
                Select a recommendation.
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}


function RecommendationRow({
  recommendation,
  selected,
  onSelect,
}: {
  recommendation: RecommendationSummary
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
          status={
            recommendation.status
          }
        />

        <span
          className={cn(
            "font-heading text-lg font-bold",
            scoreColor(
              recommendation.confidence,
            ),
          )}
        >
          {Math.round(
            recommendation.confidence *
              100,
          )}
          %
        </span>
      </div>

      <p className="mt-3 font-heading text-base font-bold">
        {recommendation.title}
      </p>

      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        {recommendation.action_type}
      </p>

      <p className="mt-2 font-mono text-[10px] text-muted-foreground">
        {recommendation
          .target_entity_kind ??
          "Resource"}
        /
        {recommendation
          .target_entity_name ??
          "unknown"}
      </p>
    </button>
  )
}


function RecommendationDetail({
  analysis,
  recommendation,
  statusNote,
  updating,
  copiedCommand,
  onStatusNoteChange,
  onStatusUpdate,
  onCopy,
}: {
  analysis: IncidentAnalysis
  recommendation: RemediationRecommendation
  statusNote: string
  updating: boolean
  copiedCommand: string | null
  onStatusNoteChange: (
    value: string,
  ) => void
  onStatusUpdate: (
    status: RecommendationStatus,
  ) => void
  onCopy: (command: string) => void
}) {
  const topologyUrl =
    recommendation.target_entity_id
      ? `/app/topology?snapshot_id=${encodeURIComponent(
          analysis.topology_snapshot_id,
        )}&entity_id=${encodeURIComponent(
          recommendation.target_entity_id,
        )}`
      : null

  return (
    <div className="space-y-6 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge
              status={
                recommendation.status
              }
            />

            <RiskBadge
              risk={recommendation.risk}
            />
          </div>

          <h4 className="mt-4 font-heading text-2xl font-bold">
            {recommendation.title}
          </h4>

          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            {recommendation.rationale}
          </p>
        </div>

        <div
          className={cn(
            "font-heading text-4xl font-black",
            scoreColor(
              recommendation.confidence,
            ),
          )}
        >
          {Math.round(
            recommendation.confidence *
              100,
          )}
          %
        </div>
      </div>


      <div className="rounded-md border border-warn/30 bg-warn/5 p-4">
        <div className="flex items-start gap-3">
          <TerminalSquare className="mt-0.5 h-4 w-4 shrink-0 text-warn" />

          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-warn">
              Operator-controlled commands
            </p>

            <p className="mt-2 text-sm text-muted-foreground">
              Topo AI has generated command
              previews only. No command has been
              executed.
            </p>
          </div>
        </div>
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
          Open target entity
          <ExternalLink />
        </Link>
      )}


      <DetailSection title="Target">
        <DetailRow
          label="action"
          value={
            recommendation.action_type
          }
        />

        <DetailRow
          label="cluster"
          value={
            recommendation.cluster_name
          }
        />

        <DetailRow
          label="namespace"
          value={
            recommendation.namespace
          }
        />

        <DetailRow
          label="resource"
          value={[
            recommendation
              .target_entity_kind,
            recommendation
              .target_entity_name,
          ]
            .filter(Boolean)
            .join("/")}
        />

        <DetailRow
          label="approval"
          value={
            recommendation
              .requires_approval
              ? "Required"
              : "Not required"
          }
        />

        <DetailRow
          label="applied"
          value={
            recommendation.applied_at
              ? formatDate(
                  recommendation
                    .applied_at,
                )
              : null
          }
        />
      </DetailSection>


      <DetailSection title="Recommended steps">
        <div className="space-y-4">
          {recommendation.steps.map(
            (step) => (
              <article
                key={step.order}
                className="rounded-md border border-border bg-background p-4"
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border font-mono text-xs font-bold">
                    {step.order}
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h5 className="font-heading font-bold">
                        {step.title}
                      </h5>

                      {step.requires_approval && (
                        <span className="rounded-sm border border-warn/30 bg-warn/10 px-2 py-0.5 font-mono text-[9px] uppercase text-warn">
                          approval required
                        </span>
                      )}
                    </div>

                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {step.description}
                    </p>

                    {step.command && (
                      <div className="mt-3 overflow-hidden rounded-sm border border-border">
                        <div className="flex items-center justify-between gap-3 border-b border-border bg-secondary/40 px-3 py-2">
                          <span className="font-mono text-[9px] uppercase text-muted-foreground">
                            command preview
                          </span>

                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              onCopy(
                                step.command!,
                              )
                            }
                          >
                            {copiedCommand ===
                            step.command ? (
                              <Check />
                            ) : (
                              <Clipboard />
                            )}

                            {copiedCommand ===
                            step.command
                              ? "Copied"
                              : "Copy"}
                          </Button>
                        </div>

                        <pre className="overflow-x-auto p-3 font-mono text-xs text-foreground">
                          {step.command}
                        </pre>
                      </div>
                    )}

                    {step.expected_result && (
                      <p className="mt-3 font-mono text-[10px] text-ok">
                        Expected:{" "}
                        {
                          step.expected_result
                        }
                      </p>
                    )}
                  </div>
                </div>
              </article>
            ),
          )}
        </div>
      </DetailSection>


      <DetailSection title="Expected outcome">
        <p className="text-sm leading-relaxed text-foreground">
          {recommendation.expected_outcome}
        </p>
      </DetailSection>


      <DetailSection title="Verification checks">
        <Checklist
          items={
            recommendation
              .verification_checks
          }
          tone="ok"
        />
      </DetailSection>


      <DetailSection title="Safety notes">
        <Checklist
          items={
            recommendation.safety_notes
          }
          tone="warn"
        />
      </DetailSection>


      <DetailSection title="Recommendation evidence">
        <DetailRow
          label="analysis"
          value={
            recommendation.analysis_id
          }
        />

        <DetailRow
          label="hypothesis"
          value={
            recommendation.hypothesis_id
          }
        />

        <DetailRow
          label="change"
          value={
            recommendation.change_id
          }
        />

        <DetailRow
          label="evidence"
          value={`${recommendation.evidence_ids.length} records`}
        />

        <pre className="mt-3 max-h-72 overflow-auto rounded-sm border border-border bg-background p-3 font-mono text-[10px] leading-relaxed text-muted-foreground">
          {JSON.stringify(
            recommendation.attributes,
            null,
            2,
          )}
        </pre>
      </DetailSection>


      <DetailSection title="Operator decision">
        <label>
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Status note
          </span>

          <textarea
            value={statusNote}
            onChange={(event) =>
              onStatusNoteChange(
                event.target.value,
              )
            }
            rows={3}
            placeholder="Record the review, approval or execution details"
            className="mt-2 w-full rounded-sm border border-input bg-background px-3 py-2 font-mono text-xs outline-none placeholder:text-muted-foreground focus:border-info"
          />
        </label>

        <StatusActions
          status={recommendation.status}
          updating={updating}
          onStatusUpdate={
            onStatusUpdate
          }
        />
      </DetailSection>
    </div>
  )
}


function StatusActions({
  status,
  updating,
  onStatusUpdate,
}: {
  status: RecommendationStatus
  updating: boolean
  onStatusUpdate: (
    status: RecommendationStatus,
  ) => void
}) {
  if (status === "applied") {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-md border border-ok/30 bg-ok/10 p-4 text-ok">
        <CheckCircle2 className="h-4 w-4" />

        <p className="text-sm font-medium">
          Recommendation marked as applied
        </p>
      </div>
    )
  }

  if (status === "dismissed") {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-md border border-border bg-secondary/40 p-4 text-muted-foreground">
        <X className="h-4 w-4" />

        <p className="text-sm font-medium">
          Recommendation dismissed
        </p>
      </div>
    )
  }

  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {status === "proposed" && (
        <Button
          disabled={updating}
          onClick={() =>
            onStatusUpdate("approved")
          }
        >
          {updating ? (
            <LoaderCircle className="animate-spin" />
          ) : (
            <Check />
          )}

          Approve
        </Button>
      )}

      {status === "approved" && (
        <Button
          disabled={updating}
          onClick={() =>
            onStatusUpdate("applied")
          }
        >
          {updating ? (
            <LoaderCircle className="animate-spin" />
          ) : (
            <CheckCircle2 />
          )}

          Mark as applied
        </Button>
      )}

      <Button
        variant="destructive"
        disabled={updating}
        onClick={() =>
          onStatusUpdate("dismissed")
        }
      >
        <X />
        Dismiss
      </Button>
    </div>
  )
}


function StatusBadge({
  status,
}: {
  status: RecommendationStatus
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


function RiskBadge({
  risk,
}: {
  risk: RecommendationRisk
}) {
  return (
    <span
      className={cn(
        "inline-flex rounded-sm border px-2 py-1 font-mono text-[10px] uppercase",
        riskStyles[risk],
      )}
    >
      {risk} risk
    </span>
  )
}


function Checklist({
  items,
  tone,
}: {
  items: string[]
  tone: "ok" | "warn"
}) {
  return (
    <ul className="space-y-2">
      {items.map((item, index) => (
        <li
          key={`${item}-${index}`}
          className="flex items-start gap-2 text-sm"
        >
          <span
            className={
              tone === "ok"
                ? "mt-1 text-ok"
                : "mt-1 text-warn"
            }
          >
            •
          </span>

          <span className="leading-relaxed text-muted-foreground">
            {item}
          </span>
        </li>
      ))}
    </ul>
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
    <section className="border-t border-border pt-5">
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
    <div className="grid grid-cols-[100px_1fr] gap-3 py-1.5 font-mono text-[10px]">
      <span className="text-muted-foreground">
        {label}
      </span>

      <span className="break-all text-foreground">
        {value || "—"}
      </span>
    </div>
  )
}


function LoadingPanel({
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


function scoreColor(
  score: number,
): string {
  if (score >= 0.8) {
    return "text-ok"
  }

  if (score >= 0.6) {
    return "text-warn"
  }

  return "text-muted-foreground"
}


function formatDate(
  value: string,
): string {
  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}