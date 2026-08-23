import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  History,
  ShieldAlert,
  Wrench,
} from "lucide-react"

import {
  affectedEntityLabel,
  formatBriefingDuration,
  formatNormalizedScore,
  humanizeToken,
  isActiveIncident,
  partitionRemediationActions,
  remediationActionTarget,
} from "@/lib/incident-briefing"
import type {
  BriefingRemediationAction,
  BriefingRemediationPreview,
  IncidentBriefing,
} from "@/lib/topo-types"
import { cn } from "@/lib/utils"
import {
  BulletList,
  Datum,
  DegradedState,
  PreviewDatum,
  SectionHeading,
  StatusBadge,
  riskTone,
} from "@/components/app/incident-briefing-ui"

export function ResponseGuidance({
  briefing,
  firstAction,
}: {
  briefing: IncidentBriefing
  firstAction: BriefingRemediationAction | null
}) {
  const remediation = briefing.remediation
  const actionGroups = partitionRemediationActions(
    remediation?.actions ?? [],
  )

  return (
    <section
      id="remediation"
      className="rounded-md border border-border bg-card"
    >
      <div className="border-b border-border p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <SectionHeading
            icon={Wrench}
            eyebrow="Read-only response guidance"
            title="What should I do next?"
          />
          {remediation && (
            <div className="text-right">
              <StatusBadge
                value={`${remediation.response_priority} response`}
                tone="warn"
              />
              <p className="mt-2 max-w-md text-xs text-muted-foreground">
                {remediation.response_priority_reason}
              </p>
            </div>
          )}
        </div>
      </div>

      {!remediation || remediation.actions.length === 0 ? (
        <div className="p-5">
          <DegradedState
            icon={Wrench}
            text="No remediation or investigation action is available yet."
          />
        </div>
      ) : (
        <div className="divide-y divide-border">
          {actionGroups.primary.map((action) => (
            <ActionRow
              key={action.action_id}
              briefing={briefing}
              action={action}
              preview={remediation.previews.find(
                (candidate) =>
                  candidate.action_id === action.action_id,
              )}
              startHere={firstAction?.action_id === action.action_id}
            />
          ))}

          {actionGroups.additional.length > 0 && (
            <details className="bg-background/25">
              <summary className="cursor-pointer px-5 py-4 text-xs font-semibold text-muted-foreground hover:text-foreground sm:px-6">
                Show {actionGroups.additional.length} additional response action{actionGroups.additional.length === 1 ? "" : "s"}
              </summary>
              <div className="divide-y divide-border border-t border-border">
                {actionGroups.additional.map((action) => (
                  <ActionRow
                    key={action.action_id}
                    briefing={briefing}
                    action={action}
                    preview={remediation.previews.find(
                      (candidate) =>
                        candidate.action_id === action.action_id,
                    )}
                    startHere={false}
                    compact
                  />
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {remediation?.read_only && (
        <footer className="flex items-center gap-2 border-t border-border bg-background/50 px-5 py-3 font-mono text-[10px] text-muted-foreground">
          <ShieldAlert className="h-3.5 w-3.5 text-info" />
          Guidance only. Topo does not modify infrastructure from this workspace.
        </footer>
      )}
    </section>
  )
}

function ActionRow({
  briefing,
  action,
  preview,
  startHere,
  compact = false,
}: {
  briefing: IncidentBriefing
  action: BriefingRemediationAction
  preview: BriefingRemediationPreview | undefined
  startHere: boolean
  compact?: boolean
}) {
  return (
    <article
      className={cn(
        "px-5 py-4 sm:px-6",
        startHere && "bg-primary/[0.035]",
      )}
    >
      <div className="grid gap-3 sm:grid-cols-[32px_minmax(0,1fr)_auto] sm:items-start">
        <span className="flex h-7 w-7 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 font-heading text-sm font-black text-primary">
          {action.rank}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-heading text-base font-bold">
              {action.title}
            </h3>
            {startHere && (
              <span className="font-mono text-[9px] uppercase tracking-widest text-primary">
                Start here
              </span>
            )}
          </div>
          {!compact && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {action.description}
            </p>
          )}
          <p className="mt-1.5 font-mono text-[9px] text-muted-foreground">
            Target: {remediationActionTarget(briefing, action)} · {humanizeToken(action.historical_support.level)} history
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 sm:justify-end">
          <StatusBadge value={`${action.risk} risk`} tone={riskTone(action.risk)} />
          <StatusBadge value={action.category} tone="info" />
          {action.requires_human_approval && (
            <StatusBadge value="manual review" tone="warn" />
          )}
        </div>
      </div>

      <details className="mt-3 border-t border-border pt-2.5 sm:ml-11">
        <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
          Review rationale, potential impact and verification
        </summary>
        <div className="mt-3 grid gap-4 text-xs text-muted-foreground lg:grid-cols-2">
          <div>
            <p className="font-mono text-[9px] uppercase tracking-widest text-foreground">
              Why
            </p>
            <p className="mt-1 leading-relaxed">{action.reason}</p>
          </div>
          <div>
            <p className="font-mono text-[9px] uppercase tracking-widest text-foreground">
              Historical support
            </p>
            <p className="mt-1 leading-relaxed">
              {action.historical_support.effective_count} effective, {action.historical_support.ineffective_count} ineffective and {action.historical_support.unknown_effect_count} unknown observations.
            </p>
          </div>
        </div>

        {preview && (
          <RemediationPreview
            briefing={briefing}
            preview={preview}
          />
        )}
      </details>
    </article>
  )
}

function RemediationPreview({
  briefing,
  preview,
}: {
  briefing: IncidentBriefing
  preview: BriefingRemediationPreview
}) {
  return (
    <div className="mt-4 rounded-sm border border-info/25 bg-info/5 p-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-info">
        Remediation preview · evidence-based, not a simulation
      </p>
      <p className="mt-3 text-sm leading-relaxed">
        {preview.intended_effect}
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <PreviewDatum
          label="Target"
          value={
            preview.affected_target.entity_ids.length > 0
              ? preview.affected_target.entity_ids
                  .map((entityId) =>
                    affectedEntityLabel(briefing, entityId),
                  )
                  .join(", ")
              : "Change context only"
          }
        />
        <PreviewDatum
          label="Potential impact"
          value={
            preview.potentially_impacted_entities.length > 0
              ? preview.potentially_impacted_entities
                  .slice(0, 4)
                  .map((entity) => entity.entity_name)
                  .join(", ")
              : preview.potential_impact_scope_note
          }
        />
        <PreviewDatum
          label="If successful"
          value={preview.expected_observation_if_successful}
        />
        <PreviewDatum
          label="Risk"
          value={humanizeToken(preview.risk)}
        />
      </div>

      {(preview.possible_failure_modes.length > 0 ||
        preview.historical_observations.length > 0) && (
        <details className="mt-4 border-t border-info/20 pt-3">
          <summary className="cursor-pointer text-xs font-medium text-info hover:underline">
            Caveats and historical observations
          </summary>
          <div className="mt-3 grid gap-4 text-xs leading-relaxed text-muted-foreground lg:grid-cols-2">
            <BulletList
              title="What could go wrong"
              items={preview.possible_failure_modes}
              empty="No structured failure mode was recorded."
            />
            <BulletList
              title="Historical evidence"
              items={preview.historical_observations}
              empty="No historical observation supports this preview yet."
            />
          </div>
        </details>
      )}
    </div>
  )
}

export function VerificationPlan({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  return (
    <section
      id="verification"
      className="rounded-md border border-ok/25 bg-ok/[0.035] p-5 sm:p-6"
    >
      <SectionHeading
        icon={CheckCircle2}
        eyebrow="After manual remediation"
        title="How to verify recovery"
      />

      {briefing.verification_plan.length === 0 ? (
        <DegradedState
          icon={CheckCircle2}
          text="No validation steps are available for the current response plan."
        />
      ) : (
        <ol className="mt-5 grid gap-3 lg:grid-cols-2">
          {briefing.verification_plan.map((step) => (
            <li
              key={step.step_id}
              className="flex gap-3 rounded-sm border border-border bg-background/60 p-4"
            >
              <span
                aria-hidden="true"
                className="mt-0.5 h-4 w-4 shrink-0 rounded-sm border border-ok/60"
              />
              <div>
                <h3 className="text-sm font-semibold">
                  {step.title}
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {step.description}
                </p>
                <p className="mt-2 font-mono text-[10px] text-ok">
                  Expected: {step.expected_observation}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

export function HistoricalContext({
  briefing,
  compact = false,
}: {
  briefing: IncidentBriefing
  compact?: boolean
}) {
  const history = briefing.historical_context
  const confirmedCount =
    history.similar_incidents.filter(
      (incident) =>
        incident.rca_verdict === "confirmed",
    ).length
  const effectiveCount =
    history.similar_incidents.filter(
      (incident) =>
        incident.primary_action_effectiveness ===
        "effective",
    ).length

  return (
    <section
      id="history"
      className={cn(
        "rounded-md border border-border bg-card",
        compact ? "p-4" : "p-5",
      )}
    >
      <SectionHeading
        icon={History}
        eyebrow="Incident memory"
        title="Similar incidents"
      />

      {history.similar_incident_count === 0 ? (
        <DegradedState
          icon={History}
          text="No similar resolved incidents were found. This is not an error."
        />
      ) : (
        <>
          <div className="mt-4 flex items-end gap-2">
            <span className={cn(
              "font-heading font-black text-primary",
              compact ? "text-3xl" : "text-4xl",
            )}>
              {history.similar_incident_count}
            </span>
            <span className="pb-1 text-sm text-muted-foreground">
              similar · {humanizeToken(history.support_level)} support
            </span>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {history.summary}
          </p>
          {compact && (
            <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-sm border border-border bg-border text-center">
              <div className="bg-background px-2 py-2">
                <p className="font-heading text-lg font-bold">{confirmedCount}</p>
                <p className="font-mono text-[8px] uppercase text-muted-foreground">confirmed</p>
              </div>
              <div className="bg-background px-2 py-2">
                <p className="font-heading text-lg font-bold">{effectiveCount}</p>
                <p className="font-mono text-[8px] uppercase text-muted-foreground">effective</p>
              </div>
            </div>
          )}
          <details className="mt-4 border-t border-border pt-3">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
              View historical cases
            </summary>
            <div className="mt-3 divide-y divide-border">
              {history.similar_incidents.map((incident) => (
                <article key={incident.incident_id} className="py-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">
                      {incident.incident_title}
                    </p>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      similarity score {formatNormalizedScore(incident.similarity)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {incident.resolution_summary}
                  </p>
                  <p className="mt-2 font-mono text-[10px] uppercase text-muted-foreground">
                    {humanizeToken(incident.rca_verdict)}
                    {incident.primary_resolution_action
                      ? ` · ${incident.primary_resolution_action}`
                      : ""}
                  </p>
                </article>
              ))}
            </div>
          </details>
        </>
      )}
    </section>
  )
}

export function OutcomeSummary({
  briefing,
  compact = false,
}: {
  briefing: IncidentBriefing
  compact?: boolean
}) {
  const outcome = briefing.outcome

  return (
    <section
      id="outcome"
      className={cn(
        "rounded-md border border-border bg-card",
        compact ? "p-4" : "p-5",
      )}
    >
      <SectionHeading
        icon={CheckCircle2}
        eyebrow="Current resolution state"
        title="Outcome"
      />

      {!outcome ? (
        <DegradedState
          icon={Clock3}
          text={
            isActiveIncident(briefing)
              ? "Incident still active. Outcome has not been recorded yet."
              : "The incident is closed, but a structured outcome is not available."
          }
        />
      ) : (
        <div className="mt-5">
          <div className="flex flex-wrap gap-2">
            <StatusBadge value={outcome.status} tone="ok" />
            <StatusBadge value={outcome.final_rca_verdict} tone="info" />
          </div>
          <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
            {outcome.resolution_summary}
          </p>
          <dl className={cn(
            "mt-5 grid gap-4",
            compact ? "grid-cols-1" : "sm:grid-cols-2",
          )}>
            {!compact && (
              <>
                <Datum label="Resolution action" value={outcome.primary_resolution_action} />
                <Datum label="Final root cause" value={outcome.final_root_cause} />
              </>
            )}
            <Datum
              label="Time to mitigation"
              value={formatBriefingDuration(outcome.time_to_mitigation_seconds)}
            />
            <Datum
              label="Time to resolution"
              value={formatBriefingDuration(outcome.time_to_resolution_seconds)}
            />
          </dl>
        </div>
      )}
    </section>
  )
}

export function EvidenceAndWarnings({
  briefing,
}: {
  briefing: IncidentBriefing
}) {
  return (
    <section id="evidence" className="border-t border-border pt-5">
      {briefing.warnings.length > 0 && (
        <div className="mb-3 flex items-start gap-3 rounded-sm border border-warn/30 bg-warn/5 px-3 py-2.5">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
          <div className="min-w-0 flex-1">
            <p className="text-xs leading-relaxed text-muted-foreground">
              {briefing.warnings[0]}
            </p>
            {briefing.warnings.length > 1 && (
              <details className="mt-2">
                <summary className="cursor-pointer font-mono text-[9px] uppercase text-warn">
                  View {briefing.warnings.length - 1} more warning{briefing.warnings.length === 2 ? "" : "s"}
                </summary>
                <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-muted-foreground">
                  {briefing.warnings.slice(1).map((warning) => (
                    <li key={warning}>• {warning}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <details className="rounded-md border border-border bg-card p-3.5">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground">
            View causal evidence ({briefing.causal_evidence.length})
          </summary>
          <div className="mt-4 divide-y divide-border">
            {briefing.causal_evidence.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No expanded evidence records are available.
              </p>
            ) : briefing.causal_evidence.map((evidence) => (
              <article key={evidence.evidence_id} className="py-3 first:pt-0">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-semibold">{evidence.title}</p>
                  <span className="font-mono text-[9px] text-muted-foreground">
                    evidence weight {formatNormalizedScore(evidence.weight)}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {evidence.detail}
                </p>
                <p className="mt-2 break-all font-mono text-[9px] text-muted-foreground">
                  {evidence.evidence_id}
                </p>
              </article>
            ))}
          </div>
        </details>

        <details className="rounded-md border border-border bg-card p-3.5">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground">
            Technical metadata
          </summary>
          <dl className="mt-4 space-y-2 font-mono text-[9px] text-muted-foreground">
            <Datum label="Causal analysis" value={briefing.root_cause.causal_analysis_id} />
            <Datum label="Root event" value={briefing.root_cause.root_event_id} />
            <Datum label="Root entity" value={briefing.root_cause.root_entity_id} />
            <Datum label="Topology snapshot" value={briefing.root_cause.topology_snapshot_id} />
          </dl>
        </details>
      </div>
    </section>
  )
}
