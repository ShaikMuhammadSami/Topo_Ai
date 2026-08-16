import {
  CheckCircle2,
  FileSearch,
  History,
  Sparkles,
  Wrench,
} from "lucide-react"

import {
  buildIncidentWorkspaceModel,
  formatBriefingDuration,
  formatConfidence,
  humanizeToken,
  isActiveIncident,
} from "@/lib/incident-briefing"
import type { IncidentBriefing } from "@/lib/topo-types"
import {
  BusinessDatum,
  Metric,
  SectionHeading,
} from "@/components/app/incident-briefing-ui"

export function BusinessOverview({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const model =
    buildIncidentWorkspaceModel(briefing)
  const business = model.business
  const impact =
    briefing.operational_context
      ?.business_impact
  const outcome = briefing.outcome

  return (
    <div className="space-y-6 py-6">
      <section className="overflow-hidden rounded-md border border-border bg-card">
        <div className="border-b border-border p-5 sm:p-7">
          <p className="font-mono text-[10px] uppercase tracking-widest text-primary">
            Business incident overview
          </p>
          <h2 className="mt-3 max-w-4xl font-heading text-2xl font-black leading-tight sm:text-3xl">
            {business.affected}
          </h2>
          <p className="mt-3 max-w-4xl text-base leading-relaxed text-muted-foreground">
            {briefing.summary.text}
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4">
          <BusinessDatum
            label="Current status"
            value={humanizeToken(business.status)}
            detail={
              isActiveIncident(briefing)
                ? "Response is in progress"
                : "Incident is no longer active"
            }
          />
          <BusinessDatum
            label="Severity"
            value={briefing.incident.severity.toUpperCase()}
            detail={
              impact?.highest_criticality
                ? humanizeToken(impact.highest_criticality)
                : humanizeToken(business.businessImpactLevel)
            }
          />
          <BusinessDatum
            label="Owner"
            value={business.owner}
            detail={
              briefing.operational_context?.ownership
                .service_name ?? "Root service"
            }
          />
          <BusinessDatum
            label="Environment"
            value={business.environment}
            detail={business.service ?? "Affected service"}
          />
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div className="rounded-md border border-border bg-card p-5 sm:p-6">
          <SectionHeading
            icon={FileSearch}
            eyebrow="Plain-language cause"
            title="What caused it?"
          />
          <p className="mt-4 text-lg font-medium leading-relaxed">
            {business.cause}
          </p>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            This is the leading evidence-backed conclusion, not a guarantee. Causal confidence is {formatConfidence(briefing.root_cause.causal_confidence)}.
          </p>
        </div>

        <div className="rounded-md border border-primary/25 bg-primary/[0.035] p-5 sm:p-6">
          <SectionHeading
            icon={Wrench}
            eyebrow="Current response"
            title="What is being done?"
          />
          <p className="mt-4 text-base leading-relaxed">
            {business.currentResponse}
          </p>
          <p className="mt-3 font-mono text-[10px] text-muted-foreground">
            Guidance is performed manually by the response team.
          </p>
        </div>
      </section>

      <section className="grid gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-3">
        <Metric
          label="Infrastructure affected"
          value={
            briefing.blast_radius
              ?.affected_entity_count ??
            impact?.affected_entity_count ??
            "Assessing"
          }
        />
        <Metric
          label="Teams affected"
          value={impact?.affected_team_count ?? "Assessing"}
        />
        <Metric
          label="Capabilities affected"
          value={impact?.affected_capability_count ?? "Assessing"}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-md border border-border bg-card p-5">
          <SectionHeading
            icon={History}
            eyebrow="Previous experience"
            title="Has this happened before?"
          />
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            {business.historicalSummary ??
              "No similar resolved incidents were found. The response does not rely on unsupported history."}
          </p>
        </section>

        <section className="rounded-md border border-border bg-card p-5">
          <SectionHeading
            icon={CheckCircle2}
            eyebrow="Resolution status"
            title={outcome ? "Recorded outcome" : "Incident in progress"}
          />
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            {outcome
              ? outcome.resolution_summary
              : isActiveIncident(briefing)
                ? "The incident remains active. A final outcome has not been recorded yet."
                : "The incident is closed, but a structured resolution outcome is not available."}
          </p>
          {outcome?.time_to_resolution_seconds !== null &&
            outcome?.time_to_resolution_seconds !== undefined && (
              <p className="mt-3 font-mono text-[10px] uppercase text-ok">
                Resolution time {formatBriefingDuration(outcome.time_to_resolution_seconds)}
              </p>
            )}
        </section>
      </div>

      {briefing.ai_summary && (
        <section className="flex items-start gap-3 border-l-2 border-info bg-info/5 px-4 py-3">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-info">
              Optional AI narrative
            </p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {briefing.ai_summary}
            </p>
          </div>
        </section>
      )}
    </div>
  )
}
