import type {
  IncidentRecordSummary,
  IncidentStatus,
} from "@/lib/topo-types"

export type IncidentHomeScope =
  | "attention"
  | "recent"

const INACTIVE_STATUSES: IncidentStatus[] = [
  "resolved",
  "dismissed",
]

export function incidentNeedsAttention(
  incident: IncidentRecordSummary,
): boolean {
  return !INACTIVE_STATUSES.includes(
    incident.status,
  )
}

export function filterIncidentHomeRecords(
  incidents: IncidentRecordSummary[],
  options: {
    query?: string
    scope?: IncidentHomeScope
  } = {},
): IncidentRecordSummary[] {
  const query = options.query
    ?.trim()
    .toLocaleLowerCase()
  const scope = options.scope ?? "attention"

  return incidents
    .filter((incident) =>
      scope === "recent" ||
      incidentNeedsAttention(incident),
    )
    .filter((incident) => {
      if (!query) {
        return true
      }

      return [
        incident.title,
        incident.incident_id,
        incident.cluster_name,
        incident.namespace,
        incident.affected_object_kind,
        incident.affected_object_name,
        incident.top_hypothesis_title,
      ]
        .filter(Boolean)
        .some((value) =>
          value
            ?.toLocaleLowerCase()
            .includes(query),
        )
    })
    .toSorted(
      (left, right) =>
        Date.parse(right.last_observed_at) -
        Date.parse(left.last_observed_at),
    )
}
