import { Suspense } from "react"

import { AppTopbar } from "@/components/app/app-topbar"
import { IncidentBriefingWorkspace } from "@/components/app/incident-briefing-workspace"

export default async function IncidentBriefingPage({
  params,
}: {
  params: Promise<{
    incidentId: string
  }>
}) {
  const routeParams = await params
  const incidentId = decodeIncidentId(
    routeParams.incidentId,
  )

  return (
    <>
      <AppTopbar
        title="Unified incident briefing"
        path={`app/incidents/${incidentId}`}
        showIncidentContext={false}
      />

      <Suspense fallback={<RouteLoading />}>
        <IncidentBriefingWorkspace
          incidentId={incidentId}
        />
      </Suspense>
    </>
  )
}

function decodeIncidentId(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

function RouteLoading() {
  return (
    <div className="mx-auto w-full max-w-[1540px] p-5">
      <div className="rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
        Loading unified incident briefing…
      </div>
    </div>
  )
}
