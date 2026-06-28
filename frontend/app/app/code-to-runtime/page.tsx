import { AppTopbar } from "@/components/app/app-topbar"
import { CodeToRuntimeView } from "@/components/app/code-to-runtime-view"

export default function CodeToRuntimePage() {
  return (
    <>
      <AppTopbar
        title="Code to runtime"
        path="app/code-to-runtime"
        showIncidentContext={false}
      />

      <CodeToRuntimeView />
    </>
  )
}