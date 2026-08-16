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
    <div className="space-y-4 py-4">
      <section className="overflow-hidden rounded-md border border-border bg-card">
        <div className="border-b border-border p-4 sm:p-5">
          <p className="font-mono text-[10px] uppercase tracking-widest text-primary">
            Business incident overview
          </p>
          <h2 className="mt-2 max-w-4xl font-heading text-xl font-black leading-tight sm:text-2xl">
            {business.affected}
          </h2>
          <p className="mt-2 max-w-4xl text-sm leading-relaxed text-muted-foreground">
            {briefing.summary.text}
          </p>
          <p className="mt-2 font-mono text-[9px] text-muted-foreground">
            {business.environment} · {business.service ?? "affected service"}
          </p>
        </div>

        <div className="grid sm:grid-cols-3">
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
            label="Business impact"
            value={humanizeToken(
              business.businessImpactLevel ??
                briefing.incident.severity,
            )}
            detail={
              impact?.highest_criticality
                ? humanizeToken(impact.highest_criticality)
                : `${briefing.blast_radius?.affected_entity_count ?? "Assessing"} infrastructure entities`
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
        </div>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <section className="rounded-md border border-border bg-card p-4 sm:p-5">
          <SectionHeading
            icon={FileSearch}
            eyebrow="Plain-language cause"
            title="What caused it?"
          />
          <p className="mt-3 text-base font-medium leading-relaxed">
            {business.cause}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
            This is the leading evidence-backed conclusion, not a guarantee. Causal confidence is {formatConfidence(briefing.root_cause.causal_confidence)}.
          </p>
          </section>

          <section className="rounded-md border border-primary/25 bg-primary/[0.035] p-4 sm:p-5">
          <SectionHeading
            icon={Wrench}
            eyebrow="Current response"
            title="What is being done?"
          />
          <p className="mt-3 text-sm leading-relaxed">
            {business.currentResponse}
          </p>
          <p className="mt-3 font-mono text-[10px] text-muted-foreground">
            Guidance is performed manually by the response team.
          </p>
          </section>
        </div>

        <aside className="rounded-md border border-border bg-card p-4">
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
          <div className="mt-4 grid grid-cols-3 gap-px overflow-hidden rounded-sm border border-border bg-border">
            <Metric
              label="Entities"
              value={briefing.blast_radius?.affected_entity_count ?? impact?.affected_entity_count ?? "—"}
            />
            <Metric
              label="Teams"
              value={impact?.affected_team_count ?? "—"}
            />
            <Metric
              label="Capabilities"
              value={impact?.affected_capability_count ?? "—"}
            />
          </div>
        </aside>
      </div>

      <details className="rounded-md border border-border bg-card p-4">
        <summary className="cursor-pointer list-none">
          <SectionHeading
            icon={History}
            eyebrow="Previous experience"
            title={`Similar incidents · ${briefing.historical_context.similar_incident_count}`}
          />
        </summary>
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {business.historicalSummary ??
            "No similar resolved incidents were found. The response does not rely on unsupported history."}
        </p>
      </details>

      {briefing.ai_summary && (
        <details className="border-l-2 border-info bg-info/5 px-4 py-2.5">
          <summary className="cursor-pointer list-none font-mono text-[10px] uppercase tracking-widest text-info">
            <span className="inline-flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5" />
              Optional AI narrative
            </span>
          </summary>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {briefing.ai_summary}
          </p>
        </details>
      )}
    </div>
  )
}
