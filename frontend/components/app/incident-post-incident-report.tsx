"use client"

import type {
  ReactNode,
} from "react"
import {
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileText,
  LoaderCircle,
  RefreshCw,
  Save,
  ShieldCheck,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"
import {
  downloadApiFile,
  generatePostIncidentReport,
  getPostIncidentReport,
  listPostIncidentReports,
  updatePostIncidentReport,
  updateReportActionItem,
} from "@/lib/topo-api"
import type {
  PostIncidentReportDetail,
  PostIncidentReportStatus,
  PostIncidentReportSummary,
  ReportActionStatus,
} from "@/lib/topo-types"


type ActionDraft = {
  status: ReportActionStatus
  ownerTeam: string
  ownerContact: string
  dueDate: string
  notes: string
}


export function IncidentPostIncidentReport({
  incidentId,
}: {
  incidentId: string
}) {
  const [reports, setReports] =
    useState<
      PostIncidentReportSummary[]
    >([])

  const [selectedReportId, setSelectedReportId] =
    useState("")

  const [report, setReport] =
    useState<
      PostIncidentReportDetail | null
    >(null)

  const [reviewStatus, setReviewStatus] =
    useState<PostIncidentReportStatus>(
      "draft",
    )

  const [reviewerName, setReviewerName] =
    useState("")

  const [reviewNotes, setReviewNotes] =
    useState("")

  const [actionDrafts, setActionDrafts] =
    useState<
      Record<string, ActionDraft>
    >({})

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  useEffect(() => {
    if (!incidentId) {
      setReports([])
      setReport(null)
      setSelectedReportId("")
      return
    }

    let cancelled = false

    async function loadReports() {
      setLoading(true)
      setError(null)

      try {
        const values =
          await listPostIncidentReports(
            incidentId,
          )

        if (cancelled) {
          return
        }

        setReports(values)

        const latestId =
          values[0]?.report_id ?? ""

        setSelectedReportId(latestId)

        if (!latestId) {
          setReport(null)
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            errorMessage(requestError),
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadReports()

    return () => {
      cancelled = true
    }
  }, [incidentId])


  useEffect(() => {
    if (!selectedReportId) {
      return
    }

    let cancelled = false

    async function loadReport() {
      setLoading(true)
      setError(null)

      try {
        const value =
          await getPostIncidentReport(
            incidentId,
            selectedReportId,
          )

        if (!cancelled) {
          applyReport(value)
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(
            errorMessage(requestError),
          )
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadReport()

    return () => {
      cancelled = true
    }
  }, [
    incidentId,
    selectedReportId,
  ])


  function applyReport(
    value: PostIncidentReportDetail,
  ) {
    setReport(value)

    setReviewStatus(value.status)

    setReviewerName(
      value.reviewer_name ?? "",
    )

    setReviewNotes(
      value.review_notes ?? "",
    )

    setActionDrafts(
      Object.fromEntries(
        value.action_items.map(
          (action) => [
            action.action_item_id,
            {
              status: action.status,
              ownerTeam:
                action.owner_team ?? "",
              ownerContact:
                action.owner_contact ?? "",
              dueDate:
                action.due_date ?? "",
              notes:
                action.notes ?? "",
            },
          ],
        ),
      ),
    )
  }


  async function refreshList() {
    const values =
      await listPostIncidentReports(
        incidentId,
      )

    setReports(values)
  }


  async function handleGenerate() {
    setLoading(true)
    setError(null)

    try {
      const generated =
        await generatePostIncidentReport(
          incidentId,
          {
            provider: "auto",
            forceRegenerate:
              Boolean(report),
          },
        )

      await refreshList()

      setSelectedReportId(
        generated.report_id,
      )

      applyReport(generated)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  async function handleSaveReview() {
    if (!report) {
      return
    }

    if (
      reviewStatus === "approved"
      && !reviewerName.trim()
    ) {
      setError(
        "A reviewer name is required "
        + "before approval.",
      )
      return
    }

    setLoading(true)
    setError(null)

    try {
      const updated =
        await updatePostIncidentReport(
          incidentId,
          report.report_id,
          {
            status: reviewStatus,
            reviewer_name:
              reviewerName.trim()
              || null,
            review_notes:
              reviewNotes.trim()
              || null,
          },
        )

      applyReport(updated)
      await refreshList()
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  function updateActionDraft(
    actionItemId: string,
    update: Partial<ActionDraft>,
  ) {
    setActionDrafts(
      (current) => ({
        ...current,
        [actionItemId]: {
          ...current[actionItemId],
          ...update,
        },
      }),
    )
  }


  async function saveAction(
    actionItemId: string,
  ) {
    if (!report) {
      return
    }

    const draft =
      actionDrafts[actionItemId]

    if (!draft) {
      return
    }

    setLoading(true)
    setError(null)

    try {
      const updated =
        await updateReportActionItem(
          incidentId,
          report.report_id,
          actionItemId,
          {
            status: draft.status,
            owner_team:
              draft.ownerTeam.trim()
              || null,
            owner_contact:
              draft.ownerContact.trim()
              || null,
            due_date:
              draft.dueDate.trim()
              || null,
            notes:
              draft.notes.trim()
              || null,
          },
        )

      applyReport(updated)
      await refreshList()
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  function exportUrl(
    format: "markdown" | "json",
  ): string {
    if (!report) {
      return "#"
    }

    return (
      `/api/v1/incidents/${encodeURIComponent(
        incidentId,
      )}/reports/${encodeURIComponent(
        report.report_id,
      )}/export?format=${format}`
    )
  }

  async function exportReport(format: "markdown" | "json") {
    if (!report) return
    try {
      await downloadApiFile(exportUrl(format), `incident-report.${format === "markdown" ? "md" : "json"}`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Report export is unavailable.")
    }
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            post-incident workflow
          </p>

          <div className="mt-2 flex items-center gap-2">
            <FileText className="h-5 w-5 text-info" />

            <h3 className="font-heading text-lg font-bold">
              Post-Incident Report
            </h3>
          </div>
        </div>

        <Button
          variant="outline"
          disabled={loading}
          onClick={() =>
            void handleGenerate()
          }
        >
          {loading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : report ? (
            <RefreshCw className="h-4 w-4" />
          ) : (
            <FileText className="h-4 w-4" />
          )}

          {report
            ? "Generate new version"
            : "Generate report"}
        </Button>
      </header>


      {error && (
        <div className="m-5 flex gap-3 rounded-md border border-danger/40 bg-danger/10 p-4 text-danger">
          <AlertCircle className="h-5 w-5 shrink-0" />

          <p className="font-mono text-xs">
            {error}
          </p>
        </div>
      )}


      {reports.length > 0 && (
        <div className="border-b border-border p-5">
          <FieldLabel>
            Report version
          </FieldLabel>

          <select
            value={selectedReportId}
            onChange={(event) =>
              setSelectedReportId(
                event.target.value,
              )
            }
            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
          >
            {reports.map((item) => (
              <option
                key={item.report_id}
                value={item.report_id}
              >
                Version {item.version}
                {" — "}
                {item.status}
                {" — "}
                {new Date(
                  item.created_at,
                ).toLocaleString()}
              </option>
            ))}
          </select>
        </div>
      )}


      {loading && !report && (
        <div className="flex items-center gap-2 p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Building post-incident report…
        </div>
      )}


      {!loading &&
        !error &&
        !report && (
        <div className="p-5">
          <p className="text-sm text-muted-foreground">
            Generate a versioned report from
            the incident, RCA, blast radius,
            ownership, investigation and
            recovery evidence.
          </p>
        </div>
      )}


      {report && (
        <div className="space-y-7 p-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase">
              <Badge>
                version {report.version}
              </Badge>

              <Badge>
                {report.status}
              </Badge>

              <Badge>
                {report.provider}
              </Badge>

              <Badge>
                generated report self-score {report.overall_confidence.toFixed(2)} (uncalibrated)
              </Badge>

              <Badge>
                {
                  report
                    .completed_action_item_count
                }
                /
                {
                  report
                    .action_item_count
                }
                {" actions"}
              </Badge>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void exportReport("markdown")}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs"
              >
                <Download className="h-4 w-4" />
                Markdown
              </button>

              <button
                type="button"
                onClick={() => void exportReport("json")}
                className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs"
              >
                <Download className="h-4 w-4" />
                JSON
              </button>
            </div>
          </div>


          <div>
            <h4 className="font-heading text-xl font-bold">
              {report.title}
            </h4>
          </div>


          <ReportSection
            title="Executive summary"
            value={
              report.executive_summary
            }
          />

          <ReportSection
            title="Incident overview"
            value={
              report.incident_overview
            }
          />

          <ReportSection
            title="Root cause"
            value={report.root_cause}
          />

          <ListSection
            title="Contributing factors"
            values={
              report
                .contributing_factors
            }
          />

          <ReportSection
            title="Business impact"
            value={
              report.business_impact
            }
          />

          <ReportSection
            title="Technical impact"
            value={
              report.technical_impact
            }
          />


          <div>
            <SectionTitle>
              Incident timeline
            </SectionTitle>

            <div className="mt-4 space-y-4">
              {report.timeline.map(
                (item, index) => (
                  <div
                    key={`${item.timestamp}-${index}`}
                    className="border-l-2 border-border pl-4"
                  >
                    <div className="flex flex-wrap gap-2 font-mono text-[10px] text-muted-foreground">
                      <span>
                        {formatTimestamp(
                          item.timestamp,
                        )}
                      </span>

                      <span className="uppercase">
                        {item.phase}
                      </span>
                    </div>

                    <p className="mt-1 text-sm">
                      {item.event}
                    </p>

                    <EvidenceIds
                      values={
                        item.evidence_ids
                      }
                    />
                  </div>
                ),
              )}
            </div>
          </div>


          <div>
            <SectionTitle>
              Investigation findings
            </SectionTitle>

            {report.investigation_findings
              .length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
                No investigation findings were
                included.
              </p>
            ) : (
              <div className="mt-4 space-y-3">
                {report
                  .investigation_findings
                  .map((finding, index) => (
                    <article
                      key={`${finding.summary}-${index}`}
                      className="rounded-md border border-border bg-card p-4"
                    >
                      <p className="font-semibold">
                        {finding.summary}
                      </p>

                      <p className="mt-2 text-xs leading-5 text-muted-foreground">
                        {
                          finding
                            .significance
                        }
                      </p>

                      <EvidenceIds
                        values={
                          finding
                            .evidence_ids
                        }
                      />
                    </article>
                  ))}
              </div>
            )}
          </div>


          <ReportSection
            title="Remediation summary"
            value={
              report.remediation_summary
            }
          />

          <ReportSection
            title="Recovery validation"
            value={
              report.recovery_validation
            }
          />

          <ListSection
            title="Lessons learned"
            values={
              report.lessons_learned
            }
          />


          {report.evidence_gaps.length >
            0 && (
            <div className="rounded-md border border-warn/40 bg-warn/10 p-4">
              <SectionTitle>
                Evidence gaps
              </SectionTitle>

              <ul className="mt-3 space-y-2 text-sm">
                {report.evidence_gaps.map(
                  (item) => (
                    <li key={item}>
                      • {item}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}


          <div>
            <SectionTitle>
              Corrective and preventive actions
            </SectionTitle>

            <div className="mt-4 space-y-4">
              {report.action_items.map(
                (action) => {
                  const draft =
                    actionDrafts[
                      action.action_item_id
                    ]

                  return (
                    <article
                      key={
                        action.action_item_id
                      }
                      className="rounded-md border border-border bg-card"
                    >
                      <header className="flex items-start justify-between gap-4 border-b border-border p-4">
                        <div>
                          <p className="font-mono text-[10px] uppercase text-muted-foreground">
                            Action{" "}
                            {action.sequence}
                            {" · "}
                            {action.priority}
                          </p>

                          <h4 className="mt-1 font-heading font-bold">
                            {action.title}
                          </h4>
                        </div>

                        {action.status ===
                          "completed" && (
                          <CheckCircle2 className="h-5 w-5 text-ok" />
                        )}
                      </header>

                      <div className="space-y-4 p-4">
                        <p className="text-sm leading-6">
                          {action.description}
                        </p>

                        <Info
                          label="SUCCESS CRITERIA"
                          value={
                            action
                              .success_criteria
                          }
                        />

                        <EvidenceIds
                          values={
                            action.evidence_ids
                          }
                        />

                        {draft && (
                          <div className="grid gap-4 border-t border-border pt-4 lg:grid-cols-2">
                            <label>
                              <FieldLabel>
                                Status
                              </FieldLabel>

                              <select
                                value={
                                  draft.status
                                }
                                onChange={(
                                  event,
                                ) =>
                                  updateActionDraft(
                                    action
                                      .action_item_id,
                                    {
                                      status:
                                        event.target.value as ReportActionStatus,
                                    },
                                  )
                                }
                                className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                              >
                                <option value="open">
                                  Open
                                </option>

                                <option value="in_progress">
                                  In progress
                                </option>

                                <option value="completed">
                                  Completed
                                </option>

                                <option value="cancelled">
                                  Cancelled
                                </option>
                              </select>
                            </label>

                            <label>
                              <FieldLabel>
                                Due date
                              </FieldLabel>

                              <input
                                value={
                                  draft.dueDate
                                }
                                onChange={(
                                  event,
                                ) =>
                                  updateActionDraft(
                                    action
                                      .action_item_id,
                                    {
                                      dueDate:
                                        event
                                          .target
                                          .value,
                                    },
                                  )
                                }
                                placeholder="YYYY-MM-DD"
                                className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                              />
                            </label>

                            <label>
                              <FieldLabel>
                                Owner team
                              </FieldLabel>

                              <input
                                value={
                                  draft
                                    .ownerTeam
                                }
                                onChange={(
                                  event,
                                ) =>
                                  updateActionDraft(
                                    action
                                      .action_item_id,
                                    {
                                      ownerTeam:
                                        event
                                          .target
                                          .value,
                                    },
                                  )
                                }
                                className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                              />
                            </label>

                            <label>
                              <FieldLabel>
                                Owner contact
                              </FieldLabel>

                              <input
                                value={
                                  draft
                                    .ownerContact
                                }
                                onChange={(
                                  event,
                                ) =>
                                  updateActionDraft(
                                    action
                                      .action_item_id,
                                    {
                                      ownerContact:
                                        event
                                          .target
                                          .value,
                                    },
                                  )
                                }
                                className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                              />
                            </label>

                            <label className="lg:col-span-2">
                              <FieldLabel>
                                Notes
                              </FieldLabel>

                              <textarea
                                value={
                                  draft.notes
                                }
                                onChange={(
                                  event,
                                ) =>
                                  updateActionDraft(
                                    action
                                      .action_item_id,
                                    {
                                      notes:
                                        event
                                          .target
                                          .value,
                                    },
                                  )
                                }
                                rows={3}
                                className="mt-2 w-full rounded-sm border border-input bg-background px-3 py-2 text-sm"
                              />
                            </label>

                            <div className="lg:col-span-2">
                              <Button
                                disabled={
                                  loading
                                }
                                onClick={() =>
                                  void saveAction(
                                    action
                                      .action_item_id,
                                  )
                                }
                              >
                                <Save className="h-4 w-4" />
                                Save action
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    </article>
                  )
                },
              )}
            </div>
          </div>


          <div className="rounded-md border border-border bg-card p-5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-info" />

              <SectionTitle>
                Review and approval
              </SectionTitle>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <label>
                <FieldLabel>
                  Status
                </FieldLabel>

                <select
                  value={reviewStatus}
                  onChange={(event) =>
                    setReviewStatus(
                      event.target.value as PostIncidentReportStatus
                    )
                  }
                  className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                >
                  <option value="draft">
                    Draft
                  </option>

                  <option value="in_review">
                    In review
                  </option>

                  <option value="approved">
                    Approved
                  </option>

                  <option value="rejected">
                    Rejected
                  </option>
                </select>
              </label>

              <label>
                <FieldLabel>
                  Reviewer
                </FieldLabel>

                <input
                  value={reviewerName}
                  onChange={(event) =>
                    setReviewerName(
                      event.target.value,
                    )
                  }
                  className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                />
              </label>

              <label className="lg:col-span-2">
                <FieldLabel>
                  Review notes
                </FieldLabel>

                <textarea
                  value={reviewNotes}
                  onChange={(event) =>
                    setReviewNotes(
                      event.target.value,
                    )
                  }
                  rows={4}
                  className="mt-2 w-full rounded-sm border border-input bg-background px-3 py-2 text-sm"
                />
              </label>

              <div className="lg:col-span-2">
                <Button
                  disabled={loading}
                  onClick={() =>
                    void handleSaveReview()
                  }
                >
                  <ShieldCheck className="h-4 w-4" />
                  Save review
                </Button>
              </div>
            </div>
          </div>


          {report.warnings.length > 0 && (
            <div>
              <SectionTitle>
                Generation warnings
              </SectionTitle>

              <ul className="mt-3 space-y-2 font-mono text-xs text-muted-foreground">
                {report.warnings.map(
                  (warning) => (
                    <li key={warning}>
                      • {warning}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}


function ReportSection({
  title,
  value,
}: {
  title: string
  value: string
}) {
  return (
    <div>
      <SectionTitle>
        {title}
      </SectionTitle>

      <p className="mt-3 whitespace-pre-wrap text-sm leading-6">
        {value}
      </p>
    </div>
  )
}


function ListSection({
  title,
  values,
}: {
  title: string
  values: string[]
}) {
  return (
    <div>
      <SectionTitle>
        {title}
      </SectionTitle>

      <ul className="mt-3 space-y-2 text-sm">
        {values.map((value) => (
          <li key={value}>
            • {value}
          </li>
        ))}
      </ul>
    </div>
  )
}


function SectionTitle({
  children,
}: {
  children: ReactNode
}) {
  return (
    <h4 className="font-heading font-bold">
      {children}
    </h4>
  )
}


function FieldLabel({
  children,
}: {
  children: ReactNode
}) {
  return (
    <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      {children}
    </span>
  )
}


function Badge({
  children,
}: {
  children: ReactNode
}) {
  return (
    <span className="rounded-sm border border-border px-2 py-1">
      {children}
    </span>
  )
}


function EvidenceIds({
  values,
}: {
  values: string[]
}) {
  return (
    <div className="mt-3 flex flex-wrap gap-1">
      {values.map((value) => (
        <span
          key={value}
          title={value}
          className="max-w-[280px] truncate rounded-sm border border-border px-2 py-1 font-mono text-[9px] text-muted-foreground"
        >
          {value}
        </span>
      ))}
    </div>
  )
}


function Info({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>

      <p className="mt-2 text-xs leading-5">
        {value}
      </p>
    </div>
  )
}


function formatTimestamp(
  value: string | null,
): string {
  if (!value) {
    return "Time unavailable"
  }

  const date = new Date(value)

  if (
    Number.isNaN(
      date.getTime(),
    )
  ) {
    return value
  }

  return date.toLocaleString()
}


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : (
        "Unable to process the "
        + "post-incident report."
      )
}
