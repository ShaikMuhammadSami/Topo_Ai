import { AppTopbar } from "@/components/app/app-topbar"
import { SignalsView } from "@/components/app/signals-view"

export default function SignalsPage() {
  return (
    <>
      <AppTopbar title="Signals & changes" path="app/signals" />
      <SignalsView />
    </>
  )
}
