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
  compactDependencyPath,
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
    <div className="space-y-4 py-4">
      <section
        aria-labelledby="immediate-answer-title"
        className="overflow-hidden rounded-md border border-border bg-card"
      >
        <h2 id="immediate-answer-title" className="sr-only">
          Immediate incident answer
        </h2>
        <div className="grid lg:grid-cols-[minmax(0,1.08fr)_minmax(340px,0.92fr)]">
          <div
            id="what-happened"
            className="border-b border-border p-4 sm:p-5 lg:border-b-0 lg:border-r"
          >
            <Eyebrow icon={Activity}>What happened</Eyebrow>
            <p className="mt-2 max-w-3xl text-base font-medium leading-relaxed sm:text-lg">
              {model.immediate.whatHappened}
            </p>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground sm:text-sm">
              {briefing.incident.current_state}
            </p>
          </div>

          <div
            id="root-cause"
            className="border-l-2 border-l-primary p-4 sm:p-5"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Eyebrow icon={FileSearch}>Likely root cause</Eyebrow>
              <span className="font-heading text-2xl font-black text-primary">
                {formatConfidence(root.causal_confidence)}
              </span>
            </div>
            <h3 className="mt-2 font-heading text-lg font-bold">
              {model.immediate.rootCause}
            </h3>
            <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground sm:text-sm">
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
        <details className="border-l-2 border-info bg-info/5 px-4 py-2.5">
          <summary className="cursor-pointer list-none font-mono text-[10px] uppercase tracking-widest text-info">
            <span className="inline-flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5" />
              AI-assisted responder narrative
            </span>
          </summary>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
            {briefing.ai_summary}
          </p>
        </details>
      )}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.28fr)]">
            <WhatChanged briefing={briefing} />
            <FailurePath briefing={briefing} />
          </div>

          <ResponseGuidance briefing={briefing} firstAction={firstAction} />
          <VerificationPlan briefing={briefing} />
        </div>

        <aside
          aria-label="Incident context"
          className="space-y-4 xl:sticky xl:top-[172px]"
        >
          <BlastRadiusSection briefing={briefing} />
          <OwnershipSection briefing={briefing} />
          <HistoricalContext briefing={briefing} compact />
          <OutcomeSummary briefing={briefing} compact />
        </aside>
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

function WhatChanged({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const changes =
    briefing.recent_relevant_changes
  const primary = changes[0]

  return (
    <section
      id="what-changed"
      className="rounded-md border border-border bg-card p-4"
    >
      <SectionHeading
        icon={GitCommitHorizontal}
        eyebrow="Before symptoms"
        title="What changed"
      />
      {!primary ? (
        <DegradedState
          icon={GitCommitHorizontal}
          text="No durable pre-incident change is linked to this briefing."
        />
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge
              value={primary.change_type ?? primary.role}
              tone="info"
            />
            {primary.minutes_before_incident !== null && (
              <span className="font-mono text-[9px] text-muted-foreground">
                {formatMinutes(primary.minutes_before_incident)} before symptoms
              </span>
            )}
          </div>
          <h3 className="mt-2 text-sm font-semibold leading-snug">
            {primary.title}
          </h3>
          <p className="mt-2 line-clamp-2 font-mono text-[9px] text-muted-foreground">
            {[
              primary.source,
              primary.release_version,
              primary.commit_sha,
            ].filter(Boolean).join(" · ")}
          </p>

          {changes.length > 1 && (
            <details className="mt-3 border-t border-border pt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                View {changes.length - 1} additional relevant change{changes.length === 2 ? "" : "s"}
              </summary>
              <div className="mt-2 divide-y divide-border">
                {changes.slice(1).map((change) => (
                  <div key={change.event_id} className="py-2 text-xs">
                    <p className="font-medium">{change.title}</p>
                    <p className="mt-1 font-mono text-[9px] text-muted-foreground">
                      {change.source ?? change.role}
                    </p>
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

function FailurePath({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  const model = buildIncidentWorkspaceModel(briefing)
  const visiblePath = compactDependencyPath(
    model.technical.dependencyPath,
  )

  return (
    <section
      id="dependency-path"
      className="rounded-md border border-border bg-card p-4"
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
          <ol className="mt-4 flex flex-col gap-2 md:flex-row md:items-stretch">
            {visiblePath.map((step, index) => (
              <li
                key={`${step.node_id}-${step.order}`}
                className="flex min-w-0 flex-1 items-center gap-2"
              >
                {index > 0 && (
                  <ArrowRight className="hidden h-3.5 w-3.5 shrink-0 text-muted-foreground md:block" />
                )}
                <div className="min-w-0 flex-1 rounded-sm border border-border bg-background px-2.5 py-2.5">
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

          <details className="mt-3 border-t border-border pt-2.5">
            <summary className="cursor-pointer font-mono text-[10px] uppercase text-muted-foreground hover:text-foreground">
              {model.technical.dependencyPath.length > visiblePath.length
                ? `View full ${model.technical.dependencyPath.length}-step path and evidence`
                : "View path evidence and IDs"}
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
      className="rounded-md border border-border bg-card p-4"
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
          <div className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border">
            <Metric label="Affected" value={blast.affected_entity_count} />
            <Metric label="Services" value={blast.affected_services.length} />
            <Metric label="Teams" value={blast.affected_teams.length} />
            <Metric label="Direct" value={blast.direct_impact_count} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {blast.affected_services.map((service) => (
              <StatusBadge key={service} value={service} tone="info" />
            ))}
            {blast.business_capabilities.map((capability) => (
              <StatusBadge key={capability} value={capability} tone="warn" />
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
            {blast.indirect_impact_count} indirect and {blast.potential_impact_count} potential impacts are included in the total.
          </p>
          {blast.important_affected_entities.length > 0 && (
            <details className="mt-3 border-t border-border pt-2.5">
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
      className="rounded-md border border-border bg-card p-4"
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
        <dl className="mt-4 grid gap-3">
          <Datum label="Owner team" value={ownership.owner_team} />
          <Datum label="On-call" value={ownership.oncall_contact} />
          <Datum label="Technical service" value={ownership.service_name} />
          <Datum label="Capability" value={ownership.business_capability} />
        </dl>
      )}

      {impact && (
        <details className="mt-4 border-t border-border pt-3">
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
            Routing and owner details
          </summary>
          <div className="mt-3">
            {ownership?.resolved && (
              <dl className="grid gap-3">
                <Datum label="Criticality" value={humanizeToken(ownership.criticality)} />
                <Datum label="Owner email" value={ownership.owner_email} />
                <Datum label="Repository" value={ownership.repository_url} link />
              </dl>
            )}
            <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
              {impact.routing_recommendation}
            </p>
            {context.escalation_targets.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {context.escalation_targets.map((target) => (
                  <span
                    key={target}
                    className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-background px-2 py-1 font-mono text-[9px]"
                  >
                    <PhoneCall className="h-3 w-3 text-info" />
                    {target}
                  </span>
                ))}
              </div>
            )}
          </div>
        </details>
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
