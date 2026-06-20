import { AppTopbar } from "@/components/app/app-topbar"
import { IdentitiesView } from "@/components/app/identities-view"

export default function IdentitiesPage() {
  return (
    <>
      <AppTopbar title="Identity resolution" path="app/identities" />
      <IdentitiesView />
    </>
  )
}
