import { AppTopbar } from "@/components/app/app-topbar"
import { IntegrationsView } from "@/components/app/integrations-view"

export default function IntegrationsPage() {
  return (
    <>
      <AppTopbar title="Workflow integrations" path="app/integrations" />
      <IntegrationsView />
    </>
  )
}
