import { Suspense } from "react"

import { AppTopbar } from "@/components/app/app-topbar"
import { LiveIncidentWorkspace } from "@/components/app/live-incident-workspace"

export default function IncidentWorkspacePage() {
  return (
    <>
      <AppTopbar
        title="Incident workspace · live analysis"
        path="app"
        showIncidentContext={false}
      />

      <Suspense fallback={<IncidentLoading />}>
        <LiveIncidentWorkspace />
      </Suspense>
    </>
  )
}

function IncidentLoading() {
  return (
    <div className="mx-auto w-full max-w-[1750px] p-5">
      <div className="rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
        Loading incident workspace…
      </div>
    </div>
  )
}