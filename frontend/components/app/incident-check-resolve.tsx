"use client"

import {
  useRef,
  useState,
} from "react"
import { useRouter } from "next/navigation"
import {
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  LoaderCircle,
  SearchCheck,
  ShieldCheck,
  ShieldX,
  X,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  checkIncidentResolution,
  getIncidentResolutionPlan,
  updateIncidentRecordStatus,
} from "@/lib/topo-api"
import {
  submitIncidentStatus,
} from "@/lib/incident-resolution"
import type {
  BriefingIncident,
  IncidentResolutionCheck,
  IncidentResolutionCheckResult,
  IncidentResolutionPlan,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"


export function IncidentCheckResolve({
  incident,
}: {
  incident: BriefingIncident
}) {
  const router = useRouter()
  const statusSubmissionGate = useRef(false)
  const resolveActionGate = useRef(false)
  const [open, setOpen] = useState(false)
  const [plan, setPlan] =
    useState<IncidentResolutionPlan | null>(null)
  const [result, setResult] =
    useState<IncidentResolutionCheckResult | null>(null)
  const [loadingPlan, setLoadingPlan] =
    useState(false)
  const [checking, setChecking] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [confirmResolve, setConfirmResolve] =
    useState(false)
  const [error, setError] =
    useState<string | null>(null)

  if (
    incident.status === "resolved" ||
    incident.status === "dismissed"
  ) {
    return null
  }

  async function openDialog() {
    setOpen(true)
    setLoadingPlan(true)
    setError(null)
    setResult(null)
    setConfirmResolve(false)

    try {
      setPlan(
        await getIncidentResolutionPlan(
          incident.incident_id,
        ),
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoadingPlan(false)
    }
  }

  async function runChecks() {
    if (!plan?.evidence || !plan.can_check) {
      return
    }
    setChecking(true)
    setError(null)
    setResult(null)
    setConfirmResolve(false)

    try {
      setResult(
        await checkIncidentResolution(
          incident.incident_id,
          plan.evidence.snapshot_id,
        ),
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setChecking(false)
    }
  }

  async function markResolved() {
    if (
      !result?.eligible_to_resolve ||
      !result.resolution_note ||
      resolving ||
      resolveActionGate.current ||
      statusSubmissionGate.current
    ) {
      return
    }
    resolveActionGate.current = true
    setResolving(true)
    setError(null)

    try {
      const revalidated =
        await checkIncidentResolution(
          incident.incident_id,
          result.evidence.snapshot_id,
        )
      setResult(revalidated)
      if (
        !revalidated.eligible_to_resolve ||
        !revalidated.resolution_note
      ) {
        setConfirmResolve(false)
        throw new Error(
          "Recovery evidence is no longer valid. Review the updated checks before resolving.",
        )
      }
      await submitIncidentStatus({
        incidentId: incident.incident_id,
        status: "resolved",
        note: revalidated.resolution_note,
        gate: statusSubmissionGate,
        updateStatus:
          updateIncidentRecordStatus,
        navigate: (href) =>
          router.push(href),
      })
    } catch (requestError) {
      setError(errorMessage(requestError))
      setConfirmResolve(false)
    } finally {
      resolveActionGate.current = false
      setResolving(false)
    }
  }

  return (
    <>
      <div className="mt-3 flex justify-end">
        <Button
          type="button"
          onClick={() => void openDialog()}
        >
          <SearchCheck />
          Check &amp; Resolve
        </Button>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-3 backdrop-blur-sm sm:p-6"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setOpen(false)
            }
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="check-resolve-title"
            className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-md border border-border bg-background shadow-2xl"
          >
            <header className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-border bg-background/95 p-4 backdrop-blur sm:p-5">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-widest text-primary">
                  Read-only recovery verification
                </p>
                <h2
                  id="check-resolve-title"
                  className="mt-1 font-heading text-xl font-black"
                >
                  Check &amp; Resolve
                </h2>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Close Check and Resolve"
                onClick={() => setOpen(false)}
              >
                <X />
              </Button>
            </header>

            <div className="space-y-5 p-4 sm:p-5">
              <div className="flex items-start gap-3 rounded-md border border-info/30 bg-info/5 p-4 text-sm">
                <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-info" />
                <p>
                  Topo will only inspect already collected topology evidence. It will not run kubectl, contact the cluster, restart workloads or modify infrastructure. Marking resolved always requires your final confirmation.
                </p>
              </div>

              {error && (
                <div className="flex items-start gap-3 rounded-md border border-danger/35 bg-danger/5 p-4 text-danger">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p className="font-mono text-xs">
                    {error}
                  </p>
                </div>
              )}

              {loadingPlan ? (
                <Loading text="Preparing scoped recovery checks…" />
              ) : plan ? (
                <>
                  <Context plan={plan} />

                  <section className="rounded-md border border-border bg-card p-4">
                    <SectionTitle>
                      Checks Topo will perform
                    </SectionTitle>
                    <ol className="mt-3 space-y-3">
                      {plan.checks.map((check) => (
                        <li
                          key={check.code}
                          className="rounded-sm border border-border p-3"
                        >
                          <p className="text-sm font-semibold">
                            {check.title}
                          </p>
                          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                            {check.description}
                          </p>
                        </li>
                      ))}
                    </ol>
                  </section>

                  {plan.kubectl_commands.length > 0 && (
                    <section className="rounded-md border border-border bg-card p-4">
                      <SectionTitle>
                        Human-readable equivalents
                      </SectionTitle>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Topo does not execute these commands. They show the equivalent operator checks.
                      </p>
                      <div className="mt-3 space-y-2">
                        {plan.kubectl_commands.map(
                          (command) => (
                            <pre
                              key={command}
                              className="overflow-x-auto rounded-sm border border-border bg-background p-3 font-mono text-[10px]"
                            >
                              {command}
                            </pre>
                          ),
                        )}
                      </div>
                    </section>
                  )}

                  {plan.limitation && (
                    <div className="rounded-md border border-warn/35 bg-warn/5 p-4 text-sm text-warn">
                      {plan.limitation}
                    </div>
                  )}

                  {!result && (
                    <div className="flex justify-end">
                      <Button
                        type="button"
                        disabled={
                          checking || !plan.can_check
                        }
                        onClick={() => void runChecks()}
                      >
                        {checking ? (
                          <LoaderCircle className="animate-spin" />
                        ) : (
                          <SearchCheck />
                        )}
                        {checking
                          ? "Checking"
                          : "Confirm and run read-only checks"}
                      </Button>
                    </div>
                  )}

                  {checking && (
                    <Loading text="Evaluating persisted snapshot evidence…" />
                  )}

                  {result && (
                    <Result
                      result={result}
                      confirmResolve={confirmResolve}
                      resolving={resolving}
                      onCheckAgain={() =>
                        void runChecks()
                      }
                      onRequestResolve={() =>
                        setConfirmResolve(true)
                      }
                      onCancelResolve={() =>
                        setConfirmResolve(false)
                      }
                      onResolve={() =>
                        void markResolved()
                      }
                    />
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Recovery-check context is unavailable.
                </p>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  )
}


function Context({
  plan,
}: {
  plan: IncidentResolutionPlan
}) {
  return (
    <section className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2">
      <ContextItem
        label="Tenant"
        value={plan.target.tenant_id}
      />
      <ContextItem
        label="Affected environment"
        value={[
          plan.target.cluster_name,
          plan.target.namespace,
        ].filter(Boolean).join(" / ")}
      />
      <ContextItem
        label="Affected workload"
        value={[
          plan.target.workload_kind,
          plan.target.workload_name,
        ].filter(Boolean).join("/") || "Unresolved"}
      />
      <ContextItem
        label="Evidence source"
        value={
          plan.evidence
            ? `${plan.evidence.collector_name} ${plan.evidence.collector_version}`
            : "No matching persisted snapshot"
        }
      />
      <ContextItem
        label="Evidence timestamp"
        value={
          plan.evidence
            ? formatDate(plan.evidence.collected_at)
            : "Unavailable"
        }
      />
    </section>
  )
}


function Result({
  result,
  confirmResolve,
  resolving,
  onCheckAgain,
  onRequestResolve,
  onCancelResolve,
  onResolve,
}: {
  result: IncidentResolutionCheckResult
  confirmResolve: boolean
  resolving: boolean
  onCheckAgain: () => void
  onRequestResolve: () => void
  onCancelResolve: () => void
  onResolve: () => void
}) {
  return (
    <section className="space-y-4 border-t border-border pt-5">
      <div
        className={cn(
          "rounded-md border p-4",
          result.status === "verified"
            ? "border-ok/35 bg-ok/5"
            : result.status === "failed"
              ? "border-danger/35 bg-danger/5"
              : "border-warn/35 bg-warn/5",
        )}
      >
        <p className="font-heading text-lg font-bold">
          {result.status === "verified"
            ? "Recovery checks passed"
            : result.status === "failed"
              ? "Recovery not confirmed"
              : "Recovery remains inconclusive"}
        </p>
        <p className="mt-2 text-sm text-muted-foreground">
          {result.summary}
        </p>
        <p className="mt-2 font-mono text-[10px] text-muted-foreground">
          {result.passed_count} PASS · {result.failed_count} FAIL · {result.unknown_count} UNKNOWN
        </p>
      </div>

      <div className="space-y-3">
        {result.checks.map((check) => (
          <CheckResult
            key={check.code}
            check={check}
          />
        ))}
      </div>

      {confirmResolve &&
      result.eligible_to_resolve ? (
        <div className="rounded-md border border-ok/35 bg-ok/5 p-4">
          <p className="text-sm font-semibold">
            Confirm incident resolution
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            This records the evidence-backed note and changes only the incident status. It does not modify Kubernetes.
          </p>
          <div className="mt-4 flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={resolving}
              onClick={onCancelResolve}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={resolving}
              onClick={onResolve}
            >
              {resolving ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <CheckCircle2 />
              )}
              {resolving
                ? "Saving"
                : "Confirm mark resolved"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={onCheckAgain}
          >
            <SearchCheck /> Check again
          </Button>
          {result.eligible_to_resolve && (
            <Button
              type="button"
              onClick={onRequestResolve}
            >
              <CheckCircle2 /> Mark Resolved
            </Button>
          )}
        </div>
      )}
    </section>
  )
}


function CheckResult({
  check,
}: {
  check: IncidentResolutionCheck
}) {
  const Icon =
    check.status === "pass"
      ? CheckCircle2
      : check.status === "fail"
        ? ShieldX
        : CircleHelp
  return (
    <article
      className={cn(
        "rounded-md border p-4",
        check.status === "pass"
          ? "border-ok/30"
          : check.status === "fail"
            ? "border-danger/30"
            : "border-warn/30",
      )}
    >
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold">
              {check.title}
            </p>
            <span className="font-mono text-[10px] font-bold uppercase">
              {check.status}
            </span>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {check.summary}
          </p>
          <p className="mt-2 break-all font-mono text-[10px] text-muted-foreground">
            Evidence: {check.source_type}/{check.source_id}
          </p>
          <div className="mt-2 grid gap-2 font-mono text-[10px] sm:grid-cols-2">
            <p>Expected: {check.expected ?? "—"}</p>
            <p>Observed: {check.observed ?? "—"}</p>
          </div>
        </div>
      </div>
    </article>
  )
}


function ContextItem({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="bg-card p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 break-all text-sm font-semibold">
        {value}
      </p>
    </div>
  )
}


function SectionTitle({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
      {children}
    </p>
  )
}


function Loading({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border p-5 font-mono text-xs text-muted-foreground">
      <LoaderCircle className="h-4 w-4 animate-spin" />
      {text}
    </div>
  )
}


function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString()
}


function errorMessage(value: unknown): string {
  return value instanceof Error
    ? value.message
    : "An unexpected request error occurred."
}
