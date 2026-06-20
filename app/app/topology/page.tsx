import { AppTopbar } from "@/components/app/app-topbar"
import { TopologyView } from "@/components/app/topology-view"

export default function TopologyPage() {
  return (
    <>
      <AppTopbar title="Topology · temporal graph" path="app/topology" />
      <TopologyView />
    </>
  )
}
