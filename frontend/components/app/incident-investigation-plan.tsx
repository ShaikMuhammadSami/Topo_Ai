"use client"

import {
  useEffect,
  useState,
  ReactNode
} from "react"
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
} from "lucide-react"

import {
  Button,
} from "@/components/ui/button"
import {
  generateInvestigationPlan,
  getInvestigationPlan,
  listInvestigationPlans,
  updateInvestigationStep,
} from "@/lib/topo-api"
import type {
  InvestigationPlanDetail,
  InvestigationPlanSummary,
  InvestigationStepStatus,
} from "@/lib/topo-types"


type StepDraft = {
  status: InvestigationStepStatus
  finding: string
  responderNotes: string
}


export function IncidentInvestigationPlan({
  incidentId,
}: {
  incidentId: string
}) {
  const [plans, setPlans] =
    useState<
      InvestigationPlanSummary[]
    >([])

  const [selectedPlanId, setSelectedPlanId] =
    useState("")

  const [plan, setPlan] =
    useState<
      InvestigationPlanDetail | null
    >(null)

  const [drafts, setDrafts] =
    useState<
      Record<string, StepDraft>
    >({})

  const [loading, setLoading] =
    useState(false)

  const [error, setError] =
    useState<string | null>(null)


  useEffect(() => {
    if (!incidentId) {
      setPlans([])
      setSelectedPlanId("")
      setPlan(null)
      return
    }

    let cancelled = false

    async function loadPlans() {
      setLoading(true)
      setError(null)

      try {
        const values =
          await listInvestigationPlans(
            incidentId,
          )

        if (cancelled) {
          return
        }

        setPlans(values)

        setSelectedPlanId(
          values[0]?.plan_id ?? "",
        )

        if (values.length === 0) {
          setPlan(null)
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

    void loadPlans()

    return () => {
      cancelled = true
    }
  }, [incidentId])


  useEffect(() => {
    if (!selectedPlanId) {
      return
    }

    let cancelled = false

    async function loadPlan() {
      setLoading(true)
      setError(null)

      try {
        const value =
          await getInvestigationPlan(
            incidentId,
            selectedPlanId,
          )

        if (!cancelled) {
          setPlan(value)
          setDrafts(
            draftsFromPlan(value),
          )
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

    void loadPlan()

    return () => {
      cancelled = true
    }
  }, [
    incidentId,
    selectedPlanId,
  ])


  async function handleGenerate(
    forceRegenerate: boolean,
  ) {
    setLoading(true)
    setError(null)

    try {
      const generated =
        await generateInvestigationPlan(
          incidentId,
          {
            provider: "auto",
            forceRegenerate,
          },
        )

      const values =
        await listInvestigationPlans(
          incidentId,
        )

      setPlans(values)
      setSelectedPlanId(
        generated.plan_id,
      )
      setPlan(generated)
      setDrafts(
        draftsFromPlan(generated),
      )
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  function updateDraft(
    stepId: string,
    update: Partial<StepDraft>,
  ) {
    setDrafts((current) => ({
      ...current,
      [stepId]: {
        ...current[stepId],
        ...update,
      },
    }))
  }


  async function saveStep(
    stepId: string,
  ) {
    const draft = drafts[stepId]

    if (!draft || !plan) {
      return
    }

    setLoading(true)
    setError(null)

    try {
      const updated =
        await updateInvestigationStep(
          incidentId,
          plan.plan_id,
          stepId,
          {
            status: draft.status,
            finding:
              draft.finding.trim()
              || null,
            responder_notes:
              draft.responderNotes
                .trim()
              || null,
          },
        )

      setPlan(updated)
      setDrafts(
        draftsFromPlan(updated),
      )

      const values =
        await listInvestigationPlans(
          incidentId,
        )

      setPlans(values)
    } catch (requestError) {
      setError(
        errorMessage(requestError),
      )
    } finally {
      setLoading(false)
    }
  }


  return (
    <section className="overflow-hidden rounded-md border border-border bg-background">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            responder workflow
          </p>

          <div className="mt-2 flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-info" />

            <h3 className="font-heading text-lg font-bold">
              Investigation Planner
            </h3>
          </div>
        </div>

        <Button
          variant="outline"
          disabled={loading}
          onClick={() =>
            void handleGenerate(
              Boolean(plan),
            )
          }
        >
          {loading ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : plan ? (
            <RefreshCw className="h-4 w-4" />
          ) : (
            <ClipboardCheck className="h-4 w-4" />
          )}

          {plan
            ? "Generate new plan"
            : "Generate plan"}
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


      {plans.length > 0 && (
        <div className="border-b border-border p-5">
          <label>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              Investigation plan
            </span>

            <select
              value={selectedPlanId}
              onChange={(event) =>
                setSelectedPlanId(
                  event.target.value,
                )
              }
              className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 font-mono text-xs"
            >
              {plans.map((item) => (
                <option
                  key={item.plan_id}
                  value={item.plan_id}
                >
                  {item.title}
                  {" — "}
                  {item.status}
                  {" — "}
                  {new Date(
                    item.created_at,
                  ).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}


      {loading && !plan && (
        <div className="flex items-center gap-2 p-5 font-mono text-xs text-muted-foreground">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          Building investigation plan…
        </div>
      )}


      {!loading &&
        !error &&
        !plan && (
        <div className="p-5">
          <p className="text-sm text-muted-foreground">
            Generate a grounded investigation
            workflow using the incident’s RCA,
            topology, ownership, network and
            recovery evidence.
          </p>
        </div>
      )}


      {plan && (
        <div className="space-y-6 p-5">
          <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase">
            <Badge>
              {plan.provider}
            </Badge>

            <Badge>
              {plan.status}
            </Badge>

            <Badge>
              generated plan self-score {plan.overall_confidence.toFixed(2)} (uncalibrated)
            </Badge>

            <Badge>
              {plan.completed_step_count}
              /
              {plan.step_count}
              {" complete"}
            </Badge>
          </div>


          <div>
            <h4 className="font-heading text-lg font-bold">
              {plan.title}
            </h4>

            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              {plan.objective}
            </p>

            <p className="mt-3 text-sm leading-6">
              {plan.incident_summary}
            </p>
          </div>


          {plan.evidence_gaps.length >
            0 && (
            <div className="rounded-md border border-warn/40 bg-warn/10 p-4">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-4 w-4 text-warn" />

                <h4 className="font-heading font-bold">
                  Evidence gaps
                </h4>
              </div>

              <ul className="mt-3 space-y-2 text-sm">
                {plan.evidence_gaps.map(
                  (item) => (
                    <li key={item}>
                      • {item}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}


          <div className="space-y-4">
            {plan.steps.map((step) => {
              const draft =
                drafts[step.step_id]

              return (
                <article
                  key={step.step_id}
                  className="rounded-md border border-border bg-card"
                >
                  <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4">
                    <div className="flex gap-3">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border font-mono text-xs">
                        {step.sequence}
                      </span>

                      <div>
                        <h4 className="font-heading font-bold">
                          {step.title}
                        </h4>

                        <p className="mt-1 text-xs leading-5 text-muted-foreground">
                          {step.objective}
                        </p>
                      </div>
                    </div>

                    {step.status ===
                      "completed" && (
                      <CheckCircle2 className="h-5 w-5 text-ok" />
                    )}
                  </header>


                  <div className="space-y-4 p-4">
                    <Info
                      label="TARGET"
                      value={step.target}
                    />

                    {step.command && (
                      <div>
                        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                          Read-only command
                        </p>

                        <div className="mt-2 flex gap-2">
                          <pre className="flex-1 overflow-x-auto rounded-md border border-border bg-background p-3 font-mono text-xs">
                            {step.command}
                          </pre>

                          <Button
                            variant="outline"
                            onClick={() =>
                              void navigator
                                .clipboard
                                .writeText(
                                  step.command
                                  ?? "",
                                )
                            }
                          >
                            <Copy className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    )}

                    <div className="grid gap-4 lg:grid-cols-3">
                      <Info
                        label="EXPECTED"
                        value={
                          step
                            .expected_observation
                        }
                      />

                      <Info
                        label="SUCCESS"
                        value={
                          step
                            .success_criteria
                        }
                      />

                      <Info
                        label="FAILURE"
                        value={
                          step
                            .failure_indication
                        }
                      />
                    </div>


                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                        Evidence
                      </p>

                      <div className="mt-2 flex flex-wrap gap-1">
                        {step.evidence_ids.map(
                          (evidenceId) => (
                            <span
                              key={evidenceId}
                              title={
                                evidenceId
                              }
                              className="max-w-[280px] truncate rounded-sm border border-border px-2 py-1 font-mono text-[9px] text-muted-foreground"
                            >
                              {evidenceId}
                            </span>
                          ),
                        )}
                      </div>
                    </div>


                    {draft && (
                      <div className="grid gap-4 border-t border-border pt-4 lg:grid-cols-2">
                        <label>
                          <FieldLabel>
                            Status
                          </FieldLabel>

                          <select
                            value={draft.status}
                            onChange={(event) => {
                              const status = event.target.value as InvestigationStepStatus
                              updateDraft(step.step_id, { status })
                            }}
                            className="mt-2 h-10 w-full rounded-sm border border-input bg-background px-3 text-sm"
                          >
                            <option value="pending">
                              Pending
                            </option>

                            <option value="in_progress">
                              In progress
                            </option>

                            <option value="completed">
                              Completed
                            </option>

                            <option value="blocked">
                              Blocked
                            </option>

                            <option value="skipped">
                              Skipped
                            </option>
                          </select>
                        </label>

                        <label>
                          <FieldLabel>
                            Finding
                          </FieldLabel>

                          <textarea
                            value={
                              draft.finding
                            }
                            onChange={(
                              event,
                            ) =>
                              updateDraft(
                                step.step_id,
                                {
                                  finding:
                                    event
                                      .target
                                      .value,
                                },
                              )
                            }
                            rows={3}
                            placeholder="What did you observe?"
                            className="mt-2 w-full resize-y rounded-sm border border-input bg-background px-3 py-2 text-sm"
                          />
                        </label>

                        <label className="lg:col-span-2">
                          <FieldLabel>
                            Responder notes
                          </FieldLabel>

                          <textarea
                            value={
                              draft
                                .responderNotes
                            }
                            onChange={(
                              event,
                            ) =>
                              updateDraft(
                                step.step_id,
                                {
                                  responderNotes:
                                    event
                                      .target
                                      .value,
                                },
                              )
                            }
                            rows={3}
                            placeholder="Add investigation context or follow-up notes."
                            className="mt-2 w-full resize-y rounded-sm border border-input bg-background px-3 py-2 text-sm"
                          />
                        </label>

                        <div className="lg:col-span-2">
                          <Button
                            disabled={loading}
                            onClick={() =>
                              void saveStep(
                                step.step_id,
                              )
                            }
                          >
                            {loading ? (
                              <LoaderCircle className="h-4 w-4 animate-spin" />
                            ) : (
                              <CheckCircle2 className="h-4 w-4" />
                            )}

                            Save progress
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </article>
              )
            })}
          </div>


          {plan.warnings.length > 0 && (
            <div>
              <h4 className="font-heading font-bold">
                Generation warnings
              </h4>

              <ul className="mt-3 space-y-2 font-mono text-xs text-muted-foreground">
                {plan.warnings.map(
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


function draftsFromPlan(
  plan: InvestigationPlanDetail,
): Record<string, StepDraft> {
  return Object.fromEntries(
    plan.steps.map((step) => [
      step.step_id,
      {
        status: step.status,
        finding:
          step.finding ?? "",
        responderNotes:
          step.responder_notes ?? "",
      },
    ]),
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


function errorMessage(
  value: unknown,
): string {
  return value instanceof Error
    ? value.message
    : (
        "Unable to process the "
        + "investigation plan request."
      )
}
