import { AppTopbar } from "@/components/app/app-topbar"
import { CliView } from "@/components/app/cli-view"

export default function CliPage() {
  return (
    <>
      <AppTopbar title="Topo CLI" path="app/cli" />
      <CliView />
    </>
  )
}
