import type {
  IncidentRecordView,
  IncidentStatus,
  IncidentStatusUpdate,
} from "@/lib/topo-types"

export type SubmissionGate = {
  current: boolean
}

export type IncidentStatusSubmission =
  | {
      outcome: "saved"
      incident: IncidentRecordView
    }
  | {
      outcome: "duplicate"
    }

export function resolutionSuccessHref(
  incidentId: string,
): string {
  return `/app?resolved_incident=${encodeURIComponent(
    incidentId,
  )}`
}

export async function submitIncidentStatus({
  incidentId,
  status,
  note,
  gate,
  updateStatus,
  navigate,
}: {
  incidentId: string
  status: IncidentStatus
  note: string | null
  gate: SubmissionGate
  updateStatus: (
    incidentId: string,
    request: IncidentStatusUpdate,
  ) => Promise<IncidentRecordView>
  navigate: (href: string) => void
}): Promise<IncidentStatusSubmission> {
  if (gate.current) {
    return { outcome: "duplicate" }
  }

  gate.current = true

  try {
    const incident = await updateStatus(
      incidentId,
      { status, note },
    )

    if (incident.status !== status) {
      throw new Error(
        `Incident status was not saved as ${status}.`,
      )
    }

    if (status === "resolved") {
      navigate(
        resolutionSuccessHref(incidentId),
      )
    }

    return {
      outcome: "saved",
      incident,
    }
  } finally {
    gate.current = false
  }
}
