import { AppTopbar } from "@/components/app/app-topbar"
import { LiveClusterView } from "@/components/app/live-cluster-view"

export default function LiveClusterPage() {
  return (
    <>
      <AppTopbar
        title="Live cluster"
        path="app/live-cluster"
        showIncidentContext={false}
      />

      <LiveClusterView />
    </>
  )
}