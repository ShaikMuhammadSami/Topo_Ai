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

      <LiveTopologyView />
    </>
  )
}