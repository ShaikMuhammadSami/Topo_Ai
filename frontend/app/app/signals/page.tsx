import { Suspense } from "react"

import { AppTopbar } from "@/components/app/app-topbar"
import { LiveSignalsView } from "@/components/app/live-signals-view"

export default function SignalsPage() {
  return (
    <>
      <AppTopbar
        title="Signals & changes · live evidence"
        path="app/signals"
        showIncidentContext={false}
      />

      <Suspense fallback={<SignalsLoading />}>
        <LiveSignalsView />
      </Suspense>
    </>
  )
}

function SignalsLoading() {
  return (
    <div className="mx-auto w-full max-w-[1700px] p-5">
      <div className="rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
        Loading signals and changes…
      </div>
    </div>
  )
}