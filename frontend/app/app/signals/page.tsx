import { AppTopbar } from "@/components/app/app-topbar"
import { LiveSignalsView } from "@/components/app/live-signals-view"

export default function SignalsPage() {
  return (
    <>
      <AppTopbar
        title="Signals · live events"
        path="app/signals"
        showIncidentContext={false}
      />

      <LiveSignalsView />
    </>
  )
}