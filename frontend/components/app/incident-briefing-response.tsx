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
  formatConfidence,
  humanizeToken,
  isActiveIncident,
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
          {remediation.actions.map((action, index) => {
            const preview = remediation.previews.find(
              (candidate) =>
                candidate.action_id === action.action_id,
            )

            return (
              <article
                key={action.action_id}
                className={cn(
                  "p-5 sm:p-6",
                  index === 0 &&
                    "bg-primary/[0.035]",
                )}
              >
                <div className="grid gap-4 md:grid-cols-[42px_minmax(0,1fr)_auto]">
                  <span className="flex h-9 w-9 items-center justify-center rounded-sm border border-primary/30 bg-primary/10 font-heading text-lg font-black text-primary">
                    {action.rank}
                  </span>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-heading text-lg font-bold">
                        {action.title}
                      </h3>
                      {firstAction?.action_id === action.action_id && (
                        <span className="font-mono text-[9px] uppercase tracking-widest text-primary">
                          Start here
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {action.description}
                    </p>
                    <p className="mt-3 font-mono text-[10px] text-muted-foreground">
                      Target: {remediationActionTarget(briefing, action)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-start gap-2 md:justify-end">
                    <StatusBadge value={`${action.risk} risk`} tone={riskTone(action.risk)} />
                    <StatusBadge value={action.category} tone="info" />
                    {action.requires_human_approval && (
                      <StatusBadge value="manual review required" tone="warn" />
                    )}
                  </div>
                </div>

                <details className="mt-4 ml-0 border-t border-border pt-3 md:ml-[58px]">
                  <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
                    Why this action and what evidence supports it
                  </summary>
                  <div className="mt-3 grid gap-4 text-sm text-muted-foreground lg:grid-cols-2">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-foreground">
                        Reason
                      </p>
                      <p className="mt-1 leading-relaxed">{action.reason}</p>
                    </div>
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-widest text-foreground">
                        Historical support
                      </p>
                      <p className="mt-1 leading-relaxed">
                        {humanizeToken(action.historical_support.level)} · {action.historical_support.effective_count} effective, {action.historical_support.ineffective_count} ineffective observations
                      </p>
                    </div>
                  </div>
                </details>

                {preview && (
                  <RemediationPreview
                    briefing={briefing}
                    preview={preview}
                  />
                )}
              </article>
            )
          })}
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

function RemediationPreview({
  briefing,
  preview,
}: {
  briefing: IncidentBriefing
  preview: BriefingRemediationPreview
}) {
  return (
    <div className="mt-5 ml-0 rounded-sm border border-info/25 bg-info/5 p-4 md:ml-[58px]">
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
}: {
  briefing: IncidentBriefing
}) {
  const history = briefing.historical_context

  return (
    <section
      id="history"
      className="rounded-md border border-border bg-card p-5"
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
          <div className="mt-4 flex items-end gap-3">
            <span className="font-heading text-4xl font-black text-primary">
              {history.similar_incident_count}
            </span>
            <span className="pb-1 text-sm text-muted-foreground">
              similar · {humanizeToken(history.support_level)} support
            </span>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            {history.summary}
          </p>
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
                      {formatConfidence(incident.similarity)} similar
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
}: {
  briefing: IncidentBriefing
}) {
  const outcome = briefing.outcome

  return (
    <section
      id="outcome"
      className="rounded-md border border-border bg-card p-5"
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
          <dl className="mt-5 grid gap-4 sm:grid-cols-2">
            <Datum label="Resolution action" value={outcome.primary_resolution_action} />
            <Datum label="Final root cause" value={outcome.final_root_cause} />
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
      <div className="grid gap-4 lg:grid-cols-2">
        <details className="rounded-md border border-border bg-card p-4">
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
                    weight {formatConfidence(evidence.weight)}
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

        <details className="rounded-md border border-border bg-card p-4">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-muted-foreground hover:text-foreground">
            Warnings ({briefing.warnings.length})
          </summary>
          <ul className="mt-4 space-y-2 text-xs leading-relaxed text-muted-foreground">
            {briefing.warnings.length === 0 ? (
              <li>No briefing warnings.</li>
            ) : briefing.warnings.map((warning) => (
              <li key={warning} className="flex gap-2">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warn" />
                {warning}
              </li>
            ))}
          </ul>
        </details>
      </div>
    </section>
  )
}
