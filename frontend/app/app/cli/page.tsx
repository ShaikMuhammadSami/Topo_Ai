import { AppTopbar } from "@/components/app/app-topbar"
import { CliView } from "@/components/app/cli-view"

export default function CliPage() {
  return (
    <>
      <AppTopbar title="CLI simulator" path="app/cli" />
      <CliView />
    </>
  )
}
