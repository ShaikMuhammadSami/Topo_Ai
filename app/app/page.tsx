import { AppTopbar } from "@/components/app/app-topbar"
import { IncidentWorkspace } from "@/components/app/incident-workspace"

export default function WorkspacePage() {
  return (
    <>
      <AppTopbar title="Incident workspace" path="app" />
      <IncidentWorkspace />
    </>
  )
}
