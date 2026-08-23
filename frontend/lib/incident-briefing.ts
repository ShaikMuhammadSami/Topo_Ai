import type {
  BriefingAffectedEntity,
  BriefingCausalPathStep,
  BriefingRemediationAction,
  IncidentBriefing,
} from "@/lib/topo-types"

export type IncidentWorkspaceMode =
  | "technical"
  | "business"

export const TECHNICAL_SECTION_ORDER = [
  "what-happened",
  "root-cause",
  "impact",
  "next-action",
  "what-changed",
  "dependency-path",
  "blast-radius",
  "ownership",
  "remediation",
  "verification",
  "history",
  "outcome",
  "evidence",
] as const

export function compactDependencyPath(
  steps: BriefingCausalPathStep[],
  limit = 5,
): BriefingCausalPathStep[] {
  if (steps.length <= limit) {
    return steps
  }

  const leadingCount = Math.max(
    1,
    Math.ceil(limit / 2),
  )
  const trailingCount = Math.max(
    1,
    limit - leadingCount,
  )

  return [
    ...steps.slice(0, leadingCount),
    ...steps.slice(-trailingCount),
  ]
}

export function partitionRemediationActions(
  actions: BriefingRemediationAction[],
  primaryLimit = 3,
): {
  primary: BriefingRemediationAction[]
  additional: BriefingRemediationAction[]
} {
  return {
    primary: actions.slice(0, primaryLimit),
    additional: actions.slice(primaryLimit),
  }
}

export function incidentWorkspaceMode(
  value: string | null | undefined,
): IncidentWorkspaceMode {
  return value === "business"
    ? "business"
    : "technical"
}

export function incidentWorkspaceHref(
  incidentId: string,
  mode: IncidentWorkspaceMode = "technical",
): string {
  const base = `/app/incidents/${encodeURIComponent(
    incidentId,
  )}`

  return mode === "business"
    ? `${base}?view=business`
    : base
}

export function incidentTopologyHref(
  briefing: IncidentBriefing,
): string | null {
  const snapshotId =
    briefing.root_cause.topology_snapshot_id
  const entityId =
    briefing.root_cause.root_entity_id

  if (!snapshotId || !entityId) {
    return null
  }

  return `/app/topology?snapshot_id=${encodeURIComponent(
    snapshotId,
  )}&entity_id=${encodeURIComponent(
    entityId,
  )}`
}

export function formatNormalizedScore(
  score: number,
): string {
  return score.toFixed(2)
}

export function formatRankingScore(
  score: number | null | undefined,
): string {
  return score === null || score === undefined
    ? "Legacy rank"
    : `${score.toFixed(1)} / 100`
}

export function humanizeToken(
  value: string | null | undefined,
): string {
  if (!value) {
    return "Not available"
  }

  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) =>
      letter.toUpperCase(),
    )
}

export function formatBriefingDuration(
  seconds: number | null | undefined,
): string | null {
  if (seconds === null || seconds === undefined) {
    return null
  }

  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.floor(seconds / 60)

  if (minutes < 60) {
    return `${minutes}m`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60

  if (hours < 24) {
    return remainingMinutes > 0
      ? `${hours}h ${remainingMinutes}m`
      : `${hours}h`
  }

  const days = Math.floor(hours / 24)
  const remainingHours = hours % 24

  return remainingHours > 0
    ? `${days}d ${remainingHours}h`
    : `${days}d`
}

export function incidentElapsedSeconds(
  briefing: IncidentBriefing,
  now = Date.now(),
): number | null {
  const startedAt = Date.parse(
    briefing.incident.first_observed_at,
  )

  if (Number.isNaN(startedAt)) {
    return null
  }

  const endedAt = briefing.outcome?.resolved_at
    ? Date.parse(briefing.outcome.resolved_at)
    : now

  if (Number.isNaN(endedAt)) {
    return null
  }

  return Math.max(
    0,
    Math.floor((endedAt - startedAt) / 1000),
  )
}

export function affectedEntityLabel(
  briefing: IncidentBriefing,
  entityId: string,
): string {
  const entity = [
    ...(briefing.blast_radius
      ?.important_affected_entities ?? []),
    ...(
      briefing.remediation?.previews.flatMap(
        (preview) =>
          preview.potentially_impacted_entities,
      ) ?? []
    ),
  ].find(
    (candidate) =>
      candidate.entity_id === entityId,
  )

  if (entity) {
    return entity.entity_name
  }

  const ownership =
    briefing.operational_context?.ownership

  if (ownership?.entity_id === entityId) {
    return (
      ownership.service_name ??
      briefing.incident.affected_object_name ??
      entityId
    )
  }

  return entityId
}

export function buildIncidentWorkspaceModel(
  briefing: IncidentBriefing,
) {
  const context = briefing.operational_context
  const ownership = context?.ownership
  const impact = context?.business_impact
  const firstAction =
    briefing.remediation?.actions[0] ?? null
  const capability =
    ownership?.business_capability ??
    impact?.business_capabilities[0] ??
    briefing.blast_radius
      ?.business_capabilities[0] ??
    null
  const service =
    ownership?.service_name ??
    briefing.blast_radius
      ?.affected_services[0] ??
    briefing.incident.affected_object_name ??
    null
  const primaryImpact =
    capability ?? service ?? "Impact is being assessed"
  const owner =
    ownership?.resolved && ownership.owner_team
      ? ownership.owner_team
      : "Ownership unavailable"
  const affectedCount =
    briefing.blast_radius
      ?.affected_entity_count ??
    impact?.affected_entity_count ??
    0
  const businessImpactLevel =
    impact?.business_impact_level ?? null
  const causeTitle =
    briefing.root_cause.causal_change_title ||
    briefing.root_cause.root_event_title

  return {
    immediate: {
      whatHappened: briefing.summary.text,
      rootCause: causeTitle,
      rootCauseSummary:
        briefing.root_cause.summary,
      causalConfidence:
        briefing.root_cause.causal_confidence,
      primaryImpact,
      owner,
      nextAction:
        firstAction?.title ??
        "No response action is available yet",
    },
    technical: {
      changes:
        briefing.recent_relevant_changes,
      dependencyPath:
        briefing.dependency_path,
      affectedCount,
      actions:
        briefing.remediation?.actions ?? [],
      affectedEntities:
        briefing.blast_radius
          ?.important_affected_entities ?? [],
      topologyHref:
        incidentTopologyHref(briefing),
    },
    business: {
      affected: primaryImpact,
      service,
      environment:
        briefing.incident.environment ??
        briefing.incident.cluster_name,
      seriousness: [
        briefing.incident.severity.toUpperCase(),
        impact?.highest_criticality
          ? humanizeToken(
              impact.highest_criticality,
            )
          : null,
        affectedCount > 0
          ? `${affectedCount} infrastructure component${
              affectedCount === 1 ? "" : "s"
            } affected`
          : null,
      ].filter(
        (item): item is string =>
          Boolean(item),
      ),
      cause: `${causeTitle} is the leading cause identified by the causal analysis.`,
      owner,
      currentResponse:
        firstAction?.description ??
        firstAction?.title ??
        "The response path is still being established.",
      status: briefing.incident.status,
      businessImpactLevel,
      historicalSummary:
        briefing.historical_context
          .similar_incident_count > 0
          ? briefing.historical_context.summary
          : null,
    },
    degraded: {
      ownershipUnavailable:
        !ownership?.resolved,
      historyUnavailable:
        briefing.historical_context
          .similar_incident_count === 0,
      outcomeUnavailable:
        briefing.outcome === null,
      aiUnavailable:
        !briefing.ai_summary,
      dependencyPathUnavailable:
        briefing.dependency_path.length === 0,
      remediationUnavailable:
        !briefing.remediation ||
        briefing.remediation.actions.length === 0,
      blastRadiusUnavailable:
        briefing.blast_radius === null,
    },
  }
}

export function isMutationControlLabel(
  label: string,
): boolean {
  return /\b(execute|auto[- ]?fix|rollback now|restart now|approve (?:and|&) execute)\b/i.test(
    label,
  )
}

export function isActiveIncident(
  briefing: IncidentBriefing,
): boolean {
  return ![
    "resolved",
    "dismissed",
  ].includes(briefing.incident.status)
}

export function remediationActionTarget(
  briefing: IncidentBriefing,
  action: BriefingRemediationAction,
): string {
  if (action.entity_ids.length === 0) {
    return "No specific target recorded"
  }

  return action.entity_ids
    .map((entityId) =>
      affectedEntityLabel(
        briefing,
        entityId,
      ),
    )
    .join(", ")
}

export function importantEntitySummary(
  entities: BriefingAffectedEntity[],
): string {
  if (entities.length === 0) {
    return "No affected entity detail is available."
  }

  return entities
    .map((entity) => entity.entity_name)
    .join(", ")
}
