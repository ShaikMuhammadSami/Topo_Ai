import { Suspense } from "react"

import { AppTopbar } from "@/components/app/app-topbar"
import { IncidentHome } from "@/components/app/incident-home"
import { LiveIncidentWorkspace } from "@/components/app/live-incident-workspace"

export default async function IncidentWorkspacePage({
  searchParams,
}: {
  searchParams: Promise<{
    mode?: string
    analysis_id?: string
    signal_id?: string
    incident_id?: string
  }>
}) {
  const query = await searchParams
  const advanced =
    query.mode === "advanced" ||
    Boolean(
      query.analysis_id ||
      query.signal_id ||
      query.incident_id,
    )

  return (
    <>
      <AppTopbar
        title={
          advanced
            ? "Advanced incident analysis"
            : "Incidents"
        }
        path="app"
        showIncidentContext={false}
      />

      <Suspense fallback={<IncidentLoading />}>
        {advanced ? (
          <LiveIncidentWorkspace />
        ) : (
          <IncidentHome />
        )}
      </Suspense>
    </>
  )
}

function IncidentLoading() {
  return (
    <div className="mx-auto w-full max-w-[1750px] p-5">
      <div className="rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
        Loading incidents…
      </div>
    </div>
  )
}
