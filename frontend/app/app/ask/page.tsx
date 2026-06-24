import { AppTopbar } from "@/components/app/app-topbar"
import { AskView } from "@/components/app/ask-view"

export default function AskPage() {
  return (
    <>
      <AppTopbar title="Ask topo" path="app/ask" />
      <AskView />
    </>
  )
}
