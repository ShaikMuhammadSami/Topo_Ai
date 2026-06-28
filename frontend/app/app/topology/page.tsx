import { Suspense } from "react"

import { AppTopbar } from "@/components/app/app-topbar"
import { LiveTopologyView } from "@/components/app/live-topology-view"

export default function TopologyPage() {
  return (
    <>
      <AppTopbar
        title="Topology · live snapshots"
        path="app/topology"
        showIncidentContext={false}
      />

      <Suspense fallback={<TopologyLoading />}>
        <LiveTopologyView />
      </Suspense>
    </>
  )
}

function TopologyLoading() {
  return (
    <div className="mx-auto w-full max-w-[1600px] p-5">
      <div className="rounded-md border border-border bg-card p-6 font-mono text-xs text-muted-foreground">
        Loading topology…
      </div>
    </div>
  )
}