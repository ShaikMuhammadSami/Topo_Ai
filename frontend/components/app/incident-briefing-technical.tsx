import Link from "next/link"
import {
  Activity,
  ArrowRight,
  Building2,
  ExternalLink,
  FileSearch,
  GitCommitHorizontal,
  Network,
  PhoneCall,
  Route,
  Sparkles,
  Users,
  Wrench,
} from "lucide-react"

import {
  buildIncidentWorkspaceModel,
  formatConfidence,
  humanizeToken,
} from "@/lib/incident-briefing"
import type { IncidentBriefing } from "@/lib/topo-types"
import {
  Datum,
  DegradedState,
  Eyebrow,
  ImmediateDatum,
  Metric,
  SectionHeading,
  StatusBadge,
} from "@/components/app/incident-briefing-ui"
import {
  EvidenceAndWarnings,
  HistoricalContext,
  OutcomeSummary,
  ResponseGuidance,
  VerificationPlan,
} from "@/components/app/incident-briefing-response"

export function TechnicalWorkspace({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const model =
    buildIncidentWorkspaceModel(briefing)
  const root = briefing.root_cause
  const firstAction =
    briefing.remediation?.actions[0] ?? null

  return (
    <div className="space-y-8 py-6">
      <section
        aria-labelledby="immediate-answer-title"
        className="overflow-hidden rounded-md border border-border bg-card"
      >
        <h2 id="immediate-answer-title" className="sr-only">
          Immediate incident answer
        </h2>
        <div className="grid lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <div
            id="what-happened"
            className="border-b border-border p-5 sm:p-6 lg:border-b-0 lg:border-r"
          >
            <Eyebrow icon={Activity}>What happened</Eyebrow>
            <p className="mt-3 max-w-3xl text-lg font-medium leading-relaxed sm:text-xl">
              {model.immediate.whatHappened}
            </p>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              {briefing.incident.current_state}
            </p>
          </div>

          <div
            id="root-cause"
            className="border-l-2 border-l-primary p-5 sm:p-6"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Eyebrow icon={FileSearch}>Likely root cause</Eyebrow>
              <span className="font-heading text-2xl font-black text-primary">
                {formatConfidence(root.causal_confidence)}
              </span>
            </div>
            <h3 className="mt-3 font-heading text-xl font-bold">
              {model.immediate.rootCause}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {model.immediate.rootCauseSummary}
            </p>
            <p className="mt-3 font-mono text-[10px] uppercase text-muted-foreground">
              {humanizeToken(root.confidence_level)} confidence · {root.root_event_source}
            </p>
          </div>
        </div>

        <div className="grid border-t border-border sm:grid-cols-3">
          <ImmediateDatum
            id="impact"
            icon={Building2}
            label="Primary impact"
            value={model.immediate.primaryImpact}
          />
          <ImmediateDatum
            icon={Users}
            label="Root owner"
            value={model.immediate.owner}
          />
          <ImmediateDatum
            id="next-action"
            icon={Wrench}
            label="First response"
            value={model.immediate.nextAction}
            emphasize
          />
        </div>
      </section>

      {briefing.ai_summary && (
        <section className="flex items-start gap-3 border-l-2 border-info bg-info/5 px-4 py-3">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-info" />
          <div>
            <p className="font-mono text-[10px] uppercase tracking-widest text-info">
              Responder narrative · AI-assisted
            </p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
              {briefing.ai_summary}
            </p>
          </div>
        </section>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
        {briefing.recent_relevant_changes.length > 0 && (
          <section
            id="what-changed"
            className="rounded-md border border-border bg-card p-5"
          >
            <SectionHeading
              icon={GitCommitHorizontal}
              eyebrow="Pre-incident context"
              title="What changed"
            />
            <div className="mt-4 divide-y divide-border">
              {briefing.recent_relevant_changes.map((change) => (
                <article
                  key={change.event_id}
                  className="py-4 first:pt-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      value={change.change_type ?? change.role}
                      tone="info"
                    />
                    {change.minutes_before_incident !== null && (
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {formatMinutes(change.minutes_before_incident)} before symptoms
                      </span>
                    )}
                  </div>
                  <h3 className="mt-2 text-sm font-semibold">
                    {change.title}
                  </h3>
                  <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                    {[
                      change.source,
                      change.pipeline_name,
                      change.release_version,
                      change.commit_sha,
                    ].filter(Boolean).join(" · ")}
                  </p>
                </article>
              ))}
            </div>
          </section>
        )}
        <FailurePath briefing={briefing} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <BlastRadiusSection briefing={briefing} />
        <OwnershipSection briefing={briefing} />
      </div>

      <ResponseGuidance briefing={briefing} firstAction={firstAction} />
      <VerificationPlan briefing={briefing} />

      <div className="grid gap-6 xl:grid-cols-2">
        <HistoricalContext briefing={briefing} />
        <OutcomeSummary briefing={briefing} />
      </div>

      <EvidenceAndWarnings briefing={briefing} />

      {!briefing.ai_summary && briefing.ai_status !== "not_requested" && (
        <p className="font-mono text-[10px] text-muted-foreground">
          AI narrative unavailable; deterministic incident evidence remains complete.
        </p>
      )}
    </div>
  )
}

function FailurePath({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const model = buildIncidentWorkspaceModel(briefing)

  return (
    <section
      id="dependency-path"
      className="rounded-md border border-border bg-card p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionHeading
          icon={Route}
          eyebrow="Causal topology"
          title="Failure path"
        />
        {model.technical.topologyHref && (
          <Link
            href={model.technical.topologyHref}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-info hover:underline"
          >
            View pinned topology
            <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        )}
      </div>

      {model.technical.dependencyPath.length === 0 ? (
        <DegradedState
          icon={Network}
          text="A dependency path is not available for this analysis."
        />
      ) : (
        <>
          <ol className="mt-5 flex flex-col gap-2 lg:flex-row lg:items-stretch">
            {model.technical.dependencyPath.map((step, index) => (
              <li
                key={`${step.node_id}-${step.order}`}
                className="flex min-w-0 flex-1 items-center gap-2"
              >
                {index > 0 && (
                  <ArrowRight className="hidden h-4 w-4 shrink-0 text-muted-foreground lg:block" />
                )}
                <div className="min-w-0 flex-1 rounded-sm border border-border bg-background px-3 py-3">
                  <p className="font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
                    {humanizeToken(step.node_type)}
                  </p>
                  <p className="mt-1 truncate text-sm font-semibold" title={step.label}>
                    {step.label}
                  </p>
                  {step.relation_from_previous && (
                    <p className="mt-1 truncate font-mono text-[9px] text-info">
                      {humanizeToken(step.relation_from_previous)}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>

          <details className="mt-4 border-t border-border pt-3">
            <summary className="cursor-pointer font-mono text-[10px] uppercase text-muted-foreground hover:text-foreground">
              View path evidence and IDs
            </summary>
            <div className="mt-3 space-y-2 font-mono text-[10px] text-muted-foreground">
              <p>
                Snapshot: {briefing.root_cause.topology_snapshot_id ?? "not recorded"}
              </p>
              {model.technical.dependencyPath.map((step) => (
                <p key={`raw-${step.node_id}`} className="break-all">
                  {step.order}. {step.node_id}
                  {step.topology_relationship_id
                    ? ` · relationship ${step.topology_relationship_id}`
                    : ""}
                </p>
              ))}
            </div>
          </details>
        </>
      )}
    </section>
  )
}

function BlastRadiusSection({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const blast = briefing.blast_radius

  return (
    <section
      id="blast-radius"
      className="rounded-md border border-border bg-card p-5"
    >
      <SectionHeading
        icon={Network}
        eyebrow="Dependency impact"
        title="Blast radius"
      />
      {!blast ? (
        <DegradedState
          icon={Network}
          text="Blast-radius detail is unavailable; the rest of the briefing is unaffected."
        />
      ) : (
        <>
          <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-4">
            <Metric label="Affected" value={blast.affected_entity_count} />
            <Metric label="Direct" value={blast.direct_impact_count} />
            <Metric label="Indirect" value={blast.indirect_impact_count} />
            <Metric label="Potential" value={blast.potential_impact_count} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {blast.affected_services.map((service) => (
              <StatusBadge key={service} value={service} tone="info" />
            ))}
            {blast.business_capabilities.map((capability) => (
              <StatusBadge key={capability} value={capability} tone="warn" />
            ))}
          </div>
          {blast.important_affected_entities.length > 0 && (
            <details className="mt-4 border-t border-border pt-3">
              <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                View {blast.returned_entity_count} important affected entities
                {blast.omitted_entity_count > 0
                  ? ` (${blast.omitted_entity_count} more omitted)`
                  : ""}
              </summary>
              <div className="mt-3 divide-y divide-border">
                {blast.important_affected_entities.map((entity) => (
                  <div
                    key={entity.entity_id}
                    className="grid gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_120px_90px]"
                  >
                    <div>
                      <p className="text-sm font-semibold">{entity.entity_name}</p>
                      <p className="mt-1 font-mono text-[9px] text-muted-foreground">
                        {entity.entity_kind} · distance {entity.distance}
                      </p>
                    </div>
                    <span className="font-mono text-[10px] uppercase text-muted-foreground">
                      {humanizeToken(entity.impact)}
                    </span>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {formatConfidence(entity.impact_score)}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  )
}

function OwnershipSection({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const context = briefing.operational_context
  const ownership = context?.ownership
  const impact = context?.business_impact

  return (
    <section
      id="ownership"
      className="rounded-md border border-border bg-card p-5"
    >
      <SectionHeading
        icon={Users}
        eyebrow="Response routing"
        title="Owner and business context"
      />
      {!ownership?.resolved ? (
        <DegradedState
          icon={Users}
          text="Root-cause ownership is unresolved. No owner has been inferred."
        />
      ) : (
        <dl className="mt-5 grid gap-4 sm:grid-cols-2">
          <Datum label="Owner team" value={ownership.owner_team} />
          <Datum label="On-call" value={ownership.oncall_contact} />
          <Datum label="Technical service" value={ownership.service_name} />
          <Datum label="Capability" value={ownership.business_capability} />
          <Datum label="Criticality" value={humanizeToken(ownership.criticality)} />
          <Datum label="Repository" value={ownership.repository_url} link />
        </dl>
      )}

      {impact && (
        <div className="mt-5 border-t border-border pt-4">
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Routing recommendation
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {impact.routing_recommendation}
          </p>
          {context.escalation_targets.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {context.escalation_targets.map((target) => (
                <span
                  key={target}
                  className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-background px-2 py-1 font-mono text-[10px]"
                >
                  <PhoneCall className="h-3 w-3 text-info" />
                  {target}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function formatMinutes(value: number): string {
  if (value < 1) {
    return "less than 1 minute"
  }

  const rounded = Math.round(value)
  return `${rounded} minute${rounded === 1 ? "" : "s"}`
}
