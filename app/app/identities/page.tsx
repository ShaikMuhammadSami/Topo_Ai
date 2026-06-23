import { AppTopbar } from "@/components/app/app-topbar"
import { LiveIdentitiesView } from "@/components/app/live-identities-view"

export default function IdentitiesPage() {
  return (
    <>
      <AppTopbar
        title="Identities · live resolution"
        path="app/identities"
        showIncidentContext={false}
      />

      <LiveIdentitiesView />
    </>
  )
}